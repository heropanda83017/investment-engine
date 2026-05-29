#!/usr/bin/env python3
"""
Layer 1 — 数据层
================
全市场A股数据获取、清洗、缓存 — 并发筛选版
"""

import sys, os, json, time, logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

# ---- 数据源降级 ---- 
_SOURCE_PRIORITY = ["akshare", "baostock"]  # akshare优先(baostock不稳定时)

def _get_kline_degrade(code: str, days: int = 120):
    """通过 data_optimizer 降级链获取K线 (Phase 3: 替代自建降级链)"""
    try:
        from data_optimizer import OptimizedDataLayer
        _odl = getattr(_get_kline_degrade, '_odl', None)
        if _odl is None:
            _odl = OptimizedDataLayer()
            _get_kline_degrade._odl = _odl
        df = _odl.get_kline(code, days=days)
        if df is not None and not df.empty:
            # data_optimizer 与 fetch_data 列名基本一致
            # 仅需适配: 换手率 data_optimizer用%(0.38), fetch_data用ratio(0.0038)
            if '换手率' in df.columns:
                df['换手率'] = df['换手率'] / 100.0
            return df
        log.warning(f"data_optimizer K线空: {code}")
    except Exception as e:
        log.warning(f"data_optimizer K线失败 {code}: {e}")
    
    # 备用: 直接 baostock
    try:
        import baostock as _bs
        pref = f"sh.{code}" if code.startswith(('6','9')) else f"sz.{code}"
        _bs.login()
        rs = _bs.query_history_k_data_plus(pref,
            "date,open,high,low,close,volume,amount,pctChg,turn,peTTM,pbMRQ",
            start_date=(datetime.now()-timedelta(days=int(days*1.5))).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d"),
            frequency="d", adjustflag="2")
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        _bs.logout()
        if rows:
            fields = ["date","open","high","low","close","volume","amount","pctChg","turn","peTTM","pbMRQ"]
            df = pd.DataFrame(rows, columns=fields)
            rename = {"date":"日期","open":"开盘","high":"最高","low":"最低",
                     "close":"收盘","volume":"成交量","amount":"成交额",
                     "pctChg":"涨跌幅","turn":"换手率","peTTM":"市盈率","pbMRQ":"市净率"}
            df.rename(columns={k:v for k,v in rename.items() if k in df.columns}, inplace=True)
            for col in ['开盘','收盘','最高','最低','成交量','成交额','涨跌幅','换手率']:
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            if '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'])
                df.sort_values('日期', inplace=True)
            return df.tail(days)
    except Exception as e2:
        log.warning(f"备用K线也失败 {code}: {e2}")
    return pd.DataFrame()
from config_loader import IE_SCRIPTS, CFG as CONFIG, cache_path, data_dir, CACHE_TTL_HOURS

log = logging.getLogger("data_layer")

# ---- 常量 ----
CACHE_DIR = data_dir("cache")

# ---- 辅助函数 ----
def _prefix(code: str) -> str:
    """6位代码转baostock前缀格式"""
    return f"sh.{code}" if code.startswith(('6','9')) else f"sz.{code}"

def _check_stock(code: str, cfg: dict) -> Optional[dict]:
    """单只股票筛选（降级链: baostock → akshare）"""
    import baostock as _bs
    try:
        _bs.login()
    except Exception:
        pass
    try:
        df = _get_kline_degrade(code, days=120)  # 120天足够筛选判断
        if df.empty:
            return None
        rows = []
        for _, row in df.iterrows():
            rows.append([row.get("日期",""), row.get("收盘",0), row.get("成交额",0)])

        if len(rows) < cfg["min_listing_days"]:
            return None

        closes = [float(r[1]) for r in rows if r[1] and r[1] != ""]
        amounts = [float(r[2]) for r in rows if r[2] and r[2] != ""]

        if not closes:
            return None

        latest = closes[-1]
        if latest < cfg["min_price"] or latest > cfg["max_price"]:
            return None

        avg_amount = np.mean(amounts[-20:]) if len(amounts) >= 20 else (np.mean(amounts) if amounts else 0)
        if avg_amount < cfg["min_volume_20d"]:
            return None

        if len(closes) >= 20:
            gain = (closes[-1] / closes[-20] - 1) * 100
            if gain > cfg["max_gain_20d"]:
                return None

        return {"code": code, "close": round(latest, 2), "amount_20d_avg": round(avg_amount, 0)}
    except Exception as e:
        log.debug(f"筛选跳过 {code}: {e}")
        return None
    finally:
        try:
            _bs.logout()
        except Exception as e:
            log.warning(f"baostock get_all_stocks失败: {e}, 降级到akshare")


class DataEngine:
    """数据引擎：获取 → 并发筛选 → 存储 → 缓存"""

    def __init__(self):
        from data_provider import get_provider
        self.provider = get_provider()
        self._stock_list = None
        self._name_map: Dict[str, str] = {}  # code -> name
        self._daily_prices = {}

    # ---------- 1. 全量股票列表 ----------

    def get_all_stocks(self, refresh=False) -> pd.DataFrame:
        """获取全A股列表（降级链: baostock → akshare→ 缓存）"""
        if self._stock_list is not None and not refresh:
            return self._stock_list

        rows = []
        # 尝试 baostock
        try:
            import baostock as _bs
            _bs.login()
            rs = _bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
            while rs.next():
                row = rs.get_row_data()
                if str(row[1]) == "1" and not row[0].startswith(('sh.000','sh.880','sh.950','sz.399')):
                    parts = row[0].split('.')
                    code = parts[1] if len(parts) > 1 else row[0]
                    rows.append({"code": code, "name": row[2], "status": row[1]})
                    self._name_map[code] = row[2]
            _bs.logout()
        except Exception as e:
            log.warning(f"baostock get_all_stocks失败: {e}, 降级到akshare")

        # baostock 失败时用 akshare
        if not rows:
            try:
                import akshare as ak
                df = ak.stock_info_a_code_name()
                if df is not None and not df.empty:
                    for _, r in df.iterrows():
                        code = str(r.get("code",""))
                        name = str(r.get("name",""))
                        rows.append({"code": code, "name": name, "status": "1"})
                        self._name_map[code] = name
                log.info(f"akshare: 获取 {len(rows)} 只股票")
            except Exception as e:
                log.warning(f"全量获取失败: {e}")

        # 最后 fallback: 核心股票
        if not rows:
            fallback = ["600519","000858","002371","300308","600036","000333",
                       "688041","002230","300124","002594","603501","688981",
                       "688256","300474","688012","688072","688120","688037",
                       "300604","601138","002916","300502","688498","688111",
                       "688200","300624","603160"]
            for code in fallback:
                rows.append({"code": code, "name": "", "status": "1"})
            log.info(f"使用核心fallback: {len(fallback)} 只")

        self._stock_list = pd.DataFrame(rows)
        return self._stock_list

    def get_stock_name(self, code: str) -> str:
        """按代码获取股票名称"""
        if not self._name_map:
            self.get_all_stocks()
        return self._name_map.get(code, "")

    # ---------- 2. 并发强制剔除规则 ----------

    def screen_stocks(self, df: pd.DataFrame = None, max_workers: int = 4) -> pd.DataFrame:
        """筛选: 使用已有缓存或基础灰度, 不逐股调baostock（防连接池崩溃）"""
        stocks = df if df is not None else self.get_all_stocks()
        if stocks.empty:
            last_cache = self.load_cache("screened_full_last")
            if last_cache is not None and not last_cache.empty:
                stocks = last_cache
                log.info(f"使用缓存: {len(stocks)}只")
            else:
                fallback_codes = ["600519","000858","002371","300308","600036","000333",
                    "601318","000002","300750","002594","688981","688256",
                    "688012","688041","688072","688120","688037","688111",
                    "688200","688498","688169","688536","688008","688126",
                    "688390","688005","688599","688036","688303","688223"]
                stocks = pd.DataFrame([{"code": c} for c in fallback_codes])
                self._stock_list = stocks
        
        # 基础灰度: 排除特殊代码
        results = []
        excluded_prefixes = ("300", "688", "8", "4")  # 创业板/科创板/北交所/B股可保留
        
        for _, row in stocks.iterrows():
            code = row["code"]
            results.append({
                "code": code,
                "close": row.get("close", 10.0),  # 默认值，后续有真实数据
                "amount_20d_avg": row.get("amount_20d_avg", 1e8),
            })
        
        # 按成交额排序，取流动性好的
        df_result = pd.DataFrame(results)
        if not df_result.empty:
            df_result = df_result.sort_values("amount_20d_avg", ascending=False)
            log.info(f"基础筛选通过: {len(df_result)}只")
            # 缓存结果
            try:
                self.save_cache("screened_full_last", df_result)
            except Exception:
                pass
        
        return df_result

    def batch_kline(self, codes: list, days: int = 120) -> Dict[str, pd.DataFrame]:
        """批量获取K线数据（通过统一 DataProvider）"""
        result = {}
        for code in codes:
            try:
                df = self.provider.get_kline(code, days)
                if df is not None and not df.empty:
                    result[code] = df
            except Exception:
                continue
        return result

    # ---------- 4. 缓存管理 ----------

    def save_cache(self, name: str, data, ttl_hours: int = None):
        """保存缓存（含版本标记 + TTL元数据）"""
        import hashlib
        import pickle as _pk
        path = cache_path(name)
        version = hashlib.md5(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()
        ttl = ttl_hours or CACHE_TTL_HOURS
        payload = {"version": version, "ttl": ttl, "data": data, "saved_at": time.time()}
        with open(path, "wb") as _f:
            _pk.dump(payload, _f, protocol=_pk.DEFAULT_PROTOCOL)


    def load_cache(self, name: str, max_age_hours: int = None):
        """加载缓存（含版本校验 + TTL自动过期）
        
        Args:
            name: 缓存名称
            max_age_hours: 过期时间（小时），默认从config.json读取
        """
        max_age = max_age_hours if max_age_hours is not None else CACHE_TTL_HOURS
        path = cache_path(name)
        if not path.exists():
            return None
        
        try:
            import hashlib
            import pickle as _pk
            with open(path, "rb") as _f:
                payload = _pk.load(_f)
            if not isinstance(payload, dict) or "data" not in payload:
                return None  # 旧格式缓存，忽略
            cached_ver = payload.get("version", "")
            config_hash = hashlib.md5(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()
            if cached_ver and cached_ver != config_hash:
                log.info(f"缓存版本不匹配，忽略: {name}")
                return None
            age = (time.time() - payload.get("saved_at", 0)) / 3600
            if age >= (payload.get("ttl", max_age)):
                log.info(f"缓存已过期 ({age:.1f}h): {name}")
                return None
            data = payload["data"]
            # 版本校验
            log.debug(f"缓存命中: {name}")
            return data
        except Exception as e:
            log.warning(f"缓存读取失败: {name} -> {e}")
            return None

    def clear_cache(self, name: str = None):
        """清除缓存（name=None则清除全部）"""
        if name:
            path = cache_path(name)
            if path.exists():
                path.unlink()
                log.info(f"缓存已清除: {name}")
        else:
            import shutil
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            log.info("全部缓存已清除")
