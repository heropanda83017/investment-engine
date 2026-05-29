"""绩效可视化模块 — 收益曲线 / 回撤图 / IC柱状图 / 看板"""

import sys, json, logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from config_loader import IE_SCRIPTS, report_dir

log = logging.getLogger("visualization")


def equity_curve(returns, title="策略收益曲线") -> str:
    """生成收益曲线HTML(Plotly)"""
    try:
        import plotly.graph_objects as go
        cum = (1 + returns).cumprod()
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=list(range(len(cum))), y=cum.values,
            mode='lines', name='净值', line=dict(color='#1f77b4', width=2)))
        fig.update_layout(
            title=title, xaxis_title="交易日", yaxis_title="净值",
            template="plotly_white", height=400,
            margin=dict(l=40, r=20, t=40, b=40))
        return fig.to_html(full_html=False, include_plotlyjs=False)
    except ImportError:
        return "<p>需安装plotly: pip install plotly</p>"


def drawdown_chart(returns, title="回撤图") -> str:
    """生成回撤曲线HTML"""
    try:
        import plotly.graph_objects as go
        cum = (1 + returns).cumprod()
        peak = cum.expanding().max()
        dd = (cum - peak) / peak * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=list(range(len(dd))), y=dd.values, fill='tozeroy',
            mode='lines', name='回撤', line=dict(color='#d62728', width=1)))
        fig.update_layout(
            title=title, xaxis_title="交易日", yaxis_title="回撤(%)",
            template="plotly_white", height=300,
            margin=dict(l=40, r=20, t=30, b=40))
        return fig.to_html(full_html=False, include_plotlyjs=False)
    except ImportError:
        return "<p>需安装plotly</p>"


def ic_bar_chart(ic_data: Dict[str, float], title="因子IC对比") -> str:
    """生成因子IC柱状图"""
    try:
        import plotly.graph_objects as go
        factors = list(ic_data.keys())
        values = list(ic_data.values())
        colors = ['#2ca02c' if v > 0 else '#d62728' for v in values]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=factors, y=values, marker_color=colors))
        fig.update_layout(
            title=title, xaxis_title="因子", yaxis_title="IC值",
            template="plotly_white", height=350,
            margin=dict(l=40, r=20, t=30, b=60))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        return fig.to_html(full_html=False, include_plotlyjs=False)
    except ImportError:
        return "<p>需安装plotly</p>"


def performance_dashboard(metrics: dict, returns=None, ic_data: dict = None) -> str:
    """生成完整绩效看板HTML"""
    html_parts = ['<!DOCTYPE html><html><head><meta charset="utf-8">']
    html_parts.append('<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>')
    html_parts.append('</head><body style="font-family:sans-serif;max-width:1000px;margin:auto;padding:20px">')
    html_parts.append(f'<h2>📊 绩效看板</h2>')
    html_parts.append(f'<p>生成: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>')

    # 指标卡片
    html_parts.append('<div style="display:flex;flex-wrap:wrap;gap:10px;margin:20px 0">')
    card_keys = [
        ("年化收益", "annualized_return", "{:.1%}"),
        ("年化波动", "annualized_vol", "{:.1%}"),
        ("Sharpe", "sharpe_ratio", "{:.2f}"),
        ("Sortino", "sortino_ratio", "{:.2f}"),
        ("最大回撤", "max_drawdown", "{:.1%}"),
        ("胜率", "win_rate", "{:.0%}"),
        ("总收益", "total_return", "{:.1%}"),
        ("样本天数", "sample_days", "{:.0f}"),
    ]
    for label, key, fmt in card_keys:
        val = metrics.get(key, 0)
        try:
            display = fmt.format(val)
        except Exception:
            display = str(val)
        html_parts.append(
            f'<div style="background:#f5f5f5;border-radius:8px;padding:12px 18px;'
            f'min-width:100px;text-align:center">'
            f'<div style="font-size:12px;color:#666">{label}</div>'
            f'<div style="font-size:20px;font-weight:bold;color:#333">{display}</div></div>')
    html_parts.append('</div>')

    # 收益曲线
    if returns is not None and len(returns) > 0:
        html_parts.append('<h3>收益曲线</h3>')
        html_parts.append(equity_curve(returns))

        html_parts.append('<h3>回撤图</h3>')
        html_parts.append(drawdown_chart(returns))

    # IC柱状图
    if ic_data:
        html_parts.append('<h3>因子IC</h3>')
        html_parts.append(ic_bar_chart(ic_data))

    html_parts.append('</body></html>')
    return "\n".join(html_parts)


def save_dashboard(metrics: dict, returns=None, ic_data: dict = None) -> str:
    """保存看板到HTML文件"""
    html = performance_dashboard(metrics, returns, ic_data)
    path = report_dir("backtest") / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"看板已保存: {path}")
    return str(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import numpy as np
    np.random.seed(42)
    fake_rets = pd.Series(np.random.randn(252) * 0.02 + 0.001)
    fake_metrics = {
        "annualized_return": 0.15, "annualized_vol": 0.20,
        "sharpe_ratio": 0.75, "sortino_ratio": 1.1,
        "max_drawdown": -0.15, "win_rate": 0.55,
        "total_return": 0.30, "sample_days": 252,
    }
    fake_ic = {"trend": 0.12, "volume": 0.08, "volatility": 0.03,
               "capital": 0.15, "fundamental": 0.10, "sentiment": 0.05}
    path = save_dashboard(fake_metrics, fake_rets, fake_ic)
    print(f"示例看板: {path}")
