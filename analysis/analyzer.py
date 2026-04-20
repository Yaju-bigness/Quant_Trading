"""
数据分析模块
包含：技术分析、统计分析、因子分析、报告生成、消息面分析
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from loguru import logger
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime, timedelta

from data.data_source import DataSource
from strategy.technical import TechnicalIndicators
from strategy.sentiment import SentimentAnalyzer

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


class NewsAnalyzer:
    """消息面分析"""

    def __init__(self):
        self.data_source = DataSource(use_tdx=False)
        self.sentiment_analyzer = SentimentAnalyzer()

    def analyze_news_sentiment(self, stock_code: str, limit: int = 20) -> Dict:
        """
        分析新闻情绪
        :param stock_code: 股票代码
        :param limit: 新闻数量
        :return: 分析结果
        """
        try:
            news_list = self.data_source.get_news(stock_code, limit)
            if not news_list:
                return {'score': 0, 'status': '无数据', 'news': []}

            # 分析情绪
            sentiment_score = self.sentiment_analyzer.analyze_news_batch(news_list)

            # 统计关键词
            positive_count = 0
            negative_count = 0
            for news in news_list:
                title = news.get('title', '')
                if any(w in title for w in SentimentAnalyzer.POSITIVE_WORDS):
                    positive_count += 1
                if any(w in title for w in SentimentAnalyzer.NEGATIVE_WORDS):
                    negative_count += 1

            # 判断状态
            if sentiment_score > 0.3:
                status = '积极'
            elif sentiment_score > 0.1:
                status = '偏积极'
            elif sentiment_score > -0.1:
                status = '中性'
            elif sentiment_score > -0.3:
                status = '偏消极'
            else:
                status = '消极'

            return {
                'score': sentiment_score,
                'status': status,
                'news': news_list[:10],
                'positive_count': positive_count,
                'negative_count': negative_count,
                'total_count': len(news_list)
            }
        except Exception as e:
            logger.error(f"新闻分析失败: {e}")
            return {'score': 0, 'status': '分析失败', 'news': []}

    def analyze_money_flow(self, stock_code: str) -> Dict:
        """
        分析资金流向
        :param stock_code: 股票代码
        :return: 分析结果
        """
        try:
            df = self.data_source.get_money_flow(stock_code, days=10)
            if df.empty:
                return {'score': 0, 'status': '无数据', 'trend': '未知'}

            # 计算主力资金净流入
            if '主力净流入-净额' in df.columns:
                net_inflow = df['主力净流入-净额'].astype(float)
            else:
                return {'score': 0, 'status': '无数据', 'trend': '未知'}

            # 近3日和近5日净流入
            net_3d = net_inflow.head(3).sum()
            net_5d = net_inflow.head(5).sum()
            net_10d = net_inflow.sum()

            # 判断趋势
            positive_days = (net_inflow > 0).sum()

            if positive_days >= 7:
                trend = '持续流入'
                status = '积极'
                score = 0.8
            elif positive_days >= 5:
                trend = '偏流入'
                status = '偏积极'
                score = 0.5
            elif positive_days >= 3:
                trend = '震荡'
                status = '中性'
                score = 0
            elif positive_days >= 1:
                trend = '偏流出'
                status = '偏消极'
                score = -0.3
            else:
                trend = '持续流出'
                status = '消极'
                score = -0.6

            return {
                'score': score,
                'status': status,
                'trend': trend,
                'net_3d': net_3d,
                'net_5d': net_5d,
                'net_10d': net_10d,
                'positive_days': positive_days,
                'total_days': len(net_inflow)
            }
        except Exception as e:
            logger.error(f"资金流向分析失败: {e}")
            return {'score': 0, 'status': '分析失败', 'trend': '未知'}

    def analyze_comprehensive(self, stock_code: str) -> Dict:
        """
        综合消息面分析
        :param stock_code: 股票代码
        :return: 综合分析结果
        """
        # 新闻情绪
        news_result = self.analyze_news_sentiment(stock_code)

        # 资金流向
        flow_result = self.analyze_money_flow(stock_code)

        # 综合评分（加权平均）
        weights = {'news': 0.4, 'flow': 0.6}
        total_score = (
            news_result['score'] * weights['news'] +
            flow_result['score'] * weights['flow']
        )

        # 综合建议
        if total_score > 0.4:
            suggestion = '消息面积极，可关注买入机会'
            sentiment = '积极'
        elif total_score > 0.1:
            suggestion = '消息面偏积极，可适当关注'
            sentiment = '偏积极'
        elif total_score > -0.1:
            suggestion = '消息面中性，建议观望'
            sentiment = '中性'
        elif total_score > -0.4:
            suggestion = '消息面偏消极，注意风险'
            sentiment = '偏消极'
        else:
            suggestion = '消息面消极，建议谨慎'
            sentiment = '消极'

        return {
            'news': news_result,
            'flow': flow_result,
            'total_score': total_score,
            'sentiment': sentiment,
            'suggestion': suggestion
        }


class TechnicalAnalyzer:
    """技术分析"""

    def __init__(self):
        self.data_source = DataSource(use_tdx=False)

    def analyze_stock(self, stock_code: str,
                      start_date: str,
                      end_date: str) -> Dict:
        """
        综合技术分析
        :param stock_code: 股票代码
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 分析结果
        """
        # 获取数据
        df = self.data_source.get_daily_kline(stock_code, start_date, end_date)
        if df.empty:
            return {}

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # 计算技术指标
        analysis = {
            'stock_code': stock_code,
            'date_range': f"{start_date} ~ {end_date}",
            'latest_price': close.iloc[-1],
            'price_change': (close.iloc[-1] - close.iloc[0]) / close.iloc[0],
            'high_52w': close.rolling(252).max().iloc[-1] if len(close) >= 252 else close.max(),
            'low_52w': close.rolling(252).min().iloc[-1] if len(close) >= 252 else close.min(),
        }

        # 均线分析
        ma5 = TechnicalIndicators.SMA(close, 5).iloc[-1]
        ma10 = TechnicalIndicators.SMA(close, 10).iloc[-1]
        ma20 = TechnicalIndicators.SMA(close, 20).iloc[-1]
        ma60 = TechnicalIndicators.SMA(close, 60).iloc[-1] if len(close) >= 60 else None

        analysis['ma'] = {
            'MA5': ma5,
            'MA10': ma10,
            'MA20': ma20,
            'MA60': ma60,
            'trend': '多头' if ma5 > ma10 > ma20 else '空头' if ma5 < ma10 < ma20 else '震荡'
        }

        # MACD分析
        macd_data = TechnicalIndicators.MACD(close)
        analysis['macd'] = {
            'macd': macd_data['macd'].iloc[-1],
            'signal': macd_data['signal'].iloc[-1],
            'hist': macd_data['hist'].iloc[-1],
            'trend': '多头' if macd_data['hist'].iloc[-1] > 0 else '空头'
        }

        # RSI分析
        rsi = TechnicalIndicators.RSI(close)
        analysis['rsi'] = {
            'value': rsi.iloc[-1],
            'status': '超买' if rsi.iloc[-1] > 70 else '超卖' if rsi.iloc[-1] < 30 else '正常'
        }

        # KDJ分析
        kdj = TechnicalIndicators.KDJ(high, low, close)
        analysis['kdj'] = {
            'K': kdj['K'].iloc[-1],
            'D': kdj['D'].iloc[-1],
            'J': kdj['J'].iloc[-1],
            'status': '超买' if kdj['J'].iloc[-1] > 80 else '超卖' if kdj['J'].iloc[-1] < 20 else '正常'
        }

        # 布林带
        boll = TechnicalIndicators.BOLL(close)
        current_price = close.iloc[-1]
        boll_position = (current_price - boll['lower'].iloc[-1]) / \
                        (boll['upper'].iloc[-1] - boll['lower'].iloc[-1])
        analysis['bollinger'] = {
            'upper': boll['upper'].iloc[-1],
            'mid': boll['mid'].iloc[-1],
            'lower': boll['lower'].iloc[-1],
            'position': boll_position,  # 0-1，0表示下轨，1表示上轨
            'status': '接近上轨' if boll_position > 0.8 else '接近下轨' if boll_position < 0.2 else '中轨附近'
        }

        # 成交量分析
        vol_ma5 = volume.rolling(5).mean().iloc[-1]
        vol_ma10 = volume.rolling(10).mean().iloc[-1]
        analysis['volume'] = {
            'latest': volume.iloc[-1],
            'ma5': vol_ma5,
            'ma10': vol_ma10,
            'ratio': volume.iloc[-1] / vol_ma5,  # 量比
            'status': '放量' if volume.iloc[-1] > vol_ma5 * 1.5 else '缩量' if volume.iloc[-1] < vol_ma5 * 0.5 else '正常'
        }

        # ATR - 波动率
        atr = TechnicalIndicators.ATR(high, low, close)
        analysis['atr'] = atr.iloc[-1]
        analysis['volatility'] = atr.iloc[-1] / current_price  # 波动率

        # 综合评分
        score = 0

        # 均线得分
        if analysis['ma']['trend'] == '多头':
            score += 25
        elif analysis['ma']['trend'] == '空头':
            score -= 25

        # MACD得分
        if analysis['macd']['trend'] == '多头':
            score += 20

        # RSI得分
        if analysis['rsi']['status'] == '超卖':
            score += 15
        elif analysis['rsi']['status'] == '超买':
            score -= 15

        # KDJ得分
        if analysis['kdj']['status'] == '超卖':
            score += 15
        elif analysis['kdj']['status'] == '超买':
            score -= 15

        # 量能得分
        if analysis['volume']['status'] == '放量':
            score += 10

        analysis['score'] = score
        analysis['recommendation'] = self._get_recommendation(score)

        return analysis

    def _get_recommendation(self, score: int) -> str:
        """根据评分给出建议"""
        if score >= 50:
            return "强烈买入"
        elif score >= 30:
            return "买入"
        elif score >= 10:
            return "谨慎买入"
        elif score >= -10:
            return "持有观望"
        elif score >= -30:
            return "谨慎卖出"
        elif score >= -50:
            return "卖出"
        else:
            return "强烈卖出"

    def generate_report(self, analysis: Dict) -> str:
        """生成文字报告"""
        if not analysis:
            return "无法生成报告，数据为空"

        # 处理可能为None的值
        ma60_str = f"{analysis['ma']['MA60']:.2f}" if analysis['ma'].get('MA60') else 'N/A'

        report = f"""
{'='*60}
股票技术分析报告
{'='*60}
股票代码: {analysis['stock_code']}
分析区间: {analysis['date_range']}
最新价格: {analysis['latest_price']:.2f}
区间涨跌: {analysis['price_change']*100:.2f}%
52周最高: {analysis['high_52w']:.2f}
52周最低: {analysis['low_52w']:.2f}

【均线分析】
MA5: {analysis['ma']['MA5']:.2f}
MA10: {analysis['ma']['MA10']:.2f}
MA20: {analysis['ma']['MA20']:.2f}
MA60: {ma60_str}
趋势: {analysis['ma']['trend']}

【MACD分析】
MACD: {analysis['macd']['macd']:.4f}
Signal: {analysis['macd']['signal']:.4f}
Histogram: {analysis['macd']['hist']:.4f}
趋势: {analysis['macd']['trend']}

【RSI分析】
RSI(14): {analysis['rsi']['value']:.2f}
状态: {analysis['rsi']['status']}

【KDJ分析】
K: {analysis['kdj']['K']:.2f}
D: {analysis['kdj']['D']:.2f}
J: {analysis['kdj']['J']:.2f}
状态: {analysis['kdj']['status']}

【布林带分析】
上轨: {analysis['bollinger']['upper']:.2f}
中轨: {analysis['bollinger']['mid']:.2f}
下轨: {analysis['bollinger']['lower']:.2f}
位置: {analysis['bollinger']['position']:.2%}
状态: {analysis['bollinger']['status']}

【成交量分析】
最新成交量: {analysis['volume']['latest']:,.0f}
5日均量: {analysis['volume']['ma5']:,.0f}
10日均量: {analysis['volume']['ma10']:,.0f}
量比: {analysis['volume']['ratio']:.2f}
状态: {analysis['volume']['status']}

【波动率分析】
ATR: {analysis['atr']:.2f}
波动率: {analysis['volatility']:.2%}

{'='*60}
综合评分: {analysis['score']}
操作建议: {analysis['recommendation']}
{'='*60}
"""
        return report

    def plot_analysis(self, stock_code: str, stock_name: str,
                      start_date: str, end_date: str,
                      save_path: str = None,
                      include_news: bool = True):
        """
        绘制技术分析图表
        :param stock_code: 股票代码
        :param stock_name: 股票名称
        :param start_date: 开始日期
        :param end_date: 结束日期
        :param save_path: 保存路径（可选）
        :param include_news: 是否包含消息面分析
        """
        # 获取数据
        df = self.data_source.get_daily_kline(stock_code, start_date, end_date)
        if df.empty:
            logger.error("无法获取数据")
            return

        # 获取分析结果
        analysis = self.analyze_stock(stock_code, start_date, end_date)
        if not analysis:
            return

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # 计算指标
        ma5 = TechnicalIndicators.SMA(close, 5)
        ma10 = TechnicalIndicators.SMA(close, 10)
        ma20 = TechnicalIndicators.SMA(close, 20)
        ma60 = TechnicalIndicators.SMA(close, 60)

        macd_data = TechnicalIndicators.MACD(close)
        rsi = TechnicalIndicators.RSI(close)
        kdj = TechnicalIndicators.KDJ(high, low, close)
        boll = TechnicalIndicators.BOLL(close)

        # 获取消息面分析
        news_analysis = None
        if include_news:
            try:
                news_analyzer = NewsAnalyzer()
                news_analysis = news_analyzer.analyze_comprehensive(stock_code)
            except Exception as e:
                logger.warning(f"消息面分析失败: {e}")

        # 创建图表
        rows = 5 if include_news and news_analysis else 4
        fig = plt.figure(figsize=(16, 4.5 * rows))
        fig.suptitle(f'{stock_name} ({stock_code}) 趋势分析', fontsize=16, fontweight='bold', y=0.98, x=0.06, ha='left')

        # 创建子图网格
        gs = fig.add_gridspec(rows, 2, hspace=0.35, wspace=0.15, top=0.94, bottom=0.05)

        # 日期格式化（只显示月-日，去掉年份）
        date_formatter = mdates.DateFormatter('%m-%d')

        # 1. K线与均线
        ax1 = fig.add_subplot(gs[0, :])
        ax1.plot(df['date'], close, label='收盘价', linewidth=1.5, color='black')
        ax1.plot(df['date'], ma5, label='MA5', linewidth=1, alpha=0.8)
        ax1.plot(df['date'], ma10, label='MA10', linewidth=1, alpha=0.8)
        ax1.plot(df['date'], ma20, label='MA20', linewidth=1, alpha=0.8)
        ax1.plot(df['date'], ma60, label='MA60', linewidth=1, alpha=0.8)
        ax1.fill_between(df['date'], boll['upper'], boll['lower'], alpha=0.1, color='gray', label='布林带')
        ax1.set_title('K线与均线', fontsize=12)
        ax1.set_ylabel('价格')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(date_formatter)
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=0, fontsize=8)

        # 2. MACD
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.plot(df['date'], macd_data['macd'], label='MACD', linewidth=1)
        ax2.plot(df['date'], macd_data['signal'], label='Signal', linewidth=1)
        colors = ['red' if x >= 0 else 'green' for x in macd_data['hist']]
        ax2.bar(df['date'], macd_data['hist'], color=colors, alpha=0.3, label='Histogram')
        ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
        ax2.set_title('MACD指标', fontsize=12)
        ax2.legend(loc='upper left', fontsize=8)
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(date_formatter)
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=0, fontsize=8)

        # 3. RSI
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.plot(df['date'], rsi, label='RSI(14)', linewidth=1.5, color='purple')
        ax3.axhline(y=70, color='red', linestyle='--', linewidth=0.8, label='超买线(70)')
        ax3.axhline(y=30, color='green', linestyle='--', linewidth=0.8, label='超卖线(30)')
        ax3.axhline(y=50, color='gray', linestyle='-', linewidth=0.5)
        ax3.fill_between(df['date'], 30, 70, alpha=0.1, color='gray')
        ax3.set_title('RSI指标', fontsize=12)
        ax3.set_ylim(0, 100)
        ax3.legend(loc='upper left', fontsize=8)
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(date_formatter)
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=0, fontsize=8)

        # 4. KDJ
        ax4 = fig.add_subplot(gs[2, 0])
        ax4.plot(df['date'], kdj['K'], label='K', linewidth=1)
        ax4.plot(df['date'], kdj['D'], label='D', linewidth=1)
        ax4.plot(df['date'], kdj['J'], label='J', linewidth=1, alpha=0.7)
        ax4.axhline(y=80, color='red', linestyle='--', linewidth=0.8)
        ax4.axhline(y=20, color='green', linestyle='--', linewidth=0.8)
        ax4.set_title('KDJ指标', fontsize=12)
        ax4.legend(loc='upper left', fontsize=8)
        ax4.grid(True, alpha=0.3)
        ax4.xaxis.set_major_formatter(date_formatter)
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=0, fontsize=8)

        # 5. 成交量
        ax5 = fig.add_subplot(gs[2, 1])
        colors = ['red' if close.iloc[i] >= close.iloc[i-1] else 'green'
                  for i in range(1, len(close))]
        colors.insert(0, 'gray')
        ax5.bar(df['date'], volume, color=colors, alpha=0.6)
        vol_ma5 = volume.rolling(5).mean()
        vol_ma10 = volume.rolling(10).mean()
        ax5.plot(df['date'], vol_ma5, label='VOL MA5', linewidth=1, color='orange')
        ax5.plot(df['date'], vol_ma10, label='VOL MA10', linewidth=1, color='blue')
        ax5.set_title('成交量', fontsize=12)
        ax5.legend(loc='upper left', fontsize=8)
        ax5.grid(True, alpha=0.3)
        ax5.xaxis.set_major_formatter(date_formatter)
        plt.setp(ax5.xaxis.get_majorticklabels(), rotation=0, fontsize=8)

        # 6. 综合评分与建议
        ax6 = fig.add_subplot(gs[3, :])
        ax6.axis('off')

        score = analysis['score']
        recommendation = analysis['recommendation']

        # 根据建议设置颜色
        recommendation_colors = {
            '强烈买入': 'darkgreen',
            '买入': 'green',
            '谨慎买入': 'olive',
            '持有观望': 'gray',
            '谨慎卖出': 'orange',
            '卖出': 'red',
            '强烈卖出': 'darkred',
        }
        rec_color = recommendation_colors.get(recommendation, 'black')

        # 评分颜色
        if score >= 50:
            score_color = 'darkgreen'
        elif score >= 30:
            score_color = 'green'
        elif score >= 10:
            score_color = 'olive'
        elif score >= -10:
            score_color = 'gray'
        elif score >= -30:
            score_color = 'orange'
        elif score >= -50:
            score_color = 'red'
        else:
            score_color = 'darkred'

        # 分隔线
        ax6.plot([0.05, 0.95], [0.95, 0.95], color='lightgray', linewidth=1, transform=ax6.transAxes)

        # 标题
        ax6.text(0.5, 0.82, '【技术面分析】',
                transform=ax6.transAxes, fontsize=14, fontweight='bold',
                ha='center', va='center')

        # 操作建议（去掉背景色，只用颜色区分）
        ax6.text(0.5, 0.62, f'操作建议: {recommendation}',
                transform=ax6.transAxes, fontsize=16, fontweight='bold',
                color=rec_color, ha='center', va='center')

        # 评分显示
        ax6.text(0.5, 0.45, f'综合评分: {score}',
                transform=ax6.transAxes, fontsize=14, fontweight='bold',
                color=score_color, ha='center', va='center')

        # 详细指标 - 分两行显示
        detail_line1 = f"均线趋势: {analysis['ma']['trend']}    MACD: {analysis['macd']['trend']}    RSI: {analysis['rsi']['value']:.1f} ({analysis['rsi']['status']})"
        detail_line2 = f"KDJ: {analysis['kdj']['status']}    布林带: {analysis['bollinger']['status']}    量能: {analysis['volume']['status']}"

        ax6.text(0.5, 0.30, detail_line1,
                transform=ax6.transAxes, fontsize=11,
                color='black', ha='center', va='center')
        ax6.text(0.5, 0.18, detail_line2,
                transform=ax6.transAxes, fontsize=11,
                color='black', ha='center', va='center')

        # 价格信息
        price_text = (f"最新价: {analysis['latest_price']:.2f}    "
                     f"区间涨跌: {analysis['price_change']*100:+.2f}%    "
                     f"波动率: {analysis['volatility']:.2%}")
        ax6.text(0.5, 0.06, price_text,
                transform=ax6.transAxes, fontsize=10,
                color='gray', ha='center', va='center')

        # 7. 消息面分析（如果启用）
        if include_news and news_analysis:
            ax7 = fig.add_subplot(gs[4, :])
            ax7.axis('off')

            # 消息面标题
            news_sentiment = news_analysis['sentiment']
            news_suggestion = news_analysis['suggestion']
            news_score = news_analysis['total_score']

            # 消息面情绪颜色
            sentiment_colors = {
                '积极': 'darkgreen',
                '偏积极': 'green',
                '中性': 'gray',
                '偏消极': 'orange',
                '消极': 'red',
            }
            news_color = sentiment_colors.get(news_sentiment, 'gray')

            # 分隔线
            ax7.plot([0.05, 0.95], [0.95, 0.95], color='lightgray', linewidth=1, transform=ax7.transAxes)

            # 消息面标题
            ax7.text(0.5, 0.82, '【消息面分析】',
                    transform=ax7.transAxes, fontsize=14, fontweight='bold',
                    ha='center', va='center')

            # 消息面情绪（去掉背景色）
            ax7.text(0.5, 0.62, f'消息面情绪: {news_sentiment}',
                    transform=ax7.transAxes, fontsize=14, fontweight='bold',
                    color=news_color, ha='center', va='center')

            # 消息面建议
            ax7.text(0.5, 0.45, news_suggestion,
                    transform=ax7.transAxes, fontsize=12,
                    ha='center', va='center')

            # 新闻情绪详情
            news_info = news_analysis.get('news', {})
            flow_info = news_analysis.get('flow', {})

            detail_line1 = ""
            detail_line2 = ""

            if news_info:
                detail_line1 = f"新闻情绪: {news_info.get('status', '未知')}    (利好 {news_info.get('positive_count', 0)} 条 / 利空 {news_info.get('negative_count', 0)} 条)"
            if flow_info:
                detail_line2 = f"资金流向: {flow_info.get('trend', '未知')}"

            if detail_line1:
                ax7.text(0.5, 0.30, detail_line1,
                        transform=ax7.transAxes, fontsize=11,
                        color='gray', ha='center', va='center')
            if detail_line2:
                ax7.text(0.5, 0.18, detail_line2,
                        transform=ax7.transAxes, fontsize=11,
                        color='gray', ha='center', va='center')

            # 最新新闻标题（如果有）
            if news_info and news_info.get('news'):
                news_list = news_info['news'][:2]  # 只显示2条
                news_titles = ' | '.join([f"{n.get('title', '')[:35]}..." for n in news_list])
                ax7.text(0.5, 0.06, f"近期: {news_titles}",
                        transform=ax7.transAxes, fontsize=10,
                        color='dimgray', ha='center', va='center')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"图表已保存: {save_path}")

        plt.show()


class PerformanceAnalyzer:
    """绩效分析"""

    def __init__(self):
        pass

    def analyze_returns(self,
                        equity_curve: List[Dict],
                        benchmark_data: pd.DataFrame = None) -> Dict:
        """
        分析收益表现
        :param equity_curve: 权益曲线
        :param benchmark_data: 基准数据
        """
        if not equity_curve:
            return {}

        equity_df = pd.DataFrame(equity_curve)
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        equity_df = equity_df.set_index('date')

        # 计算日收益率
        equity_df['returns'] = equity_df['equity'].pct_change()

        results = {
            'total_return': (equity_df['equity'].iloc[-1] / equity_df['equity'].iloc[0]) - 1,
            'annual_return': self._annual_return(equity_df['equity']),
            'volatility': self._annual_volatility(equity_df['returns']),
            'sharpe_ratio': 0,
            'max_drawdown': self._max_drawdown(equity_df['equity']),
            'win_days': (equity_df['returns'] > 0).sum(),
            'loss_days': (equity_df['returns'] < 0).sum(),
        }

        # 夏普比率
        risk_free = 0.03 / 252
        excess_returns = equity_df['returns'] - risk_free
        if len(excess_returns) > 0 and excess_returns.std() > 0:
            results['sharpe_ratio'] = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)

        # Sortino比率
        downside_returns = equity_df['returns'][equity_df['returns'] < 0]
        if len(downside_returns) > 0:
            downside_std = downside_returns.std()
            if downside_std > 0:
                results['sortino_ratio'] = (excess_returns.mean() / downside_std) * np.sqrt(252)

        # 基准对比
        if benchmark_data is not None and not benchmark_data.empty:
            benchmark_data['date'] = pd.to_datetime(benchmark_data['date'])
            benchmark_data = benchmark_data.set_index('date')

            # 对齐日期
            aligned = equity_df.join(benchmark_data['close'].rename('benchmark'),
                                     how='inner')
            if len(aligned) > 1:
                aligned['benchmark_returns'] = aligned['benchmark'].pct_change()
                results['alpha'] = results['annual_return'] - \
                                   self._annual_return(aligned['benchmark'])
                results['beta'] = self._calculate_beta(
                    aligned['returns'].dropna(),
                    aligned['benchmark_returns'].dropna()
                )

        return results

    def _annual_return(self, series: pd.Series) -> float:
        """计算年化收益"""
        if len(series) < 2:
            return 0
        total_return = series.iloc[-1] / series.iloc[0] - 1
        days = (series.index[-1] - series.index[0]).days
        if days > 0:
            return (1 + total_return) ** (252 / days) - 1
        return 0

    def _annual_volatility(self, returns: pd.Series) -> float:
        """计算年化波动率"""
        if len(returns) < 2:
            return 0
        return returns.std() * np.sqrt(252)

    def _max_drawdown(self, equity: pd.Series) -> float:
        """计算最大回撤"""
        if len(equity) < 2:
            return 0
        peak = equity.expanding().max()
        drawdown = (equity - peak) / peak
        return drawdown.min()

    def _calculate_beta(self, returns: pd.Series,
                        benchmark_returns: pd.Series) -> float:
        """计算Beta"""
        if len(returns) < 2 or len(benchmark_returns) < 2:
            return 0
        covariance = returns.cov(benchmark_returns)
        variance = benchmark_returns.var()
        if variance > 0:
            return covariance / variance
        return 0


class MarketAnalyzer:
    """市场分析"""

    def __init__(self):
        self.data_source = DataSource(use_tdx=False)

    def analyze_market_sentiment(self) -> Dict:
        """
        分析市场情绪
        """
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare未安装，无法进行市场情绪分析")
            return {}

        try:
            # 获取涨跌停数据
            up_limit = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
            down_limit = ak.stock_zt_pool_dtgc_em(date=datetime.now().strftime('%Y%m%d'))

            up_count = len(up_limit) if not up_limit.empty else 0
            down_count = len(down_limit) if not down_limit.empty else 0

            # 获取大盘数据
            sh_index = self.data_source.get_index_data('000001')
            sh_change = sh_index['close'].pct_change().iloc[-1] if not sh_index.empty else 0

            return {
                'up_limit_count': up_count,
                'down_limit_count': down_count,
                'ratio': up_count / down_count if down_count > 0 else up_count,
                'index_change': sh_change,
                'sentiment': '亢奋' if up_count > 100 else '低迷' if down_count > up_count else '正常'
            }
        except Exception as e:
            logger.error(f"市场情绪分析失败: {e}")
            return {}

    def get_sector_performance(self) -> pd.DataFrame:
        """
        获取板块表现
        """
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare未安装，无法获取板块数据")
            return pd.DataFrame()

        try:
            df = ak.stock_board_industry_name_em()
            return df
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return pd.DataFrame()

    def analyze_today_volume(self, stock_code: str) -> Dict:
        """
        分析今日交易量
        :param stock_code: 股票代码
        :return: 交易量分析结果
        """
        try:
            # 获取最近30天K线数据
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

            df = self.data_source.get_daily_kline(stock_code, start_date, end_date)
            if df.empty or len(df) < 5:
                return {'status': '数据不足', 'score': 0}

            # 最新一日数据
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]

            volume = latest['volume']
            amount = latest.get('amount', volume * latest['close'])

            # 计算成交量均线
            vol_ma5 = df['volume'].tail(5).mean()
            vol_ma10 = df['volume'].tail(10).mean()
            vol_ma20 = df['volume'].tail(20).mean()

            # 量比 = 今日成交量 / 5日均量
            volume_ratio = volume / vol_ma5 if vol_ma5 > 0 else 1

            # 换手率（如果有）
            turnover = latest.get('turnover', 0)

            # 成交额变化
            amount_ma5 = df['amount'].tail(5).mean() if 'amount' in df.columns else vol_ma5 * df['close'].tail(5).mean()
            amount_ratio = amount / amount_ma5 if amount_ma5 > 0 else 1

            # 价格涨跌
            price_change = (latest['close'] - prev['close']) / prev['close'] * 100 if prev['close'] > 0 else 0

            # 判断量能状态
            if volume_ratio > 2.0:
                volume_status = '巨量'
                volume_score = 0.8
            elif volume_ratio > 1.5:
                volume_status = '放量'
                volume_score = 0.5
            elif volume_ratio > 1.0:
                volume_status = '温和放量'
                volume_score = 0.2
            elif volume_ratio > 0.7:
                volume_status = '正常'
                volume_score = 0
            elif volume_ratio > 0.5:
                volume_status = '缩量'
                volume_score = -0.2
            else:
                volume_status = '地量'
                volume_score = -0.3

            # 价量配合分析
            if price_change > 0 and volume_ratio > 1.2:
                price_volume_status = '价涨量增（健康）'
                price_volume_score = 0.5
            elif price_change > 0 and volume_ratio < 0.8:
                price_volume_status = '价涨量缩（背离）'
                price_volume_score = -0.3
            elif price_change < 0 and volume_ratio > 1.2:
                price_volume_status = '价跌量增（恐慌）'
                price_volume_score = -0.4
            elif price_change < 0 and volume_ratio < 0.8:
                price_volume_status = '价跌量缩（惜售）'
                price_volume_score = 0.1
            else:
                price_volume_status = '价量正常'
                price_volume_score = 0

            # 综合评分
            total_score = volume_score + price_volume_score

            return {
                'volume': volume,
                'amount': amount,
                'volume_ratio': volume_ratio,
                'amount_ratio': amount_ratio,
                'vol_ma5': vol_ma5,
                'vol_ma10': vol_ma10,
                'vol_ma20': vol_ma20,
                'turnover': turnover,
                'volume_status': volume_status,
                'price_change_pct': price_change,
                'price_volume_status': price_volume_status,
                'score': total_score,
                'suggestion': self._get_volume_suggestion(volume_status, price_volume_status)
            }
        except Exception as e:
            logger.error(f"今日交易量分析失败: {e}")
            return {'status': '分析失败', 'score': 0}

    def _get_volume_suggestion(self, volume_status: str, price_volume_status: str) -> str:
        """根据量能状态给出建议"""
        if '价涨量增' in price_volume_status:
            return '量价配合良好，上涨趋势健康'
        elif '价涨量缩' in price_volume_status:
            return '量价背离，注意回调风险'
        elif '价跌量增' in price_volume_status:
            return '放量下跌，可能存在恐慌抛售'
        elif '价跌量缩' in price_volume_status:
            return '缩量下跌，抛压较轻'
        elif volume_status in ['巨量', '放量']:
            return '成交活跃，关注资金动向'
        elif volume_status in ['缩量', '地量']:
            return '成交清淡，市场观望情绪浓厚'
        return '量能正常'

    def analyze_market_overview(self) -> Dict:
        """
        大盘情绪分析
        :return: 大盘分析结果
        """
        result = {
            'indices': {},
            'market_breadth': {},
            'sentiment': '中性',
            'score': 0,
            'suggestion': ''
        }

        try:
            # 1. 获取主要指数数据
            indices_df = self.data_source.get_index_realtime()
            if not indices_df.empty:
                for _, row in indices_df.iterrows():
                    code = row.get('code', '')
                    name = row.get('name', '')
                    pct_change = row.get('pct_change', 0)

                    # 处理pct_change可能是字符串的情况
                    if isinstance(pct_change, str):
                        pct_change = float(pct_change.replace('%', ''))

                    result['indices'][code] = {
                        'name': name,
                        'pct_change': pct_change,
                        'price': row.get('price', 0),
                        'volume': row.get('volume', 0),
                        'amount': row.get('amount', 0)
                    }

            # 2. 获取市场涨跌统计
            overview = self.data_source.get_market_overview()
            if overview:
                result['market_breadth'] = overview

            # 3. 计算市场情绪得分
            score = 0

            # 指数涨跌贡献
            for code, idx_data in result['indices'].items():
                pct = idx_data.get('pct_change', 0)
                if pct > 1:
                    score += 20
                elif pct > 0.5:
                    score += 10
                elif pct < -1:
                    score -= 20
                elif pct < -0.5:
                    score -= 10

            # 涨跌比贡献
            if overview:
                up_ratio = overview.get('up_ratio', 0.5)
                if up_ratio > 0.7:
                    score += 25
                elif up_ratio > 0.55:
                    score += 10
                elif up_ratio < 0.3:
                    score -= 25
                elif up_ratio < 0.45:
                    score -= 10

                # 涨跌停贡献
                limit_up = overview.get('limit_up', 0)
                limit_down = overview.get('limit_down', 0)
                if limit_up > 80:
                    score += 15
                elif limit_up > 50:
                    score += 8
                if limit_down > 50:
                    score -= 15
                elif limit_down > 30:
                    score -= 8

            result['score'] = score

            # 4. 判断市场情绪
            if score > 40:
                result['sentiment'] = '极度亢奋'
                result['suggestion'] = '市场情绪高涨，注意追高风险'
            elif score > 20:
                result['sentiment'] = '偏强'
                result['suggestion'] = '市场情绪较好，可适度参与'
            elif score > 0:
                result['sentiment'] = '偏暖'
                result['suggestion'] = '市场情绪温和，谨慎操作'
            elif score > -20:
                result['sentiment'] = '中性偏弱'
                result['suggestion'] = '市场情绪一般，建议观望'
            elif score > -40:
                result['sentiment'] = '偏弱'
                result['suggestion'] = '市场情绪低迷，控制仓位'
            else:
                result['sentiment'] = '极度低迷'
                result['suggestion'] = '市场情绪恐慌，等待企稳'

        except Exception as e:
            logger.error(f"大盘情绪分析失败: {e}")

        return result

    def analyze_sector_sentiment(self, top_n: int = 10) -> Dict:
        """
        板块情绪分析
        :param top_n: 返回前N个板块
        :return: 板块分析结果
        """
        result = {
            'hot_sectors': [],      # 热门板块
            'weak_sectors': [],     # 弱势板块
            'industry_sectors': [], # 行业板块详情
            'concept_sectors': [],  # 概念板块详情
            'sentiment': '中性',
            'score': 0,
            'suggestion': ''
        }

        try:
            # 1. 获取行业板块数据
            industry_df = self.data_source.get_sector_data()
            if not industry_df.empty:
                # 按涨跌幅排序
                if 'pct_change' in industry_df.columns:
                    industry_df['pct_change_num'] = pd.to_numeric(industry_df['pct_change'], errors='coerce')
                    industry_df = industry_df.sort_values('pct_change_num', ascending=False)

                    # 热门板块
                    hot = industry_df.head(top_n)
                    for _, row in hot.iterrows():
                        result['hot_sectors'].append({
                            'name': row.get('name', ''),
                            'code': row.get('code', ''),
                            'pct_change': row.get('pct_change', 0),
                            'leading_stock': row.get('leading_stock', ''),
                            'amount': row.get('amount', 0)
                        })

                    # 弱势板块
                    weak = industry_df.tail(top_n)
                    for _, row in weak.iloc[::-1].iterrows():
                        result['weak_sectors'].append({
                            'name': row.get('name', ''),
                            'code': row.get('code', ''),
                            'pct_change': row.get('pct_change', 0),
                            'leading_stock': row.get('leading_stock', ''),
                            'amount': row.get('amount', 0)
                        })

                result['industry_sectors'] = industry_df.to_dict('records')[:30]

            # 2. 获取概念板块数据
            concept_df = self.data_source.get_concept_sectors()
            if not concept_df.empty:
                if 'pct_change' in concept_df.columns:
                    concept_df['pct_change_num'] = pd.to_numeric(concept_df['pct_change'], errors='coerce')
                    concept_df = concept_df.sort_values('pct_change_num', ascending=False)

                result['concept_sectors'] = concept_df.to_dict('records')[:30]

            # 3. 计算板块情绪得分
            score = 0

            if result['hot_sectors']:
                # 热门板块平均涨幅
                hot_avg = 0
                for s in result['hot_sectors'][:5]:
                    pct = s.get('pct_change', 0)
                    if isinstance(pct, str):
                        pct = float(pct.replace('%', ''))
                    hot_avg += pct
                hot_avg /= 5

                if hot_avg > 3:
                    score += 30
                elif hot_avg > 1.5:
                    score += 15
                elif hot_avg > 0.5:
                    score += 5

            if result['weak_sectors']:
                # 弱势板块平均跌幅
                weak_avg = 0
                for s in result['weak_sectors'][:5]:
                    pct = s.get('pct_change', 0)
                    if isinstance(pct, str):
                        pct = float(pct.replace('%', ''))
                    weak_avg += pct
                weak_avg /= 5

                if weak_avg < -3:
                    score -= 30
                elif weak_avg < -1.5:
                    score -= 15
                elif weak_avg < -0.5:
                    score -= 5

            # 统计涨跌板块数量
            if not industry_df.empty and 'pct_change_num' in industry_df.columns:
                up_count = len(industry_df[industry_df['pct_change_num'] > 0])
                down_count = len(industry_df[industry_df['pct_change_num'] < 0])
                total = up_count + down_count

                if total > 0:
                    up_ratio = up_count / total
                    if up_ratio > 0.7:
                        score += 20
                    elif up_ratio > 0.55:
                        score += 10
                    elif up_ratio < 0.3:
                        score -= 20
                    elif up_ratio < 0.45:
                        score -= 10

            result['score'] = score

            # 4. 判断板块情绪
            if score > 30:
                result['sentiment'] = '板块普涨'
                result['suggestion'] = '板块轮动活跃，热点明确，可积极参与'
            elif score > 15:
                result['sentiment'] = '偏强'
                result['suggestion'] = '板块多数上涨，关注热点持续性'
            elif score > 0:
                result['sentiment'] = '分化'
                result['suggestion'] = '板块涨跌互现，精选强势板块'
            elif score > -15:
                result['sentiment'] = '偏弱'
                result['suggestion'] = '板块多数下跌，控制仓位'
            else:
                result['sentiment'] = '普跌'
                result['suggestion'] = '板块普遍下跌，规避风险'

        except Exception as e:
            logger.error(f"板块情绪分析失败: {e}")

        return result


class ReportGenerator:
    """报告生成器"""

    def __init__(self):
        self.tech_analyzer = TechnicalAnalyzer()
        self.perf_analyzer = PerformanceAnalyzer()

    def generate_daily_report(self,
                              stock_list: Dict[str, str],
                              date: str = None) -> str:
        """
        生成日报
        :param stock_list: 股票列表 {name: code}
        :param date: 日期，默认今天
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        report_lines = [
            f"{'='*60}",
            f"量化交易日报 - {date}",
            f"{'='*60}\n"
        ]

        for name, code in stock_list.items():
            analysis = self.tech_analyzer.analyze_stock(
                code,
                (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'),
                date
            )

            if analysis:
                report_lines.append(f"【{name} ({code})】")
                report_lines.append(f"最新价: {analysis['latest_price']:.2f}")
                report_lines.append(f"综合评分: {analysis['score']}")
                report_lines.append(f"操作建议: {analysis['recommendation']}")
                report_lines.append(f"均线趋势: {analysis['ma']['trend']}")
                report_lines.append(f"RSI: {analysis['rsi']['value']:.1f} ({analysis['rsi']['status']})")
                report_lines.append(f"KDJ状态: {analysis['kdj']['status']}")
                report_lines.append("")

        return "\n".join(report_lines)


if __name__ == '__main__':
    # 测试技术分析
    analyzer = TechnicalAnalyzer()
    analysis = analyzer.analyze_stock('300308', '2024-01-01', '2024-12-31')
    print(analyzer.generate_report(analysis))
