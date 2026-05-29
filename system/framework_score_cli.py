#!/usr/bin/env python3
"""framework_score_cli.py — 子进程调用获取框架评分（绕过 import 链问题）"""
import sys, os, json

# Ensure project root is in path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# Also add scripts/ for env, strategies/ for analysis
_SCRIPTS = os.path.join(_ROOT, "scripts")
_STRATEGIES = os.path.join(_ROOT, "strategies")
for p in [_SCRIPTS, _STRATEGIES]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(_ROOT)

if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    from strategies.deep_analysis import analyze_stock_full
    from scripts.data_optimizer import OptimizedDataLayer
    
    ol = OptimizedDataLayer()
    result = analyze_stock_full(code, "", ol)
    fw = result.get("frameworks", {})
    vp = result.get("volume_price", {})
    rc = result.get("reverse_checks", [])
    
    try:
        from strategies.framework_scorer import score_all_frameworks
        scored = score_all_frameworks(fw)
        composite = scored.get("composite", 0.0)
    except Exception:
        composite = 0.0
    
    hard_reject = result.get("hard_reject", False)
    vp_stage = vp.get("stage", "未知")
    behavioral_bias = len(fw.get("行为金融", {}).get("biases", [])) if "行为金融" in fw else 0
    reverse_flags = len(rc)
    
    adj = composite * 0.10
    if hard_reject:
        adj = -0.15
    if vp_stage == "派发":
        adj -= 0.05
    elif vp_stage == "吸筹":
        adj += 0.03
    if reverse_flags > 2:
        adj -= 0.05
    adjustment = max(-0.15, min(0.15, adj))
    
    out = {
        "composite": round(composite, 3),
        "hard_reject": hard_reject,
        "vp_stage": vp_stage,
        "moat_score": round(fw.get("护城河", {}).get("total_score", 0) if "护城河" in fw else 0, 1),
        "behavioral_bias": behavioral_bias,
        "reverse_flags": reverse_flags,
        "adjustment": round(adjustment, 3),
    }
    print(json.dumps(out, ensure_ascii=False))
