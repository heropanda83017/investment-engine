
"""weekly_review.py — 周复盘报告生成"""
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

from report import render_html, save_report, make_table, make_metric_row
from signal_generator import get_signal_stats
from ic_analyzer import calc_icir, factor_stability_score
from ic_report import generate_factor_summary

from env import IE_ROOT


def generate_weekly_review(factors_ic: dict = None,
                           strategy_pnl: pd.Series = None,
                           adjustments: list = None,
                           report_date: str = "") -> str:
    """生成周复盘报告

    Parameters
    ----------
    factors_ic : dict, optional
        {factor_name: pd.Series(IC历史)}
    strategy_pnl : pd.Series, optional
        策略周净值序列
    adjustments : list, optional
        下周调整建议列表

    Returns
    -------
    str : HTML 文件路径
    """
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    sections = []

    # ── 1. 本周概览 ──
    metrics = [("报告周期", f"本周 {report_date}", "")]
    if strategy_pnl is not None and len(strategy_pnl) > 0:
        weekly_ret = strategy_pnl.iloc[-1] / strategy_pnl.iloc[0] - 1 if len(strategy_pnl) >= 2 else 0
        cls = "good" if weekly_ret > 0 else "bad"
        metrics.append(("周收益", f'{weekly_ret*100:.2f}%', cls))

    sections.append({
        "heading": "本周概览",
        "content": make_metric_row(metrics),
        "images": []
    })

    # ── 2. 信号表现 ──
    stats = get_signal_stats(days=7)
    if stats["total"] > 0:
        hit_rate = f'{stats["hit_rate"]*100:.1f}%'
        hit_cls = "good" if stats["hit_rate"] > 0.5 else ("warn" if stats["hit_rate"] > 0.3 else "bad")
        sig_metrics = [
            ("本周信号", str(stats["total"]), ""),
            ("命中率", hit_rate, hit_cls),
            ("平均收益", f'{stats["avg_return"]*100:.2f}%', "good" if stats["avg_return"] > 0 else "bad"),
        ]
        sections.append({
            "heading": "本周信号表现",
            "content": make_metric_row(sig_metrics),
            "images": []
        })

    # ── 3. 因子 IC 周报（依赖方向A） ──
    if factors_ic and len(factors_ic) > 0:
        summary_text = generate_factor_summary(factors_ic)
        # 生成 IC 柱状图（复用 report.py 的 plot_ic_bar）
        from report import plot_ic_bar
        latest_ic = {name: series.iloc[-1] for name, series in factors_ic.items() if len(series) > 0}
        if latest_ic:
            ic_series = pd.Series(latest_ic)
            img = plot_ic_bar(ic_series.sort_values())
            sections.append({
                "heading": "因子 IC 周报",
                "content": summary_text.replace("\\n", "<br>"),
                "images": [img]
            })

    # ── 4. 调整建议 ──
    if adjustments:
        adj_html = "<ul>" + "".join(f"<li>{a}</li>" for a in adjustments) + "</ul>"
        sections.append({
            "heading": "下周调整建议",
            "content": adj_html,
            "images": []
        })

    # ── 组装 ──
    html = render_html(f"周复盘 - {report_date}", sections, report_date)
    path = save_report(html, report_type="weekly", subdir="weekly")
    return path
