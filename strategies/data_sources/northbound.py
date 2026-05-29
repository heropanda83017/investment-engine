"""
northbound.py — hsgt_realtime, _northbound_cache_path, _save_northbound_snapshot, _load_northbound_history
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
import os
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

def hsgt_realtime() -> pd.DataFrame:
    """
    """
# === 自缓存辅助函数 ===
# ===== Test: hsgt_realtime =====
#         沪深股通当日实时分钟流向（含集合竞价 09:10–15:00，262 个时间点）。
#         返回字段: time, hgt(沪股通累计净买入), sgt(深股通累计净买入)
#         单位: 亿元
#         url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
#         r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
#         d = r.json()
#         times = d.get("time", [])
#         hgt = d.get("hgt", [])
#         sgt = d.get("sgt", [])
#
#         n = len(times)
#         return pd.DataFrame({
#             "time": times,
#             "hgt_yi": hgt[:n] + [None] * (n - len(hgt)),
#             "sgt_yi": sgt[:n] + [None] * (n - len(sgt)),
#         })




def _northbound_cache_path() -> Path:
    """北向资金本地 CSV 缓存路径"""
# ===== Test: _northbound_cache_path =====
#         p = Path.home() / ".tradingagents" / "cache" / "northbound_daily.csv"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         return p



def _save_northbound_snapshot(date: str, hgt: float, sgt: float):
    """写入/更新当天北向收盘数据到 CSV"""
# ===== Test: _save_northbound_snapshot =====
#         path = _northbound_cache_path()
#         rows = {}
#         if path.exists():
#             for line in path.read_text().strip().split("\n")[1:]:
#                 parts = line.split(",")
#                 if len(parts) == 3:
#                     rows[parts[0]] = line
#         rows[date] = f"{date},{hgt},{sgt}"
#         with open(path, "w") as f:
#             f.write("date,hgt,sgt\n")
#             for d in sorted(rows.keys()):
#                 f.write(rows[d] + "\n")



def _load_northbound_history(n: int = 20) -> pd.DataFrame:
    """读取最近 N 天北向历史"""
# 用法 1: 实时分钟流向
# 用法 2: 自动缓存今日收盘数据
# 用法 3: 读取历史
# ===== Test: _load_northbound_history =====
#         path = _northbound_cache_path()
#         if not path.exists():
#             return pd.DataFrame()
#         df = pd.read_csv(path)
#         return df.tail(n)
#
#     df = hsgt_realtime()
#     print(f"分钟点数: {len(df)}")
#     print(df.tail(5))
#
#     if not df.empty:
#         last = df.dropna().iloc[-1]
#         _save_northbound_snapshot("2026-05-17", last["hgt_yi"], last["sgt_yi"])
#
#     hist = _load_northbound_history(20)
#     print(hist)



import requests

# ===== Test: baidu_pae_init =====
#     _BAIDU_PAE_HEADERS = {
#         "Host": "finance.pae.baidu.com",
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0",
#         "Accept": "application/vnd.finance-web.v1+json",
#         "Origin": "https://gushitong.baidu.com",
#         "Referer": "https://gushitong.baidu.com/",
#     }



