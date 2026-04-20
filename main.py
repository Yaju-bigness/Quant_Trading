"""
量化交易系统主程序
支持：回测、实盘、数据分析、参数优化、风险管理
"""
import argparse
from datetime import datetime, timedelta
from loguru import logger

from config.config import STOCKS, TRADING_CONFIG, BACKTEST_CONFIG, RISK_CONFIG
from data.data_source import DataSource
from data.data_manager import DataManager
from strategy.technical import (
    MAStrategy, MACDStrategy, KDJStrategy,
    BollingerStrategy, CompositeStrategy
)
from strategy.sentiment import (
    NewsSentimentStrategy, MoneyFlowStrategy,
    CompositeSentimentStrategy
)
from backtest.engine import BacktestEngine
from trade.executor import PaperTrader, LiveTradingEngine, create_trader
from analysis.analyzer import TechnicalAnalyzer, ReportGenerator
from analysis.html_report import HTMLReportGenerator
from analysis.performance import PerformanceAnalyzer
from risk.manager import RiskManager, RiskConfig
from optimization.optimizer import GridSearchOptimizer, GeneticOptimizer, optimize_strategy


def run_backtest(args):
    """运行回测"""
    logger.info("开始回测...")

    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=args.capital or TRADING_CONFIG['initial_capital'],
        commission_rate=TRADING_CONFIG['commission_rate'],
        stamp_duty=TRADING_CONFIG['stamp_duty'],
        slippage=TRADING_CONFIG['slippage']
    )

    # 选择策略
    strategy_map = {
        'ma': MAStrategy(),
        'macd': MACDStrategy(),
        'kdj': KDJStrategy(),
        'boll': BollingerStrategy(),
        'composite': CompositeStrategy(),
    }

    if args.compare:
        # 对比模式使用所有策略
        strategies = list(strategy_map.values())
    elif args.strategy == 'all':
        strategies = list(strategy_map.values())
    else:
        strategies = [strategy_map.get(args.strategy, CompositeStrategy())]

    # 获取股票
    if args.stock:
        stock_code = args.stock
        stock_name = args.name or stock_code
    else:
        stock_code = list(STOCKS.values())[0]
        stock_name = list(STOCKS.keys())[0]

    start_date = args.start or BACKTEST_CONFIG['start_date']
    end_date = args.end or BACKTEST_CONFIG['end_date']

    # 运行回测
    if args.compare:
        # 多策略对比
        results = engine.compare_strategies(
            strategies, stock_code, stock_name,
            start_date, end_date
        )
    else:
        # 单策略回测
        for strategy in strategies:
            logger.info(f"回测策略: {strategy.name}")
            report = engine.run_backtest(
                strategy, stock_code, stock_name,
                start_date, end_date
            )

            if report:
                engine.plot_results(report, save_path=args.output)

    logger.info("回测完成")


def run_live(args):
    """运行实盘交易"""
    logger.info("启动实盘交易...")

    # 创建交易执行器
    if args.paper:
        trader = PaperTrader(initial_capital=args.capital or TRADING_CONFIG['initial_capital'])
    else:
        from config.config import THS_API_CONFIG
        trader = create_trader('live', THS_API_CONFIG)

    # 选择策略
    strategies = [
        CompositeStrategy(),
        # 可以添加更多策略
    ]

    # 创建交易引擎
    engine = LiveTradingEngine(
        trader=trader,
        strategies=strategies,
        stock_list=STOCKS
    )

    # 启动实时交易
    try:
        engine.start(interval=args.interval or 60)
    except KeyboardInterrupt:
        engine.stop()
        logger.info("交易已停止")


def run_analysis(args):
    """运行数据分析"""
    logger.info("开始数据分析...")

    analyzer = TechnicalAnalyzer()

    # 默认日期为近一个月
    end_date = args.end or datetime.now().strftime('%Y-%m-%d')
    start_date = args.start or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    # 分析股票
    if args.stock:
        stock_code = args.stock
        stock_name = args.name or stock_code

        # 生成HTML报告
        if args.html:
            html_generator = HTMLReportGenerator()
            html_path = args.html if args.html != True else f"{stock_code}_report.html"
            html_generator.save_html_report(
                stock_code, stock_name,
                start_date, end_date,
                html_path
            )
            logger.info(f"HTML报告已生成: {html_path}")
        else:
            # 打印文字报告
            analysis = analyzer.analyze_stock(stock_code, start_date, end_date)
            if analysis:
                print(analyzer.generate_report(analysis))

            # 弹出图表
            analyzer.plot_analysis(
                stock_code, stock_name,
                start_date, end_date,
                save_path=args.output
            )
    else:
        # 分析所有关注的股票 - 只打印报告
        for name, code in STOCKS.items():
            logger.info(f"分析 {name} ({code})")
            analysis = analyzer.analyze_stock(code, start_date, end_date)
            print(analyzer.generate_report(analysis))


def run_html_report(args):
    """生成HTML分析报告"""
    logger.info("生成HTML报告...")

    html_generator = HTMLReportGenerator()

    # 默认日期为近一个月
    end_date = args.end or datetime.now().strftime('%Y-%m-%d')
    start_date = args.start or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    if args.stock:
        stock_code = args.stock
        stock_name = args.name or stock_code
        output_path = args.output or f"{stock_code}_report.html"

        html_generator.save_html_report(
            stock_code, stock_name,
            start_date, end_date,
            output_path
        )
    else:
        # 为所有关注股票生成HTML报告
        for name, code in STOCKS.items():
            logger.info(f"生成 {name} ({code}) HTML报告...")
            output_path = f"{code}_report.html"
            html_generator.save_html_report(
                code, name,
                start_date, end_date,
                output_path
            )


def run_report(args):
    """生成报告"""
    logger.info("生成报告...")

    generator = ReportGenerator()
    report = generator.generate_daily_report(STOCKS)
    print(report)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"报告已保存: {args.output}")


def run_optimize(args):
    """运行策略参数优化"""
    logger.info("开始策略参数优化...")

    # 选择策略
    strategy_map = {
        'ma': MAStrategy,
        'macd': MACDStrategy,
        'kdj': KDJStrategy,
        'boll': BollingerStrategy,
        'composite': CompositeStrategy,
    }
    strategy_class = strategy_map.get(args.strategy, MAStrategy)

    # 定义参数网格
    if args.strategy == 'ma':
        param_grid = {
            'short_period': [5, 10, 15],
            'mid_period': [20, 30, 40],
            'long_period': [60, 80, 100],
        }
    elif args.strategy == 'macd':
        param_grid = {
            'fast': [8, 10, 12, 14],
            'slow': [20, 24, 26, 30],
            'signal': [7, 9, 11],
        }
    elif args.strategy == 'kdj':
        param_grid = {
            'n': [7, 9, 11, 14],
            'm1': [2, 3, 4],
            'm2': [2, 3, 4],
        }
    elif args.strategy == 'boll':
        param_grid = {
            'period': [15, 20, 25],
            'std_dev': [1.5, 2.0, 2.5],
        }
    else:
        param_grid = {
            'ma_short': [5, 10],
            'ma_mid': [20, 30],
            'rsi_oversold': [25, 30, 35],
            'rsi_overbought': [65, 70, 75],
        }

    # 获取股票
    if args.stock:
        stock_code = args.stock
        stock_name = args.name or stock_code
    else:
        stock_code = list(STOCKS.values())[0]
        stock_name = list(STOCKS.keys())[0]

    start_date = args.start or BACKTEST_CONFIG['start_date']
    end_date = args.end or BACKTEST_CONFIG['end_date']

    # 获取数据
    data_source = DataSource(use_tdx=False)
    data = data_source.get_daily_kline(stock_code, start_date, end_date)

    if data.empty:
        logger.error("无法获取数据")
        return

    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=TRADING_CONFIG['initial_capital'],
        commission_rate=TRADING_CONFIG['commission_rate'],
        stamp_duty=TRADING_CONFIG['stamp_duty'],
        slippage=TRADING_CONFIG['slippage']
    )

    # 定义回测函数
    def backtest_func(strategy, data, stock_code, stock_name):
        return engine.run_backtest(strategy, stock_code, stock_name,
                                  start_date, end_date, data)

    # 运行优化
    if args.method == 'grid':
        optimizer = GridSearchOptimizer(
            strategy_class, param_grid,
            scoring=args.scoring
        )
        result = optimizer.optimize(backtest_func, data, stock_code, stock_name)
    else:
        # 遗传算法
        param_bounds = {k: (min(v), max(v)) for k, v in param_grid.items()}
        optimizer = GeneticOptimizer(
            strategy_class, param_bounds,
            scoring=args.scoring
        )
        result = optimizer.optimize(backtest_func, data, stock_code, stock_name)

    # 输出结果
    print(f"\n优化完成!")
    print(f"最佳参数: {result.best_params}")
    print(f"最佳得分 ({args.scoring}): {result.best_score:.4f}")
    print(f"优化耗时: {result.optimization_time:.1f}秒")

    # 保存结果
    if args.output:
        import json
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump({
                'best_params': result.best_params,
                'best_score': result.best_score,
                'optimization_time': result.optimization_time
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"优化结果已保存: {args.output}")


def run_cache(args):
    """数据缓存管理"""
    from data.data_manager import DataCache

    cache = DataCache()

    if args.clear:
        cache.clear_memory()
        cache.clear_disk()
        print("缓存已清空")
    elif args.stats:
        stats = cache.get_cache_stats()
        print("\n缓存统计:")
        print(f"  内存缓存数: {stats['memory_cache_count']}")
        print(f"  磁盘缓存数: {stats['disk_cache_count']}")
        print(f"  磁盘使用: {stats['disk_usage_mb']:.2f} MB")
    elif args.preload:
        data_source = DataSource(use_tdx=False)
        data_manager = DataManager(use_cache=True)

        stock_codes = list(STOCKS.values())
        start_date = BACKTEST_CONFIG['start_date']
        end_date = datetime.now().strftime('%Y-%m-%d')

        data_manager.preload_data(data_source, stock_codes, start_date, end_date)
        print("数据预加载完成")
    else:
        stats = cache.get_cache_stats()
        print("使用 --stats 查看缓存统计")
        print("使用 --clear 清空缓存")
        print("使用 --preload 预加载数据")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='量化交易系统')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 回测命令
    backtest_parser = subparsers.add_parser('backtest', help='运行回测')
    backtest_parser.add_argument('--stock', '-s', help='股票代码')
    backtest_parser.add_argument('--name', '-n', help='股票名称')
    backtest_parser.add_argument('--strategy', choices=['ma', 'macd', 'kdj', 'boll', 'composite', 'all'],
                                default='composite', help='选择策略')
    backtest_parser.add_argument('--start', help='开始日期 YYYY-MM-DD')
    backtest_parser.add_argument('--end', help='结束日期 YYYY-MM-DD')
    backtest_parser.add_argument('--capital', type=float, help='初始资金')
    backtest_parser.add_argument('--compare', action='store_true', help='对比多个策略')
    backtest_parser.add_argument('--output', '-o', help='输出文件路径')

    # 实盘命令
    live_parser = subparsers.add_parser('live', help='运行实盘交易')
    live_parser.add_argument('--paper', action='store_true', help='使用模拟盘')
    live_parser.add_argument('--capital', type=float, help='初始资金(模拟盘)')
    live_parser.add_argument('--interval', type=int, default=60, help='监控间隔(秒)')

    # 分析命令
    analysis_parser = subparsers.add_parser('analyze', help='数据分析')
    analysis_parser.add_argument('--stock', '-s', help='股票代码')
    analysis_parser.add_argument('--name', '-n', help='股票名称')
    analysis_parser.add_argument('--start', help='开始日期')
    analysis_parser.add_argument('--end', help='结束日期')
    analysis_parser.add_argument('--output', '-o', help='保存图表路径')
    analysis_parser.add_argument('--html', nargs='?', const=True, default=False,
                                help='生成HTML报告（可指定文件名）')

    # HTML报告命令
    html_parser = subparsers.add_parser('html', help='生成HTML分析报告')
    html_parser.add_argument('--stock', '-s', help='股票代码')
    html_parser.add_argument('--name', '-n', help='股票名称')
    html_parser.add_argument('--start', help='开始日期')
    html_parser.add_argument('--end', help='结束日期')
    html_parser.add_argument('--output', '-o', help='HTML文件保存路径')

    # 报告命令
    report_parser = subparsers.add_parser('report', help='生成报告')
    report_parser.add_argument('--output', '-o', help='输出文件路径')

    # 优化命令
    optimize_parser = subparsers.add_parser('optimize', help='策略参数优化')
    optimize_parser.add_argument('--stock', '-s', help='股票代码')
    optimize_parser.add_argument('--name', '-n', help='股票名称')
    optimize_parser.add_argument('--strategy', choices=['ma', 'macd', 'kdj', 'boll', 'composite'],
                                default='ma', help='选择策略')
    optimize_parser.add_argument('--method', choices=['grid', 'genetic'],
                                default='grid', help='优化方法')
    optimize_parser.add_argument('--start', help='开始日期 YYYY-MM-DD')
    optimize_parser.add_argument('--end', help='结束日期 YYYY-MM-DD')
    optimize_parser.add_argument('--scoring', choices=['sharpe', 'return', 'calmar'],
                                default='sharpe', help='评分指标')
    optimize_parser.add_argument('--output', '-o', help='输出报告路径')

    # 缓存命令
    cache_parser = subparsers.add_parser('cache', help='数据缓存管理')
    cache_parser.add_argument('--clear', action='store_true', help='清空缓存')
    cache_parser.add_argument('--stats', action='store_true', help='查看缓存统计')
    cache_parser.add_argument('--preload', action='store_true', help='预加载数据')

    args = parser.parse_args()

    # 执行对应命令
    if args.command == 'backtest':
        run_backtest(args)
    elif args.command == 'live':
        run_live(args)
    elif args.command == 'analyze':
        run_analysis(args)
    elif args.command == 'html':
        run_html_report(args)
    elif args.command == 'report':
        run_report(args)
    elif args.command == 'optimize':
        run_optimize(args)
    elif args.command == 'cache':
        run_cache(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
