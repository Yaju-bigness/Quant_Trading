"""
回测引擎
支持：事件驱动回测、完整交易模拟、绩效分析、风险管理
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 配置中文字体
plt.rcParams['font.family'] = ['Arial Unicode MS', 'PingFang HK', 'Kaiti SC', 'Lantinghei SC', 'Heiti TC', 'STHeiti', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

from strategy.base import BaseStrategy, TradeSignal, Signal
from data.data_source import DataSource
from data.data_manager import DataManager, DataCache
from risk.manager import RiskManager, RiskConfig, StopLossType
from analysis.performance import PerformanceAnalyzer, PerformanceMetrics


@dataclass
class Trade:
    """交易记录"""
    date: datetime
    stock_code: str
    stock_name: str
    action: str  # 'buy' or 'sell'
    price: float
    quantity: int
    amount: float
    commission: float
    reason: str = ""


@dataclass
class Position:
    """持仓信息"""
    stock_code: str
    stock_name: str
    quantity: int = 0
    avg_cost: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def profit_loss(self) -> float:
        return (self.current_price - self.avg_cost) * self.quantity

    @property
    def profit_loss_pct(self) -> float:
        if self.avg_cost == 0:
            return 0
        return (self.current_price - self.avg_cost) / self.avg_cost


@dataclass
class Portfolio:
    """投资组合"""
    initial_capital: float
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def profit_loss(self) -> float:
        return self.total_value - self.initial_capital

    @property
    def profit_loss_pct(self) -> float:
        return (self.total_value - self.initial_capital) / self.initial_capital


class BacktestEngine:
    """回测引擎"""

    def __init__(self,
                 initial_capital: float = 100000,
                 commission_rate: float = 0.0003,
                 stamp_duty: float = 0.001,
                 slippage: float = 0.001,
                 min_trade_unit: int = 100,
                 risk_config: RiskConfig = None,
                 use_cache: bool = True):
        """
        初始化回测引擎
        :param initial_capital: 初始资金
        :param commission_rate: 佣金率
        :param stamp_duty: 印花税（仅卖出）
        :param slippage: 滑点
        :param min_trade_unit: 最小交易单位
        :param risk_config: 风险配置
        :param use_cache: 是否使用数据缓存
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.stamp_duty = stamp_duty
        self.slippage = slippage
        self.min_trade_unit = min_trade_unit

        self.data_source = DataSource(use_tdx=False)
        self.data_manager = DataManager(use_cache=use_cache)
        self.risk_config = risk_config or RiskConfig()
        self.risk_manager = RiskManager(self.risk_config)
        self.performance_analyzer = PerformanceAnalyzer()

        self.portfolio = None
        self.equity_curve = []
        self.daily_returns = []
        self.benchmark_curve = []

    def reset(self):
        """重置回测状态"""
        self.portfolio = Portfolio(
            initial_capital=self.initial_capital,
            cash=self.initial_capital
        )
        self.equity_curve = []
        self.daily_returns = []
        self.benchmark_curve = []
        self.risk_manager = RiskManager(self.risk_config)

    def _calculate_commission(self, amount: float, is_sell: bool) -> float:
        """计算交易成本"""
        commission = amount * self.commission_rate
        commission = max(commission, 5)  # 最低5元

        if is_sell:
            commission += amount * self.stamp_duty

        return commission

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """应用滑点"""
        if is_buy:
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)

    def _execute_trade(self,
                       date: datetime,
                       stock_code: str,
                       stock_name: str,
                       action: str,
                       price: float,
                       quantity: int,
                       reason: str = "") -> bool:
        """
        执行交易
        :return: 是否成功
        """
        if quantity <= 0 or quantity % self.min_trade_unit != 0:
            logger.warning(f"交易数量不合法: {quantity}")
            return False

        # 应用滑点
        actual_price = self._apply_slippage(price, action == 'buy')

        # 计算金额和手续费
        amount = actual_price * quantity
        is_sell = action == 'sell'
        commission = self._calculate_commission(amount, is_sell)

        if action == 'buy':
            # 买入检查资金
            total_cost = amount + commission
            if total_cost > self.portfolio.cash:
                logger.warning(f"资金不足: 需要{total_cost:.2f}, 可用{self.portfolio.cash:.2f}")
                return False

            # 执行买入
            self.portfolio.cash -= total_cost

            if stock_code in self.portfolio.positions:
                pos = self.portfolio.positions[stock_code]
                total_quantity = pos.quantity + quantity
                pos.avg_cost = (pos.avg_cost * pos.quantity + amount) / total_quantity
                pos.quantity = total_quantity
            else:
                self.portfolio.positions[stock_code] = Position(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    quantity=quantity,
                    avg_cost=actual_price,
                    current_price=actual_price
                )

        else:  # sell
            # 卖出检查持仓
            if stock_code not in self.portfolio.positions:
                logger.warning(f"无持仓: {stock_code}")
                return False

            pos = self.portfolio.positions[stock_code]
            if quantity > pos.quantity:
                logger.warning(f"持仓不足: 需要{quantity}, 持有{pos.quantity}")
                return False

            # 执行卖出
            self.portfolio.cash += amount - commission
            pos.quantity -= quantity

            if pos.quantity == 0:
                del self.portfolio.positions[stock_code]

        # 记录交易
        trade = Trade(
            date=date,
            stock_code=stock_code,
            stock_name=stock_name,
            action=action,
            price=actual_price,
            quantity=quantity,
            amount=amount,
            commission=commission,
            reason=reason
        )
        self.portfolio.trades.append(trade)

        logger.info(f"{date.strftime('%Y-%m-%d')} {action.upper()} {stock_name} "
                   f"{quantity}股 @ {actual_price:.2f}, 手续费{commission:.2f}")

        return True

    def run_backtest(self,
                     strategy: BaseStrategy,
                     stock_code: str,
                     stock_name: str,
                     start_date: str,
                     end_date: str,
                     data: pd.DataFrame = None) -> Dict:
        """
        运行回测（优化版：信号索引查找提升速度）
        """
        self.reset()

        # 获取数据
        if data is None:
            data = self.data_source.get_daily_kline(stock_code, start_date, end_date)

        if data.empty:
            logger.error(f"无法获取数据: {stock_code}")
            return {}

        # 生成信号
        signals = strategy.generate_signals(data)

        # 将信号按日期索引（优化：O(1)查找替代O(n)遍历）
        signal_dict = {}
        for sig in signals:
            # 根据价格和日期匹配
            mask = data['close'] == sig.price
            if mask.any():
                sig_date = data.loc[mask.index[0], 'date'] if mask.any() else None
                # 尝试更精确的匹配：找最后一个匹配日期
                matched = data[mask]
                if not matched.empty:
                    sig_date = matched['date'].iloc[0]
                    if sig_date not in signal_dict:
                        signal_dict[sig_date] = []
                    signal_dict[sig_date].append(sig)

        # 预构建日期索引集合，加速查找
        date_set = set(data['date'].tolist())

        # 遍历每个交易日
        for idx, row in data.iterrows():
            date = row['date']
            close_price = row['close']

            # 更新持仓市值
            for code, pos in self.portfolio.positions.items():
                pos.current_price = close_price

            # 记录每日净值
            self.equity_curve.append({
                'date': date,
                'equity': self.portfolio.total_value,
                'cash': self.portfolio.cash,
                'position_value': self.portfolio.total_value - self.portfolio.cash
            })

            # 执行交易信号
            if date in signal_dict:
                for sig in signal_dict[date]:
                    if sig.signal == Signal.BUY:
                        quantity = strategy.calculate_position(
                            self.portfolio.cash, sig.price, sig
                        )
                        if quantity > 0:
                            self._execute_trade(
                                date, stock_code, stock_name,
                                'buy', sig.price, quantity, sig.reason
                            )
                    elif sig.signal == Signal.SELL:
                        if stock_code in self.portfolio.positions:
                            pos = self.portfolio.positions[stock_code]
                            if pos.quantity > 0:
                                self._execute_trade(
                                    date, stock_code, stock_name,
                                    'sell', sig.price, pos.quantity, sig.reason
                                )

        # 计算收益
        self._calculate_daily_returns()

        return self._generate_report(stock_code, stock_name)

    def run_portfolio_backtest(self,
                                strategies: Dict[str, BaseStrategy],
                                stock_list: Dict[str, str],
                                start_date: str,
                                end_date: str) -> Dict:
        """
        多标的组合回测：每只股票独立生成信号，共享资金池
        :param strategies: {stock_code: strategy} 每只股票对应的策略
        :param stock_list: {name: code} 股票列表
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 组合回测报告
        """
        self.reset()
        all_signals = {}  # {date: [(stock_code, signal)]}

        # 为每只股票获取数据并生成信号
        for name, code in stock_list.items():
            strategy = strategies.get(code, list(strategies.values())[0]) if strategies else None
            if strategy is None:
                continue

            data = self.data_source.get_daily_kline(code, start_date, end_date)
            if data.empty:
                continue

            signals = strategy.generate_signals(data)
            for sig in signals:
                mask = data['close'] == sig.price
                if mask.any():
                    sig_date = data.loc[mask.index[0], 'date']
                    if sig_date not in all_signals:
                        all_signals[sig_date] = []
                    all_signals[sig_date].append((code, name, sig))

        # 获取所有交易日
        first_code = list(stock_list.values())[0]
        all_dates = self.data_source.get_daily_kline(first_code, start_date, end_date)
        if all_dates.empty:
            return {}

        # 遍历交易日
        for _, row in all_dates.iterrows():
            date = row['date']

            # 更新所有持仓市值
            for code, pos in self.portfolio.positions.items():
                # 简化：使用同一天的数据
                pos.current_price = row['close']

            self.equity_curve.append({
                'date': date,
                'equity': self.portfolio.total_value,
                'cash': self.portfolio.cash,
                'position_value': self.portfolio.total_value - self.portfolio.cash
            })

            # 执行信号
            if date in all_signals:
                for code, name, sig in all_signals[date]:
                    if sig.signal == Signal.BUY:
                        strategy = strategies.get(code, list(strategies.values())[0])
                        quantity = strategy.calculate_position(
                            self.portfolio.cash, sig.price, sig
                        )
                        if quantity > 0:
                            self._execute_trade(date, code, name, 'buy', sig.price, quantity, sig.reason)
                    elif sig.signal == Signal.SELL:
                        if code in self.portfolio.positions:
                            pos = self.portfolio.positions[code]
                            if pos.quantity > 0:
                                self._execute_trade(date, code, name, 'sell', sig.price, pos.quantity, sig.reason)

        self._calculate_daily_returns()
        return self._generate_report('PORTFOLIO', '组合回测')

    def significance_test(self, report: Dict, benchmark_return: float = 0.03,
                           n_bootstrap: int = 1000) -> Dict:
        """
        统计显著性检验
        :param report: 回测报告
        :param benchmark_return: 基准年化收益率
        :param n_bootstrap: Bootstrap采样次数
        :return: 检验结果
        """
        from scipy import stats as scipy_stats

        if not report or not self.daily_returns:
            return {'significant': False, 'reason': '数据不足'}

        returns = np.array(self.daily_returns)
        result = {}

        # 1. t检验：策略日均收益是否显著大于0
        daily_benchmark = (1 + benchmark_return) ** (1/252) - 1
        excess_returns = returns - daily_benchmark

        if len(excess_returns) > 1:
            t_stat, p_value = scipy_stats.ttest_1samp(excess_returns, 0)
            result['t_stat'] = t_stat
            result['p_value'] = p_value / 2  # 单侧检验
            result['t_significant'] = p_value / 2 < 0.05
        else:
            result['t_significant'] = False

        # 2. Bootstrap置信区间
        bootstrap_returns = []
        n = len(returns)
        for _ in range(n_bootstrap):
            sample = np.random.choice(returns, size=n, replace=True)
            bootstrap_returns.append(np.mean(sample) * 252)

        ci_lower = np.percentile(bootstrap_returns, 2.5)
        ci_upper = np.percentile(bootstrap_returns, 97.5)
        result['bootstrap_ci'] = (ci_lower, ci_upper)
        result['bootstrap_significant'] = ci_lower > benchmark_return

        # 3. 综合判断
        result['significant'] = result.get('t_significant', False) or result.get('bootstrap_significant', False)
        result['annual_return'] = report.get('annual_return', 0)
        result['benchmark_return'] = benchmark_return

        return result

    def _calculate_daily_returns(self):
        """计算每日收益"""
        if len(self.equity_curve) < 2:
            return

        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i-1]['equity']
            curr_equity = self.equity_curve[i]['equity']
            daily_return = (curr_equity - prev_equity) / prev_equity
            self.daily_returns.append(daily_return)

    def _generate_report(self, stock_code: str, stock_name: str) -> Dict:
        """生成回测报告"""
        if not self.equity_curve:
            return {}

        # 使用PerformanceAnalyzer计算高级指标
        metrics: PerformanceMetrics = self.performance_analyzer.calculate_metrics(
            self.equity_curve,
            self.benchmark_curve if self.benchmark_curve else None,
            [{'date': t.date, 'action': t.action, 'stock_code': t.stock_code,
              'price': t.price, 'quantity': t.quantity, 'commission': t.commission}
             for t in self.portfolio.trades]
        )

        # 交易统计
        trades = self.portfolio.trades
        buy_trades = [t for t in trades if t.action == 'buy']
        sell_trades = [t for t in trades if t.action == 'sell']

        total_trades = len(trades)
        total_commission = sum(t.commission for t in trades)

        # 盈亏统计
        profit_trades = 0
        loss_trades = 0
        total_profit = 0
        total_loss = 0

        # 配对买卖计算盈亏
        for i, sell in enumerate(sell_trades):
            buy = None
            for t in buy_trades:
                if t.stock_code == sell.stock_code and t.date < sell.date:
                    buy = t
                    break

            if buy:
                profit = (sell.price - buy.price) * sell.quantity - sell.commission - buy.commission
                if profit > 0:
                    profit_trades += 1
                    total_profit += profit
                else:
                    loss_trades += 1
                    total_loss += abs(profit)

        total_closed = profit_trades + loss_trades
        win_rate = profit_trades / total_closed if total_closed > 0 else 0

        report = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'initial_capital': self.initial_capital,
            'final_capital': self.portfolio.total_value,
            # 收益指标
            'total_return': metrics.total_return,
            'annual_return': metrics.annual_return,
            'excess_return': metrics.excess_return,
            # 风险指标
            'volatility': metrics.volatility,
            'max_drawdown': metrics.max_drawdown,
            'var_95': metrics.var_95,
            'cvar_95': metrics.cvar_95,
            # 风险调整收益
            'sharpe_ratio': metrics.sharpe_ratio,
            'sortino_ratio': metrics.sortino_ratio,
            'calmar_ratio': metrics.calmar_ratio,
            'information_ratio': metrics.information_ratio,
            # Alpha/Beta
            'alpha': metrics.alpha,
            'beta': metrics.beta,
            'r_squared': metrics.r_squared,
            # 交易统计
            'total_trades': total_trades,
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'win_rate': win_rate,
            'profit_factor': metrics.profit_factor,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'total_commission': total_commission,
            # 收益分布
            'skewness': metrics.skewness,
            'kurtosis': metrics.kurtosis,
            # 原始数据
            'equity_curve': self.equity_curve,
            'trades': trades
        }

        return report

    def plot_results(self, report: Dict, save_path: str = None):
        """绘制回测结果"""
        if not report or 'equity_curve' not in report:
            logger.error("无回测数据")
            return

        equity_df = pd.DataFrame(report['equity_curve'])

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # 1. 资金曲线
        ax1 = axes[0, 0]
        ax1.plot(equity_df['date'], equity_df['equity'], label='总资产', linewidth=2)
        ax1.axhline(y=report['initial_capital'], color='r', linestyle='--', label='初始资金')
        ax1.set_title(f"{report['stock_name']} 资金曲线")
        ax1.set_xlabel('日期')
        ax1.set_ylabel('资产')
        ax1.legend()
        ax1.grid(True)

        # 2. 收益率曲线
        ax2 = axes[0, 1]
        returns = (equity_df['equity'] / report['initial_capital'] - 1) * 100
        ax2.plot(equity_df['date'], returns, label='累计收益率%', color='green')
        ax2.axhline(y=0, color='r', linestyle='--')
        ax2.set_title('累计收益率')
        ax2.set_xlabel('日期')
        ax2.set_ylabel('收益率(%)')
        ax2.legend()
        ax2.grid(True)

        # 3. 持仓市值 vs 现金
        ax3 = axes[1, 0]
        ax3.fill_between(equity_df['date'], 0, equity_df['cash'],
                        alpha=0.3, label='现金')
        ax3.fill_between(equity_df['date'], equity_df['cash'],
                        equity_df['equity'], alpha=0.3, label='持仓市值')
        ax3.set_title('资产构成')
        ax3.set_xlabel('日期')
        ax3.set_ylabel('金额')
        ax3.legend()
        ax3.grid(True)

        # 4. 关键指标
        ax4 = axes[1, 1]
        ax4.axis('off')
        metrics_text = f"""
        回测报告
        ━━━━━━━━━━━━━━━━━━━━━━━
        股票: {report['stock_name']} ({report['stock_code']})

        收益指标:
          总收益率: {report['total_return']*100:.2f}%
          年化收益率: {report['annual_return']*100:.2f}%
          夏普比率: {report['sharpe_ratio']:.2f}
          索提诺比率: {report.get('sortino_ratio', 0):.2f}
          卡玛比率: {report.get('calmar_ratio', 0):.2f}
          最大回撤: {report['max_drawdown']*100:.2f}%

        风险指标:
          年化波动率: {report.get('volatility', 0)*100:.2f}%
          VaR(95%): {report.get('var_95', 0)*100:.2f}%

        交易统计:
          总交易次数: {report['total_trades']}
          胜率: {report['win_rate']*100:.1f}%
          盈利因子: {report.get('profit_factor', 0):.2f}

        盈亏统计:
          总盈利: {report['total_profit']:.2f}
          总亏损: {report['total_loss']:.2f}
          总手续费: {report['total_commission']:.2f}
        """
        ax4.text(0.1, 0.9, metrics_text, transform=ax4.transAxes,
                fontsize=11, verticalalignment='top')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"图表已保存: {save_path}")

        plt.show()

    def compare_strategies(self,
                          strategies: List[BaseStrategy],
                          stock_code: str,
                          stock_name: str,
                          start_date: str,
                          end_date: str) -> Dict:
        """
        对比多个策略
        """
        results = {}
        data = self.data_source.get_daily_kline(stock_code, start_date, end_date)

        for strategy in strategies:
            logger.info(f"回测策略: {strategy.name}")
            report = self.run_backtest(strategy, stock_code, stock_name,
                                       start_date, end_date, data)
            results[strategy.name] = report

        # 绘制对比图
        self._plot_comparison(results, stock_name)

        return results

    def _plot_comparison(self, results: Dict, stock_name: str):
        """绘制策略对比图"""
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # 收益对比
        ax1 = axes[0]
        for name, report in results.items():
            if report and 'equity_curve' in report:
                equity_df = pd.DataFrame(report['equity_curve'])
                returns = (equity_df['equity'] / report['initial_capital'] - 1) * 100
                ax1.plot(equity_df['date'], returns, label=name, linewidth=2)

        ax1.set_title(f'{stock_name} 策略收益对比')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('收益率(%)')
        ax1.legend()
        ax1.grid(True)

        # 指标对比
        ax2 = axes[1]
        metrics = ['total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate']
        metric_names = ['总收益率', '夏普比率', '最大回撤', '胜率']

        x = np.arange(len(metrics))
        width = 0.8 / len(results)

        for i, (name, report) in enumerate(results.items()):
            if report:
                values = [report.get(m, 0) for m in metrics]
                # 标准化显示
                display_values = [
                    values[0] * 100,  # 收益率转百分比
                    values[1],         # 夏普比率
                    values[2] * 100,   # 回撤转百分比
                    values[3] * 100    # 胜率转百分比
                ]
                ax2.bar(x + i * width, display_values, width, label=name)

        ax2.set_title('策略指标对比')
        ax2.set_xticks(x + width * (len(results) - 1) / 2)
        ax2.set_xticklabels(metric_names)
        ax2.legend()
        ax2.grid(True, axis='y')

        plt.tight_layout()
        plt.show()


if __name__ == '__main__':
    # 测试回测
    from strategy.technical import CompositeStrategy, MACDStrategy

    engine = BacktestEngine(initial_capital=100000)

    # 单策略回测
    strategy = CompositeStrategy()
    report = engine.run_backtest(
        strategy,
        '300308',
        '中际旭创',
        '2024-01-01',
        '2024-12-31'
    )

    if report:
        engine.plot_results(report)

    # 多策略对比
    # strategies = [CompositeStrategy(), MACDStrategy()]
    # results = engine.compare_strategies(strategies, '300308', '中际旭创',
    #                                     '2024-01-01', '2024-12-31')
