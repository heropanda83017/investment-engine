import logging
log = logging.getLogger(__name__)
#!/usr/bin/env python3
"""startup_pipeline.py — 开机自检+智能补跑
在用户登录时触发，检查哪些本轮未运行，按顺序补跑。
幂等设计：已完成的任务跳过，仅补未完成的步骤。"""

import os, sys, json, subprocess, time
from datetime import datetime, timezone, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.join(DIR, "news_db")
IMPACTS_DIR = os.path.join(DIR, "impacts")
SIG_DIR = os.path.join(DIR, "signals")
ARCHIVE_DIR = os.path.join(DIR, "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

def today():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

def is_done(dir_path, prefix, date_str=None):
    """检查某日任务是否已完成
    支持: 扁平目录(impacts/signals) 和 嵌套目录(news_db/YYYY/MM/)"""
    d = date_str or today()
    if not os.path.exists(dir_path): return False
    # 扁平目录: 直接搜 prefix + date
    if any(f.startswith(prefix) and d in f for f in os.listdir(dir_path)):
        return True
    # 嵌套目录: news_db/YYYY/MM/YYYY-MM-DD.json
    yr, mo = d[:4], d[5:7]
    nested = os.path.join(dir_path, yr, mo)
    if os.path.exists(nested):
        for f in os.listdir(nested):
            if f.startswith(d) and f.endswith('.json'):
                return True
    return False

def run_script(name, label):
    fp = os.path.join(DIR, name)
    if not os.path.exists(fp):
        print("  [SKIP] %s not found" % name); return True
    print("  [RUN] %s: %s" % (label, name))
    t0 = time.time()
    r = subprocess.run([sys.executable, fp], capture_output=True, text=True, timeout=120, cwd=DIR)
    el = time.time()-t0
    ok = r.returncode == 0
    if ok:
        print("    OK in %.1fs" % el)
    else:
        print("    FAIL (exit=%d) in %.1fs" % (r.returncode, el))
        if r.stderr: print("    ERR: %s" % r.stderr[:300])
    return ok

def check_and_run():
    td = today()
    print("="*50)
    print(" Startup Pipeline — %s" % td)
    print("="*50)
    print()
    # Step 0: 归档前一日产出
    ar_script = os.path.join(DIR, "daily_archive.py")
    if os.path.exists(ar_script):
        run_script("daily_archive.py", "Archive")

    # Step 1: 新闻采集
    news_needed = not is_done(NEWS_DIR, td, td)
    if news_needed:
        run_script("news_pipeline.py", "L1: News Fetch")
    else:
        print("  [SKIP] news: already fetched today")

    # Step 2: 新闻影响映射
    impact_needed = not is_done(IMPACTS_DIR, "impact_", td)
    if impact_needed and (news_needed or is_done(NEWS_DIR, td, td)):
        run_script("news_factor_mapper.py", "L2: Mapper")
    else:
        print("  [SKIP] mapper: already done or no news")

    # Step 3: 信号生成
    sig_needed = not is_done(SIG_DIR, "signal_", td)
    if sig_needed:
        run_script("signal_generator.py", "L3: Signal")
    else:
        print("  [SKIP] signal: already generated today")

    print()
    print("="*50)
    # Summary
    news_ok = is_done(NEWS_DIR, td, td)
    impact_ok = is_done(IMPACTS_DIR, "impact_", td)
    sig_ok = is_done(SIG_DIR, "signal_", td)
    print(" Summary: News=%s Mapper=%s Signal=%s" % (
        "OK" if news_ok else "MISS", "OK" if impact_ok else "MISS", "OK" if sig_ok else "MISS"))
    print("="*50)

if __name__ == "__main__":
    try:
        check_and_run()
    except Exception as e:
        log.error(f"启动流水线失败: {e}")
        raise