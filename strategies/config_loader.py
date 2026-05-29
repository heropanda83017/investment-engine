#!/usr/bin/env python3
"""配置加载器 — 统一路径+配置管理"""

import sys, os, json, logging
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("config")

_CURRENT = Path(__file__).resolve()
PROJECT_ROOT = _CURRENT.parent.parent
SRC_DIR = _CURRENT.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"

def _load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Config load failed: {e}")
        return {}

CFG = _load_config()
# 向后兼容: 将 blackhorse 子配置提升到顶层
# (原 blackhorse-ai 配置是扁平结构，合并后嵌套在 blackhorse 下)
if "blackhorse" in CFG and isinstance(CFG["blackhorse"], dict):
    for _k, _v in CFG["blackhorse"].items():
        if _k not in CFG:
            CFG[_k] = _v

# 权重归一化校验
_factor_weights = CFG.get("blackhorse", {}).get("factors", {})
_total_w = sum(v.get("weight", 0) for v in _factor_weights.values())
if abs(_total_w - 1.0) > 0.02:
    log.warning(f"因子权重和={_total_w:.3f}，偏离1.0超过2%，评分可能有偏")
BACKTEST_CFG = CFG.get("backtest", {})
FACTOR_THRESHOLDS = CFG.get("factor_thresholds", {})
OPTIMIZER_CFG = CFG.get("optimizer", {})
CACHE_TTL_HOURS = CFG.get("data", {}).get("cache_ttl_hours", 6)

from _path_setup import ensure_ie_paths
ensure_ie_paths()
from env import IE_SCRIPTS as _IE_SCRIPTS
IE_SCRIPTS = str(_IE_SCRIPTS)

# 确保IE_SCRIPTS在sys.path中（供所有模块共享）
if IE_SCRIPTS not in sys.path and os.path.exists(IE_SCRIPTS):
    sys.path.insert(0, IE_SCRIPTS)

def data_dir(subdir: str = "") -> Path:
    d = PROJECT_ROOT / "data" / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d

def report_dir(subdir: str = "") -> Path:
    d = PROJECT_ROOT / "reports" / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d

def log_dir() -> Path:
    d = PROJECT_ROOT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_config_path() -> Path:
    """返回 config.json 的绝对路径"""
    config_file = Path(__file__).parent.parent / "config" / "config.json"
    if not config_file.exists():
        config_file = Path(__file__).parent / "config.json"  # fallback: src/config.json
    return config_file if config_file.exists() else None


def cache_path(name: str) -> Path:
    return data_dir("cache") / f"{name}.pkl"

def import_from_dsh(module_name: str):
    """从investment-engine延迟导入模块（路径不存在时返回None）"""
    if not os.path.exists(IE_SCRIPTS):
        log.warning(f"IE_SCRIPTS不存在: {IE_SCRIPTS}")
        return None
    if IE_SCRIPTS not in sys.path:
        sys.path.insert(0, IE_SCRIPTS)
    try:
        return __import__(module_name)
    except ImportError as e:
        log.warning(f"从IE导入 {module_name} 失败: {e}")
        return None

def mmx_path() -> str:
    import shutil
    mmx = shutil.which("mmx")
    if mmx:
        return mmx
    candidates = [
        str(Path.home() / "AppData/Roaming/npm/mmx.cmd"),
        str(Path.home() / "AppData/Roaming/npm/mmx"),
        "mmx",
    ]
    for c in candidates:
        if shutil.which(c) or os.path.exists(c):
            return c
    return "mmx"
