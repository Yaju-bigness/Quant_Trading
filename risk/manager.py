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
        更新追踪止损（优化版：阶梯式追踪）
        盈利5%后收紧到3%回撤，盈利10%后收紧到5%回撤
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

        # 阶梯式追踪止损
        profit_pct = (current_price - pos_risk.entry_price) / pos_risk.entry_price

        if profit_pct > 0.10:
            # 盈利10%以上：回撤5%触发
            trail_pct = 0.05
        elif profit_pct > 0.05:
            # 盈利5%-10%：回撤3%触发
            trail_pct = 0.03
        else:
            # 盈利5%以下：使用默认追踪止损
            trail_pct = self.config.trailing_stop_pct

        # 更新止损价格
        new_stop = pos_risk.highest_price * (1 - trail_pct)
        if new_stop > pos_risk.stop_loss_price:
            pos_risk.stop_loss_price = new_stop
            logger.info(f"追踪止损更新: {stock_code} 盈利{profit_pct*100:.1f}%, "
                       f"回撤{trail_pct*100:.1f}%, 新止损价 {new_stop:.2f}")

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

    def dynamic_position(self, capital: float, price: float,
                          stock_volatility: float = None,
                          market_trend: str = 'neutral',
                          **kwargs) -> int:
        """
        动态仓位调整：结合个股波动率和大盘状态
        :param capital: 总资金
        :param price: 当前价格
        :param stock_volatility: 个股年化波动率
        :param market_trend: 大盘趋势 'bull'(牛市)/'bear'(熊市)/'neutral'(震荡)
        :return: 建议股数
        """
        # 基础仓位范围
        min_pct = 0.15
        max_pct = 0.25
        base_pct = self.config.max_position_pct

        # 大盘趋势调整
        if market_trend == 'bull':
            position_pct = min(max_pct, base_pct * 1.2)
        elif market_trend == 'bear':
            position_pct = max(min_pct, base_pct * 0.75)
        else:
            position_pct = base_pct

        # 个股波动率调整
        if stock_volatility is not None:
            target_vol = 0.20  # 目标波动率20%
            vol_ratio = target_vol / stock_volatility if stock_volatility > 0 else 1
            # 波动率调整不超过±30%
            vol_adjust = max(0.7, min(1.3, vol_ratio))
            position_pct *= vol_adjust

        # 限制在合理范围
        position_pct = max(min_pct, min(max_pct, position_pct))

        logger.info(f"动态仓位: 大盘{market_trend}, 波动率{stock_volatility or 'N/A'}, "
                   f"仓位{position_pct*100:.1f}%")

        return int(capital * position_pct / price / 100) * 100


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


class AdaptiveATRStopLoss:
    """ATR动态止损（波动率自适应）：高波动时ATR倍数增大，低波动时缩小"""

    def __init__(self, atr_multiplier_range: Tuple[float, float] = (1.5, 2.5),
                 lookback: int = 20):
        """
        :param atr_multiplier_range: ATR倍数范围 (低波动, 高波动)
        :param lookback: ATR百分位回看天数
        """
        self.atr_multiplier_range = atr_multiplier_range
        self.lookback = lookback

    def calculate_stop_price(self, entry_price: float, atr: float,
                              atr_history: List[float] = None) -> float:
        """
        计算自适应ATR止损价
        :param entry_price: 入场价
        :param atr: 当前ATR值
        :param atr_history: 近期ATR序列（用于计算百分位）
        """
        if atr_history and len(atr_history) >= self.lookback:
            # 计算ATR百分位
            percentile = sum(1 for a in atr_history if a < atr) / len(atr_history)
            # 高百分位(高波动)用大倍数，低百分位(低波动)用小倍数
            low_mult, high_mult = self.atr_multiplier_range
            multiplier = low_mult + (high_mult - low_mult) * percentile
        else:
            multiplier = sum(self.atr_multiplier_range) / 2  # 默认取中间值

        stop_price = entry_price - multiplier * atr
        logger.info(f"自适应ATR止损: 倍数{multiplier:.2f}, ATR={atr:.2f}, 止损价={stop_price:.2f}")
        return stop_price


class TrailingTakeProfit:
    """移动止盈：跟随股价上涨调整止盈线，最高价回落N%触发止盈"""

    def __init__(self, activation_pct: float = 0.05, trail_pct: float = 0.03):
        """
        :param activation_pct: 激活阈值（盈利百分比），如5%
        :param trail_pct: 回撤触发比例，如3%
        """
        self.activation_pct = activation_pct
        self.trail_pct = trail_pct

    def check_take_profit(self, entry_price: float, current_price: float,
                           highest_price: float) -> Tuple[bool, str]:
        """
        检查是否触发移动止盈
        :return: (是否触发, 原因)
        """
        profit_pct = (current_price - entry_price) / entry_price

        # 未达到激活阈值
        if profit_pct < self.activation_pct:
            return False, ""

        # 计算从最高价的回撤
        drawdown_from_peak = (highest_price - current_price) / highest_price

        if drawdown_from_peak >= self.trail_pct:
            return True, (f"移动止盈触发: 盈利{profit_pct*100:.1f}%, "
                         f"从最高{highest_price:.2f}回落{drawdown_from_peak*100:.1f}%")

        return False, ""


class EmergencyHandler:
    """极端行情应急处理"""

    def __init__(self, market_drop_threshold: float = 0.03,
                 limit_down_threshold: float = -0.095):
        """
        :param market_drop_threshold: 大盘暴跌阈值（单日跌幅），默认3%
        :param limit_down_threshold: 跌停判断阈值，默认-9.5%
        """
        self.market_drop_threshold = market_drop_threshold
        self.limit_down_threshold = limit_down_threshold
        self.trading_paused = False
        self.pause_reason = ""

    def check_market_crash(self, index_pct_change: float) -> Tuple[bool, str]:
        """检测大盘暴跌"""
        if index_pct_change <= -self.market_drop_threshold * 100:
            self.trading_paused = True
            self.pause_reason = f"大盘暴跌{index_pct_change:.2f}%，暂停买入"
            logger.warning(self.pause_reason)
            return True, self.pause_reason
        return False, ""

    def check_limit_down(self, current_price: float, prev_close: float,
                          stock_code: str) -> Tuple[bool, str]:
        """检测个股跌停"""
        if prev_close > 0:
            pct_change = (current_price - prev_close) / prev_close
            if pct_change <= self.limit_down_threshold:
                # 创业板/科创板20%涨跌停
                if stock_code.startswith('30') or stock_code.startswith('68'):
                    if pct_change <= -0.195:
                        return True, f"个股{stock_code}跌停({pct_change*100:.2f}%)"
                else:
                    return True, f"个股{stock_code}跌停({pct_change*100:.2f}%)"
        return False, ""

    def check_suspension(self, volume: float, stock_code: str) -> Tuple[bool, str]:
        """检测停牌（成交量为0）"""
        if volume == 0:
            return True, f"个股{stock_code}疑似停牌(成交量为0)"
        return False, ""

    def should_allow_buy(self) -> Tuple[bool, str]:
        """是否允许买入"""
        if self.trading_paused:
            return False, self.pause_reason
        return True, ""

    def resume_trading(self):
        """恢复交易（需手动确认）"""
        self.trading_paused = False
        self.pause_reason = ""
        logger.info("交易已恢复")


class StrategyHealthMonitor:
    """策略失效检测与自动切换"""

    def __init__(self, max_consecutive_losses: int = 3,
                 min_win_rate: float = 0.4,
                 win_rate_window: int = 20,
                 max_drawdown_pct: float = 0.15):
        """
        :param max_consecutive_losses: 最大连续亏损次数
        :param min_win_rate: 最低胜率
        :param win_rate_window: 胜率计算窗口
        :param max_drawdown_pct: 最大回撤限制
        """
        self.max_consecutive_losses = max_consecutive_losses
        self.min_win_rate = min_win_rate
        self.win_rate_window = win_rate_window
        self.max_drawdown_pct = max_drawdown_pct
        self.consecutive_losses = 0
        self.recent_trades: List[Dict] = []
        self.strategy_paused = False
        self.position_reduction = 1.0  # 仓位缩减系数

    def record_trade(self, profit: float):
        """记录交易结果"""
        self.recent_trades.append({
            'profit': profit,
            'is_win': profit > 0
        })

        # 只保留最近N笔
        if len(self.recent_trades) > self.win_rate_window:
            self.recent_trades = self.recent_trades[-self.win_rate_window:]

        # 更新连续亏损
        if profit > 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        self._check_health()

    def _check_health(self):
        """检查策略健康状态"""
        # 连续亏损检查
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.position_reduction = 0.5  # 仓位减半
            logger.warning(f"策略连续亏损{self.consecutive_losses}次，仓位缩减至50%")

        # 胜率检查
        if len(self.recent_trades) >= self.win_rate_window:
            win_rate = sum(1 for t in self.recent_trades if t['is_win']) / len(self.recent_trades)
            if win_rate < self.min_win_rate:
                self.strategy_paused = True
                logger.warning(f"策略胜率{win_rate*100:.1f}%低于阈值{self.min_win_rate*100:.1f}%，暂停策略")

    def check_drawdown(self, current_drawdown: float):
        """检查回撤"""
        if current_drawdown > self.max_drawdown_pct:
            self.strategy_paused = True
            logger.warning(f"最大回撤{current_drawdown*100:.2f}%超限{self.max_drawdown_pct*100:.1f}%，暂停策略")

    def get_position_multiplier(self) -> float:
        """获取仓位调整系数"""
        return self.position_reduction

    def is_paused(self) -> bool:
        """策略是否暂停"""
        return self.strategy_paused

    def reset(self):
        """重置监控状态"""
        self.consecutive_losses = 0
        self.recent_trades = []
        self.strategy_paused = False
        self.position_reduction = 1.0
