"""
数据获取模块
支持：AKShare免费数据 + 同花顺/通达信API
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from loguru import logger
import requests
import json

try:
    from pytdx.hq import TdxHq_API
    TDX_AVAILABLE = True
except ImportError:
    TDX_AVAILABLE = False
    logger.warning("pytdx未安装，通达信API不可用，将使用AKShare")


class DataSource:
    """统一数据源接口"""

    def __init__(self, use_tdx: bool = True):
        self.use_tdx = use_tdx and TDX_AVAILABLE
        self.tdx_api = None
        if self.use_tdx:
            self._init_tdx()

    def _init_tdx(self):
        """初始化通达信连接"""
        try:
            from config.config import THS_API_CONFIG
            self.tdx_api = TdxHq_API()
            # 连接通达信服务器
            self.tdx_api.connect(
                THS_API_CONFIG['host'],
                THS_API_CONFIG['port']
            )
            logger.info("通达信API连接成功")
        except Exception as e:
            logger.error(f"通达信API连接失败: {e}")
            self.use_tdx = False

    def get_stock_code_info(self, stock_code: str) -> Dict:
        """
        获取股票市场代码信息
        返回: {'code': '300308', 'market': 0}  # 0=深圳, 1=上海
        """
        if stock_code.startswith('6'):
            return {'code': stock_code, 'market': 1}  # 上海
        else:
            return {'code': stock_code, 'market': 0}  # 深圳

    # ==================== 行情数据 ====================

    def get_daily_kline(self, stock_code: str, start_date: str,
                        end_date: str) -> pd.DataFrame:
        """
        获取日K线数据
        :param stock_code: 股票代码
        :param start_date: 开始日期 YYYY-MM-DD
        :param end_date: 结束日期 YYYY-MM-DD
        :return: DataFrame with columns: date, open, high, low, close, volume, amount
        """
        try:
            if self.use_tdx:
                return self._get_daily_tdx(stock_code, start_date, end_date)
            else:
                return self._get_daily_akshare(stock_code, start_date, end_date)
        except Exception as e:
            logger.error(f"获取K线数据失败 {stock_code}: {e}")
            return pd.DataFrame()

    def _get_daily_akshare(self, stock_code: str, start_date: str,
                          end_date: str) -> pd.DataFrame:
        """使用AKShare获取日K线（多数据源备用）"""

        # 方法1: 东方财富数据源（最常用）
        try:
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 前复权
            )
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '收盘': 'close',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '振幅': 'amplitude',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '换手率': 'turnover'
                })
                df['date'] = pd.to_datetime(df['date'])
                logger.debug("数据源: 东方财富(hist)")
                return df
        except Exception as e:
            logger.warning(f"[备用1]东方财富源失败: {e}")

        # 方法2: 东方财富分钟数据聚合（备用）
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=stock_code, period='daily', adjust='qfq')
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '时间': 'date',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '收盘': 'close',
                    '成交量': 'volume',
                    '成交额': 'amount'
                })
                df['date'] = pd.to_datetime(df['date'])
                # 过滤日期
                start = pd.to_datetime(start_date)
                end = pd.to_datetime(end_date)
                df = df[(df['date'] >= start) & (df['date'] <= end)]
                if not df.empty:
                    logger.debug("数据源: 东方财富(min_em)")
                    return df
        except Exception as e:
            logger.warning(f"[备用2]东方财富min源失败: {e}")

        # 方法3: 新浪数据源
        try:
            market = 'sh' if stock_code.startswith('6') else 'sz'
            df = ak.stock_zh_a_daily(symbol=f"{market}{stock_code}",
                                     start_date=start_date, end_date=end_date, adjust="qfq")
            if df is not None and not df.empty:
                df = df.rename(columns={
                    'date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                logger.debug("数据源: 新浪")
                return df
        except Exception as e:
            logger.warning(f"[备用3]新浪源失败: {e}")

        # 方法4: 腾讯数据源
        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=stock_code,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '收盘': 'close',
                    '成交量': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                logger.debug("数据源: 腾讯")
                return df
        except Exception as e:
            logger.warning(f"[备用4]腾讯源失败: {e}")

        # 方法5: 网易数据源
        try:
            df = ak.stock_zh_a_hist_163(
                symbol=stock_code,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '收盘': 'close',
                    '成交量': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                logger.debug("数据源: 网易")
                return df
        except Exception as e:
            logger.warning(f"[备用5]网易源失败: {e}")

        # 方法6: 同花顺数据源
        try:
            df = ak.stock_zh_a_hist_ths(
                symbol=stock_code,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df = df.rename(columns={
                    'date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                logger.debug("数据源: 同花顺")
                return df
        except Exception as e:
            logger.warning(f"[备用6]同花顺源失败: {e}")

        # 方法7: 东方财富另一个接口
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                # 只能获取当日数据，作为最后手段
                stock_data = df[df['代码'] == stock_code]
                if not stock_data.empty:
                    row = stock_data.iloc[0]
                    single_day_df = pd.DataFrame([{
                        'date': pd.Timestamp.now().normalize(),
                        'open': float(row.get('今开', 0)),
                        'high': float(row.get('最高', 0)),
                        'low': float(row.get('最低', 0)),
                        'close': float(row.get('最新价', 0)),
                        'volume': float(row.get('成交量', 0)),
                    }])
                    logger.debug("数据源: 东方财富(spot_em) - 仅当日")
                    return single_day_df
        except Exception as e:
            logger.warning(f"[备用7]东方财富spot源失败: {e}")

        # 方法8: 使用 yfinance（如果安装了）
        try:
            import yfinance as yf
            market = 'SS' if stock_code.startswith('6') else 'SZ'
            ticker = yf.Ticker(f"{stock_code}.{market}")
            df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
            if df is not None and not df.empty:
                df = df.reset_index()
                df = df.rename(columns={
                    'Date': 'date',
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close',
                    'Volume': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                logger.debug("数据源: Yahoo Finance")
                return df
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[备用8]Yahoo Finance源失败: {e}")

        logger.error(f"所有数据源({8}个)均获取失败")
        return pd.DataFrame()

    def _get_daily_tdx(self, stock_code: str, start_date: str,
                       end_date: str) -> pd.DataFrame:
        """使用通达信获取日K线"""
        if not self.tdx_api:
            return self._get_daily_akshare(stock_code, start_date, end_date)

        try:
            info = self.get_stock_code_info(stock_code)
            data = self.tdx_api.get_security_bars(
                9,  # 9=日K线
                info['market'],
                info['code'],
                0,  # 起始位置
                800  # 获取数量
            )

            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df = df.rename(columns={
                'datetime': 'date',
            })
            df['date'] = pd.to_datetime(df['date'])

            # 过滤日期范围
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            df = df[(df['date'] >= start) & (df['date'] <= end)]

            return df
        except Exception as e:
            logger.error(f"通达信获取数据失败: {e}")
            return self._get_daily_akshare(stock_code, start_date, end_date)

    def get_realtime_quote(self, stock_codes: List[str]) -> pd.DataFrame:
        """
        获取实时行情
        :param stock_codes: 股票代码列表
        :return: 实时行情DataFrame
        """
        try:
            if self.use_tdx:
                return self._get_realtime_tdx(stock_codes)
            else:
                return self._get_realtime_akshare(stock_codes)
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return pd.DataFrame()

    def _get_realtime_akshare(self, stock_codes: List[str]) -> pd.DataFrame:
        """使用AKShare获取实时行情（多数据源备用）"""

        # 方法1: 东方财富实时行情
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                df = df[df['代码'].isin(stock_codes)]
                df = df.rename(columns={
                    '代码': 'code',
                    '名称': 'name',
                    '最新价': 'price',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '最高': 'high',
                    '最低': 'low',
                    '今开': 'open',
                    '昨收': 'pre_close'
                })
                logger.debug("实时行情数据源: 东方财富(spot_em)")
                return df
        except Exception as e:
            logger.warning(f"[实时备用1]东方财富源失败: {e}")

        # 方法2: 新浪实时行情
        try:
            result_df = pd.DataFrame()
            for code in stock_codes:
                market = 'sh' if code.startswith('6') else 'sz'
                df = ak.stock_zh_a_spot_sina(symbol=market)
                if df is not None and not df.empty:
                    stock_df = df[df['代码'] == code]
                    result_df = pd.concat([result_df, stock_df], ignore_index=True)

            if not result_df.empty:
                result_df = result_df.rename(columns={
                    '代码': 'code',
                    '名称': 'name',
                    '最新价': 'price',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '最高': 'high',
                    '最低': 'low',
                    '今开': 'open',
                    '昨收': 'pre_close'
                })
                logger.debug("实时行情数据源: 新浪(sina)")
                return result_df
        except Exception as e:
            logger.warning(f"[实时备用2]新浪源失败: {e}")

        # 方法3: 腾讯实时行情
        try:
            result_df = pd.DataFrame()
            for code in stock_codes:
                df = ak.stock_zh_a_hist_tx(symbol=code, start_date='', end_date='', adjust='')
                if df is not None and not df.empty:
                    latest = df.iloc[-1:].copy()
                    latest['code'] = code
                    result_df = pd.concat([result_df, latest], ignore_index=True)

            if not result_df.empty:
                result_df = result_df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '收盘': 'price',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume'
                })
                logger.debug("实时行情数据源: 腾讯(tx)")
                return result_df
        except Exception as e:
            logger.warning(f"[实时备用3]腾讯源失败: {e}")

        # 方法4: 网易实时行情
        try:
            result_df = pd.DataFrame()
            for code in stock_codes:
                df = ak.stock_zh_a_hist_163(symbol=code, start_date='', end_date='', adjust='')
                if df is not None and not df.empty:
                    latest = df.iloc[-1:].copy()
                    latest['code'] = code
                    result_df = pd.concat([result_df, latest], ignore_index=True)

            if not result_df.empty:
                result_df = result_df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '收盘': 'price',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume'
                })
                logger.debug("实时行情数据源: 网易(163)")
                return result_df
        except Exception as e:
            logger.warning(f"[实时备用4]网易源失败: {e}")

        # 方法5: Yahoo Finance（如果安装了）
        try:
            import yfinance as yf
            result_df = pd.DataFrame()
            for code in stock_codes:
                market = 'SS' if code.startswith('6') else 'SZ'
                ticker = yf.Ticker(f"{code}.{market}")
                info = ticker.info
                if info:
                    result_df = pd.concat([result_df, pd.DataFrame([{
                        'code': code,
                        'name': info.get('shortName', ''),
                        'price': info.get('currentPrice', 0),
                        'open': info.get('regularMarketOpen', 0),
                        'high': info.get('dayHigh', 0),
                        'low': info.get('dayLow', 0),
                        'volume': info.get('volume', 0),
                        'pre_close': info.get('previousClose', 0),
                    }])], ignore_index=True)

            if not result_df.empty:
                logger.debug("实时行情数据源: Yahoo Finance")
                return result_df
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[实时备用5]Yahoo Finance源失败: {e}")

        logger.error(f"所有实时行情数据源(5个)均获取失败")
        return pd.DataFrame()

    def _get_realtime_tdx(self, stock_codes: List[str]) -> pd.DataFrame:
        """使用通达信获取实时行情"""
        if not self.tdx_api:
            return self._get_realtime_akshare(stock_codes)

        try:
            stocks = [self.get_stock_code_info(code) for code in stock_codes]
            data = self.tdx_api.get_security_quotes(stocks)

            df = pd.DataFrame(data)
            df = df.rename(columns={
                'code': 'code',
                'price': 'price',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'vol': 'volume',
                'amount': 'amount'
            })
            return df
        except Exception as e:
            logger.error(f"通达信获取实时行情失败: {e}")
            return self._get_realtime_akshare(stock_codes)

    # ==================== 消息面数据 ====================

    def get_money_flow(self, stock_code: str, days: int = 10) -> pd.DataFrame:
        """
        获取资金流向数据
        :param stock_code: 股票代码
        :param days: 天数
        :return: 资金流向DataFrame
        """
        try:
            market = "sh" if stock_code.startswith('6') else "sz"
            df = ak.stock_individual_fund_flow(stock=stock_code, market=market)
            if df is not None and not df.empty:
                return df.head(days)
        except Exception as e:
            logger.warning(f"获取资金流向失败: {e}")

        # 备用方案
        try:
            df = ak.stock_fund_flow_individual(symbol=stock_code)
            if df is not None and not df.empty:
                return df.head(days)
        except Exception as e:
            logger.warning(f"备用资金流向接口失败: {e}")

        return pd.DataFrame()

    def get_news(self, stock_code: str, limit: int = 50) -> List[Dict]:
        """
        获取个股新闻
        :param stock_code: 股票代码
        :param limit: 获取数量
        :return: 新闻列表
        """
        try:
            # AKShare获取新闻
            df = ak.stock_news_em(symbol=stock_code)
            news_list = []
            for _, row in df.head(limit).iterrows():
                news_list.append({
                    'title': row.get('新闻标题', ''),
                    'content': row.get('新闻内容', ''),
                    'time': row.get('发布时间', ''),
                    'source': row.get('新闻来源', '')
                })
            return news_list
        except Exception as e:
            logger.error(f"获取新闻失败 {stock_code}: {e}")
            return []

    def get_announcements(self, stock_code: str) -> List[Dict]:
        """
        获取公司公告
        :param stock_code: 股票代码
        :return: 公告列表
        """
        try:
            df = ak.stock_notice_report(symbol=stock_code)
            announcements = []
            for _, row in df.iterrows():
                announcements.append({
                    'title': row.get('公告标题', ''),
                    'type': row.get('公告类型', ''),
                    'date': row.get('公告日期', ''),
                })
            return announcements
        except Exception as e:
            logger.error(f"获取公告失败 {stock_code}: {e}")
            return []

    # ==================== 基本面数据 ====================

    def get_financial_indicator(self, stock_code: str) -> pd.DataFrame:
        """
        获取财务指标
        :param stock_code: 股票代码
        :return: 财务指标DataFrame
        """
        try:
            df = ak.stock_financial_analysis_indicator(symbol=stock_code)
            return df
        except Exception as e:
            logger.error(f"获取财务指标失败 {stock_code}: {e}")
            return pd.DataFrame()

    def get_stock_info(self, stock_code: str) -> Dict:
        """
        获取股票基本信息
        :param stock_code: 股票代码
        :return: 股票信息字典
        """
        try:
            df = ak.stock_individual_info_em(symbol=stock_code)
            info = dict(zip(df['item'], df['value']))
            return info
        except Exception as e:
            logger.error(f"获取股票信息失败 {stock_code}: {e}")
            return {}

    # ==================== 市场数据 ====================

    def get_index_data(self, index_code: str = '000300',
                       start_date: str = None,
                       end_date: str = None) -> pd.DataFrame:
        """
        获取指数数据
        :param index_code: 指数代码，默认沪深300
        """
        try:
            if index_code in ['000001', '000300', '000016', '000905']:
                # 沪深指数
                df = ak.stock_zh_index_daily(symbol=f"sh{index_code}")
            else:
                df = ak.stock_zh_index_daily(symbol=f"sz{index_code}")

            df['date'] = pd.to_datetime(df['date'])
            if start_date and end_date:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
            return df
        except Exception as e:
            logger.error(f"获取指数数据失败: {e}")
            return pd.DataFrame()

    def close(self):
        """关闭连接"""
        if self.tdx_api:
            self.tdx_api.disconnect()
            logger.info("通达信API连接已关闭")


# 便捷函数
def get_data_source() -> DataSource:
    """获取数据源实例"""
    return DataSource()


if __name__ == '__main__':
    # 测试
    ds = DataSource(use_tdx=False)

    # 测试获取K线
    df = ds.get_daily_kline('300308', '2024-01-01', '2024-12-31')
    print(df.head())
    print(f"获取到 {len(df)} 条数据")

    # 测试获取新闻
    news = ds.get_news('300308', limit=5)
    print(f"获取到 {len(news)} 条新闻")
    for n in news[:3]:
        print(f"- {n['title']}")

    ds.close()
