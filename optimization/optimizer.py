"""
策略参数优化模块
包含：网格搜索、遗传算法优化、Walk-Forward验证
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from loguru import logger
from itertools import product
import multiprocessing as mp
from functools import partial
import warnings
warnings.filterwarnings('ignore')


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict
    best_score: float
    all_results: List[Dict]
    optimization_time: float


class GridSearchOptimizer:
    """网格搜索优化器"""

    def __init__(self,
                 strategy_class,
                 param_grid: Dict[str, List],
                 scoring: str = 'sharpe',
                 n_jobs: int = -1):
        """
        :param strategy_class: 策略类
        :param param_grid: 参数网格 {'param_name': [value1, value2, ...]}
        :param scoring: 评分指标 (sharpe, return, calmar, sortino)
        :param n_jobs: 并行数 (-1为全部CPU)
        """
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.scoring = scoring
        self.n_jobs = n_jobs if n_jobs > 0 else mp.cpu_count()

    def optimize(self,
                backtest_func: Callable,
                data: pd.DataFrame,
                stock_code: str,
                stock_name: str) -> OptimizationResult:
        """
        执行网格搜索
        :param backtest_func: 回测函数 (strategy, data) -> Dict
        :param data: 数据
        :return: 优化结果
        """
        import time
        start_time = time.time()

        # 生成所有参数组合
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        param_combinations = list(product(*param_values))

        logger.info(f"网格搜索: {len(param_combinations)} 种参数组合")

        # 准备参数列表
        tasks = []
        for params in param_combinations:
            param_dict = dict(zip(param_names, params))
            tasks.append((param_dict, backtest_func, data, stock_code, stock_name))

        # 并行执行
        if self.n_jobs > 1 and len(tasks) > 10:
            with mp.Pool(self.n_jobs) as pool:
                results = pool.starmap(self._evaluate_params, tasks)
        else:
            results = [self._evaluate_params(*task) for task in tasks]

        # 找最佳参数
        best_idx = np.argmax([r['score'] for r in results])
        best_result = results[best_idx]

        optimization_time = time.time() - start_time
        logger.info(f"网格搜索完成，耗时 {optimization_time:.1f} 秒")
        logger.info(f"最佳参数: {best_result['params']}, 得分: {best_result['score']:.4f}")

        return OptimizationResult(
            best_params=best_result['params'],
            best_score=best_result['score'],
            all_results=results,
            optimization_time=optimization_time
        )

    def _evaluate_params(self,
                        params: Dict,
                        backtest_func: Callable,
                        data: pd.DataFrame,
                        stock_code: str,
                        stock_name: str) -> Dict:
        """评估单组参数"""
        try:
            strategy = self.strategy_class(params=params)
            report = backtest_func(strategy, data, stock_code, stock_name)

            if not report:
                return {'params': params, 'score': -999, 'report': None}

            # 计算得分
            if self.scoring == 'sharpe':
                score = report.get('sharpe_ratio', -999)
            elif self.scoring == 'return':
                score = report.get('total_return', -999)
            elif self.scoring == 'calmar':
                max_dd = report.get('max_drawdown', 1)
                score = report.get('annual_return', 0) / max_dd if max_dd > 0 else -999
            elif self.scoring == 'sortino':
                score = report.get('sortino_ratio', -999)
            else:
                score = report.get('sharpe_ratio', -999)

            return {'params': params, 'score': score, 'report': report}

        except Exception as e:
            logger.warning(f"参数评估失败 {params}: {e}")
            return {'params': params, 'score': -999, 'report': None}


class GeneticOptimizer:
    """遗传算法优化器"""

    def __init__(self,
                 strategy_class,
                 param_bounds: Dict[str, Tuple],
                 scoring: str = 'sharpe',
                 population_size: int = 50,
                 generations: int = 30,
                 mutation_rate: float = 0.1,
                 crossover_rate: float = 0.7,
                 elite_size: int = 5):
        """
        :param strategy_class: 策略类
        :param param_bounds: 参数范围 {'param_name': (min, max)}
        :param population_size: 种群大小
        :param generations: 迭代代数
        :param mutation_rate: 变异率
        :param crossover_rate: 交叉率
        :param elite_size: 精英保留数量
        """
        self.strategy_class = strategy_class
        self.param_bounds = param_bounds
        self.scoring = scoring
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_size = elite_size

    def optimize(self,
                backtest_func: Callable,
                data: pd.DataFrame,
                stock_code: str,
                stock_name: str) -> OptimizationResult:
        """
        执行遗传算法优化
        """
        import time
        start_time = time.time()

        # 初始化种群
        population = self._init_population()
        all_results = []
        best_score_history = []

        for gen in range(self.generations):
            # 评估适应度
            fitness_scores = []
            for individual in population:
                result = self._evaluate_individual(
                    individual, backtest_func, data, stock_code, stock_name
                )
                fitness_scores.append(result['score'])
                all_results.append(result)

            # 记录最佳
            best_idx = np.argmax(fitness_scores)
            best_score = fitness_scores[best_idx]
            best_score_history.append(best_score)

            if gen % 5 == 0:
                logger.info(f"第 {gen} 代，最佳得分: {best_score:.4f}")

            # 选择
            selected = self._selection(population, fitness_scores)

            # 交叉
            offspring = self._crossover(selected)

            # 变异
            offspring = self._mutation(offspring)

            # 精英保留
            elite_idx = np.argsort(fitness_scores)[-self.elite_size:]
            elites = [population[i] for i in elite_idx]

            # 新一代
            population = elites + offspring[:self.population_size - self.elite_size]

        # 最终结果
        best_individual = population[0]
        best_result = self._evaluate_individual(
            best_individual, backtest_func, data, stock_code, stock_name
        )

        optimization_time = time.time() - start_time
        logger.info(f"遗传算法完成，耗时 {optimization_time:.1f} 秒")
        logger.info(f"最佳参数: {best_result['params']}, 得分: {best_result['score']:.4f}")

        return OptimizationResult(
            best_params=best_result['params'],
            best_score=best_result['score'],
            all_results=all_results,
            optimization_time=optimization_time
        )

    def _init_population(self) -> List[Dict]:
        """初始化种群"""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param, (min_val, max_val) in self.param_bounds.items():
                if isinstance(min_val, int) and isinstance(max_val, int):
                    individual[param] = np.random.randint(min_val, max_val + 1)
                else:
                    individual[param] = np.random.uniform(min_val, max_val)
            population.append(individual)
        return population

    def _evaluate_individual(self,
                            individual: Dict,
                            backtest_func: Callable,
                            data: pd.DataFrame,
                            stock_code: str,
                            stock_name: str) -> Dict:
        """评估个体"""
        try:
            strategy = self.strategy_class(params=individual)
            report = backtest_func(strategy, data, stock_code, stock_name)

            if not report:
                return {'params': individual, 'score': -999, 'report': None}

            if self.scoring == 'sharpe':
                score = report.get('sharpe_ratio', -999)
            elif self.scoring == 'return':
                score = report.get('total_return', -999)
            elif self.scoring == 'calmar':
                max_dd = report.get('max_drawdown', 1)
                score = report.get('annual_return', 0) / max_dd if max_dd > 0 else -999
            else:
                score = report.get('sharpe_ratio', -999)

            return {'params': individual.copy(), 'score': score, 'report': report}

        except Exception as e:
            return {'params': individual.copy(), 'score': -999, 'report': None}

    def _selection(self, population: List[Dict], fitness: List[float]) -> List[Dict]:
        """轮盘赌选择"""
        # 将负数转换为正数
        fitness = np.array(fitness)
        fitness = fitness - fitness.min() + 1e-6
        probs = fitness / fitness.sum()

        selected_idx = np.random.choice(
            len(population),
            size=self.population_size - self.elite_size,
            replace=True,
            p=probs
        )
        return [population[i].copy() for i in selected_idx]

    def _crossover(self, population: List[Dict]) -> List[Dict]:
        """交叉操作"""
        offspring = []
        for i in range(0, len(population) - 1, 2):
            parent1 = population[i]
            parent2 = population[i + 1]

            if np.random.random() < self.crossover_rate:
                # 单点交叉
                child1, child2 = {}, {}
                keys = list(parent1.keys())
                cross_point = np.random.randint(1, len(keys))

                for j, key in enumerate(keys):
                    if j < cross_point:
                        child1[key] = parent1[key]
                        child2[key] = parent2[key]
                    else:
                        child1[key] = parent2[key]
                        child2[key] = parent1[key]

                offspring.extend([child1, child2])
            else:
                offspring.extend([parent1.copy(), parent2.copy()])

        return offspring

    def _mutation(self, population: List[Dict]) -> List[Dict]:
        """变异操作"""
        for individual in population:
            for param in individual.keys():
                if np.random.random() < self.mutation_rate:
                    min_val, max_val = self.param_bounds[param]
                    if isinstance(min_val, int):
                        individual[param] = np.random.randint(min_val, max_val + 1)
                    else:
                        individual[param] = np.random.uniform(min_val, max_val)

        return population


class WalkForwardOptimizer:
    """Walk-Forward验证优化器"""

    def __init__(self,
                 in_sample_ratio: float = 0.7,
                 n_splits: int = 5,
                 optimization_method: str = 'grid'):
        """
        :param in_sample_ratio: 样本内比例
        :param n_splits: 分割次数
        :param optimization_method: 优化方法 (grid, genetic)
        """
        self.in_sample_ratio = in_sample_ratio
        self.n_splits = n_splits
        self.optimization_method = optimization_method

    def optimize(self,
                strategy_class,
                param_grid: Dict,
                backtest_func: Callable,
                data: pd.DataFrame,
                stock_code: str,
                stock_name: str) -> Dict:
        """
        执行Walk-Forward验证
        """
        import time
        start_time = time.time()

        # 分割数据
        total_len = len(data)
        fold_size = total_len // self.n_splits

        results = []
        all_params = []

        for i in range(self.n_splits - 1):
            # 样本内（训练）
            train_end = (i + 1) * fold_size
            train_start = max(0, train_end - int(fold_size / (1 - self.in_sample_ratio) * self.in_sample_ratio))

            # 样本外（测试）
            test_start = train_end
            test_end = min((i + 2) * fold_size, total_len)

            train_data = data.iloc[train_start:train_end]
            test_data = data.iloc[test_start:test_end]

            logger.info(f"Fold {i+1}: 训练 {train_start}-{train_end}, 测试 {test_start}-{test_end}")

            # 在训练集上优化
            if self.optimization_method == 'grid':
                optimizer = GridSearchOptimizer(strategy_class, param_grid)
            else:
                # 转换为bounds格式
                param_bounds = {k: (min(v), max(v)) for k, v in param_grid.items()}
                optimizer = GeneticOptimizer(strategy_class, param_bounds)

            opt_result = optimizer.optimize(backtest_func, train_data, stock_code, stock_name)
            best_params = opt_result.best_params
            all_params.append(best_params)

            # 在测试集上验证
            strategy = strategy_class(params=best_params)
            test_report = backtest_func(strategy, test_data, stock_code, stock_name)

            results.append({
                'fold': i + 1,
                'train_period': f"{train_data['date'].iloc[0]} ~ {train_data['date'].iloc[-1]}",
                'test_period': f"{test_data['date'].iloc[0]} ~ {test_data['date'].iloc[-1]}",
                'best_params': best_params,
                'train_score': opt_result.best_score,
                'test_return': test_report.get('total_return', 0) if test_report else 0,
                'test_sharpe': test_report.get('sharpe_ratio', 0) if test_report else 0,
                'test_max_dd': test_report.get('max_drawdown', 0) if test_report else 0
            })

        # 汇总结果
        test_returns = [r['test_return'] for r in results]
        test_sharpes = [r['test_sharpe'] for r in results]

        # 参数稳定性分析
        param_stability = self._analyze_param_stability(all_params, param_grid)

        optimization_time = time.time() - start_time
        logger.info(f"Walk-Forward完成，耗时 {optimization_time:.1f} 秒")

        summary = {
            'n_folds': self.n_splits - 1,
            'avg_test_return': np.mean(test_returns),
            'std_test_return': np.std(test_returns),
            'avg_test_sharpe': np.mean(test_sharpes),
            'std_test_sharpe': np.std(test_sharpes),
            'param_stability': param_stability,
            'recommended_params': self._get_recommended_params(all_params),
            'fold_results': results,
            'optimization_time': optimization_time
        }

        return summary

    def _analyze_param_stability(self, all_params: List[Dict],
                                 param_grid: Dict) -> Dict:
        """分析参数稳定性"""
        stability = {}
        for param in param_grid.keys():
            values = [p.get(param) for p in all_params]
            if values:
                stability[param] = {
                    'values': values,
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'cv': np.std(values) / abs(np.mean(values)) if np.mean(values) != 0 else 0
                }
        return stability

    def _get_recommended_params(self, all_params: List[Dict]) -> Dict:
        """获取推荐参数（中位数或众数）"""
        recommended = {}
        for param in all_params[0].keys():
            values = [p[param] for p in all_params]
            if isinstance(values[0], int):
                # 整数参数取众数
                from collections import Counter
                counts = Counter(values)
                recommended[param] = counts.most_common(1)[0][0]
            else:
                # 浮点参数取中位数
                recommended[param] = np.median(values)
        return recommended


def optimize_strategy(strategy_class,
                     param_grid: Dict,
                     data: pd.DataFrame,
                     backtest_func: Callable,
                     method: str = 'grid',
                     **kwargs) -> OptimizationResult:
    """
    策略参数优化便捷函数
    :param strategy_class: 策略类
    :param param_grid: 参数网格或范围
    :param data: 数据
    :param backtest_func: 回测函数
    :param method: 优化方法 (grid, genetic)
    :return: 优化结果
    """
    if method == 'grid':
        optimizer = GridSearchOptimizer(strategy_class, param_grid, **kwargs)
    elif method == 'genetic':
        param_bounds = {k: (min(v), max(v)) for k, v in param_grid.items()}
        optimizer = GeneticOptimizer(strategy_class, param_bounds, **kwargs)
    else:
        raise ValueError(f"未知的优化方法: {method}")

    return optimizer.optimize(backtest_func, data, 'test', 'test')


if __name__ == '__main__':
    # 测试示例
    from strategy.technical import MAStrategy

    # 参数网格
    param_grid = {
        'short_period': [5, 10, 15],
        'mid_period': [20, 30, 40],
        'long_period': [60, 80, 100]
    }

    print("网格搜索参数组合数:", len(list(product(*param_grid.values()))))

    # 实际使用示例：
    # optimizer = GridSearchOptimizer(MAStrategy, param_grid)
    # result = optimizer.optimize(backtest_func, data, '300308', '中际旭创')
