#!/usr/bin/env python3
"""
风控模块 — 持仓限制+行业集中度+回撤监控+流动性检查
====================================================
5项防线：
  P1 单股仓位 ≤ max_position_pct (默认15%)
  P2 行业集中度 ≤ max_industry_pct (默认30%)
  P3 最大回撤 ≤ max_drawdown (默认20%)
  P4 流动性 ≤ max_trade_volume_pct (默认5%)
  P5 组合级熔断 — 总亏损超限时强行平仓
"""

import logging
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from config_loader import CFG, IE_SCRIPTS
import sys

log = logging.getLogger("risk_manager")

_RISK_CFG = CFG.get("backtest", {})
DEFAULT_MAX_POS_PCT = _RISK_CFG.get("max_position_pct", 0.15)
DEFAULT_MAX_INDUSTRY_PCT = _RISK_CFG.get("max_industry_pct", 0.30)
DEFAULT_MAX_DRAWDOWN = _RISK_CFG.get("max_drawdown", 0.20)
DEFAULT_MAX_TRADE_VOL_PCT = _RISK_CFG.get("max_trade_volume_pct", 0.05)


class RiskController:
    """风控控制器 — 5道防线"""

    def __init__(self,
                 max_pos_pct: float = None,
                 max_industry_pct: float = None,
                 max_drawdown: float = None,
                 max_trade_vol_pct: float = None):
        self.max_pos_pct = max_pos_pct or DEFAULT_MAX_POS_PCT
        self.max_industry_pct = max_industry_pct or DEFAULT_MAX_INDUSTRY_PCT
        self.max_drawdown = max_drawdown or DEFAULT_MAX_DRAWDOWN
        self.max_trade_vol_pct = max_trade_vol_pct or DEFAULT_MAX_TRADE_VOL_PCT
        self.peak_value: float = 0
        self.alerts: List[Dict] = []

    def check_position(self, code: str, position_value: float,
                       total_value: float) -> Tuple[bool, str]:
        """P1: 单只股票仓位不超过上限"""
        if total_value <= 0:
            return True, ""
        pct = position_value / total_value
        if pct > self.max_pos_pct:
            excess = (pct - self.max_pos_pct) * total_value
            msg = (f"[P1] {code} 仓位 {pct:.1%} 超限 ({self.max_pos_pct:.1%})"
                   f"，需减仓 {excess:,.0f}元")
            self.alerts.append({"level": "WARN", "code": code, "msg": msg})
            return False, msg
        return True, f"{code} 仓位 {pct:.1%} 正常"

    def check_industry(self, holdings: Dict[str, float],
                       industry_map: Dict[str, str]) -> Tuple[bool, str]:
        """P2: 单一行业持仓不超过上限"""
        industry_values = {}
        for code, val in holdings.items():
            ind = industry_map.get(code, "未知")
            industry_values[ind] = industry_values.get(ind, 0) + val

        total = sum(holdings.values())
        for ind, val in industry_values.items():
            pct = val / total if total > 0 else 0
            if pct > self.max_industry_pct:
                msg = (f"[P2] 行业[{ind}] 占比 {pct:.1%} 超限 "
                       f"({self.max_industry_pct:.1%})")
                self.alerts.append({"level": "WARN", "code": ind, "msg": msg})
                return False, msg
        return True, "行业集中度正常"

    def check_drawdown(self, current_value: float) -> Tuple[bool, str]:
        """P3: 组合回撤不超过上限"""
        self.peak_value = max(self.peak_value, current_value)
        if self.peak_value <= 0:
            return True, "无回撤数据"

        dd = (self.peak_value - current_value) / self.peak_value
        if dd > self.max_drawdown:
            msg = (f"[P3] 组合回撤 {dd:.1%} 触发熔断线 "
                   f"({self.max_drawdown:.1%})，建议清仓")
            self.alerts.append({"level": "CRITICAL", "code": "PORTFOLIO", "msg": msg})
            return False, msg
        elif dd > self.max_drawdown * 0.7:
            msg = f"[P3] 组合回撤 {dd:.1%} 接近警戒线 ({self.max_drawdown:.1%})"
            self.alerts.append({"level": "WARN", "code": "PORTFOLIO", "msg": msg})
        return True, f"回撤 {dd:.1%} 正常"

    def check_liquidity(self, code: str, trade_value: float,
                        daily_volume: float, avg_price: float) -> Tuple[bool, str]:
        """P4: 交易额不超过日成交额的一定比例"""
        if daily_volume <= 0 or avg_price <= 0:
            return True, f"{code} 无成交量数据"

        daily_value = daily_volume * avg_price
        pct = trade_value / daily_value if daily_value > 0 else 1

        if pct > self.max_trade_vol_pct:
            msg = (f"[P4] {code} 交易额占日成交 {pct:.1%} "
                   f"超限 ({self.max_trade_vol_pct:.1%})")
            self.alerts.append({"level": "WARN", "code": code, "msg": msg})
            return False, msg
        return True, f"{code} 流动性正常"

    def check_portfolio(self, holdings: Dict[str, float],
                        total_value: float,
                        prices: Dict[str, float] = None,
                        daily_volumes: Dict[str, float] = None,
                        industry_map: Dict[str, str] = None) -> List[Dict]:
        """P1-P5 全检，返回告警列表"""
        self.alerts = []

        for code, pos_value in holdings.items():
            ok, msg = self.check_position(code, pos_value, total_value)
            if not ok:
                log.warning(msg)

        if industry_map:
            ok, msg = self.check_industry(holdings, industry_map)
            if not ok:
                log.warning(msg)

        ok, msg = self.check_drawdown(total_value)
        if not ok:
            log.warning(msg)

        if prices and daily_volumes:
            for code, pos_value in holdings.items():
                if code in prices and code in daily_volumes:
                    ok, msg = self.check_liquidity(
                        code, pos_value, daily_volumes[code], prices[code]
                    )
                    if not ok:
                        log.warning(msg)

        # P5 组合级熔断：基于持仓数量估算尾部风险
        # 使用简化的波动率估算：sqrt(n) * 2.5% (假设单只2.5%日波动, sqrt(n)为组合波动分散)
        n_positions = max(len(holdings), 1)
        estimated_risk = total_value * 0.025 * (n_positions ** 0.5)
        max_tolerable = total_value * self.max_drawdown
        if estimated_risk > max_tolerable:
            self.alerts.append({
                "level": "P5",
                "code": "PORTFOLIO",
                "msg": f"组合预估风险 {estimated_risk:,.0f} > 最大容忍 {max_tolerable:,.0f}，建议减仓"
            })

        return self.alerts

    def check_trade(self, code: str, price: float,
                    trade_volume: float, cash: float,
                    total_value: float, existing_value: float = 0) -> Tuple[bool, str]:
        """买入前检查：加仓后仓位是否超限 + 流动性"""
        trade_value = price * trade_volume
        new_pos_value = existing_value + trade_value
        new_total = total_value

        ok, _ = self.check_position(code, new_pos_value, new_total)
        if not ok:
            new_pct = new_pos_value / new_total
            return False, f"[TRADE] {code} 加仓后 {new_pct:.1%} 超限，拒绝买入"

        if trade_value > cash * 0.98:
            return False, f"[TRADE] {code} 资金不足"

        return True, f"{code} 买入合规"

    def risk_summary(self) -> str:
        """风控摘要（供DailyReport集成）"""
        if not self.alerts:
            return "## 风控状态\n\n✅ 无风险警告\n"
        lines = ["## 风控告警", ""]
        for a in self.alerts:
            icon = {"CRITICAL": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}.get(
                a.get("level", "INFO"), "ℹ️")
            lines.append(f"- {icon} [{a['level']}] {a['code']}: {a['msg']}")
        return "\n".join(lines)


if __name__ == "__main__":
    # 快速自测
    rc = RiskController()
    rc.check_position("002371", 200000, 1000000)
    rc.check_drawdown(800000)
    rc.check_industry({"002371": 200000, "688041": 300000},
                      {"002371": "半导体", "688041": "半导体"})
    print(rc.risk_summary())


# ── VaR / CVaR / 相关性约束（2026-05-27 新增）──

def compute_var(returns: np.ndarray, level: float = 0.95, method: str = "historical") -> float:
    """计算 VaR（Value at Risk）

    Parameters
    ----------
    returns : np.ndarray
        收益率序列
    level : float
        置信水平，默认 95%
    method : str
        "historical" 历史模拟法（推荐） / "parametric" 参数法

    Returns
    -------
    float : VaR（正数表示最大损失）
    """
    if len(returns) < 20:
        return 0.0
    arr = np.array(returns)
    if method == "parametric":
        mu = np.mean(arr)
        sigma = np.std(arr, ddof=1)
        from scipy import stats
        return abs(mu - sigma * stats.norm.ppf(1 - level))
    else:
        return abs(np.percentile(arr, (1 - level) * 100))


def compute_cvar(returns: np.ndarray, level: float = 0.95) -> float:
    """计算 CVaR（Conditional VaR / Expected Shortfall）"""
    var = compute_var(returns, level)
    tail = returns[returns <= -var]
    if len(tail) == 0:
        return var
    return abs(np.mean(tail))


def compute_correlation_risk(holdings: Dict[str, float],
                              price_data: Dict[str, pd.DataFrame],
                              max_corr: float = 0.8) -> dict:
    """计算持仓相关性风险

    Parameters
    ----------
    holdings : dict
        {code: weight}
    price_data : dict
        {code: DataFrame} 含 close 列
    max_corr : float
        相关性上限阈值

    Returns
    -------
    dict : {avg_correlation, max_pair, high_corr_pairs, risk_level}
    """
    codes = list(holdings.keys())
    if len(codes) < 2:
        return {"avg_correlation": 0, "max_pair": "", "high_corr_pairs": [], "risk_level": "low"}

    # 计算收益率
    rets = {}
    for code in codes:
        df = price_data.get(code)
        if df is not None and "close" in df.columns:
            rets[code] = df["close"].pct_change().dropna()

    common_idx = None
    for r in rets.values():
        if common_idx is None:
            common_idx = r.index
        else:
            common_idx = common_idx.intersection(r.index)

    if common_idx is None or len(common_idx) < 10:
        return {"avg_correlation": 0, "max_pair": "", "high_corr_pairs": [], "risk_level": "unknown"}

    valid_codes = [c for c in codes if c in rets]
    corr_matrix = pd.DataFrame({c: rets[c].loc[common_idx] for c in valid_codes}).corr()
    triu = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    corr_vals = triu.stack()

    if corr_vals.empty:
        return {"avg_correlation": 0, "max_pair": "", "high_corr_pairs": [], "risk_level": "low"}

    avg_corr = float(corr_vals.mean())
    max_pair = corr_vals.idxmax()
    high_pairs = [f"{p[0]}-{p[1]}" for p in corr_vals[corr_vals > max_corr].index.tolist()]

    if avg_corr > max_corr:
        risk = "high"
    elif avg_corr > max_corr * 0.7:
        risk = "medium"
    else:
        risk = "low"

    return {
        "avg_correlation": round(avg_corr, 4),
        "max_pair": str(max_pair),
        "high_corr_pairs": high_pairs[:10],
        "risk_level": risk,
    }


def portfolio_risk_score(holdings: Dict[str, float],
                          price_data: Dict[str, pd.DataFrame] = None,
                          returns: np.ndarray = None) -> dict:
    """综合组合风险评估

    整合 VaR / CVaR / 相关性 / 集中度 为统一评分

    Returns
    -------
    dict : {var_95, cvar_95, correlation_risk, concentration, overall_risk}
    """
    score = {"overall_risk": "unknown"}

    # VaR / CVaR
    if returns is not None and len(returns) > 20:
        score["var_95"] = round(compute_var(returns), 4)
        score["cvar_95"] = round(compute_cvar(returns), 4)

    # 相关性
    if price_data:
        corr = compute_correlation_risk(holdings, price_data)
        score["correlation"] = corr

    # 集中度
    if holdings:
        weights = np.array(list(holdings.values()))
        hhi = np.sum(weights ** 2)  # Herfindahl 指数
        top_weight = max(weights)
        score["concentration"] = {
            "hhi": round(hhi, 4),
            "top_weight": round(top_weight, 4),
            "num_holdings": len(holdings),
        }
        score["concentration"]["risk_level"] = "high" if hhi > 0.3 else ("medium" if hhi > 0.15 else "low")

    # 综合判定
    risk_signals = 0
    if score.get("var_95", 0) > 0.05:
        risk_signals += 1
    if score.get("correlation", {}).get("risk_level") == "high":
        risk_signals += 1
    if score.get("concentration", {}).get("risk_level") == "high":
        risk_signals += 1

    if risk_signals >= 2:
        score["overall_risk"] = "high"
    elif risk_signals == 1:
        score["overall_risk"] = "medium"
    else:
        score["overall_risk"] = "low"

    return score
