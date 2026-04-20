"""
技术指标策略
包含：均线策略、MACD策略、KDJ策略、RSI策略、布林带策略、综合策略
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from loguru import logger

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logger.warning("talib未安装，使用内置计算")

from strategy.base import BaseStrategy, TradeSignal, Signal


class TechnicalIndicators:
    """技术指标计算工具类"""

    @staticmethod
    def SMA(data: pd.Series, period: int) -> pd.Series:
        """简单移动平均"""
        return data.rolling(window=period).mean()

    @staticmethod
    def EMA(data: pd.Series, period: int) -> pd.Series:
        """指数移动平均"""
        return data.ewm(span=period, adjust=False).mean()

    @staticmethod
    def MACD(close: pd.Series, fast: int = 12, slow: int = 26,
             signal: int = 9) -> Dict[str, pd.Series]:
        """MACD指标"""
        if TALIB_AVAILABLE:
            macd, signal_line, hist = talib.MACD(
                close.values, fastperiod=fast, slowperiod=slow,
                signalperiod=signal
            )
            return {
                'macd': pd.Series(macd, index=close.index),
                'signal': pd.Series(signal_line, index=close.index),
                'hist': pd.Series(hist, index=close.index)
            }
        else:
            ema_fast = TechnicalIndicators.EMA(close, fast)
            ema_slow = TechnicalIndicators.EMA(close, slow)
            macd_line = ema_fast - ema_slow
            signal_line = TechnicalIndicators.EMA(macd_line, signal)
            hist = macd_line - signal_line
            return {
                'macd': macd_line,
                'signal': signal_line,
                'hist': hist
            }

    @staticmethod
    def RSI(close: pd.Series, period: int = 14) -> pd.Series:
        """RSI指标"""
        if TALIB_AVAILABLE:
            return pd.Series(talib.RSI(close.values, timeperiod=period),
                           index=close.index)
        else:
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))

    @staticmethod
    def KDJ(high: pd.Series, low: pd.Series, close: pd.Series,
            n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, pd.Series]:
        """KDJ指标"""
        if TALIB_AVAILABLE:
            slowk, slowd = talib.STOCH(
                high.values, low.values, close.values,
                fastk_period=n, slowk_period=m1, slowk_matype=0,
                slowd_period=m2, slowd_matype=0
            )
            j = 3 * slowk - 2 * slowd
            return {
                'K': pd.Series(slowk, index=close.index),
                'D': pd.Series(slowd, index=close.index),
                'J': pd.Series(j, index=close.index)
            }
        else:
            low_n = low.rolling(window=n).min()
            high_n = high.rolling(window=n).max()
            rsv = (close - low_n) / (high_n - low_n) * 100
            k = rsv.ewm(alpha=1/m1, adjust=False).mean()
            d = k.ewm(alpha=1/m2, adjust=False).mean()
            j = 3 * k - 2 * d
            return {'K': k, 'D': d, 'J': j}

    @staticmethod
    def BOLL(close: pd.Series, period: int = 20,
             std_dev: float = 2) -> Dict[str, pd.Series]:
        """布林带"""
        if TALIB_AVAILABLE:
            upper, mid, lower = talib.BBANDS(
                close.values, timeperiod=period,
                nbdevup=std_dev, nbdevdn=std_dev
            )
            return {
                'upper': pd.Series(upper, index=close.index),
                'mid': pd.Series(mid, index=close.index),
                'lower': pd.Series(lower, index=close.index)
            }
        else:
            mid = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            return {
                'upper': mid + std_dev * std,
                'mid': mid,
                'lower': mid - std_dev * std
            }

    @staticmethod
    def ATR(high: pd.Series, low: pd.Series, close: pd.Series,
            period: int = 14) -> pd.Series:
        """ATR - 平均真实波幅"""
        if TALIB_AVAILABLE:
            return pd.Series(talib.ATR(high.values, low.values, close.values,
                                       timeperiod=period), index=close.index)
        else:
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.rolling(window=period).mean()


class MAStrategy(BaseStrategy):
    """均线策略（优化版：成交量+RSI过滤假信号）"""

    def __init__(self, params: Dict = None):
        default_params = {
            'short_period': 5,
            'mid_period': 20,
            'long_period': 60,
            'volume_confirm': True,    # 成交量确认
            'rsi_filter': True,        # RSI过滤
            'volume_ratio_threshold': 1.2,  # 量比阈值
            'rsi_overbought': 70,      # RSI超买线
            'rsi_oversold': 30,        # RSI超卖线
        }
        if params:
            default_params.update(params)
        super().__init__("均线策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        # 计算均线
        close = data['close']
        ma_short = TechnicalIndicators.SMA(close, self.params['short_period'])
        ma_mid = TechnicalIndicators.SMA(close, self.params['mid_period'])
        ma_long = TechnicalIndicators.SMA(close, self.params['long_period'])

        # 计算RSI（用于过滤）
        rsi = TechnicalIndicators.RSI(close, 14) if self.params.get('rsi_filter') else None

        # 计算成交量均线（用于确认）
        if self.params.get('volume_confirm') and 'volume' in data.columns:
            vol_ma5 = data['volume'].rolling(5).mean()

        # 均线多头/空头排列
        for i in range(1, len(data)):
            # 金叉买入：短期均线上穿中期均线
            if ma_short.iloc[i-1] <= ma_mid.iloc[i-1] and \
               ma_short.iloc[i] > ma_mid.iloc[i]:
                # 确认长期均线向上
                if ma_long.iloc[i] > ma_long.iloc[i-1]:
                    confidence = 0.7
                    reason = f"MA{self.params['short_period']}金叉MA{self.params['mid_period']}，且长期均线向上"

                    # RSI过滤：避免超买区假信号
                    if self.params.get('rsi_filter') and rsi is not None:
                        if rsi.iloc[i] > self.params['rsi_overbought']:
                            continue  # RSI超买，跳过
                        elif rsi.iloc[i] < self.params['rsi_oversold']:
                            confidence += 0.1  # RSI超卖区金叉更可靠

                    # 成交量确认：放量金叉更可靠
                    if self.params.get('volume_confirm') and 'volume' in data.columns:
                        vol_ratio = data['volume'].iloc[i] / vol_ma5.iloc[i] if vol_ma5.iloc[i] > 0 else 1
                        if vol_ratio > self.params['volume_ratio_threshold']:
                            confidence += 0.1  # 放量确认
                            reason += f"，放量(量比{vol_ratio:.1f})"
                        else:
                            confidence -= 0.1  # 缩量金叉降低置信度

                    signals.append(TradeSignal(
                        signal=Signal.BUY,
                        price=data['close'].iloc[i],
                        reason=reason,
                        confidence=min(confidence, 1.0)
                    ))

            # 死叉卖出：短期均线下穿中期均线
            elif ma_short.iloc[i-1] >= ma_mid.iloc[i-1] and \
                 ma_short.iloc[i] < ma_mid.iloc[i]:
                confidence = 0.6
                reason = f"MA{self.params['short_period']}死叉MA{self.params['mid_period']}"

                # RSI过滤
                if self.params.get('rsi_filter') and rsi is not None:
                    if rsi.iloc[i] < self.params['rsi_oversold']:
                        confidence -= 0.1  # RSI超卖区死叉可能反弹

                # 成交量确认
                if self.params.get('volume_confirm') and 'volume' in data.columns:
                    vol_ratio = data['volume'].iloc[i] / vol_ma5.iloc[i] if vol_ma5.iloc[i] > 0 else 1
                    if vol_ratio > self.params['volume_ratio_threshold']:
                        confidence += 0.1  # 放量死叉更可靠
                        reason += f"，放量(量比{vol_ratio:.1f})"

                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=data['close'].iloc[i],
                    reason=reason,
                    confidence=min(confidence, 1.0)
                ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        # 固定仓位比例
        position_ratio = 0.3  # 单次开仓30%
        return int(capital * position_ratio / price / 100) * 100


class MACDStrategy(BaseStrategy):
    """MACD策略（优化版：增加顶底背离检测、柱状图确认）"""

    def __init__(self, params: Dict = None):
        default_params = {
            'fast': 12,
            'slow': 26,
            'signal': 9,
            'short_line_fast': 8,   # A股短线参数
            'short_line_slow': 21,
            'short_line_signal': 5,
            'use_short_line': False,  # 是否使用短线参数
            'detect_divergence': True,  # 背离检测
        }
        if params:
            default_params.update(params)
        super().__init__("MACD策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        # 选择参数组
        if self.params.get('use_short_line'):
            fast = self.params['short_line_fast']
            slow = self.params['short_line_slow']
            sig_period = self.params['short_line_signal']
        else:
            fast = self.params['fast']
            slow = self.params['slow']
            sig_period = self.params['signal']

        macd_data = TechnicalIndicators.MACD(
            data['close'], fast, slow, sig_period
        )

        macd = macd_data['macd']
        signal_line = macd_data['signal']
        hist = macd_data['hist']

        for i in range(1, len(data)):
            # MACD金叉
            if macd.iloc[i-1] <= signal_line.iloc[i-1] and \
               macd.iloc[i] > signal_line.iloc[i]:
                confidence = 0.6
                reason_parts = []

                # MACD在零轴上方，信号更强
                if macd.iloc[i] > 0:
                    confidence = 0.8
                    reason_parts.append("零轴上方")
                else:
                    reason_parts.append("零轴下方(弱势)")

                # 柱状图放大确认
                if hist.iloc[i] > 0 and hist.iloc[i] > hist.iloc[i-1]:
                    confidence += 0.05
                    reason_parts.append("红柱放大")

                # 背离检测：价格创新低但MACD未创新低
                if self.params.get('detect_divergence') and i >= 20:
                    if self._check_bullish_divergence(data['close'], macd, i):
                        confidence += 0.1
                        reason_parts.append("底背离")

                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=data['close'].iloc[i],
                    reason=f"MACD金叉({'+'.join(reason_parts)})",
                    confidence=min(confidence, 1.0)
                ))

            # MACD死叉
            elif macd.iloc[i-1] >= signal_line.iloc[i-1] and \
                 macd.iloc[i] < signal_line.iloc[i]:
                confidence = 0.6
                reason_parts = []

                # MACD在零轴下方，信号更强
                if macd.iloc[i] < 0:
                    confidence = 0.8
                    reason_parts.append("零轴下方")
                else:
                    reason_parts.append("零轴上方")

                # 柱状图放大确认
                if hist.iloc[i] < 0 and hist.iloc[i] < hist.iloc[i-1]:
                    confidence += 0.05
                    reason_parts.append("绿柱放大")

                # 顶背离检测
                if self.params.get('detect_divergence') and i >= 20:
                    if self._check_bearish_divergence(data['close'], macd, i):
                        confidence += 0.1
                        reason_parts.append("顶背离")

                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=data['close'].iloc[i],
                    reason=f"MACD死叉({'+'.join(reason_parts)})",
                    confidence=min(confidence, 1.0)
                ))

        return signals

    def _check_bullish_divergence(self, close: pd.Series, macd: pd.Series,
                                   idx: int, lookback: int = 20) -> bool:
        """检测底背离：价格创新低但MACD未创新低"""
        if idx < lookback:
            return False
        recent_close = close.iloc[idx-lookback:idx+1]
        recent_macd = macd.iloc[idx-lookback:idx+1]
        # 价格近期的最低点
        price_min_idx = recent_close.idxmin()
        # MACD近期的最低点
        macd_min_idx = recent_macd.idxmin()
        # 价格创新低但MACD没创新低
        if price_min_idx == recent_close.index[-1] and macd_min_idx != recent_macd.index[-1]:
            return True
        return False

    def _check_bearish_divergence(self, close: pd.Series, macd: pd.Series,
                                   idx: int, lookback: int = 20) -> bool:
        """检测顶背离：价格创新高但MACD未创新高"""
        if idx < lookback:
            return False
        recent_close = close.iloc[idx-lookback:idx+1]
        recent_macd = macd.iloc[idx-lookback:idx+1]
        price_max_idx = recent_close.idxmax()
        macd_max_idx = recent_macd.idxmax()
        if price_max_idx == recent_close.index[-1] and macd_max_idx != recent_macd.index[-1]:
            return True
        return False

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.25
        return int(capital * position_ratio / price / 100) * 100


class KDJStrategy(BaseStrategy):
    """KDJ策略"""

    def __init__(self, params: Dict = None):
        default_params = {
            'n': 9,
            'm1': 3,
            'm2': 3,
            'oversold': 20,   # 超卖线
            'overbought': 80, # 超买线
        }
        if params:
            default_params.update(params)
        super().__init__("KDJ策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        kdj = TechnicalIndicators.KDJ(
            data['high'], data['low'], data['close'],
            self.params['n'], self.params['m1'], self.params['m2']
        )

        k = kdj['K']
        d = kdj['D']
        j = kdj['J']

        for i in range(1, len(data)):
            # K线上穿D线，且处于超卖区域
            if k.iloc[i-1] <= d.iloc[i-1] and k.iloc[i] > d.iloc[i]:
                if k.iloc[i] < self.params['oversold']:
                    signals.append(TradeSignal(
                        signal=Signal.BUY,
                        price=data['close'].iloc[i],
                        reason=f"KDJ超卖区金叉(K={k.iloc[i]:.1f})",
                        confidence=0.75
                    ))
                elif k.iloc[i] < 50:
                    signals.append(TradeSignal(
                        signal=Signal.BUY,
                        price=data['close'].iloc[i],
                        reason=f"KDJ低位金叉(K={k.iloc[i]:.1f})",
                        confidence=0.6
                    ))

            # K线下穿D线，且处于超买区域
            elif k.iloc[i-1] >= d.iloc[i-1] and k.iloc[i] < d.iloc[i]:
                if k.iloc[i] > self.params['overbought']:
                    signals.append(TradeSignal(
                        signal=Signal.SELL,
                        price=data['close'].iloc[i],
                        reason=f"KDJ超买区死叉(K={k.iloc[i]:.1f})",
                        confidence=0.75
                    ))
                elif k.iloc[i] > 50:
                    signals.append(TradeSignal(
                        signal=Signal.SELL,
                        price=data['close'].iloc[i],
                        reason=f"KDJ高位死叉(K={k.iloc[i]:.1f})",
                        confidence=0.6
                    ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.2
        return int(capital * position_ratio / price / 100) * 100


class BollingerStrategy(BaseStrategy):
    """布林带策略"""

    def __init__(self, params: Dict = None):
        default_params = {
            'period': 20,
            'std_dev': 2,
        }
        if params:
            default_params.update(params)
        super().__init__("布林带策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        boll = TechnicalIndicators.BOLL(
            data['close'],
            self.params['period'],
            self.params['std_dev']
        )

        close = data['close']

        for i in range(self.params['period'], len(data)):
            # 价格触及下轨，买入信号
            if close.iloc[i-1] <= boll['lower'].iloc[i-1] and \
               close.iloc[i] > boll['lower'].iloc[i]:
                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=close.iloc[i],
                    reason="价格触及布林下轨反弹",
                    confidence=0.7
                ))

            # 价格触及上轨，卖出信号
            elif close.iloc[i-1] >= boll['upper'].iloc[i-1] and \
                 close.iloc[i] < boll['upper'].iloc[i]:
                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=close.iloc[i],
                    reason="价格触及布林上轨回落",
                    confidence=0.7
                ))

            # 布林带收口后突破
            bandwidth = (boll['upper'].iloc[i] - boll['lower'].iloc[i]) / boll['mid'].iloc[i]
            prev_bandwidth = (boll['upper'].iloc[i-5] - boll['lower'].iloc[i-5]) / boll['mid'].iloc[i-5]

            if bandwidth < prev_bandwidth * 0.5:  # 带宽收窄一半
                # 向上突破
                if close.iloc[i] > boll['upper'].iloc[i]:
                    signals.append(TradeSignal(
                        signal=Signal.BUY,
                        price=close.iloc[i],
                        reason="布林带收口后向上突破",
                        confidence=0.8
                    ))
                # 向下突破
                elif close.iloc[i] < boll['lower'].iloc[i]:
                    signals.append(TradeSignal(
                        signal=Signal.SELL,
                        price=close.iloc[i],
                        reason="布林带收口后向下突破",
                        confidence=0.8
                    ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.25
        return int(capital * position_ratio / price / 100) * 100


class CompositeStrategy(BaseStrategy):
    """
    综合技术策略（优化版：加权打分制，权重可配置）
    多个指标共振时才产生信号
    """

    def __init__(self, params: Dict = None):
        default_params = {
            'ma_short': 5,
            'ma_mid': 20,
            'ma_long': 60,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'min_score': 0.3,    # 最低触发分数(0-1)，替代min_signals
            'weights': {         # 指标权重
                'ma': 0.30,
                'macd': 0.25,
                'rsi': 0.20,
                'kdj': 0.25,
            },
        }
        if params:
            default_params.update(params)
        super().__init__("综合技术策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        close = data['close']

        # 计算所有指标
        ma_short = TechnicalIndicators.SMA(close, self.params['ma_short'])
        ma_mid = TechnicalIndicators.SMA(close, self.params['ma_mid'])
        ma_long = TechnicalIndicators.SMA(close, self.params['ma_long'])

        rsi = TechnicalIndicators.RSI(close, self.params['rsi_period'])

        macd_data = TechnicalIndicators.MACD(
            close,
            self.params['macd_fast'],
            self.params['macd_slow'],
            self.params['macd_signal']
        )

        kdj = TechnicalIndicators.KDJ(data['high'], data['low'], data['close'])

        weights = self.params.get('weights', {'ma': 0.30, 'macd': 0.25, 'rsi': 0.20, 'kdj': 0.25})

        for i in range(max(self.params['ma_long'], 30), len(data)):
            buy_score = 0
            sell_score = 0
            reasons = []

            # MA判断（权重：weights['ma']）
            if ma_short.iloc[i] > ma_mid.iloc[i] and \
               ma_mid.iloc[i] > ma_long.iloc[i]:
                buy_score += weights.get('ma', 0.30)
                reasons.append("均线多头排列")
            elif ma_short.iloc[i] < ma_mid.iloc[i] and \
                 ma_mid.iloc[i] < ma_long.iloc[i]:
                sell_score += weights.get('ma', 0.30)
                reasons.append("均线空头排列")

            # RSI判断（权重：weights['rsi']）
            if rsi.iloc[i] < self.params['rsi_oversold']:
                buy_score += weights.get('rsi', 0.20)
                reasons.append(f"RSI超卖({rsi.iloc[i]:.1f})")
            elif rsi.iloc[i] > self.params['rsi_overbought']:
                sell_score += weights.get('rsi', 0.20)
                reasons.append(f"RSI超买({rsi.iloc[i]:.1f})")

            # MACD判断（权重：weights['macd']）
            if macd_data['hist'].iloc[i] > 0 and \
               macd_data['hist'].iloc[i] > macd_data['hist'].iloc[i-1]:
                buy_score += weights.get('macd', 0.25)
                reasons.append("MACD红柱放大")
            elif macd_data['hist'].iloc[i] < 0 and \
                 macd_data['hist'].iloc[i] < macd_data['hist'].iloc[i-1]:
                sell_score += weights.get('macd', 0.25)
                reasons.append("MACD绿柱放大")

            # KDJ判断（权重：weights['kdj']）
            if kdj['J'].iloc[i] < 20:
                buy_score += weights.get('kdj', 0.25)
                reasons.append(f"KDJ超卖(J={kdj['J'].iloc[i]:.1f})")
            elif kdj['J'].iloc[i] > 80:
                sell_score += weights.get('kdj', 0.25)
                reasons.append(f"KDJ超买(J={kdj['J'].iloc[i]:.1f})")

            # 生成信号（加权打分制）
            min_score = self.params.get('min_score', 0.3)
            if buy_score >= min_score:
                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=close.iloc[i],
                    reason=f"多指标共振买入({'+'.join(reasons[:3])})",
                    confidence=min(buy_score, 1.0)
                ))
            elif sell_score >= min_score:
                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=close.iloc[i],
                    reason=f"多指标共振卖出({'+'.join(reasons[:3])})",
                    confidence=min(sell_score, 1.0)
                ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        # 根据置信度调整仓位
        base_ratio = 0.2
        position_ratio = base_ratio * signal.confidence
        return int(capital * position_ratio / price / 100) * 100
