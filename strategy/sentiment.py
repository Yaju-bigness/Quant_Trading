"""
消息面/情绪策略
包含：新闻情绪分析、资金流向、龙虎榜、北向资金等
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from loguru import logger
from datetime import datetime, timedelta
import re

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

from strategy.base import BaseStrategy, TradeSignal, Signal


class SentimentAnalyzer:
    """情绪分析工具"""

    # 简单的情感词典（实际应用建议使用NLP模型）
    POSITIVE_WORDS = [
        '利好', '增长', '盈利', '上涨', '突破', '新高', '翻倍', '并购',
        '中标', '签约', '订单', '扩张', '增持', '回购', '分红', '业绩',
        '创新', '领先', '龙头', '成长', '超预期', '扭亏', '盈利',
    ]

    NEGATIVE_WORDS = [
        '利空', '下跌', '亏损', '减持', '质押', '诉讼', '违规', '处罚',
        '退市', '风险', '预警', '下降', '下滑', '违约', '债务', '裁员',
        '调查', '处罚', '监管', '警示', '亏损', '下滑',
    ]

    @classmethod
    def analyze_text(cls, text: str) -> float:
        """
        分析文本情绪
        :param text: 文本内容
        :return: 情绪分数 -1 到 1
        """
        if not text:
            return 0

        text = text.lower()
        pos_count = sum(1 for word in cls.POSITIVE_WORDS if word in text)
        neg_count = sum(1 for word in cls.NEGATIVE_WORDS if word in text)

        total = pos_count + neg_count
        if total == 0:
            return 0

        return (pos_count - neg_count) / total

    @classmethod
    def analyze_news_batch(cls, news_list: List[Dict]) -> float:
        """
        批量分析新闻情绪
        :param news_list: 新闻列表
        :return: 综合情绪分数
        """
        if not news_list:
            return 0

        scores = []
        weights = []

        for i, news in enumerate(news_list[:20]):  # 只分析最近20条
            title = news.get('title', '')
            content = news.get('content', '')

            # 标题权重更高
            title_score = cls.analyze_text(title) * 1.5
            content_score = cls.analyze_text(content)

            # 时间衰减权重
            time_weight = 1.0 - (i * 0.03)  # 越近的新闻权重越高
            weights.append(time_weight)
            scores.append((title_score + content_score) / 2)

        if not scores:
            return 0

        weighted_score = np.average(scores, weights=weights)
        return np.clip(weighted_score, -1, 1)


class MoneyFlowStrategy(BaseStrategy):
    """资金流向策略"""

    def __init__(self, params: Dict = None):
        default_params = {
            'lookback_days': 5,      # 回看天数
            'flow_threshold': 0.02,  # 资金流入/流出阈值
        }
        if params:
            default_params.update(params)
        super().__init__("资金流向策略", default_params)

    def get_money_flow(self, stock_code: str,
                       days: int = 5) -> pd.DataFrame:
        """
        获取资金流向数据
        :param stock_code: 股票代码
        :param days: 天数
        :return: 资金流向DataFrame
        """
        try:
            df = ak.stock_individual_fund_flow(stock=stock_code, market="sh" if stock_code.startswith('6') else "sz")
            return df.head(days)
        except Exception as e:
            logger.error(f"获取资金流向失败: {e}")
            return pd.DataFrame()

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        """
        基于资金流向生成信号
        注意：此方法需要额外的资金流向数据
        """
        signals = []

        # 这里需要结合实时资金流向数据
        # 在实际使用中，应该通过回调或数据注入方式获取

        return signals

    def generate_signal_with_flow(self, stock_code: str,
                                  price_data: pd.DataFrame) -> List[TradeSignal]:
        """
        结合资金流向生成信号
        """
        signals = []

        try:
            flow_df = self.get_money_flow(stock_code, self.params['lookback_days'])
            if flow_df.empty:
                return signals

            # 计算主力资金净流入
            flow_df['net_inflow'] = flow_df['主力净流入-净额'].astype(float)

            # 连续净流入
            if all(flow_df['net_inflow'].head(3) > 0):
                latest_price = price_data['close'].iloc[-1]
                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=latest_price,
                    reason=f"连续{len(flow_df[flow_df['net_inflow']>0])}日主力净流入",
                    confidence=0.7
                ))

            # 连续净流出
            elif all(flow_df['net_inflow'].head(3) < 0):
                latest_price = price_data['close'].iloc[-1]
                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=latest_price,
                    reason=f"连续{len(flow_df[flow_df['net_inflow']<0])}日主力净流出",
                    confidence=0.6
                ))

        except Exception as e:
            logger.error(f"资金流向策略执行失败: {e}")

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.25
        return int(capital * position_ratio / price / 100) * 100


class NorthboundFlowStrategy(BaseStrategy):
    """北向资金策略"""

    def __init__(self, params: Dict = None):
        default_params = {
            'lookback_days': 10,
            'hold_threshold': 0.01,  # 持仓变化阈值
        }
        if params:
            default_params.update(params)
        super().__init__("北向资金策略", default_params)

    def get_northbound_holding(self, stock_code: str) -> pd.DataFrame:
        """
        获取北向资金持股数据
        :param stock_code: 股票代码
        :return: 持股数据
        """
        try:
            df = ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")
            df = df[df['代码'] == stock_code]
            return df
        except Exception as e:
            logger.error(f"获取北向持股失败: {e}")
            return pd.DataFrame()

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        # 需要额外的北向资金数据
        return []

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.3
        return int(capital * position_ratio / price / 100) * 100


class NewsSentimentStrategy(BaseStrategy):
    """新闻情绪策略"""

    def __init__(self, params: Dict = None):
        default_params = {
            'sentiment_threshold': 0.3,  # 情绪阈值
            'news_count': 20,            # 分析新闻数量
        }
        if params:
            default_params.update(params)
        super().__init__("新闻情绪策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        # 需要新闻数据注入
        return []

    def generate_signal_with_news(self, stock_code: str,
                                   price_data: pd.DataFrame,
                                   news_list: List[Dict]) -> List[TradeSignal]:
        """
        结合新闻数据生成信号
        """
        signals = []

        if not news_list:
            return signals

        # 分析新闻情绪
        sentiment = SentimentAnalyzer.analyze_news_batch(news_list)

        latest_price = price_data['close'].iloc[-1]
        threshold = self.params['sentiment_threshold']

        if sentiment > threshold:
            signals.append(TradeSignal(
                signal=Signal.BUY,
                price=latest_price,
                reason=f"新闻情绪积极(分数:{sentiment:.2f})",
                confidence=min(sentiment, 1.0)
            ))
        elif sentiment < -threshold:
            signals.append(TradeSignal(
                signal=Signal.SELL,
                price=latest_price,
                reason=f"新闻情绪消极(分数:{sentiment:.2f})",
                confidence=min(abs(sentiment), 1.0)
            ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.15 * signal.confidence  # 根据置信度调整
        return int(capital * position_ratio / price / 100) * 100


class DragonTigerStrategy(BaseStrategy):
    """龙虎榜策略"""

    def __init__(self, params: Dict = None):
        default_params = {
            'lookback_days': 30,
            'institution_buy_threshold': 50000000,  # 机构买入金额阈值 5000万
        }
        if params:
            default_params.update(params)
        super().__init__("龙虎榜策略", default_params)

    def get_dragon_tiger(self, stock_code: str) -> pd.DataFrame:
        """
        获取龙虎榜数据
        :param stock_code: 股票代码
        :return: 龙虎榜数据
        """
        try:
            df = ak.stock_lhb_detail_em(start_date="20240101", end_date="20241231", code=stock_code)
            return df
        except Exception as e:
            logger.error(f"获取龙虎榜失败: {e}")
            return pd.DataFrame()

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        return []

    def generate_signal_with_lhb(self, stock_code: str,
                                  price_data: pd.DataFrame) -> List[TradeSignal]:
        """
        结合龙虎榜数据生成信号
        """
        signals = []

        try:
            lhb_df = self.get_dragon_tiger(stock_code)
            if lhb_df.empty:
                return signals

            # 分析最近上榜情况
            recent_lhb = lhb_df.head(5)
            if recent_lhb.empty:
                return signals

            # 计算机构和游资买卖情况
            total_buy = recent_lhb['买入金额'].sum()
            total_sell = recent_lhb['卖出金额'].sum()
            net_buy = total_buy - total_sell

            latest_price = price_data['close'].iloc[-1]

            if net_buy > self.params['institution_buy_threshold']:
                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    price=latest_price,
                    reason=f"龙虎榜显示净买入{net_buy/100000000:.2f}亿",
                    confidence=0.65
                ))
            elif net_buy < -self.params['institution_buy_threshold']:
                signals.append(TradeSignal(
                    signal=Signal.SELL,
                    price=latest_price,
                    reason=f"龙虎榜显示净卖出{abs(net_buy)/100000000:.2f}亿",
                    confidence=0.6
                ))

        except Exception as e:
            logger.error(f"龙虎榜策略执行失败: {e}")

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.2
        return int(capital * position_ratio / price / 100) * 100


class CompositeSentimentStrategy(BaseStrategy):
    """
    综合情绪策略
    结合新闻、资金流向、龙虎榜等多维度情绪指标
    """

    def __init__(self, params: Dict = None):
        default_params = {
            'news_weight': 0.3,      # 新闻权重
            'money_flow_weight': 0.4, # 资金流向权重
            'lhb_weight': 0.3,       # 龙虎榜权重
        }
        if params:
            default_params.update(params)
        super().__init__("综合情绪策略", default_params)

    def generate_signals(self, data: pd.DataFrame) -> List[TradeSignal]:
        return []

    def generate_composite_signal(self,
                                   stock_code: str,
                                   price_data: pd.DataFrame,
                                   news_list: List[Dict] = None) -> List[TradeSignal]:
        """
        生成综合情绪信号
        """
        signals = []
        scores = {}

        # 新闻情绪
        if news_list:
            news_sentiment = SentimentAnalyzer.analyze_news_batch(news_list)
            scores['news'] = news_sentiment

        # 资金流向
        try:
            flow_strategy = MoneyFlowStrategy()
            flow_signals = flow_strategy.generate_signal_with_flow(stock_code, price_data)
            if flow_signals:
                scores['money_flow'] = 1 if flow_signals[0].signal == Signal.BUY else -1
        except:
            pass

        # 龙虎榜
        try:
            lhb_strategy = DragonTigerStrategy()
            lhb_signals = lhb_strategy.generate_signal_with_lhb(stock_code, price_data)
            if lhb_signals:
                scores['lhb'] = 1 if lhb_signals[0].signal == Signal.BUY else -1
        except:
            pass

        if not scores:
            return signals

        # 加权计算综合分数
        composite_score = 0
        total_weight = 0

        for key, score in scores.items():
            weight = self.params.get(f'{key}_weight', 0.33)
            composite_score += score * weight
            total_weight += weight

        if total_weight > 0:
            composite_score /= total_weight

        latest_price = price_data['close'].iloc[-1]

        if composite_score > 0.3:
            signals.append(TradeSignal(
                signal=Signal.BUY,
                price=latest_price,
                reason=f"综合情绪积极(分数:{composite_score:.2f})",
                confidence=min(composite_score, 1.0)
            ))
        elif composite_score < -0.3:
            signals.append(TradeSignal(
                signal=Signal.SELL,
                price=latest_price,
                reason=f"综合情绪消极(分数:{composite_score:.2f})",
                confidence=min(abs(composite_score), 1.0)
            ))

        return signals

    def calculate_position(self, capital: float, price: float,
                          signal: TradeSignal) -> int:
        position_ratio = 0.25 * signal.confidence
        return int(capital * position_ratio / price / 100) * 100
