"""
HTML报告生成器
生成美观的HTML格式分析报告
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
import os

from data.data_source import DataSource
from strategy.technical import TechnicalIndicators
from strategy.sentiment import SentimentAnalyzer
from analysis.analyzer import NewsAnalyzer


class HTMLReportGenerator:
    """HTML报告生成器"""

    def __init__(self):
        self.data_source = DataSource(use_tdx=False)
        self.news_analyzer = NewsAnalyzer()

    def generate_html_report(self, stock_code: str, stock_name: str,
                             start_date: str, end_date: str,
                             include_news: bool = True) -> str:
        """
        生成HTML分析报告
        """
        # 获取K线数据
        df = self.data_source.get_daily_kline(stock_code, start_date, end_date)
        if df.empty:
            logger.error("无法获取数据")
            return ""

        # 计算技术指标
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        ma5 = TechnicalIndicators.SMA(close, 5)
        ma10 = TechnicalIndicators.SMA(close, 10)
        ma20 = TechnicalIndicators.SMA(close, 20)
        ma60 = TechnicalIndicators.SMA(close, 60)

        macd_data = TechnicalIndicators.MACD(close)
        rsi = TechnicalIndicators.RSI(close)
        kdj = TechnicalIndicators.KDJ(high, low, close)
        boll = TechnicalIndicators.BOLL(close)

        # 计算评分
        score, recommendation = self._calculate_score(
            close, ma5, ma10, ma20, ma60, macd_data, rsi, kdj, volume
        )

        # 获取消息面分析
        news_analysis = None
        if include_news:
            try:
                news_analysis = self.news_analyzer.analyze_comprehensive(stock_code)
            except Exception as e:
                logger.warning(f"消息面分析失败: {e}")

        # 准备图表数据
        chart_data = self._prepare_chart_data(
            df, ma5, ma10, ma20, ma60, macd_data, rsi, kdj, boll, volume
        )

        # 生成HTML
        html = self._render_html(
            stock_code, stock_name, start_date, end_date,
            df, chart_data, score, recommendation,
            macd_data, rsi, kdj, boll, ma5, ma10, ma20, news_analysis
        )

        return html

    def _calculate_score(self, close, ma5, ma10, ma20, ma60, macd_data, rsi, kdj, volume):
        """计算综合评分"""
        score = 0

        # MA判断
        if ma5.iloc[-1] > ma10.iloc[-1] > ma20.iloc[-1]:
            score += 25
        elif ma5.iloc[-1] < ma10.iloc[-1] < ma20.iloc[-1]:
            score -= 25

        # MACD判断
        if macd_data['hist'].iloc[-1] > 0:
            score += 20

        # RSI判断
        rsi_val = rsi.iloc[-1]
        if rsi_val < 30:
            score += 15
        elif rsi_val > 70:
            score -= 15

        # KDJ判断
        j_val = kdj['J'].iloc[-1]
        if j_val < 20:
            score += 15
        elif j_val > 80:
            score -= 15

        # 量能判断
        vol_ma5 = volume.rolling(5).mean().iloc[-1]
        if volume.iloc[-1] > vol_ma5 * 1.5:
            score += 10

        # 生成建议
        if score >= 50:
            recommendation = "强烈买入"
        elif score >= 30:
            recommendation = "买入"
        elif score >= 10:
            recommendation = "谨慎买入"
        elif score >= -10:
            recommendation = "持有观望"
        elif score >= -30:
            recommendation = "谨慎卖出"
        elif score >= -50:
            recommendation = "卖出"
        else:
            recommendation = "强烈卖出"

        return score, recommendation

    def _prepare_chart_data(self, df, ma5, ma10, ma20, ma60, macd_data, rsi, kdj, boll, volume):
        """准备图表数据"""
        dates = [d.strftime('%m-%d') for d in df['date']]

        # 计算成交量颜色：涨红跌绿
        close_list = df['close'].tolist()
        volume_colors = []
        for i in range(len(close_list)):
            if i == 0:
                volume_colors.append('#DC143C')  # 第一根默认红色
            else:
                if close_list[i] >= close_list[i-1]:
                    volume_colors.append('#DC143C')  # 涨 - 红色
                else:
                    volume_colors.append('#228B22')  # 跌 - 绿色

        return {
            'dates': dates,
            'close': close_list,
            'ma5': ma5.tolist(),
            'ma10': ma10.tolist(),
            'ma20': ma20.tolist(),
            'ma60': [v if not pd.isna(v) else None for v in ma60.tolist()],
            'boll_upper': boll['upper'].tolist(),
            'boll_lower': boll['lower'].tolist(),
            'macd': macd_data['macd'].tolist(),
            'macd_signal': macd_data['signal'].tolist(),
            'macd_hist': macd_data['hist'].tolist(),
            'rsi': rsi.tolist(),
            'kdj_k': kdj['K'].tolist(),
            'kdj_d': kdj['D'].tolist(),
            'kdj_j': kdj['J'].tolist(),
            'volume': volume.tolist(),
            'volume_colors': volume_colors,
        }

    def _render_html(self, stock_code, stock_name, start_date, end_date,
                     df, chart_data, score, recommendation,
                     macd_data, rsi, kdj, boll, ma5, ma10, ma20, news_analysis):
        """渲染HTML页面"""

        # 最新价格信息
        latest_price = df['close'].iloc[-1]
        price_change = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0] * 100
        high_52w = df['close'].max()
        low_52w = df['close'].min()

        # 颜色映射（红涨绿跌）
        rec_colors = {
            '强烈买入': '#DC143C',
            '买入': '#FF4500',
            '谨慎买入': '#FF6347',
            '持有观望': '#808080',
            '谨慎卖出': '#32CD32',
            '卖出': '#228B22',
            '强烈卖出': '#006400',
        }
        rec_color = rec_colors.get(recommendation, '#808080')

        score_color = '#DC143C' if score >= 30 else '#FF6347' if score >= 10 else '#808080' if score >= -10 else '#32CD32' if score >= -30 else '#228B22'

        # 消息面分析部分
        news_html = ""
        if news_analysis:
            news_sentiment = news_analysis['sentiment']
            news_suggestion = news_analysis['suggestion']
            news_info = news_analysis.get('news', {})
            flow_info = news_analysis.get('flow', {})

            sentiment_colors = {
                '积极': '#DC143C',
                '偏积极': '#FF6347',
                '中性': '#808080',
                '偏消极': '#32CD32',
                '消极': '#228B22',
            }
            news_color = sentiment_colors.get(news_sentiment, '#808080')

            news_html = f"""
            <div class="section">
                <h2>【消息面分析】</h2>
                <div class="sentiment-box" style="border-color: {news_color}">
                    <div class="sentiment-label" style="color: {news_color}">消息面情绪: {news_sentiment}</div>
                    <div class="suggestion">{news_suggestion}</div>
                </div>
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="label">新闻情绪:</span>
                        <span class="value">{news_info.get('status', '未知')} (利好 <span style="color:#DC143C">{news_info.get('positive_count', 0)}</span> 条 / 利空 <span style="color:#228B22">{news_info.get('negative_count', 0)}</span> 条)</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">资金流向:</span>
                        <span class="value">{flow_info.get('trend', '未知')}</span>
                    </div>
                </div>
            </div>
            """

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{stock_name} ({stock_code}) 技术分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: #fff;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            padding: 30px 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header .subtitle {{
            font-size: 14px;
            color: #aaa;
        }}
        .content {{
            padding: 30px 40px;
        }}
        .section {{
            margin-bottom: 30px;
            padding: 25px;
            background: #f8f9fa;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }}
        .section h2 {{
            font-size: 18px;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }}
        .recommendation-box {{
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 15px;
            margin-bottom: 20px;
        }}
        .recommendation {{
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 15px;
        }}
        .score {{
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 15px;
        }}
        .detail-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .detail-item {{
            background: #fff;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        .detail-item .label {{
            font-weight: bold;
            color: #666;
            margin-right: 10px;
        }}
        .detail-item .value {{
            color: #333;
        }}
        .chart-container {{
            background: #fff;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 15px rgba(0,0,0,0.08);
        }}
        .chart-title {{
            font-size: 16px;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }}
        .chart {{
            width: 100%;
            height: 350px;
        }}
        .charts-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 900px) {{
            .charts-row {{
                grid-template-columns: 1fr;
            }}
        }}
        .sentiment-box {{
            text-align: center;
            padding: 25px;
            background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
            border-radius: 15px;
            margin-bottom: 20px;
            border-left: 4px solid;
        }}
        .sentiment-label {{
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .suggestion {{
            font-size: 16px;
            color: #666;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{stock_name} ({stock_code}) 技术分析报告</h1>
            <div class="subtitle">分析区间: {start_date} ~ {end_date} | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <div class="content">
            <!-- 技术面分析 -->
            <div class="section">
                <h2>【技术面分析】</h2>
                <div class="recommendation-box">
                    <div class="recommendation" style="color: {rec_color}">操作建议: {recommendation}</div>
                    <div class="score" style="color: {score_color}">综合评分: {score}</div>
                </div>
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="label">最新价:</span>
                        <span class="value">{latest_price:.2f}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">区间涨跌:</span>
                        <span class="value" style="color: {'#DC143C' if price_change >= 0 else '#228B22'}">{price_change:+.2f}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">52周最高:</span>
                        <span class="value">{high_52w:.2f}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">52周最低:</span>
                        <span class="value">{low_52w:.2f}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">均线趋势:</span>
                        <span class="value">{'多头排列' if ma5.iloc[-1] > ma10.iloc[-1] > ma20.iloc[-1] else '空头排列' if ma5.iloc[-1] < ma10.iloc[-1] < ma20.iloc[-1] else '震荡'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">MACD:</span>
                        <span class="value">{'多头' if macd_data['hist'].iloc[-1] > 0 else '空头'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">RSI:</span>
                        <span class="value">{rsi.iloc[-1]:.1f} ({'超买' if rsi.iloc[-1] > 70 else '超卖' if rsi.iloc[-1] < 30 else '正常'})</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">KDJ:</span>
                        <span class="value">{'超买' if kdj['J'].iloc[-1] > 80 else '超卖' if kdj['J'].iloc[-1] < 20 else '正常'}</span>
                    </div>
                </div>
            </div>

            <!-- K线图 -->
            <div class="chart-container">
                <div class="chart-title">K线与均线</div>
                <div id="chart-kline" class="chart"></div>
            </div>

            <!-- 技术指标图表 -->
            <div class="charts-row">
                <div class="chart-container">
                    <div class="chart-title">MACD指标</div>
                    <div id="chart-macd" class="chart"></div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">RSI指标</div>
                    <div id="chart-rsi" class="chart"></div>
                </div>
            </div>

            <div class="charts-row">
                <div class="chart-container">
                    <div class="chart-title">KDJ指标</div>
                    <div id="chart-kdj" class="chart"></div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">成交量</div>
                    <div id="chart-volume" class="chart"></div>
                </div>
            </div>

            <!-- 消息面分析 -->
            {news_html}
        </div>

        <div class="footer">
            本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。
        </div>
    </div>

    <script>
        // 图表数据
        const chartData = {self._dict_to_json(chart_data)};

        // K线图
        const klineChart = echarts.init(document.getElementById('chart-kline'));
        klineChart.setOption({{
            tooltip: {{ trigger: 'axis' }},
            legend: {{ data: ['收盘价', 'MA5', 'MA10', 'MA20', 'MA60', '布林上轨', '布林下轨'], top: 5 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true }},
            xAxis: {{ type: 'category', data: chartData.dates, axisLabel: {{ rotate: 45 }} }},
            yAxis: {{ type: 'value', scale: true }},
            series: [
                {{ name: '收盘价', type: 'line', data: chartData.close, lineStyle: {{ width: 2 }} }},
                {{ name: 'MA5', type: 'line', data: chartData.ma5, lineStyle: {{ width: 1 }}, smooth: true }},
                {{ name: 'MA10', type: 'line', data: chartData.ma10, lineStyle: {{ width: 1 }}, smooth: true }},
                {{ name: 'MA20', type: 'line', data: chartData.ma20, lineStyle: {{ width: 1 }}, smooth: true }},
                {{ name: 'MA60', type: 'line', data: chartData.ma60, lineStyle: {{ width: 1 }}, smooth: true }},
                {{ name: '布林上轨', type: 'line', data: chartData.boll_upper, lineStyle: {{ width: 1, type: 'dashed' }}, itemStyle: {{ opacity: 0.5 }} }},
                {{ name: '布林下轨', type: 'line', data: chartData.boll_lower, lineStyle: {{ width: 1, type: 'dashed' }}, itemStyle: {{ opacity: 0.5 }} }}
            ]
        }});

        // MACD图
        const macdChart = echarts.init(document.getElementById('chart-macd'));
        macdChart.setOption({{
            tooltip: {{ trigger: 'axis' }},
            legend: {{ data: ['MACD', 'Signal', 'Histogram'], top: 5 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true }},
            xAxis: {{ type: 'category', data: chartData.dates, axisLabel: {{ rotate: 45 }} }},
            yAxis: {{ type: 'value' }},
            series: [
                {{ name: 'MACD', type: 'line', data: chartData.macd, lineStyle: {{ width: 1 }} }},
                {{ name: 'Signal', type: 'line', data: chartData.macd_signal, lineStyle: {{ width: 1 }} }},
                {{ name: 'Histogram', type: 'bar', data: chartData.macd_hist.map(v => ({{
                    value: v,
                    itemStyle: {{ color: v >= 0 ? '#DC143C' : '#228B22' }}
                }})) }}
            ]
        }});

        // RSI图
        const rsiChart = echarts.init(document.getElementById('chart-rsi'));
        rsiChart.setOption({{
            tooltip: {{ trigger: 'axis' }},
            legend: {{ data: ['RSI'], top: 5 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true }},
            xAxis: {{ type: 'category', data: chartData.dates, axisLabel: {{ rotate: 45 }} }},
            yAxis: {{ type: 'value', min: 0, max: 100 }},
            series: [
                {{ name: 'RSI', type: 'line', data: chartData.rsi, lineStyle: {{ width: 2, color: '#9c27b0' }} }},
                {{ name: '超买线', type: 'line', data: Array(chartData.dates.length).fill(70), lineStyle: {{ type: 'dashed', color: '#228B22' }}, symbol: 'none' }},
                {{ name: '超卖线', type: 'line', data: Array(chartData.dates.length).fill(30), lineStyle: {{ type: 'dashed', color: '#DC143C' }}, symbol: 'none' }}
            ]
        }});

        // KDJ图
        const kdjChart = echarts.init(document.getElementById('chart-kdj'));
        kdjChart.setOption({{
            tooltip: {{ trigger: 'axis' }},
            legend: {{ data: ['K', 'D', 'J'], top: 5 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true }},
            xAxis: {{ type: 'category', data: chartData.dates, axisLabel: {{ rotate: 45 }} }},
            yAxis: {{ type: 'value' }},
            series: [
                {{ name: 'K', type: 'line', data: chartData.kdj_k, lineStyle: {{ width: 1 }} }},
                {{ name: 'D', type: 'line', data: chartData.kdj_d, lineStyle: {{ width: 1 }} }},
                {{ name: 'J', type: 'line', data: chartData.kdj_j, lineStyle: {{ width: 1 }} }}
            ]
        }});

        // 成交量图
        const volumeChart = echarts.init(document.getElementById('chart-volume'));
        volumeChart.setOption({{
            tooltip: {{ trigger: 'axis' }},
            legend: {{ data: ['成交量'], top: 5 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true }},
            xAxis: {{ type: 'category', data: chartData.dates, axisLabel: {{ rotate: 45 }} }},
            yAxis: {{ type: 'value' }},
            series: [
                {{ name: '成交量', type: 'bar', data: chartData.volume.map((v, i) => ({{
                    value: v,
                    itemStyle: {{ color: chartData.volume_colors[i] }}
                }})) }}
            ]
        }});

        // 响应式
        window.addEventListener('resize', function() {{
            klineChart.resize();
            macdChart.resize();
            rsiChart.resize();
            kdjChart.resize();
            volumeChart.resize();
        }});
    </script>
</body>
</html>
        """

        return html

    def _dict_to_json(self, data):
        """将字典转换为JSON字符串"""
        import json
        return json.dumps(data, ensure_ascii=False)

    def save_html_report(self, stock_code: str, stock_name: str,
                         start_date: str, end_date: str,
                         output_path: str,
                         include_news: bool = True) -> bool:
        """
        生成并保存HTML报告
        """
        html = self.generate_html_report(stock_code, stock_name, start_date, end_date, include_news)

        if not html:
            return False

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"HTML报告已保存: {output_path}")
            return True
        except Exception as e:
            logger.error(f"保存HTML报告失败: {e}")
            return False


if __name__ == '__main__':
    # 测试
    generator = HTMLReportGenerator()
    generator.save_html_report(
        '300308', '中际旭创',
        '2024-06-01', '2024-12-31',
        'report.html'
    )
