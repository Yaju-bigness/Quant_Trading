# 量化交易系统

一个完整的A股量化交易系统，支持回测、实盘交易、数据分析、参数优化和风险管理。

## 功能特性

### 核心功能
- **数据获取**: 8个备用数据源（AKShare、通达信、新浪、腾讯、网易等）
- **策略模块**: 技术指标策略、消息面策略、综合策略
- **回测系统**: 完整的回测引擎，支持高级绩效分析
- **实盘交易**: 支持模拟盘和通达信实盘
- **数据分析**: 技术分析、市场分析、HTML可视化报告

### 新增功能
- **风险管理**: 止损止盈、追踪止损、ATR动态止损、仓位管理
- **绩效分析**: 夏普比率、索提诺比率、卡玛比率、Alpha/Beta等15+指标
- **参数优化**: 网格搜索、遗传算法、Walk-Forward验证
- **数据缓存**: 内存+磁盘两级缓存，自动过期清理

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
}

# 仓位管理配置
POSITION_CONFIG = {
    'method': 'atr',                # fixed/kelly/atr/volatility
    'target_volatility': 0.15,      # 目标波动率
}
```

## 使用方法

### 1. 回测

```bash
# 使用默认配置回测
python main.py backtest

# 指定股票和策略
python main.py backtest --stock 300308 --name 中际旭创 --strategy composite

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
```

### 4. 策略参数优化

```bash
# 网格搜索优化
python main.py optimize --strategy ma --method grid --scoring sharpe

# 遗传算法优化
python main.py optimize --strategy macd --method genetic --scoring calmar

# 指定股票和日期
python main.py optimize --strategy composite --stock 300308 \
    --start 2023-01-01 --end 2024-12-31 --output optimize_result.json
```

### 5. 数据缓存管理

```bash
# 查看缓存统计
python main.py cache --stats

# 清空缓存
python main.py cache --clear

# 预加载数据到缓存
python main.py cache --preload
```

### 6. 生成报告

```bash
python main.py report --output daily_report.txt
```

## 代码结构

```
quant_trading/
├── config/               # 配置文件
│   └── config.py         # 系统配置（风险、仓位、优化等）
├── data/                 # 数据获取模块
│   ├── data_source.py    # 多数据源接口（8个备用源）
│   └── data_manager.py   # 数据缓存、验证、清洗
├── strategy/             # 策略模块
│   ├── base.py           # 策略基类
│   ├── technical.py      # 技术指标策略
│   └── sentiment.py      # 消息面策略
├── backtest/             # 回测模块
│   └── engine.py         # 回测引擎（集成风险管理和绩效分析）
├── trade/                # 实盘交易模块
│   └── executor.py       # 模拟盘/实盘交易执行器
├── analysis/             # 数据分析模块
│   ├── analyzer.py       # 技术分析器
│   ├── performance.py    # 绩效分析（15+指标）
│   └── html_report.py    # HTML可视化报告
├── risk/                 # 风险管理模块
│   └── manager.py        # 止损止盈、仓位管理、风险控制
├── optimization/         # 参数优化模块
│   └── optimizer.py      # 网格搜索、遗传算法、Walk-Forward
├── utils/                # 工具函数
└── main.py               # 主程序入口
```

## 策略说明

### 技术指标策略

| 策略 | 说明 | 信号触发条件 |
|------|------|--------------|
| MA策略 | 均线金叉死叉 | 短期均线上穿/下穿中期均线 |
| MACD策略 | MACD金叉死叉 | MACD与Signal线交叉，结合零轴判断 |
| KDJ策略 | KDJ超买超卖 | K/D线在超卖/超买区金叉死叉 |
| 布林带策略 | 价格触及上下轨 | 价格触及布林带边界反弹或突破 |
| 综合策略 | 多指标共振 | MA、MACD、RSI、KDJ多指标确认 |

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

# 追踪止损（持续更新）
risk_manager.stop_loss_manager.add_position(
    '300308', '中际旭创', 100, 100, StopLossType.TRAILING
)
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

### 网格搜索
```python
from optimization import GridSearchOptimizer

param_grid = {
    'short_period': [5, 10, 15],
    'mid_period': [20, 30, 40],
    'long_period': [60, 80, 100],
}

optimizer = GridSearchOptimizer(MAStrategy, param_grid, scoring='sharpe')
result = optimizer.optimize(backtest_func, data, stock_code, stock_name)

print(f"最佳参数: {result.best_params}")
print(f"最佳夏普比率: {result.best_score}")
```

### 遗传算法
```python
from optimization import GeneticOptimizer

param_bounds = {
    'short_period': (5, 15),
    'mid_period': (20, 40),
    'long_period': (60, 100),
}

optimizer = GeneticOptimizer(
    MAStrategy, param_bounds,
    population_size=50, generations=30
)
result = optimizer.optimize(backtest_func, data, stock_code, stock_name)
```

### Walk-Forward验证
```python
from optimization import WalkForwardOptimizer

wf_optimizer = WalkForwardOptimizer(in_sample_ratio=0.7, n_splits=5)
summary = wf_optimizer.optimize(
    MAStrategy, param_grid, backtest_func, data, stock_code, stock_name
)

print(f"平均测试收益: {summary['avg_test_return']:.2%}")
print(f"参数稳定性: {summary['param_stability']}")
```

## HTML报告

生成的HTML报告包含：

- **技术面分析**: K线图、均线、MACD、RSI、KDJ、成交量
- **消息面分析**: 新闻情绪、资金流向
- **操作建议**: 综合评分、买入/卖出建议
- **可视化图表**: ECharts交互式图表，支持缩放、hover

颜色遵循中国股市惯例：**红涨绿跌**

## 风险提示

- 本系统仅供学习和研究使用
- 实盘交易有风险，投资需谨慎
- 历史回测不代表未来收益
- 参数优化可能导致过拟合
- 请在充分了解风险后使用

## 未来扩展

1. [ ] 添加更多因子策略（动量、价值、质量等）
2. [ ] 机器学习策略（LSTM、Transformer）
3. [ ] 多标的组合回测和优化
4. [ ] 实时风控预警系统
5. [ ] Web可视化Dashboard
6. [ ] 策略实盘监控系统

## 更新日志

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
