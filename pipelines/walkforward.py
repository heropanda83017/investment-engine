#!/usr/bin/env python3
"""Walk-Forward 滚动回测 — 验证策略在不同市场周期下的稳定性"""

import sys, os, json, logging
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

try:
    from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES
except ImportError:
    from pathlib import Path
    DATA_ROOT = Path(__file__).parent.parent
    IE_SCRIPTS = DATA_ROOT / "scripts"
    IE_STRATEGIES = DATA_ROOT / "strategies"
    IE_PIPELINES = DATA_ROOT / "pipelines"
    BH_CACHE = DATA_ROOT / "data" / "cache"
    BH_REPORTS = DATA_ROOT / "reports"
    TRACKING = DATA_ROOT / "tracking"
    SYSTEM = DATA_ROOT / "system"
    XHS_REPORT = DATA_ROOT / "reports"
    XHS_SCORES = DATA_ROOT / "data"
    WX_ARTICLES = DATA_ROOT / "data"


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(IE_SCRIPTS))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("walkforward")

FOCUS_CODES = ["688981","688012","600584","002371","688072",
    "300308","300502","300394","002230","600519",
    "000858","000333","300124","002594","300750",
    "600036","603501","002049","688126","000725"]


def run():
    from fetch_data import DataEngine
    from build_features import FactorScorer
    from backtest import run_portfolio, PerformanceMetrics

    de = DataEngine()
    price_data = {}
    for code in FOCUS_CODES:
        try:
            df = de.ol.get_kline(code, days=500)
            if df is not None and not df.empty and len(df) > 200:
                price_data[code] = df
        except: pass

    log.info(f"数据加载: {len(price_data)}/{len(FOCUS_CODES)}")

    all_dates = sorted(set().union(*[set(d.index) for d in price_data.values()]))
    window_size, step = 120, 20
    results = []

    for start in range(0, len(all_dates) - window_size - step, step):
        end = start + window_size
        test_end = min(end + step, len(all_dates))
        if test_end - end < 5: continue

        train_dates = all_dates[start:end]
        test_dates = all_dates[end:test_end]
        assert train_dates[-1] < test_dates[0], f"数据泄露: 训练期结束 {train_dates[-1]} >= 测试期开始 {test_dates[0]}"
        
        # 训练期: 用 train 数据评分（关键修复：不接触测试期数据）
        scorer = FactorScorer()
        scored = []
        for c in price_data:
            df_train = price_data[c]
            if train_dates[0] in df_train.index and train_dates[-1] in df_train.index:
                df_restricted = df_train.loc[train_dates[0]:train_dates[-1]]
                try:
                    score = scorer.score_stock(c, df_restricted)["total_score"]
                    scored.append((score, c))
                except Exception:
                    continue
        scored.sort(reverse=True)
        top5 = [c for _, c in scored[:5]]

        if len(top5) >= 3:
            # 测试期: 仅在 test_dates 上回测（关键修复：不使用训练期数据）
            test_price_data = {}
            for c in top5:
                if c in price_data and test_dates[0] in price_data[c].index:
                    df_test = price_data[c].loc[test_dates[0]:]
                    if len(df_test) >= 5:
                        test_price_data[c] = df_test
            if len(test_price_data) >= 3:
                bt = run_portfolio(list(test_price_data.keys()), test_price_data, top_n=min(3, len(test_price_data)), rebalance_days=10)
            ret = bt.get("return_pct", 0)
            dv = bt.get("daily_values", [])
            sharpe = 0.0
            if dv and len(dv) > 1:
                dr = pd.Series([(dv[i]/dv[i-1]-1) for i in range(1,len(dv))])
                sharpe = PerformanceMetrics.sharpe_ratio(dr)
            results.append({
                "window": f"{all_dates[start]}~{all_dates[min(test_end-1,len(all_dates)-1)]}",
                "return_pct": ret, "sharpe": round(sharpe, 3), "stocks": len(scored)
            })

    report = {"method": "walk_forward", "windows": results,
              "summary": {"count": len(results), "avg_return": round(float(np.mean([r["return_pct"] for r in results])), 2) if results else 0}}
    out = Path(__file__).parent.parent / "reports" / "backtest" / f"walkforward_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f: json.dump(report, f, indent=2)
    # ── WF 可视化报告（2026-05-27 新增）──
    try:
        from strategies.backtest_report import generate_backtest_report
        # 取最后一段结果为全样本模拟
        all_returns = []
        for w in results:
            all_returns.append(float(w.get("return_pct", 0)) / 100)
        if all_returns:
            from backtest import PerformanceMetrics
            import numpy as np
            pm = PerformanceMetrics.all_metrics(np.array(all_returns)) if hasattr(PerformanceMetrics, 'all_metrics') else {"sharpe": 0}
            html_path = generate_backtest_report(
                returns=np.array(all_returns),
                metrics=pm,
                strategy_name="walkforward",
                report_date=datetime.now().strftime("%Y-%m-%d")
            )
            print(f"  WF 报告: {html_path}")
    except Exception as e:
        log.warning(f"WF 报告生成跳过: {e}")

    print(f"Walk-Forward 完成: {len(results)} 窗口, 报告: {out}")
    return report

if __name__ == "__main__":
    run()
