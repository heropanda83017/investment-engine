#!/usr/bin/env python3
"""ai_intel.py — AI 产业情报分析

从 news_db 读取最新 AI 新闻，按赛道聚类，输出结构化 JSON。
可被 framework_score_cli.py 调用，反馈到 signal_generator。

使用方式:
    python system/ai_intel.py                          # 分析最近一期新闻
    python system/ai_intel.py --days 3                  # 分析最近3天
    python system/ai_intel.py --output json             # JSON 输出 (默认)
    python system/ai_intel.py --output text             # 文本简报
"""

import sys, os, json, logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

try:
    from env import IE_ROOT
except ImportError:
    IE_ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("ai_intel")

# ── 赛道定义: tag → 赛道名 → A 股受益标的 ──
SECTOR_MAP = {
    "chip": {
        "name": "算力/芯片",
        "stocks": ["688981", "002371", "688012", "688126", "600584", "688072", "300308", "300433"],
        "signal_weight": 0.08,
    },
    "model": {
        "name": "大模型/技术",
        "stocks": ["688981", "002371", "000725"],
        "signal_weight": 0.05,
    },
    "agent": {
        "name": "智能体/Agent",
        "stocks": ["002371", "688012", "300308"],
        "signal_weight": 0.06,
    },
    "AI": {
        "name": "AI 综合",
        "stocks": ["000725", "688981", "002371", "300308"],
        "signal_weight": 0.04,
    },
    "prod": {
        "name": "AI 产品/应用",
        "stocks": ["300308", "300433", "000725"],
        "signal_weight": 0.03,
    },
}

# ── A 股标的映射（美股/港股 → A 股关联）──
FOREIGN_MAP = {
    "NVIDIA": {"name": "英伟达链", "stocks": ["300308", "688012", "002371"], "signal_weight": 0.06},
    "Anthropic": {"name": "Anthropic链", "stocks": ["300308", "002371"], "signal_weight": 0.04},
    "OpenAI": {"name": "OpenAI链", "stocks": ["300308", "002371"], "signal_weight": 0.04},
    "Alibaba": {"name": "阿里云/AI", "stocks": ["688981", "002371"], "signal_weight": 0.03},
    "华为": {"name": "华为链", "stocks": ["688981", "600584", "002371", "000725"], "signal_weight": 0.07},
}


def load_news(days: int = 1) -> list:
    """从 news_db 加载最近 N 天的新闻"""
    db_dir = IE_ROOT / "system" / "news_db"
    if not db_dir.exists():
        log.warning(f"news_db 不存在: {db_dir}")
        return []
    
    all_items = []
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_ts = cutoff.strftime("%Y-%m-%d")
    
    for y in range(cutoff.year, datetime.now().year + 1):
        for m in range(1, 13):
            month_dir = db_dir / str(y) / f"{m:02d}"
            if not month_dir.exists():
                continue
            for f in sorted(month_dir.glob("*.json")):
                if f.name == "health.json":
                    continue
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, dict):
                        items = data.get("items", [])
                    else:
                        items = data
                    all_items.extend(items)
                except Exception as e:
                    log.debug(f"跳过 {f.name}: {e}")
    
    # Filter by date + dedup
    seen = set()
    unique = []
    for item in all_items:
        # Date filter: check pub field or fallback to file date
        pub = item.get("pub", "") or item.get("date", "") or item.get("publishedAt", "")
        if pub and pub[:10] < cutoff_ts:
            continue
        # Dedup by title (keep empty-title items, don't silently drop)
        t = (item.get("title") or "").strip() or "(untitled)"
        if t not in seen:
            seen.add(t)
            unique.append(item)
    
    log.info(f"加载 {len(unique)} 条新闻 (去重后)")
    return unique


def analyze_sectors(items: list) -> dict:
    """按赛道聚类分析"""
    if not items:
        return {"sectors": [], "summary": {"total": 0, "positive": 0, "negative": 0, "neutral": 0}}
    
    # Count by tag
    tag_counts = defaultdict(lambda: {"count": 0, "positive": 0, "negative": 0, "items": []})
    for item in items:
        tags = item.get("tags", []) or []
        if isinstance(tags, str):
            tags = [tags]
        if not tags:
            tags = ["AI"]  # default
        direction = item.get("dir", "中性")
        for tag in tags:
            tag_counts[tag]["count"] += 1
            if direction == "利好":
                tag_counts[tag]["positive"] += 1
            elif direction == "利空":
                tag_counts[tag]["negative"] += 1
            tag_counts[tag]["items"].append((item.get("title") or "")[:60])
    
    # Build sector output
    sectors = []
    for tag, info in sorted(tag_counts.items()):
        sector_def = SECTOR_MAP.get(tag, {"name": tag, "stocks": [], "signal_weight": 0.02})
        total = info["count"]
        pos_ratio = info["positive"] / total if total > 0 else 0
        
        # Signal impact: positive ratio drives signal weight (range -0.5x~+1.5x weight)
        signal_impact = sector_def["signal_weight"] * (pos_ratio * 2 - 0.5)
        
        sectors.append({
            "tag": tag,
            "name": sector_def["name"],
            "count": total,
            "positive": info["positive"],
            "negative": info["negative"],
            "positive_ratio": round(pos_ratio, 2),
            "signal_weight": sector_def["signal_weight"],
            "signal_impact": round(signal_impact, 3),
            "beneficiary_stocks": sector_def["stocks"],
            "top_items": info["items"][:3],
        })
    
    # Company heat
    cos_count = defaultdict(int)
    cos_positive = defaultdict(int)
    for item in items:
        cos_list = item.get("cos", []) or []
        if isinstance(cos_list, str):
            cos_list = [cos_list]
        for co in cos_list:
            cos_count[co] += 1
            if item.get("dir", "") == "利好":
                cos_positive[co] += 1
    
    companies = []
    for co, cnt in sorted(cos_count.items(), key=lambda x: x[1], reverse=True):
        foreign = FOREIGN_MAP.get(co)
        companies.append({
            "name": co,
            "mention_count": cnt,
            "positive_ratio": round(cos_positive[co] / cnt, 2) if cnt > 0 else 0,
            "a_share_link": foreign["name"] if foreign else "",
            "beneficiary_stocks": foreign["stocks"] if foreign else [],
        })
    
    total = len(items)
    pos = sum(1 for i in items if i.get("dir") == "利好")
    neg = sum(1 for i in items if i.get("dir") == "利空")
    
    return {
        "sectors": sectors,
        "companies": companies,
        "summary": {
            "total": total,
            "positive": pos,
            "negative": neg,
            "neutral": total - pos - neg,
            "positive_ratio": round(pos / total, 2) if total > 0 else 0,
            "hot_tags": [s["tag"] for s in sorted(sectors, key=lambda x: x["count"], reverse=True)[:3]],
        }
    }


def generate_text_report(analysis: dict) -> str:
    """生成可读文本简报"""
    lines = []
    lines.append(f"# AI 产业情报 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    
    s = analysis["summary"]
    lines.append(f"新闻: {s['total']} 条 | 利好 {s['positive']}/{s['negative']}利空 | 积极率 {s['positive_ratio']:.0%}")
    lines.append("")
    
    for sec in analysis["sectors"]:
        emoji = "🟢" if sec["positive_ratio"] > 0.5 else ("🔴" if sec["positive_ratio"] < 0.2 else "⚪")
        sig = "+" if sec["signal_impact"] > 0 else ""
        lines.append(f"### {emoji} {sec['name']} ({sec['count']}条)")
        lines.append(f"积极率: {sec['positive_ratio']:.0%} | 信号影响: {sig}{sec['signal_impact']}")
        stocks = sec["beneficiary_stocks"]
        if stocks:
            lines.append(f"A股映射: {', '.join(stocks[:5])}")
        lines.append("")
    
    if analysis["companies"]:
        lines.append("### 公司热度")
        for co in analysis["companies"][:5]:
            emoji = "🔥" if co["mention_count"] > 5 else "⭐"
            link = f" → {co['a_share_link']}" if co["a_share_link"] else ""
            lines.append(f"{emoji} {co['name']}: {co['mention_count']}次提及{link}")
    
    return "\n".join(lines)


def run(output: str = "json", days: int = 1) -> dict:
    """主入口"""
    items = load_news(days=days)
    analysis = analyze_sectors(items)
    
    if output == "text":
        print(generate_text_report(analysis))
    else:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
    
    return analysis


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI 产业情报分析")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    parser.add_argument("--days", type=int, default=1, help="回看天数")
    args = parser.parse_args()
    run(output=args.output, days=args.days)
