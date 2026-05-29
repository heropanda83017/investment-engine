#!/usr/bin/env python3
"""
Alpha191 精选因子模块 — 10 个短周期价量因子

基于国泰君安短周期价量特征多因子选股体系（WorldQuant 101 扩展版）。
从 191 个因子中精选 10 个与 blackhorse-ai 现有 6 因子正交性强的因子，
补充量价背离、波动结构、统计动量等维度。

使用方式：
    from alpha191_factors import compute_all_alpha191
    result = compute_all_alpha191(df)
    # result = {"score": total_score(0-100), "details": {...}}

依赖：pandas, numpy, config_loader
"""

import sys, os, logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from config_loader import CFG as CONFIG

log = logging.getLogger("alpha191")


# ==================== 公用辅助函数 ====================

def tsmax(s: np.ndarray, n: int) -> np.ndarray:
    """滚动窗口最大值，前 n-1 个位置用当前累计最大值填充"""
    result = pd.Series(s).rolling(n, min_periods=1).max().values
    return result


def tsmin(s: np.ndarray, n: int) -> np.ndarray:
    """滚动窗口最小值"""
    result = pd.Series(s).rolling(n, min_periods=1).min().values
    return result


def tsrank(s: np.ndarray, n: int) -> np.ndarray:
    """
    序列 s 末位值在过去 n 天的顺序排位 (percentile 0~1)。
    若窗口内当前值是最大值则返回 1.0，最小值返回 0.0。
    """
    result = np.full_like(s, 0.5, dtype=float)
    for i in range(n - 1, len(s)):
        window = s[i - n + 1 : i + 1]
        # 去掉 nan 后再排位
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            continue
        rank = np.sum(valid <= s[i]) - 1  # 当前值在窗口内排第几（0-based）
        result[i] = rank / max(len(valid) - 1, 1)
    return result


def decaylinear(s: np.ndarray, d: int) -> np.ndarray:
    """
    线性衰减加权移动平均。
    权重: d, d-1, ..., 1（最后一天权重最大），归一化和为 1。
    """
    weights = np.arange(d, 0, -1, dtype=float)
    weights /= weights.sum()
    result = np.full_like(s, np.nan, dtype=float)
    for i in range(d - 1, len(s)):
        segment = s[i - d + 1 : i + 1]
        if np.any(np.isnan(segment)):
            continue
        result[i] = np.dot(segment, weights)
    return result


def sma(s: np.ndarray, n: int, m: float) -> np.ndarray:
    """
    扩展移动平均: y[i+1] = (s[i]*m + y[i]*(n-m)) / n
    首值 = s[0]
    """
    result = np.full_like(s, np.nan, dtype=float)
    if len(s) == 0:
        return result
    result[0] = s[0]
    for i in range(1, len(s)):
        if np.isnan(result[i - 1]):
            result[i] = s[i]
        else:
            result[i] = (s[i - 1] * m + result[i - 1] * (n - m)) / n
    return result


def delta(s: np.ndarray, n: int) -> np.ndarray:
    """s[i] - s[i-n]，前 n 个位置填 0"""
    result = np.full_like(s, 0.0, dtype=float)
    if len(s) > n:
        result[n:] = s[n:] - s[:-n]
    return result


def rank(s: np.ndarray) -> np.ndarray:
    """向量 A 升序排序百分比 (0~1)"""
    valid = ~np.isnan(s)
    if not valid.any():
        return np.full_like(s, 0.5, dtype=float)
    result = np.full_like(s, 0.5, dtype=float)
    # 逐列处理
    result[valid] = (pd.Series(s[valid]).rank(pct=True).values)
    return result


def corr_pair(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    """
    序列 a, b 过去 n 天相关系数。
    返回与输入等长的数组，前 n-1 个为 nan。
    """
    result = np.full_like(a, np.nan, dtype=float)
    for i in range(n - 1, len(a)):
        window_a = a[i - n + 1 : i + 1]
        window_b = b[i - n + 1 : i + 1]
        valid = ~(np.isnan(window_a) | np.isnan(window_b))
        if valid.sum() < 3:
            continue
        corr = np.corrcoef(window_a[valid], window_b[valid])
        result[i] = corr[0, 1] if corr.shape == (2, 2) else 0.0
    return result


# ==================== 评分辅助 ====================

def score_by_boundaries(value, boundaries, scores, direction="gt"):
    """同 build_features.py 中的评分函数"""
    for i, b in enumerate(boundaries):
        is_last = (i == len(boundaries) - 1)
        if direction == "gt":
            if value > b or (is_last and value == b):
                return scores[i] if i < len(scores) else 0
        elif direction == "lt":
            if value < b or (is_last and value == b):
                return scores[i] if i < len(scores) else 0
    return 0


def _safe_last(arr: np.ndarray) -> float:
    """取数组最后一位有效值"""
    if len(arr) == 0:
        return 0.0
    val = arr[-1]
    return val if not np.isnan(val) else 0.0


# ==================== 10 个 Alpha191 因子 ====================

# ---------- Alpha #005: 量价背离 ----------
def alpha_005(df: pd.DataFrame) -> Dict:
    """(-1 * TSMAX(CORR(RANK(VOLUME), RANK(HIGH), 5), 3))
    量价背离信号。量价正相关越高则负分越大 → 警示回调。"""
    volume = df["成交量"].values.astype(float)
    high = df["最高"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_005", {})
    
    rk_vol = rank(volume)
    rk_high = rank(high)
    c = corr_pair(rk_vol, rk_high, 5)
    val = -1 * _safe_last(tsmax(c, 3))
    
    b = T.get("boundaries", [-0.3, -0.1, 0.1])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s, direction="lt")
    return {"score": score, "details": {"alpha_005": round(val, 4)}}


# ---------- Alpha #011: 价格位置加权量 ----------
def alpha_011(df: pd.DataFrame) -> Dict:
    """SUM(((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW)*VOLUME, 6)
    价格在当日区间的位置 × 成交量累计。数值大 = 价格靠近高位且量大。"""
    close = df["收盘"].values.astype(float)
    high = df["最高"].values.astype(float)
    low = df["最低"].values.astype(float)
    volume = df["成交量"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_011", {})
    
    ratio = ((close - low) - (high - close)) / (high - low + 1e-10)
    val = np.sum(ratio[-6:]) * np.mean(volume[-6:]) if len(ratio) >= 6 else 0.0
    
    b = T.get("boundaries", [0, -100, -500])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s)
    return {"score": score, "details": {"alpha_011": round(val, 2)}}


# ---------- Alpha #016: 量价相关性 ----------
def alpha_016(df: pd.DataFrame) -> Dict:
    """-1 * TSMAX(RANK(CORR(RANK(VOLUME), RANK(VWAP), 5)), 5)
    量价相关性——成交量与均价的正相关程度，越高说明上涨放量越健康。"""
    volume = df["成交量"].values.astype(float)
    vwap = df["均价"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_016", {})
    
    rk_vol = rank(volume)
    rk_vwap = rank(vwap)
    c = corr_pair(rk_vol, rk_vwap, 5)
    val = -1 * _safe_last(tsmax(rank(c), 5))
    
    b = T.get("boundaries", [-0.3, -0.5, -0.7])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s, direction="lt")
    return {"score": score, "details": {"alpha_016": round(val, 4)}}


# ---------- Alpha #028: 摆动指标 (类KDJ) ----------
def alpha_028(df: pd.DataFrame) -> Dict:
    """3*SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1)
       -2*SMA(SMA(...,3,1),3,1)
    类似 KDJ 的 K 值和 D 值的背离。"""
    close = df["收盘"].values.astype(float)
    high = df["最高"].values.astype(float)
    low = df["最低"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_028", {})
    
    h9 = tsmax(high, 9)
    l9 = tsmin(low, 9)
    raw = (close - l9) / (h9 - l9 + 1e-10) * 100
    k = sma(raw, 3, 1)
    d = sma(k, 3, 1)
    val = _safe_last(3 * k - 2 * d)
    
    b = T.get("boundaries", [60, 40, 20])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s)
    return {"score": score, "details": {"alpha_028": round(val, 2)}}


# ---------- Alpha #032: 高价量背离 ----------
def alpha_032(df: pd.DataFrame) -> Dict:
    """-1 * SUM(RANK(CORR(RANK(HIGH), RANK(VOLUME), 3)), 3)
    高价区域的量价背离。"""
    high = df["最高"].values.astype(float)
    volume = df["成交量"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_032", {})
    
    rk_h = rank(high)
    rk_v = rank(volume)
    c = corr_pair(rk_h, rk_v, 3)
    rk_c = rank(c)
    val = -1 * float(np.sum(rk_c[-3:])) if len(rk_c) >= 3 else 0.0
    
    b = T.get("boundaries", [-1.5, -0.8, -0.3])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s, direction="lt")
    return {"score": score, "details": {"alpha_032": round(val, 4)}}


# ---------- Alpha #040: 涨跌量比 ----------
def alpha_040(df: pd.DataFrame) -> Dict:
    """SUM(up_volume,26)/SUM(down_volume,26)*100
    过去 26 日上涨日成交量之和 / 下跌日成交量之和。"""
    close = df["收盘"].values.astype(float)
    volume = df["成交量"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_040", {})
    
    up_vol = np.where(close > np.roll(close, 1), volume, 0.0)
    down_vol = np.where(close <= np.roll(close, 1), volume, 0.0)
    up_vol[0] = 0
    down_vol[0] = 0
    
    sum_up = np.sum(up_vol[-26:]) if len(up_vol) >= 26 else np.sum(up_vol)
    sum_down = np.sum(down_vol[-26:]) if len(down_vol) >= 26 else np.sum(down_vol)
    val = (sum_up / max(sum_down, 1e-6)) * 100
    
    b = T.get("boundaries", [120, 100, 80])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s)
    return {"score": score, "details": {"alpha_040": round(val, 2)}}


# ---------- Alpha #044: 下跌量确认 + 均价变化 ----------
def alpha_044(df: pd.DataFrame) -> Dict:
    """TSRANK(DECAYLINEAR(CORR(LOW,MEAN(VOLUME,10),7),6),4)
       + TSRANK(DECAYLINEAR(DELTA(VWAP,3),10),15)
    下跌时成交量的确认 + 均价短期变化趋势。"""
    low = df["最低"].values.astype(float)
    close = df["收盘"].values.astype(float)
    volume = df["成交量"].values.astype(float)
    vwap = df["均价"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_044", {})
    
    # Part 1: LOW与VOLUME的相关性→DECAYLINEAR→TSRANK
    vol_ma10 = pd.Series(volume).rolling(10, min_periods=1).mean().values
    c = corr_pair(low, vol_ma10, 7)
    dl = decaylinear(c, 6)
    tr1 = _safe_last(tsrank(dl, 4))
    
    # Part 2: VWAP的3日变化→DECAYLINEAR→TSRANK
    dv = delta(vwap, 3)
    dl2 = decaylinear(dv, 10)
    tr2 = _safe_last(tsrank(dl2, 15))
    
    val = tr1 + tr2
    
    b = T.get("boundaries", [1.2, 0.8, 0.4])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s)
    return {"score": score, "details": {"alpha_044": round(val, 4)}}


# ---------- Alpha #047: 波动位置 ----------
def alpha_047(df: pd.DataFrame) -> Dict:
    """SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,9,1)
    价格在 6 日波动区间的位置，越高=越接近区间顶部。"""
    close = df["收盘"].values.astype(float)
    high = df["最高"].values.astype(float)
    low = df["最低"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_047", {})
    
    h6 = tsmax(high, 6)
    l6 = tsmin(low, 6)
    raw = (h6 - close) / (h6 - l6 + 1e-10) * 100  # 0=在顶部, 100=在底部
    val = _safe_last(sma(raw, 9, 1))
    
    # 接近顶部(值小)得分高
    b = T.get("boundaries", [30, 50, 70])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s, direction="lt")
    return {"score": score, "details": {"alpha_047": round(val, 2)}}


# ---------- Alpha #060: 量价强度(长周期) ----------
def alpha_060(df: pd.DataFrame) -> Dict:
    """SUM(((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW)*VOLUME, 20)
    与 Alpha#011 同逻辑，20 日窗口——衡量中长期量价强度。"""
    close = df["收盘"].values.astype(float)
    high = df["最高"].values.astype(float)
    low = df["最低"].values.astype(float)
    volume = df["成交量"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_060", {})
    
    ratio = ((close - low) - (high - close)) / (high - low + 1e-10)
    val = np.sum(ratio[-20:]) * np.mean(volume[-20:]) if len(ratio) >= 20 else 0.0
    
    b = T.get("boundaries", [0, -200, -1000])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s)
    return {"score": score, "details": {"alpha_060": round(val, 2)}}


# ---------- Alpha #101: 日内位置 ----------
def alpha_101(df: pd.DataFrame) -> Dict:
    """(CLOSE-OPEN)/(HIGH-LOW)
    收盘价在当日价格区间的位置。>0 = 收在均线上方。"""
    close = df["收盘"].values.astype(float)
    open_ = df["开盘"].values.astype(float)
    high = df["最高"].values.astype(float)
    low = df["最低"].values.astype(float)
    T = CONFIG.get("alpha191", {}).get("alpha_101", {})
    
    val = _safe_last((close - open_) / (high - low + 1e-10))
    
    b = T.get("boundaries", [0.3, 0, -0.3])
    s = T.get("scores", [10, 6, 2])
    score = score_by_boundaries(val, b, s)
    return {"score": score, "details": {"alpha_101": round(val, 4)}}


# ==================== 主编排函数 ====================

# 因子列表（执行顺序）
ALPHA_FACTORS = [
    ("alpha_005", alpha_005, 1.5),
    ("alpha_011", alpha_011, 1.0),
    ("alpha_016", alpha_016, 1.5),
    ("alpha_028", alpha_028, 1.0),
    ("alpha_032", alpha_032, 1.0),
    ("alpha_040", alpha_040, 1.0),
    ("alpha_044", alpha_044, 1.0),
    ("alpha_047", alpha_047, 1.0),
    ("alpha_060", alpha_060, 1.0),
    ("alpha_101", alpha_101, 1.0),
]
# 格式: (名称, 函数, 权重)


def compute_all_alpha191(df: pd.DataFrame) -> Dict:
    """
    计算所有 10 个 Alpha191 因子，返回综合评分 + 明细。
    
    参数:
        df: DataFrame 含 开盘/收盘/最高/最低/均价/成交量
    
    返回:
        {"score": int(0-100), "details": {name: {score, detail_value, weight}}}
    """
    if df.empty or len(df) < 30:
        return {"score": 0, "details": {}}
    
    # VWAP fallback: 如果"均价"列不存在，从OHLCV计算
    # 使用Typical Price(high+low+close)/3 + 累积VWAP回退
    if "均价" not in df.columns:
        if all(c in df.columns for c in ["最高","最低","收盘","成交量"]):
            log.warning("均价列缺失，使用Typical Price+累积VWAP回退")
            typical = (df["最高"].values.astype(float) + df["最低"].values.astype(float) + df["收盘"].values.astype(float)) / 3
            vol = df["成交量"].values.astype(float)
            cum_vp = 0.0; cum_v = 0.0
            vwap_list = []
            for tp, v in zip(typical, vol):
                cum_vp += tp * v; cum_v += v
                vwap_list.append(cum_vp / cum_v if cum_v > 0 else tp)
            df = df.copy()
            df["均价"] = vwap_list
        elif "收盘" in df.columns:
            log.warning("均价列缺失且无OHLC数据，使用收盘价回退")
            df = df.copy()
            df["均价"] = df["收盘"].values.astype(float)
    
    total_score = 0.0
    total_weight = 0.0
    details = {}
    errors = []
    
    for name, func, weight in ALPHA_FACTORS:
        try:
            result = func(df)
            factor_score = result["score"]
            total_score += factor_score * weight
            total_weight += weight
            details[name] = {
                "score": factor_score,
                "value": result["details"].get(name, "N/A"),
                "weight": weight,
            }
        except Exception as e:
            log.warning(f"Alpha191 {name} 计算失败: {e}")
            errors.append(name)
    
    # 归一化到 0-100
    if total_weight > 0:
        final_score = min(100, int(total_score / total_weight * 10))
    else:
        final_score = 0
    
    result = {
        "score": final_score,
        "details": details,
        "errors": errors,
        "factors_count": len(details),
    }
    
    return result


# ==================== CLI 测试入口 ====================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 生成模拟数据测试
    np.random.seed(42)
    n = 100
    test_df = pd.DataFrame({
        "开盘": np.random.randn(n).cumsum() + 100,
        "收盘": np.random.randn(n).cumsum() + 100,
        "最高": np.random.randn(n).cumsum() + 102,
        "最低": np.random.randn(n).cumsum() + 98,
        "均价": (test_df["最高"] + test_df["最低"] + test_df["收盘"]) / 3,
        "成交量": np.abs(np.random.randn(n) * 1e6 + 1e7),
        "成交额": np.abs(np.random.randn(n) * 1e8 + 1e9),
        "涨跌幅": np.random.randn(n) * 0.02,
    })
    # 保证 high>=close>=low
    test_df["最高"] = test_df[["最高", "收盘", "开盘"]].max(axis=1)
    test_df["最低"] = test_df[["最低", "收盘", "开盘"]].min(axis=1)
    
    result = compute_all_alpha191(test_df)
    print(f"Alpha191 综合评分: {result['score']}/100")
    print(f"因子数: {result['factors_count']}")
    for name, det in result["details"].items():
        print(f"  {name:12s} → {det['score']:2d}分 (值={det['value']}, 权重={det['weight']})")
    if result["errors"]:
        print(f"错误因子: {result['errors']}")
