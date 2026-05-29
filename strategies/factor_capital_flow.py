#!/usr/bin/env python3
"""资金面因子 — 融资融券/股东户数/大宗交易

数据源: a-stock-data 资金面层
"""
import logging
from typing import Dict
log = logging.getLogger("factor_capital_flow")

def factor_capital_flow(code: str) -> Dict:
    try:
        from data_sources.proxy import margin_trading, holder_num_change, block_trade
    except ImportError:
        return {"score": 5, "details": {"error": "a_stock_data 不可用"}}
    
    score = 5
    details = {}
    
    # 融资融券: 融资净买入为正 → 加分
    try:
        margin = margin_trading(code)
        if margin and isinstance(margin, dict):
            net_buy = float(margin.get("rzye", 0)) - float(margin.get("rqye", 0))
            details["margin_net"] = round(net_buy, 2)
            if net_buy > 0:
                score += min(net_buy / 1e7 * 5, 20)
            elif net_buy < 0:
                score -= min(abs(net_buy) / 1e7 * 5, 10)
    except Exception:
        pass
    
    # 股东户数: 减少 = 筹码集中 → 加分
    try:
        holders = holder_num_change(code)
        if holders and isinstance(holders, dict):
            change = float(holders.get("change", 0))
            details["holder_change"] = round(change, 2)
            if change < -5:
                score += 15
            elif change < 0:
                score += 8
            elif change > 5:
                score -= 10
    except Exception:
        pass
    
    return {"score": min(max(score, 0), 100), "details": details}
