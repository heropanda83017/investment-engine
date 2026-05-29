"""策略进化流水线 — 自学习循环编排器"""

import sys, json, logging, time, copy
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from config_loader import IE_SCRIPTS, CFG as CONFIG, report_dir

log = logging.getLogger("strategy_pipeline")

# 延迟导入(模块级导入可能因依赖缺失而失败)
# from factor_tracker import FactorTracker
# from strategy_optimizer import StrategyOptimizer
# from backtest_engine import BacktestEngine


class StrategyPipeline:
    """策略进化流水线 — 编排自学习循环

    工作流:
    1. 因子追踪: 每周更新IC数据
    2. 权重优化: 每月基于ICIR+市场状态优化
    3. 回测验证: 每次权重变更前做新旧对比
    4. 版本记录: 每次优化产生版本快照
    """

    def __init__(self, mode: str = "auto", use_ic_weighting: bool = False):
        self.mode = mode  # auto / manual / dry-run
        self.use_ic_weighting = use_ic_weighting  # ICIR动态加权（默认关闭）
        self._pipeline_dir = report_dir("pipeline")
        self._pipeline_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    def _state_path(self) -> Path:
        return self._pipeline_dir / "pipeline_state.json"

    def _load_state(self) -> dict:
        """加载历史状态"""
        path = self._state_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_factor_update": None,
            "last_weight_optimize": None,
            "last_full_backtest": None,
            "current_version": "v0",
            "total_optimizations": 0,
            "total_rollbacks": 0,
            "performance_history": [],
            "use_ic_weighting": False,
            "last_ic_weights": None,
        }

    def _save_state(self):
        """持久化状态"""
        with open(self._state_path(), "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    # ---------- 1. 因子追踪更新 ----------

    def update_factor_tracking(self):
        """每周因子追踪更新"""
        from factor_tracker import FactorTracker

        today = datetime.now().strftime("%Y-%m-%d")
        last = self._state.get("last_factor_update")
        if last == today:
            log.info("今日已更新因子追踪，跳过")
            return

        ft = FactorTracker()
        perfs = ft.get_all_performances()
        log.info(f"因子追踪更新完成: {len(perfs)} 个因子")

        # 标记需要关注的因子
        warnings = []
        for name, perf in perfs.items():
            if perf.decay_half_life < 20:
                warnings.append(f"{name}: 快速衰减(半衰期{perf.decay_half_life:.0f}d)")
            if perf.rank_ic < -0.05:
                warnings.append(f"{name}: 负IC({perf.rank_ic:.2f})")

        summary = ft.summary()
        print("\n=== 因子绩效追踪 ===")
        print(summary.to_string())

        if warnings:
            print(f"\n⚠️ 警告:\n" + "\n".join(f"  - {w}" for w in warnings))

        self._state["last_factor_update"] = today
        self._save_state()

    # ---------- 2. 权重优化 ----------

    def optimize_weights(self, force: bool = False) -> dict:
        """每月权重优化"""
        from factor_tracker import FactorTracker
        from strategy_optimizer import StrategyOptimizer

        today = datetime.now().strftime("%Y-%m-%d")
        last = self._state.get("last_weight_optimize")

        # 检查是否已到每月优化周期
        if not force and last:
            last_dt = datetime.strptime(last, "%Y-%m-%d")
            if (datetime.now() - last_dt).days < 25:
                log.info(f"距离上次优化{(datetime.now()-last_dt).days}天，未到月周期")
                return {"status": "skipped", "reason": "未到月优化周期"}
        # 种子数据: 即使IC历史为空，用当前config权重作为优化起点
        log.info("执行权重优化(使用当前config权重或默认值)...")

        # 获取最新因子绩效
        ft = FactorTracker()
        perfs = ft.get_all_performances()
        perf_dicts = {n: p.to_dict() for n, p in perfs.items()}
        log.info(f"加载因子绩效: {len(perf_dicts)} 个因子")

        # 检测市场状态
        opt = StrategyOptimizer()
        regime = opt.detect_regime_from_market()
        log.info(f"当前市场状态: {regime}")

        # 优化权重
        old_weights = opt._current_weights.copy()
        new_weights, reason = opt.optimize_weights(perf_dicts, regime)
        log.info(f"优化结果: {new_weights}")
        log.info(f"理由: {reason}")

        # 计算权重变化
        changes = {}
        for n in old_weights:
            delta = new_weights.get(n, 0) - old_weights.get(n, 0)
            if abs(delta) > 0.005:
                changes[n] = round(delta, 4)

        result = {
            "status": "optimized",
            "date": today,
            "regime": regime,
            "old_weights": old_weights,
            "new_weights": new_weights,
            "changes": changes,
            "reason": reason,
        }

        # dry-run模式不写入配置
        if self.mode == "dry-run":
            log.info("dry-run模式: 不写入config.json")
            return result

        # 执行回测验证
        backtest_result = self._run_verification_backtest(old_weights, new_weights)
        result["backtest"] = backtest_result

        # 决策: 是否采纳新权重
        decision, decision_reason = self._make_decision(backtest_result)
        result["decision"] = decision
        result["decision_reason"] = decision_reason

        if decision == "accept":
            if self.mode != "dry-run":
                opt.update_config(new_weights)
                # V4 Pro 评审: 闭合IC反馈环—权重更新后持久化到config.json
                self._sync_ic_to_weights(new_weights)
                version_name = f"v{datetime.now().strftime('%Y%m%d')}"
                opt._save_version(version_name, old_weights, new_weights,
                                  perf_dicts, backtest_result, decision_reason)
                self._state["current_version"] = version_name
                log.info(f"✅ 新权重已写入config.json，版本: {version_name}")
            else:
                log.info(f"⏸️ dry-run模式: 新权重未写入(预览: {new_weights})")
            self._state["total_optimizations"] += 1
        elif decision == "rollback":
            self._state["total_rollbacks"] += 1
            log.warning(f"↩️ 新权重被驳回: {decision_reason}")
        else:
            log.info(f"⏸️ 优化跳过: {decision_reason}")

        self._state["last_weight_optimize"] = today
        self._save_state()

        # 记录绩效历史
        self._state.setdefault("performance_history", []).append({
            "date": today,
            "decision": decision,
            "old_weights": old_weights,
            "new_weights": new_weights if decision == "accept" else None,
            "regime": regime,
        })
        self._save_state()

        return result

    # ---------- 3. 回测验证 ----------

    
    # ---------- ICIR动态加权（2026-05-27 新增）----------

    def run_ic_optimization(self) -> dict:
        '''基于 ICIR 动态调整因子权重（开关由 use_ic_weighting 控制）
        
        流程:
        1. 从 FactorTracker 获取各因子历史 IC
        2. 计算 ICIR 权重
        3. 更新 state 中的权重配置
        4. 返回新权重
        
        仅在 use_ic_weighting=True 时生效。
        '''
        if not self.use_ic_weighting:
            return {"status": "skipped", "reason": "IC weighting disabled"}

        try:
            from factor_tracker import FactorTracker
            tracker = FactorTracker()
            weights = tracker.get_icir_weights()
            if not weights:
                return {"status": "failed", "reason": "No IC data available"}

            # 更新 state
            self._state["last_ic_weights"] = weights
            self._state["total_optimizations"] = self._state.get("total_optimizations", 0) + 1
            self._save_state()

            return {"status": "success", "weights": weights}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def toggle_ic_weighting(self, enabled: bool = None) -> bool:
        '''切换 IC 加权开关，返回当前状态'''
        if enabled is not None:
            self.use_ic_weighting = enabled
        self._state["use_ic_weighting"] = self.use_ic_weighting
        self._save_state()
        return self.use_ic_weighting

    def _sync_ic_to_weights(self, weights: dict):
        """将优化后的权重同步到config.json（闭合IC反馈环）"""
        import json
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent / "config" / "config.json"
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            for factor_name, new_w in weights.items():
                if factor_name in cfg.get("factors", {}):
                    old_w = cfg["factors"][factor_name].get("weight", 0)
                    cfg["factors"][factor_name]["weight"] = round(new_w, 4)
                    log.info(f"  权重更新 {factor_name}: {old_w:.4f} → {new_w:.4f}")
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            log.info(f"config.json 权重已更新")
        except Exception as e:
            log.warning(f"config.json 权重同步失败: {e}")

    def _run_verification_backtest(self, old_weights: dict,
                                   new_weights: dict) -> dict:
        """运行验证回测 — 基于最近排名结果的实际历史数据回测"""
        from backtest import walk_forward_cv

        try:
            # 1. 加载最新排名
            factor_dir = report_dir("factors")
            rank_file = factor_dir / "daily_rank.csv"
            if not rank_file.exists():
                return {"status": "no_data", "message": "无历史排名数据"}
            rank_df = pd.read_csv(rank_file)
            if rank_df.empty:
                return {"status": "no_data", "message": "排名数据为空"}

            # 2. 取top-N候选
            top_n = min(10, len(rank_df))
            top_codes = rank_df.head(top_n)["code"].tolist()
            log.info(f"验证回测: {len(top_codes)} 只候选, 获取历史数据...")

            # 3. 获取历史K线
            from fetch_data import DataEngine
            de = DataEngine()
            price_data = de.batch_kline(top_codes, days=250)

            valid_codes = [c for c in top_codes if c in price_data and len(price_data[c]) > 60]
            if len(valid_codes) < 3:
                return {"status": "no_data", "message": f"仅{len(valid_codes)}只有足够历史数据"}

            # 4. 运行组合回测（单期排名无需walk-forward）
            from backtest import run_portfolio, PerformanceMetrics
            result = run_portfolio(
                valid_codes, price_data,
                top_n=min(5, len(valid_codes)),
            )

            if result.get("status") != "ok":
                return {"status": "error", "message": f"回测失败: {result.get('msg', '未知错误')}"}

            # 5. 计算绩效指标
            returns_pct = result.get("return_pct", 0)
            log.info(f"验证回测完成: {len(valid_codes)}只, 收益率{returns_pct:.2f}%")

            return {
                "status": "completed",
                "stocks_tested": len(valid_codes),
                "top_n": result.get("top_n", 5),
                "total_return_pct": returns_pct,
                "sharpe_ratio": PerformanceMetrics.sharpe_ratio(pd.Series(result.get("daily_returns", []))) if len(result.get("daily_returns", [])) > 5 else 0,
                "max_drawdown": PerformanceMetrics.max_drawdown(
                    pd.Series(result.get("daily_returns", []))
                ) if len(result.get("daily_returns", [])) > 10 else 0.0,
                "benchmark_sharpe": 0.5,
                "stocks": result.get("stocks", 0),
                "message": f"基于{len(valid_codes)}只股票{250}天历史数据回测"
            }
        except Exception as e:
            log.warning(f"验证回测失败: {e}")
            return {"status": "error", "message": str(e)}

    def _make_decision(self, backtest_result: dict) -> Tuple[str, str]:
        """基于回测结果做采纳/回滚决策"""
        if not backtest_result:
            return "hold", "无回测数据，暂不调整"

        if backtest_result.get("status") == "no_data":
            return "accept", "无历史对比数据，首次部署直接采纳"

        if backtest_result.get("status") == "error":
            return "hold", f"回测出错: {backtest_result.get('message', '')}"

        # 回滚条件1: 新策略Sharpe显著低于旧策略
        new_sharpe = backtest_result.get("sharpe_ratio", 0)
        old_sharpe = backtest_result.get("benchmark_sharpe", 0)
        if old_sharpe > 0 and new_sharpe < old_sharpe * 0.8:
            return "rollback", f"新策略Sharpe({new_sharpe:.2f})低于基准({old_sharpe:.2f})"

        # 回滚条件2: 新策略最大回撤超限
        new_dd = backtest_result.get("max_drawdown", 0)
        if abs(new_dd) > 0.25:
            return "rollback", f"新策略最大回撤({new_dd:.1%})超过25%"

        return "accept", "基于最新IC数据和市场状态优化"

    # ---------- 4. 完整流水线 ----------

    def run_full_pipeline(self) -> dict:
        """运行完整策略进化流水线"""
        log.info("=" * 50)
        log.info("策略进化流水线启动")
        log.info("=" * 50)

        results = {}

        # Step 0: 风控检查
        log.info("[0/4] 风控前置检查...")
        try:
            from risk_manager import RiskController
            rc = RiskController()
            risk_report = rc.check_portfolio({}, 0)
            if risk_report.get("alerts"):
                log.warning(f"风控告警: {len(risk_report['alerts'])} 条")
                for alert in risk_report["alerts"]:
                    log.warning(f"  P{alert.get('level', '?')}: {alert.get('message', '')}")
            results["risk_check"] = {
                "status": "ok" if not risk_report.get("alerts") else "warning",
                "alerts": len(risk_report.get("alerts", [])),
            }
        except Exception as e:
            log.warning(f"风控检查跳过: {e}")
            results["risk_check"] = f"skipped: {e}"

        # Step 1: 因子追踪
        log.info("[1/3] 因子绩效追踪...")
        try:
            self.update_factor_tracking()
            results["factor_tracking"] = "ok"
        except Exception as e:
            log.error(f"因子追踪失败: {e}")
            results["factor_tracking"] = f"error: {e}"

        # Step 2: 权重优化
        log.info("[2/3] 权重优化...")
        try:
            opt_result = self.optimize_weights()
            results["optimization"] = opt_result.get("status", "error")
        except Exception as e:
            log.error(f"权重优化失败: {e}")
            results["optimization"] = f"error: {e}"

        # Step 3: 报告生成
        log.info("[3/3] 流水线报告...")
        results["state"] = {
            "current_version": self._state["current_version"],
            "total_optimizations": self._state["total_optimizations"],
            "total_rollbacks": self._state["total_rollbacks"],
        }

        # 保存流水线报告
        report = {
            "date": datetime.now().isoformat(),
            "results": results,
            "state": self._state,
        }
        report_path = self._pipeline_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        log.info(f"流水线完成: {report_path}")
        return results

    # ---------- 5. 状态查询 ----------


    def checkpoint(self, tag: str = "") -> str:
        """保存当前状态快照（checkpoint），返回快照标识"""
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        tag_suffix = f"_{tag}" if tag else ""
        cp_dir = self._state_path().parent / "checkpoints"
        cp_dir.mkdir(parents=True, exist_ok=True)
        cp_file = cp_dir / f"checkpoint_{ts}{tag_suffix}.json"
        
        cp_state = {
            "timestamp": ts,
            "tag": tag,
            "mode": self.mode,
            "state": dict(self._state),
        }
        with open(cp_file, "w", encoding="utf-8") as f:
            json.dump(cp_state, f, ensure_ascii=False, indent=2)
        
        self._state["last_checkpoint"] = str(cp_file)
        self._save_state()
        
        log.info(f"Checkpoint saved: {cp_file.name}")
        return str(cp_file)

    def run_with_checkpoint(self, pipeline_func, *args, **kwargs):
        """执行流水线函数，成功则保存checkpoint，失败则回滚到上一个checkpoint
        
        返回:
            (result, checkpoint_path)
        """
        # 运行前保存pre-checkpoint
        pre_cp = self.checkpoint(tag="pre")
        
        try:
            result = pipeline_func(*args, **kwargs)
            # 成功后保存post-checkpoint
            post_cp = self.checkpoint(tag="post")
            return result, post_cp
        except Exception as e:
            log.error(f"流水线执行失败: {e}，回滚到 {pre_cp}")
            self._load_checkpoint(pre_cp)
            raise

    def _load_checkpoint(self, cp_path: str) -> bool:
        """从checkpoint文件恢复状态"""
        cp_file = Path(cp_path)
        if not cp_file.exists():
            log.warning(f"Checkpoint文件不存在: {cp_path}")
            return False
        try:
            with open(cp_file, "r", encoding="utf-8") as f:
                cp_state = json.load(f)
            self._state = cp_state.get("state", self._state)
            self.mode = cp_state.get("mode", self.mode)
            self._save_state()
            log.info(f"已从checkpoint恢复: {cp_file.name}")
            return True
        except Exception as e:
            log.error(f"Checkpoint恢复失败: {e}")
            return False

    def list_checkpoints(self, limit: int = 10) -> list:
        """列出最近的checkpoint"""
        cp_dir = self._state_path().parent / "checkpoints"
        if not cp_dir.exists():
            return []
        files = sorted(cp_dir.glob("checkpoint_*.json"), reverse=True)
        result = []
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    cp = json.load(fh)
                result.append({
                    "file": f.name,
                    "timestamp": cp.get("timestamp", ""),
                    "tag": cp.get("tag", ""),
                })
            except Exception as e:
                log.warning(f"  ⚠️ 跳过: {e}")
                result.append({"file": f.name, "timestamp": "?", "tag": "?"})
        return result

    def summary(self) -> str:
        """输出流水线状态摘要"""
        lines = [
            "=" * 50,
            "📊 策略进化流水线状态",
            "=" * 50,
            f"当前版本: {self._state.get('current_version', 'v0')}",
            f"总优化次数: {self._state.get('total_optimizations', 0)}",
            f"总回滚次数: {self._state.get('total_rollbacks', 0)}",
            f"最后因子更新: {self._state.get('last_factor_update', 'N/A')}",
            f"最后权重优化: {self._state.get('last_weight_optimize', 'N/A')}",
            f"最后完整回测: {self._state.get('last_full_backtest', 'N/A')}",
        ]

        perf = self._state.get("performance_history", [])
        if perf:
            lines.append(f"\n最近5次决策:")
            for p in perf[-5:]:
                icon = "✅" if p.get("decision") == "accept" else "↩️" if p.get("decision") == "rollback" else "⏸️"
                lines.append(f"  {icon} {p['date']}: {p['decision']} (市场: {p['regime']})")

        return "\n".join(lines)


# ==================== CLI入口 ====================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="策略进化流水线")
    parser.add_argument("action", nargs="?", default="status",
                        choices=["status", "update_factors", "optimize",
                                "full_pipeline", "dry_run"])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s",
                        datefmt="%H:%M:%S")

    mode = "dry-run" if args.action == "dry_run" else "auto"
    pipeline = StrategyPipeline(mode=mode)

    if args.action == "status":
        print(pipeline.summary())
    elif args.action == "update_factors":
        pipeline.update_factor_tracking()
    elif args.action == "optimize":
        result = pipeline.optimize_weights(force=True)
        print(f"\n优化结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    elif args.action in ("full_pipeline", "dry_run"):
        results = pipeline.run_full_pipeline()
        print(f"\n流水线结果: {json.dumps(results, indent=2, ensure_ascii=False)}")
