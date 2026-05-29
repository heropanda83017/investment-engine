#!/usr/bin/env python3
"""
quick_start.py — 数据管道快速上手示例

一键运行：python quick_start.py
"""

import sys, json
sys.path.insert(0, "${AIGC_DATA_ROOT:-E:/AIGC-KB/output}/05-脚本")

from data_pipeline import get_pipeline
pl = get_pipeline()

print("=" * 55)
print("  数据管道 — 快速上手")
print("=" * 55)

# 1. K线（自动baostock -> 缓存）
k = pl.kline("600519", days=60)
print("\n1. 贵州茅台 近60日K线")
print("   Latest: %.2f" % k["收盘"].iloc[-1])
print("   High: %.2f" % k["最高"].max())
print("   Low: %.2f" % k["最低"].min())

# 2. 财务
f = pl.financial("600519")
print("\n2. 贵州茅台 财务摘要")
latest = f.iloc[-1]
print("   ROE: %.1f%%" % latest.get("净资产收益率", 0))
print("   毛利率: %.1f%%" % latest.get("销售毛利率", 0))
print("   净利率: %.1f%%" % latest.get("销售净利率", 0))

# 3. 实时
rt = pl.realtime(["600519", "002371"])
print("\n3. 实时快照")
for d in rt:
    print("   %s: %.2f (%.2f%%)" % (d["code"], d.get("price",0), d.get("change_pct",0)))

# 4. 批量对比
print("\n4. 批量分析")
df = pl.batch(["600519", "000858", "002371"])
for _, row in df.iterrows():
    print("   %s: 最新价=%.2f  ROE=%.1f%%  毛利率=%.1f%%" % (
        row["代码"], row["最新价"], row["净资产收益率"], row["销售毛利率"]))

# 5. 看板
dash = pl.dashboard()
print("\n5. 监控看板: %s" % dash)

print("\nDone! 更多功能: python data_pipeline.py --help")
