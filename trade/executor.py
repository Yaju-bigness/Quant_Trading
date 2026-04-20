"""
实盘交易执行器
支持：模拟盘、通达信实盘（需开通）
"""
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
import time
import threading
from queue import Queue

try:
    from pytdx.trade import TdxTradeApi
    TDX_TRADE_AVAILABLE = True
except ImportError:
    TDX_TRADE_AVAILABLE = False

from strategy.base import TradeSignal, Signal
from data.data_source import DataSource


class TradeExecutor:
    """交易执行器基类"""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Dict] = {}  # {stock_code: {quantity, avg_cost}}
        self.trade_history: List[Dict] = []
        self.data_source = DataSource(use_tdx=False)

    def get_position(self, stock_code: str) -> Dict:
        """获取持仓"""
        return self.positions.get(stock_code, {'quantity': 0, 'avg_cost': 0})

    def get_total_value(self, prices: Dict[str, float]) -> float:
        """计算总资产"""
        position_value = sum(
            pos['quantity'] * prices.get(code, pos.get('current_price', 0))
            for code, pos in self.positions.items()
        )
        return self.cash + position_value

    def execute_signal(self, signal: TradeSignal, stock_code: str,
                       stock_name: str, quantity: int = None) -> bool:
        """
        执行交易信号
        :param signal: 交易信号
        :param stock_code: 股票代码
        :param stock_name: 股票名称
        :param quantity: 交易数量（None则自动计算）
        :return: 是否成功
        """
        raise NotImplementedError

    def sync_positions(self):
        """同步持仓信息"""
        pass


class PaperTrader(TradeExecutor):
    """模拟盘交易"""

    def __init__(self, initial_capital: float = 100000,
                 commission_rate: float = 0.0003,
                 stamp_duty: float = 0.001,
                 slippage: float = 0.001):
        super().__init__(initial_capital)
        self.commission_rate = commission_rate
        self.stamp_duty = stamp_duty
        self.slippage = slippage

    def execute_signal(self, signal: TradeSignal, stock_code: str,
                       stock_name: str, quantity: int = None) -> bool:
        """执行交易信号（模拟）"""

        if quantity is None:
            # 自动计算仓位
            if signal.signal == Signal.BUY:
                position_ratio = 0.3 * signal.confidence
                quantity = int(self.cash * position_ratio / signal.price / 100) * 100
            else:
                quantity = self.get_position(stock_code)['quantity']

        if quantity <= 0:
            logger.warning(f"交易数量为0，跳过")
            return False

        # 计算实际价格（含滑点）
        is_buy = signal.signal == Signal.BUY
        actual_price = signal.price * (1 + self.slippage * (1 if is_buy else -1))
        amount = actual_price * quantity

        # 计算手续费
        commission = max(amount * self.commission_rate, 5)
        if not is_buy:
            commission += amount * self.stamp_duty

        # 执行交易
        if is_buy:
            total_cost = amount + commission
            if total_cost > self.cash:
                logger.warning(f"资金不足: 需要{total_cost:.2f}, 可用{self.cash:.2f}")
                return False

            self.cash -= total_cost

            if stock_code in self.positions:
                pos = self.positions[stock_code]
                total_qty = pos['quantity'] + quantity
                pos['avg_cost'] = (pos['avg_cost'] * pos['quantity'] + amount) / total_qty
                pos['quantity'] = total_qty
            else:
                self.positions[stock_code] = {
                    'quantity': quantity,
                    'avg_cost': actual_price,
                    'stock_name': stock_name
                }

            logger.info(f"[模拟买入] {stock_name} {quantity}股 @ {actual_price:.2f}, "
                       f"金额{amount:.2f}, 手续费{commission:.2f}")
        else:
            pos = self.get_position(stock_code)
            if quantity > pos['quantity']:
                logger.warning(f"持仓不足: 需要{quantity}, 持有{pos['quantity']}")
                return False

            self.cash += amount - commission

            if quantity == pos['quantity']:
                del self.positions[stock_code]
            else:
                self.positions[stock_code]['quantity'] -= quantity

            logger.info(f"[模拟卖出] {stock_name} {quantity}股 @ {actual_price:.2f}, "
                       f"金额{amount:.2f}, 手续费{commission:.2f}")

        # 记录交易
        self.trade_history.append({
            'time': datetime.now(),
            'stock_code': stock_code,
            'stock_name': stock_name,
            'action': 'buy' if is_buy else 'sell',
            'price': actual_price,
            'quantity': quantity,
            'amount': amount,
            'commission': commission,
            'reason': signal.reason
        })

        return True


class TdxTrader(TradeExecutor):
    """通达信实盘交易（优化版：重试机制+防重复提交）"""

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config
        self.trade_api = None
        self._pending_orders: Dict[str, float] = {}  # {stock_code: last_submit_time}
        self._dedup_interval = 5.0  # 防重复提交间隔(秒)
        self._connect()

    def _connect(self):
        """连接交易服务器"""
        if not TDX_TRADE_AVAILABLE:
            logger.error("pytdx未安装，无法使用实盘交易")
            return False

        try:
            self.trade_api = TdxTradeApi()
            result = self.trade_api.connect(
                self.config.get('host', '119.29.51.120'),
                self.config.get('port', 7709)
            )
            if result:
                logger.info("交易服务器连接成功")
                # 登录
                login_result = self.trade_api.login(
                    self.config.get('account', ''),
                    self.config.get('password', '')
                )
                if login_result:
                    logger.info("交易账户登录成功")
                    self.sync_positions()
                    return True
                else:
                    logger.error("交易账户登录失败")
            else:
                logger.error("交易服务器连接失败")
        except Exception as e:
            logger.error(f"交易服务器连接异常: {e}")

        return False

    def sync_positions(self):
        """同步持仓信息"""
        if not self.trade_api:
            return

        try:
            # 查询持仓
            result = self.trade_api.query_data(0)  # 0=持仓查询
            if result:
                for pos in result:
                    self.positions[pos['code']] = {
                        'quantity': pos.get('vol', 0),
                        'available': pos.get('enable_balance', 0),
                        'avg_cost': pos.get('cost_price', 0),
                        'current_price': pos.get('price', 0),
                        'profit_loss': pos.get('income_balance', 0)
                    }
                logger.info(f"持仓同步完成，共{len(self.positions)}只股票")

            # 查询资金
            fund_result = self.trade_api.query_data(1)  # 1=资金查询
            if fund_result:
                self.cash = fund_result[0].get('enable_balance', 0)
                logger.info(f"可用资金: {self.cash:.2f}")

        except Exception as e:
            logger.error(f"同步持仓失败: {e}")

    def execute_signal(self, signal: TradeSignal, stock_code: str,
                       stock_name: str, quantity: int = None) -> bool:
        """执行交易信号（实盘，带重试和防重复）"""

        if not self.trade_api:
            logger.error("未连接交易服务器")
            return False

        # 防重复提交检查
        now = time.time()
        if stock_code in self._pending_orders:
            elapsed = now - self._pending_orders[stock_code]
            if elapsed < self._dedup_interval:
                logger.warning(f"防重复提交: {stock_code} 在{elapsed:.1f}秒内已提交过")
                return False

        if quantity is None:
            if signal.signal == Signal.BUY:
                position_ratio = 0.3 * signal.confidence
                quantity = int(self.cash * position_ratio / signal.price / 100) * 100
            else:
                quantity = self.get_position(stock_code).get('available', 0)

        if quantity <= 0:
            logger.warning("交易数量为0，跳过")
            return False

        # 带重试的执行
        result = self._execute_with_retry(signal, stock_code, stock_name, quantity)

        if result:
            self._pending_orders[stock_code] = time.time()

        return result

    def _execute_with_retry(self, signal: TradeSignal, stock_code: str,
                             stock_name: str, quantity: int,
                             max_retries: int = 3, retry_interval: float = 0.1) -> bool:
        """带重试的交易执行"""
        market = 1 if stock_code.startswith('6') else 0

        for attempt in range(1, max_retries + 1):
            try:
                if signal.signal == Signal.BUY:
                    result = self.trade_api.buy(
                        market, stock_code, signal.price, quantity
                    )
                    if result:
                        logger.info(f"[买入委托] {stock_name} {quantity}股 @ {signal.price:.2f}")
                        self.trade_history.append({
                            'time': datetime.now(),
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'action': 'buy',
                            'price': signal.price,
                            'quantity': quantity,
                            'reason': signal.reason
                        })
                        return True
                else:
                    result = self.trade_api.sell(
                        market, stock_code, signal.price, quantity
                    )
                    if result:
                        logger.info(f"[卖出委托] {stock_name} {quantity}股 @ {signal.price:.2f}")
                        self.trade_history.append({
                            'time': datetime.now(),
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'action': 'sell',
                            'price': signal.price,
                            'quantity': quantity,
                            'reason': signal.reason
                        })
                        return True

                # 执行失败
                if attempt < max_retries:
                    logger.warning(f"交易执行失败，第{attempt}次重试...")
                    time.sleep(retry_interval)
                else:
                    logger.error(f"交易执行失败，已重试{max_retries}次")

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"交易异常: {e}，第{attempt}次重试...")
                    time.sleep(retry_interval)
                else:
                    logger.error(f"交易执行异常，已重试{max_retries}次: {e}")

        return False

    def query_orders(self) -> List[Dict]:
        """查询委托单"""
        if not self.trade_api:
            return []

        try:
            result = self.trade_api.query_data(2)  # 2=当日委托
            return result if result else []
        except Exception as e:
            logger.error(f"查询委托失败: {e}")
            return []

    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if not self.trade_api:
            return False

        try:
            result = self.trade_api.cancel(order_id)
            if result:
                logger.info(f"撤单成功: {order_id}")
                return True
        except Exception as e:
            logger.error(f"撤单失败: {e}")

        return False

    def disconnect(self):
        """断开连接"""
        if self.trade_api:
            self.trade_api.disconnect()
            logger.info("交易服务器已断开")


class LiveTradingEngine:
    """
    实时交易引擎
    支持实时监控和自动交易
    """

    def __init__(self, trader: TradeExecutor,
                 strategies: List,
                 stock_list: Dict[str, str]):
        """
        :param trader: 交易执行器
        :param strategies: 策略列表
        :param stock_list: 股票列表 {name: code}
        """
        self.trader = trader
        self.strategies = strategies
        self.stock_list = stock_list
        self.data_source = DataSource(use_tdx=False)

        self.running = False
        self.signal_queue = Queue()
        self.latest_prices = {}

    def start(self, interval: int = 60):
        """
        启动实时交易
        :param interval: 监控间隔(秒)
        """
        self.running = True
        logger.info(f"实时交易引擎启动，监控间隔{interval}秒")

        while self.running:
            try:
                self._monitor()
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                logger.error(f"监控异常: {e}")
                time.sleep(10)

    def stop(self):
        """停止实时交易"""
        self.running = False
        logger.info("实时交易引擎已停止")

    def _monitor(self):
        """监控循环"""
        logger.info("开始新一轮监控...")

        # 获取实时行情
        stock_codes = list(self.stock_list.values())
        quotes = self.data_source.get_realtime_quote(stock_codes)

        if quotes.empty:
            logger.warning("无法获取实时行情")
            return

        # 更新最新价格
        for _, row in quotes.iterrows():
            self.latest_prices[row['code']] = row['price']

        # 对每只股票执行策略
        for name, code in self.stock_list.items():
            try:
                self._process_stock(name, code, quotes)
            except Exception as e:
                logger.error(f"处理股票{name}失败: {e}")

    def _process_stock(self, stock_name: str, stock_code: str, quotes: pd.DataFrame):
        """处理单只股票"""

        # 获取最近K线数据
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.Timedelta(days=100)).strftime('%Y-%m-%d')

        kline = self.data_source.get_daily_kline(stock_code, start_date, end_date)
        if kline.empty:
            return

        # 执行每个策略
        for strategy in self.strategies:
            signals = strategy.generate_signals(kline)

            # 只处理最新信号
            if signals:
                latest_signal = signals[-1]

                # 检查信号是否在最近1天内
                latest_date = kline['date'].iloc[-1]
                if (datetime.now() - latest_date.to_pydatetime()).days <= 1:
                    # 执行交易
                    self.trader.execute_signal(
                        latest_signal,
                        stock_code,
                        stock_name
                    )

    def get_account_summary(self) -> Dict:
        """获取账户摘要"""
        return {
            'cash': self.trader.cash,
            'positions': self.trader.positions,
            'total_value': self.trader.get_total_value(self.latest_prices),
            'trade_count': len(self.trader.trade_history)
        }

    def print_status(self):
        """打印当前状态"""
        summary = self.get_account_summary()
        print("\n" + "="*50)
        print(f"账户状态 @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*50)
        print(f"可用资金: {summary['cash']:.2f}")
        print(f"总资产: {summary['total_value']:.2f}")
        print(f"\n持仓:")
        for code, pos in summary['positions'].items():
            print(f"  {pos.get('stock_name', code)}: {pos['quantity']}股")
        print("="*50 + "\n")


def create_trader(mode: str = 'paper', config: Dict = None) -> TradeExecutor:
    """
    创建交易执行器
    :param mode: 'paper'=模拟盘, 'live'=实盘
    :param config: 配置信息
    """
    if mode == 'live':
        if not config:
            raise ValueError("实盘交易需要配置信息")
        return TdxTrader(config)
    else:
        return PaperTrader(initial_capital=config.get('initial_capital', 100000))


if __name__ == '__main__':
    # 测试模拟盘
    from strategy.technical import CompositeStrategy

    trader = PaperTrader(initial_capital=100000)
    strategy = CompositeStrategy()

    stocks = {'中际旭创': '300308', '江波龙': '301308', '长飞光纤': '601869'}

    engine = LiveTradingEngine(trader, [strategy], stocks)

    # 运行一次监控（测试）
    # engine._monitor()
    # engine.print_status()

    # 持续运行
    # engine.start(interval=60)
