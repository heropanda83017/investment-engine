
"""ic_analyzer.py — IC衰减曲线 + 滚动IC + 因子稳定性评分
设计决策: ICIR加权, 3档窗口[60,120,240], 冷启动保护
"""
import numpy as np
import pandas as pd
try:
    from scipy.stats import spearmanr
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def calc_rank_ic(factor_vals: pd.Series, forward_ret: pd.Series) -> float:
    """计算单期 RankIC（Spearman相关系数）"""
    valid = factor_vals.dropna().index.intersection(forward_ret.dropna().index)
    if len(valid) < 10:
        return 0.0
    if _HAS_SCIPY:
        rho, _ = spearmanr(factor_vals.loc[valid], forward_ret.loc[valid])
        return rho if not np.isnan(rho) else 0.0
    else:
        # 无 scipy 时用 pandas rank corr
        return factor_vals.loc[valid].corr(forward_ret.loc[valid], method='spearman') or 0.0


def calc_icir(ic_series: pd.Series) -> float:
    """计算 ICIR = mean(IC) / std(IC)"""
    if len(ic_series) < 5 or ic_series.std() == 0:
        return 0.0
    return ic_series.mean() / ic_series.std()


def calc_ic_series(factor_df: pd.DataFrame, ret_df: pd.DataFrame) -> pd.Series:
    """计算因子在时间序列上的每日 IC"""
    common_dates = factor_df.index.intersection(ret_df.index)
    ic_list = []
    for date in common_dates:
        ic = calc_rank_ic(factor_df.loc[date], ret_df.loc[date])
        ic_list.append(ic)
    return pd.Series(ic_list, index=common_dates, name="rank_ic")


def rolling_ic(ic_series: pd.Series, windows: list = None) -> pd.DataFrame:
    """滚动窗口IC统计

    Parameters
    ----------
    ic_series : pd.Series
        历史 IC 序列
    windows : list
        窗口大小列表，默认 [60, 120, 240]

    Returns
    -------
    pd.DataFrame : columns = {window}d_mean, {window}d_icir, {window}d_stability
    """
    if windows is None:
        windows = [60, 120, 240]
    result = {}
    for w in windows:
        if len(ic_series) < w:
            continue
        roll = ic_series.rolling(w, min_periods=max(20, w // 4))
        result[f"{w}d_mean"] = roll.mean()
        result[f"{w}d_std"] = roll.std()
        # ICIR = mean / std
        result[f"{w}d_icir"] = result[f"{w}d_mean"] / result[f"{w}d_std"].replace(0, np.nan)
        # 稳定性评分 = ICIR * sign_direction * cold_start
        n_samples = roll.count()
        result[f"{w}d_stability"] = (
            result[f"{w}d_icir"]
            * np.sign(result[f"{w}d_mean"]).clip(lower=0)  # 只取正向
            * np.minimum(1.0, n_samples / max(w, 1))
        )
    return pd.DataFrame(result)


def factor_stability_score(ic_series: pd.Series, window: int = 120) -> float:
    """单因子稳定性评分 [-1.0, 1.0]

    公式: ICIR_120d * sign(RankIC_120d_positive_ratio) * cold_start_penalty
    """
    if len(ic_series) < max(20, window // 4):
        return 0.0

    recent = ic_series.iloc[-min(window, len(ic_series)):]
    icir = calc_icir(recent)

    # 方向一致性: 60%以上同向才给正分
    positive_ratio = (recent > 0).mean()
    direction = 1.0 if positive_ratio >= 0.6 else (-1.0 if positive_ratio <= 0.4 else 0.0)

    # 冷启动保护
    cold = min(1.0, len(recent) / window)

    score = icir * direction * cold
    return max(-1.0, min(1.0, score))


def ic_decay_curve(ic_series: pd.Series, max_lag: int = 20) -> pd.Series:
    """IC衰减曲线：计算 lag 1..N 的 IC

    衡量因子预测力的衰减速度，衰减越快说明因子越短期
    """
    decay = []
    for lag in range(1, max_lag + 1):
        shifted = ic_series.shift(lag)
        aligned = pd.concat([ic_series, shifted], axis=1).dropna()
        if len(aligned) < 10:
            decay.append(0.0)
        else:
            rho, _ = spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
            decay.append(rho if not np.isnan(rho) else 0.0)
    return pd.Series(decay, index=range(1, max_lag + 1), name="ic_decay")


def icir_weight(factors_ic: dict) -> dict:
    """ICIR加权：根据各因子近期的 ICIR 计算动态权重

    Parameters
    ----------
    factors_ic : dict
        {factor_name: ic_series}

    Returns
    -------
    dict : {factor_name: weight}
        权重归一化到 [0, 1]，负 ICIR 因子权重设为 0
    """
    icirs = {}
    for name, series in factors_ic.items():
        ir = calc_icir(series)
        icirs[name] = max(0.0, ir)  # 负ICIR -> 0

    total = sum(icirs.values())
    if total == 0:
        # 退化为等权
        n = len(factors_ic)
        return {name: 1.0 / n for name in factors_ic}

    return {name: val / total for name, val in icirs.items()}
