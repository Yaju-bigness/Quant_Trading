"""
日内/短线策略
包含：分时量价突破策略、RSI均值回归策略
"""
import pandas as pd
import numpy as np
from typing import List, Dict
from loguru import logger

from strategy.base import BaseStrategy, TradeSignal, Signal
from strategy.technical import TechnicalIndicators


class IntradayVolumePriceStrategy(BaseStrategy):
    """
    分时量价突破策略
    逻辑：
    - 买入：放量突破前日高点（成交量 > 5日均量 * 1.5 + 收盘价 > 前日最高价）
    - 卖出：缩量跌破前日低点（收盘价 < 前日最低价）
    - 量价配合：价格上涨+成交量放大=健康上涨信号
    """

    def __init__(self, params: Dict = None):
        default_params = {
            'volume_ratio_threshold': 1.5,   # 量比阈值
            'lookback_days': 5,              # 均量回看天数
            'breakout_pct': 0.005,           # 突破确认幅度(0.5%)
            'use_ma_filter': True,           # 均线趋势过滤
            'ma_period': 20,                 # 均线周期
        }
        if params:
            default_params.update(params)
        super().__init__("分时量价策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']

        lookback = self.params['lookback_days']
        vol_ma = volume.rolling(lookback).mean()
        ma = TechnicalIndicators.SMA(close, self.params['ma_period']) if self.params.get('use_ma_filter') else None

        for i in range(lookback + 1, len(data)):
            prev_high = high.iloc[i-1]
            prev_low = low.iloc[i-1]
            curr_close = close.iloc[i]
            curr_vol = volume.iloc[i]
            curr_vol_ma = vol_ma.iloc[i]

            if pd.isna(curr_vol_ma) or curr_vol_ma == 0:
                continue

            vol_ratio = curr_vol / curr_vol_ma
            breakout_pct = self.params['breakout_pct']

            # 买入信号：放量突破前日高点
            if curr_close > prev_high * (1 + breakout_pct):
                confidence = 0.6
                reason = f"突破前日高点{prev_high:.2f}"

                # 成交量确认
                if vol_ratio > self.params['volume_ratio_threshold']:
                    confidence += 0.15
                    reason += f"，放量(量比{vol_ratio:.1f})"

                # 均线趋势过滤
                if ma is not None and not pd.isna(ma.iloc[i]):
                    if curr_close > ma.iloc[i]:
                        confidence += 0.1
                        reason += "，均线上方"

                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=curr_close,
                    reason=reason,
                    confidence=min(confidence, 1.0)
                ))

            # 卖出信号：跌破前日低点
            elif curr_close < prev_low * (1 - breakout_pct):
                confidence = 0.6
                reason = f"跌破前日低点{prev_low:.2f}"

                # 缩量下跌可能只是回调
                if vol_ratio < 0.7:
                    confidence -= 0.1  # 缩量下跌降低卖出信号强度
                    reason += "，缩量"
                elif vol_ratio > self.params['volume_ratio_threshold']:
                    confidence += 0.1
                    reason += "，放量"

                # 均线趋势过滤
                if ma is not None and not pd.isna(ma.iloc[i]):
                    if curr_close < ma.iloc[i]:
                        confidence += 0.1
                        reason += "，均线下方"

                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=curr_close,
                    reason=reason,
                    confidence=min(confidence, 1.0)
                ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.2 * signal.confidence
        return int(capital * position_ratio / price / 100) * 100


class RSIMeanReversionStrategy(BaseStrategy):
    """
    RSI均值回归策略
    逻辑：
    - 买入：RSI < 20 + 价格在布林下轨附近 + MA20以上(趋势过滤)
    - 卖出：RSI > 80 + 价格在布林上轨附近 + MA20以下(趋势过滤)
    - 增加趋势过滤：MA20以上才做多，MA20以下才做空
    """

    def __init__(self, params: Dict = None):
        default_params = {
            'rsi_period': 14,
            'rsi_oversold': 20,           # 严格超卖线
            'rsi_overbought': 80,         # 严格超买线
            'boll_period': 20,
            'boll_std_dev': 2.0,
            'ma_trend_period': 20,        # 趋势过滤均线
            'use_trend_filter': True,     # 是否启用趋势过滤
            'boll_position_threshold': 0.15,  # 布林位置阈值(接近下轨/上轨)
        }
        if params:
            default_params.update(params)
        super().__init__("RSI均值回归策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        close = data['close']
        high = data['high']
        low = data['low']

        # 计算指标
        rsi = TechnicalIndicators.RSI(close, self.params['rsi_period'])
        boll = TechnicalIndicators.BOLL(close, self.params['boll_period'], self.params['boll_std_dev'])
        ma_trend = TechnicalIndicators.SMA(close, self.params['ma_trend_period'])

        for i in range(self.params['boll_period'], len(data)):
            if pd.isna(rsi.iloc[i]) or pd.isna(boll['upper'].iloc[i]):
                continue

            curr_rsi = rsi.iloc[i]
            curr_close = close.iloc[i]
            boll_range = boll['upper'].iloc[i] - boll['lower'].iloc[i]
            boll_position = (curr_close - boll['lower'].iloc[i]) / boll_range if boll_range > 0 else 0.5

            threshold = self.params['boll_position_threshold']
            use_trend = self.params.get('use_trend_filter', True)
            ma_val = ma_trend.iloc[i]
            above_ma = not use_trend or (not pd.isna(ma_val) and curr_close > ma_val)
            below_ma = not use_trend or (not pd.isna(ma_val) and curr_close < ma_val)

            # 买入信号：RSI超卖 + 布林下轨附近 + 均线上方
            if curr_rsi < self.params['rsi_oversold'] and boll_position < threshold and above_ma:
                confidence = 0.7
                reason = f"RSI超卖({curr_rsi:.1f})+布林下轨(位置{boll_position:.2f})"
                if above_ma and use_trend:
                    reason += "，均线上方"
                if curr_rsi < 10:
                    confidence += 0.1  # 极度超卖
                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=curr_close,
                    reason=reason,
                    confidence=min(confidence, 1.0)
                ))

            # 卖出信号：RSI超买 + 布林上轨附近 + 均线下方
            elif curr_rsi > self.params['rsi_overbought'] and boll_position > (1 - threshold) and below_ma:
                confidence = 0.7
                reason = f"RSI超买({curr_rsi:.1f})+布林上轨(位置{boll_position:.2f})"
                if below_ma and use_trend:
                    reason += "，均线下方"
                if curr_rsi > 90:
                    confidence += 0.1  # 极度超买
                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=curr_close,
                    reason=reason,
                    confidence=min(confidence, 1.0)
                ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        # 根据RSI极端程度调整仓位
        position_ratio = 0.15 * signal.confidence
        return int(capital * position_ratio / price / 100) * 100
