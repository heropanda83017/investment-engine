#!/usr/bin/env python3
"""
batch_analysis.py — 批量股票分析示例

分析一个完整的股票池并输出横向对比报告。
"""

import sys, os, json
from datetime import datetime
sys.path.insert(0, "${AIGC_DATA_ROOT:-E:/AIGC-KB/output}/05-脚本")

# 候选股票池（来自选股报告的候选列表）
WATCHLIST = {
    "600519": "贵州茅台",
    "000858": "五粮液",
    "002371": "北方华创",
    "300308": "中际旭创",
    "600036": "招商银行",
    "000333": "美的集团",
    "688041": "海光信息",
    "002230": "科大讯飞",
    "300124": "汇川技术",
}

from stock_analyst import StockAnalyst
sa = StockAnalyst()

print("=== 批量分析报告 ===")
print("时间: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
print("股票池: %d 只" % len(WATCHLIST))
print()

# 批量财务分析
df = sa.batch_analyze(list(WATCHLIST.keys()))
print(df.to_string())

# 生成图表
print("\n=== 生成个股图表 ===")
for code in ["600519", "002371", "300308"]:
    k_path = sa.plot_kline(code)
    f_path = sa.plot_financial(code)
    print("  %s: K线图=%s" % (code, k_path))

# 保存报告
report = {
    "time": datetime.now().isoformat(),
    "stocks": len(WATCHLIST),
    "analysis": df.to_dict("records") if not df.empty else [],
}
report_path = "${AIGC_DATA_ROOT:-E:/AIGC-KB/output}/stock_analyst_data/reports/batch_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2, default=str)
print("\n报告已保存: %s" % report_path)
print("\nDone!")
