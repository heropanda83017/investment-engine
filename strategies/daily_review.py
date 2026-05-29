
"""daily_review.py — 日复盘报告生成"""
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

from report import render_html, save_report, make_table, make_metric_row
from signal_generator import get_signal_stats

from env import IE_ROOT


def generate_daily_review(factor_ics: dict = None, market_state: str = "",
                          report_date: str = "") -> str:
    """生成日复盘报告

    Parameters
    ----------
    factor_ics : dict, optional
        {factor_name: rank_ic(float)}
    market_state : str
        市场状态描述

    Returns
    -------
    str : HTML 文件路径
    """
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    sections = []

    # ── 1. 市场概览 ──
    metrics = [
        ("日期", report_date, ""),
        ("市场状态", market_state or "待判定", "warn"),
    ]
    sections.append({
        "heading": "市场概览",
        "content": make_metric_row(metrics),
        "images": []
    })

    # ── 2. 信号命中率 ──
    stats = get_signal_stats(days=30)
    if stats["total"] > 0:
        hit_rate = f'{stats["hit_rate"]*100:.1f}%'
        hit_cls = "good" if stats["hit_rate"] > 0.5 else ("warn" if stats["hit_rate"] > 0.3 else "bad")
        sig_metrics = [
            ("信号总数", str(stats["total"]), ""),
            ("已结算", str(stats.get("settled", 0)), ""),
            ("命中率", hit_rate, hit_cls),
            ("平均收益", f'{stats["avg_return"]*100:.2f}%', "good" if stats["avg_return"] > 0 else "bad"),
        ]
        sections.append({
            "heading": "信号表现",
            "content": make_metric_row(sig_metrics),
            "images": []
        })

    # ── 3. 因子表现 TOP/BOTTOM ──
    if factor_ics and len(factor_ics) > 0:
        sorted_factors = sorted(factor_ics.items(), key=lambda x: x[1], reverse=True)
        top3 = sorted_factors[:3]
        bottom3 = sorted_factors[-3:]

        rows = []
        for name, ic in top3:
            cls = "good" if ic > 0 else "bad"
            rows.append([name, f'<span class="{cls}">{ic:.4f}</span>', "TOP"])
        for name, ic in bottom3:
            cls = "good" if ic > 0 else "bad"
            rows.append([name, f'<span class="{cls}">{ic:.4f}</span>', "BOTTOM"])

        sections.append({
            "heading": "因子表现 TOP/BOTTOM 3",
            "content": make_table(["因子", "RankIC", "排名"], rows),
            "images": []
        })

    # ── 组装 ──
    html = render_html(f"日复盘 - {report_date}", sections, report_date)
    path = save_report(html, report_type="daily", subdir="daily")
    return path
