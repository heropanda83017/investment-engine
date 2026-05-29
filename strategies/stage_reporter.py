"""
stage_reporter.py — 流水线阶段管理与状态报告
"""
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("stage_reporter")

STAGE_DEFINITIONS = {
    "S01": "数据采集",
    "S02": "因子评分",
    "S03": "报告生成",
    "S04": "风控检查",
    "S05": "深度分析",
    "S06": "MCP盘面",
}
STAGE_ORDER = ["S01", "S02", "S03", "S04", "S05", "S06"]

def create_report() -> dict:
    return {"created_at": datetime.now().isoformat(), "stages": {}}

def save_report(report: dict, path: Path = None):
    import json
    path = path or Path(__file__).parent.parent / "_cache" / "pipeline_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)

def verify_gate(stage: str, report: dict) -> bool:
    return stage in report.get("stages", {})

def get_pipeline_summary(report: dict) -> str:
    stages = report.get("stages", {})
    passed = sum(1 for s in stages.values() if s.get("status") == "ok")
    return f"{passed}/{len(STAGE_ORDER)} stages passed"

def format_summary_text(summary: str) -> str:
    return f"[Pipeline] {summary}"
