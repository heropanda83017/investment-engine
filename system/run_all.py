#!/usr/bin/env python3
"""run_all.py - Pipeline orchestrator"""
import os, sys, subprocess, time, logging

log = logging.getLogger(__name__)
DIR = os.path.dirname(os.path.abspath(__file__))
STEPS = [("news_pipeline.py","L1:News"),("news_factor_mapper.py","L2:Mapper"),("signal_generator.py","L3:Signal")]

def run_one(script, label):
    fp = os.path.join(DIR, script)
    if not os.path.exists(fp): print("[run] SKIP %s" % script); return True
    print("\n" + "="*50)
    print(" [%s] %s" % (label, script))
    print("="*50)
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, fp], capture_output=True, text=True, timeout=120, cwd=DIR)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning(f"  subprocess 调用失败: {e}")
        return False
    print(r.stdout)
    if r.stderr: print("ERR: %s" % r.stderr[:300])
    print("  Done %.1fs exit=%d" % (time.time()-t0, r.returncode))
    return r.returncode == 0

if __name__ == "__main__":
    print("="*50); print(" Full Pipeline"); print("="*50)
    for s,l in STEPS:
        if not run_one(s,l): print("FAIL at %s" % s); break
    print("\nDone")
