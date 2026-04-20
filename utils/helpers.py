"""
工具函数
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os


def format_number(num: float, decimal: int = 2) -> str:
    """格式化数字显示"""
    if abs(num) >= 1e8:
        return f"{num/1e8:.{decimal}f}亿"
    elif abs(num) >= 1e4:
        return f"{num/1e4:.{decimal}f}万"
    else:
        return f"{num:.{decimal}f}"


def calculate_compound_return(returns: List[float]) -> float:
    """计算复利收益"""
    return (1 + pd.Series(returns)).prod() - 1


def calculate_sharpe_ratio(returns: List[float],
                          risk_free_rate: float = 0.03) -> float:
    """计算夏普比率"""
    returns = np.array(returns)
    excess_returns = returns - risk_free_rate / 252
    if np.std(excess_returns) == 0:
        return 0
    return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """计算最大回撤"""
    equity = np.array(equity_curve)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    return np.min(drawdown)


def trading_days_between(start_date: str, end_date: str) -> int:
    """计算两个日期之间的交易日数（简化版，不含节假日）"""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    days = pd.bdate_range(start, end)
    return len(days)


def get_next_trading_day(date: str = None) -> str:
    """获取下一个交易日"""
    if date is None:
        date = datetime.now()

    next_day = pd.to_datetime(date) + timedelta(days=1)

    # 简单处理：跳过周末
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)

    return next_day.strftime('%Y-%m-%d')


def save_backtest_result(result: Dict, filename: str):
    """保存回测结果"""
    # 移除不可序列化的字段
    save_result = {}
    for key, value in result.items():
        if key in ['equity_curve', 'trades']:
            # 转换为可序列化格式
            if isinstance(value, list):
                save_result[key] = [
                    {k: str(v) if isinstance(v, datetime) else v
                     for k, v in item.items()}
                    if isinstance(item, dict) else item
                    for item in value
                ]
        else:
            save_result[key] = value

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(save_result, f, ensure_ascii=False, indent=2)


def load_backtest_result(filename: str) -> Dict:
    """加载回测结果"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_trade_id() -> str:
    """生成交易ID"""
    return datetime.now().strftime('%Y%m%d%H%M%S%f')


def validate_stock_code(code: str) -> bool:
    """验证股票代码格式"""
    if not code:
        return False
    # 6位数字
    if len(code) != 6:
        return False
    return code.isdigit()


def get_market_code(stock_code: str) -> int:
    """获取市场代码"""
    if stock_code.startswith('6'):
        return 1  # 上海
    else:
        return 0  # 深圳


class Singleton:
    """单例模式装饰器"""
    _instances = {}

    def __init__(self, cls):
        self._cls = cls

    def __call__(self, *args, **kwargs):
        if self._cls not in self._instances:
            self._instances[self._cls] = self._cls(*args, **kwargs)
        return self._instances[self._cls]


def setup_logger(log_file: str = None):
    """配置日志"""
    from loguru import logger
    import sys

    # 移除默认处理器
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="INFO"
    )

    # 文件输出
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="30 days"
        )

    return logger


if __name__ == '__main__':
    # 测试工具函数
    print(format_number(123456789))
    print(format_number(12345))

    print(f"夏普比率: {calculate_sharpe_ratio([0.01, -0.02, 0.03, 0.02, -0.01]):.2f}")
    print(f"最大回撤: {calculate_max_drawdown([100, 110, 105, 115, 108, 120]):.2%}")

    print(f"下一个交易日: {get_next_trading_day()}")
