"""
配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 交易标的
STOCKS = {
    '中际旭创': '300308',  # 创业板
    '江波龙': '301308',    # 创业板
    '长飞光纤': '601869',  # 主板
}

# 交易配置
TRADING_CONFIG = {
    'initial_capital': 100000,  # 初始资金 10万
    'commission_rate': 0.0003,  # 佣金率 万三
    'stamp_duty': 0.001,        # 印花税 千一（仅卖出）
    'min_trade_unit': 100,      # 最小交易单位（手）
    'slippage': 0.001,          # 滑点
}

# 回测配置
BACKTEST_CONFIG = {
    'start_date': '2023-01-01',
    'end_date': '2024-12-31',
    'benchmark': '000300',  # 沪深300作为基准
}

# 风险管理配置
RISK_CONFIG = {
    'max_position_pct': 0.2,        # 单只股票最大仓位比例
    'max_total_position_pct': 0.8,  # 总仓位上限
    'max_single_loss_pct': 0.02,    # 单笔最大亏损占总资金比例
    'max_daily_loss_pct': 0.05,     # 单日最大亏损
    'max_drawdown_pct': 0.15,       # 最大回撤限制
    'stop_loss_pct': 0.08,          # 默认止损比例 8%
    'take_profit_pct': 0.15,        # 默认止盈比例 15%
    'trailing_stop_pct': 0.05,      # 追踪止损回撤比例 5%
    'atr_multiplier': 2.0,          # ATR止损倍数
    'risk_free_rate': 0.03,         # 无风险利率
}

# 仓位管理配置
POSITION_CONFIG = {
    'method': 'atr',                # 仓位计算方法: fixed/kelly/atr/volatility
    'base_position_ratio': 0.2,     # 基础仓位比例
    'kelly_fraction': 0.5,          # Kelly比例（半Kelly）
    'target_volatility': 0.15,      # 目标波动率
}

# 同花顺/通达信API配置（需填入实际值）
THS_API_CONFIG = {
    'host': os.getenv('THS_HOST', '119.29.51.120'),
    'port': int(os.getenv('THS_PORT', 7709)),
    # 实盘账号信息（请勿提交到git）
    'account': os.getenv('THS_ACCOUNT', ''),
    'password': os.getenv('THS_PASSWORD', ''),
}

# 技术指标参数
INDICATOR_PARAMS = {
    'ma_short': 5,
    'ma_mid': 20,
    'ma_long': 60,
    'rsi_period': 14,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'bollinger_period': 20,
    'bollinger_std': 2,
    'kdj_n': 9,
    'kdj_m1': 3,
    'kdj_m2': 3,
}

# 数据配置
DATA_CONFIG = {
    'cache_dir': os.path.expanduser('~/.quant_trading/cache'),
    'cache_expire_hours': 4,
    'use_cache': True,
}

# 优化配置
OPTIMIZATION_CONFIG = {
    'method': 'grid',      # grid/genetic
    'scoring': 'sharpe',   # sharpe/return/calmar
    'n_jobs': -1,          # 并行数
}

# 日志配置
LOG_CONFIG = {
    'level': 'INFO',
    'format': '{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
    'rotation': '10 MB',
    'retention': '30 days',
}
