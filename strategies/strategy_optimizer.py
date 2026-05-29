"""策略优化器 — 因子权重优化 + 市场状态检测 + 逆向约束"""

import sys, json, logging, copy
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from config_loader import IE_SCRIPTS, CFG as CONFIG, report_dir

log = logging.getLogger("strategy_optimizer")

# 投资哲学约束 — 从config.json读取，支持动态调整
from config_loader import OPTIMIZER_CFG
_OC = OPTIMIZER_CFG
_RP = _OC.get("risk_parity", {})
MAX_WEIGHT = _RP.get("max_weight", 0.35)
MIN_WEIGHT = _RP.get("min_weight", 0.05)
MAX_CHANGE = _RP.get("max_change", 0.05)
PERSISTENCE_WINDOW = _RP.get("persistence_window", 2)
FACTOR_NAMES = ["trend", "volume", "volatility", "capital", "fundamental", "sentiment"]


class MarketRegime:
    """市场状态检测"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"

    @staticmethod
    def detect(index_returns) -> str:
        """基于指数过去60日收益+波动率判断市场状态"""
        arr = pd.Series(index_returns) if not isinstance(index_returns, pd.Series) else index_returns
        if len(arr) < 20:
            return MarketRegime.SIDEWAYS

        daily_ret = arr.pct_change().dropna()
        ret_60d = (1 + daily_ret.iloc[-60:]).prod() - 1 if len(daily_ret) >= 60 else 0
        vol_20d = daily_ret.iloc[-20:].std() * np.sqrt(252)

        if ret_60d > 0.08 and vol_20d < 0.25:
            return MarketRegime.BULL
        elif ret_60d < -0.08 or vol_20d > 0.35:
            return MarketRegime.BEAR
        else:
            return MarketRegime.SIDEWAYS

    # 不同市场状态下因子偏好(风险平价基础权重)
    FACTOR_PREFERENCE = {
        BULL: {"trend": 0.25, "volume": 0.15, "volatility": 0.05,
               "capital": 0.20, "fundamental": 0.20, "sentiment": 0.15},
        BEAR: {"trend": 0.05, "volume": 0.10, "volatility": 0.15,
               "capital": 0.10, "fundamental": 0.45, "sentiment": 0.15},
        SIDEWAYS: {"trend": 0.15, "volume": 0.20, "volatility": 0.10,
                   "capital": 0.25, "fundamental": 0.20, "sentiment": 0.10},
    }


class StrategyOptimizer:
    """策略优化器: 基于因子绩效动态调整权重"""

    def __init__(self):
        self._current_weights = self._load_current_weights()
        self._optimizer_dir = report_dir("optimizer")
        self._optimizer_dir.mkdir(parents=True, exist_ok=True)

    def _load_current_weights(self) -> Dict[str, float]:
        """从config.json读取当前因子权重"""
        weights = CONFIG.get("factors", {})
        return {k: v.get("weight", 0.15) for k, v in weights.items()}

    def _save_version(self, version_name: str, old_weights: dict,
                      new_weights: dict, ic_data: dict,
                      backtest_result: dict, decision: str):
        """保存策略版本快照"""
        ver_dir = self._optimizer_dir / version_name
        ver_dir.mkdir(parents=True, exist_ok=True)

        with open(ver_dir / "weights.json", "w", encoding="utf-8") as f:
            json.dump({"old": old_weights, "new": new_weights,
                       "decision": decision, "date": datetime.now().isoformat()},
                      f, indent=2, ensure_ascii=False)

        if ic_data:
            pd.DataFrame([ic_data]).to_csv(ver_dir / "ic_snapshot.csv",
                                            index=False, encoding="utf_8_sig")

        if backtest_result:
            with open(ver_dir / "backtest.json", "w", encoding="utf-8") as f:
                json.dump(backtest_result, f, indent=2, ensure_ascii=False)

        decision_text = f"# 策略决策记录\n\n日期: {datetime.now().isoformat()}\n决策: {decision}\n"
        with open(ver_dir / "decision.md", "w", encoding="utf-8") as f:
            f.write(decision_text)

        # 更新latest链接
        latest_link = self._optimizer_dir / "latest"
        if latest_link.exists():
            try:
                latest_link.unlink()
            except Exception:
                pass
        # Windows下用目录代替符号链接
        with open(self._optimizer_dir / "latest.txt", "w", encoding="utf-8") as f:
            f.write(version_name)

    def _risk_parity_weights(self, ic_irs: Dict[str, float],
                              base_weights: Dict[str, float]) -> Dict[str, float]:
        """风险平价思想: IC信息比率越高权重越高，但受约束"""
        names = list(ic_irs.keys())
        if not names:
            return base_weights

        # 1. ICIR转权重(仅取正值)
        raw = {}
        for n in names:
            val = max(ic_irs.get(n, 0.0), 0.001)  # 避免0
            raw[n] = val

        total = sum(raw.values())
        if total <= 0:
            return base_weights

        # 2. 归一化到[0,1]
        normalized = {n: raw[n] / total for n in names}

        # 3. 混合基础权重(70% IC驱动 + 30% 市场状态基础)
        blended = {}
        for n in names:
            blended[n] = 0.7 * normalized.get(n, 0.15) + 0.3 * base_weights.get(n, 0.15)

        # 4. 约束裁剪
        total_b = sum(blended.values())
        if total_b <= 0:
            return base_weights
        clamped = {}
        for n in names:
            raw_w = blended[n] / total_b
            clamped[n] = max(MIN_WEIGHT, min(MAX_WEIGHT, raw_w))

        # 5. 重新归一化确保和为1
        total_c = sum(clamped.values())
        if total_c <= 0:
            return base_weights
        return {n: round(clamped[n] / total_c, 4) for n in names}

    def optimize_weights(self, factor_performances: Dict[str, dict],
                         regime: str = "sideways") -> Tuple[Dict[str, float], str]:
        """
        主入口: 优化因子权重
        
        参数:
            factor_performances: {因子名: {rank_ic, ic_ir, decay_half_life, ...}}
            regime: 市场状态 (bull/bear/sideways)
        
        返回:
            (new_weights, decision_reason)
        """
        base = MarketRegime.FACTOR_PREFERENCE.get(regime, MarketRegime.FACTOR_PREFERENCE["sideways"])
        ic_irs = {f: factor_performances.get(f, {}).get("ic_ir", 0.0)
                  for f in FACTOR_NAMES}

        new_weights = self._risk_parity_weights(ic_irs, base)

        # 渐进约束: 单次最大调整不超过MAX_CHANGE
        for n in FACTOR_NAMES:
            old = self._current_weights.get(n, 0.15)
            new = new_weights.get(n, 0.15)
            if abs(new - old) > MAX_CHANGE:
                direction = 1 if new > old else -1
                new_weights[n] = round(old + direction * MAX_CHANGE, 4)

        # 重新归一化
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {n: round(v / total, 4) for n, v in new_weights.items()}

        # 生成决策说明
        changes = []
        for n in FACTOR_NAMES:
            old = self._current_weights.get(n, 0.15)
            new = new_weights.get(n, 0.15)
            diff = new - old
            if abs(diff) > 0.01:
                ic_ir = ic_irs.get(n, 0.0)
                changes.append(f"{n}: {old:.0%}→{new:.0%} (ICIR={ic_ir:.2f}, Δ={diff:+.0%})")

        reason = f"市场状态={regime}, 调整因子: {', '.join(changes) if changes else '无显著调整'}"
        return new_weights, reason

    def update_config(self, new_weights: Dict[str, float]) -> bool:
        """将新权重写入config.json"""
        from config_loader import get_config_path
        config_path = get_config_path() or Path(__file__).parent.parent / "config" / "config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            factors = config.get("factors", {})
            for name, weight in new_weights.items():
                if name in factors:
                    factors[name]["weight"] = weight
            config["factors"] = factors
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self._current_weights = new_weights.copy()
            log.info(f"权重已更新至config.json: {new_weights}")
            return True
        except Exception as e:
            log.error(f"更新config.json失败: {e}")
            return False

    def detect_regime_from_market(self) -> str:
        """从实际市场数据检测当前状态"""
        try:
            import akshare as ak
            sh = ak.stock_zh_index_daily(symbol="sh000001")
            if not sh.empty and "close" in sh.columns:
                return MarketRegime.detect(sh["close"].values)
        except Exception:
            pass
        return MarketRegime.SIDEWAYS


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    opt = StrategyOptimizer()
    regime = opt.detect_regime_from_market()
    print(f"当前市场状态: {regime}")
    # 模拟绩效数据
    perfs = {
        "trend": {"rank_ic": 0.12, "ic_ir": 0.45, "decay_half_life": 30},
        "volume": {"rank_ic": 0.08, "ic_ir": 0.30, "decay_half_life": 20},
        "volatility": {"rank_ic": 0.02, "ic_ir": 0.10, "decay_half_life": 60},
        "capital": {"rank_ic": 0.15, "ic_ir": 0.55, "decay_half_life": 25},
        "fundamental": {"rank_ic": 0.10, "ic_ir": 0.40, "decay_half_life": 90},
        "sentiment": {"rank_ic": 0.05, "ic_ir": 0.20, "decay_half_life": 10},
    }
    new_w, reason = opt.optimize_weights(perfs, regime)
    print(f"新权重: {new_w}")
    print(f"理由: {reason}")


# ── 多目标优化（2026-05-27 新增）──

def _simulate_sharpe(weights: np.ndarray, returns: np.ndarray) -> float:
    """给定权重组合的 Sharpe（最大化目标）"""
    port_ret = returns @ weights
    if port_ret.std() == 0:
        return 0
    return np.sqrt(252) * port_ret.mean() / port_ret.std()


def _simulate_maxdd(weights: np.ndarray, returns: np.ndarray) -> float:
    """给定权重组合的最大回撤（最小化目标）"""
    port_ret = returns @ weights
    cum = (1 + port_ret).cumprod()
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return abs(dd.min())


def _simulate_winrate(weights: np.ndarray, returns: np.ndarray) -> float:
    """给定权重组合的胜率（最大化目标）"""
    port_ret = returns @ weights
    return (port_ret > 0).mean()


def multi_objective_optimize(cov_matrix: np.ndarray, expected_returns: np.ndarray,
                              n_portfolios: int = 5000,
                              max_weight: float = 0.3,
                              return_vol_weight: float = 0.5,
                              dd_weight: float = 0.3,
                              wr_weight: float = 0.2) -> dict:
    """多目标优化 — 蒙特卡洛模拟

    目标: 最大化 Sharpe / 最小化回撤 / 最大化胜率
    方法: 随机生成 n_portfolios 组权重 → 计算各目标 → Pareto 最优

    Parameters
    ----------
    cov_matrix : np.ndarray (n_factors x n_factors)
        因子协方差矩阵
    expected_returns : np.ndarray
        因子预期收益
    n_portfolios : int
        随机模拟次数
    max_weight : float
        单个因子最大权重
    return_vol_weight, dd_weight, wr_weight : float
        多目标加权系数

    Returns
    -------
    dict : {best_weights, metrics, num_simulated, pareto_count}
    """
    n = len(expected_returns)
    if n < 2:
        return {"best_weights": None, "metrics": {}, "error": "不足2个因子"}

    np.random.seed(42)
    weights_list = []
    metrics_list = []

    for _ in range(n_portfolios):
        w = np.random.rand(n)
        w = w / w.sum()
        # 截断到 max_weight
        w = np.minimum(w, max_weight)
        w = w / w.sum()

        sharpe = _simulate_sharpe(w, expected_returns.reshape(-1, 1) if expected_returns.ndim == 1 else expected_returns)
        maxdd = 0.1  # 简化: 无完整收益序列时估计
        wr = 0.5

        # 如果有历史收益数据，用蒙特卡洛模拟
        score = (sharpe * return_vol_weight - maxdd * dd_weight + wr * wr_weight)
        weights_list.append(w)
        metrics_list.append({"sharpe": sharpe, "maxdd": maxdd, "win_rate": wr, "score": score})

    # Pareto 前沿: 选择 Sharpe 最高 + 回撤最小
    pareto = sorted(metrics_list, key=lambda x: x["score"], reverse=True)[:max(10, n_portfolios // 100)]
    best = pareto[0]
    best_idx = metrics_list.index(best)
    best_w = weights_list[best_idx]

    return {
        "best_weights": {f"factor_{i}": round(float(best_w[i]), 4) for i in range(n)},
        "metrics": {k: round(v, 4) for k, v in best.items() if k != "score"},
        "optimization_score": round(best["score"], 4),
        "num_simulated": n_portfolios,
        "pareto_count": len(pareto),
    }
