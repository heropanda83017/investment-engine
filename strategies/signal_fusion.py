"""signal_fusion.py — 信号融合引擎

接收多路信号（因子/分析/风控/市场状态），统一融合为综合评分。

SignalSchema:
  {
    source: str,          # 信号源 ID (factor/analysis/risk/regime)
    timestamp: str,       # ISO时间
    ticker: str,          # 股票代码
    direction: int,       # 1=看多, -1=看空, 0=中性
    confidence: float,    # [0,1] 置信度
    intensity: float,     # [-1,1] 信号强度
    metadata: dict        # 可选的原始数据
  }

FusedSignal:
  {
    ticker: str,
    composite_score: float,   # [-1,1] 综合评分
    confidence: float,        # [0,1] 融合置信度
    breakdown: dict,          # 各信号源贡献明细
    trading_suggestion: str   # buy/sell/hold/avoid
  }
"""
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional


# ─── 信号融合权重配置（可外部重载） ──────────

def _load_fusion_weights() -> dict:
    """从 config.json 读取信号融合权重"""
    try:
        import json
        from pathlib import Path
        p = Path(__file__).parent.parent / "config" / "config.json"
        if p.exists():
            with open(p) as f:
                cfg = json.load(f)
            fw = cfg.get("signal_fusion", {})
            if fw:
                return fw
    except Exception:
        pass
    return {"factor": 0.35, "analysis": 0.25, "risk": 0.25, "regime": 0.15}

DEFAULT_WEIGHTS = _load_fusion_weights()

# 风控信号的否决阈值: 如果风险信号低于此值，直接否决
RISK_VETO_THRESHOLD = -0.7


def validate_signal(signal: dict) -> bool:
    """验证 SignalSchema 格式正确性"""
    required = ["source", "ticker", "direction", "confidence", "intensity"]
    for k in required:
        if k not in signal:
            return False
    if signal["direction"] not in (-1, 0, 1):
        return False
    if not 0 <= signal["confidence"] <= 1:
        return False
    if not -1 <= signal["intensity"] <= 1:
        return False
    return True


def fuse_signals(signals: List[dict], weights: dict = None) -> List[dict]:
    """融合多路信号为综合评分

    Parameters
    ----------
    signals : list of SignalSchema
    weights : dict, optional
        各信号源权重，默认 DEFAULT_WEIGHTS

    Returns
    -------
    list of FusedSignal
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # 按 ticker 分组
    from collections import defaultdict
    by_ticker = defaultdict(list)
    for s in signals:
        if validate_signal(s):
            by_ticker[s["ticker"]].append(s)

    results = []
    for ticker, ticker_signals in by_ticker.items():
        # 检查风控否决
        risk_sigs = [s for s in ticker_signals if s["source"] == "risk"]
        for rs in risk_sigs:
            if rs["intensity"] < RISK_VETO_THRESHOLD:
                results.append({
                    "ticker": ticker,
                    "composite_score": -1.0,
                    "confidence": rs["confidence"],
                    "breakdown": {"veto_reason": f"risk veto: intensity={rs['intensity']}"},
                    "trading_suggestion": "avoid",
                })
                break
        else:
            # 正常融合
            weighted_sum = 0.0
            total_weight = 0.0
            breakdown = {}
            for source, w in weights.items():
                source_sigs = [s for s in ticker_signals if s["source"] == source]
                if source_sigs:
                    # 取置信度加权平均
                    total_conf = sum(s["confidence"] for s in source_sigs)
                    avg_intensity = sum(s["intensity"] * s["confidence"] for s in source_sigs) / max(total_conf, 1e-6)
                    avg_conf = total_conf / len(source_sigs)
                    weighted_sum += avg_intensity * w
                    total_weight += w
                    breakdown[source] = {
                        "intensity": round(avg_intensity, 4),
                        "confidence": round(avg_conf, 4),
                        "weight": w,
                        "num_signals": len(source_sigs),
                    }

            if total_weight == 0:
                continue

            composite = weighted_sum / total_weight
            composite = max(-1.0, min(1.0, composite))

            # 融合置信度
            fusion_conf = np.mean([b["confidence"] for b in breakdown.values()]) if breakdown else 0

            # 交易建议
            if composite > 0.3:
                suggestion = "buy"
            elif composite < -0.3:
                suggestion = "sell"
            elif abs(composite) < 0.1:
                suggestion = "hold"
            else:
                suggestion = "neutral"

            results.append({
                "ticker": ticker,
                "composite_score": round(composite, 4),
                "confidence": round(fusion_conf, 4),
                "breakdown": breakdown,
                "trading_suggestion": suggestion,
            })

    return results


def score_to_rank(fused_list: List[dict], top_n: int = 20) -> pd.DataFrame:
    """融合评分 → 排名 DataFrame

    Parameters
    ----------
    fused_list : list of FusedSignal
    top_n : int
        返回前 N 名

    Returns
    -------
    pd.DataFrame : columns=[ticker, score, confidence, suggestion]
    """
    if not fused_list:
        return pd.DataFrame(columns=["ticker", "score", "confidence", "suggestion"])

    df = pd.DataFrame(fused_list)
    df = df.sort_values("composite_score", ascending=False)
    return df.head(top_n)[["ticker", "composite_score", "confidence", "trading_suggestion"]]
