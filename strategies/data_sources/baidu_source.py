"""
baidu_source.py — baidu_kline_with_ma, baidu_concept_blocks
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
import re
import time
from pathlib import Path

def baidu_kline_with_ma(code: str, start_time: str = "") -> dict:
    """百度股市通K线 — 独有能力: 返回时自带 ma5/ma10/ma20 均价"""
# 用法
# keys 包含: time, open, close, high, low, volume, amount, ma5avgprice, ma10avgprice, ma20avgprice 等
# ===== Test: baidu_kline_with_ma =====
#         url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
#         params = {
#             "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
#             "isFutures": "false", "isStock": "true", "newFormat": "1",
#             "group": "quotation_kline_ab", "finClientType": "pc",
#             "code": code, "start_time": start_time, "ktype": "1",
#         }
#         headers = {
#             "User-Agent": "Mozilla/5.0",
#             "Accept": "application/vnd.finance-web.v1+json",
#             "Origin": "https://gushitong.baidu.com",
#             "Referer": "https://gushitong.baidu.com/",
#         }
#         r = requests.get(url, params=params, headers=headers, timeout=10)
#         d = r.json()
#         result = d.get("Result", {})
#         md = result.get("newMarketData", {})
#         keys = md.get("keys", [])  # includes: ma5avgprice, ma10avgprice, ma20avgprice
#         rows = md.get("marketData", "").split(";")
#         return {"keys": keys, "rows": rows}
#
#     data = baidu_kline_with_ma("600519")
#     print("字段:", data["keys"][:10])
#     print("最近5根K线:", data["rows"][-5:])



import requests
import re
import time
from pathlib import Path

# ===== Test: eastmoney_reports_init =====
#     REPORT_API = "https://reportapi.eastmoney.com/report/list"
#     PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
#     UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"



def baidu_concept_blocks(code: str) -> dict:
    """
    """
# 用法
# ===== Test: baidu_concept_blocks =====
#         百度股市通概念板块归属。
#         返回: {industry: [...], concept: [...], region: [...], concept_tags: [...]}
#         url = (
#             f"https://finance.pae.baidu.com/api/getrelatedblock"
#             f"?code={code}&market=ab"
#             f"&typeCode=all&finClientType=pc"
#         )
#         r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
#         d = r.json()
#         if str(d.get("ResultCode", -1)) != "0":
#             raise RuntimeError(f"百度PAE错误: {d}")
#
#         result = {"industry": [], "concept": [], "region": [], "concept_tags": []}
#         for block in d.get("Result", []):
#             block_type = block.get("type", "")
#             for item in block.get("list", []):
#                 entry = {
#                     "name": item.get("name", ""),
#                     "change_pct": item.get("increase", ""),
#                     "desc": item.get("desc", ""),
#                 }
#                 if "行业" in block_type:
#                     result["industry"].append(entry)
#                 elif "概念" in block_type:
#                     result["concept"].append(entry)
#                     result["concept_tags"].append(entry["name"])
#                 elif "地域" in block_type:
#                     result["region"].append(entry)
#         return result
#
#     blocks = baidu_concept_blocks("688017")
#     print("行业:", [b["name"] for b in blocks["industry"]])
#     print("概念:", blocks["concept_tags"])
#     print("地域:", [b["name"] for b in blocks["region"]])



import requests


