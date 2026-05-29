"""
tencent_source.py — tencent_quote
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
import urllib.request

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    """
# 用法: 个股
# 用法: 指数 — sh000001=上证指数, sh000300=沪深300, sz399006=创业板指
# 用法: ETF — sh510050=上证50ETF, sh510300=沪深300ETF
# ===== Test: tencent_quote =====
#         批量拉取腾讯财经实时行情。
#         codes: ["688017", "300476", "002463"]
#         也支持指数: ["000001", "000300", "399006"]
#         也支持ETF: ["510050", "510300"]
#         返回: {code: {name, price, pe_ttm, pb, mcap, ...}}
#         prefixed = []
#         for c in codes:
#             if c.startswith(("6", "9")):
#                 prefixed.append(f"sh{c}")
#             elif c.startswith("8"):
#                 prefixed.append(f"bj{c}")
#             else:
#                 prefixed.append(f"sz{c}")
#
#         url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
#         req = urllib.request.Request(url)
#         req.add_header("User-Agent", "Mozilla/5.0")
#         resp = urllib.request.urlopen(req, timeout=10)
#         data = resp.read().decode("gbk")
#
#         result = {}
#         for line in data.strip().split(";"):
#             if not line.strip() or "=" not in line or '"' not in line:
#                 continue
#             key = line.split("=")[0].split("_")[-1]
#             vals = line.split('"')[1].split("~")
#             if len(vals) < 53:
#                 continue
#             code = key[2:]
#             result[code] = {
#                 "name":         vals[1],
#                 "price":        float(vals[3]) if vals[3] else 0,
#                 "last_close":   float(vals[4]) if vals[4] else 0,
#                 "open":         float(vals[5]) if vals[5] else 0,
#                 "change_amt":   float(vals[31]) if vals[31] else 0,
#                 "change_pct":   float(vals[32]) if vals[32] else 0,
#                 "high":         float(vals[33]) if vals[33] else 0,
#                 "low":          float(vals[34]) if vals[34] else 0,
#                 "amount_wan":   float(vals[37]) if vals[37] else 0,
#                 "turnover_pct": float(vals[38]) if vals[38] else 0,
#                 "pe_ttm":       float(vals[39]) if vals[39] else 0,
#                 "amplitude_pct":float(vals[43]) if vals[43] else 0,
#                 "mcap_yi":      float(vals[44]) if vals[44] else 0,
#                 "float_mcap_yi":float(vals[45]) if vals[45] else 0,
#                 "pb":           float(vals[46]) if vals[46] else 0,
#                 "limit_up":     float(vals[47]) if vals[47] else 0,
#                 "limit_down":   float(vals[48]) if vals[48] else 0,
#                 "vol_ratio":    float(vals[49]) if vals[49] else 0,
#                 "pe_static":    float(vals[52]) if vals[52] else 0,
#             }
#         return result
#
#     quotes = tencent_quote(["688017", "300476", "002463"])
#     for code, q in quotes.items():
#         print(f"{q['name']}({code}): {q['price']}元 PE={q['pe_ttm']} PB={q['pb']} 市值={q['mcap_yi']}亿")
#
#     index_quotes = tencent_quote(["000001", "000300", "399006"])
#
#     etf_quotes = tencent_quote(["510050", "510300"])



import requests


