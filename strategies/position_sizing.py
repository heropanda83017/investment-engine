#!/usr/bin/env python3
"""仓位管理模块 — 信号强度 → 仓位比例映射 + 风控约束

投资哲学: 单票≤15% · 分散3-5行业 · 安全边际

使用方式:
    from position_sizing import calculate_position, validate_portfolio
    pos = calculate_position(signal_strength=0.65, cash_ratio=0.5)
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

log = logging.getLogger("position_sizing")

# 仓位映射锚点: {信号强度: 目标仓位比例}
# REVIEW 确认: 映射表输出的是"目标仓位比例"，单票≤15%是组合层面的上限约束
# 两者不冲突——映射表决定"想买多少"，风控决定"最多能买多少"
POSITION_ANCHORS: Dict[float, float] = {
    # 映射表定义"理想仓位比例"，单票≤15%是最终硬约束
    # 插值后的值会被 SINGLE_STOCK_CAP 截断
    # 信号(1.0)→20%被截断到15%；信号(0.7)→13%在限内
    0.0: 0.00,    # 无信号 → 不持仓
    0.3: 0.05,    # 弱信号 → 5% (低于上限)
    0.5: 0.10,    # 中等信号 → 10%
    0.7: 0.13,    # 强信号 → 13% (接近上限)
    1.0: 0.20,    # 极强信号 → 20% (会被上限截断到15%)
}

# 风控约束
SINGLE_STOCK_CAP = 0.15       # 单只股票占整个组合上限 15%
MAX_INDUSTRY_EXPOSURE = 0.30  # 单行业上限 30%
MIN_POSITION = 0.0            # 最小仓位
MAX_TOTAL_POSITION = 1.0      # 满仓


def _linear_interpolate(intensity: float) -> float:
    """分段线性插值: 将[0,1]信号强度映射到仓位比例"""
    points = sorted(POSITION_ANCHORS.items())
    
    # 边界处理
    if intensity <= points[0][0]:
        return points[0][1]
    if intensity >= points[-1][0]:
        return points[-1][1]
    
    # 找到所在区间做线性插值
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        if x1 <= intensity <= x2:
            t = (intensity - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    
    return 0.0


def calculate_position(
    signal_strength: float,
    cash_ratio: float = 1.0,
    existing_position_ratio: float = 0.0,
) -> Dict:
    """计算单只股票的建仓/加仓/减仓建议

    参数:
        signal_strength: 信号强度 [0, 1]
        cash_ratio: 当前可用现金比例 [0, 1]
        existing_position_ratio: 已有仓位比例

    返回:
        {"target_pct": 目标仓位, "action": "BUY"/"ADD"/"HOLD"/"REDUCE",
         "signal_strength": 原始信号, "capped": 是否被上限截断,
         "cash_used": 本次操作使用的现金比例}
    """
    if not (0.0 <= signal_strength <= 1.0):
        log.warning(f"信号强度越界: {signal_strength}，已截断到[0,1]")
        signal_strength = max(0.0, min(1.0, signal_strength))
    if not (0.0 <= cash_ratio <= 1.0):
        log.warning(f"现金比例越界: {cash_ratio}，已截断到[0,1]")
        cash_ratio = max(0.0, min(1.0, cash_ratio))
    if not (0.0 <= existing_position_ratio <= 1.0):
        log.warning(f"已有仓位越界: {existing_position_ratio}，已截断到[0,1]")
        existing_position_ratio = max(0.0, min(1.0, existing_position_ratio))
    
    # Step 1: 信号强度 → 理想仓位 (通过锚点线性插值)
    target = _linear_interpolate(signal_strength)
    
    # Step 2: 单票上限约束
    capped = target >= SINGLE_STOCK_CAP
    target = min(target, SINGLE_STOCK_CAP)
    
    # Step 3: 计算与现有仓位的差值，决定操作
    diff = target - existing_position_ratio
    tolerance = 0.02  # 2% 阈值避免频繁交易
    
    if diff > tolerance:
        # 需要加仓 → 现金约束仅在此场景生效
        if cash_ratio < 1.0:
            target = existing_position_ratio + min(diff, cash_ratio)
            target = min(target, SINGLE_STOCK_CAP)
        # 如果现金用完无法加仓，降级为HOLD
        if target <= existing_position_ratio + 0.001:
            action = "HOLD"
        else:
            action = "BUY" if existing_position_ratio == 0 else "ADD"
    elif diff < -tolerance:
        # 需要减仓 → 不受现金约束
        action = "REDUCE"
        target = round(max(target, 0.0), 4)
    else:
        # 无需操作
        action = "HOLD"
        target = existing_position_ratio

    # 重算capped + cash_used（在现金约束之后）
    capped = target >= SINGLE_STOCK_CAP
    actual_delta = target - existing_position_ratio

    return {
        "target_pct": round(target, 4),
        "action": action,
        "signal_strength": round(signal_strength, 4),
        "capped": capped,
        "cash_used": round(actual_delta if actual_delta > 0 else 0, 4),
    }


def validate_portfolio(positions: List[Dict]) -> Dict:
    """验证整个组合的风控约束

    参数:
        positions: [{"code": str, "weight": float, "industry": str}, ...]

    返回:
        {"passed": bool, "warnings": [str], "violations": [str]}
    """
    result = {"passed": True, "warnings": [], "violations": []}
    
    if not positions:
        result["warnings"].append("持仓为空")
        return result
    
    total_weight = sum(p.get("weight", 0) for p in positions)
    
    # 1. 总仓位检查
    if total_weight > MAX_TOTAL_POSITION + 0.01:
        result["violations"].append(f"总仓位 {total_weight:.1%} 超过上限 {MAX_TOTAL_POSITION:.0%}")
        result["passed"] = False
    
    # 2. 单票仓位检查
    for p in positions:
        w = p.get("weight", 0)
        if w > SINGLE_STOCK_CAP + 0.01:
            result["violations"].append(
                f"{p.get('code', '?')} 仓位 {w:.1%} 超过单票上限 {SINGLE_STOCK_CAP:.0%}"
            )
            result["passed"] = False
    
    # 3. 行业分散度检查
    industry_weights: Dict[str, float] = {}
    for p in positions:
        ind = p.get("industry", "未知")
        industry_weights[ind] = industry_weights.get(ind, 0) + p.get("weight", 0)
    
    for ind, w in industry_weights.items():
        if w > MAX_INDUSTRY_EXPOSURE + 0.01:
            result["violations"].append(
                f"行业 {ind} 总仓位 {w:.1%} 超过上限 {MAX_INDUSTRY_EXPOSURE:.0%}"
            )
            result["passed"] = False
    
    # 4. 行业分散度警告（少于3个行业）
    if len(industry_weights) < 3:
        result["warnings"].append(f"仅覆盖 {len(industry_weights)} 个行业，建议分散到3-5个行业")
    
    return result


def get_position_summary(positions: List[Dict]) -> str:
    """生成仓位摘要文本"""
    total = sum(p.get("weight", 0) for p in positions)
    n = len(positions)
    
    industries = set()
    for p in positions:
        ind = p.get("industry", "未知")
        if ind:
            industries.add(ind)
    
    return (
        f"持仓 {n} 只, 总仓位 {total:.1%}, "
        f"覆盖 {len(industries)} 个行业 | "
        f"单票上限 {SINGLE_STOCK_CAP:.0%}, 单行业上限 {MAX_INDUSTRY_EXPOSURE:.0%}"
    )


# ── 凯利公式仓位（2026-05-27 新增）──

DEFAULT_FRACTION = 0.25  # 半凯利（保守）


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float,
                   fraction_kelly: float = DEFAULT_FRACTION) -> float:
    """凯利公式计算仓位比例

    Parameters
    ----------
    win_rate : float
        胜率 (0~1)
    avg_win : float
        平均盈利率 (正数)
    avg_loss : float
        平均亏损率 (正数，函数内部取绝对值)
    fraction_kelly : float
        凯利系数，默认0.25（半凯利极度保守）

    Returns
    -------
    float : 建议仓位比例 [0, 1]
    """
    if win_rate <= 0 or win_rate >= 1:
        return fraction_kelly * 0.5
    if avg_loss <= 0:
        return fraction_kelly * 0.3

    b = avg_win / avg_loss  # 赔率
    p = win_rate
    q = 1 - p

    if b <= 0:
        return 0.0

    kelly = (b * p - q) / b  # 标准凯利
    kelly = max(0, min(kelly, 1))  # 截断到 [0, 1]

    return round(kelly * fraction_kelly, 4)


def volatility_adjusted_position(base_pct: float, atr_ratio: float,
                                 target_vol: float = 0.15) -> float:
    """波动率调整仓位

    base_pct * (target_vol / annualized_vol)
    高波动时降低仓位，低波动时增加仓位

    Parameters
    ----------
    base_pct : float
        基础仓位比例
    atr_ratio : float
        ATR/Price 比率（日波动率估计）
    target_vol : float
        目标年化波动率，默认 15%

    Returns
    -------
    float : 调整后仓位比例
    """
    if atr_ratio <= 0:
        return base_pct
    annualized_vol = atr_ratio * np.sqrt(252)
    if annualized_vol <= 0:
        return base_pct
    adj = base_pct * (target_vol / annualized_vol)
    return round(max(0, min(adj, 1)), 4)


def calculate_position_combined(score: float, confidence: float,
                                 win_rate: float = None, avg_win: float = None,
                                 avg_loss: float = None,
                                 atr_ratio: float = None,
                                 max_position: float = 0.15) -> float:
    """综合仓位计算（凯利 + 波动率调整 + 信号强度）

    优先级: 信号强度基准 → 凯利校准 → 波动率调整 → 上限截断

    Parameters
    ----------
    score : float
        综合信号评分 [-1, 1]
    confidence : float
        信号置信度 [0, 1]
    win_rate, avg_win, avg_loss : float, optional
        凯利参数，传入则启用凯利调整
    atr_ratio : float, optional
        波动率调整参数，传入则启用波动率调整
    max_position : float
        最大仓位上限

    Returns
    -------
    float : 建议仓位比例
    """
    # 1. 信号强度基准
    if score <= 0:
        return 0.0
    position = score * confidence * max_position

    # 2. 凯利校准
    if all(v is not None for v in [win_rate, avg_win, avg_loss]):
        kelly = kelly_fraction(win_rate, avg_win, avg_loss)
        position = position * (1 + kelly) / 2

    # 3. 波动率调整
    if atr_ratio is not None:
        position = volatility_adjusted_position(position, atr_ratio)

    # 4. 上限截断
    return round(min(position, max_position), 4)
