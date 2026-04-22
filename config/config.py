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

# 板块股票池（用于排名筛选）
SECTOR_STOCKS = {
    'PCB': {
        '沪电股份': '002463',
        '深南电路': '002916',
        '景旺电子': '603228',
        '胜宏科技': '300476',
        '生益科技': '600183',
        '鹏鼎控股': '002938',
        '东山精密': '002384',
        '崇达技术': '002815',
        '兴森科技': '002436',
        '世运电路': '603920',
        '奥士康': '002913',
        '明阳电路': '300739',
        '四会富仕': '300852',
        '中京电子': '002579',
        '博敏电子': '603936',
        '超声电子': '000823',
        '天津普林': '002134',
        '方正科技': '600601',
        '逸豪新材': '301176',
        '科翔股份': '300903',
        '威尔高': '301257',
        '满坤科技': '301132',
        '金百泽': '301041',
        '本川智能': '300964',
        '迅捷兴': '688655',
    },
    '存储': {
        '兆易创新': '603986',
        '江波龙': '301308',
        '北京君正': '300223',
        '澜起科技': '688008',
        '东芯股份': '688110',
        '普冉股份': '688766',
        '恒烁股份': '688416',
        '佰维存储': '688045',
        '德明利': '001309',
        '朗科科技': '300042',
        '万润科技': '002654',
        '好上好': '001298',
        '大为股份': '002213',
        '聚辰股份': '688123',
        '芯天下': '301659',
    },
    'CPO': {
        '中际旭创': '300308',
        '新易盛': '300502',
        '天孚通信': '300394',
        '光迅科技': '002281',
        '华工科技': '000988',
        '亨通光电': '600487',
        '太辰光': '300570',
        '剑桥科技': '603083',
        '博创科技': '300548',
        '仕佳光子': '688313',
        '源杰科技': '688498',
        '中瓷电子': '003031',
        '联特科技': '301205',
        '光库科技': '300620',
        '罗博特科': '300757',
        '通宇通讯': '002792',
        '铭普光磁': '002902',
        '亚康股份': '301085',
        '鼎通科技': '688672',
        '可川科技': '603052',
    },
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
    # 新增：动态仓位范围
    'min_position_pct': 0.15,       # 最低单只仓位(熊市)
    'max_position_pct_dynamic': 0.25,  # 最高单只仓位(牛市)
    # 新增：极端行情配置
    'emergency_drop_threshold': 0.03,  # 大盘暴跌阈值
    'limit_down_threshold': -0.095,    # 跌停判断阈值
    # 新增：策略失效检测
    'max_consecutive_losses': 3,    # 最大连续亏损次数
    'min_win_rate': 0.4,           # 最低胜率
    'win_rate_window': 20,         # 胜率计算窗口
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
    # 新增：缓存优化配置
    'max_memory_items': 100,       # 内存缓存最大条目数
    'max_memory_size_mb': 500,     # 内存缓存最大占用(MB)
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
