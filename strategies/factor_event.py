"""
factor_event.py — 事件因子评分模块

基于 FactorHub 参考数据中表现最佳的事件因子类别，用现有数据源
实施分红除权、业绩预告、回购三类事件评分。

FactorHub 参考:
  EVT009 分红除权  Sharpe 1.18  ← 高分红跑赢市场
  EVT001 业绩预告  Sharpe 0.96  ← 业绩超预期驱动
  EVT004 回购      Sharpe 1.11  ← 回购公告后上涨

数据源优先级:
  分红:     akshare → baostock
  业绩预告: Tushare (pro.forecast) → 无降级
  回购:     预留 — 上层调用方通过沃道MCP覆盖
"""

import logging, json, time
from datetime import datetime, date, timedelta
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger("event_factor")

# ===== 数据源 =====
_USE_TUSHARE = False
try:
    import tushare as ts
    _pro = ts.pro_api()
    _test = _pro.forecast(ts_code="600519.SH", start_date="20240101", end_date="20240110")
    if not _test.empty:
        _USE_TUSHARE = True
except Exception:
    pass

logger.info(f"事件因子: Tushare业绩预告={'可用' if _USE_TUSHARE else '不可用'}")


def get_dividend_records(code: str, years: int = 2) -> list:
    """从 akshare 获取分红记录（主数据源）"""
    try:
        import akshare as ak
        df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df is not None and not df.empty:
            records = []
            cutoff = datetime.now() - timedelta(days=years * 365)
            for _, row in df.iterrows():
                ann_date = str(row.get("公告日期", ""))
                if ann_date and ann_date >= cutoff.strftime("%Y-%m-%d"):
                    cash_div = float(row.get("派息", 0) or 0)
                    progress = str(row.get("进度", ""))
                    if cash_div > 0 and ("实施" in progress or "预案" in progress):
                        records.append({
                            "date": str(row.get("除权除息日", "") or ""),
                            "ann_date": ann_date,
                            "cash_per_10": cash_div,
                            "stk_div": float(row.get("送股", 0) or 0) + float(row.get("转增", 0) or 0),
                            "progress": progress,
                        })
            return records
    except Exception as e:
        logger.debug(f"akshare 分红查询失败 {code}: {e}")
    
    # 降级: baostock
    try:
        import baostock as bs
        bs.login()
        try:
            bs_code = f"sh.{code}" if code.startswith(('6', '9')) else f"sz.{code}"
            rs = bs.query_dividend_data(bs_code, year=str(datetime.now().year - 1), yearType="report")
            records = []
            while rs.next():
                row = rs.get_row_data()
                if row and len(row) > 11:
                    cash_div = float(row[11] or 0)
                    if cash_div > 0:
                        records.append({
                            "date": row[2] or "",
                            "ann_date": row[1] or "",
                            "cash_per_10": cash_div,
                            "stk_div": float(row[10] or 0),
                        })
            return records
        finally:
            bs.logout()
    except Exception as e:
        logger.debug(f"baostock 分红查询失败 {code}: {e}")
    return []


# Tushare 限频保护
_last_tushare_call = 0.0

def _tushare_safe_call(func, *args, **kwargs):
    """带限频保护的 Tushare 调用（确保间隔 ≥61 秒）"""
    global _last_tushare_call, _USE_TUSHARE
    elapsed = time.time() - _last_tushare_call
    if elapsed < 61:
        logger.debug(f"Tushare 限频: 跳过({61-elapsed:.0f}s)")
        return None
    try:
        result = func(*args, **kwargs)
        _last_tushare_call = time.time()
        return result
    except Exception as e:
        if "频率超限" in str(e):
            logger.warning(f"Tushare 频率超限，后续请求跳过")
            _USE_TUSHARE = False
        return None


def get_forecast_data(code: str) -> Optional[dict]:
    """获取最新业绩预告（带限频保护）"""
    if not _USE_TUSHARE:
        return None
    
    try:
        start = f"{datetime.now().year - 1}0101"
        end = datetime.now().strftime("%Y%m%d")
        df = _tushare_safe_call(_pro.forecast, ts_code=code, start_date=start, end_date=end)
        if df is not None and not df.empty:
            latest = df.iloc[0]
            return {
                "type": str(latest.get("type", "")),
                "pct_change_min": float(latest.get("pct_change_min", 0) or 0),
                "pct_change_max": float(latest.get("pct_change_max", 0) or 0),
                "net_profit_min": float(latest.get("net_profit_min", 0) or 0),
                "ann_date": str(latest.get("ann_date", "")),
            }
    except Exception as e:
        logger.debug(f"业绩预告查询失败 {code}: {e}")
    return None


# ===== 评分函数 =====

def score_dividend(records: list, current_price: float = None) -> float:
    """
    分红评分 (0-100)
    
    基于近2年分红记录:
    - 股息率 > 5% → 90-100
    - 股息率 3-5% → 70-90
    - 股息率 1-3% → 40-70
    - 有分红但低 → 20-40
    - 无分红 → 0-20
    
    有 current_price 时做真实股息率计算，否则走绝对派息额保守估算。
    """
    if not records:
        return 10.0
    
    total_cash = sum(r["cash_per_10"] for r in records)
    avg_cash_per_10 = total_cash / len(records)
    
    # 有股价 → 真实股息率
    if current_price and current_price > 0:
        dividend_per_share = avg_cash_per_10 / 10
        yield_pct = dividend_per_share / current_price * 100
        if yield_pct > 5:
            return 95.0
        elif yield_pct > 3:
            return 80.0
        elif yield_pct > 1:
            return 55.0
        elif yield_pct > 0.5:
            return 30.0
        else:
            return 15.0
    
    # 无股价 → 绝对派息额保守估算
    if avg_cash_per_10 >= 30:
        return 90.0
    elif avg_cash_per_10 >= 15:
        return 75.0
    elif avg_cash_per_10 >= 8:
        return 60.0
    elif avg_cash_per_10 >= 3:
        return 40.0
    elif avg_cash_per_10 >= 1:
        return 20.0
    else:
        return 10.0


def score_forecast(forecast: Optional[dict]) -> float:
    """
    业绩预告评分 (0-100)
    
    基于最新业绩预告类型:
    - 预增/扭亏/大幅上升 → 70-100
    - 略增/续盈 → 50-70
    - 不确定 → 40-50
    - 略减/预减 → 20-40
    - 首亏/续亏 → 0-20
    """
    if not forecast:
        return 50.0
    
    ftype = forecast.get("type", "")
    
    # 正向
    if "扭亏" in ftype:
        return 95.0
    elif "预增" in ftype or "大幅上升" in ftype:
        pct = max(forecast.get("pct_change_max", 0) or 0, forecast.get("pct_change_min", 0) or 0)
        if pct > 100:
            return 90.0
        elif pct > 50:
            return 80.0
        else:
            return 70.0
    elif "略增" in ftype or "续盈" in ftype:
        return 60.0
    
    # 中性
    elif "不确定" in ftype:
        return 45.0
    
    # 负向
    elif "略减" in ftype:
        return 30.0
    elif "预减" in ftype or "预警" in ftype:
        return 20.0
    elif "首亏" in ftype or "续亏" in ftype or "亏损" in ftype:
        return 5.0
    
    return 45.0


def score_buyback_announcements(code: str) -> float:
    """
    回购评分 (0-100)
    
    通过沃道MCP搜索回购公告。有则加分。
    此函数由上层调用方结合MCP结果调用。
    """
    return 0.0


def total_event_score(code: str, 
                      dividend_override: float = None,
                      forecast_override: float = None,
                      buyback_bonus: float = 0.0) -> float:
    """
    综合事件评分
    
    权重: 分红30% + 业绩预告50% + 回购20%
    """
    if dividend_override is not None:
        ds = dividend_override
    else:
        records = get_dividend_records(code)
        ds = score_dividend(records)
    
    if forecast_override is not None:
        fs = forecast_override
    else:
        fc = get_forecast_data(code)
        fs = score_forecast(fc)
    
    bs_val = min(buyback_bonus, 100.0)
    total = ds * 0.30 + fs * 0.50 + bs_val * 0.20
    return round(total, 1)


def batch_event_score(codes: list) -> Dict[str, float]:
    """批量计算事件因子评分"""
    scores = {}
    for code in codes:
        try:
            scores[code] = total_event_score(code)
        except Exception as e:
            logger.debug(f"事件评分失败 {code}: {e}")
            scores[code] = 50.0
    return scores


# ===== 自测 =====
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_codes = ["600519", "000858", "002371"]
    for code in test_codes:
        s = total_event_score(code)
        records = get_dividend_records(code)
        fc = get_forecast_data(code)
        print(f"{code}: 总分={s}")
        print(f"  分红: {len(records)}笔 = {score_dividend(records):.0f}分")
        print(f"  业绩预告: {fc['type'] if fc else '无'} = {score_forecast(fc):.0f}分")
