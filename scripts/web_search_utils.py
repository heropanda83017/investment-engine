# web_search_utils
from ddgs import DDGS
import akshare as ak

def search(query, max_results=5, region="cn-zh"):
    """DuckDuckGo search (free, no API key)"""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, region=region, safesearch="moderate", max_results=max_results))
    return [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]

def US_market():
    result = {}
    try:
        df = ak.currency_boc_sina(symbol="美元")
        if not df.empty:
            result["USD_CNY_rate"] = float(df.iloc[-1]["中行折算价"])
    except:
        pass
    result["note"] = "yfinance blocked in sandbox. Use local terminal directly."
    return result