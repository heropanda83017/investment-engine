
"""ic_report.py — 生成IC报告 + 可视化图表"""
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

from report import render_html, save_report, make_table, plot_ic_bar, plot_ic_trend
from ic_analyzer import rolling_ic, factor_stability_score, ic_decay_curve, calc_icir

from env import IE_ROOT


def generate_ic_report(factors_ic: dict, report_date: str = "") -> str:
    """生成因子IC周报

    Parameters
    ----------
    factors_ic : dict
        {factor_name: pd.Series(IC历史序列)}

    Returns
    -------
    str : HTML 文件路径
    """
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    sections = []

    # ── 1. IC 概览表 ──
    rows = []
    ic_bars = {}
    for name, series in factors_ic.items():
        recent = series.iloc[-20:] if len(series) >= 20 else series
        rank_ic_5d = round(series.iloc[-5:].mean(), 4) if len(series) >= 5 else 0.0
        rank_ic_20d = round(series.iloc[-20:].mean(), 4) if len(series) >= 20 else 0.0
        icir = round(calc_icir(series), 4)
        stability = round(factor_stability_score(series), 4)

        # 趋势标记
        def _tag(v):
            if v > 0.02: return f'<span class="good">{v}</span>'
            if v < -0.02: return f'<span class="bad">{v}</span>'
            return str(v)

        rows.append([name, _tag(rank_ic_5d), _tag(rank_ic_20d), _tag(icir), _tag(stability)])
        ic_bars[name] = series.iloc[-1] if len(series) > 0 else 0.0

    table_html = make_table(
        ["因子", "RankIC(5d)", "RankIC(20d)", "ICIR", "稳定性"],
        rows
    )
    sections.append({"heading": "IC 概览", "content": table_html, "images": []})

    # ── 2. 最新 IC 柱状图 ──
    if ic_bars:
        ic_series = pd.Series(ic_bars)
        img = plot_ic_bar(ic_series.sort_values())
        sections.append({"heading": "因子最新 IC", "content": "", "images": [img]})

    # ── 3. IC 趋势图 ──
    if factors_ic:
        ic_df = pd.DataFrame(factors_ic)
        img = plot_ic_trend(ic_df)
        sections.append({"heading": "IC 滚动趋势（20日）", "content": "", "images": [img]})

    # ── 4. IC衰减分析 ──
    decay_parts = []
    for name, series in list(factors_ic.items())[:5]:  # 最多展示5个因子
        decay = ic_decay_curve(series, max_lag=10)
        if not decay.empty:
            mean_decay = round(decay.mean(), 3)
            decay_parts.append(f"<p><b>{name}</b>: 平均自相关={mean_decay}")

    if decay_parts:
        sections.append({
            "heading": "IC衰减分析（前5因子）",
            "content": "".join(decay_parts),
            "images": []
        })

    # ── 组装 ──
    title = f"因子 IC 周报 - {report_date}"
    html = render_html(title, sections, report_date)

    path = save_report(html, report_type="ic", subdir="weekly")
    return path


def generate_factor_summary(factors_ic: dict) -> str:
    """生成因子摘要文本（用于周报/日复盘引用）"""
    lines = ["## 因子表现摘要\\n"]
    for name, series in factors_ic.items():
        rank_ic = round(series.iloc[-5:].mean(), 4) if len(series) >= 5 else 0.0
        icir = round(calc_icir(series), 4)
        score = round(factor_stability_score(series), 4)
        tag = "✅" if score > 0.3 else ("⚠️" if score > 0 else "❌")
        lines.append(f"{tag} {name}: RankIC={rank_ic}, ICIR={icir}, 稳定性={score}")
    return "\\n".join(lines)
