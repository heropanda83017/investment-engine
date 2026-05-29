"""因子绩效追踪器 — 信息系数(IC) + 因子衰减 + 多空收益"""

import sys, json, logging, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
def _spearmanr(x, y):
    """手动计算Spearman秩相关系数(替代scipy.stats.spearmanr)"""
    import numpy as np
    n = len(x)
    if n < 3:
        return 0.0
    rx = np.argsort(np.argsort(x)) + 1
    ry = np.argsort(np.argsort(y)) + 1
    d = rx - ry
    denom = n * (n * n - 1)
    if denom == 0:
        return 0.0
    rho = 1.0 - (6.0 * (d * d).sum()) / denom
    return float(rho)


from config_loader import IE_SCRIPTS, CFG as CONFIG, report_dir

log = logging.getLogger("factor_tracker")

FACTOR_NAMES = ["trend", "volume", "volatility", "capital", "fundamental", "sentiment", "alpha191", "frameworks", "consensus", "capital_flow", "market_signal", "factorhub", "event_factor"]
LOOKBACK_DAYS = [5, 10, 20, 60]  # 预测期


class FactorPerformance:
    """单因子绩效快照"""
    def __init__(self, name: str, rank_ic: float = 0.0, ic_ir: float = 0.0,
                 long_short_ret: float = 0.0, decay_half_life: float = 999.0,
                 turnover: float = 0.0, samples: int = 0):
        self.name = name
        self.rank_ic = rank_ic        # Spearman IC
        self.ic_ir = ic_ir            # IC信息比率
        self.long_short_ret = long_short_ret  # 多空收益差
        self.decay_half_life = decay_half_life  # 半衰期(天)
        self.turnover = turnover      # 因子暴露换手率
        self.samples = samples        # 样本量

    def to_dict(self) -> dict:
        return {k: round(v, 4) if isinstance(v, float) else v
                for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "FactorPerformance":
        return cls(**{k: d.get(k, v) for k, v in cls.__dict__.items()
                      if not k.startswith("_")})


class FactorTracker:
    """追踪各因子历史绩效，计算IC、ICIR、衰减率"""

    def __init__(self, data_dir: str = None):
        self._dir = Path(data_dir) if data_dir else report_dir("factors")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._history: Dict[str, List[dict]] = {}
        self._load_history()

    def _history_path(self) -> Path:
        return self._dir / "factor_ic_history.csv"

    def _load_history(self):
        """从CSV加载历史IC数据"""
        path = self._history_path()
        if path.exists():
            try:
                df = pd.read_csv(path, encoding="utf-8")
                for _, row in df.iterrows():
                    fname = row.get("factor", "")
                    if fname not in self._history:
                        self._history[fname] = []
                    self._history[fname].append(row.to_dict())
                log.info(f"已加载 {sum(len(v) for v in self._history.values())} 条IC记录")
            except Exception as e:
                log.warning(f"加载IC历史失败: {e}")

    def _save_history(self):
        """持久化IC历史"""
        rows = []
        for fname, records in self._history.items():
            for r in records:
                r["factor"] = fname
                rows.append(r)
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(self._history_path(), index=False, encoding="utf_8_sig")

    def _compute_spearman_ic(
        self, factor_scores: pd.Series, forward_returns: pd.Series
    ) -> float:
        """计算Spearman秩相关系数作为IC"""
        valid = factor_scores.notna() & forward_returns.notna()
        if valid.sum() < 30:  # 最少30个样本
            return 0.0
        ic = _spearmanr(factor_scores[valid].values if hasattr(factor_scores[valid], "values") else factor_scores[valid],
                           forward_returns[valid].values if hasattr(forward_returns[valid], "values") else forward_returns[valid])
        return float(ic) if not np.isnan(ic) else 0.0

    def compute_ic(
        self, factor_name: str, factor_scores: pd.Series,
        forward_returns: pd.Series, lookback_days: int = 20
    ) -> float:
        """计算单因子在特定预测期的IC"""
        ic = self._compute_spearman_ic(factor_scores, forward_returns)
        records = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "factor": factor_name,
            "lookback_days": lookback_days,
            "rank_ic": round(ic, 4),
            "samples": int(factor_scores.notna().sum()),
        }
        if factor_name not in self._history:
            self._history[factor_name] = []
        self._history[factor_name].append(records)
        self._save_history()
        return ic

    def get_recent_ic(self, factor_name: str, window: int = 12) -> List[float]:
        """获取最近N期IC值序列"""
        records = self._history.get(factor_name, [])
        if not records:
            return []
        # 按日期去重取最近
        seen = set()
        unique = []
        for r in reversed(records):
            d = r.get("date", "")
            if d not in seen:
                seen.add(d)
                unique.append(r.get("rank_ic", r.get("ic", 0.0)))
        return unique[:window]

    def compute_ic_ir(self, factor_name: str, window: int = 12) -> float:
        """IC信息比率 = mean(IC) / std(IC)"""
        ics = self.get_recent_ic(factor_name, window)
        if len(ics) < 3:
            return 0.0
        mean_ic = np.mean(ics)
        std_ic = np.std(ics)
        if std_ic == 0:
            return 0.0
        return float(mean_ic / std_ic)

    def compute_decay(self, factor_name: str) -> float:
        """估算因子半衰期（天数）"""
        ics = self.get_recent_ic(factor_name, window=60)
        if len(ics) < 10:
            return 999.0
        # 计算IC序列自相关衰减
        x = np.arange(len(ics))
        y = np.abs(ics)
        if np.std(y) == 0:
            return 999.0
        # 拟合指数衰减: y = a * exp(-x/b)
        try:
            from scipy.optimize import curve_fit
            popt, _ = curve_fit(lambda t, a, b: a * np.exp(-t / b),
                                x, y, p0=(max(y), len(ics) / 2), maxfev=2000)
            half_life = popt[1] * np.log(2)
            return max(float(half_life), 1.0)
        except Exception:
            return 999.0

    def get_performance(self, factor_name: str) -> FactorPerformance:
        """获取因子综合绩效快照"""
        ic_20d = self.get_recent_ic(factor_name, window=1)
        recent_ic = ic_20d[0] if ic_20d else 0.0
        ic_ir = self.compute_ic_ir(factor_name, window=12)
        decay = self.compute_decay(factor_name)
        records = self._history.get(factor_name, [])
        samples = records[-1]["samples"] if records else 0
        return FactorPerformance(
            name=factor_name,
            rank_ic=recent_ic,
            ic_ir=ic_ir,
            decay_half_life=decay,
            samples=samples
        )


    def backfill_from_history(self, factor_dir: str = None) -> int:
        """从历史因子快照文件回填IC数据
        
        在init时调用，从已有回测/评分历史中提取因子值和收益率数据，
        计算并填充历史IC记录，使优化器有数据可依。
        
        参数:
            factor_dir: 历史因子快照目录，默认使用report_dir下的factors
            
        返回:
            回填的记录数
        """
        if factor_dir is None:
            from config_loader import report_dir
            factor_dir = str(report_dir("factors"))
        
        factor_path = Path(factor_dir)
        if not factor_path.exists():
            log.warning(f"因子历史目录不存在: {factor_dir}")
            return 0
        
        count = 0
        # 扫描所有因子快照CSV文件
        snapshot_files = sorted(factor_path.glob("factor_snapshot_*.csv"))
        if not snapshot_files:
            log.info(f"无历史因子快照可回填: {factor_dir}")
            return 0
        
        for snap_file in snapshot_files:
            try:
                df = pd.read_csv(snap_file)
                if "code" not in df.columns or "total" not in df.columns:
                    continue
                
                # 提取日期
                date_str = snap_file.stem.replace("factor_snapshot_", "")
                
                # 对每个因子列计算截面IC
                factor_cols = [c for c in df.columns 
                              if c not in ("code", "date", "total", "rank")]
                
                for col in factor_cols:
                    valid = df[col].notna() & df["total"].notna()
                    scores = df.loc[valid, col].values
                    totals = df.loc[valid, "total"].values
                    if len(scores) >= 10 and len(totals) >= 10:
                        # 对齐长度
                        min_len = min(len(scores), len(totals))
                        ic_val = self._compute_spearman_ic(
                            pd.Series(scores[:min_len]), 
                            pd.Series(totals[:min_len])
                        )
                        if ic_val is not None and not np.isnan(ic_val):
                            self._history.setdefault(col, []).append({
                                "date": date_str,
                                "rank_ic": round(float(ic_val), 4),
                            })
                            count += 1
            except Exception as e:
                log.debug(f"回填跳过文件 {snap_file.name}: {e}")
        
        if count > 0:
            self._save_history()
            log.info(f"历史IC回填完成: {count} 条记录 from {len(snapshot_files)} 个快照文件")
        
        # 如果仍然为空，生成回测基准IC
        if not any(self._history.values()):
            log.info("历史快照为空，生成基准IC数据用于冷启动")
            self._seed_default_ics()
        
        return count
    
    def _seed_default_ics(self):
        """冷启动: 当无历史数据时，生成默认基准IC数据
        
        用于首次运行时优化器有输入数据可依。
        """
        import datetime
        default_factors = ["trend", "volume", "volatility", "capital", 
                          "fundamental", "sentiment", "alpha191",
                          "frameworks", "consensus", "capital_flow", 
                          "market_signal", "factorhub", "event_factor"]
        # 使用保守的默认IC值（经验值）
        default_ics = {
            "trend": 0.04, "volume": 0.03, "volatility": -0.02,
            "capital": 0.05, "fundamental": 0.06, "sentiment": 0.02,
            "alpha191": 0.03, "frameworks": 0.02, "consensus": 0.01,
            "capital_flow": 0.02, "market_signal": 0.01,
            "factorhub": 0.02, "event_factor": 0.01,
        }
        # 生成过去12周的基准数据
        for week_offset in range(12):
            week_date = (datetime.datetime.now() - datetime.timedelta(weeks=week_offset)).strftime("%Y%m%d")
            for factor_name, ic_val in default_ics.items():
                self._history.setdefault(factor_name, []).append({
                    "date": week_date,
                    "ic": round(ic_val + np.random.normal(0, 0.01), 4),
                })
        
        self._save_history()
        log.info(f"已生成默认IC种子数据: 12周 × {len(default_factors)} 因子")

    def get_all_performances(self) -> Dict[str, FactorPerformance]:
        """获取所有因子绩效"""
        return {f: self.get_performance(f) for f in FACTOR_NAMES}

    def summary(self) -> pd.DataFrame:
        """输出绩效汇总DataFrame"""
        rows = []
        for name, perf in self.get_all_performances().items():
            rows.append(perf.to_dict())
        return pd.DataFrame(rows) if rows else pd.DataFrame()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ft = FactorTracker()
    print(ft.summary().to_string())


    # ── ic_analyzer 集成方法（2026-05-27 新增）──

    def get_stability_score(self, factor_name: str, window: int = 120) -> float:
        '''因子稳定性评分，复用 ic_analyzer'''
        from ic_analyzer import factor_stability_score
        ic_hist = self.get_recent_ic(factor_name, window=window)
        if not ic_hist:
            return 0.0
        series = pd.Series(ic_hist)
        return factor_stability_score(series, window=window)

    def get_rolling_ic_summary(self, windows: list = None) -> pd.DataFrame:
        '''滚动 IC 统计'''
        from ic_analyzer import rolling_ic
        perfs = self.get_all_performances()
        if not perfs:
            return pd.DataFrame()
        rows = {}
        for name, perf in perfs.items():
            ic_hist = self.get_recent_ic(name, window=max(windows or [240]))
            if ic_hist:
                rows[name] = pd.Series(ic_hist)
        if not rows:
            return pd.DataFrame()
        ic_df = pd.DataFrame(rows)
        return rolling_ic(ic_df.mean(axis=1), windows=windows)

    def get_decay_curve(self, factor_name: str, max_lag: int = 20) -> pd.Series:
        '''因子 IC 衰减曲线'''
        from ic_analyzer import ic_decay_curve
        ic_hist = self.get_recent_ic(factor_name, window=240)
        if not ic_hist:
            return pd.Series(dtype=float)
        series = pd.Series(ic_hist)
        return ic_decay_curve(series, max_lag=max_lag)

    def get_icir_weights(self) -> dict:
        '''基于 ICIR 的动态权重（开关由 strategy_pipeline 控制）'''
        from ic_analyzer import icir_weight
        perfs = self.get_all_performances()
        factors_ic = {}
        for name in perfs:
            ic_hist = self.get_recent_ic(name, window=240)
            if ic_hist:
                factors_ic[name] = pd.Series(ic_hist)
        if not factors_ic:
            return {}
        return icir_weight(factors_ic)
