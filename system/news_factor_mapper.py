#!/usr/bin/env python3
"""news_factor_mapper.py - Layer 2: 新闻->因子映射器
输入: news_db/{date}.json
输出: news_impact_{date}.json
Schema: {"date":str,"impacts":[NewsImpact],"aggregate":dict[str,int],"cold_start":bool}
"""

import os, sys, json
from datetime import datetime, timezone, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.join(DIR, "news_db")
IMPACTS_DIR = os.path.join(DIR, "impacts")
os.makedirs(IMPACTS_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)

# News-to-factor mapping rules (configurable JSON, editable without code changes)
DEFAULT_RULES = {
    "ai-models": {"利好":{"趋势":3},"利空":{"趋势":-2},"中性":{"趋势":1}},
    "ai-products": {"利好":{"量能":2},"利空":{"量能":-1},"中性":{"量能":0}},
    "industry": {"利好":{"资金":2},"利空":{"资金":-2},"中性":{"资金":1}},
    "paper": {"利好":{"alpha191":2},"利空":{"alpha191":-1},"中性":{"alpha191":0}},
    "tip": {"利好":{"情绪":1},"利空":{"情绪":-1},"中性":{"情绪":0}},
}

# Company-specific mapping (overrides category rules)
COMPANY_RULES = {
    "NVIDIA": {"利好":{"趋势":5,"资金":3},"利空":{"趋势":-4,"资金":-3}},
    "OpenAI": {"利好":{"趋势":3,"量能":2},"利空":{"趋势":-2}},
    "Anthropic": {"利好":{"趋势":3},"利空":{"趋势":-2}},
    "华为": {"利好":{"基本面":2,"趋势":3},"利空":{"基本面":-3,"趋势":-2}},
}

# Sector impact mapping
SECTOR_MAP = {
    "chip": ["688981","688072","002371","688012"],           # 半导体设备/制造
    "compute": ["300308","688126"],                           # 算力/光模块
    "AI": ["000725","688981"],                                # AI概念
    "con": ["300433","000725"],                               # 消费电子
    "pol": ["688981","002049","002371"],                      # 政策敏感
}

FACTOR_KEYS = ["趋势","量能","资金","波动","基本面","情绪","alpha191"]

def load_news(date_str=None):
    """Load news from news_db, auto-detect latest if no date given"""
    if date_str:
        yr, mo = date_str[:4], date_str[5:7]
        fp = os.path.join(NEWS_DIR, yr, mo, date_str+".json")
        if os.path.exists(fp):
            with open(fp,"r",encoding="utf-8") as f: return json.load(f)
        print("  Not found: %s" % fp); return None
    # Auto-detect latest
    if not os.path.exists(NEWS_DIR): return None
    years = sorted([d for d in os.listdir(NEWS_DIR) if os.path.isdir(os.path.join(NEWS_DIR,d))], reverse=True)
    for y in years:
        months = sorted([d for d in os.listdir(os.path.join(NEWS_DIR,y)) if os.path.isdir(os.path.join(NEWS_DIR,y,d))], reverse=True)
        for m in months:
            files = sorted([f for f in os.listdir(os.path.join(NEWS_DIR,y,m)) if f.endswith(".json") and f!="health.json"], reverse=True)
            if files:
                with open(os.path.join(NEWS_DIR,y,m,files[0]),"r",encoding="utf-8") as fp:
                    return json.load(fp)
    return None

def map_impact(item, rules):
    """Map a single news item to factor adjustments"""
    cat = item.get("cat") or ""
    direction = item.get("dir","中性")
    tags = item.get("tags",[])
    companies = item.get("cos",[])
    
    # Step 1: Category-based impact
    adj = {}
    cat_rules = rules.get(cat, DEFAULT_RULES.get("industry", {}))
    cat_adj = cat_rules.get(direction, cat_rules.get("中性", {}))
    adj.update(cat_adj)
    
    # Step 2: Company-specific override
    for co in companies:
        if co in COMPANY_RULES:
            co_adj = COMPANY_RULES[co].get(direction, {})
            for k,v in co_adj.items():
                adj[k] = adj.get(k,0) + v
    
    # Step 3: Sector detection
    affected = []
    for tag in tags:
        if tag in SECTOR_MAP:
            affected.extend(SECTOR_MAP[tag])
    
    # Compute strength (max absolute adjustment)
    strength = max([abs(v) for v in adj.values()]) if adj else 0
    
    return {
        "news_id": item.get("id",""),
        "title": (item.get("title") or "")[:60],
        "direction": direction,
        "strength": strength,
        "factor_adjustments": adj,
        "affected_stocks": list(set(affected)),
        "reasoning": "%s category=%s dir=%s cos=%s" % (item.get("title","")[:40], cat, direction, companies),
    }

def run(date_str=None):
    news_data = load_news(date_str)
    if not news_data:
        print("[mapper] No news data found"); return None
    
    items = news_data.get("items",[])
    print("[mapper] Processing %d news items" % len(items))
    
    impacts = []
    aggregate = {k:0 for k in FACTOR_KEYS}
    
    for item in items:
        impact = map_impact(item, DEFAULT_RULES)
        impacts.append(impact)
        for k,v in impact["factor_adjustments"].items():
            if k in aggregate:
                aggregate[k] += v
    
    # Cold-start flag
    is_cold = len(items) < 5
    
    result = {
        "date": news_data.get("date", datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")),
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "news_count": len(items),
        "cold_start": is_cold,
        "impacts": impacts,
        "aggregate_impact": aggregate,
    }
    
    # Save
    td = result["date"]
    fp = os.path.join(IMPACTS_DIR, "impact_%s.json" % td)
    with open(fp,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print("  Saved: %s" % fp)
    print("  Aggregate: %s" % aggregate)
    return result

if __name__=="__main__":
    run()
