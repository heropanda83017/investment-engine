"""anysearch_source.py — AnySearch MCP 集成 (JSON-RPC 2.0)
"""
import json, logging, time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger("anysearch")
CACHE_DIR = Path(__file__).resolve().parent.parent / "_cache" / "anysearch"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MCP_URL = "https://api.anysearch.com/mcp"
API_KEY = "as_sk_687b4de1cecc89a9856e0dfb3dd2bc84"
_REQ_ID = 0

def _next_id():
    global _REQ_ID; _REQ_ID += 1; return _REQ_ID

def mcp_call(method, params=None, timeout=15):
    payload = json.dumps({"jsonrpc":"2.0","id":_next_id(),"method":method,"params":params or {}}).encode()
    req = Request(MCP_URL, data=payload,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {API_KEY}",
                 "User-Agent":"investment-engine/1.0"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
        if "error" in result:
            logger.warning(f"MCP error: {result['error']}"); return None
        return result.get("result")
    except Exception as e:
        logger.warning(f"MCP failed: {e}"); return None

def _cache_get(key):
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            with open(p) as f: d = json.load(f)
            if (datetime.now()-datetime.fromtimestamp(p.stat().st_mtime)).seconds < 21600: return d
        except: pass
    return None

def _cache_set(key, data):
    with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def search_news(query, max_results=5):
    ck = f"news_{query[:20]}_{date.today()}"
    c = _cache_get(ck)
    if c: return c
    r = mcp_call("tools/call", {"name":"search", "arguments":{"query":query,"limit":max_results}})
    if not r: return []
    items = []
    content = r.get("content", [])
    if isinstance(content, list):
        for item in content:
            text = item.get("text","") if isinstance(item,dict) else str(item)
            # 解析 markdown 格式的搜索结果
            lines = text.split("\n")
            title = ""
            url = ""
            for line in lines:
                if line.startswith("###"):
                    title = line.replace("###","").strip()
                if "URL" in line:
                    url = line.split(": ")[-1].strip()
            items.append({"title":title,"content":text[:800],"url":url,"date":str(date.today())})
    _cache_set(ck, items)
    return items[:max_results]

def search_sentiment(stock_name, stock_code=""):
    query = f"{stock_name} {stock_code}".strip()
    ck = f"sent_{query[:15]}_{date.today()}"
    c = _cache_get(ck)
    if c is not None: return c
    news = search_news(query, 5)
    if not news: return 0.0
    pos_kw = ["涨停","大涨","突破","利好","新高","超预期","增持","回购"]
    neg_kw = ["跌停","大跌","破位","利空","新低","预警","减持","亏损"]
    score, cnt = 0.0, 0
    for item in news:
        text = item.get("content","")
        if not text: continue
        p = sum(1 for k in pos_kw if k in text)
        n = sum(1 for k in neg_kw if k in text)
        if p+n > 0: score += (p-n)/(p+n); cnt += 1
    s = round(score/max(cnt,1), 4)
    s = max(-1.0, min(1.0, s))
    _cache_set(ck, s)
    return s

def batch_sentiment(stocks):
    results = {}
    for s in stocks:
        name = s.get("name",str(s)) if isinstance(s,dict) else str(s)
        code = s.get("code","") if isinstance(s,dict) else ""
        results[code or name] = search_sentiment(name, code)
        time.sleep(0.3)
    return results
