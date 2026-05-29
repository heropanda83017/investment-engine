#!/usr/bin/env python3
"""TickFlow 实时数据提供者 — 对接 tickflow 逐笔流水线"""

import sys, logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import os

from env import DATA_ROOT, IE_SCRIPTS, IE_STRATEGIES, IE_PIPELINES, BH_CACHE, BH_REPORTS, TRACKING, SYSTEM, XHS_REPORT, XHS_SCORES, WX_ARTICLES


log = logging.getLogger("tickflow_provider")

# tickflow 脚本路径
TICKFLOW_PATH = Path(os.environ.get("TICKFLOW_PATH", str(IE_SCRIPTS / "tickflow.py")))


class TickFlowProvider:
    """基于 tickflow 的高频数据提供者（补充日频数据中的日内信号）"""
    
    def get_kline(self, code: str, days: int = 120) -> Optional[pd.DataFrame]:
        """获取K线（从天级tickflow聚合或回退到日频）"""
        return None  # tickflow 做盘后分析用，不替代日K线
    
    def get_intraday_snapshot(self, code: str) -> dict:
        """获取日内逐笔快照摘要"""
        try:
            import subprocess, json
            r = subprocess.run(
                [sys.executable, str(TICKFLOW_PATH), "snapshot", code],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception as e:
            log.debug(f"tickflow snapshot {code}: {e}")
        return {}
    
    def get_financial(self, code: str) -> pd.DataFrame:
        return pd.DataFrame()
    
    def get_all_stocks(self) -> list:
        return []
    
    def get_stock_name(self, code: str) -> str:
        return ""
