"""
数据管理模块
包含：数据缓存、数据验证、数据持久化
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
import os
import json
import hashlib
import pickle
from pathlib import Path


class DataCache:
    """数据缓存管理器（支持LRU淘汰、内存上限、分类过期）"""

    # 缓存类型与默认过期时间（秒）
    CACHE_EXPIRE = {
        'kline': 4 * 3600,        # 日K线 4小时
        'realtime': 30,            # 实时行情 30秒
        'money_flow': 3600,        # 资金流向 1小时
        'news': 1800,              # 新闻 30分钟
        'default': 4 * 3600,       # 默认 4小时
    }

    def __init__(self, cache_dir: str = None, expire_hours: int = 4,
                 max_memory_items: int = 100, max_memory_size_mb: float = 500):
        """
        :param cache_dir: 缓存目录
        :param expire_hours: 缓存过期时间（小时），仅用于向后兼容
        :param max_memory_items: 内存缓存最大条目数
        :param max_memory_size_mb: 内存缓存最大占用(MB)
        """
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.quant_trading/cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.expire_hours = expire_hours
        self.max_memory_items = max_memory_items
        self.max_memory_size_mb = max_memory_size_mb
        self.memory_cache: Dict[str, Tuple[datetime, any]] = {}

    def _get_cache_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_str = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.pkl"

    def _get_expire_seconds(self, cache_type: str = None) -> float:
        """根据缓存类型获取过期秒数"""
        if cache_type and cache_type in self.CACHE_EXPIRE:
            return self.CACHE_EXPIRE[cache_type]
        return self.expire_hours * 3600

    def _estimate_size_mb(self, data) -> float:
        """估算数据占用内存(MB)"""
        try:
            import sys
            return sys.getsizeof(data) / 1024 / 1024
        except Exception:
            return 0

    def _evict_if_needed(self):
        """当内存缓存超过限制时淘汰最早的条目"""
        # 条目数超限
        if len(self.memory_cache) > self.max_memory_items:
            # 淘汰最早20%的条目
            sorted_keys = sorted(self.memory_cache.keys(),
                                 key=lambda k: self.memory_cache[k][0])
            evict_count = max(1, len(sorted_keys) // 5)
            for key in sorted_keys[:evict_count]:
                del self.memory_cache[key]
            logger.debug(f"内存缓存淘汰 {evict_count} 条(条目数超限)")

        # 内存占用超限
        total_size = sum(self._estimate_size_mb(v[1]) for v in self.memory_cache.values())
        if total_size > self.max_memory_size_mb:
            sorted_keys = sorted(self.memory_cache.keys(),
                                 key=lambda k: self.memory_cache[k][0])
            evict_count = max(1, len(sorted_keys) // 5)
            for key in sorted_keys[:evict_count]:
                del self.memory_cache[key]
            logger.debug(f"内存缓存淘汰 {evict_count} 条(内存超限)")

    def get(self, *args, cache_type: str = None, **kwargs) -> Optional[any]:
        """
        从缓存获取数据
        :param cache_type: 缓存类型(kline/realtime/money_flow/news)
        :return: 缓存数据，不存在或过期返回None
        """
        cache_key = self._get_cache_key(*args, **kwargs)
        expire_seconds = self._get_expire_seconds(cache_type)

        # 先检查内存缓存
        if cache_key in self.memory_cache:
            cache_time, data = self.memory_cache[cache_key]
            if (datetime.now() - cache_time).total_seconds() < expire_seconds:
                logger.debug(f"内存缓存命中: {cache_key[:8]}")
                return data
            else:
                del self.memory_cache[cache_key]

        # 检查文件缓存（仅非实时数据使用文件缓存）
        if cache_type != 'realtime':
            cache_path = self._get_cache_path(cache_key)
            if cache_path.exists():
                file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
                if (datetime.now() - file_time).total_seconds() < expire_seconds:
                    try:
                        with open(cache_path, 'rb') as f:
                            data = pickle.load(f)
                        # 同时缓存到内存
                        self.memory_cache[cache_key] = (datetime.now(), data)
                        logger.debug(f"文件缓存命中: {cache_key[:8]}")
                        return data
                    except Exception as e:
                        logger.warning(f"缓存读取失败: {e}")
                else:
                    # 删除过期缓存
                    cache_path.unlink()

        return None

    def set(self, data: any, *args, cache_type: str = None, **kwargs):
        """保存数据到缓存"""
        cache_key = self._get_cache_key(*args, **kwargs)

        # 保存到内存
        self.memory_cache[cache_key] = (datetime.now(), data)

        # 淘汰检查
        self._evict_if_needed()

        # 保存到文件（实时数据不写文件缓存）
        if cache_type != 'realtime':
            cache_path = self._get_cache_path(cache_key)
            try:
                with open(cache_path, 'wb') as f:
                    pickle.dump(data, f)
                logger.debug(f"数据已缓存: {cache_key[:8]}")
            except Exception as e:
                logger.warning(f"缓存写入失败: {e}")

    def clear_memory(self):
        """清空内存缓存"""
        self.memory_cache.clear()
        logger.info("内存缓存已清空")

    def clear_disk(self):
        """清空磁盘缓存"""
        for cache_file in self.cache_dir.glob("*.pkl"):
            cache_file.unlink()
        logger.info("磁盘缓存已清空")

    def clear_expired(self):
        """清理过期缓存（内存+磁盘）"""
        cleared = 0
        now = datetime.now()

        # 清理内存缓存
        expired_keys = []
        for key, (cache_time, _) in self.memory_cache.items():
            if (now - cache_time).total_seconds() > self.expire_hours * 3600:
                expired_keys.append(key)
        for key in expired_keys:
            del self.memory_cache[key]

        # 清理磁盘缓存
        for cache_file in self.cache_dir.glob("*.pkl"):
            file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if now - file_time >= timedelta(hours=self.expire_hours):
                cache_file.unlink()
                cleared += 1
        logger.info(f"清理过期缓存: 内存{len(expired_keys)}个, 磁盘{cleared}个")

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        memory_size = len(self.memory_cache)
        disk_size = len(list(self.cache_dir.glob("*.pkl")))
        disk_usage = sum(f.stat().st_size for f in self.cache_dir.glob("*.pkl"))

        return {
            'memory_cache_count': memory_size,
            'disk_cache_count': disk_size,
            'disk_usage_mb': disk_usage / 1024 / 1024
        }


class DataValidator:
    """数据验证器"""

    @staticmethod
    def validate_kline(df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        验证K线数据
        :return: (是否有效, 错误信息列表)
        """
        errors = []

        # 检查必要列
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            errors.append(f"缺少必要列: {missing_cols}")

        if errors:
            return False, errors

        # 检查数据量
        if len(df) < 10:
            errors.append(f"数据量不足: {len(df)} < 10")

        # 检查空值
        null_counts = df[required_columns].isnull().sum()
        for col, count in null_counts.items():
            if count > 0:
                errors.append(f"列 '{col}' 包含 {count} 个空值")

        # 检查价格合理性
        if (df['high'] < df['low']).any():
            errors.append("存在最高价 < 最低价的异常数据")

        if (df['close'] > df['high']).any() or (df['close'] < df['low']).any():
            errors.append("存在收盘价超出最高/最低价范围的异常数据")

        if (df['open'] > df['high']).any() or (df['open'] < df['low']).any():
            errors.append("存在开盘价超出最高/最低价范围的异常数据")

        # 检查价格为正
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if (df[col] <= 0).any():
                negative_count = (df[col] <= 0).sum()
                errors.append(f"列 '{col}' 包含 {negative_count} 个非正值")

        # 检查成交量为正
        if (df['volume'] < 0).any():
            errors.append("成交量包含负值")

        # 检查日期连续性（工作日）
        if 'date' in df.columns:
            df_sorted = df.sort_values('date')
            dates = pd.to_datetime(df_sorted['date'])
            date_diffs = dates.diff().dropna()

            # 允许周末和节假日，但不应该有超过7天的间隔
            max_gap = date_diffs.max()
            if max_gap > pd.Timedelta(days=7):
                errors.append(f"日期间隔过大: 最大间隔 {max_gap.days} 天")

        # 检查价格异常波动（单日涨跌超30%预警）
        if 'close' in df.columns:
            pct_change = df['close'].pct_change().abs()
            abnormal_days = (pct_change > 0.3).sum()
            if abnormal_days > 0:
                logger.warning(f"发现 {abnormal_days} 天异常波动(涨跌>30%)")

        return len(errors) == 0, errors

    @staticmethod
    def validate_realtime(df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """验证实时行情数据"""
        errors = []

        required_columns = ['code', 'price']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            errors.append(f"缺少必要列: {missing_cols}")

        if 'price' in df.columns and (df['price'] <= 0).any():
            errors.append("存在非正价格")

        return len(errors) == 0, errors

    @staticmethod
    def clean_kline(df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗K线数据（含异常值检测与自动修复）
        :return: 清洗后的DataFrame
        """
        df = df.copy()

        # 删除空值行
        df = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])

        # 删除异常价格行
        df = df[df['high'] >= df['low']]
        df = df[(df['close'] <= df['high']) & (df['close'] >= df['low'])]
        df = df[(df['open'] <= df['high']) & (df['open'] >= df['low'])]

        # 删除非正价格
        for col in ['open', 'high', 'low', 'close']:
            df = df[df[col] > 0]

        # 删除负成交量
        df = df[df['volume'] >= 0]

        # 去重
        df = df.drop_duplicates(subset=['date'], keep='last')

        # 排序
        df = df.sort_values('date').reset_index(drop=True)

        # 3σ异常值检测与修复
        for col in ['close', 'volume']:
            mean_val = df[col].mean()
            std_val = df[col].std()
            if std_val > 0:
                lower = mean_val - 3 * std_val
                upper = mean_val + 3 * std_val
                outlier_mask = (df[col] < lower) | (df[col] > upper)
                if outlier_mask.any():
                    # 用中位数替换异常值
                    median_val = df.loc[~outlier_mask, col].median()
                    df.loc[outlier_mask, col] = median_val
                    logger.info(f"列'{col}'修复{outlier_mask.sum()}个异常值(3σ)")

        # 修复close导致的high/low不一致
        df['high'] = df[['high', 'close', 'open']].max(axis=1)
        df['low'] = df[['low', 'close', 'open']].min(axis=1)

        logger.info(f"数据清洗: 原始{len(df)}行 -> 清洗后{len(df)}行")

        return df

    @staticmethod
    def detect_anomalies(df: pd.DataFrame, z_threshold: float = 3.0) -> Dict[str, List[int]]:
        """
        使用Z-score检测异常值
        :param df: K线数据
        :param z_threshold: Z-score阈值
        :return: {列名: [异常行索引]}
        """
        anomalies = {}
        for col in ['close', 'volume']:
            if col not in df.columns:
                continue
            mean_val = df[col].mean()
            std_val = df[col].std()
            if std_val > 0:
                z_scores = (df[col] - mean_val) / std_val
                outlier_idx = df.index[z_scores.abs() > z_threshold].tolist()
                if outlier_idx:
                    anomalies[col] = outlier_idx
        return anomalies

    @staticmethod
    def auto_repair(df: pd.DataFrame) -> pd.DataFrame:
        """
        自动修复缺失值和异常值
        - 缺失值：线性插值填充
        - 异常值(3σ外)：用相邻日中位数替换
        """
        df = df.copy()

        # 修复缺失值
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                missing = df[col].isna().sum()
                if missing > 0:
                    df[col] = df[col].interpolate(method='linear')
                    # 首尾缺失用bfill/ffill
                    df[col] = df[col].ffill().bfill()
                    logger.info(f"列'{col}'插值修复{missing}个缺失值")

        # 修复异常值
        for col in ['close', 'volume']:
            if col not in df.columns or len(df) < 5:
                continue
            mean_val = df[col].mean()
            std_val = df[col].std()
            if std_val > 0:
                outlier_mask = (df[col] - mean_val).abs() > 3 * std_val
                if outlier_mask.any():
                    # 用滚动中位数替换
                    rolling_median = df[col].rolling(window=5, center=True, min_periods=1).median()
                    df.loc[outlier_mask, col] = rolling_median[outlier_mask]
                    logger.info(f"列'{col}'异常值修复{outlier_mask.sum()}个")

        # 修复价格一致性
        if all(c in df.columns for c in ['open', 'high', 'low', 'close']):
            df['high'] = df[['high', 'close', 'open']].max(axis=1)
            df['low'] = df[['low', 'close', 'open']].min(axis=1)

        return df

    @staticmethod
    def fill_missing_dates(df: pd.DataFrame, fill_method: str = 'ffill') -> pd.DataFrame:
        """
        填充缺失日期（仅工作日）
        :param fill_method: 填充方法 (ffill, bfill, interpolate)
        """
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')

        # 生成完整工作日索引
        full_range = pd.bdate_range(start=df.index.min(), end=df.index.max())

        # 重新索引
        df = df.reindex(full_range)

        # 填充
        if fill_method == 'ffill':
            df = df.ffill()
        elif fill_method == 'bfill':
            df = df.bfill()
        elif fill_method == 'interpolate':
            df = df.interpolate()

        df = df.reset_index()
        df = df.rename(columns={'index': 'date'})

        return df


class DataManager:
    """数据管理器 - 统一管理数据获取、缓存、验证"""

    def __init__(self, cache_dir: str = None, use_cache: bool = True):
        self.use_cache = use_cache
        self.cache = DataCache(cache_dir) if use_cache else None
        self.validator = DataValidator()

    def get_kline(self,
                  data_source,
                  stock_code: str,
                  start_date: str,
                  end_date: str,
                  force_refresh: bool = False) -> pd.DataFrame:
        """
        获取K线数据（带缓存和验证）
        """
        # 尝试从缓存获取
        if self.use_cache and not force_refresh:
            cached = self.cache.get('kline', stock_code, start_date, end_date, cache_type='kline')
            if cached is not None:
                is_valid, errors = self.validator.validate_kline(cached)
                if is_valid:
                    return cached
                else:
                    logger.warning(f"缓存数据验证失败: {errors}")

        # 获取新数据
        df = data_source.get_daily_kline(stock_code, start_date, end_date)

        if df.empty:
            return df

        # 验证
        is_valid, errors = self.validator.validate_kline(df)
        if not is_valid:
            logger.warning(f"数据验证问题: {errors}")
            # 尝试自动修复
            df = self.validator.auto_repair(df)
            # 清洗数据
            df = self.validator.clean_kline(df)

        # 缓存
        if self.use_cache:
            self.cache.set(df, 'kline', stock_code, start_date, end_date, cache_type='kline')

        return df

    def get_realtime(self,
                     data_source,
                     stock_codes: List[str],
                     force_refresh: bool = True) -> pd.DataFrame:
        """
        获取实时行情（实时数据通常不缓存或短时间缓存）
        """
        df = data_source.get_realtime_quote(stock_codes)

        if not df.empty:
            is_valid, errors = self.validator.validate_realtime(df)
            if not is_valid:
                logger.warning(f"实时数据验证问题: {errors}")

        return df

    def preload_data(self,
                     data_source,
                     stock_codes: List[str],
                     start_date: str,
                     end_date: str):
        """
        预加载数据到缓存
        """
        logger.info(f"开始预加载 {len(stock_codes)} 只股票数据...")
        success = 0
        failed = 0

        for i, code in enumerate(stock_codes):
            try:
                df = self.get_kline(data_source, code, start_date, end_date)
                if not df.empty:
                    success += 1
                else:
                    failed += 1

                if (i + 1) % 10 == 0:
                    logger.info(f"进度: {i+1}/{len(stock_codes)}")
            except Exception as e:
                logger.error(f"预加载失败 {code}: {e}")
                failed += 1

        logger.info(f"预加载完成: 成功 {success}, 失败 {failed}")

    def export_data(self,
                    df: pd.DataFrame,
                    filepath: str,
                    format: str = 'csv'):
        """
        导出数据
        :param format: csv, excel, parquet, feather
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if format == 'csv':
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
        elif format == 'excel':
            df.to_excel(filepath, index=False)
        elif format == 'parquet':
            df.to_parquet(filepath, index=False)
        elif format == 'feather':
            df.to_feather(filepath)
        else:
            raise ValueError(f"不支持的格式: {format}")

        logger.info(f"数据已导出: {filepath}")

    def import_data(self, filepath: str) -> pd.DataFrame:
        """导入数据"""
        filepath = Path(filepath)

        if filepath.suffix == '.csv':
            df = pd.read_csv(filepath)
        elif filepath.suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(filepath)
        elif filepath.suffix == '.parquet':
            df = pd.read_parquet(filepath)
        elif filepath.suffix == '.feather':
            df = pd.read_feather(filepath)
        else:
            raise ValueError(f"不支持的格式: {filepath.suffix}")

        # 尝试转换日期列
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])

        logger.info(f"数据已导入: {filepath}, {len(df)} 行")

        return df


if __name__ == '__main__':
    # 测试缓存
    cache = DataCache()
    cache.set({'test': 'data'}, 'test_key')
    result = cache.get('test_key')
    print(f"缓存测试: {result}")

    # 测试验证器
    test_df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=10),
        'open': [10 + i for i in range(10)],
        'high': [10.5 + i for i in range(10)],
        'low': [9.5 + i for i in range(10)],
        'close': [10 + i for i in range(10)],
        'volume': [100000 for _ in range(10)]
    })

    is_valid, errors = DataValidator.validate_kline(test_df)
    print(f"验证结果: {is_valid}, 错误: {errors}")

    # 缓存统计
    stats = cache.get_cache_stats()
    print(f"缓存统计: {stats}")
