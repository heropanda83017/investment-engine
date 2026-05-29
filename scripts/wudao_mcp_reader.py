#!/usr/bin/env python3
"""wudao_mcp_reader.py --- 读取 wudao MCP 缓存的实时盘面数据

cronjob 的 Step 0 将 wudao MCP 数据存为 JSON 到 _cache/wudao/，
Python 脚本通过此模块读取并整合到日报中。
"""

import json, os, logging
from pathlib import Path
from datetime import datetime, date
from typing import Optional

log = logging.getLogger("wudao_reader")
from env import IE_CACHE
CACHE_DIR = IE_CACHE / "wudao"

def load_cache(name: str) -> Optional[dict]:
    fp = CACHE_DIR / f"{name}.json"
    if not fp.exists():
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"read {fp} failed: {e}")
        return None

def extract_text(data: Optional[dict]) -> Optional[str]:
    if not data:
        return None
    content = data.get("content", [])
    if isinstance(content, list) and content:
        text = content[0].get("text", "")
        return text[:500] if text else None
    text = data.get("text", "")
    return text[:500] if text else str(data)[:500]

def get_overview_text():
    return extract_text(load_cache("market_overview"))

def get_limit_stats_text():
    return extract_text(load_cache("limit_stats"))

def get_sectors_text():
    return extract_text(load_cache("hot_sectors"))

def get_ladder_text():
    return extract_text(load_cache("limit_up_ladder"))

def get_flow_text():
    return extract_text(load_cache("capital_flow"))

def gen_market_section() -> str:
    parts = []
    t = get_overview_text()
    if t: parts.append(f"### 市场总览\n{t[:300]}")
    t = get_limit_stats_text()
    if t: parts.append(f"### 涨跌停统计\n{t[:200]}")
    t = get_ladder_text()
    if t: parts.append(f"### 涨停梯队\n{t[:300]}")
    t = get_sectors_text()
    if t: parts.append(f"### 热点板块\n{t[:300]}")
    t = get_flow_text()
    if t: parts.append(f"### 资金流向\n{t[:300]}")
    if not parts:
        parts.append("> wudao MCP data not cached, run cronjob Step 0 first")
    return "\n\n".join(parts)

def has_cache() -> bool:
    return any(CACHE_DIR.glob("*.json"))

if __name__ == "__main__":
    print("=== wudao MCP cache status ===")
    for name in ["market_overview", "limit_stats", "limit_up_ladder", "hot_sectors", "capital_flow"]:
        fp = CACHE_DIR / f"{name}.json"
        s = "OK" if fp.exists() else "--"
        print(f"  {name}: {s}")
