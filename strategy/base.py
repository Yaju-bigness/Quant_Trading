"""
策略基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np


class Signal(Enum):
    """交易信号"""
    BUY = 1
    SELL = -1
    HOLD = 0


@dataclass
class TradeSignal:
    """交易信号数据类"""
    signal: Signal
    price: float
    reason: str
    confidence: float = 1.0  # 信号置信度 0-1
    quantity: int = 0  # 建议数量


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, name: str, params: Dict = None):
        self.name = name
        self.params = params or {}
        self.positions = {}  # 当前持仓

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        """
        生成交易信号
        :param data: 包含OHLCV的数据
        :return: 交易信号列表
        """
        pass

    @abstractmethod
    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        """
        计算持仓数量
        :param capital: 可用资金
        :param price: 当前价格
        :param signal: 交易信号
        :return: 建议持仓数量
        """
        pass

    def set_position(self, stock_code: str, quantity: int):
        """设置持仓"""
        self.positions[stock_code] = quantity

    def get_position(self, stock_code: str) -> int:
        """获取持仓"""
        return self.positions.get(stock_code, 0)

    def clear_positions(self):
        """清空持仓"""
        self.positions.clear()

    def update_params(self, params: Dict):
        """更新策略参数"""
        self.params.update(params)

    def validate_data(self, data: pd.DataFrame) -> bool:
        """验证数据格式"""
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        return all(col in data.columns for col in required_columns)

    def auto_adjust_params(self, data: pd.DataFrame):
        """
        根据近期市场波动率自动调整策略参数
        - 波动率高时：扩大止损范围、缩短均线周期
        - 波动率低时：缩小止损范围、延长均线周期
        """
        if data.empty or len(data) < 20:
            return

        close = data['close']
        # 计算20日年化波动率
        returns = close.pct_change().dropna()
        if len(returns) < 20:
            return
        recent_vol = returns.tail(20).std() * np.sqrt(252)

        # 波动率为NaN时跳过调整
        if pd.isna(recent_vol):
            return

        # 波动率分位判断
        if recent_vol > 0.4:  # 高波动
            vol_level = 'high'
        elif recent_vol < 0.15:  # 低波动
            vol_level = 'low'
        else:
            vol_level = 'normal'

        # 根据波动率调整参数
        if vol_level == 'high':
            # 缩短均线周期，提高灵敏度
            if 'short_period' in self.params:
                self.params['short_period'] = max(3, self.params.get('short_period', 5) - 2)
            if 'mid_period' in self.params:
                self.params['mid_period'] = max(10, self.params.get('mid_period', 20) - 5)
            if 'stop_loss_pct' in self.params:
                self.params['stop_loss_pct'] = min(0.15, self.params.get('stop_loss_pct', 0.08) + 0.02)
        elif vol_level == 'low':
            # 延长均线周期，降低噪音
            if 'short_period' in self.params:
                self.params['short_period'] = min(15, self.params.get('short_period', 5) + 2)
            if 'mid_period' in self.params:
                self.params['mid_period'] = min(40, self.params.get('mid_period', 20) + 5)
            if 'stop_loss_pct' in self.params:
                self.params['stop_loss_pct'] = max(0.05, self.params.get('stop_loss_pct', 0.08) - 0.02)

        logger.debug(f"参数自适应: 波动率{recent_vol:.2%}({vol_level}), 参数已调整")
