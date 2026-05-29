#!/usr/bin/env python3
"""
blackhorse-ai 每日自动化流水线
==============================
由 cronjob 定时触发：screen → rank → report → risk check
"""

import os, sys, json, logging
from pathlib import Path
import pandas as pd
from datetime import datetime

# ---- 路径 ----
# 确保根目录在 sys.path 中（cronjob 运行时脚本目录是 pipelines/，不是根目录）
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPT_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from _path_setup import ensure_ie_paths
ensure_ie_paths()
from env import IE_ROOT, BH_REPORTS, IE_CACHE
from strategies.stage_reporter import (
    create_report, save_report, verify_gate, get_pipeline_summary,
    format_summary_text, STAGE_DEFINITIONS, STAGE_ORDER
)


LOG_DIR = IE_ROOT / "logs"
REPORT_DIR = BH_REPORTS / "daily"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("pipeline")


def run_pipeline():
    """每日流水线：data → rank → report → risk → deep"""
    log = logging.getLogger("pipeline")
    today = datetime.now().strftime("%Y-%m-%d")
    log.info("=" * 50)
    log.info(f"每日流水线启动 | {today}")
    log.info("=" * 50)

    # ── S01: 数据采集 ──
    log.info("[1/6] 并发筛选全市场...")
    try:
        from fetch_data import DataEngine
        de = DataEngine()
        stocks = de.screen_stocks()
        log.info(f"  筛选通过: {len(stocks)} 只")
    except Exception as e:
        log.error(f"  S01 数据采集失败: {e}")
        stocks = []
        de = type('obj', (object,), {'_name_map': {}})()

    # ── S02: 因子评分 ──
    log.info("[2/6] 因子打分排名...")
    rank = []
    try:
        from score_stocks import ScoringEngine
        se = ScoringEngine(name_map=de._name_map)
        if hasattr(stocks, 'sort_values') and len(stocks) > 0:
            codes = (stocks.sort_values("amount_20d_avg", ascending=False)
                           .head(50)["code"].tolist())
            rank = se.daily_rank(codes, top_n=20)
            log.info(f"  排名完成: top={len(rank)}")
        else:
            log.warning(f"  无股票数据，跳过评分")
    except Exception as e:
        log.error(f"  S02 因子评分失败: {e}")
        rank = pd.DataFrame()

    # ── S04: 报告生成 ──
    log.info("[3/6] 生成日报...")
    from strategies.daily_review import generate_daily_review
    from pipelines.weekly_tracker import attach_to_pipeline
    try:
        report_path = generate_daily_review()
        log.info(f"  日报已生成: {report_path}")
    except Exception as e:
        log.warning(f"  日报生成跳过: {e}")

    # ── S05: 风控检查 ──
    log.info("[4/6] 风控检查...")
    try:
        from risk_manager import RiskController
        rc = RiskController()
        if not rank.empty:
            total_val = 1000000
            pos_count = min(10, len(rank))
            pos_val = total_val / max(pos_count, 1)
            holdings = {r["code"]: pos_val for _, r in rank.head(pos_count).iterrows()}
            alerts = rc.check_portfolio(holdings, total_val)
            if alerts:
                log.warning(f"  风控告警: {len(alerts)} 条")
                for a in alerts:
                    log.warning(f"    [{a['level']}] {a['code']}: {a['msg']}")
        else:
            log.info("  风控正常")
    except Exception as e:
        log.warning(f"  S05 风控检查跳过: {e}")

    # ── S06: 深度分析（限 top 3）──
    log.info("[5/6] 深度21框架分析...")
    try:
        from deep_analysis import generate_deep_report
        sn = {}
        if hasattr(de, '_name_map') and de._name_map:
            sn = {k: v for k, v in de._name_map.items() if len(k) == 6}
        report = generate_deep_report(rank, sn, top_n=3)
        log.info(f"  深度报告 ({len(report)} chars)")
    except Exception as e:
        log.warning(f"  深度分析跳过: {e}")

    # ── AnySearch 情绪因子 ──
    log.info("[5b/6] AnySearch 舆情情绪...")
    try:
        from strategies.anysearch_source import search_sentiment
        sentiment_scores = {}
        for _, row in rank.head(5).iterrows():
            code = str(row.get("code", ""))
            name = de._name_map.get(code, "") if hasattr(de, '_name_map') else ""
            if code:
                s = search_sentiment(name, code)
                sentiment_scores[code] = s
                log.info(f"  {code} {name}: 情绪={s:.2f}")
        if sentiment_scores:
            csv_path = BH_REPORTS / "factors" / f"sentiment_{datetime.now().strftime('%Y%m%d')}.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            import csv
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["code", "sentiment"])
                for k, v in sentiment_scores.items():
                    w.writerow([k, v])
            log.info(f"  情绪数据已保存: {csv_path}")
    except Exception as e:
        log.warning(f"  情绪分析跳过: {e}")

    # ── wudao MCP（直连优先 → 缓存兜底）──
    log.info("[6/6] wudao MCP + tickflow 实时...")
    wudao_ok = False
    try:
        from strategies.wudao_mcp_source import get_all_market_data, market_overview
        live = market_overview()
        if live:
            all_data = get_all_market_data()
            log.info(f"  wudao MCP 直连成功")
            wudao_ok = True
        else:
            raise Exception("直连无数据")
    except Exception as e:
        log.info(f"  wudao 直连失败({e}), 读缓存...")
        try:
            from wudao_mcp_reader import gen_market_section, has_cache
            if has_cache():
                md = gen_market_section()
                if md:
                    (IE_CACHE / "wudao" / "market_section.txt").write_text(md, encoding="utf-8")
                    log.info(f"  wudao 缓存数据已读取")
                    wudao_ok = True
        except Exception as e2:
            log.warning(f"  wudao 缓存也失败: {e2}")

    # ── tickflow 实时监控 ──
    try:
        from scripts.tickflow import TickFlow
        tf = TickFlow()
        tick_data = tf.fetch_snapshot(codes=rank.head(5)["code"].tolist() if not rank.empty else [])
        if tick_data:
            import json
            tf_path = BH_REPORTS / "realtime" / "tick_snapshot.json"
            tf_path.parent.mkdir(parents=True, exist_ok=True)
            tf_path.write_text(json.dumps(tick_data, ensure_ascii=False))
            log.info(f"  tickflow 快照已保存 ({len(tick_data)} 条)")
    except Exception as e:
        log.warning(f"  tickflow 跳过: {e}")

    # ── 日复盘报告 ──
    try:
        from pipelines.weekly_tracker import attach_to_pipeline
        path = attach_to_pipeline()
        if path:
            log.info(f"  日复盘: {path}")
    except Exception as e:
        log.warning(f"  日复盘跳过: {e}")

    log.info("=" * 50)
    log.info("流水线完成")
    log.info("=" * 50)
    return True

if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)
