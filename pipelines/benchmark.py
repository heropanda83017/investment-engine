#!/usr/bin/env python3
"""性能基准测试 — 记录全流程选股各环节耗时"""

import sys, os, json, time
from pathlib import Path
from datetime import datetime
import pandas as pd

from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(IE_SCRIPTS))

FOCUS_CODES = ["688981","688012","600584","002371","688072",
    "300308","300502","300394","002230","600519",
    "000858","000333","300124","002594","300750",
    "600036","603501","002049","688126","000725"]

def benchmark():
    from fetch_data import DataEngine
    from build_features import FactorScorer
    from backtest import PerformanceMetrics

    results = {}
    
    t0 = time.time()
    de = DataEngine()
    price_data = {}
    for code in FOCUS_CODES:
        try:
            df = de.ol.get_kline(code, days=500)
            if df is not None and not df.empty:
                price_data[code] = df
        except: pass
    results["data_load"] = round(time.time() - t0, 2)
    
    t0 = time.time()
    scorer = FactorScorer()
    for code, df in price_data.items():
        scorer.score_stock(code, df)
    results["factor_scoring"] = round(time.time() - t0, 2)
    
    results["stocks"] = len(price_data)
    results["total"] = results.get("data_load", 0) + results.get("factor_scoring", 0)
    results["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    out = Path(__file__).parent.parent / "reports" / "backtest" / f"benchmark_{datetime.now().strftime('%Y%m%d')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    
    # ── 多基准对比（2026-05-27 新增）──
    try:
        from datetime import datetime
        import baostock as bs
        lg = bs.login()
        indices = {"sh.000300": "沪深300", "sh.000905": "中证500", "sh.000688": "科创50"}
        index_data = {}
        for code, name in indices.items():
            rs = bs.query_history_k_data_plus(code, "date,close", 
                start_date=(datetime.now() - pd.Timedelta(days=500)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d"),
                frequency="d")
            rows = []
            while rs.next():
                rows.append([rs.get_row_data()[0], rs.get_row_data()[1]])
            if rows:
                df_idx = pd.DataFrame(rows, columns=["date","close"])
                df_idx["close"] = pd.to_numeric(df_idx["close"], errors="coerce")
                df_idx["ret"] = df_idx["close"].pct_change()
                index_data[name] = {
                    "total_return": round(float(df_idx["close"].iloc[-1] / df_idx["close"].iloc[0] - 1), 4),
                    "sharpe": round(float(PerformanceMetrics.sharpe_ratio(df_idx["ret"].dropna())), 4),
                }
        bs.logout()
        results["benchmarks"] = index_data
        # 保存更新
        with open(out, "w") as f:
            json.dump(results, f, indent=2)
        for name, data in index_data.items():
            print(f"  {name}: 收益={data['total_return']*100:.1f}%, 夏普={data['sharpe']:.2f}")
    except Exception as e:
        print(f"  ⚠️ 基准对比跳过: {e}")

    print(f"\n📊 性能基准 ({results['date']})")
    print(f"  数据加载: {results['data_load']:.1f}s")
    print(f"  因子评分: {results['factor_scoring']:.1f}s")
    print(f"  股票数量: {results['stocks']}")
    print(f"  总耗时:   {results['total']:.1f}s")
    print(f"  报告: {out}")

if __name__ == "__main__":
    benchmark()
