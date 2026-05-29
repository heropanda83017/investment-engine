"""
valuation_utils.py — forward_pe, pe_digestion, calc_peg, full_valuation, industry_comparison
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import math
import requests
import urllib.request
import pandas as pd
from datetime import datetime


def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 当前股价 / 未来年度一致预期EPS"""
    if eps_forecast <= 0:
        return float("inf")
    return price / eps_forecast


def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    """当前PE消化到目标PE需要多少年。

    target_pe 固定30x（A股成长股合理估值锚点）。
    cagr: 用 下一年EPS / 当年EPS - 1
    """
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    years = math.log(current_pe / target_pe) / math.log(1 + cagr)
    return round(years, 1)


def calc_peg(pe: float, cagr: float) -> float:
    """PEG = PE / (CAGR * 100)

    PEG < 1   → 便宜
    PEG 1-1.5 → 合理
    PEG > 1.5 → 贵
    """
    if cagr <= 0:
        return float("inf")
    return pe / (cagr * 100)


def full_valuation(code: str) -> dict:
    """单票完整估值分析。"""
    # TODO: 从测试块中恢复实现
    # 腾讯实时行情 + 机构一致预期 + 估值指标
    # prefix = "sh" if code.startswith(("6","9")) else ...
    # url = f"https://qt.gtimg.cn/q={prefix}{code}"
    # ...
    return {"name": "", "price": 0, "mcap_yi": 0, "pe_ttm": 0}


def industry_comparison(top_n: int = 20) -> dict:
    """全行业涨跌幅排名（东财行业板块，~100 个行业）。

    返回: {top: [...], bottom: [...], total: int}
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    headers = {"User-Agent": UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    items = d.get("data", {}).get("diff", [])
    if not items:
        return {"top": [], "bottom": [], "total": 0}

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "rank": i + 1,
            "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0),
            "code": item.get("f12", ""),
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
            "leader": item.get("f140", ""),
            "leader_change": item.get("f136", 0),
        })

    return {
        "top": rows[:top_n],
        "bottom": rows[-top_n:],
        "total": len(rows),
    }
