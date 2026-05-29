#!/usr/bin/env python3
"""进化引擎 — 预测→验证→贝叶斯更新→审计标记

核心流程:
1. 记录预测（模型输出的信号/评分/选股）
2. 与实际结果对比（收益/IC/胜率）
3. 贝叶斯更新因子权重
4. 准确率<阈值时自动降权并审计标记

使用方式:
    from evolution_engine import EvolutionEngine
    ee = EvolutionEngine()
    ee.record_prediction("2026-05-26", {"trend": 0.18, ...}, ["000001", ...])
    ee.verify_outcome("2026-05-26", actual_returns={"000001": 0.03, ...})
    ee.update_weights()  → 返回更新后的权重
"""

import logging
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

log = logging.getLogger("evolution_engine")

# 默认数据目录
DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "evolution"

# 降权阈值: ICIR < 1.0 或 t-stat < 2.0 时触发降权
# REVIEW 建议: 不直接用 50% 准确率，改用统计显著性
ICIR_DOWNGRADE_THRESHOLD = 1.0
TSTAT_DOWNGRADE_THRESHOLD = 2.0

# 因子权重范围
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.40


class EvolutionEngine:
    """进化引擎 — 自学习核心"""

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 预测记录: {date: {"predicted_scores": {...}, "selected": [...], "weights": {...}}}
        self.predictions: Dict = {}
        # 验证记录: {date: {"actual_returns": {...}, "accuracy": float, "ic": float}}
        self.verifications: Dict = {}
        # 因子性能历史: {factor_name: [{"ic": float, "icir": float, "tstat": float, "date": str}]}
        self.factor_history: Dict[str, List] = defaultdict(list)
        # 审计标记: {factor_name: {"flagged": bool, "reason": str, "date": str}}
        self.audit_flags: Dict = {}

        self._load_state()

    # ---- 状态持久化 ----

    def _state_path(self) -> Path:
        return self.data_dir / "evolution_state.json"

    def _load_state(self):
        path = self._state_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.predictions = data.get("predictions", {})
                self.verifications = data.get("verifications", {})
                # factor_history 需要从列表转 defaultdict
                raw_history = data.get("factor_history", {})
                self.factor_history = defaultdict(list, raw_history)
                self.audit_flags = data.get("audit_flags", {})
                log.info(f"进化引擎状态已加载: {len(self.verifications)} 条验证记录")
            except Exception as e:
                log.warning(f"加载进化状态失败: {e}")

    def _save_state(self):
        data = {
            "predictions": self.predictions,
            "verifications": self.verifications,
            "factor_history": dict(self.factor_history),
            "audit_flags": self.audit_flags,
        }
        with open(self._state_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 核心流程 ----

    def record_prediction(self, date: str, weights: Dict[str, float],
                          selected_stocks: List[str] = None,
                          factor_scores: Dict[str, float] = None):
        """记录一次预测（信号输出）"""
        self.predictions[date] = {
            "weights": dict(weights),
            "selected": selected_stocks or [],
            "factor_scores": factor_scores or {},
            "timestamp": datetime.now().isoformat(),
        }
        self._save_state()
        log.info(f"预测已记录: {date} | 权重={len(weights)}因子, 选股={len(selected_stocks or [])}只")

    def verify_outcome(self, date: str, actual_returns: Dict[str, float] = None,
                       benchmark_return: float = 0.0) -> Dict:
        """验证预测结果，计算准确率

        参数:
            date: 预测日期
            actual_returns: {code: 实际收益率}
            benchmark_return: 基准收益率（如沪深300）

        返回:
            {"accuracy": float, "ic": float, "excess_return": float, ...}
        """
        if actual_returns is None: actual_returns = {}
        pred = self.predictions.get(date)
        if not pred:
            log.warning(f"未找到 {date} 的预测记录")
            return {"error": "no_prediction"}

        selected = pred.get("selected", [])
        if not selected or not actual_returns:
            return {"accuracy": 0.0, "ic": 0.0, "excess_return": 0.0}

        # 1. 准确率: 选股池中收益为正的比例
        selected_with_data = [c for c in selected if c in actual_returns]
        positive_count = sum(1 for c in selected_with_data
                            if actual_returns.get(c, 0) > 0)
        accuracy = positive_count / max(len(selected_with_data), 1) if selected_with_data else 0.0

        # 2. 超额收益: 选股平均收益 - 基准
        selected_returns = [actual_returns.get(c, 0) for c in selected if c in actual_returns]
        avg_return = np.mean(selected_returns) if selected_returns else 0
        excess_return = avg_return - benchmark_return

        # 3. IC (信息系数): 预测分数与真实收益的Spearman相关
        ic = 0.0
        scores = pred.get("factor_scores", {})
        if scores and selected:
            common_codes = [c for c in selected if c in scores and c in actual_returns]
            if len(common_codes) >= 10:
                try:
                    from scipy.stats import spearmanr
                except ImportError:
                    import numpy as _np
                    def _sp(x,y):
                        n=len(x)
                        if n<3: return 0.0
                        rx=_np.argsort(_np.argsort(_np.array(x)))
                        ry=_np.argsort(_np.argsort(_np.array(y)))
                        return 1-6*sum((rx-ry)**2)/(n*(n**2-1))
                    spearmanr=_sp
                actual = [actual_returns.get(c, 0) for c in common_codes]
                try:
                    pred_scores = [scores.get(c, 0) for c in common_codes] if isinstance(scores, dict) else scores
                    ic, _ = spearmanr(pred_scores, actual)
                    ic = round(ic, 4) if not np.isnan(ic) else 0.0
                except Exception:
                    ic = 0.0

        verification = {
            "accuracy": round(accuracy, 4),
            "ic": round(ic, 4),
            "excess_return": round(excess_return, 4),
            "avg_return": round(avg_return, 4),
            "selected_count": len(selected),
            "benchmark_return": round(benchmark_return, 4),
        }

        self.verifications[date] = verification

        # 更新因子历史
        weights = pred.get("weights", {})
        for factor_name in weights:
            self.factor_history[factor_name].append({
                "date": date,
                "ic": ic,
                "accuracy": accuracy,
                # t-stat 用 sqrt(N) * IC 近似
                "tstat": round(abs(ic) * np.sqrt(len(selected) - 2) / np.sqrt(max(1 - ic * ic, 1e-10)), 4),
                "icir": round(abs(ic) / max(1e-6, (1 - abs(ic)) / max(len(selected), 10)), 4),
            })

        self._save_state()
        log.info(f"验证完成: {date} | 准确率={accuracy:.2%}, IC={ic:.4f}")
        return verification

    def update_weights(self, current_weights: Dict[str, float]) -> Dict[str, float]:
        """基于因子历史表现，贝叶斯更新权重

        逻辑:
        - 对每个因子，检查最近 N 期的 ICIR / t-stat
        - ICIR >= 1.0 且 t-stat >= 2.0: 维持/加分
        - 否则: 降权至下限
        - 归一化: 权重和=1，单因子∈[MIN_WEIGHT, MAX_WEIGHT]

        返回:
            {factor_name: new_weight}
        """
        if not current_weights:
            return current_weights

        new_weights = {}

        for factor_name in current_weights:
            history = self.factor_history.get(factor_name, [])
            if not history:
                # 无历史数据，维持原权重
                new_weights[factor_name] = current_weights[factor_name]
                continue

            # 取最近 12 期均值
            recent = history[-12:]
            avg_icir = np.mean([h.get("icir", 0) for h in recent])
            avg_tstat = np.mean([h.get("tstat", 0) for h in recent])
            avg_acc = np.mean([h.get("accuracy", 0.5) for h in recent])

            old_weight = current_weights[factor_name]

            if avg_icir >= ICIR_DOWNGRADE_THRESHOLD and avg_tstat >= TSTAT_DOWNGRADE_THRESHOLD:
                # 表现好: 维持权重（并考虑提高）
                boost = min(1.0 + avg_acc * 0.2, 1.2)  # 最多提升20%
                new_weights[factor_name] = min(old_weight * boost, MAX_WEIGHT)
                # 清除审计标记
                self.audit_flags.pop(factor_name, None)
            else:
                # 表现差: 降权
                new_weights[factor_name] = MIN_WEIGHT
                # 审计标记
                if factor_name not in self.audit_flags:
                    self.audit_flags[factor_name] = {
                        "flagged": True,
                        "reason": f"ICIR={avg_icir:.2f}, t-stat={avg_tstat:.2f}, 均低于阈值",
                        "date": datetime.now().strftime("%Y-%m-%d"),
                    }
                    log.warning(f"审计标记: {factor_name} 因子降权至 {MIN_WEIGHT}")

        # 归一化: 权重和=1
        total = sum(new_weights.values())
        if total > 0:
            for k in new_weights:
                new_weights[k] /= total

        # 二次约束: 单因子∈[MIN_WEIGHT, MAX_WEIGHT]
        # 先clip到[MIN_WEIGHT, MAX_WEIGHT]，再归一化
        for k in new_weights:
            new_weights[k] = max(MIN_WEIGHT, min(MAX_WEIGHT, new_weights[k]))
        
        # 最终归一化: clip → normalize → repeat（两轮消除截断误差）
        for _ in range(2):
            for k in new_weights:
                new_weights[k] = round(max(MIN_WEIGHT, min(MAX_WEIGHT, new_weights[k])), 6)
            total = sum(new_weights.values())
            if total > 0:
                for k in new_weights:
                    new_weights[k] /= total
        for k in new_weights:
            new_weights[k] = round(new_weights[k], 4)

        self._save_state()
        log.info(f"权重已更新: {len(new_weights)} 因子 | 审计标记: {len(self.audit_flags)} 个")
        return {k: round(v, 4) for k, v in new_weights.items()}

    def get_audit_report(self) -> str:
        """生成审计报告"""
        if not self.audit_flags:
            return "✅ 所有因子正常运行，无审计标记"

        lines = ["⚠️ 审计报告 - 标记因子:"]
        for factor, info in self.audit_flags.items():
            lines.append(f"  - {factor}: {info.get('reason', '未知')} (标记于 {info.get('date', '?')})")
        return "\n".join(lines)

    def get_performance_summary(self, window: int = 12) -> str:
        """生成性能摘要"""
        if not self.verifications:
            return "暂无验证数据"

        recent_dates = sorted(self.verifications.keys())[-window:]
        recent_vs = [self.verifications[d] for d in recent_dates]

        avg_acc = np.mean([v.get("accuracy", 0) for v in recent_vs])
        avg_ic = np.mean([v.get("ic", 0) for v in recent_vs])
        avg_excess = np.mean([v.get("excess_return", 0) for v in recent_vs])

        lines = [
            f"📊 进化引擎 - 最近 {len(recent_vs)} 期表现",
            f"  平均准确率: {avg_acc:.2%}",
            f"  平均IC: {avg_ic:.4f}",
            f"  平均超额收益: {avg_excess:.2%}",
            f"  审计标记因子: {len(self.audit_flags)} 个",
        ]
        return "\n".join(lines)



    def verify_pending_predictions(self, price_data_provider=None) -> int:
        """验证所有待验证的预测（昨天预测，今天验证）

        从factor_snapshot文件读取昨天的因子分数，
        计算今天开盘买入到收盘的收益，与预测分数做Spearman相关。

        参数:
            price_data_provider: 数据提供者，用于获取股票价格

        返回:
            已验证的预测数
        """
        from pathlib import Path
        import pandas as pd
        from config_loader import report_dir
        try:
            from scipy.stats import spearmanr
        except ImportError:
            import numpy as _np
            def _sp(x,y):
                n=len(x)
                if n<3:return 0.0
                rx=_np.argsort(_np.argsort(_np.array(x)))
                ry=_np.argsort(_np.argsort(_np.array(y)))
                return 1-6*sum((rx-ry)**2)/(n*(n**2-1))
            spearmanr=_sp

        verified = 0

        # 找到所有未验证的预测
        pending_dates = [d for d in self.predictions
                        if d not in self.verifications]
        if not pending_dates:
            log.info("无待验证的预测")
            return 0

        for date in pending_dates[:5]:  # 最多验证5天
            pred = self.predictions[date]
            selected = pred.get("selected", [])
            if not selected:
                continue

            # 获取昨天到今天收盘的收益率
            actual_returns = {}
            try:
                if price_data_provider is not None:
                    for code in selected[:20]:
                        df = price_data_provider.get_kline(code, days=5)
                        if df is not None and len(df) >= 2:
                            close_series = df["收盘"].values if "收盘" in df.columns else df["close"].values if "close" in df.columns else None
                            if close_series is not None and len(close_series) >= 2:
                                ret = (close_series[-1] / close_series[-2] - 1)
                                actual_returns[code] = round(float(ret), 6)
            except Exception as e:
                log.debug(f"获取收益率失败: {e}")

            if actual_returns:
                # 计算预测性IC
                scores = pred.get("factor_scores", {})
                common = [c for c in selected if c in scores and c in actual_returns]
                if len(common) >= 5:
                    pred_scores = [scores[c] for c in common]
                    actual = [actual_returns[c] for c in common]
                    ic, _ = spearmanr(pred_scores, actual)
                    acc = sum(1 for r in actual if r > 0) / max(len(actual), 1)
                    ic_val = round(ic, 4) if not np.isnan(ic) else 0.0

                    self.verifications[date] = {
                        "accuracy": round(acc, 4),
                        "ic": ic_val,
                        "excess_return": round(float(np.mean(actual)), 6),
                        "selected_count": len(common),
                    }
                    verified += 1
                    log.info(f"预测性IC验证 {date}: IC={ic_val:.4f} accuracy={acc:.2%}")

        if verified > 0:
            self._save_state()
            log.info(f"共验证 {verified} 天预测")

        return verified

    def full_evolution_cycle(self, date: str, weights: Dict[str, float],
                             selected_stocks: List[str],
                             factor_scores: Dict[str, float],
                             actual_returns: Dict[str, float],
                             benchmark_return: float = 0.0) -> Dict:
        """一次完整的进化周期: 记录→验证→更新

        返回:
            {"prediction": ..., "verification": ..., "new_weights": ..., "audit": ...}
        """
        self.record_prediction(date, weights, selected_stocks, factor_scores)
        verification = self.verify_outcome(date, actual_returns, benchmark_return)
        new_weights = self.update_weights(weights)
        return {
            "date": date,
            "verification": verification,
            "new_weights": new_weights,
            "audit_flags": dict(self.audit_flags),
        }
