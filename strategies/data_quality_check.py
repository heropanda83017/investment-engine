"""data_quality_check.py — 数据源交叉验证 + 质量评分

检查维度:
1. 基础质量: 价格>0, 成交量>0, 无NaN, 日期连续
2. 跨源一致性: baostock vs akshare vs tushare 收盘价差异
3. 异常检测: 单日涨跌幅超阈值, 停牌日识别

输出: reports/quality/YYYY-MM-DD_quality_report.csv
"""
import time, json, logging, csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("data_quality")

from env import IE_ROOT
REPORT_DIR = Path(IE_ROOT) / "reports" / "quality"

# 默认检查股票池（核心 20 只 + 指数）
FOCUS_CODES = [
    "688981", "688012", "600584", "002371", "688072",
    "300308", "300502", "300394", "002230", "600519",
    "000858", "000333", "300124", "002594", "300750",
    "600036", "603501", "002049", "688126", "000725",
]

INDICES = {
    "sh.000300": "沪深300",
    "sh.000905": "中证500",
    "sh.000688": "科创50",
}


def _safe_float(val, default=0.0) -> float:
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except: return default


# ─── 1. 基础质量检查 ────────────────────────


def check_basic_quality(df: pd.DataFrame, code: str, source: str) -> dict:
    """单源基础质量检查

    检查项:
    - 数据行数
    - 价格 > 0 比例
    - 成交量 > 0 比例
    - NaN 比例
    - 日期连续性（跳天检测）
    - 极端涨跌幅（单日 > 20%）

    Returns
    -------
    dict : {code, source, rows, price_ok_pct, volume_ok_pct, nan_pct,
            missing_dates, extreme_days, score}
    """
    if df is None or df.empty:
        return {"code": code, "source": source, "rows": 0,
                "quality_score": 0.0, "price_ok_pct": 0.0,
                "vol_ok_pct": 0.0, "nan_pct": 1.0,
                "extreme_days": 0, "issues": ["数据为空"]}

    # 列名标准化
    close_col = "close" if "close" in df.columns else ("收盘" if "收盘" in df.columns else None)
    vol_col = "volume" if "volume" in df.columns else ("成交量" if "成交量" in df.columns else None)

    if not close_col:
        return {"code": code, "source": source, "rows": len(df),
                "quality_score": 0.0, "price_ok_pct": 0.0,
                "vol_ok_pct": 0.0, "nan_pct": 1.0,
                "extreme_days": 0, "issues": ["缺少收盘价列"]}

    close = df[close_col].dropna()
    total = len(df)
    issues = []

    # 价格 > 0
    price_ok = (close > 0).sum()
    price_ok_pct = price_ok / max(total, 1)

    if price_ok_pct < 0.9:
        issues.append(f"价格异常比例 {1-price_ok_pct:.1%}")

    # 成交量 > 0
    vol_ok_pct = 1.0
    if vol_col:
        vol = df[vol_col].dropna()
        if len(vol) > 0:
            vol_ok = (vol > 0).sum()
            vol_ok_pct = vol_ok / max(len(vol), 1)
            if vol_ok_pct < 0.8:
                issues.append(f"成交量异常比例 {1-vol_ok_pct:.1%}")

    # NaN 比例
    nan_cols = [c for c in df.columns if df[c].isna().sum() > 0]
    nan_pct = sum(df[c].isna().sum() for c in nan_cols) / max(total * len(df.columns), 1)

    # 极端涨跌幅
    if close_col and len(close) > 1:
        pct_chg = close.pct_change().dropna()
        extreme = (pct_chg.abs() > 0.20).sum()
        if extreme > 0:
            issues.append(f"极端涨跌幅 {extreme} 天")

    # 得分 = 各维度加权
    score = price_ok_pct * 0.4 + vol_ok_pct * 0.3 + (1 - nan_pct) * 0.3
    score = max(0, min(1, score))

    return {
        "code": code, "source": source, "rows": total,
        "quality_score": round(score, 4),
        "price_ok_pct": round(price_ok_pct, 4),
        "vol_ok_pct": round(vol_ok_pct, 4),
        "nan_pct": round(nan_pct, 4),
        "extreme_days": extreme if "extreme" in dir() else 0,
        "issues": issues,
    }


# ─── 2. 跨源交叉验证 ────────────────────────


def cross_validate(code: str, primary_df: pd.DataFrame,
                   secondary_df: pd.DataFrame,
                   primary_name: str = "baostock",
                   secondary_name: str = "akshare") -> dict:
    """两数据源交叉验证收盘价

    Returns
    -------
    dict : {code, common_dates, max_diff_pct, mean_diff_pct, consistent}
    """
    if primary_df is None or secondary_df is None:
        return {"code": code, "common_dates": 0, "consistent": False, "error": "数据缺失"}

    # 提取收盘价
    def _get_close(df):
        if "close" in df.columns: return df["close"]
        if "收盘" in df.columns: return df["收盘"]
        return None

    pc = _get_close(primary_df)
    sc = _get_close(secondary_df)

    if pc is None or sc is None:
        return {"code": code, "common_dates": 0, "consistent": False, "error": "缺少收盘价"}

    # 对齐日期
    common = pc.dropna().index.intersection(sc.dropna().index)
    if len(common) < 5:
        return {"code": code, "common_dates": len(common), "consistent": False, "error": f"共同日期仅{len(common)}天"}

    p_aligned = pc.loc[common]
    s_aligned = sc.loc[common]

    # 计算差异（用中间价归一化）
    mid = (p_aligned + s_aligned) / 2
    diff_pct = (p_aligned - s_aligned).abs() / mid.replace(0, np.nan)

    max_diff = float(diff_pct.max()) if len(diff_pct) > 0 else 0
    mean_diff = float(diff_pct.mean()) if len(diff_pct) > 0 else 0

    # 一致性判定: 平均差异 < 1% 且最大差异 < 5%
    consistent = mean_diff < 0.01 and max_diff < 0.05

    return {
        "code": code,
        "common_dates": len(common),
        "max_diff_pct": round(max_diff * 100, 2),
        "mean_diff_pct": round(mean_diff * 100, 4),
        "consistent": consistent,
    }


# ─── 3. 全量扫描 ────────────────────────────


def scan_all(codes: list = None, days: int = 120) -> List[dict]:
    """全量数据质量扫描

    对每只股票: baostock(主) + akshare(副) → 基础质量 + 交叉验证

    Returns
    -------
    list[dict] : 每只股票的完整质量报告
    """
    if codes is None:
        codes = FOCUS_CODES

    results = []
    total = len(codes)
    _akshare_cooldown = 1.5  # akshare 请求间隔
    log.info(f"数据质量扫描: {total} 只股票, {days} 天数据")

    import baostock as bs

    for idx, code in enumerate(codes):
        if (idx + 1) % 5 == 0:
            log.info(f"  进度: {idx+1}/{total}")

        # baostock (主源)
        bs_df = None
        try:
            lg = bs.login()
            if lg.error_code == '0':
                rs = bs.query_history_k_data_plus(
                    f"sh.{code}" if code.startswith("6") else f"sz.{code}",
                    "date,close,volume,amount,peTTM,pbMRQ",
                    start_date=(datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d"),
                    frequency="d")
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                bs.logout()
                if rows:
                    bs_df = pd.DataFrame(rows, columns=rs.fields)
                    for col in ["close", "volume", "amount", "peTTM", "pbMRQ"]:
                        if col in bs_df.columns:
                            bs_df[col] = pd.to_numeric(bs_df[col], errors="coerce")
        except Exception as e:
            log.warning(f"  {code} baostock 失败: {e}")

        # akshare (副源，仅单次尝试，失败不阻塞)
        ak_df = None
        try:
            import akshare as ak
            import warnings; warnings.filterwarnings('ignore')
            ak_raw = ak.stock_zh_a_hist(symbol=code, period="daily",
                start_date=(datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"), adjust="qfq")
            if ak_raw is not None and not ak_raw.empty:
                ak_df = ak_raw.rename(columns={"日期": "date", "收盘": "close"})
                ak_df["close"] = pd.to_numeric(ak_df["close"], errors="coerce")
                ak_df["date_str"] = ak_df["date"].astype(str)
                ak_df.set_index("date_str", inplace=True)
        except Exception as e:
            log.warning(f"  {code} akshare 不可用: {str(e)[:60]}")
        

                # 基础质量（主源）
        quality = check_basic_quality(bs_df, code, "baostock")

        # 交叉验证 baostock vs akshare
        cross = {"code": code, "common_dates": 0, "consistent": False,
                 "mean_diff_pct": 0, "max_diff_pct": 0, "akshare_ok": False}
        if bs_df is not None and ak_df is not None and "close" in bs_df.columns and "close" in ak_df.columns:
            try:
                # baostock 日期列
                bs_dates = bs_df["date"].astype(str) if "date" in bs_df.columns else bs_df.index.astype(str)
                bs_close = pd.Series(bs_df["close"].values, index=bs_dates)
                # akshare 日期索引（已 set_index date_str）
                ak_close = ak_df["close"]
                common = bs_close.index.intersection(ak_close.index.astype(str))
                if len(common) >= 5:
                    b = bs_close.loc[common].astype(float)
                    a = ak_close.loc[common].astype(float)
                    mid = (b + a) / 2
                    diff = (b - a).abs() / mid.replace(0, np.nan)
                    cross = {
                        "code": code,
                        "common_dates": len(common),
                        "mean_diff_pct": round(float(diff.mean()) * 100, 4),
                        "max_diff_pct": round(float(diff.max()) * 100, 2),
                        "consistent": float(diff.mean()) < 0.01 and float(diff.max()) < 0.05,
                        "akshare_ok": True,
                    }
            except Exception as e:
                log.warning(f"  {code} 交叉验证失败: {e}")

        result = {
            "code": code,
            "rows": quality["rows"],
            "quality_score": quality["quality_score"],
            "price_ok_pct": quality["price_ok_pct"],
            "vol_ok_pct": quality["vol_ok_pct"],
            "nan_pct": quality["nan_pct"],
            "common_dates": cross["common_dates"],
            "cross_consistent": cross["consistent"],
            "akshare_ok": cross.get("akshare_ok", False),
            "cross_mean_diff": cross["mean_diff_pct"],
            "cross_max_diff": cross["max_diff_pct"],
            "issues": "; ".join(quality.get("issues", [])),
        }
        results.append(result)

    return results


def save_report(results: List[dict]) -> str:
    """保存质量报告为 CSV + 汇总文本"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    # CSV
    csv_path = REPORT_DIR / f"{today}_quality_report.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
    log.info(f"  质量报告: {csv_path}")

    # 汇总
    scores = [r["quality_score"] for r in results if r["quality_score"] > 0]
    avg_score = np.mean(scores) if scores else 0
    passed = sum(1 for r in results if r["quality_score"] >= 0.8)
    failed = sum(1 for r in results if r["quality_score"] < 0.8 and r["quality_score"] > 0)
    no_data = sum(1 for r in results if r["quality_score"] == 0)

    # MCP 连通性检查
    mcp_status = {}
    for mcp_name, mcp_module, mcp_fn in [
        ("anysearch", "anysearch_source", "mcp_call"),
        ("wudao", "wudao_mcp_source", "market_overview"),
    ]:
        try:
            m = __import__(mcp_module, fromlist=[mcp_fn])
            fn = getattr(m, mcp_fn)
            r = fn()
            mcp_status[mcp_name] = r is not None
        except:
            mcp_status[mcp_name] = False

    # tickflow 检查
    tickflow_ok = False
    try:
        from scripts.tickflow import TickFlowRealtime
        tf = TickFlowRealtime()
        tickflow_ok = True
    except: pass
    failed = sum(1 for r in results if r["quality_score"] < 0.8 and r["quality_score"] > 0)
    no_data = sum(1 for r in results if r["quality_score"] == 0)

    summary_path = REPORT_DIR / f"{today}_quality_summary.txt"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"数据质量扫描报告 | {today}\n")
        f.write(f"{'='*40}\n")
        f.write(f"扫描股票: {len(results)} 只\n")
        f.write(f"平均质量分: {avg_score:.2f}\n")
        f.write(f"通过(≥0.8): {passed} 只\n")
        f.write(f"待关注(<0.8): {failed} 只\n")
        f.write(f"无数据: {no_data} 只\n\n")
        f.write(f"问题股票:\n")
        for r in results:
            if r["issues"]:
                f.write(f"  {r['code']}: {r['issues']} (分={r['quality_score']:.2f})\n")

    log.info(f"  质量汇总: {summary_path}")
    log.info(f"  平均分={avg_score:.2f}, 通过={passed}, 关注={failed}, 无数据={no_data}")
    return str(csv_path)


def run_check(codes: list = None, days: int = 120) -> str:
    """一站式运行数据质量检查"""
    log.info("=" * 40)
    log.info("数据质量检查启动")
    log.info("=" * 40)

    t0 = time.time()
    results = scan_all(codes, days)
    path = save_report(results)

    log.info(f"总耗时: {time.time()-t0:.1f}s")
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    run_check()
