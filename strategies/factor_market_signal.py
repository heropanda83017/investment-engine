#!/usr/bin/env python3
"""市场信号因子 — 龙虎榜/北向资金/题材热度

数据源: a-stock-data 信号层
"""
import logging
from typing import Dict
log = logging.getLogger("factor_market_signal")

def factor_market_signal(code: str) -> Dict:
    try:
        from data_sources.proxy import dragon_tiger_board, hsgt_realtime, baidu_concept_blocks
    except ImportError:
        return {"score": 5, "details": {"error": "a_stock_data 不可用"}}
    
    score = 5
    details = {"dragon_tiger": 0, "northbound": 0, "concept_count": 0}
    
    # 龙虎榜: 机构净买入 → 加分
    try:
        dt = dragon_tiger_board(code)
        if dt and isinstance(dt, dict):
            inst_net = float(dt.get("inst_net", 0))
            details["dragon_tiger"] = round(inst_net, 2)
            if inst_net > 0:
                score += min(inst_net / 1e6 * 10, 25)
    except Exception:
        pass
    
    # 北向资金: 净流入 → 加分
    try:
        hsgt = hsgt_realtime()
        if hsgt and isinstance(hsgt, dict):
            net = float(hsgt.get("net_amount", 0))
            if net > 0:
                details["northbound"] = round(net, 2)
                score += 5
    except Exception:
        pass
    
    # 概念板块: 覆盖多概念 → 加分
    try:
        blocks = baidu_concept_blocks(code)
        if blocks and isinstance(blocks, dict):
            concepts = blocks.get("concepts", [])
            details["concept_count"] = len(concepts)
            score += min(len(concepts) * 3, 15)
    except Exception:
        pass
    
    return {"score": min(score, 100), "details": details}
