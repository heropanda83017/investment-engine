"""数据源健康监控 — 可用性追踪 + 自动降级"""

import sys, json, logging, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from config_loader import IE_SCRIPTS, CFG as CONFIG, report_dir

log = logging.getLogger("data_monitor")

DEFAULT_SOURCES = [
    {"name": "baostock", "priority": 0, "type": "kline+financial",
     "fallback": ["tushare", "akshare", "cache"]},
    {"name": "tushare", "priority": 1, "type": "kline+financial",
     "fallback": ["akshare", "cache"]},
    {"name": "akshare", "priority": 2, "type": "kline+financial",
     "fallback": ["cache"]},
    {"name": "cache", "priority": 3, "type": "kline", "fallback": []},
]


class DataSourceHealth:
    """单个数据源健康状态"""
    def __init__(self, name: str):
        self.name = name
        self.success_count = 0
        self.failure_count = 0
        self.total_latency_ms = 0.0
        self.last_success = None
        self.last_failure = None
        self.consecutive_failures = 0
        self.is_available = True

    def record_success(self, latency_ms: float):
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.last_success = time.time()
        self.consecutive_failures = 0
        self.is_available = True

    def record_failure(self):
        self.failure_count += 1
        self.last_failure = time.time()
        self.consecutive_failures += 1
        if self.consecutive_failures >= 5:
            self.is_available = False

    def avg_latency(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.total_latency_ms / self.success_count if self.success_count > 0 else 0.0

    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.is_available,
            "success_rate": round(self.success_rate(), 3),
            "avg_latency_ms": round(self.avg_latency(), 1),
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.success_count + self.failure_count,
        }


class DataSourceMonitor:
    """数据源健康监控器 — 追踪可用性、延迟、降级链"""

    def __init__(self):
        self._sources: Dict[str, DataSourceHealth] = {}
        self._deg_chain = CONFIG.get("data_sources", DEFAULT_SOURCES)
        for src in self._deg_chain:
            self._sources[src["name"]] = DataSourceHealth(src["name"])
        self._monitor_dir = report_dir("monitor")
        self._monitor_dir.mkdir(parents=True, exist_ok=True)

    def record(self, source: str, success: bool, latency_ms: float = 0):
        """记录一次数据源调用结果"""
        if source not in self._sources:
            self._sources[source] = DataSourceHealth(source)
        if success:
            self._sources[source].record_success(latency_ms)
        else:
            self._sources[source].record_failure()

    def get_best_available(self, data_type: str = "kline") -> str:
        """获取当前可用的最优数据源(按优先级 + 可用性)"""
        for src in self._deg_chain:
            h = self._sources.get(src["name"])
            min_rate = CONFIG.get("data_monitor", {}).get("min_success_rate", 0.3)
            if h and h.is_available and h.success_rate() > min_rate:
                return src["name"]
        return "cache"

    def get_degrade_chain(self, source: str) -> List[str]:
        """获取指定数据源的降级链"""
        for src in self._deg_chain:
            if src["name"] == source:
                return src.get("fallback", [])
        return []

    def snapshot(self) -> dict:
        """当前健康快照"""
        return {
            "timestamp": datetime.now().isoformat(),
            "sources": {n: h.to_dict() for n, h in self._sources.items()},
            "best_available": self.get_best_available(),
        }

    def should_degrade(self, source: str) -> bool:
        """当前数据源是否应降级"""
        h = self._sources.get(source)
        if not h:
            return True
        return not h.is_available or h.success_rate() < 0.5

    def save_snapshot(self):
        """保存快照到磁盘"""
        path = self._monitor_dir / "data_source_health.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, indent=2, ensure_ascii=False)

    def summary(self) -> str:
        """输出可读摘要"""
        snap = self.snapshot()
        lines = ["📡 数据源健康状态", "=" * 40]
        for name, info in snap["sources"].items():
            icon = "🟢" if info["available"] else "🔴"
            lines.append(f"{icon} {name}: 成功率{info['success_rate']:.0%} "
                         f"延迟{info['avg_latency_ms']}ms "
                         f"连续失败{info['consecutive_failures']}次")
        lines.append(f"\n最优信源: {snap['best_available']}")
        return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dm = DataSourceMonitor()
    print(dm.summary())


def backfill_ic_history():
    """一次性回填IC历史数据：从因子快照重建IC记录
    
    在系统首次部署或因子权重重置后调用。
    扫描 data/factors/factor_snapshot_*.csv 文件，
    为每个因子计算历史IC并写入 factor_tracker 数据库。
    
    返回: 回填的记录数
    """
    import pandas as pd
    import numpy as np
    from pathlib import Path
    from config_loader import report_dir
    from factor_tracker import FactorTracker
    from scipy.stats import spearmanr
    
    ft = FactorTracker()
    factor_dir = Path(report_dir("factors"))
    snapshots = sorted(factor_dir.glob("factor_snapshot_*.csv"))
    
    if not snapshots:
        # 无历史快照，生成模拟IC数据冷启动
        log.info("无历史快照，使用默认IC种子数据")
        try:
            from evolution_engine import EvolutionEngine
            ee = EvolutionEngine()
            count = ee.backfill_from_history() if hasattr(ee, 'backfill_from_history') else 0
            return count
        except Exception:
            return 0
    
    count = 0
    for snap in snapshots:
        try:
            df = pd.read_csv(snap)
            factor_cols = [c for c in df.columns if c not in ("code", "date", "total", "rank")]
            for col in factor_cols:
                scores = df[col].dropna().values
                totals = df["total"].dropna().values
                if len(scores) >= 10 and len(totals) >= 10:
                    ic, _ = spearmanr(scores[:min(len(scores), len(totals))], 
                                      totals[:min(len(scores), len(totals))])
                    if not np.isnan(ic):
                        ft._history.setdefault(col, []).append({
                            "date": snap.stem.replace("factor_snapshot_", ""),
                            "ic": round(float(ic), 4),
                        })
                        count += 1
        except Exception:
            continue
    
    if count > 0:
        ft._save_history()
        log.info(f"IC历史回填完成: {count} 条记录")
    
    return count
