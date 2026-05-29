#!/usr/bin/env python3
"""daily_archive.py — 日度归档 + 摘要生成
将当日新闻/影响/信号归档到 archive/YYYY-MM-DD/ 目录，
同时生成 readable 的日度摘要。"""

import os, sys, json, shutil
from datetime import datetime, timezone, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(DIR, "archive")

def yesterday():
    return (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=1)).strftime("%Y-%m-%d")

def archive_yesterday():
    yd = yesterday()
    dest = os.path.join(ARCHIVE_DIR, yd)
    if os.path.exists(dest):
        print("[archive] %s already archived" % yd); return
    os.makedirs(dest, exist_ok=True)
    files_copied = 0
    
    # 遍历news_db/impacts/signals查找匹配昨日的数据
    for src_dir, prefix in [
        (os.path.join(DIR, "news_db"), yd),
        (os.path.join(DIR, "impacts"), "impact_"),
        (os.path.join(DIR, "signals"), "signal_"),
    ]:
        if not os.path.exists(src_dir): continue
        for f in os.listdir(src_dir):
            if yd in f and f.endswith(".json"):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(dest, f))
                files_copied += 1

    if files_copied == 0:
        # 检查是否有任何数据
        print("[archive] No data for %s (possibly weekend/holiday)" % yd)
        os.rmdir(dest)
        return

    # 生成摘要
    summary = generate_summary(dest, yd)
    if summary:
        sp = os.path.join(dest, "_summary.md")
        with open(sp, "w", encoding="utf-8") as f:
            f.write(summary)

    print("[archive] %s: %d files archived -> %s" % (yd, files_copied, dest))

def generate_summary(arch_dir, date_str):
    """从归档中提取关键信息生成 readable 摘要"""
    summary = []
    summary.append("# Daily Summary — %s" % date_str)
    summary.append("")

    # 读取信号
    sig_file = os.path.join(arch_dir, "signal_%s.json" % date_str)
    if os.path.exists(sig_file):
        with open(sig_file, "r", encoding="utf-8") as f:
            sig = json.load(f)
        signals = sig.get("signals", [])
        buys = [s for s in signals if s.get("signal")=="BUY"]
        holds = [s for s in signals if s.get("signal")=="HOLD"]
        sells = [s for s in signals if s.get("signal")=="SELL"]
        summary.append("## 今日信号")
        summary.append("")
        for b in buys:
            summary.append("- BUY  %s (%.0f%%) score=%.1f safe=%s" % (
                b.get("name",""), b.get("confidence",0)*100, b.get("score",0), b.get("safety","?")))
        for h in holds:
            summary.append("- HOLD %s (%.0f%%) score=%.1f safe=%s cycle=%s" % (
                h.get("name",""), h.get("confidence",0)*100, h.get("score",0), h.get("safety","?"), h.get("cycle","?")))
        for s in sells:
            summary.append("- SELL %s (%.0f%%) score=%.1f" % (
                s.get("name",""), s.get("confidence",0)*100, s.get("score",0)))
        summary.append("")
        pf = sig.get("portfolio", {})
        summary.append("Portfolio: B=%d H=%d S=%d" % (pf.get("buys",0), pf.get("holds",0), pf.get("sells",0)))
        summary.append("")

    # 读取新闻影响
    imp_file = os.path.join(arch_dir, "impact_%s.json" % date_str)
    if os.path.exists(imp_file):
        with open(imp_file, "r", encoding="utf-8") as f:
            imp = json.load(f)
        agg = imp.get("aggregate_impact", {})
        top = sorted(agg.items(), key=lambda x: -abs(x[1]))[:5]
        summary.append("## 新闻因子冲击")
        summary.append("")
        for k,v in top:
            summary.append("- %s: %+d" % (k, v))
        summary.append("")

    return "\n".join(summary)

if __name__ == "__main__":
    archive_yesterday()