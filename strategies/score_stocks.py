#!/usr/bin/env python3
"""Layer 3 - 模型层: 打分排序+LLM风险排雷"""
import sys, json, logging, subprocess
from config_loader import IE_SCRIPTS, CFG as CONFIG, report_dir, mmx_path
import os
from pathlib import Path; import pandas as pd; import numpy as np
from datetime import datetime; from build_features import FactorScorer

log = logging.getLogger("model_layer")

class ScoringEngine:
    def __init__(self, name_map: dict = None):
        self.scorer = FactorScorer(name_map=name_map)
    
    def daily_rank(self, codes: list, top_n: int = 20) -> pd.DataFrame:
        df = self.scorer.batch_score(codes)
        if df.empty: return df
        df["rank"] = range(1, len(df)+1)
        df["date"] = datetime.now().strftime("%Y-%m-%d")
        df = df[df["total"].notna()].head(top_n)
        out = report_dir("factors") / "daily_rank.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf_8_sig")
        log.info(f"日排名已保存: {len(df)}只 -> {out}")

        # IC追踪: 保存因子分数快照（供未来收益计算IC用）
        # V4 Pro评审: 原IC计算使用当日总分(自指)，改为保存快照供未来收益对比
        try:
            ic_dir = report_dir("factors")
            snapshot_path = ic_dir / f"factor_snapshot_{datetime.now().strftime('%Y%m%d')}.csv"
            if not df.empty and "code" in df.columns:
                cols = ["code", "date", "total"] + [f for f in ["trend","volume","volatility","capital","fundamental","sentiment","alpha191","frameworks"] if f in df.columns]
                snapshot = df[cols].copy() if all(c in df.columns for c in cols) else df
                snapshot.to_csv(snapshot_path, index=False, encoding="utf_8_sig")
                log.info(f"因子快照已保存: {snapshot_path}")
        except Exception as e:
            log.debug(f"因子快照保存跳过: {e}")

        # IC追踪：计算预测性IC（因子排名 vs 未来收益率排名）
        # 使用last_price作为未来收益代理：分数高的股票应有更好的后续表现
        try:
            from factor_tracker import FactorTracker
            from scipy.stats import spearmanr
            ft = FactorTracker()
            for factor_name in ["trend", "volume", "volatility", "capital", "fundamental", "sentiment", "alpha191", "frameworks"]:
                if factor_name in df.columns and "total" in df.columns:
                    scores = df[factor_name].values
                    # 使用截面排名作为当前预测信号
                    # 真正的预测性IC需要未来收益数据，在evolution_engine.verify_outcome中计算
                    # 此处记录截面区分度作为代理指标
                    if len(scores) >= 10:
                        from scipy.stats import rankdata
                        # 修复: 排除自身因子的贡献，避免自引用IC膨胀
                        other_factors = [f for f in ["trend", "volume", "volatility", "capital", "fundamental", "sentiment", "alpha191", "frameworks"] if f != factor_name]
                        other_factors = [f for f in other_factors if f in df.columns]
                        ic_val = 0.0
                        if other_factors:
                            ex_self = df[other_factors].sum(axis=1).values
                            ic_val, _ = spearmanr(scores, ex_self)
                        if not np.isnan(ic_val):
                            log.info(f"  xIC({factor_name})={ic_val:.3f}")
        except Exception as e:
            log.debug(f"IC追踪跳过: {e}")

        # 预测性IC: 记录预测，等下一交易日验证
        try:
            from evolution_engine import EvolutionEngine
            ee = EvolutionEngine()
            weights = {f: self.scorer.w.get(f, 0.1) for f in ["trend","volume","volatility","capital","fundamental","sentiment","alpha191","frameworks"]}
            factor_scores = {}
            if not df.empty and "code" in df.columns:
                for _, row in df.iterrows():
                    factor_scores[row["code"]] = row.get("total", 50)
            ee.record_prediction(
                date=datetime.now().strftime("%Y-%m-%d"),
                weights=weights,
                selected_stocks=df["code"].tolist() if "code" in df.columns else [],
                factor_scores=factor_scores
            )
            log.info(f"  预测已记录至evolution_engine: {len(factor_scores)}只股票")
        except Exception as e:
            log.debug(f"预测记录跳过: {e}")

        return df

class LLMReview:
    def __init__(self):
        self.mmx = mmx_path()
    
    def review_stock(self, code: str, name: str, factors: dict) -> dict:
        import json as _j
        prompt = f"分析{name}({code})的量化因子得分: {factors}。给出风险标签(政策/业绩/合规/技术/流动性)和1-5分风险等级。简短回复JSON。"
        try:
            r = subprocess.run([self.mmx, "text", "chat", "--model", "MiniMax-M2.7",
                "--message", prompt, "--output", "json", "--quiet", "--non-interactive"],
                capture_output=True, text=True, timeout=30)
            d = _j.loads(r.stdout)  # only parse stdout; stderr may have warnings
            raw = d.get("choices",[{}])[0].get("message",{}).get("content","")
            # 尝试解析 content 是否为内嵌JSON
            if raw.startswith("{"):
                try:
                    risk = _j.loads(raw)
                    raw = _j.dumps(risk, ensure_ascii=False)
                except (json.JSONDecodeError, ValueError):
                    pass
            return {"code": code, "llm_review": raw}
        except Exception as e:
            log.warning(f"LLM review failed for {code}: {e}")
            return {"code": code, "llm_review": "review_failed"}


# ── 可配置权重 + ICIR 接入（2026-05-27 新增）──

def load_weights(config_path: str = None) -> dict:
    """从 config.json 加载因子权重，不存在则返回空"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        weights = {}
        for name, fc in cfg.get("factors", {}).items():
            if "weight" in fc:
                weights[name] = fc["weight"]
        return weights if weights else _scoring_defaults()
    except Exception:
        return _scoring_defaults()


def _scoring_defaults() -> dict:
    """从 config.json 读取规范权重"""
    import json
    try:
        with open(Path(__file__).parent.parent / "config" / "config.json") as f:
            cfg = json.load(f)
            bh = cfg.get("blackhorse", {})
            factors = bh.get("factors", {})
            return {k: v.get("weight", 0) for k, v in factors.items() if isinstance(v, dict) and v.get("weight", 0) > 0}
    except Exception:
        return {
    "trend": 0.1429,
    "volume": 0.0952,
    "capital": 0.1905,
    "fundamental": 0.1429,
    "sentiment": 0.0952,
    "alpha191": 0.0476,
    "frameworks": 0.0952,
    "event_factor": 0.1429,
    "factorhub": 0.0476
}


def apply_icir_weights(base_weights: dict, icir_scores: dict = None, blend: float = 0.3) -> dict:
    """将 ICIR 动态权重混入基础权重

    Parameters
    ----------
    base_weights : dict
        基础配置权重
    icir_scores : dict, optional
        {factor_name: icir_value} 来自 ic_analyzer
    blend : float
        ICIR 混入比例，默认 0.3（70% 基础 + 30% ICIR）

    Returns
    -------
    dict : 混合后权重
    """
    if not icir_scores:
        return base_weights

    # 归一化 ICIR
    values = np.array(list(icir_scores.values()))
    vmin, vmax = values.min(), values.max()
    if vmax > vmin:
        normalized = (values - vmin) / (vmax - vmin)
    else:
        normalized = np.ones_like(values) / len(values)

    icir_norm = dict(zip(icir_scores.keys(), normalized))

    blended = {}
    all_keys = set(base_weights.keys()) | set(icir_norm.keys())
    for k in all_keys:
        base = base_weights.get(k, 0)
        icir = icir_norm.get(k, 0)
        blended[k] = base * (1 - blend) + icir * blend

    # 重新归一化
    total = sum(blended.values())
    if total > 0:
        blended = {k: v / total for k, v in blended.items()}

    return blended
