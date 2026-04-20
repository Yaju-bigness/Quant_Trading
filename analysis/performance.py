"""
绩效分析模块
包含：夏普比率、索提诺比率、卡玛比率、信息比率、Alpha/Beta等高级指标
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """绩效指标"""
    # 收益指标
    total_return: float = 0          # 总收益率
    annual_return: float = 0         # 年化收益率
    excess_return: float = 0         # 超额收益

    # 风险指标
    volatility: float = 0            # 年化波动率
    max_drawdown: float = 0          # 最大回撤
    max_drawdown_duration: int = 0   # 最大回撤持续天数
    var_95: float = 0                # 95% VaR
    cvar_95: float = 0               # 95% CVaR

    # 风险调整收益
    sharpe_ratio: float = 0          # 夏普比率
    sortino_ratio: float = 0         # 索提诺比率
    calmar_ratio: float = 0          # 卡玛比率
    information_ratio: float = 0     # 信息比率
    treynor_ratio: float = 0         # 特雷诺比率

    # Alpha/Beta
    alpha: float = 0                 # Jensen's Alpha
    beta: float = 0                  # Beta系数
    r_squared: float = 0             # R平方

    # 交易统计
    total_trades: int = 0            # 总交易次数
    win_rate: float = 0              # 胜率
    profit_factor: float = 0         # 盈利因子
    avg_win: float = 0               # 平均盈利
    avg_loss: float = 0              # 平均亏损
    max_consecutive_wins: int = 0    # 最大连续盈利
    max_consecutive_losses: int = 0  # 最大连续亏损

    # 其他
    skewness: float = 0              # 偏度
    kurtosis: float = 0              # 峰度


class PerformanceAnalyzer:
    """绩效分析器"""

    def __init__(self, risk_free_rate: float = 0.03):
        """
        :param risk_free_rate: 无风险利率（年化）
        """
        self.risk_free_rate = risk_free_rate

    def calculate_metrics(self,
                         equity_curve: List[Dict],
                         benchmark_curve: List[Dict] = None,
                         trades: List[Dict] = None) -> PerformanceMetrics:
        """
        计算全部绩效指标
        :param equity_curve: 净值曲线 [{date, equity}]
        :param benchmark_curve: 基准净值曲线
        :param trades: 交易记录
        :return: 绩效指标
        """
        metrics = PerformanceMetrics()

        if not equity_curve:
            return metrics

        # 转换为DataFrame
        equity_df = pd.DataFrame(equity_curve)
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        equity_df = equity_df.sort_values('date')

        # 计算日收益率
        equity_df['returns'] = equity_df['equity'].pct_change()
        returns = equity_df['returns'].dropna()

        # 基准收益率
        benchmark_returns = None
        if benchmark_curve:
            bench_df = pd.DataFrame(benchmark_curve)
            bench_df['date'] = pd.to_datetime(bench_df['date'])
            bench_df = bench_df.sort_values('date')
            bench_df['returns'] = bench_df['equity'].pct_change()
            benchmark_returns = bench_df['returns'].dropna()

        # 1. 收益指标
        metrics.total_return = (equity_df['equity'].iloc[-1] / equity_df['equity'].iloc[0] - 1)

        days = (equity_df['date'].iloc[-1] - equity_df['date'].iloc[0]).days
        if days > 0:
            metrics.annual_return = (1 + metrics.total_return) ** (252 / days) - 1

        # 2. 风险指标
        metrics.volatility = returns.std() * np.sqrt(252)
        metrics.max_drawdown, metrics.max_drawdown_duration = self._calculate_drawdown(equity_df['equity'])
        metrics.var_95 = self._calculate_var(returns, 0.95)
        metrics.cvar_95 = self._calculate_cvar(returns, 0.95)

        # 3. 风险调整收益
        daily_rf = self.risk_free_rate / 252
        excess_returns = returns - daily_rf

        # 夏普比率
        if returns.std() > 0:
            metrics.sharpe_ratio = excess_returns.mean() / returns.std() * np.sqrt(252)

        # 索提诺比率（只考虑下行风险）
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = downside_returns.std() * np.sqrt(252)
            if downside_std > 0:
                metrics.sortino_ratio = (metrics.annual_return - self.risk_free_rate) / downside_std

        # 卡玛比率
        if metrics.max_drawdown > 0:
            metrics.calmar_ratio = metrics.annual_return / metrics.max_drawdown

        # 信息比率
        if benchmark_returns is not None and len(benchmark_returns) > 0:
            # 对齐日期
            aligned_returns = returns.align(benchmark_returns, join='inner')[0]
            aligned_bench = returns.align(benchmark_returns, join='inner')[1]

            if len(aligned_returns) > 0:
                active_returns = aligned_returns - aligned_bench
                tracking_error = active_returns.std() * np.sqrt(252)
                if tracking_error > 0:
                    metrics.information_ratio = active_returns.mean() * 252 / tracking_error

                # Alpha/Beta
                metrics.alpha, metrics.beta, metrics.r_squared = self._calculate_alpha_beta(
                    aligned_returns, aligned_bench
                )

                # 超额收益
                benchmark_total = (1 + aligned_bench).prod() - 1
                metrics.excess_return = metrics.total_return - benchmark_total

        # 特雷诺比率
        if metrics.beta > 0:
            metrics.treynor_ratio = (metrics.annual_return - self.risk_free_rate) / metrics.beta

        # 4. 交易统计
        if trades:
            metrics = self._calculate_trade_stats(metrics, trades)

        # 5. 高阶矩
        if len(returns) > 3:
            metrics.skewness = returns.skew()
            metrics.kurtosis = returns.kurtosis()

        return metrics

    def _calculate_drawdown(self, equity: pd.Series) -> Tuple[float, int]:
        """计算最大回撤及持续时间"""
        # 累计最大值
        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max

        max_dd = abs(drawdown.min())

        # 计算最大回撤持续时间
        drawdown_periods = []
        in_drawdown = False
        dd_start = 0

        for i, dd in enumerate(drawdown):
            if dd < 0 and not in_drawdown:
                in_drawdown = True
                dd_start = i
            elif dd == 0 and in_drawdown:
                in_drawdown = False
                drawdown_periods.append(i - dd_start)

        if in_drawdown:
            drawdown_periods.append(len(drawdown) - dd_start)

        max_dd_duration = max(drawdown_periods) if drawdown_periods else 0

        return max_dd, max_dd_duration

    def _calculate_var(self, returns: pd.Series, confidence: float) -> float:
        """计算VaR"""
        return abs(np.percentile(returns, (1 - confidence) * 100))

    def _calculate_cvar(self, returns: pd.Series, confidence: float) -> float:
        """计算CVaR (Expected Shortfall)"""
        var = self._calculate_var(returns, confidence)
        return abs(returns[returns <= -var].mean())

    def _calculate_alpha_beta(self, strategy_returns: pd.Series,
                              benchmark_returns: pd.Series) -> Tuple[float, float, float]:
        """
        计算Alpha、Beta、R-squared
        """
        # 回归分析
        X = benchmark_returns.values
        Y = strategy_returns.values

        # 确保长度一致
        min_len = min(len(X), len(Y))
        X = X[:min_len]
        Y = Y[:min_len]

        # 添加常数项
        X_with_const = np.column_stack([np.ones(min_len), X])

        # OLS回归
        try:
            coeffs = np.linalg.lstsq(X_with_const, Y, rcond=None)[0]
            alpha = coeffs[0] * 252  # 年化Alpha
            beta = coeffs[1]

            # R-squared
            Y_pred = X_with_const @ coeffs
            ss_res = np.sum((Y - Y_pred) ** 2)
            ss_tot = np.sum((Y - Y.mean()) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            return alpha, beta, r_squared
        except:
            return 0, 1, 0

    def _calculate_trade_stats(self, metrics: PerformanceMetrics,
                               trades: List[Dict]) -> PerformanceMetrics:
        """计算交易统计"""
        if not trades:
            return metrics

        metrics.total_trades = len(trades)

        # 区分买卖
        buy_trades = [t for t in trades if t.get('action') == 'buy']
        sell_trades = [t for t in trades if t.get('action') == 'sell']

        # 配对计算盈亏
        profits = []
        for i, sell in enumerate(sell_trades):
            # 找对应的买入
            for buy in buy_trades:
                if buy.get('stock_code') == sell.get('stock_code') and \
                   buy.get('date', buy.get('time')) < sell.get('date', sell.get('time')):
                    profit = (sell['price'] - buy['price']) * sell['quantity']
                    profit -= sell.get('commission', 0) + buy.get('commission', 0)
                    profits.append(profit)
                    break

        if profits:
            wins = [p for p in profits if p > 0]
            losses = [p for p in profits if p < 0]

            metrics.win_rate = len(wins) / len(profits) if profits else 0
            metrics.avg_win = np.mean(wins) if wins else 0
            metrics.avg_loss = abs(np.mean(losses)) if losses else 0

            total_profit = sum(wins)
            total_loss = abs(sum(losses))
            metrics.profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

            # 连续盈亏
            metrics.max_consecutive_wins = self._max_consecutive(profits, lambda x: x > 0)
            metrics.max_consecutive_losses = self._max_consecutive(profits, lambda x: x < 0)

        return metrics

    def _max_consecutive(self, values: List, condition) -> int:
        """计算最大连续次数"""
        max_count = 0
        current_count = 0

        for v in values:
            if condition(v):
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0

        return max_count

    def generate_report(self, metrics: PerformanceMetrics,
                       equity_curve: List[Dict] = None) -> str:
        """生成绩效报告"""
        report = []
        report.append("=" * 60)
        report.append("策略绩效分析报告")
        report.append("=" * 60)

        # 收益指标
        report.append("\n【收益指标】")
        report.append(f"  总收益率: {metrics.total_return*100:.2f}%")
        report.append(f"  年化收益率: {metrics.annual_return*100:.2f}%")
        if metrics.excess_return != 0:
            report.append(f"  超额收益: {metrics.excess_return*100:.2f}%")

        # 风险指标
        report.append("\n【风险指标】")
        report.append(f"  年化波动率: {metrics.volatility*100:.2f}%")
        report.append(f"  最大回撤: {metrics.max_drawdown*100:.2f}%")
        report.append(f"  最大回撤持续: {metrics.max_drawdown_duration}天")
        report.append(f"  VaR(95%): {metrics.var_95*100:.2f}%")
        report.append(f"  CVaR(95%): {metrics.cvar_95*100:.2f}%")

        # 风险调整收益
        report.append("\n【风险调整收益】")
        report.append(f"  夏普比率: {metrics.sharpe_ratio:.3f}")
        report.append(f"  索提诺比率: {metrics.sortino_ratio:.3f}")
        report.append(f"  卡玛比率: {metrics.calmar_ratio:.3f}")
        if metrics.information_ratio != 0:
            report.append(f"  信息比率: {metrics.information_ratio:.3f}")
        if metrics.treynor_ratio != 0:
            report.append(f"  特雷诺比率: {metrics.treynor_ratio:.3f}")

        # Alpha/Beta
        if metrics.beta != 0:
            report.append("\n【市场相关性】")
            report.append(f"  Alpha: {metrics.alpha*100:.2f}%")
            report.append(f"  Beta: {metrics.beta:.3f}")
            report.append(f"  R²: {metrics.r_squared:.3f}")

        # 交易统计
        if metrics.total_trades > 0:
            report.append("\n【交易统计】")
            report.append(f"  总交易次数: {metrics.total_trades}")
            report.append(f"  胜率: {metrics.win_rate*100:.1f}%")
            report.append(f"  盈利因子: {metrics.profit_factor:.2f}")
            report.append(f"  平均盈利: {metrics.avg_win:.2f}")
            report.append(f"  平均亏损: {metrics.avg_loss:.2f}")
            report.append(f"  最大连续盈利: {metrics.max_consecutive_wins}次")
            report.append(f"  最大连续亏损: {metrics.max_consecutive_losses}次")

        # 高阶矩
        if metrics.skewness != 0:
            report.append("\n【收益分布】")
            report.append(f"  偏度: {metrics.skewness:.3f}")
            report.append(f"  峰度: {metrics.kurtosis:.3f}")
            if metrics.skewness > 0:
                report.append("  分布特征: 右偏，正收益概率较大")
            else:
                report.append("  分布特征: 左偏，需警惕尾部风险")

        # 综合评价
        report.append("\n【综合评价】")
        rating = self._rate_strategy(metrics)
        report.append(f"  策略评级: {rating}")

        report.append("=" * 60)

        return "\n".join(report)

    def _rate_strategy(self, metrics: PerformanceMetrics) -> str:
        """策略评级"""
        score = 0

        # 年化收益
        if metrics.annual_return > 0.3:
            score += 25
        elif metrics.annual_return > 0.2:
            score += 20
        elif metrics.annual_return > 0.1:
            score += 15
        elif metrics.annual_return > 0:
            score += 10

        # 夏普比率
        if metrics.sharpe_ratio > 2:
            score += 25
        elif metrics.sharpe_ratio > 1.5:
            score += 20
        elif metrics.sharpe_ratio > 1:
            score += 15
        elif metrics.sharpe_ratio > 0.5:
            score += 10

        # 最大回撤
        if metrics.max_drawdown < 0.1:
            score += 20
        elif metrics.max_drawdown < 0.2:
            score += 15
        elif metrics.max_drawdown < 0.3:
            score += 10
        elif metrics.max_drawdown < 0.5:
            score += 5

        # 胜率
        if metrics.win_rate > 0.6:
            score += 15
        elif metrics.win_rate > 0.5:
            score += 10
        elif metrics.win_rate > 0.4:
            score += 5

        # 盈亏比
        if metrics.profit_factor > 2:
            score += 15
        elif metrics.profit_factor > 1.5:
            score += 10
        elif metrics.profit_factor > 1:
            score += 5

        # 评级
        if score >= 80:
            return "★★★★★ 优秀"
        elif score >= 65:
            return "★★★★☆ 良好"
        elif score >= 50:
            return "★★★☆☆ 一般"
        elif score >= 35:
            return "★★☆☆☆ 较差"
        else:
            return "★☆☆☆☆ 差"


class RollingAnalyzer:
    """滚动分析器"""

    def __init__(self, window: int = 252):
        self.window = window

    def calculate_rolling_metrics(self, equity_curve: List[Dict]) -> pd.DataFrame:
        """计算滚动绩效指标"""
        df = pd.DataFrame(equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df['returns'] = df['equity'].pct_change()

        # 滚动夏普
        df['rolling_sharpe'] = (
            df['returns'].rolling(self.window).mean() /
            df['returns'].rolling(self.window).std() * np.sqrt(252)
        )

        # 滚动波动率
        df['rolling_volatility'] = df['returns'].rolling(self.window).std() * np.sqrt(252)

        # 滚动最大回撤
        df['rolling_max_dd'] = df['equity'].rolling(self.window).apply(
            lambda x: abs(min((x - x.expanding().max()) / x.expanding().max()))
        )

        # 滚动收益
        df['rolling_return'] = df['equity'].pct_change(self.window)

        return df[['date', 'rolling_sharpe', 'rolling_volatility', 'rolling_max_dd', 'rolling_return']]


if __name__ == '__main__':
    # 测试
    analyzer = PerformanceAnalyzer()

    # 模拟净值曲线
    import random
    equity = 100000
    equity_curve = [{'date': '2024-01-01', 'equity': equity}]

    for i in range(1, 252):
        equity *= (1 + random.gauss(0.001, 0.02))
        equity_curve.append({
            'date': f'2024-{i//30+1:02d}-{i%30+1:02d}',
            'equity': equity
        })

    metrics = analyzer.calculate_metrics(equity_curve)
    print(analyzer.generate_report(metrics))
