"""
ds_monitor.py — 数据源健康监控

每日开盘前运行，检查所有数据源可用性并生成报告。
"""

import time, json, logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("ds_monitor")

# 缓存目录
CACHE_DIR = Path(__file__).resolve().parent.parent / "_cache" / "monitor"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def check_baostock() -> dict:
    """检查 baostock 连通性"""
    t0 = time.time()
    try:
        import baostock as bs
        lg = bs.login()
        ok = lg.error_code == '0'
        if ok: bs.logout()
        return {"ok": ok, "ms": int((time.time()-t0)*1000), "detail": "" if ok else lg.error_msg}
    except Exception as e:
        return {"ok": False, "ms": int((time.time()-t0)*1000), "detail": str(e)[:60]}


def check_akshare() -> dict:
    """检查 akshare 连通性"""
    t0 = time.time()
    try:
        import akshare as ak
        import warnings; warnings.filterwarnings('ignore')
        df = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20260520", adjust="qfq")
        ok = len(df) > 0
        return {"ok": ok, "ms": int((time.time()-t0)*1000), "detail": f"{len(df)}条K线"}
    except Exception as e:
        return {"ok": False, "ms": int((time.time()-t0)*1000), "detail": str(e)[:60]}


def check_tushare() -> dict:
    """检查 Tushare 连通性"""
    t0 = time.time()
    try:
        import tushare as ts
        pro = ts.pro_api()
        df = pro.trade_cal(exchange="SSE", start_date="20260520", end_date="20260527")
        ok = df is not None and not df.empty
        return {"ok": ok, "ms": int((time.time()-t0)*1000), "detail": f"{len(df)}条日历" if ok else "空"}
    except Exception as e:
        return {"ok": False, "ms": int((time.time()-t0)*1000), "detail": str(e)[:60]}


def check_factorhub() -> dict:
    """检查 FactorHub 连通性"""
    t0 = time.time()
    try:
        from urllib.request import Request, urlopen
        import json
        req = Request("https://factorhub.cn/api/v1/factors?page=1&page_size=5",
            headers={"X-API-Key": "${FACTORHUB_API_KEY}",
                     "User-Agent": "investment-engine/1.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok = "data" in data
            return {"ok": ok, "ms": int((time.time()-t0)*1000), "detail": f"{data.get('total',0)}因子"}
    except Exception as e:
        return {"ok": False, "ms": int((time.time()-t0)*1000), "detail": str(e)[:60]}


def check_anysearch() -> dict:
    """检查 AnySearch 连通性"""
    t0 = time.time()
    try:
        from urllib.request import Request, urlopen
        import json
        payload = json.dumps({"query": "test", "max_results": 1}).encode("utf-8")
        req = Request("https://api.anysearch.com/v1/search", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            return {"ok": ok, "ms": int((time.time()-t0)*1000), "detail": "OK"}
    except Exception as e:
        return {"ok": False, "ms": int((time.time()-t0)*1000), "detail": str(e)[:60]}


def run_all_checks() -> dict:
    """运行全部数据源检查"""
    checks = {
        "baostock": check_baostock,
        "akshare": check_akshare,
        "tushare": check_tushare,
        "factorhub": check_factorhub,
        "anysearch": check_anysearch,
    }
    results = {}
    for name, fn in checks.items():
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = {"ok": False, "ms": -1, "detail": str(e)[:60]}
    
    # 保存到缓存
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results.values() if r["ok"]),
            "fail": sum(1 for r in results.values() if not r["ok"]),
        }
    }
    with open(CACHE_DIR / "ds_health.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def print_health_report(report: dict = None):
    """打印健康报告"""
    if report is None:
        report_path = CACHE_DIR / "ds_health.json"
        if report_path.exists():
            with open(report_path) as f:
                report = json.load(f)
        else:
            report = run_all_checks()
    
    print(f"数据源健康报告 @ {report['timestamp']}")
    print("=" * 60)
    for name, r in report["results"].items():
        icon = "✅" if r["ok"] else "❌"
        print(f"  {icon} {name:12s}: {r['ms']:4d}ms  {r['detail']}")
    print("=" * 60)
    s = report["summary"]
    print(f"  {s['ok']}/{s['total']} 可用, {s['fail']} 异常")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_all_checks()
    print_health_report(report)
