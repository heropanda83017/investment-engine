"""
ths_source.py — ths_eps_forecast, ths_hot_reason, iwencai_search, iwencai_query
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
import os
import json
import secrets
import pandas as pd
from pathlib import Path

def ths_eps_forecast(code: str) -> pd.DataFrame:
    """
    """
    # 找含"每股收益"的表格
    # fallback: 返回第一个表
# 用法
# "预测机构数" < 3 的要谨慎
# ===== Test: ths_eps_forecast =====
#         同花顺机构一致预期EPS。
#         直连 basic.10jqka.com.cn，解析HTML表格。
#         返回 DataFrame: 年度, 预测机构数, 最小值, 均值, 最大值
#         "均值" = 机构一致预期EPS
#         url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
#         headers = {
#             "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
#             "Referer": "https://basic.10jqka.com.cn/",
#         }
#         r = requests.get(url, headers=headers, timeout=15)
#         r.encoding = "gbk"
#         dfs = pd.read_html(StringIO(r.text))
#         for df in dfs:
#             cols = [str(c) for c in df.columns]
#             if any("每股收益" in c or "均值" in c for c in cols):
#                 return df
#         return dfs[0] if dfs else pd.DataFrame()
#
#     df = ths_eps_forecast("688017")
#     print(df)



import os
import json
import secrets
import requests

# ===== Test: iwencai_init =====
#     IWENCAI_BASE = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
#     IWENCAI_KEY = os.environ.get("IWENCAI_API_KEY", "")



def ths_hot_reason(date: str = None) -> pd.DataFrame:
    """
    """
# ===== Test: ths_hot_reason =====
#         同花顺当日强势股归因。
#         date: 'YYYY-MM-DD' 格式，None=今天
#         返回 DataFrame，含每只股票的题材标签 (reason)。
#
#         实测: 73ms 拿到 ~125 只 + 完整字段
#
#     from datetime import date as _date
#     # 字段重命名（中文友好）
# 用法
# ===== Test: ths_hot_reason =====
#         if date is None:
#             date = _date.today().strftime("%Y-%m-%d")
#
#         url = (
#             f"http://zx.10jqka.com.cn/event/api/getharden/"
#             f"date/{date}/orderby/date/orderway/desc/charset/GBK/"
#         )
#         headers = {
#             "User-Agent": (
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                 "Chrome/117.0.0.0 Safari/537.36"
#             )
#         }
#         r = requests.get(url, headers=headers, timeout=10)
#         data = r.json()
#         if data.get("errocode", 0) != 0:
#             raise RuntimeError(f"同花顺热点错误: {data.get('errormsg', '')}")
#
#         rows = data.get("data") or []
#         df = pd.DataFrame(rows)
#         if df.empty:
#             return df
#
#         rename_map = {
#             "name": "名称", "code": "代码", "reason": "题材归因",
#             "close": "收盘价", "zhangdie": "涨跌额", "zhangfu": "涨幅%",
#             "huanshou": "换手率%", "chengjiaoe": "成交额",
#             "chengjiaoliang": "成交量", "ddejingliang": "大单净量",
#             "market": "市场",
#         }
#         df = df.rename(columns=rename_map)
#         return df
#
#     df = ths_hot_reason("2026-05-09")
#     print(f"当日强势股: {len(df)} 只")
#     print(df[["代码", "名称", "涨幅%", "题材归因"]].head(10))



import requests
import pandas as pd
from pathlib import Path

# ===== Test: hsgt_init =====
#     HSGT_HEADERS = {
#         "User-Agent": (
#             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#             "Chrome/117.0.0.0 Safari/537.36"
#         ),
#         "Host": "data.hexin.cn",
#         "Referer": "https://data.hexin.cn/",
#     }



def iwencai_search(query: str, channel: str = "report", size: int = 50) -> list[dict]:
    """
    """
# ===== Test: iwencai_search =====
#         iwencai 语义搜索。
#         channel: "report"(研报) / "announcement"(公告) / "news"(新闻)
#         size: 默认10, 实测可调到50（隐藏参数）
#         headers = {
#             "Authorization": f"Bearer {IWENCAI_KEY}",
#             "Content-Type": "application/json",
#             **_claw_headers(),
#         }
#         payload = {
#             "channels": [channel],
#             "app_id": "AIME_SKILL",
#             "query": query,
#             "size": size,
#         }
#         r = requests.post(
#             f"{IWENCAI_BASE}/v1/comprehensive/search",
#             json=payload, headers=headers, timeout=30,
#         )
#         if r.status_code != 200:
#             raise RuntimeError(f"iwencai HTTP {r.status_code}: {r.text[:200]}")
#         data = r.json()
#         if data.get("status_code", 0) != 0:
#             raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
#         return data.get("data") or []



def iwencai_query(query: str, page: int = 1, limit: int = 50) -> list[dict]:
    """
    """
# ===== Test: iwencai_query =====
#         iwencai NL数据查询（结构化字段）。
#         例: "贵州茅台 ROE" → DataFrame-like rows
#         headers = {
#             "Authorization": f"Bearer {IWENCAI_KEY}",
#             "Content-Type": "application/json",
#             **_claw_headers(),
#         }
#         payload = {
#             "query": query,
#             "page": str(page),
#             "limit": str(limit),
#             "is_cache": "1",
#             "expand_index": "true",
#         }
#         r = requests.post(
#             f"{IWENCAI_BASE}/v1/query2data",
#             json=payload, headers=headers, timeout=30,
#         )
#         if r.status_code != 200:
#             raise RuntimeError(f"iwencai HTTP {r.status_code}: {r.text[:200]}")
#         data = r.json()
#         if data.get("status_code", 0) != 0:
#             raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
#         return data.get("datas") or []



