#!/usr/bin/env python3
"""run_deep_analysis.py — 单股深度分析包装器"""
import sys, os, json

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_ROOT, "scripts")
_STRATEGIES = os.path.join(_ROOT, "strategies")
for p in [_ROOT, _SCRIPTS, _STRATEGIES]:
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(_ROOT)

from scripts.data_optimizer import OptimizedDataLayer
from strategies.deep_analysis import analyze_stock_full
from strategies.framework_scorer import score_all_frameworks

code = sys.argv[1] if len(sys.argv) > 1 else "600076"
name = sys.argv[2] if len(sys.argv) > 2 else ""

ol = OptimizedDataLayer()
result = analyze_stock_full(code, name, ol)

try:
    fw = result.get("frameworks", {})
    scored = score_all_frameworks(fw)
    result["_fw_composite"] = scored.get("composite", 0.0)
    result["_fw_details"] = scored.get("details", [])
except Exception:
    result["_fw_composite"] = 0.0
    result["_fw_details"] = []

print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
