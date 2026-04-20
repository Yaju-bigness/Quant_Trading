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
