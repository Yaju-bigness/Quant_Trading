"""
快速测试脚本
演示系统基本功能
"""
from datetime import datetime
from config.config import STOCKS
from data.data_source import DataSource
from strategy.technical import CompositeStrategy
from backtest.engine import BacktestEngine
from analysis.analyzer import TechnicalAnalyzer

# 配置中文字体
import matplotlib.pyplot as plt
plt.rcParams['font.family'] = ['Arial Unicode MS', 'PingFang HK', 'Kaiti SC', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False


def test_data_fetch():
    """测试数据获取"""
    print("\n" + "="*50)
    print("测试数据获取")
    print("="*50)

    ds = DataSource(use_tdx=False)

    # 测试获取K线数据
    for name, code in STOCKS.items():
        print(f"\n获取 {name} ({code}) K线数据...")
        df = ds.get_daily_kline(code, '2024-01-01', '2024-12-31')
        if not df.empty:
            print(f"  成功获取 {len(df)} 条数据")
            print(f"  最新价格: {df['close'].iloc[-1]:.2f}")
            print(f"  区间涨跌: {(df['close'].iloc[-1]/df['close'].iloc[0]-1)*100:.2f}%")
        else:
            print(f"  获取失败")

    # 测试获取新闻
    print(f"\n获取新闻数据...")
    news = ds.get_news('300308', limit=5)
    if news:
        print(f"  成功获取 {len(news)} 条新闻")
        for n in news[:2]:
            print(f"  - {n['title'][:30]}...")

    ds.close()


def test_backtest():
    """测试回测功能"""
    print("\n" + "="*50)
    print("测试回测功能")
    print("="*50)

    engine = BacktestEngine(initial_capital=100000)
    strategy = CompositeStrategy()

    # 回测第一只股票
    name, code = list(STOCKS.items())[0]
    print(f"\n回测 {name} ({code})...")
    print(f"策略: {strategy.name}")
    print(f"日期: 2024-01-01 ~ 2024-12-31")
    print(f"初始资金: 100,000")

    report = engine.run_backtest(
        strategy, code, name,
        '2024-01-01', '2024-12-31'
    )

    if report:
        print("\n回测结果:")
        print(f"  最终资产: {report['final_capital']:.2f}")
        print(f"  总收益率: {report['total_return']*100:.2f}%")
        print(f"  年化收益: {report['annual_return']*100:.2f}%")
        print(f"  最大回撤: {report['max_drawdown']*100:.2f}%")
        print(f"  夏普比率: {report['sharpe_ratio']:.2f}")
        print(f"  交易次数: {report['total_trades']}")
        print(f"  胜率: {report['win_rate']*100:.1f}%")

        # 显示最近几笔交易
        if report['trades']:
            print("\n最近交易记录:")
            for trade in report['trades'][-5:]:
                print(f"  {trade.date.strftime('%Y-%m-%d')} {trade.action.upper()} "
                      f"{trade.stock_name} {trade.quantity}股 @ {trade.price:.2f}")

        return report

    return None


def test_analysis():
    """测试分析功能"""
    print("\n" + "="*50)
    print("测试技术分析")
    print("="*50)

    analyzer = TechnicalAnalyzer()

    for name, code in STOCKS.items():
        print(f"\n分析 {name} ({code})...")
        analysis = analyzer.analyze_stock(
            code,
            '2024-01-01',
            datetime.now().strftime('%Y-%m-%d')
        )

        if analysis:
            print(f"  最新价: {analysis['latest_price']:.2f}")
            print(f"  均线趋势: {analysis['ma']['trend']}")
            print(f"  MACD: {analysis['macd']['trend']}")
            print(f"  RSI: {analysis['rsi']['value']:.1f} ({analysis['rsi']['status']})")
            print(f"  KDJ: {analysis['kdj']['status']}")
            print(f"  综合评分: {analysis['score']}")
            print(f"  操作建议: {analysis['recommendation']}")


def main():
    """主测试流程"""
    print("\n" + "#"*60)
    print("#  量化交易系统测试")
    print("#"*60)

    # 测试数据获取
    test_data_fetch()

    # 测试回测
    report = test_backtest()

    # 测试分析
    test_analysis()

    print("\n" + "#"*60)
    print("#  测试完成")
    print("#"*60)

    # 如果回测成功，询问是否显示图表
    if report:
        engine = BacktestEngine(initial_capital=100000)
        try:
            print("\n正在生成回测图表...")
            engine.plot_results(report)
        except Exception as e:
            print(f"图表生成失败: {e}")
            print("请确保已安装 matplotlib: pip install matplotlib")


if __name__ == '__main__':
    main()
