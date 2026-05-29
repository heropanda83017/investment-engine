#!/usr/bin/env python3
"""研报因子 — 一致预期EPS/PEG/机构评级

数据源: a-stock-data 研报层（东财reportapi + 同花顺一致预期）

因子逻辑:
  1. 一致预期EPS增长率 (fy1/fy0 - 1) → 成长性得分
  2. PEG = PE / EPS增长率 → 估值合理度得分
  3. 机构覆盖数 → 关注度得分
"""
import logging
from typing import Dict
log = logging.getLogger("factor_consensus")

def factor_consensus(code: str) -> Dict:
    """机构一致预期因子"""
    try:
        from data_sources.proxy import eastmoney_reports, ths_eps_forecast
    except ImportError:
        return {"score": 5, "details": {"error": "a_stock_data 不可用"}}
    
    score = 5
    details = {"eps_consensus": 0, "peg": 0, "institution_count": 0}
    
    try:
        reports = eastmoney_reports(code)
        if reports and isinstance(reports, list):
            details["institution_count"] = len(reports)
            score += min(len(reports), 10)
    except Exception:
        pass
    
    try:
        forecast = ths_eps_forecast(code)
        if forecast:
            details["eps_consensus"] = round(float(forecast.get("eps", 0)), 3)
            growth = float(forecast.get("growth", 0))
            if growth > 0:
                score += min(growth * 20, 30)
                details["growth"] = round(growth, 2)
    except Exception:
        pass
    
    return {"score": min(score, 100), "details": details}
