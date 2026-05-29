"""factor_lab.py — 因子实验室

持续实现→测试→优化闭环。

子命令:
  python -m factor_lab recommend    # 推荐下一批待实现因子
  python -m factor_lab report       # 因子IC健康报告 + 淘汰建议
  python -m factor_lab status       # 因子池状态一览
"""
import sys, os, json, logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("factor_lab")

IE_ROOT = r"E:\AIGC-KB\output\investment-engine"
STRATEGIES = os.path.join(IE_ROOT, "strategies")
CONFIG_PATH = os.path.join(IE_ROOT, "config", "config.json")
FACTOR_REGISTRY = os.path.join(IE_ROOT, "config", "factor_registry.json")


# ─── 因子注册表管理 ─────────────────────────


def _load_registry() -> dict:
    """加载因子注册表（记录每个alpha的状态/IC/权重）"""
    if os.path.exists(FACTOR_REGISTRY):
        with open(FACTOR_REGISTRY) as f:
            return json.load(f)
    return {"factors": {}, "last_updated": "", "version": 1}


def _save_registry(registry: dict):
    Path(FACTOR_REGISTRY).parent.mkdir(parents=True, exist_ok=True)
    with open(FACTOR_REGISTRY, 'w') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def _get_implemented_alphas() -> set:
    """从 alpha191_factors.py 解析已实现的 alpha 函数名"""
    ap = os.path.join(STRATEGIES, "alpha191_factors.py")
    if not os.path.exists(ap):
        return set()
    implemented = set()
    with open(ap) as f:
        for line in f:
            s = line.strip()
            if s.startswith('def alpha_'):
                name = s.split('(')[0].replace('def ', '')
                implemented.add(name)
    return implemented


# ─── recommend — 推荐待实现因子 ──────────────


def recommend(top_n: int = 15) -> List[dict]:
    """基于 FactorHub 208 因子参考数据，推荐待实现的 alpha 因子

    Returns
    -------
    list[dict] : [{code, name, category, sharpe, priority}, ...]
    """
    sys.path.insert(0, STRATEGIES)
    from factorhub_source import FactorHubClient

    client = FactorHubClient()
    ref = client.fetch_factor_values()
    if not ref or "data" not in ref:
        log.warning("FactorHub 参考数据不可用，使用本地缓存")
        return _fallback_recommend()

    all_factors = ref["data"]
    implemented = _get_implemented_alphas()

    # 按 Sharpe 排序
    scored = []
    for f in all_factors:
        code = f.get("code", "")
        sharpe = f.get("sharpe_ratio", 0)
        try:
            sharpe = float(sharpe) if sharpe else 0
        except: sharpe = 0

        # 检查是否已在 alpha191 中实现
        alpha_name = f"alpha_{code.lower()}" if code else ""
        already_implemented = alpha_name in implemented or any(code in n for n in implemented)

        scored.append({
            "code": code,
            "name": f.get("name", ""),
            "category": f.get("category", ""),
            "sharpe": round(sharpe, 4),
            "description": f.get("description", "")[:100],
            "implemented": already_implemented,
        })

    scored.sort(key=lambda x: x["sharpe"], reverse=True)

    # 排除已实现，取 top_n
    not_implemented = [s for s in scored if not s["implemented"]][:top_n]

    log.info(f"FactorHub: {len(all_factors)} 因子, {len(implemented)} 已实现, 推荐 {len(not_implemented)}")
    for i, f in enumerate(not_implemented):
        log.info(f"  #{i+1} [{f['category']}] {f['code']} {f['name']} Sharpe={f['sharpe']}")

    return not_implemented


def _fallback_recommend() -> list:
    """FactorHub 不可用时的静态推荐列表"""
    return [
        {"code": "MOM001", "name": "动量因子", "category": "动量因子", "sharpe": 0.0, "description": "基于过去6个月股价涨跌幅排序"},
        {"code": "VAL001", "name": "价值因子", "category": "价值因子", "sharpe": 0.0, "description": "基于PE/PB/PS综合估值"},
    ]


# ─── report — 因子表现报告 ──────────────────


def report(days: list = None) -> dict:
    """生成因子 IC 健康报告 + 淘汰建议

    Parameters
    ----------
    days : list
        统计窗口，默认 [20, 60, 120]

    Returns
    -------
    dict : {healthy, warning, danger, pruning_suggestions}
    """
    if days is None:
        days = [20, 60, 120]

    registry = _load_registry()
    factors = registry.get("factors", {})
    implemented = _get_implemented_alphas()

    if not implemented:
        log.warning("alpha191_factors.py 中未找到已实现的因子")
        return {"healthy": 0, "warning": 0, "danger": 0, "pruning": []}

    # 尽量从 factor_tracker 读取真实 IC
    try:
        sys.path.insert(0, STRATEGIES)
        from factor_tracker import FactorTracker
        tracker = FactorTracker()
    except Exception:
        tracker = None

    report_data = {"generated": datetime.now().isoformat(), "total": len(implemented)}
    healthy, warning, danger = 0, 0, 0
    pruning = []

    for alpha_name in sorted(implemented):
        ic_data = {}
        if tracker:
            for d in days:
                ic_list = tracker.get_recent_ic(alpha_name, window=d)
                if ic_list:
                    ic_data[f"{d}d_ic"] = round(sum(ic_list) / len(ic_list), 4)
                else:
                    ic_data[f"{d}d_ic"] = None

        # 判定
        ic_120d = ic_data.get("120d_ic")
        ic_60d = ic_data.get("60d_ic")
        ic_20d = ic_data.get("20d_ic")

        if ic_120d is None:
            status = "insufficient_data"
        elif ic_120d < 0 and (ic_60d is not None and ic_60d < 0):
            status = "danger"
            danger += 1
            pruning.append({"alpha": alpha_name, "reason": f"120d_IC={ic_120d}, 60d_IC={ic_60d}"})
        elif ic_120d < 0 or (ic_60d is not None and ic_60d < 0):
            status = "warning"
            warning += 1
        else:
            status = "healthy"
            healthy += 1

        report_data[alpha_name] = {"status": status, **ic_data}

    report_data["healthy"] = healthy
    report_data["warning"] = warning
    report_data["danger"] = danger
    report_data["pruning_suggestions"] = pruning

    # 输出摘要
    log.info(f"因子健康报告: {healthy}健康 / {warning}关注 / {danger}建议淘汰")
    if pruning:
        log.warning(f"  建议淘汰 ({len(pruning)}):")
        for p in pruning:
            log.warning(f"    {p['alpha']}: {p['reason']}")

    return report_data


# ─── status — 因子池一览 ────────────────────


def status():
    """显示所有因子状态"""
    implemented = _get_implemented_alphas()
    log.info(f"已实现 alpha 因子: {len(implemented)} 个")
    for a in sorted(implemented):
        log.info(f"  ✅ {a}")

    # FactorHub 参考数据
    try:
        sys.path.insert(0, STRATEGIES)
        from factorhub_source import FactorHubClient
        client = FactorHubClient()
        ref = client.fetch_factor_values()
        if ref and "data" in ref:
            categories = set(f.get("category", "") for f in ref["data"])
            log.info(f"FactorHub 参考: {len(ref['data'])} 因子, {len(categories)} 个类别")
    except Exception:
        log.info("FactorHub: 不可用")

    available = 191 - len(implemented)
    log.info(f"待实现: ~{available} 个alpha因子可用于扩展")


# ─── CLI 入口 ────────────────────────────────


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "recommend":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        recommend(n)
    elif cmd == "report":
        report()
    elif cmd == "status":
        status()
    else:
        print(f"用法: python -m factor_lab [recommend [N] | report | status]")


if __name__ == "__main__":
    main()
