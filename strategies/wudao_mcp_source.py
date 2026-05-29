"""wudao_mcp_source.py — wudao MCP Python 直连 (JSON-RPC 2.0)

从 Hermes 配置读取 token，直接 HTTP 调用 wudao MCP 服务。
获取实时盘面数据、涨跌停统计、板块热点等。
"""
import json, logging, time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger("wudao_mcp")

MCP_URL = "https://stock.quicktiny.cn/api/mcp-stream"
AUTH_TOKEN = "lb_643b662d34b1f75d1107ed5cb9980896b1e64082b157681f35956418ff7fc8e7"
_REQ_ID = 0
from env import IE_CACHE
CACHE_DIR = IE_CACHE / "wudao"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _next_id():
    global _REQ_ID; _REQ_ID += 1; return _REQ_ID

def _cache_get(key, ttl=300):
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            with open(p) as f: d = json.load(f)
            if (time.time() - p.stat().st_mtime) < ttl: return d
        except: pass
    return None

def _cache_set(key, data):
    with open(CACHE_DIR / f"{key}.json", "w") as f:
        json.dump(data, f)

def mcp_call(method, params=None, timeout=15, use_cache=True, cache_ttl=300):
    """调用 wudao MCP 方法"""
    cache_key = f"mcp_{method}_{datetime.now().strftime('%Y%m%d_%H')}"
    if use_cache:
        cached = _cache_get(cache_key, cache_ttl)
        if cached: return cached

    payload = json.dumps({"jsonrpc":"2.0","id":_next_id(),"method":method,"params":params or{}}).encode()
    req = Request(MCP_URL, data=payload,
        headers={"Content-Type":"application/json",
                  "Authorization":f"Bearer {AUTH_TOKEN}",
                  "User-Agent":"investment-engine/1.0"},
        method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
        if "error" in result:
            logger.warning(f"wudao MCP error: {result['error']}"); return None
        r = result.get("result")
        if use_cache and r: _cache_set(cache_key, r)
        return r
    except Exception as e:
        logger.warning(f"wudao MCP failed: {e}"); return None

def market_overview() -> Optional[dict]:
    """获取市场概况（涨跌家数/温度）"""
    return mcp_call("tools/call", {"name":"market_overview","arguments":{"date":"2026-05-27"}})

def limit_stats(date_str: str = None) -> Optional[dict]:
    """涨跌停统计"""
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    return mcp_call("tools/call", {"name":"limit_stats","arguments":{"date":date_str or "2026-05-27"}})

def hot_sectors(date_str: str = None) -> Optional[dict]:
    """热点板块"""
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    return mcp_call("tools/call", {"name":"hot_sectors","arguments":{"date":date_str or "2026-05-27"}})

def limit_up_ladder(date_str: str = None) -> Optional[dict]:
    """涨停梯队"""
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    return mcp_call("tools/call", {"name":"limit_up_ladder","arguments":{"date":date_str or "2026-05-27"}})

def capital_flow(flow_type: str = "market", date_str: str = None) -> Optional[dict]:
    """资金流向"""
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    return mcp_call("tools/call", {"name":"capital_flow","arguments":{"flowType":flow_type,"date":date_str or "2026-05-27"}})

def get_all_market_data(date_str: str = None) -> dict:
    """一键获取全部市场数据"""
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    return {
        "overview": market_overview(),
        "limit_stats": limit_stats(date_str),
        "hot_sectors": hot_sectors(date_str),
        "ladder": limit_up_ladder(date_str),
        "capital_flow": capital_flow("market", date_str),
    }

def format_market_section(data: dict) -> str:
    """市场数据 → 可读文本"""
    lines = ["## 实时盘面数据\n"]
    ov = data.get("overview", {})
    if ov:
        lines.append(f"市场温度: {ov.get('temperature','?')}")
    ls = data.get("limit_stats", {})
    if ls:
        lines.append(f"涨停: {ls.get('limit_up',0)} 跌停: {ls.get('limit_down',0)}")
    hs = data.get("hot_sectors", {})
    if hs:
        top = hs[:3] if isinstance(hs, list) else []
        lines.append(f"热点: {', '.join([s.get('name','') for s in top[:3]])}")
    return "\n".join(lines)

def has_live_data() -> bool:
    """检查是否有实时数据（代替旧版 has_cache）"""
    data = market_overview()
    return data is not None
