"""
env.py — 投资体系统一路径与环境变量管理
=========================================
所有 E: 盘硬编码路径集中管理于此。
其他文件通过 `from env import DATA_ROOT, DSH, BH, ...` 引用。

用法:
    # 设置环境变量 AIGC_DATA_ROOT 可覆盖默认路径
    $env:AIGC_DATA_ROOT = "D:/MyData"  # Windows PowerShell
    export AIGC_DATA_ROOT="/mnt/data"   # Linux/Mac
    
默认值: E:/AIGC-KB/输出 (向后兼容)
"""

import os, json, logging
from pathlib import Path
logger = logging.getLogger("env")

# 根路径 (通过环境变量可迁移)
DATA_ROOT = Path(os.environ.get("AIGC_DATA_ROOT", "E:/AIGC-KB/输出"))

# investment-engine (新统一底座)
IE_ROOT = DATA_ROOT / "investment-engine"
IE_SCRIPTS = IE_ROOT / "scripts"
IE_STRATEGIES = IE_ROOT / "strategies"
IE_PIPELINES = IE_ROOT / "pipelines"
IE_TRACKING = IE_ROOT / "tracking"
IE_SYSTEM = IE_ROOT / "system"
IE_CONFIG = IE_ROOT / "config"
IE_CACHE = IE_ROOT / "_cache"

# investment-engine 缓存的子目录
IE_CACHE_OPTIMIZED = IE_CACHE / "optimized"
IE_CACHE_TICKFLOW = IE_CACHE / "tickflow"
IE_CACHE_ANALYSIS = IE_CACHE / "analysis"
IE_CACHE_MONITOR = IE_CACHE / "monitor"

# blackhorse-ai (旧路径，迁移过渡期保留)
BH_CACHE = DATA_ROOT / "blackhorse-ai/data/cache"
BH_REPORTS = DATA_ROOT / "blackhorse-ai/reports"

# 投资跟踪 (新路径指向 investment-engine)
TRACKING = IE_TRACKING
SYSTEM = IE_SYSTEM


# 其他
XHS_REPORT = DATA_ROOT / "xhs-sentiment-monitoring/daily_report.md"
XHS_SCORES = DATA_ROOT / "xhs-sentiment-monitoring/sentiment_scores.json"
WX_ARTICLES = DATA_ROOT / "wechat-articles"

# 旧路径兼容 (00-信源能力指南已整合到investment-engine)
# 保留引用但指向IE_SCRIPTS
LEGACY_SCRIPTS = IE_SCRIPTS


# ===== 配置注册表 =====
# 统一配置加载入口 — 不合并配置文件，只统一访问方式
CONFIG_REGISTRY = {
    "dsh": IE_CONFIG / "config.json",
    "blackhorse": IE_CONFIG / "config.json",
    "tickflow": IE_SCRIPTS / "tickflow_config.json",
    "tracking": TRACKING / "tracker_config.json",
}


def load_config(name: str) -> dict:
    """
    统一配置加载入口。
    
    Args:
        name: "blackhorse" | "tickflow" | "tracking"
    
    Returns:
        配置字典。文件不存在或解析失败时返回空 dict。
    """
    path = CONFIG_REGISTRY.get(name)
    if path is None:
        raise ValueError(f"未知配置名称: {name}, 可选: {list(CONFIG_REGISTRY.keys())}")
    if not path.exists():
        logger.warning("配置文件不存在: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("配置加载失败 %s: %s", name, e)
        return {}
