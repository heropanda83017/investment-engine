"""framework_scorer.py — 分析框架评分标准化

将 11 个框架的输出统一为标准化评分，支持加权聚合和冲突检测。

评分标准: [-1.0, 1.0]
  > 0.3 = 看多信号
  < -0.3 = 看空信号
  中间 = 中性
"""
import numpy as np

# ─── 各框架评分函数 ─────────────────────────

def _moat_score(result: dict) -> float:
    """护城河框架 → 评分"""
    if not result:
        return 0.0
    score = result.get("total_score", 0) if isinstance(result.get("total_score"), (int, float)) else 0
    return max(-1.0, min(1.0, score / 5.0))  # 归一化到 [-1,1]

def _cycle_score(result: dict) -> float:
    """周期框架 → 评分"""
    if not result:
        return 0.0
    phase = result.get("phase", "")
    mapping = {"扩张": 0.5, "繁荣": 0.3, "衰退": -0.5, "萧条": -0.8, "复苏": 0.2}
    return mapping.get(phase, 0.0)

def _forensic_score(result: dict) -> float:
    """财务排雷框架 → 评分（越高越安全）"""
    if not result:
        return 0.0
    flags = result.get("red_flags", [])
    score = 1.0 - len(flags) * 0.2
    return max(-1.0, min(1.0, score))

def _industry_score(result: dict) -> float:
    """行业分析框架 → 评分"""
    if not result:
        return 0.0
    stage = result.get("stage", "")
    mapping = {"成长早期": 0.6, "成长中期": 0.4, "成熟期": 0.1, "衰退期": -0.5, "淘汰赛": -0.3}
    return mapping.get(stage, 0.0)

def _behavioral_score(result: dict) -> float:
    """行为金融框架 → 评分"""
    if not result:
        return 0.0
    bias_count = len(result.get("biases", []))
    sentiment = result.get("sentiment", "")
    score = -bias_count * 0.15  # 偏误越多越差
    if sentiment == "恐慌":
        score += 0.3  # 逆向买入机会
    elif sentiment == "狂热":
        score -= 0.3  # 逆向卖出信号
    return max(-1.0, min(1.0, score))

def _export_control_score(result: dict) -> float:
    """出口管制框架 → 评分"""
    if not result:
        return 0.0
    risk = result.get("risk_level", "")
    mapping = {"低": 0.3, "中": 0.0, "高": -0.5}
    return mapping.get(risk, 0.0)

def _troubled_score(result: dict) -> float:
    """困境反转框架 → 评分"""
    if not result:
        return 0.0
    category = result.get("category", "")
    mapping = {"周期困境": 0.2, "管理困境": -0.2, "结构困境": -0.5}
    return mapping.get(category, 0.0)

def _ai_compute_score(result: dict) -> float:
    """AI算力框架 → 评分"""
    if not result:
        return 0.0
    stage = result.get("stage", "")
    mapping = {"训练主导": 0.3, "推理转换": 0.5, "推理主导": 0.6}
    return mapping.get(stage, 0.0)

def _reverse_score(result: dict) -> float:
    """逆向思维框架 → 评分"""
    if not result:
        return 0.0
    consensus = result.get("consensus", "")
    if consensus == "过度悲观":
        return 0.5
    elif consensus == "过度乐观":
        return -0.5
    return 0.0

def _institutional_score(result: dict) -> float:
    """机构持仓框架 → 评分"""
    if not result:
        return 0.0
    change = result.get("institutional_change", "")
    mapping = {"大幅增持": 0.5, "小幅增持": 0.2, "不变": 0.0, "小幅减持": -0.2, "大幅减持": -0.5}
    return mapping.get(change, 0.0)

def _local_finance_score(result: dict) -> float:
    """地方财政框架 → 评分"""
    if not result:
        return 0.0
    health = result.get("fiscal_health", "")
    mapping = {"健康": 0.3, "关注": 0.0, "风险": -0.4}
    return mapping.get(health, 0.0)

# ─── 框架注册表 ──────────────────────────────

def _market_state_score(result: dict) -> float:
    """市场状态框架 → 评分"""
    if not result:
        return 0.0
    state = result.get("state", "")
    mapping = {"牛市": 0.4, "过渡": 0.1, "震荡": 0.0, "熊市": -0.4}
    return mapping.get(state, 0.0)

def _macro_causal_score(result: dict) -> float:
    """宏观因果框架 → 评分"""
    if not result:
        return 0.0
    credit = result.get("credit_cycle", "")
    debt = result.get("debt_level", "")
    credit_m = {"扩张": 0.3, "中性": 0.0, "收缩": -0.3}
    debt_m = {"低": 0.2, "中等": 0.0, "高": -0.3, "极高": -0.5}
    score = credit_m.get(credit, 0) + debt_m.get(debt, 0)
    return max(-1.0, min(1.0, score))

def _fund_evaluation_score(result: dict) -> float:
    """基金评价框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

def _alternative_score(result: dict) -> float:
    """另类投资框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

def _tariff_score(result: dict) -> float:
    """关税评估框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0





def _multi_discipline_score(result: dict) -> float:
    """多元思维框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

def _due_diligence_score(result: dict) -> float:
    """尽调流程框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

def _a_share_five_score(result: dict) -> float:
    """A股五步法框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

def _five_chapter_score(result: dict) -> float:
    """五章结构框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

def _volume_price_score(result: dict) -> float:
    """量价分析框架 → 评分"""
    return result.get("score", 0.0) if result else 0.0

FRAMEWORK_SCORERS = {
    "moat": ("护城河", _moat_score, 0.10),
    "cycle": ("周期定位", _cycle_score, 0.08),
    "forensic": ("财务排雷", _forensic_score, 0.08),
    "industry": ("行业分析", _industry_score, 0.07),
    "behavioral": ("行为金融", _behavioral_score, 0.05),
    "export_controls": ("出口管制", _export_control_score, 0.04),
    "troubled": ("困境反转", _troubled_score, 0.05),
    "ai_compute": ("AI算力", _ai_compute_score, 0.05),
    "reverse": ("逆向思维", _reverse_score, 0.04),
    "institutional": ("机构持仓", _institutional_score, 0.04),
    "local_finance": ("地方财政", _local_finance_score, 0.03),
    "market_state": ("市场状态", _market_state_score, 0.05),
    "macro_causal": ("宏观因果", _macro_causal_score, 0.04),
    "fund_evaluation": ("基金评价", _fund_evaluation_score, 0.03),
    "alternative": ("另类投资", _alternative_score, 0.03),
    "tariff": ("关税评估", _tariff_score, 0.04),
    "multi_discipline": ("多元思维", _multi_discipline_score, 0.04),
    "due_diligence": ("尽调流程", _due_diligence_score, 0.04),
    "a_share_five": ("A股五步法", _a_share_five_score, 0.04),
    "five_chapter": ("五章结构", _five_chapter_score, 0.03),
    "volume_price": ("量价分析", _volume_price_score, 0.05),
}
# key: (中文名, 评分函数, 权重)

def score_all_frameworks(framework_results: dict) -> dict:
    """对 11 个框架输出统一评分

    Parameters
    ----------
    framework_results : dict
        {framework_key: framework_output_dict}

    Returns
    -------
    dict : {scores: {name: score}, weighted: float, conflict: bool, details: str}
    """
    scores = {}
    weighted_sum = 0.0
    total_weight = 0.0
    active_count = 0

    for key, (cname, scorer, weight) in FRAMEWORK_SCORERS.items():
        result = framework_results.get(key, {})
        if result:
            score = scorer(result)
            scores[cname] = round(score, 4)
            weighted_sum += score * weight
            total_weight += weight
            active_count += 1

    if total_weight == 0 or active_count < 2:
        return {
            "scores": scores,
            "weighted_score": 0.0,
            "confidence": 0.0,
            "conflict": False,
            "num_active": active_count,
        }

    composite = weighted_sum / total_weight
    composite = max(-1.0, min(1.0, composite))

    # 冲突检测: 标准差分大 + 正负信号并存
    vals = list(scores.values())
    std = float(np.std(vals)) if len(vals) > 1 else 0
    has_positive = any(v > 0.3 for v in vals)
    has_negative = any(v < -0.3 for v in vals)
    conflict = std > 0.4 and has_positive and has_negative

    # 置信度: 活跃框架比例 + 冲突惩罚
    confidence = (active_count / len(FRAMEWORK_SCORERS)) * (0.8 if not conflict else 0.5)
    confidence = round(min(1.0, confidence), 4)

    # 信号解读
    if composite > 0.3:
        signal = "bullish"
    elif composite < -0.3:
        signal = "bearish"
    elif abs(composite) < 0.1:
        signal = "neutral"
    else:
        signal = "leaning"

    return {
        "scores": scores,
        "weighted_score": round(composite, 4),
        "confidence": confidence,
        "conflict": conflict,
        "num_active": active_count,
        "signal": signal,
    }

def format_score_summary(scored: dict) -> str:
    """评分结果 → 可读摘要"""
    if not scored or not scored.get("scores"):
        return "无框架评分数据"

    lines = [f"分析框架评分: {scored['weighted_score']} (置信度: {scored['confidence']})"]
    lines.append(f"信号: {scored.get('signal', 'unknown')} | 冲突: {'⚠️' if scored.get('conflict') else '✅'}")

    # 按评分排序
    sorted_scores = sorted(scored["scores"].items(), key=lambda x: x[1], reverse=True)
    for name, score in sorted_scores:
        tag = "🟢" if score > 0.3 else ("🔴" if score < -0.3 else "⚪")
        lines.append(f"  {tag} {name}: {score:.3f}")

    return "\\n".join(lines)
