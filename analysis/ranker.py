"""
股票排名模块
A股短线+中线实战六维度评分：技术面/量能/风险/消息面/市场情绪/全球板块联动
总分0-100，50为中性临界值
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from loguru import logger

from analysis.analyzer import TechnicalAnalyzer, MarketAnalyzer, NewsAnalyzer
from data.data_source import DataSource

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


def _display_width(s: str) -> int:
    """计算字符串显示宽度（CJK字符算2列）"""
    return sum(2 if ord(c) > 0x7F else 1 for c in s)


def _pad_right(s: str, width: int) -> str:
    """右填充字符串到指定显示宽度"""
    current = _display_width(s)
    return s + ' ' * max(0, width - current)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class StockRanker:
    """股票买入价值排名器

    A股实战六维度评分，总分0-100，50为中性：
    1. 技术面(0-20)：趋势、均线、位置、支撑压力、主升浪判断
    2. 量能(0-20)：放量健康度、资金流入、换手率合理性
    3. 风险(0-20)：估值透支、涨幅透支、筹码结构、波动级别
    4. 消息面(0-15)：业绩预告、行业催化、订单、政策
    5. 市场情绪(0-15)：板块强弱、资金偏好、连板效应
    6. 全球/板块联动(0-10)：美股映射、行业周期、海外涨价
    """

    def __init__(self):
        self.tech_analyzer = TechnicalAnalyzer()
        self.market_analyzer = MarketAnalyzer()
        self.news_analyzer = NewsAnalyzer()
        self.data_source = DataSource(use_tdx=False)

        # 缓存市场级数据（所有股票共享，只获取一次）
        self._market_overview = None
        self._global_market = None
        self._sector_data = None
        # 股票→板块映射缓存 {code: (sector_name, pct_change)}
        self._stock_sector_map = None

    def rank_stocks(self, stock_list: Dict[str, str],
                    start_date: str, end_date: str) -> List[Dict]:
        """批量分析股票并按买入价值排名"""
        self._preload_market_data()

        results = []
        for name, code in stock_list.items():
            try:
                logger.info(f"分析 {name} ({code})...")
                result = self._analyze_single(name, code, start_date, end_date)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"分析 {name} ({code}) 失败: {e}")

        results.sort(key=lambda x: x['buy_worthiness'], reverse=True)
        return results

    def _preload_market_data(self):
        """预加载市场级共享数据"""
        try:
            self._market_overview = self.market_analyzer.analyze_market_overview()
        except Exception as e:
            logger.warning(f"预加载市场概览失败: {e}")
            self._market_overview = {}

        try:
            self._global_market = self._fetch_global_market()
        except Exception as e:
            logger.warning(f"预加载全球市场数据失败: {e}")
            self._global_market = {}

        try:
            self._sector_data = self.data_source.get_sector_data()
        except Exception as e:
            logger.warning(f"预加载板块数据失败: {e}")
            self._sector_data = pd.DataFrame()

    # ==================== 核心分析 ====================

    def _analyze_single(self, name: str, code: str,
                        start_date: str, end_date: str) -> Optional[Dict]:
        """分析单只股票"""
        analysis = self.tech_analyzer.analyze_stock(code, start_date, end_date)
        if not analysis:
            return None

        vol_analysis = self.market_analyzer.analyze_today_volume(code)
        news_analysis = self._analyze_news(code)

        # 六维度评分（各自独立满分）
        s_tech = self._score_technical(analysis)
        s_vol = self._score_volume(analysis, vol_analysis)
        s_risk = self._score_risk(analysis)
        s_news = self._score_news(news_analysis)
        s_market = self._score_market_sentiment(code)
        s_global = self._score_global_and_sector(code)

        # 总分直接相加，满分100
        buy_worthiness = s_tech + s_vol + s_risk + s_news + s_market + s_global

        # 建议等级
        recommendation = self._get_recommendation(buy_worthiness)

        # 状态标签
        news_status = news_analysis.get('sentiment', '中性') if news_analysis else '无数据'
        market_status = self._market_overview.get('sentiment', '未知') if self._market_overview else '未知'
        global_status = self._global_market.get('status', '未知') if self._global_market else '未知'
        sector_status = self._get_sector_status(code)

        return {
            'name': name,
            'code': code,
            'price': analysis['latest_price'],
            'price_change': analysis['price_change'],
            'buy_worthiness': round(buy_worthiness, 1),
            'recommendation': recommendation,
            # 技术面细节
            'ma_trend': analysis['ma']['trend'],
            'macd_trend': analysis['macd']['trend'],
            'rsi_status': analysis['rsi']['status'],
            'rsi_value': analysis['rsi']['value'],
            'volume_status': analysis['volume']['status'],
            'volatility': analysis['volatility'],
            'bollinger_status': analysis['bollinger']['status'],
            'kdj_status': analysis['kdj']['status'],
            # 各维度得分
            'dim_tech': round(s_tech, 1),
            'dim_volume': round(s_vol, 1),
            'dim_risk': round(s_risk, 1),
            'dim_news': round(s_news, 1),
            'dim_market': round(s_market, 1),
            'dim_global_sector': round(s_global, 1),
            # 状态标签
            'news_status': news_status,
            'market_sentiment': market_status,
            'global_status': global_status,
            'sector_status': sector_status,
        }

    # ==================== 1. 技术面 (0-20) ====================

    def _score_technical(self, analysis: Dict) -> float:
        """
        技术面评分 0-20
        趋势方向(0-6) + 均线排列(0-5) + 位置(0-4) + 支撑压力(0-3) + 主升浪(0-2)
        """
        score = 0.0
        ma_trend = analysis['ma']['trend']
        macd_trend = analysis['macd']['trend']
        rsi_val = analysis['rsi']['value']
        kdj_status = analysis['kdj']['status']
        boll_pos = analysis['bollinger']['position']
        boll_status = analysis['bollinger']['status']

        # (1) 趋势方向 0-6：多头趋势+MACD共振最高
        if ma_trend == '多头' and macd_trend == '多头':
            score += 6  # 趋势+MACD共振
        elif ma_trend == '多头':
            score += 4
        elif ma_trend == '震荡' and macd_trend == '多头':
            score += 3  # 震荡中MACD转多
        elif ma_trend == '震荡':
            score += 2
        elif ma_trend == '空头' and macd_trend == '多头':
            score += 1  # 空头但MACD底背离可能
        # 空头+MACD空头 = 0

        # (2) 均线排列 0-5：多头排列加分，空头排列扣分
        if ma_trend == '多头':
            score += 5
        elif ma_trend == '震荡':
            score += 2.5
        # 空头 = 0

        # (3) 位置 0-4：布林带中轨附近最佳，超买/超卖扣分
        if 0.3 <= boll_pos <= 0.7:
            score += 4  # 中轨附近，有空间
        elif 0.2 <= boll_pos <= 0.8:
            score += 3
        elif boll_pos < 0.2:
            # 超卖区可能反弹
            if kdj_status == '超卖' or rsi_val < 30:
                score += 2  # 超卖+指标共振，反弹可能
            else:
                score += 1
        else:  # boll_pos > 0.8
            if kdj_status == '超买' or rsi_val > 70:
                score += 0  # 超买区+指标确认，透支
            else:
                score += 1

        # (4) 支撑压力 0-3：RSI适中最佳
        if 40 <= rsi_val <= 60:
            score += 3  # RSI中性，无压力
        elif 30 <= rsi_val <= 70:
            score += 2
        elif 20 <= rsi_val < 30:
            score += 1.5  # 超卖区有支撑
        elif rsi_val > 70:
            score += 0.5  # 超买区有压力
        else:
            score += 0

        # (5) 主升浪判断 0-2：均线多头+放量+KDJ非超买
        vol_status = analysis['volume']['status']
        if ma_trend == '多头' and vol_status in ('放量', '巨量') and kdj_status != '超买':
            score += 2
        elif ma_trend == '多头' and vol_status not in ('缩量', '地量'):
            score += 1

        return _clamp(score, 0, 20)

    # ==================== 2. 量能 (0-20) ====================

    def _score_volume(self, analysis: Dict, vol_analysis: Dict) -> float:
        """
        量能评分 0-20
        放量健康度(0-8) + 资金流入(0-7) + 换手率合理性(0-5)
        """
        score = 0.0
        vol_status = analysis['volume']['status']
        rsi_val = analysis['rsi']['value']

        # (1) 放量健康度 0-8
        pv_ok = False
        if vol_analysis and 'price_volume_status' in vol_analysis:
            pv = vol_analysis['price_volume_status']
            if '价涨量增' in pv:
                pv_ok = True

        if vol_status == '放量' and pv_ok:
            score += 8  # 放量+价涨量增，最健康
        elif vol_status == '放量':
            score += 5  # 放量但价量不配合
        elif vol_status == '温和放量' and pv_ok:
            score += 7
        elif vol_status == '温和放量':
            score += 4
        elif vol_status == '巨量' and pv_ok:
            score += 6  # 巨量价涨，短期可能过热
        elif vol_status == '巨量':
            score += 3  # 巨量但价不涨，警惕
        elif vol_status == '正常':
            score += 4
        elif vol_status == '缩量' and rsi_val > 70:
            score += 1  # 高位缩量，可能见顶
        elif vol_status == '缩量' and rsi_val < 30:
            score += 3  # 低位缩量，可能见底
        elif vol_status == '缩量':
            score += 2
        elif vol_status == '地量' and rsi_val < 30:
            score += 3  # 地量见底
        else:
            score += 1

        # (2) 资金流入 0-7
        if vol_analysis and 'score' in vol_analysis and isinstance(vol_analysis.get('score'), (int, float)):
            raw = vol_analysis['score']
            # raw 范围约 -0.7 ~ +1.3
            norm = (raw + 0.7) / 2.0 * 7
            score += _clamp(norm, 0, 7)
        else:
            score += 3.5  # 无数据中性

        # (3) 换手率合理性 0-5（从vol_analysis取换手率）
        turnover = 0
        if vol_analysis and vol_analysis.get('turnover'):
            try:
                turnover = float(vol_analysis['turnover'])
            except (ValueError, TypeError):
                pass

        if turnover == 0:
            score += 2.5  # 无换手率数据，中性
        elif 2 <= turnover <= 8:
            score += 5  # 正常换手
        elif 8 < turnover <= 15:
            score += 3  # 换手偏高，可能短期过热
        elif turnover > 15:
            score += 1  # 极高换手，风险大
        elif 1 <= turnover < 2:
            score += 3  # 偏低
        else:
            score += 2  # 极低换手

        return _clamp(score, 0, 20)

    # ==================== 3. 风险 (0-20) ====================

    def _score_risk(self, analysis: Dict) -> float:
        """
        风险评分 0-20（反向：风险越低分越高）
        涨幅透支(0-8) + 筹码结构(0-7) + 波动级别(0-5)
        """
        score = 20.0  # 从满分开始扣

        rsi_val = analysis['rsi']['value']
        boll_pos = analysis['bollinger']['position']
        kdj_status = analysis['kdj']['status']
        volatility = analysis.get('volatility', 0)
        price_change = abs(analysis['price_change'])

        # (1) 涨幅透支 0-8（扣分项）
        if rsi_val > 80:
            score -= 8  # 严重超买
        elif rsi_val > 70:
            score -= 5  # 超买
        elif rsi_val > 65:
            score -= 3
        elif rsi_val < 20:
            score -= 2  # 极度超卖也有风险
        elif rsi_val < 30:
            score -= 1

        # 区间涨幅透支
        if price_change > 0.3:
            score -= 3  # 区间涨幅>30%
        elif price_change > 0.2:
            score -= 1.5

        # 布林带极端位置
        if boll_pos > 0.95:
            score -= 3
        elif boll_pos > 0.85:
            score -= 1.5

        # (2) 筹码结构 0-7（扣分项）
        if kdj_status == '超买':
            score -= 4  # KDJ超买，筹码可能松动
        elif kdj_status == '超卖':
            score -= 1  # 超卖虽有机会但筹码不稳

        # 布林带下轨附近筹码密集区
        if boll_pos < 0.1:
            score -= 3  # 临近下轨破位风险
        elif boll_pos < 0.2:
            score -= 1

        # (3) 波动级别 0-5（扣分项）
        if volatility > 0.05:
            score -= 5  # 日均波动>5%，极高风险
        elif volatility > 0.04:
            score -= 4
        elif volatility > 0.03:
            score -= 2.5
        elif volatility > 0.02:
            score -= 1

        return _clamp(score, 0, 20)

    # ==================== 4. 消息面 (0-15) ====================

    def _score_news(self, news_analysis: Optional[Dict]) -> float:
        """
        消息面评分 0-15
        业绩/行业催化(0-7) + 资金流向(0-5) + 政策/订单(0-3)
        """
        if not news_analysis:
            return 7.5  # 无数据中性

        score = 0.0

        # (1) 新闻情绪 0-7
        news_info = news_analysis.get('news', {})
        news_score = news_info.get('score', 0) if isinstance(news_info, dict) else 0
        # news_score 范围约 -1 ~ +1
        s = (news_score + 1) / 2.0 * 7
        score += _clamp(s, 0, 7)

        # (2) 资金流向 0-5
        flow_info = news_analysis.get('flow', {})
        if isinstance(flow_info, dict):
            flow_score = flow_info.get('score', 0)
            if isinstance(flow_score, (int, float)):
                # flow_score 范围约 -0.6 ~ +0.8
                s = (flow_score + 0.6) / 1.4 * 5
                score += _clamp(s, 0, 5)
            else:
                score += 2.5
        else:
            score += 2.5

        # (3) 综合情绪评级 0-3
        sentiment = news_analysis.get('sentiment', '中性')
        if sentiment == '积极':
            score += 3
        elif sentiment == '偏积极':
            score += 2
        elif sentiment == '中性':
            score += 1.5
        elif sentiment == '偏消极':
            score += 0.5
        # 消极 = 0

        return _clamp(score, 0, 15)

    # ==================== 5. 市场情绪 (0-15) ====================

    def _score_market_sentiment(self, stock_code: str) -> float:
        """
        市场情绪评分 0-15
        板块强弱(0-6) + 资金偏好(0-5) + 连板效应(0-4)
        """
        score = 0.0

        if not self._market_overview:
            return 7.5

        # (1) 板块强弱 0-6
        up_ratio = self._market_overview.get('up_ratio', 0.5)
        if up_ratio > 0.75:
            score += 6  # 涨跌比>3:1，普涨
        elif up_ratio > 0.65:
            score += 5
        elif up_ratio > 0.55:
            score += 4
        elif up_ratio > 0.45:
            score += 3
        elif up_ratio > 0.35:
            score += 2
        elif up_ratio > 0.25:
            score += 1
        # <0.25 = 0

        # (2) 资金偏好 0-5（涨跌停比反映资金进攻性）
        limit_up = self._market_overview.get('limit_up', 0)
        limit_down = self._market_overview.get('limit_down', 0)

        if limit_up > 100:
            score += 5  # 百股涨停，极度活跃
        elif limit_up > 60:
            score += 4
        elif limit_up > 30:
            score += 3
        elif limit_up > 10:
            score += 2
        elif limit_up > 0:
            score += 1

        if limit_down > 50:
            score -= 3  # 大量跌停，恐慌
        elif limit_down > 20:
            score -= 1.5

        # (3) 连板效应 0-4（大盘指数涨跌反映市场做多情绪）
        indices_data = self._market_overview.get('indices', {})
        if indices_data:
            total_pct = 0
            count = 0
            for code, data in indices_data.items():
                pct = data.get('pct_change', 0)
                if isinstance(pct, str):
                    try:
                        pct = float(pct.replace('%', ''))
                    except ValueError:
                        pct = 0
                total_pct += pct
                count += 1
            if count > 0:
                avg_pct = total_pct / count
                if avg_pct > 1.5:
                    score += 4
                elif avg_pct > 0.8:
                    score += 3
                elif avg_pct > 0.3:
                    score += 2
                elif avg_pct > -0.3:
                    score += 1
                elif avg_pct > -0.8:
                    score += 0
                elif avg_pct > -1.5:
                    score -= 1
                else:
                    score -= 2
        else:
            score += 1.5  # 无指数数据中性

        return _clamp(score, 0, 15)

    # ==================== 6. 全球/板块联动 (0-10) ====================

    def _score_global_and_sector(self, stock_code: str) -> float:
        """
        全球/板块联动评分 0-10
        美股映射(0-4) + 行业周期(0-3) + 海外涨价/板块涨跌(0-3)
        """
        score = 0.0

        # (1) 美股映射 0-4
        global_score = self._global_market.get('score', 50) if self._global_market else 50
        # global_score 0-100, 50为中性
        s = (global_score / 100) * 4
        score += _clamp(s, 0, 4)

        # (2) 行业周期 0-3（板块涨跌趋势反映行业周期）
        sector_pct = self._get_sector_performance(stock_code)
        if sector_pct is not None:
            if sector_pct > 3:
                score += 3  # 板块强势上涨，行业景气
            elif sector_pct > 1:
                score += 2.5
            elif sector_pct > 0:
                score += 1.5
            elif sector_pct > -1:
                score += 1
            elif sector_pct > -3:
                score += 0.5
            # < -3 = 0
        else:
            score += 1.5  # 无数据中性

        # (3) 海外涨价/板块当日强度 0-3
        if sector_pct is not None:
            if sector_pct > 2:
                score += 3
            elif sector_pct > 1:
                score += 2
            elif sector_pct > 0:
                score += 1.5
            elif sector_pct > -1:
                score += 1
            elif sector_pct > -2:
                score += 0.5
            # < -2 = 0
        else:
            score += 1

        return _clamp(score, 0, 10)

    # ==================== 建议等级 ====================

    def _get_recommendation(self, score: float) -> str:
        """根据总分给出建议等级，50为中性"""
        if score >= 80:
            return '强烈买入'
        elif score >= 65:
            return '买入'
        elif score >= 50:
            return '谨慎买入'
        elif score >= 35:
            return '持有观望'
        elif score >= 20:
            return '减仓'
        else:
            return '卖出'

    # ==================== 消息面分析 ====================

    def _analyze_news(self, stock_code: str) -> Optional[Dict]:
        """分析消息面（新闻情绪 + 资金流向）"""
        try:
            return self.news_analyzer.analyze_comprehensive(stock_code)
        except Exception as e:
            logger.warning(f"消息面分析失败 {stock_code}: {e}")
            return None

    # ==================== 全球市场 ====================

    def _fetch_global_market(self) -> Dict:
        """获取全球主要市场数据"""
        result = {
            'markets': {},
            'status': '未知',
            'score': 50,
        }

        positive = 0
        negative = 0
        total = 0

        # 方法1: 获取恒生指数
        try:
            df = ak.stock_hk_index_daily_sina(symbol="HSI")
            if df is not None and not df.empty and len(df) >= 2:
                latest = df.iloc[-1]['close']
                prev = df.iloc[-2]['close']
                pct = (latest - prev) / prev * 100
                result['markets']['恒生指数'] = {'pct_change': pct}
                if pct > 0:
                    positive += 1
                else:
                    negative += 1
                total += 1
        except Exception:
            pass

        # 方法2: 东方财富全球重要指数
        if total == 0:
            try:
                df = ak.stock_zh_index_spot_em(symbol="全球重要指数")
                if df is not None and not df.empty:
                    for _, row in df.head(10).iterrows():
                        idx_name = row.get('名称', '')
                        pct = row.get('涨跌幅', 0)
                        if isinstance(pct, str):
                            try:
                                pct = float(pct.replace('%', ''))
                            except ValueError:
                                pct = 0
                        if any(kw in idx_name for kw in ['道琼斯', '纳斯达克', '标普', '恒生', '日经', '德国', '英国']):
                            result['markets'][idx_name] = {'pct_change': pct}
                            if pct > 0:
                                positive += 1
                            else:
                                negative += 1
                            total += 1
            except Exception:
                pass

        if total > 0:
            if positive > negative * 2:
                result['status'] = '全球普涨'
                result['score'] = 90
            elif positive > negative:
                result['status'] = '偏强'
                result['score'] = 70
            elif positive == negative:
                result['status'] = '分化'
                result['score'] = 50
            elif negative > positive * 2:
                result['status'] = '全球普跌'
                result['score'] = 15
            else:
                result['status'] = '偏弱'
                result['score'] = 30
        else:
            result['status'] = '无数据'
            result['score'] = 50

        return result

    # ==================== 板块映射 ====================

    def _get_sector_performance(self, stock_code: str) -> Optional[float]:
        """获取股票所属板块的涨跌幅（使用缓存）"""
        if self._stock_sector_map is None:
            self._build_stock_sector_map()

        info = self._stock_sector_map.get(stock_code)
        if info:
            return info[1]

        try:
            if self._sector_data is not None and not self._sector_data.empty and 'pct_change' in self._sector_data.columns:
                pcts = pd.to_numeric(self._sector_data['pct_change'], errors='coerce').dropna()
                if not pcts.empty:
                    return float(pcts.median())
        except Exception:
            pass

        return None

    def _build_stock_sector_map(self):
        """批量构建股票→板块映射"""
        self._stock_sector_map = {}

        if not AKSHARE_AVAILABLE:
            self._fill_sector_from_config()
            return

        sector_pct_map = {}
        for fetch_fn in [ak.stock_board_industry_name_em, ak.stock_board_concept_name_em]:
            try:
                df = fetch_fn()
                if df is None or df.empty:
                    continue
                name_col = '板块名称' if '板块名称' in df.columns else 'name'
                pct_col = '涨跌幅' if '涨跌幅' in df.columns else 'pct_change'
                if name_col in df.columns and pct_col in df.columns:
                    for _, row in df.iterrows():
                        sname = str(row[name_col])
                        pct = row[pct_col]
                        if isinstance(pct, str):
                            try:
                                pct = float(pct.replace('%', ''))
                            except (ValueError, AttributeError):
                                pct = 0
                        sector_pct_map[sname] = float(pct) if isinstance(pct, (int, float)) else 0
            except Exception:
                continue

        # 查找目标板块成分股
        target_sectors = []
        for sname in sector_pct_map:
            if any(kw in sname for kw in ['PCB', '印制电路', '电路板', '存储', '内存',
                                           'CPO', '光模块', '光电共封装', '光通信']):
                target_sectors.append(sname)

        for sname in target_sectors:
            try:
                cons_df = ak.stock_board_industry_cons_em(symbol=sname)
                if cons_df is None or cons_df.empty:
                    cons_df = ak.stock_board_concept_cons_em(symbol=sname)
                if cons_df is not None and not cons_df.empty:
                    code_col = '代码' if '代码' in cons_df.columns else 'code'
                    for _, row in cons_df.iterrows():
                        code = str(row.get(code_col, ''))
                        if code and code not in self._stock_sector_map:
                            self._stock_sector_map[code] = (sname, sector_pct_map.get(sname, 0))
            except Exception:
                continue

        # 从config补充未命中的
        self._fill_sector_from_config(sector_pct_map)
        logger.info(f"板块映射缓存完成: {len(self._stock_sector_map)} 只股票")

    def _fill_sector_from_config(self, sector_pct_map: Dict = None):
        """从config的SECTOR_STOCKS补充板块映射"""
        try:
            from config.config import SECTOR_STOCKS
            sector_keywords = {
                'PCB': ['PCB', '印制电路', '电路板'],
                '存储': ['存储', '内存', 'DRAM'],
                'CPO': ['CPO', '光模块', '光通信'],
            }
            for sector_name, stocks in SECTOR_STOCKS.items():
                matched_pct = 0
                if sector_pct_map:
                    for sname, pct in sector_pct_map.items():
                        if sector_name in sname or sname in sector_name:
                            matched_pct = pct
                            break
                    if matched_pct == 0:
                        for kw in sector_keywords.get(sector_name, []):
                            for sname, pct in sector_pct_map.items():
                                if kw in sname:
                                    matched_pct = pct
                                    break
                            if matched_pct != 0:
                                break
                for sname, code in stocks.items():
                    if code not in self._stock_sector_map:
                        self._stock_sector_map[code] = (sector_name, matched_pct)
        except Exception as e:
            logger.debug(f"从SECTOR_STOCKS推断板块失败: {e}")

    def _get_sector_status(self, stock_code: str) -> str:
        """获取板块状态标签"""
        pct = self._get_sector_performance(stock_code)
        if pct is None:
            return '无数据'
        if pct > 2:
            return '强势'
        elif pct > 0.5:
            return '偏强'
        elif pct > -0.5:
            return '中性'
        elif pct > -2:
            return '偏弱'
        else:
            return '弱势'

    # ==================== 格式化输出 ====================

    def format_ranking_table(self, ranked_results: List[Dict],
                             top_n: int = None) -> str:
        """生成对齐的文本排名表格"""
        if not ranked_results:
            return "无排名数据"

        display = ranked_results[:top_n] if top_n else ranked_results

        lines = []
        lines.append("=" * 120)
        lines.append("股票买入价值排名（六维度综合评分）")
        lines.append("=" * 120)

        headers = ['排名', '股票名称', '代码', '最新价', '涨跌幅',
                   '买入值', '建议', '技术', '量能', '风险',
                   '消息面', '市场', '全球/板块']
        col_widths = [4, 8, 8, 8, 8, 7, 8, 4, 4, 4, 6, 4, 8]

        header_line = ''
        for h, w in zip(headers, col_widths):
            header_line += _pad_right(h, w) + ' '
        lines.append(header_line)
        lines.append("-" * 120)

        for i, r in enumerate(display, 1):
            change_str = f"{r['price_change']*100:+.2f}%"
            row = [
                str(i),
                r['name'],
                r['code'],
                f"{r['price']:.2f}",
                change_str,
                f"{r['buy_worthiness']:.1f}",
                r['recommendation'],
                f"{r['dim_tech']:.0f}",
                f"{r['dim_volume']:.0f}",
                f"{r['dim_risk']:.0f}",
                r['news_status'],
                r['market_sentiment'],
                r['global_status'] + '/' + r['sector_status'],
            ]

            row_line = ''
            for val, w in zip(row, col_widths):
                row_line += _pad_right(str(val), w) + ' '
            lines.append(row_line)

        lines.append("=" * 120)
        lines.append("")
        lines.append("评分说明: 总分0-100，50为中性临界值")
        lines.append("  技术面(0-20): 趋势+均线排列+位置+支撑压力+主升浪")
        lines.append("  量能(0-20): 放量健康度+资金流入+换手率合理性")
        lines.append("  风险(0-20): 涨幅透支+筹码结构+波动级别 (风险越低分越高)")
        lines.append("  消息面(0-15): 业绩/行业催化+资金流向+政策/订单")
        lines.append("  市场情绪(0-15): 板块强弱+资金偏好+连板效应")
        lines.append("  全球/板块联动(0-10): 美股映射+行业周期+海外涨价")

        return "\n".join(lines)
