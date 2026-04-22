# 量化交易系统

一个完整的A股量化交易系统，支持回测、实盘交易、数据分析、参数优化和风险管理。

## 功能特性

### 核心功能
- **数据获取**: 14个备用数据源（直接HTTP: 东方财富/腾讯/新浪/网易 + AKShare: 8个 + 通达信）
- **策略模块**: 技术指标策略、消息面策略、综合策略
- **回测系统**: 完整的回测引擎，支持高级绩效分析
- **实盘交易**: 支持模拟盘和通达信实盘
- **数据分析**: 技术分析、市场分析、HTML可视化报告

### 市场分析功能
- **今日交易量分析**: 量比计算、量能状态判断、价量配合分析
- **大盘情绪分析**: 指数实时行情、涨跌家数统计、涨跌停统计、情绪评分
- **板块情绪分析**: 行业板块排行、概念板块热点、板块涨跌统计

### 买入价值排名
- **多股票批量分析**: 一键分析关注列表中所有股票，支持按板块批量排名
- **六维度综合评分**: 技术面(0-20) + 量能(0-20) + 风险(0-20) + 消息面(0-15) + 市场情绪(0-15) + 全球/板块联动(0-10)，总分0-100，50为中性
- **板块股票池**: 内置PCB、存储、CPO三大板块完整股票列表，支持板块内排名
- **排名输出**: 文本表格 + HTML可视化报告（ECharts柱状图 + 详细排名表）
- **消息面分析**: 新闻情绪 + 资金流向（主力净流入/流出）
- **市场情绪**: 大盘涨跌、市场宽度、涨跌停统计
- **全球市场&板块**: 全球主要指数表现 + 所属板块涨跌影响

### 新增功能
- **风险管理**: 止损止盈、追踪止损、ATR动态止损、仓位管理
- **绩效分析**: 夏普比率、索提诺比率、卡玛比率、Alpha/Beta等15+指标
- **参数优化**: 网格搜索、遗传算法、Walk-Forward验证
- **数据缓存**: 内存+磁盘两级缓存，自动过期清理

### 系统优化（v3.0）
- **数据模块**: LRU缓存淘汰+内存上限、分类过期策略、异常检测与自动修复、数据源成功率统计与超时控制、6个直接HTTP数据源(免反爬)
- **策略优化**: MA/MACD假信号过滤、综合策略加权打分、新增分时量价与RSI均值回归策略、参数自适应
- **回测优化**: 信号索引查找加速、多标的组合回测、统计显著性检验
- **风控强化**: ATR波动率自适应止损、阶梯追踪止损、移动止盈、极端行情应急、策略失效检测、仓位动态调整
- **实盘优化**: 指令自动重试（3次/100ms）、防重复提交
- **优化器增强**: A股合理参数区间、遗传算法自适应变异+锦标赛选择、Walk-Forward市场周期自适应
- **可视化增强**: ECharts dataZoom交互、风险预警仪表盘、策略绩效对比报告

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 TA-Lib (可选，用于技术指标计算)
# macOS
brew install ta-lib
pip install TA-Lib

# Ubuntu
sudo apt-get install -y build-essential wget
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
pip install TA-Lib
```

## 配置

1. 复制配置文件:
```bash
cp .env.example .env
```

2. 编辑 `.env` 填入你的交易账号信息（实盘需要）

3. 配置文件说明 (`config/config.py`):
```python
# 风险管理配置
RISK_CONFIG = {
    'max_position_pct': 0.2,        # 单只股票最大仓位
    'max_drawdown_pct': 0.15,       # 最大回撤限制
    'stop_loss_pct': 0.08,          # 止损比例
    'take_profit_pct': 0.15,        # 止盈比例
    'trailing_stop_pct': 0.05,      # 追踪止损
    # v3.0 新增
    'min_position_pct': 0.15,       # 最低仓位(熊市)
    'max_position_pct_dynamic': 0.25,  # 最高仓位(牛市)
    'emergency_drop_threshold': 0.03,  # 大盘暴跌暂停阈值
    'max_consecutive_losses': 3,    # 连续亏损暂停阈值
    'min_win_rate': 0.4,           # 最低胜率
}

# 仓位管理配置
POSITION_CONFIG = {
    'method': 'atr',                # fixed/kelly/atr/volatility
    'target_volatility': 0.15,      # 目标波动率
}

# 数据缓存配置（v3.0 新增）
DATA_CONFIG = {
    'max_memory_items': 100,        # 内存缓存最大条目数
    'max_memory_size_mb': 500,      # 内存缓存最大占用(MB)
}
```

## 使用方法

### 1. 回测

```bash
# 使用默认配置回测
python main.py backtest

# 指定股票和策略
python main.py backtest --stock 300308 --name 中际旭创 --strategy composite

# 使用新增策略
python main.py backtest --stock 300308 --strategy intraday_vp   # 分时量价策略
python main.py backtest --stock 300308 --strategy rsi_mr        # RSI均值回归策略

# 对比多个策略
python main.py backtest --compare

# 指定日期范围和资金
python main.py backtest --start 2024-01-01 --end 2024-12-31 --capital 200000
```

**回测输出指标**:
```
回测报告
━━━━━━━━━━━━━━━━━━━━━━━
收益指标:
  总收益率: 45.32%
  年化收益率: 22.15%
  夏普比率: 1.85
  索提诺比率: 2.34
  卡玛比率: 1.92
  最大回撤: 11.52%

风险指标:
  年化波动率: 18.45%
  VaR(95%): 2.15%

Alpha/Beta:
  Alpha: 8.52%
  Beta: 0.85
  R²: 0.72

交易统计:
  总交易次数: 48
  胜率: 58.3%
  盈利因子: 1.85
```

### 2. 实盘交易

```bash
# 模拟盘交易
python main.py live --paper --capital 100000

# 实盘交易（需要配置通达信）
python main.py live --interval 60
```

### 3. 数据分析

```bash
# 分析默认股票（生成图表）
python main.py analyze --stock 300308 --name 中际旭创

# 生成HTML报告
python main.py analyze --stock 300308 --html report.html

# 或使用专门的HTML命令
python main.py html --stock 300308 --output 300308_report.html

# 分析股票并包含今日交易量分析
python main.py analyze --stock 300308 --today-volume

# 单只股票指定区间分析
python3 main.py analyze --stock 688195 --start 2026-4-13 --end 2026-4-21
```

### 4. 市场分析

```bash
# 完整市场分析（大盘情绪 + 板块情绪）
python main.py market --all

# 只分析大盘情绪
python main.py market --market
# 或简写
python main.py market -m

# 只分析板块情绪
python main.py market --sector
# 或简写
python main.py market -s

# 分析板块情绪并显示TOP 5热门/弱势板块
python main.py market -s --top 5

# 分析某股票今日交易量
python main.py market --volume --stock 300308
# 或简写
python main.py market -v --stock 300308
```

**市场分析输出示例**:
```
============================================================
【大盘情绪分析】
============================================================

主要指数:
  上证指数: 3250.50 (+0.85%)
  深证成指: 10580.20 (+1.12%)
  创业板指: 2150.30 (+1.35%)

市场宽度:
  上涨: 2850 (56.2%)
  下跌: 1980 (39.0%)
  平盘: 245
  涨停: 65
  跌停: 12

市场情绪: 偏强
情绪得分: 35
操作建议: 市场情绪较好，可适度参与

============================================================
【板块情绪分析】
============================================================

热门板块 TOP5:
  1. 人工智能: +3.25% (领涨: 某某科技)
  2. 芯片: +2.85% (领涨: 某某电子)
  3. 新能源汽车: +2.15% (领涨: 某某汽车)
  4. 光伏: +1.95% (领涨: 某某光伏)
  5. 储能: +1.82% (领涨: 某某能源)

弱势板块 TOP5:
  1. 房地产: -1.85%
  2. 银行: -1.20%
  3. 保险: -0.95%
  4. 煤炭: -0.75%
  5. 钢铁: -0.65%

板块情绪: 偏强
情绪得分: 25
操作建议: 板块多数上涨，关注热点持续性
```

**今日交易量分析输出示例**:
```
============================================================
【今日交易量分析】
============================================================
成交量: 12,580,000
成交额: 456,280,000.00
量比: 1.85
5日均量: 6,800,000
10日均量: 7,200,000
20日均量: 6,500,000
换手率: 3.25%
量能状态: 放量
涨跌幅: +2.35%
价量配合: 价涨量增（健康）
分析建议: 量价配合良好，上涨趋势健康
```

### 5. 买入价值排名

```bash
# 排名所有关注股票
python main.py rank

# 排名指定股票
python main.py rank --stocks 300308,301308,601869

# 按板块排名（PCB/存储/CPO）
python main.py rank --sector PCB
python main.py rank --sector 存储
python main.py rank --sector CPO

# 只显示前5名
python main.py rank --top 5

# 板块排名 + 只看前10 + 生成HTML
python main.py rank --sector CPO --top 10 --html cpo_ranking.html

# 生成HTML排名报告
python main.py rank --html
python main.py rank --html custom_ranking.html

# 指定分析区间
python main.py rank --start 2025-01-01 --end 2026-04-21
```

**排名输出示例**:
```
========================================================================================================================
股票买入价值排名（六维度综合评分）
========================================================================================================================
排名  股票名称  代码      最新价   涨跌幅    买入值  建议      技术  量能  风险  消息面  市场  全球/板块
------------------------------------------------------------------------------------------------------------------------
1     中际旭创  300308   123.45  +5.20%    72.3   买入     16    15   低    积极    偏强  偏强/强势
2     江波龙    301308    89.32  -1.05%    51.8   谨慎买入 12    10   中    中性    中性  偏弱/中性
3     长飞光纤  601869    45.60  +0.85%    38.5   持有观望  8     7   高    偏消极  偏弱  偏弱/偏弱
========================================================================================================================

评分说明: 总分0-100，50为中性临界值
  技术面(0-20): 趋势+均线排列+位置+支撑压力+主升浪
  量能(0-20): 放量健康度+资金流入+换手率合理性
  风险(0-20): 涨幅透支+筹码结构+波动级别 (风险越低分越高)
  消息面(0-15): 业绩/行业催化+资金流向+政策/订单
  市场情绪(0-15): 板块强弱+资金偏好+连板效应
  全球/板块联动(0-10): 美股映射+行业周期+海外涨价
```

**六维度评分**:

| 维度 | 分值范围 | 子项 |
|------|----------|------|
| 技术面 | 0-20 | 趋势方向(0-6) + 均线排列(0-5) + 位置(0-4) + 支撑压力(0-3) + 主升浪(0-2) |
| 量能 | 0-20 | 放量健康度(0-8) + 资金流入(0-7) + 换手率合理性(0-5) |
| 风险 | 0-20 | 涨幅透支 + 筹码结构 + 波动级别（风险越低分越高，从20分扣减） |
| 消息面 | 0-15 | 业绩/行业催化(0-7) + 资金流向(0-5) + 政策/订单(0-3) |
| 市场情绪 | 0-15 | 板块强弱(0-6) + 资金偏好(0-5) + 连板效应(0-4) |
| 全球/板块联动 | 0-10 | 美股映射(0-4) + 行业周期(0-3) + 海外涨价(0-3) |

**建议等级**: 强烈买入(≥80) / 买入(≥65) / 谨慎买入(≥50) / 持有观望(≥35) / 减仓(≥20) / 卖出(<20)

**板块股票池** (`config/config.py` 中 `SECTOR_STOCKS`):

| 板块 | 股票数量 | 代表个股 |
|------|----------|----------|
| PCB | 25只 | 沪电股份、深南电路、景旺电子、胜宏科技、生益科技、鹏鼎控股、东山精密等 |
| 存储 | 15只 | 兆易创新、江波龙、北京君正、澜起科技、东芯股份、佰维存储等 |
| CPO | 20只 | 中际旭创、新易盛、天孚通信、光迅科技、华工科技、亨通光电等 |

### 6. 策略参数优化

```bash
# 网格搜索优化（使用A股合理参数区间）
python main.py optimize --strategy ma --method grid --scoring sharpe

# 遗传算法优化（种群80/迭代50，自适应变异+锦标赛选择）
python main.py optimize --strategy macd --method genetic --scoring calmar

# 优化新增策略
python main.py optimize --strategy intraday_vp --method grid
python main.py optimize --strategy rsi_mr --method genetic

# 指定股票和日期
python main.py optimize --strategy composite --stock 300308 \
    --start 2023-01-01 --end 2024-12-31 --output optimize_result.json
```

### 7. 数据缓存管理

```bash
# 查看缓存统计
python main.py cache --stats

# 清空缓存
python main.py cache --clear

# 预加载数据到缓存
python main.py cache --preload
```

### 8. 生成报告

```bash
python main.py report --output daily_report.txt
```

## 代码结构

```
quant_trading/
├── config/               # 配置文件
│   └── config.py         # 系统配置（风险、仓位、优化、缓存、板块股票池等）
├── data/                 # 数据获取模块
│   ├── data_source.py    # 多数据源接口（14个备用源: 6个直接HTTP + 8个AKShare）+ 成功率统计 + 超时控制
│   └── data_manager.py   # 数据缓存（LRU淘汰+分类过期）、验证、异常检测与自动修复
├── strategy/             # 策略模块
│   ├── base.py           # 策略基类 + 参数自适应
│   ├── technical.py      # 技术指标策略（MA/MACD/KDJ/布林/综合，含假信号过滤）
│   ├── sentiment.py      # 消息面策略（新闻/资金/龙虎榜/北向）
│   └── intraday.py       # 日内策略（分时量价突破/RSI均值回归）
├── backtest/             # 回测模块
│   └── engine.py         # 回测引擎（信号索引加速 + 组合回测 + 显著性检验）
├── trade/                # 实盘交易模块
│   └── executor.py       # 模拟盘/实盘（指令重试 + 防重复提交）
├── analysis/             # 数据分析模块
│   ├── analyzer.py       # 技术分析器、市场分析器（大盘/板块情绪）
│   ├── ranker.py         # 股票买入价值排名（技术面+量能+风险三维度评分）
│   ├── performance.py    # 绩效分析（15+指标）
│   └── html_report.py    # HTML可视化报告（dataZoom + 风险预警 + 策略对比 + 排名报告）
├── risk/                 # 风险管理模块
│   └── manager.py        # 止损止盈、仓位管理、ATR自适应止损、移动止盈、
│                         #   极端行情应急、策略失效检测、仓位动态调整
├── optimization/         # 参数优化模块
│   └── optimizer.py      # 网格搜索、遗传算法（自适应变异+锦标赛）、
│                         #   Walk-Forward（市场周期自适应）
├── utils/                # 工具函数
└── main.py               # 主程序入口
```

## 策略说明

### 技术指标策略

| 策略 | 命令选项 | 说明 | 信号触发条件 |
|------|----------|------|--------------|
| MA策略 | `ma` | 均线金叉死叉 | 短期均线上穿/下穿中期均线，成交量+RSI过滤假信号 |
| MACD策略 | `macd` | MACD金叉死叉 | MACD与Signal线交叉，零轴判断+柱状图确认+背离检测 |
| KDJ策略 | `kdj` | KDJ超买超卖 | K/D线在超卖/超买区金叉死叉 |
| 布林带策略 | `boll` | 价格触及上下轨 | 价格触及布林带边界反弹或突破 |
| 综合策略 | `composite` | 多指标加权共振 | MA(30%)+MACD(25%)+RSI(20%)+KDJ(25%)加权打分 |
| 分时量价策略 | `intraday_vp` | 量价突破 | 放量突破前日高点买入，跌破前日低点卖出，均线趋势过滤 |
| RSI均值回归策略 | `rsi_mr` | 超买超卖回归 | RSI<20+布林下轨+MA20上方买入，RSI>80+布林上轨+MA20下方卖出 |

### 消息面策略

| 策略 | 说明 |
|------|------|
| 新闻情绪策略 | 分析新闻正负面情绪，生成买卖信号 |
| 资金流向策略 | 主力资金连续净流入/流出 |
| 龙虎榜策略 | 机构买卖金额分析 |
| 北向资金策略 | 外资持股变动追踪 |

## 风险管理

### 止损类型

```python
from risk import RiskManager, StopLossType

risk_manager = RiskManager()

# 固定止损
stop_price = risk_manager.stop_loss_manager.calculate_stop_loss(
    entry_price=100, stop_type=StopLossType.FIXED
)  # 止损价: 92 (8%止损)

# ATR动态止损
stop_price = risk_manager.stop_loss_manager.calculate_stop_loss(
    entry_price=100, stop_type=StopLossType.ATR, atr=3.5
)  # 止损价: 93 (2倍ATR)

# 追踪止损（阶梯式：盈利5%后3%回撤，盈利10%后5%回撤）
risk_manager.stop_loss_manager.add_position(
    '300308', '中际旭创', 100, 100, StopLossType.TRAILING
)
```

### ATR波动率自适应止损（v3.0）

```python
from risk import AdaptiveATRStopLoss

atr_stop = AdaptiveATRStopLoss(atr_multiplier_range=(1.5, 2.5))
# 高波动时ATR倍数增大(2.5x)，低波动时缩小(1.5x)
stop_price = atr_stop.calculate_stop_price(
    entry_price=100, atr=3.5, atr_history=[2.0, 2.5, 3.0, 3.5, 4.0]
)
```

### 移动止盈（v3.0）

```python
from risk import TrailingTakeProfit

tp = TrailingTakeProfit(activation_pct=0.05, trail_pct=0.03)
# 盈利5%后激活，最高价回落3%触发止盈
triggered, reason = tp.check_take_profit(
    entry_price=100, current_price=108, highest_price=112
)
```

### 极端行情应急处理（v3.0）

```python
from risk import EmergencyHandler

emergency = EmergencyHandler(market_drop_threshold=0.03)

# 大盘暴跌检测（单日跌幅>=3%自动暂停买入）
crash, reason = emergency.check_market_crash(-4.5)

# 个股跌停检测
limit_down, reason = emergency.check_limit_down(
    current_price=90.5, prev_close=100, stock_code='300308'
)

# 检查是否允许买入
allow, reason = emergency.should_allow_buy()
```

### 策略失效检测（v3.0）

```python
from risk import StrategyHealthMonitor

monitor = StrategyHealthMonitor(
    max_consecutive_losses=3,  # 连续3次亏损触发
    min_win_rate=0.4,          # 最低胜率40%
    win_rate_window=20         # 近20笔交易计算
)

# 记录每笔交易结果
monitor.record_trade(profit=0.05)    # 盈利
monitor.record_trade(profit=-0.03)   # 亏损

# 连续亏损3次 → 仓位缩减至50%
# 近20笔胜率<40% → 自动暂停策略
print(f"仓位系数: {monitor.get_position_multiplier()}")  # 0.5 或 1.0
print(f"策略暂停: {monitor.is_paused()}")
```

### 仓位管理

```python
from risk import PositionSizer

sizer = PositionSizer()

# 固定比例仓位
shares = sizer.fixed_fractional(capital=100000, price=50)  # 400股

# Kelly公式仓位
shares = sizer.kelly_criterion(
    capital=100000, price=50,
    win_rate=0.55, avg_win=0.15, avg_loss=0.08
)

# ATR波动率仓位
shares = sizer.atr_based(capital=100000, price=50, atr=1.5)

# 波动率平价仓位
shares = sizer.volatility_parity(
    capital=100000, price=50, volatility=0.25
)

# 动态仓位调整（v3.0）：结合个股波动率和大盘趋势
shares = sizer.dynamic_position(
    capital=100000, price=50,
    stock_volatility=0.25,        # 个股年化波动率
    market_trend='bull'           # bull/bear/neutral
)  # 牛市0.25, 熊市0.15, 震荡0.20
```

## 绩效分析指标

| 类别 | 指标 | 说明 |
|------|------|------|
| 收益 | 总收益率、年化收益率、超额收益 | 衡量策略盈利能力 |
| 风险 | 波动率、最大回撤、VaR、CVaR | 衡量策略风险水平 |
| 风险调整 | 夏普比率、索提诺比率、卡玛比率 | 风险调整后的收益 |
| 市场 | Alpha、Beta、R²、信息比率 | 相对基准的表现 |
| 交易 | 胜率、盈利因子、平均盈亏 | 交易执行质量 |
| 分布 | 偏度、峰度 | 收益分布特征 |

## 参数优化

### 网格搜索（使用A股合理参数区间）
```python
from optimization import GridSearchOptimizer

# A股合理参数区间（v3.0）
param_grid = {
    'short_period': [3, 5, 8, 10],
    'mid_period': [15, 20, 30],
    'long_period': [40, 60, 80, 120],
}

optimizer = GridSearchOptimizer(MAStrategy, param_grid, scoring='sharpe')
result = optimizer.optimize(backtest_func, data, stock_code, stock_name)

print(f"最佳参数: {result.best_params}")
print(f"最佳夏普比率: {result.best_score}")
```

### 遗传算法（自适应变异+锦标赛选择）
```python
from optimization import GeneticOptimizer

param_bounds = {
    'short_period': (3, 10),
    'mid_period': (15, 30),
    'long_period': (40, 120),
}

optimizer = GeneticOptimizer(
    MAStrategy, param_bounds,
    population_size=80,      # v3.0: 50→80
    generations=50,          # v3.0: 30→50
    tournament_size=3        # v3.0: 锦标赛选择替代轮盘赌
)
# 自适应变异率: 前期0.2(探索) → 后期0.05(收敛)
result = optimizer.optimize(backtest_func, data, stock_code, stock_name)
```

### Walk-Forward验证（市场周期自适应）
```python
from optimization import WalkForwardOptimizer

wf_optimizer = WalkForwardOptimizer(in_sample_ratio=0.7, n_splits=5)
# v3.0: 自动检测市场周期(牛市/震荡/熊市)
#   牛市训练集比例0.6，震荡市0.7，熊市0.8
summary = wf_optimizer.optimize(
    MAStrategy, param_grid, backtest_func, data, stock_code, stock_name
)

print(f"平均测试收益: {summary['avg_test_return']:.2%}")
print(f"参数稳定性: {summary['param_stability']}")
```

## HTML报告

生成的HTML报告包含：

- **技术面分析**: K线图、均线、MACD、RSI、KDJ、成交量
- **风险预警**: 综合风险评分仪表盘、RSI/波动率/布林带/KDJ风险提示（v3.0）
- **消息面分析**: 新闻情绪、资金流向
- **操作建议**: 综合评分、买入/卖出建议
- **可视化图表**: ECharts交互式图表，支持dataZoom缩放、hover

颜色遵循中国股市惯例：**红涨绿跌**

### 策略绩效对比报告（v3.0）

```python
from analysis.html_report import HTMLReportGenerator

generator = HTMLReportGenerator()

# 为多个策略生成对比报告
strategy_results = {
    'MA策略': ma_report,
    'MACD策略': macd_report,
    '综合策略': composite_report,
}
generator.generate_comparison_report(
    strategy_results, stock_name='中际旭创',
    output_path='comparison_report.html'
)
# 包含：净值曲线叠加对比 + 雷达图多维指标对比 + 指标对比表
```

## 风险提示

- 本系统仅供学习和研究使用
- 实盘交易有风险，投资需谨慎
- 历史回测不代表未来收益
- 参数优化可能导致过拟合
- 请在充分了解风险后使用

## 未来扩展

1. [ ] 添加更多因子策略（动量、价值、质量等）
2. [ ] 机器学习策略（LSTM、Transformer）
3. [ ] Web可视化Dashboard
4. [ ] 策略实盘监控系统
5. [ ] 期货/期权多品种支持

## 更新日志

### v3.0.0 (2026-04)
- **数据模块优化**: LRU缓存淘汰+内存上限、分类过期策略(日K线4h/实时30s/资金流向1h)、3σ异常检测与自动修复、数据源成功率统计与超时控制、6个直接HTTP数据源(东方财富/腾讯/新浪/网易日K线 + 腾讯/新浪实时行情，免反爬优先尝试)
- **策略优化**: MA策略增加成交量+RSI假信号过滤、MACD策略增加背离检测和短线参数(8,21,5)、综合策略改为加权打分制(MA30%/MACD25%/RSI20%/KDJ25%)
- **新增策略**: 分时量价突破策略(`intraday_vp`)、RSI均值回归策略(`rsi_mr`)
- **策略参数自适应**: 根据市场波动率自动调整均线周期和止损范围
- **回测优化**: 信号日期索引查找(替代遍历)、多标的组合回测(`run_portfolio_backtest`)、统计显著性检验(t检验+Bootstrap)
- **风控强化**: ATR波动率自适应止损(`AdaptiveATRStopLoss`)、阶梯追踪止损(盈利5%→3%回撤/盈利10%→5%回撤)、移动止盈(`TrailingTakeProfit`)、极端行情应急处理(`EmergencyHandler`)、策略失效检测(`StrategyHealthMonitor`)、仓位动态调整(大盘趋势+个股波动率自适应0.15-0.25)
- **实盘优化**: 交易指令自动重试(最多3次/100ms)、防重复提交(5秒内同标的不重复)
- **优化器增强**: A股合理参数区间建议、遗传算法种群80/迭代50、自适应变异率(0.2→0.05)、锦标赛选择替代轮盘赌、Walk-Forward市场周期自适应(牛市0.6/震荡0.7/熊市0.8)
- **可视化增强**: ECharts dataZoom交互缩放、风险预警仪表盘(评分0-100)、策略绩效对比报告(净值曲线+雷达图)
- **新增买入价值排名**: `rank`命令批量分析多只股票，六维度评分(技术面0-20+量能0-20+风险0-20+消息面0-15+市场情绪0-15+全球/板块联动0-10)，总分0-100，50为中性，建议等级(强烈买入/买入/谨慎买入/持有观望/减仓/卖出)，文本表格+HTML可视化排名报告，`--sector`按板块排名(PCB/存储/CPO)，板块股票池自动识别
- **Bug修复**: `NorthboundFlowStrategy.generate_signals`未定义变量、`analyzer.py`缺少akshare导入、波动率nan%显示

## 更新日志

### v2.1.0 (2025-04)
- 新增市场分析命令 (`market`)
- 新增今日交易量分析（量比、量能状态、价量配合）
- 新增大盘情绪分析（指数行情、涨跌统计、情绪评分）
- 新增板块情绪分析（行业/概念板块排行、热点追踪）
- 新增数据源接口（指数实时行情、板块数据、市场概览）

### v2.0.0 (2024-04)
- 新增风险管理模块（止损止盈、仓位管理）
- 新增高级绩效分析（15+指标）
- 新增策略参数优化（网格搜索、遗传算法）
- 新增数据缓存管理
- 优化HTML报告颜色方案
- 更新配置文件结构

### v1.0.0
- 基础回测功能
- 技术指标策略
- 消息面策略
- 数据分析

## License

MIT
