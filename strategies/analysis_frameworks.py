#!/usr/bin/env python3
"""
分析框架因子化模块 — 将 17 个投资分析框架编码为可量化的选股规则

每个框架输出：
  - score: 0-10 分（可累加）
  - signals: 信号列表（买入/卖出/排除）
  - details: 因子明细（用于日报告警）

用法：
    from analysis_frameworks import apply_all_frameworks
    result = apply_all_frameworks(df, stock_name="贵州茅台", code="600519")
    # result = {"total_score": 68, "signals": [...], "details": {...}}
"""

import sys, os, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from config_loader import CFG as CONFIG

log = logging.getLogger("analysis_frameworks")

# ===================================================================
# 工具函数
# ===================================================================

def _safe(val, default=0.0):
    return val if not (val is None or (isinstance(val, float) and np.isnan(val))) else default

def _zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std()

def _percentile_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)

# ===================================================================
# 框架 1: 护城河评估 — 巴菲特四维护城河 + 另类资产三维
# ===================================================================

def framework_moat(balances: dict = None, income: dict = None) -> dict:
    """
    护城河评估：ROE稳定性 / 毛利率趋势 / 自由现金流 / 资产负债率
    另类资产三维：稀缺性 / 标准化程度 / 流动性
    
    输入：财务数据字典（可从 baostock/tushare 获取）
    返回：score 0-10, signals, details
    """
    if not balances and not income:
        return {"score": 5, "signals": [], "details": {"note": "无财务数据，默认中性"}}
    
    score = 5
    signals = []
    details = {}
    
    # 1. ROE 稳定性（连续3年ROE>15%为强护城河）
    roe_list = _safe(income.get("roe_ttm", [])) if income else []
    if isinstance(roe_list, (list, tuple)) and len(roe_list) >= 3:
        stable_roe = sum(1 for r in roe_list if r > 15)
        if stable_roe >= 3:
            score += 3
            signals.append({"type": "bullish", "source": "护城河", "msg": "连续3年ROE>15%，强护城河"})
        elif stable_roe >= 2:
            score += 1
        details["roe_stability"] = f"{stable_roe}/3"
    
    # 2. 毛利率趋势
    gross_list = _safe(income.get("gross_margin", [])) if income else []
    if isinstance(gross_list, (list, tuple)) and len(gross_list) >= 2:
        trend = gross_list[-1] - gross_list[0]
        if trend > 5:
            score += 2
            signals.append({"type": "bullish", "source": "护城河", "msg": "毛利率持续提升"})
        elif trend < -5:
            score -= 2
            signals.append({"type": "bearish", "source": "护城河", "msg": "毛利率持续下滑"})
        details["gross_trend"] = f"{trend:+.1f}%"
    
    # 3. 资产负债率
    debt_ratio = _safe(balances.get("debt_ratio", 50)) if balances else 50
    if debt_ratio < 30:
        score += 1  # 低负债=强护城河
    elif debt_ratio > 70:
        score -= 2  # 高负债=弱护城河
        signals.append({"type": "bearish", "source": "护城河", "msg": f"资产负债率{debt_ratio:.0f}%过高"})
    details["debt_ratio"] = debt_ratio
    
    score = max(0, min(10, score))
    return {"score": score, "signals": signals, "details": details}


# ===================================================================
# 框架 2: 周期定位 — 霍华德五周期温度计
# ===================================================================

def framework_cycle(market_data: dict = None) -> dict:
    """
    周期定位：宏观经济周期 / 企业盈利周期 / 市场情绪周期 / 信贷周期 / 库存周期
    
    输入：市场状态数据（PE分位数/社融增速/PMI）
    输出：当前周期位置及对应的仓位建议
    """
    score = 5
    signals = []
    details = {}
    
    market_data = market_data or {}
    pe_percentile = _safe(market_data.get("pe_percentile", 50))
    pmi = _safe(market_data.get("pmi", 50))
    credit_growth = _safe(market_data.get("credit_growth", 10))
    
    # PE 分位数（估值周期）
    if pe_percentile < 20:
        score += 2
        signals.append({"type": "bullish", "source": "周期", "msg": "PE处于历史低位，估值底"})
    elif pe_percentile > 80:
        score -= 2
        signals.append({"type": "bearish", "source": "周期", "msg": "PE处于历史高位，估值顶"})
    
    # PMI（经济周期）
    if pmi > 52:
        score += 1
        signals.append({"type": "bullish", "source": "周期", "msg": "PMI>52，经济扩张"})
    elif pmi < 48:
        score -= 1
        signals.append({"type": "bearish", "source": "周期", "msg": "PMI<48，经济收缩"})
    
    # 信贷周期
    if credit_growth > 12:
        score += 1
    elif credit_growth < 8:
        score -= 1
    
    details.update({
        "pe_percentile": pe_percentile,
        "pmi": pmi,
        "credit_growth": credit_growth,
    })
    
    score = max(0, min(10, score))
    position = "重仓" if score >= 7 else "轻仓" if score <= 3 else "中性"
    signals.append({"type": "info", "source": "周期", "msg": f"周期评分{score}/10，建议{position}"})
    
    return {"score": score, "signals": signals, "details": details, "position": position}


# ===================================================================
# 框架 3: 财务拆解 — 浑水七红旗
# ===================================================================

def framework_financial_forensic(financials: dict = None) -> dict:
    """
    财务拆解排雷（浑水式七红旗 + 15维度评分）
    输出 hard_reject（一票否决）或 score 扣分
    """
    score = 10  # 满分=无雷
    signals = []
    details = {}
    hard_reject = False
    
    if not financials:
        return {"score": 10, "signals": [], "details": {"note": "无财务数据，默认无雷"}}
    
    checks = {
        # 红旗1: 营收与现金流严重背离
        "cfo_ni_ratio": {
            "condition": lambda v: v is not None and v < 0.5,
            "penalty": -5,
            "msg": "经营现金流/净利润<0.5，利润质量差",
        },
        # 红旗2: 应收账款增速远超营收
        "ar_growth_vs_revenue": {
            "condition": lambda v: v is not None and v > 30,
            "penalty": -4,
            "msg": "应收账款增速>30%，回款风险",
        },
        # 红旗3: 毛利率异常高于同行
        "gross_margin_anomaly": {
            "condition": lambda v: v is not None and v > 20,
            "penalty": -3,
            "msg": "毛利率异常高于行业均值>20pp",
        },
        # 红旗4: 存货周转天数飙升
        "inventory_days_jump": {
            "condition": lambda v: v is not None and v > 50,
            "penalty": -3,
            "msg": "存货周转天数同比增>50%",
        },
        # 红旗5: 关联交易占比过高
        "related_party_ratio": {
            "condition": lambda v: v is not None and v > 30,
            "penalty": -4,
            "msg": "关联交易占比>30%",
        },
        # 红旗6: 大额商誉
        "goodwill_ratio": {
            "condition": lambda v: v is not None and v > 30,
            "penalty": -3,
            "msg": "商誉/净资产>30%",
        },
        # 红旗7: 频繁变更审计机构
        "auditor_change": {
            "condition": lambda v: v is not None and v >= 2,
            "penalty": -5,
            "msg": "近3年变更审计机构>=2次",
        },
    }
    
    for check_name, check in checks.items():
        val = financials.get(check_name)
        if check["condition"](val):
            score += check["penalty"]
            signals.append({"type": "bearish", "source": "财务排雷", "msg": check["msg"]})
            details[check_name] = val
            # 严重红旗触发 hard_reject
            if check["penalty"] <= -5:
                hard_reject = True
    
    score = max(0, score)
    result = {"score": score, "signals": signals, "details": details}
    if hard_reject:
        result["hard_reject"] = True
        result["reject_reason"] = "触发硬性排雷规则"
    return result


# ===================================================================
# 框架 4: 行业四步法 — PEST + 三维定位 + 产业链 + 资本市场
# ===================================================================

def framework_industry(
    industry_name: str = "",
    industry_data: dict = None,
) -> dict:
    """
    行业研究四步法因子化：
    1. PEST 宏观环境评分
    2. 三维行业定位（生命周期/竞争格局/政策导向）
    3. 产业链位置（上游/中游/下游，景气度传导）
    4. 资本市场表现（基金配置/估值分位数）
    """
    score = 5
    signals = []
    details = {"industry": industry_name}
    
    if not industry_data:
        return {"score": 5, "signals": [], "details": details}
    
    # 政策导向评分
    policy = _safe(industry_data.get("policy_score", 0))
    if policy > 0:
        score += min(policy, 3)
        signals.append({"type": "bullish", "source": "行业", "msg": f"政策支持力度评分{policy}"})
    elif policy < 0:
        score += max(policy, -3)
        signals.append({"type": "bearish", "source": "行业", "msg": f"政策收紧"})
    
    # 行业生命周期
    lifecycle = industry_data.get("lifecycle", "成熟")
    lifecycle_map = {"导入": 2, "成长": 3, "成熟": 0, "衰退": -3, "淘汰": -5}
    lc_score = lifecycle_map.get(lifecycle, 0)
    if lc_score:
        score += lc_score
    
    # 基金超配/低配
    fund_allocation = _safe(industry_data.get("fund_allocation", 0))
    if fund_allocation > 1.5:  # 超配50%以上
        score += 2
        signals.append({"type": "bullish", "source": "行业", "msg": "基金大幅超配，资金关注"})
    elif fund_allocation < 0.5:  # 低配50%以上
        score -= 1
    
    details.update({
        "lifecycle": lifecycle,
        "policy_score": policy,
        "fund_allocation": fund_allocation,
    })
    
    score = max(0, min(10, score))
    return {"score": score, "signals": signals, "details": details}


# ===================================================================
# 框架 5: 行为金融 — 五偏误自检 + 市场情绪
# ===================================================================

def framework_behavioral(
    price_data: pd.DataFrame = None,
    sentiment_score: float = 0.5,
) -> dict:
    """
    行为金融因子：从市场数据中识别非理性信号
    1. 过度反应（涨跌过头）
    2. 羊群效应（成交量异常放大）
    3. 锚定效应（股价在前期高点附近）
    4. 处置效应（放量滞涨=抛压）
    5. 确认偏误（利好出尽是利空）
    """
    score = 5
    signals = []
    details = {}
    
    if price_data is None or price_data.empty:
        return {"score": 5, "signals": [], "details": {"note": "无价格数据"}}
    
    close = price_data["收盘"].values if "收盘" in price_data.columns else []
    volume = price_data["成交量"].values if "成交量" in price_data.columns else []
    
    if len(close) < 20:
        return {"score": 5, "signals": [], "details": {"note": "数据不足"}}
    
    # 1. 过度反应：过去5日涨幅>20%有回调风险
    recent_gain = close[-1] / close[-6] - 1 if len(close) >= 6 else 0
    if recent_gain > 0.20:
        score -= 2
        signals.append({"type": "bearish", "source": "行为金融", "msg": f"5日涨幅{recent_gain*100:.0f}%，过度反应"})
    elif recent_gain < -0.15:
        score += 1  # 超卖反弹机会
        signals.append({"type": "bullish", "source": "行为金融", "msg": f"5日跌幅{recent_gain*100:.0f}%，超卖机会"})
    
    # 2. 羊群效应：成交量异常>5日均量的3倍
    if len(volume) >= 6:
        vol_ratio = volume[-1] / (np.mean(volume[-6:-1]) + 1e-6)
        if vol_ratio > 3:
            score -= 1
            signals.append({"type": "warning", "source": "行为金融", "msg": f"成交量异常放大{vol_ratio:.0f}x，警惕羊群效应"})
    
    # 3. 锚定效应：价格接近60日高点
    if len(close) >= 60:
        high_60 = np.max(close[-60:])
        dist_from_high = (high_60 - close[-1]) / high_60
        if dist_from_high < 0.03:
            score -= 1
            signals.append({"type": "warning", "source": "行为金融", "msg": "价格接近60日高点，锚定效应"})
    
    # 4. 情绪反转：sentiment 极端值
    if sentiment_score > 0.9:
        score -= 1
        signals.append({"type": "bearish", "source": "行为金融", "msg": "市场情绪极度乐观，警惕反转"})
    elif sentiment_score < 0.1:
        score += 1
        signals.append({"type": "bullish", "source": "行为金融", "msg": "市场情绪极度悲观，可能见底"})
    
    score = max(0, min(10, score))
    return {"score": score, "signals": signals, "details": {
        "recent_gain": f"{recent_gain*100:.1f}%",
        "vol_ratio": f"{vol_ratio:.1f}x" if len(volume) >= 6 else "N/A",
        "sentiment": sentiment_score,
    }}


# ===================================================================
# 框架 6: 出口管制传导链
# ===================================================================

def framework_export_controls(
    industry: str = "",
    supply_chain_data: dict = None,
) -> dict:
    """
    出口管制影响评估：制裁→短期冲击→国产替代
    关税三问：谁承担 / 转口可行 / 历史参照
    """
    score = 5
    signals = []
    details = {"industry": industry}
    
    if not supply_chain_data:
        return {"score": 5, "signals": [], "details": details}
    
    sanction_level = _safe(supply_chain_data.get("sanction_level", 0))
    domestic_alternative = _safe(supply_chain_data.get("domestic_alternative", 0.5))
    
    if sanction_level > 0:
        if domestic_alternative > 0.7:
            score += 2  # 国产替代能力强，利好
            signals.append({"type": "bullish", "source": "出口管制", "msg": "制裁利好国产替代龙头"})
        else:
            score -= sanction_level  # 制裁但无法替代，利空
            signals.append({"type": "bearish", "source": "出口管制", "msg": f"制裁等级{sanction_level}，替代率低"})
    
    details["sanction_level"] = sanction_level
    details["domestic_alternative"] = domestic_alternative
    
    score = max(0, min(10, score))
    return {"score": score, "signals": signals, "details": details}


# ===================================================================
# 框架 7: 失意公司周期判断
# ===================================================================

def framework_troubled_company(financials: dict = None) -> dict:
    """
    失意公司分类判断：周期失意 vs 结构失意 vs 管理失意
    周期失意→等待复苏（可买入）
    结构失意→业务转型（需观望）
    管理失意→治理问题（回避）
    """
    score = 5
    signals = []
    details = {}
    
    if not financials:
        return {"score": 5, "signals": [], "details": {"note": "无数据"}}
    
    revenue_decline = _safe(financials.get("revenue_decline", 0))
    margin_pressure = _safe(financials.get("margin_pressure", 0))
    management_change = _safe(financials.get("management_change", 0))
    
    if revenue_decline > 20 and margin_pressure < 5:
        # 营收降但毛利稳=周期失意
        score += 2
        details["type"] = "周期失意"
        signals.append({"type": "bullish", "source": "失意公司", "msg": "周期失意型，等待行业复苏"})
    elif revenue_decline > 20 and margin_pressure > 10:
        # 营收降+毛利降=结构失意
        score -= 2
        details["type"] = "结构失意"
        signals.append({"type": "bearish", "source": "失意公司", "msg": "结构失意型，业务承压"})
    elif management_change > 1:
        # 管理层频繁变动=管理失意
        score -= 3
        details["type"] = "管理失意"
        signals.append({"type": "bearish", "source": "失意公司", "msg": "管理失意型，回避"})
    
    score = max(0, min(10, score))
    return {"score": score, "signals": signals, "details": details}


# ===================================================================
# 框架 8-11: 轻量框架（快速评分）
# ===================================================================

def framework_ai_compute(stock_name: str = "", industry: str = "") -> dict:
    """AI算力结构判断：训练→推理转换 + 杰文斯悖论"""
    score = 5
    signals = []
    ai_related_keywords = ["算力", "芯片", "GPU", "服务器", "光模块", "PCB", "存储", "AI", "英伟达"]
    is_ai = any(kw in stock_name for kw in ai_related_keywords)
    if is_ai:
        score += 3
        signals.append({"type": "bullish", "source": "AI算力", "msg": "AI算力产业链标的，受益于推理需求爆发"})
    return {"score": max(0, min(10, score)), "signals": signals, "details": {"ai_related": is_ai}}

def framework_reverse_thinking(market_data: dict = None) -> dict:
    """芒格逆向思维：拥挤度检测"""
    score = 5
    signals = []
    crowding = _safe(market_data.get("fund_crowding", 0.5) if market_data else 0.5)
    if crowding > 0.8:
        score -= 2
        signals.append({"type": "bearish", "source": "逆向思维", "msg": "机构过度拥挤，逆向回避"})
    elif crowding < 0.2:
        score += 2
        signals.append({"type": "bullish", "source": "逆向思维", "msg": "机构低配，潜在机会"})
    return {"score": max(0, min(10, score)), "signals": signals, "details": {"crowding": crowding}}

def framework_institutional(holdings_data: dict = None) -> dict:
    """基金评价 → 机构持仓变化因子"""
    score = 5
    signals = []
    if holdings_data:
        change = _safe(holdings_data.get("fund_holding_change", 0))
        if change > 20:
            score += 2
            signals.append({"type": "bullish", "source": "机构持仓", "msg": f"机构增持{change:.0f}%"})
        elif change < -20:
            score -= 2
            signals.append({"type": "bearish", "source": "机构持仓", "msg": f"机构减持{change:.0f}%"})
    return {"score": max(0, min(10, score)), "signals": signals, "details": holdings_data or {}}

def framework_local_finance(region: str = "", finance_data: dict = None) -> dict:
    """地方财政与融资分析：城投四维 + 资金来源四象限"""
    score = 5
    signals = []
    if finance_data:
        debt_risk = _safe(finance_data.get("local_debt_risk", 0))
        if debt_risk > 0.7:
            score -= 2
            signals.append({"type": "bearish", "source": "地方财政", "msg": f"区域债务风险高"})
    return {"score": max(0, min(10, score)), "signals": signals, "details": finance_data or {}}


# ===================================================================
# 主编排：应用所有框架
# ===================================================================

ALL_FRAMEWORKS = [
    ("护城河评估", framework_moat),
    ("周期定位", framework_cycle),
    ("财务排雷", framework_financial_forensic),
    ("行业分析", framework_industry),
    ("行为金融", framework_behavioral),
    ("出口管制", framework_export_controls),
    ("失意公司", framework_troubled_company),
    ("AI算力", framework_ai_compute),
    ("逆向思维", framework_reverse_thinking),
    ("机构持仓", framework_institutional),
    ("地方财政", framework_local_finance),
]


def apply_all_frameworks(
    df: pd.DataFrame = None,
    stock_name: str = "",
    code: str = "",
    industry: str = "",
    financials: dict = None,
    market_data: dict = None,
    industry_data: dict = None,
    supply_chain_data: dict = None,
    holdings_data: dict = None,
    finance_data: dict = None,
    sentiment_score: float = 0.5,
) -> dict:
    """
    对所有可用框架评分，返回综合结果。
    
    参数：
        df: K线 DataFrame（用于行为金融因子）
        stock_name / code / industry: 股票基本信息
        financials: 财务数据字典（护城河/财务排雷/失意公司）
        market_data: 市场状态（PE/PMI/社融）
        industry_data: 行业数据（政策/生命周期/基金配置）
        supply_chain_data: 供应链数据（制裁/替代率）
        holdings_data: 机构持仓变化
        sentiment_score: 市场情绪 0-1
    
    返回：
        {"total_score": 0-100, "signal_summary": [...], 
         "framework_scores": {...}, "hard_reject": bool}
    """
    frameworks_input = {
        "framework_moat": {"balances": financials, "income": financials},
        "framework_cycle": {"market_data": market_data},
        "framework_financial_forensic": {"financials": financials},
        "framework_industry": {"industry_name": industry, "industry_data": industry_data},
        "framework_behavioral": {"price_data": df, "sentiment_score": sentiment_score},
        "framework_export_controls": {"industry": industry, "supply_chain_data": supply_chain_data},
        "framework_troubled_company": {"financials": financials},
        "framework_ai_compute": {"stock_name": stock_name, "industry": industry},
        "framework_reverse_thinking": {"market_data": market_data},
        "framework_institutional": {"holdings_data": holdings_data},
        "framework_local_finance": {"region": "", "finance_data": finance_data},
    }
    
    total_score = 0
    all_signals = []
    framework_details = {}
    hard_reject = False
    active_count = 0
    
    total_weight = 11  # 11 frameworks
    
    for name, func in ALL_FRAMEWORKS:
        try:
            kwargs = frameworks_input.get(func.__name__, {})
            result = func(**kwargs)
            fs = result.get("score", 5)
            total_score += fs
            active_count += 1
            framework_details[name] = {
                "score": fs,
                "signals": result.get("signals", []),
                "details": result.get("details", {}),
            }
            all_signals.extend(result.get("signals", []))
            if result.get("hard_reject"):
                hard_reject = True
        except Exception as e:
            log.warning(f"框架 {name} 执行异常: {e}")
            framework_details[name] = {"score": 5, "error": str(e)}
    
    # 归一化到 0-100
    normalized = min(100, int(total_score / max(active_count, 1) * 10))
    
    # 去重信号、按类型分组
    buy_signals = [s["msg"] for s in all_signals if s["type"] == "bullish"]
    sell_signals = [s["msg"] for s in all_signals if s["type"] == "bearish"]
    warn_signals = [s["msg"] for s in all_signals if s["type"] == "warning"]
    
    return {
        "total_score": normalized,
        "raw_score": total_score,
        "active_frameworks": active_count,
        "hard_reject": hard_reject,
        "reject_reason": "触发硬性排雷规则" if hard_reject else "",
        "signal_summary": {
            "buy": buy_signals[:5],
            "sell": sell_signals[:5],
            "warning": warn_signals[:5],
        },
        "all_signals": all_signals,
        "framework_scores": framework_details,
    }


# ===================================================================
# CLI 测试
# ===================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 模拟数据测试
    mock_financials = {
        "roe_ttm": [18, 20, 22],
        "gross_margin": [45, 48, 52],
        "debt_ratio": 25,
        "cfo_ni_ratio": 0.8,
        "ar_growth_vs_revenue": 10,
        "revenue_decline": 5,
        "margin_pressure": 2,
    }
    mock_market = {
        "pe_percentile": 35,
        "pmi": 51,
        "credit_growth": 11,
        "fund_crowding": 0.6,
    }
    mock_industry_data = {
        "policy_score": 2,
        "lifecycle": "成长",
        "fund_allocation": 1.8,
    }
    
    result = apply_all_frameworks(
        stock_name="贵州茅台",
        code="600519",
        industry="白酒",
        financials=mock_financials,
        market_data=mock_market,
        industry_data=mock_industry_data,
        sentiment_score=0.7,
    )
    
    print(f"综合评分: {result['total_score']}/100")
    print(f"框架数: {result['active_frameworks']}")
    print(f"硬性排雷: {'是' if result['hard_reject'] else '否'}")
    print(f"买入信号 ({len(result['signal_summary']['buy'])}):")
    for s in result['signal_summary']['buy']:
        print(f"  ✅ {s}")
    print(f"卖出信号 ({len(result['signal_summary']['sell'])}):")
    for s in result['signal_summary']['sell']:
        print(f"  ❌ {s}")
    print(f"警告信号 ({len(result['signal_summary']['warning'])}):")
    for s in result['signal_summary']['warning']:
        print(f"  ⚠️ {s}")
    print(f"\n各框架评分:")
    for name, det in result['framework_scores'].items():
        sigs = det.get('signals', [])
        sig_str = f" ({len(sigs)}信号)" if sigs else ""
        print(f"  {name}: {det['score']}/10{sig_str}")


# ── 市场状态分析（2026-05-27 新增）──

def framework_market_state(index_data: dict = None) -> dict:
    """市场状态分析：牛/熊/震荡/趋势强度
    
    Parameters
    ----------
    index_data : dict
        {"returns_20d": float, "returns_60d": float, "returns_120d": float, "volatility": float}
    """
    if not index_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    ret20 = index_data.get("returns_20d", 0)
    ret60 = index_data.get("returns_60d", 0)
    vol = index_data.get("volatility", 0.2)
    
    signals = []
    score = 0
    
    # 趋势判断
    if ret60 > 0.1 and ret20 > 0:
        state = "牛市"
        score += 0.3
    elif ret60 < -0.1 and ret20 < 0:
        state = "熊市"
        score -= 0.3
    elif abs(ret60) < 0.05:
        state = "震荡"
        score += 0.1
    else:
        state = "过渡"
        score += 0.0
    
    # 趋势强度
    if vol < 0.15:
        signals.append("低波动环境 - 趋势策略占优")
        score += 0.1
    elif vol > 0.3:
        signals.append("高波动环境 - 注意风险控制")
        score -= 0.1
    
    # 短期动量
    if ret20 > 0.05:
        signals.append("短期动能向上")
        score += 0.1
    elif ret20 < -0.05:
        signals.append("短期动能向下")
        score -= 0.1
    
    return {
        "state": state,
        "trend_strength": round(ret60 * 100, 1) if ret60 else 0,
        "volatility": round(vol * 100, 1),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"市场处于{state}，波动率{vol*100:.0f}%"
    }


# ── 宏观因果分析（达利欧三动力）──

def framework_macro_causal(macro_data: dict = None) -> dict:
    """宏观因果：达利欧三动力模型
    
    Parameters
    ----------
    macro_data : dict
        {"productivity_growth": float, "credit_cycle": str, "debt_level": str}
    """
    if not macro_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    prod = macro_data.get("productivity_growth", 0.02)
    credit = macro_data.get("credit_cycle", "中性")
    debt = macro_data.get("debt_level", "中等")
    
    signals = []
    score = 0
    
    # 生产率增长
    if prod > 0.03:
        signals.append("生产率增长强劲 - 长期利好")
        score += 0.3
    elif prod < 0.01:
        signals.append("生产率增长疲软 - 关注结构性改革")
        score -= 0.2
    
    # 信用周期
    credit_map = {"扩张": 0.3, "中性": 0.0, "收缩": -0.3}
    score += credit_map.get(credit, 0)
    if credit == "扩张":
        signals.append("信用扩张 - 短期繁荣")
    elif credit == "收缩":
        signals.append("信用收缩 - 注意去杠杆")
    
    # 债务水平
    debt_map = {"低": 0.2, "中等": 0.0, "高": -0.3, "极高": -0.5}
    score += debt_map.get(debt, 0)
    if debt in ("高", "极高"):
        signals.append(f"债务水平{debt} - 关注去杠杆风险")
    
    return {
        "productivity": f"{prod*100:.1f}%",
        "credit_cycle": credit,
        "debt_level": debt,
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"宏观: 生产率{prod*100:.0f}%/信用{credit}/债务{debt}"
    }


# ── 基金评价（四步法）──

def framework_fund_evaluation(fund_data: dict = None) -> dict:
    """基金评价：四步法（类型/经理/费率/规模）
    
    Parameters
    ----------
    fund_data : dict
        {"type": str, "manager_years": int, "fee_rate": float, "size_billion": float, "track_record": float}
    """
    if not fund_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    signals = []
    score = 0
    
    # 类型
    ftype = fund_data.get("type", "")
    passive_types = ["指数", "ETF", "被动"]
    active_types = ["主动", "混合", "股票"]
    if any(t in ftype for t in passive_types):
        score += 0.1  # 低费率优势
    elif any(t in ftype for t in active_types):
        score += 0.0
    
    # 经理年限
    years = fund_data.get("manager_years", 0)
    if years >= 8:
        signals.append(f"经理经验丰富({years}年)")
        score += 0.2
    elif years >= 3:
        score += 0.1
    else:
        signals.append(f"经理年限较短({years}年)")
        score -= 0.1
    
    # 费率
    fee = fund_data.get("fee_rate", 0.015)
    if fee < 0.005:
        signals.append(f"低费率({fee*100:.1f}%)")
        score += 0.2
    elif fee > 0.015:
        signals.append(f"高费率({fee*100:.1f}%)")
        score -= 0.1
    
    # 规模
    size = fund_data.get("size_billion", 0)
    if 1 < size < 50:
        score += 0.1  # 适中规模
    elif size > 100:
        signals.append(f"规模偏大({size:.0f}亿)")
        score -= 0.1
    
    # 历史业绩
    track = fund_data.get("track_record", 0)
    if track > 0.1:
        signals.append(f"年化超额{track*100:.1f}%")
        score += 0.2
    elif track < 0:
        signals.append("超额收益为负")
        score -= 0.2
    
    return {
        "fund_type": ftype,
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"基金评价: 经理{years}年/费率{fee*100:.1f}%/规模{size:.0f}亿"
    }


# ── 另类投资三维度 ──

def framework_alternative_investment(alt_data: dict = None) -> dict:
    """另类投资评估：稀缺性/标准化/流动性
    
    Parameters
    ----------
    alt_data : dict
        {"scarcity": float, "standardization": float, "liquidity": float}
    """
    if not alt_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    scarcity = alt_data.get("scarcity", 0.5)
    std = alt_data.get("standardization", 0.5)
    liquidity = alt_data.get("liquidity", 0.5)
    
    signals = []
    score = (scarcity + std + liquidity) / 3 * 2 - 1  # 归一化到 [-1, 1]
    
    if scarcity > 0.7:
        signals.append("稀缺性较高 - 供给受限")
    if std > 0.7:
        signals.append("标准化程度高 - 易于估值")
    if liquidity > 0.7:
        signals.append("流动性好 - 进出方便")
    if liquidity < 0.3:
        signals.append("流动性差 - 注意折价风险")
    
    return {
        "scarcity_score": round(scarcity, 2),
        "standardization_score": round(std, 2),
        "liquidity_score": round(liquidity, 2),
        "composite": round(score, 4),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"另类投资: 稀缺{scarcity:.1f}/标准化{std:.1f}/流动性{liquidity:.1f}"
    }


# ── 关税评估（三问法）──

def framework_tariff(tariff_data: dict = None) -> dict:
    """关税评估：三问法
    
    1. 谁承担（中国/美国/第三方）
    2. 转口可行（是否有转口渠道）
    3. 历史参照（类似案例影响）
    
    Parameters
    ----------
    tariff_data : dict
        {"bearer": str, "transshipment_possible": bool, "historical_impact": float}
    """
    if not tariff_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    bearer = tariff_data.get("bearer", "双方")
    transship = tariff_data.get("transshipment_possible", False)
    historical = tariff_data.get("historical_impact", -0.05)
    
    signals = []
    score = 0
    
    # 谁承担
    bearer_map = {"中国": -0.3, "美国": 0.2, "双方": -0.1, "第三方": 0.1}
    score += bearer_map.get(bearer, -0.1)
    if bearer == "中国":
        signals.append("关税主要由中国承担 - 对出口企业利空")
    elif bearer == "美国":
        signals.append("关税主要由美国承担 - 影响有限")
    
    # 转口可行
    if transship:
        signals.append("存在转口渠道 - 影响可对冲")
        score += 0.2
    else:
        signals.append("无转口渠道 - 影响直接")
        score -= 0.2
    
    # 历史参照
    score += historical * 2  # 放大历史影响
    if historical < -0.1:
        signals.append(f"历史类似事件影响{historical*100:.0f}%")
    elif historical > 0:
        signals.append("历史经验显示影响可控")
    
    return {
        "tariff_bearer": bearer,
        "transshipment": transship,
        "historical_impact": round(historical * 100, 1),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"关税: 承担方={bearer}/转口={'可' if transship else '否'}"
    }


# ── 多元思维（芒格逆向+多学科交叉）──

def framework_multi_discipline(analysis_data: dict = None) -> dict:
    """芒格多元思维：多学科交叉验证
    
    Parameters
    ----------
    analysis_data : dict
        {"checklist": list, "cross_signals": list, "consensus_count": int}
    """
    if not analysis_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    checklist = analysis_data.get("checklist", [])
    cross = analysis_data.get("cross_signals", [])
    consensus = analysis_data.get("consensus_count", 0)
    
    signals = []
    score = 0.5  # 基础分
    
    # 检查清单完成度
    checked = sum(1 for c in checklist if c) if checklist else 0
    total = len(checklist) if checklist else 1
    completeness = checked / max(total, 1)
    score += (completeness - 0.5) * 0.4
    
    if completeness < 0.3:
        signals.append("检查清单完成度低 - 分析可能不全面")
    elif completeness > 0.8:
        signals.append("检查清单完成度高 - 分析全面")
    
    # 交叉信号一致性
    if cross:
        pos = sum(1 for s in cross if s > 0)
        neg = sum(1 for s in cross if s < 0)
        if pos > 0 and neg > 0:
            signals.append("多学科信号冲突 - 需要深入分析")
            score -= 0.2
        elif pos > len(cross) * 0.7:
            signals.append("多学科信号一致看多")
            score += 0.2
        elif neg > len(cross) * 0.7:
            signals.append("多学科信号一致看空")
            score -= 0.2
    
    # 市场共识偏离
    if consensus > 5:
        signals.append(f"市场共识度高({consensus}个来源) - 注意逆向机会")
        score -= 0.1
    
    return {
        "checklist_completeness": round(completeness, 2),
        "cross_signals_count": len(cross),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"多元思维: 清单{completeness*100:.0f}%/交叉{len(cross)}信号"
    }


# ── 尽调流程（六步法）──

def framework_due_diligence(dd_data: dict = None) -> dict:
    """尽调流程：六步法（行业→公司→财务→估值→风险→退出）
    
    Parameters
    ----------
    dd_data : dict
        {"industry_score": float, "company_score": float, "financial_score": float,
         "valuation_score": float, "risk_score": float, "exit_score": float}
    """
    if not dd_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    steps = ["industry_score", "company_score", "financial_score", "valuation_score", "risk_score", "exit_score"]
    scores = {s: dd_data.get(s, 0) for s in steps}
    
    signals = []
    total = 0
    weak_steps = []
    
    for step, s in scores.items():
        total += s
        if s < -0.3:
            weak_steps.append(step.replace("_score", ""))
    
    avg = total / len(steps)
    score = (avg + 1) / 2 * 2 - 1  # 缩放到[-1,1]
    
    if weak_steps:
        signals.append(f"薄弱环节: {', '.join(weak_steps)}")
    
    # 整体判定
    if avg > 0.3:
        signals.append("尽调整体积极")
    elif avg < -0.2:
        signals.append("尽调发现多个风险点 - 建议回避")
    
    return {
        "step_scores": {k: round(v, 4) for k, v in scores.items()},
        "average": round(avg, 4),
        "weak_steps": weak_steps,
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"尽调: {len(weak_steps)}个薄弱/平均{avg:.2f}"
    }


# ── A股五步研究法 ──

def framework_a_share_five(ashare_data: dict = None) -> dict:
    """A股五步研究法：宏观→行业→标的→风控→执行
    
    Parameters
    ----------
    ashare_data : dict
        {"macro": float, "sector": float, "target": float, "risk": float, "execution": float}
    """
    if not ashare_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    steps = ["macro", "sector", "target", "risk", "execution"]
    signals = []
    weak = []
    
    total = 0
    for s in steps:
        v = ashare_data.get(s, 0)
        total += v
        if v < -0.2:
            weak.append(s)
    
    avg = total / len(steps)
    score = avg
    
    if weak:
        signals.append(f"弱势环节: {', '.join(weak)} - 需补充分析")
    
    if avg > 0.3:
        signals.append("五步分析积极 - 可考虑建仓")
    elif avg < -0.2:
        signals.append("五步分析消极 - 建议回避")
    
    return {
        "step_scores": {s: round(ashare_data.get(s, 0), 4) for s in steps},
        "average": round(avg, 4),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "weak_links": weak,
        "conclusion": f"A股五步法: {len(weak)}步弱势/均分{avg:.2f}"
    }


# ── 五章结构（报告输出模板）──

def framework_five_chapter(report_data: dict = None) -> dict:
    """五章结构：全景→公司→财务→估值→风险
    
    Parameters
    ----------
    report_data : dict
        {"overview": float, "company": float, "financial": float, "valuation": float, "risk": float}
    """
    if not report_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    chapters = ["overview", "company", "financial", "valuation", "risk"]
    total = sum(report_data.get(c, 0) for c in chapters)
    avg = total / len(chapters)
    
    score = avg
    signals = []
    
    if report_data.get("risk", 0) < -0.5:
        signals.append("风险章节评分低 - 注意尾部风险")
        score -= 0.1
    
    if report_data.get("financial", 0) > 0.5 and report_data.get("valuation", 0) > 0.3:
        signals.append("财务+估值双优 - 基本面扎实")
    
    return {
        "chapter_scores": {c: round(report_data.get(c, 0), 4) for c in chapters},
        "overall": round(avg, 4),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"五章评估: 均分{avg:.2f}"
    }


# ── 量价分析框架（道氏三阶段+成交量四法则）──

def framework_volume_price(vp_data: dict = None) -> dict:
    """量价分析：道氏三阶段+成交量验证
    
    Parameters
    ----------
    vp_data : dict
        {"stage": str, "volume_confirm": bool, "divergence": bool,
         "return_20d": float, "volume_ratio_20d": float}
    """
    if not vp_data:
        return {"score": 0, "signals": [], "conclusion": "数据不足"}
    
    stage = vp_data.get("stage", "未知")
    volume_confirm = vp_data.get("volume_confirm", False)
    divergence = vp_data.get("divergence", False)
    ret20 = vp_data.get("return_20d", 0)
    vol_ratio = vp_data.get("volume_ratio_20d", 1.0)
    
    signals = []
    score = 0
    
    # 道氏阶段
    stage_map = {
        "吸筹": 0.4, "公众参与": 0.2, "派发": -0.3,
        "底部": 0.3, "上涨": 0.2, "顶部": -0.3, "下跌": -0.2
    }
    score += stage_map.get(stage, 0)
    signals.append(f"道氏阶段: {stage}")
    
    # 成交量验证
    if volume_confirm:
        signals.append("成交量验证上涨 - 趋势可靠")
        score += 0.2
    else:
        signals.append("价涨量缩 - 上涨动能不足")
        score -= 0.2
    
    # 顶底背离
    if divergence:
        signals.append("量价背离 - 趋势可能反转")
        if score > 0:
            score -= 0.3  # 顶背离
        else:
            score += 0.3  # 底背离
    
    # 量比
    if vol_ratio > 1.5:
        signals.append("放量")
    elif vol_ratio < 0.5:
        signals.append("缩量")
    
    return {
        "stage": stage,
        "volume_confirm": volume_confirm,
        "divergence": divergence,
        "return_20d": round(ret20, 4),
        "score": round(max(-1, min(1, score)), 4),
        "signals": signals,
        "conclusion": f"量价: {stage}/量{'确认' if volume_confirm else '背离'}"
    }
