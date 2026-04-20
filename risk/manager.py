"""
风险管理模块
包含：止损止盈、追踪止损、ATR动态止损、仓位控制等
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from loguru import logger
from datetime import datetime


class StopLossType(Enum):
    """止损类型"""
    FIXED = "fixed"           # 固定百分比止损
    ATR = "atr"               # ATR动态止损
    TRAILING = "trailing"     # 追踪止损
    SUPPORT = "support"       # 支撑位止损
    TIME = "time"             # 时间止损


@dataclass
class RiskConfig:
    """风险配置"""
    max_position_pct: float = 0.2      # 单只股票最大仓位比例
    max_total_position_pct: float = 0.8  # 总仓位上限
    max_sector_pct: float = 0.3        # 单行业最大仓位
    max_single_loss_pct: float = 0.02  # 单笔最大亏损占总资金比例
    max_daily_loss_pct: float = 0.05   # 单日最大亏损
    max_drawdown_pct: float = 0.15     # 最大回撤限制
    stop_loss_pct: float = 0.08        # 默认止损比例 8%
    take_profit_pct: float = 0.15      # 默认止盈比例 15%
    trailing_stop_pct: float = 0.05    # 追踪止损回撤比例 5%
    atr_multiplier: float = 2.0        # ATR止损倍数
    risk_free_rate: float = 0.03       # 无风险利率


@dataclass
class PositionRisk:
    """持仓风险信息"""
    stock_code: str
    stock_name: str
    entry_price: float
    current_price: float
    quantity: int
    highest_price: float  # 持仓期间最高价
    lowest_price: float   # 持仓期间最低价
    entry_date: datetime
    stop_loss_price: float
    take_profit_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    risk_amount: float    # 风险敞口金额


class StopLossManager:
    """止损止盈管理器"""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self.position_risks: Dict[str, PositionRisk] = {}

    def calculate_stop_loss(self, entry_price: float, stop_type: StopLossType,
                           atr: float = None, support_level: float = None,
                           lowest_low: float = None) -> float:
        """
        计算止损价格
        :param entry_price: 入场价格
        :param stop_type: 止损类型
        :param atr: ATR值
        :param support_level: 支撑位
        :param lowest_low: 最近最低价
        :return: 止损价格
        """
        if stop_type == StopLossType.FIXED:
            return entry_price * (1 - self.config.stop_loss_pct)

        elif stop_type == StopLossType.ATR:
            if atr is None:
                logger.warning("ATR止损需要ATR值，使用固定止损")
                return entry_price * (1 - self.config.stop_loss_pct)
            return entry_price - self.config.atr_multiplier * atr

        elif stop_type == StopLossType.SUPPORT:
            if support_level is None:
                logger.warning("支撑位止损需要支撑位，使用固定止损")
                return entry_price * (1 - self.config.stop_loss_pct)
            return support_level * 0.98  # 支撑位下方2%

        elif stop_type == StopLossType.TRAILING:
            # 追踪止损需要配合update_trailing_stop使用
            return entry_price * (1 - self.config.trailing_stop_pct)

        else:
            return entry_price * (1 - self.config.stop_loss_pct)

    def calculate_take_profit(self, entry_price: float,
                             stop_loss_price: float = None,
                             risk_reward_ratio: float = 2.0) -> float:
        """
        计算止盈价格
        :param entry_price: 入场价格
        :param stop_loss_price: 止损价格
        :param risk_reward_ratio: 风险收益比
        :return: 止盈价格
        """
        if stop_loss_price:
            risk = entry_price - stop_loss_price
            return entry_price + risk * risk_reward_ratio
        return entry_price * (1 + self.config.take_profit_pct)

    def update_trailing_stop(self, stock_code: str, current_price: float) -> Optional[float]:
        """
        更新追踪止损
        :param stock_code: 股票代码
        :param current_price: 当前价格
        :return: 新止损价格（如果触发则返回None）
        """
        if stock_code not in self.position_risks:
            return None

        pos_risk = self.position_risks[stock_code]

        # 更新最高价
        if current_price > pos_risk.highest_price:
            pos_risk.highest_price = current_price
            # 更新止损价格
            new_stop = current_price * (1 - self.config.trailing_stop_pct)
            if new_stop > pos_risk.stop_loss_price:
                pos_risk.stop_loss_price = new_stop
                logger.info(f"追踪止损更新: {stock_code} 新止损价 {new_stop:.2f}")

        # 检查是否触发止损
        if current_price <= pos_risk.stop_loss_price:
            logger.warning(f"追踪止损触发: {stock_code} 当前价 {current_price:.2f} <= 止损价 {pos_risk.stop_loss_price:.2f}")
            return None

        return pos_risk.stop_loss_price

    def check_stop_loss(self, stock_code: str, current_price: float) -> Tuple[bool, str]:
        """
        检查是否触发止损
        :return: (是否触发, 原因)
        """
        if stock_code not in self.position_risks:
            return False, ""

        pos_risk = self.position_risks[stock_code]

        if current_price <= pos_risk.stop_loss_price:
            loss_pct = (current_price - pos_risk.entry_price) / pos_risk.entry_price * 100
            return True, f"触发止损: 当前价{current_price:.2f}, 止损价{pos_risk.stop_loss_price:.2f}, 亏损{loss_pct:.2f}%"

        return False, ""

    def check_take_profit(self, stock_code: str, current_price: float) -> Tuple[bool, str]:
        """
        检查是否触发止盈
        :return: (是否触发, 原因)
        """
        if stock_code not in self.position_risks:
            return False, ""

        pos_risk = self.position_risks[stock_code]

        if current_price >= pos_risk.take_profit_price:
            profit_pct = (current_price - pos_risk.entry_price) / pos_risk.entry_price * 100
            return True, f"触发止盈: 当前价{current_price:.2f}, 止盈价{pos_risk.take_profit_price:.2f}, 盈利{profit_pct:.2f}%"

        return False, ""

    def add_position(self, stock_code: str, stock_name: str,
                    entry_price: float, quantity: int,
                    stop_type: StopLossType = StopLossType.FIXED,
                    atr: float = None):
        """添加持仓到风险监控"""
        stop_loss_price = self.calculate_stop_loss(entry_price, stop_type, atr)
        take_profit_price = self.calculate_take_profit(entry_price, stop_loss_price)

        self.position_risks[stock_code] = PositionRisk(
            stock_code=stock_code,
            stock_name=stock_name,
            entry_price=entry_price,
            current_price=entry_price,
            quantity=quantity,
            highest_price=entry_price,
            lowest_price=entry_price,
            entry_date=datetime.now(),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            unrealized_pnl=0,
            unrealized_pnl_pct=0,
            risk_amount=(entry_price - stop_loss_price) * quantity
        )

        logger.info(f"添加风险监控: {stock_name} 入场价{entry_price:.2f}, "
                   f"止损价{stop_loss_price:.2f}, 止盈价{take_profit_price:.2f}")

    def remove_position(self, stock_code: str):
        """移除持仓监控"""
        if stock_code in self.position_risks:
            del self.position_risks[stock_code]
            logger.info(f"移除风险监控: {stock_code}")

    def update_position_price(self, stock_code: str, current_price: float):
        """更新持仓价格"""
        if stock_code not in self.position_risks:
            return

        pos = self.position_risks[stock_code]
        pos.current_price = current_price
        pos.highest_price = max(pos.highest_price, current_price)
        pos.lowest_price = min(pos.lowest_price, current_price)
        pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
        pos.unrealized_pnl_pct = (current_price - pos.entry_price) / pos.entry_price


class PositionSizer:
    """仓位管理器"""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()

    def fixed_fractional(self, capital: float, price: float,
                        risk_pct: float = None) -> int:
        """
        固定比例仓位
        :param capital: 总资金
        :param price: 当前价格
        :param risk_pct: 仓位比例
        :return: 股数（整手）
        """
        ratio = risk_pct or self.config.max_position_pct
        amount = capital * ratio
        return int(amount / price / 100) * 100

    def kelly_criterion(self, capital: float, price: float,
                       win_rate: float, avg_win: float, avg_loss: float) -> int:
        """
        Kelly公式计算最优仓位
        K = W - (1-W)/R
        W: 胜率, R: 盈亏比
        :param capital: 总资金
        :param price: 当前价格
        :param win_rate: 胜率
        :param avg_win: 平均盈利
        :param avg_loss: 平均亏损
        :return: 股数
        """
        if avg_loss == 0:
            return self.fixed_fractional(capital, price)

        # 计算盈亏比
        R = avg_win / avg_loss

        # Kelly比例
        kelly_pct = win_rate - (1 - win_rate) / R

        # 使用半Kelly降低风险
        kelly_pct = max(0, kelly_pct * 0.5)

        # 限制最大仓位
        kelly_pct = min(kelly_pct, self.config.max_position_pct)

        logger.info(f"Kelly仓位比例: {kelly_pct*100:.2f}% (胜率{win_rate*100:.1f}%, 盈亏比{R:.2f})")

        return int(capital * kelly_pct / price / 100) * 100

    def atr_based(self, capital: float, price: float, atr: float,
                  risk_pct: float = None) -> int:
        """
        基于ATR的仓位管理
        风险金额 = 资金 * 风险比例
        每股风险 = ATR * 倍数
        仓位 = 风险金额 / 每股风险
        """
        risk_pct = risk_pct or self.config.max_single_loss_pct
        risk_amount = capital * risk_pct
        risk_per_share = atr * self.config.atr_multiplier

        if risk_per_share <= 0:
            return self.fixed_fractional(capital, price)

        shares = risk_amount / risk_per_share
        shares = int(shares / 100) * 100

        # 检查最大仓位限制
        max_shares = int(capital * self.config.max_position_pct / price / 100) * 100
        shares = min(shares, max_shares)

        logger.info(f"ATR仓位: 风险金额{risk_amount:.0f}, 每股风险{risk_per_share:.2f}, 股数{shares}")

        return shares

    def volatility_parity(self, capital: float, price: float,
                          volatility: float, target_vol: float = 0.15) -> int:
        """
        波动率平价仓位
        根据资产波动率调整仓位，使每个持仓的风险贡献相等
        :param capital: 总资金
        :param price: 当前价格
        :param volatility: 资产年化波动率
        :param target_vol: 目标波动率
        """
        if volatility <= 0:
            return self.fixed_fractional(capital, price)

        # 根据波动率调整仓位
        vol_ratio = target_vol / volatility
        position_pct = min(vol_ratio, self.config.max_position_pct)

        logger.info(f"波动率平价: 资产波动率{volatility*100:.1f}%, 目标{target_vol*100:.1f}%, 仓位{position_pct*100:.1f}%")

        return int(capital * position_pct / price / 100) * 100

    def risk_parity(self, capital: float, positions: List[Dict],
                    target_risk: float = 0.1) -> Dict[str, int]:
        """
        风险平价分配
        使每个持仓的风险贡献相等
        :param capital: 总资金
        :param positions: 持仓列表 [{code, price, volatility}]
        :param target_risk: 目标风险水平
        :return: {code: shares}
        """
        if not positions:
            return {}

        # 计算每个资产的逆波动率
        inv_vols = {}
        for pos in positions:
            vol = pos.get('volatility', 0.2)  # 默认20%波动率
            inv_vols[pos['code']] = 1 / vol if vol > 0 else 5

        # 归一化
        total_inv_vol = sum(inv_vols.values())
        weights = {code: inv_v / total_inv_vol for code, inv_v in inv_vols.items()}

        # 计算股数
        result = {}
        for pos in positions:
            code = pos['code']
            price = pos['price']
            weight = weights[code]
            amount = capital * weight
            shares = int(amount / price / 100) * 100
            result[code] = shares
            logger.info(f"风险平价: {code} 权重{weight*100:.1f}% 股数{shares}")

        return result


class RiskManager:
    """风险管理器 - 统一管理所有风险控制"""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self.stop_loss_manager = StopLossManager(config)
        self.position_sizer = PositionSizer(config)
        self.daily_pnl = 0
        self.peak_capital = 0
        self.current_drawdown = 0

    def check_trade_allowed(self, capital: float, price: float,
                           quantity: int, current_positions: Dict) -> Tuple[bool, str]:
        """
        检查交易是否被允许
        :return: (是否允许, 原因)
        """
        # 检查单只股票仓位限制
        position_value = price * quantity
        position_pct = position_value / capital

        if position_pct > self.config.max_position_pct:
            return False, f"超过单只股票仓位限制({self.config.max_position_pct*100}%)"

        # 检查总仓位限制
        total_position = sum(p['quantity'] * p.get('current_price', price)
                           for p in current_positions.values())
        new_total = total_position + position_value
        total_pct = new_total / capital

        if total_pct > self.config.max_total_position_pct:
            return False, f"超过总仓位限制({self.config.max_total_position_pct*100}%)"

        # 检查单日亏损限制
        if self.daily_pnl < -capital * self.config.max_daily_loss_pct:
            return False, f"超过单日最大亏损限制({self.config.max_daily_loss_pct*100}%)"

        # 检查最大回撤限制
        if self.current_drawdown > self.config.max_drawdown_pct:
            return False, f"超过最大回撤限制({self.config.max_drawdown_pct*100}%)"

        return True, "风险检查通过"

    def calculate_position(self, capital: float, price: float,
                          method: str = 'fixed',
                          **kwargs) -> int:
        """
        计算建议仓位
        :param method: fixed/kelly/atr/volatility
        """
        if method == 'fixed':
            return self.position_sizer.fixed_fractional(capital, price)
        elif method == 'kelly':
            return self.position_sizer.kelly_criterion(
                capital, price,
                kwargs.get('win_rate', 0.5),
                kwargs.get('avg_win', 0.1),
                kwargs.get('avg_loss', 0.05)
            )
        elif method == 'atr':
            return self.position_sizer.atr_based(
                capital, price,
                kwargs.get('atr', price * 0.02)
            )
        elif method == 'volatility':
            return self.position_sizer.volatility_parity(
                capital, price,
                kwargs.get('volatility', 0.2)
            )
        else:
            return self.position_sizer.fixed_fractional(capital, price)

    def update_daily_pnl(self, pnl: float, current_capital: float):
        """更新每日盈亏和回撤"""
        self.daily_pnl += pnl

        # 更新峰值和回撤
        if current_capital > self.peak_capital:
            self.peak_capital = current_capital

        if self.peak_capital > 0:
            self.current_drawdown = (self.peak_capital - current_capital) / self.peak_capital

    def reset_daily(self):
        """重置每日统计"""
        self.daily_pnl = 0

    def get_risk_report(self, capital: float, current_positions: Dict) -> str:
        """生成风险报告"""
        report = []
        report.append("=" * 50)
        report.append("风险管理报告")
        report.append("=" * 50)

        # 总体风险
        report.append(f"当前资金: {capital:.2f}")
        report.append(f"峰值资金: {self.peak_capital:.2f}")
        report.append(f"当前回撤: {self.current_drawdown*100:.2f}%")
        report.append(f"今日盈亏: {self.daily_pnl:.2f}")

        # 持仓风险
        total_risk = 0
        report.append("\n持仓风险:")
        for code, pos_risk in self.stop_loss_manager.position_risks.items():
            risk_pct = (pos_risk.entry_price - pos_risk.stop_loss_price) / pos_risk.entry_price * 100
            risk_amount = pos_risk.risk_amount
            total_risk += risk_amount

            report.append(f"  {pos_risk.stock_name}:")
            report.append(f"    入场价: {pos_risk.entry_price:.2f}")
            report.append(f"    当前价: {pos_risk.current_price:.2f}")
            report.append(f"    止损价: {pos_risk.stop_loss_price:.2f} ({risk_pct:.1f}%)")
            report.append(f"    止盈价: {pos_risk.take_profit_price:.2f}")
            report.append(f"    风险敞口: {risk_amount:.2f}")

        report.append(f"\n总风险敞口: {total_risk:.2f} ({total_risk/capital*100:.2f}%)")

        # 风险状态
        report.append("\n风险状态:")
        if self.current_drawdown > self.config.max_drawdown_pct * 0.8:
            report.append("  ⚠️ 接近最大回撤限制")
        if self.daily_pnl < -capital * self.config.max_daily_loss_pct * 0.8:
            report.append("  ⚠️ 接近单日亏损限制")

        report.append("=" * 50)

        return "\n".join(report)


if __name__ == '__main__':
    # 测试风险管理模块
    config = RiskConfig()
    risk_manager = RiskManager(config)

    # 测试仓位计算
    capital = 100000
    price = 50

    print("固定比例仓位:", risk_manager.calculate_position(capital, price, 'fixed'))
    print("Kelly仓位:", risk_manager.calculate_position(capital, price, 'kelly',
                                                       win_rate=0.55, avg_win=0.15, avg_loss=0.08))
    print("ATR仓位:", risk_manager.calculate_position(capital, price, 'atr', atr=1.5))

    # 测试止损止盈
    risk_manager.stop_loss_manager.add_position(
        '300308', '中际旭创', 100, 100, StopLossType.ATR, atr=3.5
    )

    print(risk_manager.get_risk_report(capital, {}))
