"""
common.py — get_prefix, _claw_headers, dedup_articles
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import re
import os
from pathlib import Path
import secrets
import requests

def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀"""
# ===== Test: get_prefix =====
#         if code.startswith(("6", "9")):
#             return "sh"
#         elif code.startswith("8"):
#             return "bj"
#         else:
#             return "sz"



import requests

# ===== Test: eastmoney_datacenter =====
#     UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
#     DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"



def _claw_headers(call_type: str = "normal") -> dict:
    """SkillHub 2.0 必须的 X-Claw 鉴权头"""
# ===== Test: _claw_headers =====
#         return {
#             "X-Claw-Call-Type": call_type,
#             "X-Claw-Skill-Id": "report-search",
#             "X-Claw-Skill-Version": "2.0.0",
#             "X-Claw-Plugin-Id": "none",
#             "X-Claw-Plugin-Version": "none",
#             "X-Claw-Trace-Id": secrets.token_hex(32),
#         }



def dedup_articles(articles: list[dict]) -> list[dict]:
    """同一uid仅保留score最高的段落"""
# 用法: NL语义搜索研报
# ===== Test: dedup_articles =====
#         best = {}
#         for a in articles:
#             uid = a.get("uid", "") or f"{a.get('title','')}|{a.get('publish_date','')}"
#             score = float(a.get("score", 0))
#             if uid not in best or score > float(best[uid].get("score", 0)):
#                 best[uid] = a
#         return sorted(best.values(), key=lambda x: x.get("publish_date", ""), reverse=True)
#
#     articles = iwencai_search("人形机器人 行星滚柱丝杠 2026", channel="report", size=50)
#     articles = dedup_articles(articles)
#     for a in articles[:5]:
#         extra = a.get("extra") or {}
#         if isinstance(extra, str):
#             extra = json.loads(extra)
#         print(f"{a.get('publish_date','')[:10]} | {extra.get('organization','')} | {a.get('title','')[:60]}")



import requests
import pandas as pd


