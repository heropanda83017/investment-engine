#!/usr/bin/env python3
"""回测引擎 — 策略优化器与回测系统的桥梁

将优化后的因子权重转化为回测参数，调用 backtest.run_portfolio 执行验证，
返回标准化评估指标。

与 backtest.py 的区别:
- backtest.py: 底层回测实现（backtrader Cerebro）
- backtest_engine.py: 上层引擎，对接优化器和流水线
"""

import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

log = logging.getLogger("backtest_engine")


class BacktestEngine:
    """策略回测引擎 — 权重→回测→评估"""

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir
        self._last_result = None

    def run_with_weights(self, weights: Dict[str, float],
                         price_data: dict = None,
                         ranked_codes: List[str] = None,
                         top_n: int = 5,
                         cash: float = 1000000) -> Dict:
        """使用指定权重运行回测

        参数:
            weights: {factor_name: weight} 因子权重映射
            price_data: {code: DataFrame} 价格数据
            ranked_codes: 按因子评分排序的股票列表
            top_n: 持仓数量
            cash: 初始资金

        返回:
            回测结果字典
        """
        from backtest import run_portfolio

        if not ranked_codes:
            return self._empty_result("无股票数据")

        # 如果无外传 price_data，尝试用引擎数据
        if price_data is None:
            price_data = self._load_price_data(ranked_codes)

        result = run_portfolio(
            ranked_codes=ranked_codes,
            price_data=price_data,
            cash=cash,
            top_n=top_n,
        )

        self._last_result = result
        return result

    def run_walk_forward(self, weights: Dict[str, float],
                         ranked_codes_by_period: dict,
                         price_data: dict = None,
                         n_splits: int = 4) -> Dict:
        """Walk-Forward 交叉验证回测"""
        from backtest import walk_forward_cv

        if not ranked_codes_by_period:
            return self._empty_result("无时间段数据")

        result = walk_forward_cv(
            price_data=price_data or {},
            ranked_codes_by_period=ranked_codes_by_period,
            n_splits=n_splits,
        )

        self._last_result = result
        return result

    def compare_strategies(self, old_weights: Dict, new_weights: Dict,
                           ranked_codes: List[str],
                           price_data: dict = None) -> Dict:
        """比较新旧策略的回测表现

        返回:
            {"old": {...}, "new": {...}, "improvement": {...},
             "decision": "accept"/"rollback"/"hold"}
        """
        old_result = self.run_with_weights(old_weights, price_data, ranked_codes)
        new_result = self.run_with_weights(new_weights, price_data, ranked_codes)

        old_ret = old_result.get("return_pct", 0)
        new_ret = new_result.get("return_pct", 0)

        # Sharpe 比较
        old_sharpe = self._estimate_sharpe(old_result)
        new_sharpe = self._estimate_sharpe(new_result)

        improvement = {
            "return_diff": round(new_ret - old_ret, 2),
            "return_pct_change": round((new_ret / max(old_ret, 0.01) - 1) * 100, 1),
            "sharpe_diff": round(new_sharpe - old_sharpe, 4),
        }

        # 决策逻辑
        if new_ret > old_ret * 1.05 and new_sharpe > old_sharpe * 0.95:
            decision = "accept"
        elif new_ret < old_ret * 0.95:
            decision = "rollback"
        else:
            decision = "hold"

        return {
            "old": old_result,
            "new": new_result,
            "improvement": improvement,
            "decision": decision,
        }

    def _estimate_sharpe(self, result: Dict) -> float:
        """从回测结果估算Sharpe比率"""
        returns = result.get("daily_returns", [])
        if len(returns) < 5:
            return 0.0
        from backtest import sharpe_ratio
        return sharpe_ratio(pd.Series(returns))

    def _load_price_data(self, codes: List[str]) -> dict:
        """加载价格数据（从缓存或provider）"""
        price_data = {}
        try:
            from data_provider import get_provider
            provider = get_provider()
            for code in codes[:20]:  # 最多加载20只
                try:
                    df = provider.get_kline(code, days=252)
                    if df is not None and not df.empty:
                        price_data[code] = df
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"加载价格数据失败: {e}")
        return price_data

    def _empty_result(self, reason: str) -> Dict:
        return {
            "status": "no_data",
            "reason": reason,
            "return_pct": 0.0,
            "stocks": 0,
        }

    def summary(self) -> str:
        """回测摘要"""
        if not self._last_result:
            return "尚未运行回测"
        r = self._last_result
        return (
            f"回测: {r.get('status', '?')} | "
            f"收益: {r.get('return_pct', 0):.2f}% | "
            f"持仓: {r.get('stocks', 0)}只 | "
            f"日均: {r.get('rebalance_days', '?')}天再平衡"
        )
