#!/usr/bin/env python3
"""signal_generator.py - Layer 3"""
import os, json, logging
from datetime import datetime, timezone, timedelta

from _path_setup import ensure_ie_paths
ensure_ie_paths()
from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES


DIR = os.path.dirname(os.path.abspath(__file__))
TRACK = str(TRACKING)  # from env
SIG_DIR = os.path.join(DIR, "signals")
SIG_LOG = os.path.join(DIR, "signal_log.jsonl")
os.makedirs(SIG_DIR, exist_ok=True)

CODES = ["000725","688981","688072","600584","688126","002371","688012","300433","002049","300308"]
NAMES = {"000725":"京东方A","688981":"中芯国际","688072":"拓荆科技","600584":"长电科技","688126":"沪硅产业","002371":"北方华创","688012":"中微公司","300433":"蓝思科技","002049":"紫光国微","300308":"中际旭创"}

def load_impact():
    d = os.path.join(DIR, "impacts")
    if not os.path.exists(d): return {}, {}
    fs = sorted([f for f in os.listdir(d) if f.startswith("impact_")], reverse=True)
    if not fs: return {}, {}
    with open(os.path.join(d, fs[0]), "r", encoding="utf-8") as f:
        r = json.load(f)
    return r, r.get("aggregate_impact", {})

def load_scores():
    if not os.path.exists(TRACK): return None
    sc = sorted([f for f in os.listdir(TRACK) if f.startswith("scan_") and f.endswith(".json")], reverse=True)
    if not sc: return None
    with open(os.path.join(TRACK, sc[0]), "r", encoding="utf-8") as f: s = json.load(f)
    r = {}
    for c, v in s.get("results", {}).items():
        fx = v.get("factors", {})
        r[c] = {"total": fx.get("total_score", 50), "gain": fx.get("gain_20d", 0), "vr": fx.get("vol_ratio", 1.0)}
    return r

def gen(code, scores, agg):
    fx = scores.get(code, {"total": 50, "gain": 0, "vr": 1.0})
    base = fx.get("total", 50); gain = fx.get("gain", 0) or 0; vr = fx.get("vr", 1.0) or 1.0
    nb = sum(agg.get(k, 0) * 0.4 for k in agg if k in ("趋势", "资金"))
    adj = base + nb
    fw_composite = 0.0; fw_vp_stage = ""; fw_adj = 0.0; hard_reject = False
    try:
        import subprocess, json
        _DIR = os.path.dirname(os.path.abspath(__file__))
        _CLI = os.path.join(_DIR, "framework_score_cli.py")
        r = subprocess.run(['python', _CLI, code],
            capture_output=True, text=True, timeout=60,
            cwd=os.path.dirname(_DIR))
        if r.returncode == 0:
            for line in r.stdout.split('\n'):
                line = line.strip()
                if line.startswith('{'):
                    fw = json.loads(line)
                    fw_adj = fw.get("adjustment", 0.0)
                    adj = adj * (1 + fw_adj)
                    hard_reject = fw.get("hard_reject", False)
                    fw_composite = fw.get("composite", 0.0)
                    fw_vp_stage = fw.get("vp_stage", "")
                    break
    except Exception:
        pass
    safe_lvl = "极低" if gain > 80 else ("低" if gain > 50 else ("中" if gain < 25 else "低"))
    cycle = "派发" if gain > 60 else ("公众参与" if gain > 25 else "吸筹")
    bias = (1 if gain > 40 else 0) + (1 if gain > 20 and safe_lvl == "低" else 0)
    passes = sum([1 if base >= 45 else 0, 1 if gain < 80 else 0, 1 if gain <= 60 else 0, 1 if bias <= 1 else 0, 1 if (vr or 1.0) >= 0.8 else 0])
    sig = "SELL"
    if hard_reject:
        sig, conf = "SELL", 0.05
    elif adj >= 55 and gain < 80 and passes >= 3:
        sig = "BUY"
        conf = min(0.95, 0.5 + adj/200)
    elif adj >= 40 and passes >= 2:
        sig = "HOLD"
        conf = min(0.95, max(0.05, 0.5 + adj/200))
    else:
        conf = min(0.95, max(0.05, 0.5 - (50 - adj) / 200))
    risk = "高" if safe_lvl == "极低" else ("中" if safe_lvl == "低" else "低")
    return {"code": code, "name": NAMES.get(code, code), "signal": sig,
            "confidence": round(conf, 2), "score": round(adj, 1),
            "boost": round(nb, 1), "safety": safe_lvl, "cycle": cycle,
            "passes": passes, "risk": risk,
            "fw_composite": fw_composite, "fw_vp_stage": fw_vp_stage,
            "fw_adjustment": fw_adj}

def run():
    print("="*50); print(" Signal Generator"); print("="*50)
    imp, agg = load_impact(); sc = load_scores()
    if not sc:
        sc = {c: {"total": t, "gain": g, "vr": v} for c, t, g, v in [("000725",59.8,25.8,2.27),("688981",55.3,47.2,1.58),("688072",54.0,89.7,1.53),("600584",52.8,80.5,1.54),("688126",51.6,40.3,1.68),("002371",51.4,47.0,1.25),("688012",50.2,54.0,1.36),("300433",45.8,48.6,1.45),("002049",43.5,19.1,1.21),("300308",40.0,22.0,0.87)]}
        print("  Cold start: defaults")
    sigs = [gen(c, sc, agg) for c in CODES]
    for s in sigs:
        flag = "!!" if s["safety"] == "极低" else "  "
        print("  %s %s: %s (%.0f%%) score=%.1f safe=%s pass=%d/5 %s" % (s["code"], s["name"], s["signal"], s["confidence"]*100, s["score"], s["safety"], s["passes"], flag))
    result = {"date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d"), "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "signals": sigs, "portfolio": {"buys": sum(1 for s in sigs if s["signal"]=="BUY"), "holds": sum(1 for s in sigs if s["signal"]=="HOLD"), "sells": sum(1 for s in sigs if s["signal"]=="SELL")}}
    fp = os.path.join(SIG_DIR, "signal_%s.json" % result["date"])
    with open(fp, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)
    print("  Saved: %s" % fp)
    print("  B:%d H:%d S:%d" % (result["portfolio"]["buys"], result["portfolio"]["holds"], result["portfolio"]["sells"]))
    return result

if __name__ == "__main__":
    run()



# ── 信号 vs 实际对比日志（2026-05-27 新增）──
import json
from pathlib import Path
from datetime import datetime

def log_signal_vs_actual(signal: dict, actual_return: float = None):
    """记录信号vs实际走势，actual_return 由调用方事后回填"""
    entry = {
        "ts": datetime.now().isoformat(),
        "date": signal.get("date", ""),
        "ticker": signal.get("ticker", ""),
        "direction": signal.get("direction", ""),
        "confidence": signal.get("confidence", 0.0),
        "reason": signal.get("reason", ""),
        "price_at_signal": signal.get("price_at_signal", 0.0),
        "actual_return": actual_return,
        "status": "pending" if actual_return is None else "settled",
    }

def get_signal_stats(days: int = 30) -> dict:
    """获取信号统计: total, hit_rate, avg_return"""
    global SIG_LOG
    log_fp = Path(SIG_LOG)
    if not log_fp.exists():
        return {"total": 0, "hit_rate": 0.0, "avg_return": 0.0}
    records = []
    with open(SIG_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception as e:
                    logging.getLogger(__name__).warning(f"  生成跳过: {e}")
    settled = [r for r in records if r.get("status") == "settled" and r.get("actual_return") is not None]
    if not settled:
        return {"total": len(records), "hit_rate": 0.0, "avg_return": 0.0}
    hits = sum(1 for r in settled if (r["direction"] == "long" and r["actual_return"] > 0) or
                                       (r["direction"] == "short" and r["actual_return"] < 0))
    return {
        "total": len(records),
        "settled": len(settled),
        "hit_rate": round(hits / len(settled), 4),
        "avg_return": round(sum(r["actual_return"] for r in settled) / len(settled), 4),
    }
