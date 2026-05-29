"""
eastmoney_source.py — eastmoney_datacenter, eastmoney_reports, download_pdf, eastmoney_fund_flow_minute, eastmoney_stock_news, eastmoney_global_news, eastmoney_stock_info, stock_fund_flow_120d
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
import urllib.request
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta
import re
import json
import pandas as pd
from mootdx.quotes import Quotes

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                         filter_str: str = "", page_size: int = 50,
                         sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用"""
    try:
        params = {
            "reportName": report_name, "columns": columns,
            "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
            "sortColumns": sort_columns, "sortTypes": sort_types,
            "source": "WEB", "client": "WEB",
        }
        r = requests.get(DATACENTER_URL, params=params, headers={"User-Agent": UA}, timeout=15)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception:
        pass
    return []


def eastmoney_reports(stock: str, page_size: int = 50) -> list[dict]:
    """拉取指定股票的研报列表"""
    # TODO: 从测试块中恢复实现
    return []


def download_pdf(report_url: str, save_dir: str = "./reports") -> str:
    """下载单份研报PDF，返回保存路径或None"""
    # TODO: 从测试块中恢复实现
    return None


def eastmoney_fund_flow_minute(code: str) -> pd.DataFrame:
    """东财资金流分钟级"""
    # TODO: 从测试块中恢复实现
    return pd.DataFrame()


def eastmoney_stock_news(code: str, page_size: int = 50) -> list[dict]:
    """东财个股新闻 — 返回: [{title, content, time, source, url}]"""
    # TODO: 从测试块中恢复实现
    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": cb, "param": f'{{"uid":"","keyword":"{code}","type":["cmsArticleWebOld"],"client":"web"}}',
        "page": "1", "size": str(page_size),
    }
    headers = {"User-Agent": UA, "Referer": "https://www.eastmoney.com/"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        text = r.text
        if text.startswith(f"{cb}(") and text.endswith(")"):
            text = text[len(cb)+1:-1]
        d = json.loads(text)
        rows = []
        for item in d.get("data", {}).get("art", []):
            rows.append({
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "time": item.get("date", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
            })
        return rows
    except Exception:
        return []


def eastmoney_global_news(page_size: int = 50) -> list[dict]:
    """东方财富全球财经资讯（7x24 滚动）"""
    # TODO: 从测试块中恢复实现
    client = Quotes.factory(market='std')
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {"fltt": "2", "secids": "1.000001,0.399001,0.399006", "fields": "f2,f3,f4,f12,f14"}
    try:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=10)
        d = r.json()
        rows = []
        for item in d.get("data", {}).get("diff", []):
            rows.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "price": item.get("f2", 0),
                "change_pct": item.get("f3", 0),
            })
        return rows
    except Exception:
        return []


def eastmoney_stock_info(code: str) -> dict:
    """东财个股基本面信息"""
    # TODO: 从测试块中恢复实现
    return {}


def stock_fund_flow_120d(code: str) -> list[dict]:
    """个股资金流（日级，最近120个交易日）"""
    # TODO: 从测试块中恢复实现
    return []
