#!/usr/bin/env python3
"""IC历史回填 — 从历史K线计算各因子月度IC，持久化到factor_tracker"""

import sys, os, logging
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, str(IE_SCRIPTS))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("ic_backfill")

# 候选池：从缓存筛选结果取前200只流动性最好的
CACHE_FILE = Path(__file__).parent / "data" / "cache" / "screened_stocks.csv"
FOCUS_CODES = [
    "688981","688012","600584","002371","688072","300308","300502","300394",
    "002230","688111","600519","000858","000333","300124","002594","300750",
    "600036","000725","603501","002049","688126","300274","300433","002475",
    "601012","300760","000001","002415","300015","002352",
]

def backfill_ic():
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from fetch_data import DataEngine
    from build_features import FactorScorer
    from factor_tracker import FactorTracker, _spearmanr

    de = DataEngine()
    ft = FactorTracker()

    # 加载数据
    price_data = {}
    for code in FOCUS_CODES:
        try:
            df = de.ol.get_kline(code, days=500)
            if df is not None and not df.empty and len(df) > 200:
                price_data[code] = df
        except:
            continue
    log.info(f"数据加载: {len(price_data)}/{len(FOCUS_CODES)} 只")

    # 按月份划分窗口
    all_dates = sorted(set().union(*[set(d.index) for d in price_data.values()]))
    if not all_dates:
        log.error("无日期数据")
        return

    # 每20交易日为一个窗口
    window_size = 20
    step = 20
    ic_records = {f: [] for f in ["trend","volume","volatility","capital","fundamental","sentiment"]}

    for start_idx in range(0, len(all_dates) - window_size * 2, step):
        mid = start_idx + window_size
        end = min(mid + window_size, len(all_dates))

        train_dates = all_dates[start_idx:mid]
        test_dates_set = set(all_dates[mid:end])

        if len(train_dates) < 10 or len(test_dates_set) < 5:
            continue

        scorer = FactorScorer()
        scores_at_mid = {}
        prices_at_mid = {}
        prices_at_end = {}

        for code in price_data:
            kline = price_data[code]
            # 取训练期最后一天的价格
            train_idx = [i for i, d in enumerate(kline.index) if d in train_dates]
            test_idx = [i for i, d in enumerate(kline.index) if d in test_dates_set]
            if not train_idx or not test_idx:
                continue
            try:
                r = scorer.score_stock(code, kline)
                scores_at_mid[code] = r["factors"]
                prices_at_mid[code] = kline.iloc[train_idx[-1]]["收盘"]
                prices_at_end[code] = kline.iloc[test_idx[-1]]["收盘"]
            except:
                continue

        if len(scores_at_mid) < 10:
            continue

        # 计算各因子IC
        codes_list = list(scores_at_mid.keys())
        for fname in ["trend","volume","volatility","capital","fundamental","sentiment"]:
            f_scores = np.array([scores_at_mid[c].get(fname, {}).get("score", 0) for c in codes_list])
            # 实际收益
            fwd_returns = np.array([
                (prices_at_end.get(c, 0) / prices_at_mid.get(c, 1) - 1)
                for c in codes_list
            ])
            valid = (f_scores != 0) & (fwd_returns != 0) & ~np.isnan(fwd_returns)
            if valid.sum() >= 15:
                ic = _spearmanr(f_scores[valid], fwd_returns[valid])
                ft.compute_ic(fname, pd.Series(f_scores[valid]), pd.Series(fwd_returns[valid]),
                             lookback_days=window_size)
                ic_records[fname].append(ic)
                log.info(f"  {all_dates[mid]} {fname}: IC={ic:.3f} (n={valid.sum()})")

    # 汇总
    print(f"\nIC回填完成:")
    for fname, ics in ic_records.items():
        if ics:
            print(f"  {fname}: {len(ics)}期, 平均IC={np.mean(ics):.3f}, "
                  f"正IC率={sum(1 for i in ics if i>0)/len(ics):.0%}")
    ft._save_history()
    print(f"\nIC历史已持久化: {sum(len(v) for v in ft._history.values())} 条记录")

if __name__ == "__main__":
    backfill_ic()
