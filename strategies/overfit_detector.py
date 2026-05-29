"""overfit_detector.py — 过拟合检测工具集

方法:
1. 夏普比衰减 — IS vs OOS Sharpe ratio 衰减率
2. 交叉验证 — 滚动窗口 Sharpe 分布与稳定性
3. 夏普比标准误 — 估计 Sharpe 的置信区间
4. 参数敏感性 — 随机参数扰动后表现稳定性

保护条件: 至少 60 个 OOS 交易日，否则静默跳过
"""
import numpy as np
import pandas as pd
try:
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


def _require_os(asample: np.ndarray, label: str = "OOS", min_n: int = 60) -> bool:
    """样本量检查，不足时打印 warning 返回 False"""
    if len(asample) < min_n:
        import logging
        logging.warning(f"overfit_detector: {label} 样本={len(asample)} < {min_n}, 跳过检测")
        return False
    return True


def _sharpe(returns: np.ndarray, rf: float = 0.02) -> float:
    """年化 Sharpe ratio"""
    if len(returns) < 5 or np.std(returns) == 0:
        return 0.0
    excess = returns - rf / 252
    return np.sqrt(252) * np.mean(excess) / np.std(returns, ddof=1)


# ─── 1. 夏普比衰减 ──────────────────────────


def sharpe_decay(is_returns: np.ndarray, oos_returns: np.ndarray) -> dict:
    """计算 IS vs OOS Sharpe 衰减

    Returns
    -------
    dict : {is_sharpe, oos_sharpe, decay_rate, verdict}
        decay_rate > 0.5 = 严重过拟合, > 0.3 = 关注
    """
    if not _require_os(oos_returns):
        return {"is_sharpe": 0, "oos_sharpe": 0, "decay_rate": 0, "verdict": "insufficient_data"}

    is_s = _sharpe(is_returns)
    oos_s = _sharpe(oos_returns)

    if is_s <= 0:
        decay = 0.0
    elif oos_s >= is_s:
        decay = 0.0  # OOS 比 IS 好，无过拟合
    else:
        decay = (is_s - oos_s) / abs(is_s)

    if decay > 0.5:
        verdict = "severe_overfit"
    elif decay > 0.3:
        verdict = "overfit_warning"
    else:
        verdict = "acceptable"

    return {
        "is_sharpe": round(is_s, 4),
        "oos_sharpe": round(oos_s, 4),
        "decay_rate": round(decay, 4),
        "verdict": verdict,
    }


# ─── 2. 交叉验证 ────────────────────────────


def cv_sharpe_distribution(fold_results: list) -> dict:
    """滚动交叉验证的 Sharpe 分布分析

    Parameters
    ----------
    fold_results : list of dict
        [{fold_id, oos_sharpe, is_sharpe}, ...]

    Returns
    -------
    dict : {mean, std, min, max, sharpe_stability, folds_above_zero}
    """
    # 兼容多种key: oos_sharpe > sharpe_ratio > return_pct近似
    sharps = []
    for f in fold_results:
        if not f:
            continue
        val = f.get("oos_sharpe")
        if val is None:
            val = f.get("sharpe_ratio")
        if val is None and f.get("return_pct") is not None:
            # 从 return_pct 粗略估算 Sharpe (年化收益/波动率假设)
            ret = abs(f.get("return_pct", 0))
            val = ret / max(ret, 0.01) * 0.5  # 粗略近似
        sharps.append(val if val is not None else 0)
    if len(sharps) < 3:
        return {"mean": 0, "std": 0, "verdict": "insufficient_folds"}

    arr = np.array(sharps)
    result = {
        "mean": round(float(np.mean(arr)), 4),
        "std": round(float(np.std(arr, ddof=1)), 4),
        "min": round(float(np.min(arr)), 4),
        "max": round(float(np.max(arr)), 4),
        "folds_above_zero": int(np.sum(arr > 0)),
        "total_folds": len(sharps),
    }

    # 稳定性判断: std 大 + mean 低 = 不可靠
    if result["mean"] > 0 and result["std"] < abs(result["mean"]) * 0.5:
        result["verdict"] = "stable"
    elif result["mean"] > 0:
        result["verdict"] = "volatile"
    else:
        result["verdict"] = "unstable"

    return result


# ─── 3. 夏普比标准误 ────────────────────────


def sharpe_confidence_interval(returns: np.ndarray, level: float = 0.95) -> dict:
    """估计 Sharpe ratio 的标准误和置信区间

    使用 Mertens (2002) 标准误公式，适用于非正态收益
    """
    if not _require_os(returns, "returns", 20):
        return {"sharpe": 0, "se": 0, "ci_lower": 0, "ci_upper": 0}

    s = _sharpe(returns)
    n = len(returns)

    # 偏度和峰度调整
    if HAS_SCIPY:
        skew = stats.skew(returns)
        kurt = stats.kurtosis(returns, fisher=True)
        se = np.sqrt((1 + 0.5 * s**2 - skew * s + (kurt + 2) * s**2 / 4) / n)
    else:
        # 无 scipy 时用基础标准误
        se = np.sqrt((1 + 0.5 * s**2) / n)

    if HAS_SCIPY:
        z = stats.norm.ppf(1 - (1 - level) / 2)
    else:
        # 无 scipy 时的近似 z-value
        z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_map.get(level, 1.96)
    ci_lower = s - z * se
    ci_upper = s + z * se

    return {
        "sharpe": round(s, 4),
        "se": round(float(se), 4),
        "ci_lower": round(float(ci_lower), 4),
        "ci_upper": round(float(ci_upper), 4),
        "level": level,
    }


# ─── 4. 参数敏感性 ──────────────────────────


def param_sensitivity(base_sharpe: float, perturbed_sharpes: list, max_params: int = 50) -> dict:
    """随机参数扰动后的表现稳定性

    Parameters
    ----------
    base_sharpe : float
        基准参数下的 Sharpe
    perturbed_sharpes : list of float
        各扰动参数组合的 Sharpe

    Returns
    -------
    dict : {mean, std, min, max, sensitivity_ratio, verdict}
    """
    if len(perturbed_sharpes) < 3:
        return {"verdict": "insufficient_samples"}

    arr = np.array(perturbed_sharpes[:max_params])
    mean_p = float(np.mean(arr))
    std_p = float(np.std(arr, ddof=1))
    min_p = float(np.min(arr))
    max_p = float(np.max(arr))

    # 敏感性 = 扰动后的 Sharpe 均值偏离基准的比例
    if base_sharpe == 0:
        ratio = 0
    else:
        ratio = abs(mean_p - base_sharpe) / abs(base_sharpe)

    if ratio > 0.5:
        verdict = "highly_sensitive"
    elif ratio > 0.2:
        verdict = "moderate_sensitivity"
    else:
        verdict = "robust"

    return {
        "base_sharpe": round(base_sharpe, 4),
        "mean_perturbed": round(mean_p, 4),
        "std": round(std_p, 4),
        "min": round(min_p, 4),
        "max": round(max_p, 4),
        "sensitivity_ratio": round(ratio, 4),
        "verdict": verdict,
    }


# ─── 综合 ──────────────────────────────────


def full_overfit_assessment(is_returns: np.ndarray, oos_returns: np.ndarray,
                            fold_results: list = None,
                            perturbed_sharpes: list = None) -> dict:
    """综合过拟合风险评估

    整合夏普比衰减 + 交叉验证 + 标准误 + 参数敏感性
    """
    assessment = {"has_overfit_risk": False, "details": {}, "verdict": "unknown"}

    # 1. 夏普比衰减
    decay = sharpe_decay(is_returns, oos_returns)
    assessment["details"]["sharpe_decay"] = decay

    # 2. 交叉验证
    if fold_results:
        cv = cv_sharpe_distribution(fold_results)
        assessment["details"]["cv_distribution"] = cv

    # 3. 标准误
    ci = sharpe_confidence_interval(oos_returns)
    assessment["details"]["sharpe_ci"] = ci

    # 4. 参数敏感性
    if perturbed_sharpes:
        ps = param_sensitivity(ci["sharpe"], perturbed_sharpes)
        assessment["details"]["param_sensitivity"] = ps

    # 综合判定
    risk_signals = 0
    if decay.get("verdict") == "severe_overfit":
        risk_signals += 2
    elif decay.get("verdict") == "overfit_warning":
        risk_signals += 1

    if assessment["details"].get("cv_distribution", {}).get("verdict") == "unstable":
        risk_signals += 1

    if assessment["details"].get("param_sensitivity", {}).get("verdict") == "highly_sensitive":
        risk_signals += 1

    if risk_signals >= 2:
        assessment["has_overfit_risk"] = True
        assessment["verdict"] = "high_overfit_risk"
    elif risk_signals == 1:
        assessment["verdict"] = "caution"
    else:
        assessment["verdict"] = "low_risk"

    return assessment
