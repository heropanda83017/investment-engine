"""backtest_report.py — 回测报告生成

基于 report.py 渲染引擎，将 PerformanceMetrics + overfit_detector 输出转为 HTML
"""
import numpy as np
import pandas as pd
from datetime import datetime

from report import render_html, save_report, make_table, make_metric_row, plot_pnl_curve
from overfit_detector import full_overfit_assessment


def generate_backtest_report(returns: np.ndarray, metrics: dict,
                              overfit: dict = None, strategy_name: str = "",
                              benchmark_name: str = "benchmark",
                              report_date: str = "") -> str:
    """生成回测报告

    Parameters
    ----------
    returns : np.ndarray
        策略日收益率序列
    metrics : dict
        PerformanceMetrics.all_metrics() 输出的全部指标
    overfit : dict, optional
        full_overfit_assessment 的输出
    strategy_name : str
        策略名称
    benchmark_name : str
        基准名称

    Returns
    -------
    str : HTML 文件路径
    """
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    sections = []
    nav = (1 + pd.Series(returns)).cumprod()

    # ── 1. 净值曲线 ──
    img = plot_pnl_curve(nav)
    sections.append({"heading": "净值曲线", "content": "", "images": [img]})

    # ── 2. 核心指标卡片 ──
    card_items = [
        ("年化收益", f'{metrics.get("annual_return", 0)*100:.2f}%', "good" if metrics.get("annual_return", 0) > 0 else "bad"),
        ("夏普比", f'{metrics.get("sharpe", 0):.2f}', "good" if metrics.get("sharpe", 0) > 1 else "warn"),
        ("最大回撤", f'{metrics.get("max_drawdown", 0)*100:.2f}%', "bad"),
        ("胜率", f'{metrics.get("win_rate", 0)*100:.1f}%', "good" if metrics.get("win_rate", 0) > 0.5 else "bad"),
    ]
    sections.append({
        "heading": "核心指标",
        "content": make_metric_row(card_items),
        "images": []
    })

    # ── 3. 全部指标表 ──
    all_rows = [
        ["年化收益率", f'{metrics.get("annual_return", 0)*100:.2f}%'],
        ["累计收益率", f'{metrics.get("total_return", 0)*100:.2f}%'],
        ["夏普比", f'{metrics.get("sharpe", 0):.4f}'],
        ["索提诺比", f'{metrics.get("sortino", 0):.4f}'],
        ["卡玛比", f'{metrics.get("calmar", 0):.4f}'],
        ["最大回撤", f'{metrics.get("max_drawdown", 0)*100:.2f}%'],
        ["回撤天数", str(metrics.get("drawdown_duration", 0))],
        ["胜率", f'{metrics.get("win_rate", 0)*100:.1f}%'],
        ["盈亏比", f'{metrics.get("profit_loss_ratio", 0):.4f}'],
        ["交易次数", str(metrics.get("total_trades", 0))],
        ["基准", benchmark_name],
    ]
    sections.append({
        "heading": "详细指标",
        "content": make_table(["指标", "值"], all_rows),
        "images": []
    })

    # ── 4. 过拟合风险评估 ──
    if overfit:
        verdict_map = {
            "high_overfit_risk": ("高过拟合风险", "bad"),
            "caution": ("需关注", "warn"),
            "low_risk": ("低风险", "good"),
            "unknown": ("未知", ""),
        }
        v_text, v_cls = verdict_map.get(overfit.get("verdict", "unknown"), ("未知", ""))

        of_items = [
            ("过拟合判定", f'<span class="{v_cls}">{v_text}</span>', v_cls),
        ]

        decay = overfit.get("details", {}).get("sharpe_decay", {})
        if decay:
            of_items.append(("IS Sharpe", str(decay.get("is_sharpe", 0)), ""))
            of_items.append(("OOS Sharpe", str(decay.get("oos_sharpe", 0)), ""))
            of_items.append(("衰减率", f'{decay.get("decay_rate", 0)*100:.1f}%', "bad" if decay.get("decay_rate", 0) > 0.3 else "good"))

        ci = overfit.get("details", {}).get("sharpe_ci", {})
        if ci:
            of_items.append(("Sharpe 95%CI", f'[{ci.get("ci_lower", 0):.2f}, {ci.get("ci_upper", 0):.2f}]', ""))

        sections.append({
            "heading": "过拟合风险评估",
            "content": make_metric_row(of_items),
            "images": []
        })

    # ── 组装 ──
    title = f"回测报告 - {strategy_name or 'Unnamed'}"
    html = render_html(title, sections, report_date)
    path = save_report(html, report_type=f"backtest_{strategy_name or 'unnamed'}", subdir="backtest")
    return path


def generate_comparison_report(results: list, labels: list = None) -> str:
    """多策略对比报告

    Parameters
    ----------
    results : list of dict
        每个策略的 all_metrics() 输出
    labels : list of str, optional
        策略标签

    Returns
    -------
    str : HTML 文件路径
    """
    if labels is None:
        labels = [f"策略{i+1}" for i in range(len(results))]

    rows = []
    for i, (res, label) in enumerate(zip(results, labels)):
        rows.append([
            label,
            f'{res.get("annual_return", 0)*100:.2f}%',
            f'{res.get("sharpe", 0):.2f}',
            f'{res.get("max_drawdown", 0)*100:.2f}%',
            f'{res.get("win_rate", 0)*100:.1f}%',
        ])

    sections = [{
        "heading": "策略对比",
        "content": make_table(["策略", "年化收益", "夏普比", "最大回撤", "胜率"], rows),
        "images": []
    }]

    html = render_html("策略对比报告", sections)
    path = save_report(html, report_type="comparison", subdir="backtest")
    return path
