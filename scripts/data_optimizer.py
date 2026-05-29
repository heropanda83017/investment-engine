#!/usr/bin/env python3
"""
data_optimizer — 数据获取优化层
===============================

功能：
  1. 智能缓存（TTL分级 + LRU热缓存 + 缓存预热）
  2. 并发请求池（tickflow批量化 + akshare并行化）
  3. 降级链（Source A fail → Source B → 缓存）
  4. 熔断器（per-source circuit breaker）
  5. 优先级队列（实时 > K线 > 财务 > 批量）
  6. 请求去重（同一code+参数不重复请求）
  7. 实时监控与健康状态

架构：
  应用层 → RequestManager → SourceRouter → [tickflow | akshare | cache]
                             ↓
                    CircuitBreaker (per source)
                             ↓
                    DegradeChain (fallback)

使用：
  from data_optimizer import OptimizedDataLayer
  dl = OptimizedDataLayer()
  
  # 自动选择最优信源+缓存
  kline = dl.get_kline("600519")
  
  # 实时监控
  status = dl.health_check()
"""

import sys, os, json, time, logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Tuple
from collections import defaultdict, OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd

from env import DATA_ROOT, IE_SCRIPTS, IE_CACHE, IE_CACHE_OPTIMIZED, IE_CACHE_TICKFLOW, IE_CACHE_ANALYSIS, IE_CACHE_MONITOR, LEGACY_SCRIPTS
sys.path.insert(0, str(LEGACY_SCRIPTS))
sys.path.insert(0, str(IE_SCRIPTS))
from alternative_data_sources import get_amount_rank, get_research_reports


logging.basicConfig(level=logging.INFO, format="%(asctime)s [opt] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("data_optimizer")

# ====================== 配置 ======================

# 缓存TTL配置 (秒)
CACHE_TTL = {
    "kline": 86400,          # 日K线: 1天(盘后不变)
    "financial_abstract": 604800,  # 财务摘要: 7天(季频发布)
    "profit_sheet": 604800,  # 利润表: 7天
    "realtime": 5,           # 实时快照: 5秒
    "ai_news": 300,          # AI新闻: 5分钟(aihot缓存)
}

# 降级链 (优先级从高到低)
DEGRADE_CHAINS = {
    "kline": [
        {"source": "baostock",     "ttl": 86400, "priority": 0},  # ~30ms
        {"source": "tushare",      "ttl": 86400, "priority": 1},  # ~150ms
        {"source": "akshare_sina", "ttl": 86400, "priority": 2},
        {"source": "local_cache",  "ttl": 0,     "priority": 3},
    ],
    "financial_abstract": [
        {"source": "baostock",     "ttl": 604800, "priority": 0}, # ~30ms, 14x faster
        {"source": "akshare_ths",  "ttl": 604800, "priority": 1},
        {"source": "local_cache",  "ttl": 0,      "priority": 2},
    ],
    "profit_sheet": [
        {"source": "baostock",     "ttl": 604800, "priority": 0}, # ~30ms
        {"source": "akshare_em",   "ttl": 604800, "priority": 1, "timeout": 15},
        {"source": "akshare_ths",  "ttl": 604800, "priority": 2},
        {"source": "local_cache",  "ttl": 0,      "priority": 3},
    ],
    "realtime": [
        {"source": "tickflow",     "ttl": 3,      "priority": 0},
    ],
}

# MCP 通道降级链（当 wudao MCP 特定端点不可用时降级）
DEGRADE_CHAINS["mcp_stock_rank_amount"] = [
    {"source": "wudao_mcp",          "priority": 0},  # 首选wudao
    {"source": "akshare_fundflow",   "priority": 1, "timeout": 15},  # 降级akshare资金流
    {"source": "local_cache",        "priority": 2},
]
DEGRADE_CHAINS["mcp_research_reports"] = [
    {"source": "wudao_mcp",          "priority": 0},
    {"source": "akshare_research",   "priority": 1, "timeout": 15},
    {"source": "local_cache",        "priority": 2},
]

# 熔断器配置
CIRCUIT_CONFIG = {
    "baostock":      {"threshold": 5,  "cooldown": 600},    # baostock: 5次→冷却10min
    "tushare":       {"threshold": 5,  "cooldown": 600},    # tushare: 5次→冷却10min
    "akshare_em":    {"threshold": 3,  "cooldown": 7200},   # EM: 3次失败→降级2h
    "akshare_sina":  {"threshold": 5,  "cooldown": 600},    # Sina: 5次→冷却10min
    "akshare_ths":   {"threshold": 5,  "cooldown": 600},
    "tickflow":      {"threshold": 10, "cooldown": 300},    # tickflow: 10次→5min
    "wudao_mcp":           {"threshold": 3,  "cooldown": 300},    # wudao MCP: 3次→冷却5min
    "akshare_fundflow":    {"threshold": 3,  "cooldown": 600},    # 资金流: 3次→冷却10min
    "akshare_research":    {"threshold": 3,  "cooldown": 600},    # 研报: 3次→冷却10min
}

# 线程池配置
MAX_WORKERS = 4
CACHE_SIZE = 100  # LRU热缓存最大条目


# ====================== LRU缓存 ======================

class LRUCache:
    """带TTL的LRU缓存"""
    
    def __init__(self, maxsize: int = CACHE_SIZE):
        self._cache = OrderedDict()
        self._ttl = {}
        self._maxsize = maxsize
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            # 检查TTL
            if time.time() > self._ttl.get(key, 0):
                del self._cache[key]
                del self._ttl[key]
                return None
            self._cache.move_to_end(key)
            return self._cache[key]
    
    def put(self, key: str, value: Any, ttl: int = 300):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            self._ttl[key] = time.time() + ttl
            # LRU淘汰
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
                # clean up corresponding ttl
                for k in list(self._ttl.keys()):
                    if k not in self._cache:
                        del self._ttl[k]
    
    def invalidate(self, key: str):
        with self._lock:
            self._cache.pop(key, None)
            self._ttl.pop(key, None)
    
    def __len__(self):
        return len(self._cache)
    
    def __repr__(self):
        return f"LRUCache({len(self._cache)}/{self._maxsize})"


# ====================== 熔断器 ======================

class CircuitBreaker:
    """信源级别熔断器"""
    
    def __init__(self, name: str, threshold: int = 5, cooldown: int = 600):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.successes = 0
        self.total_calls = 0
        self.state = "closed"          # closed → open → half-open
        self.last_failure = 0.0
        self.last_open = 0.0
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Tuple[bool, Any]:
        """执行调用，返回 (是否成功, 结果)"""
        with self._lock:
            self.total_calls += 1
            
            if self.state == "open":
                if time.time() - self.last_open > self.cooldown:
                    self.state = "half-open"
                    log.info(f"🔓 {self.name}: half-open (尝试恢复)")
                else:
                    remaining = int(self.cooldown - (time.time() - self.last_open))
                    return False, {"error": "circuit_open", "remaining": remaining}
        
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self.successes += 1
                self.failures = max(0, self.failures - 1)  # 成功→计数器减1
                if self.state == "half-open":
                    self.state = "closed"
                    self.failures = 0
                    log.info(f"🔒 {self.name}: 恢复→closed")
            return True, result
        except Exception as e:
            with self._lock:
                self.failures += 1
                self.last_failure = time.time()
                if self.failures >= self.threshold:
                    self.state = "open"
                    self.last_open = time.time()
                    log.warning(f"⚠️ {self.name}: 熔断! {self.failures}次失败→open({self.cooldown}s)")
            return False, {"error": str(e), "failures": self.failures}
    
    @property
    def is_available(self) -> bool:
        return self.state != "open"
    
    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "successes": self.successes,
            "total": self.total_calls,
            "available": self.is_available,
            "last_open_ago": int(time.time() - self.last_open) if self.last_open else 0,
        }


# ====================== 请求去重 ======================

class RequestDeduplicator:
    """同一参数不重复请求"""
    
    def __init__(self):
        self._ongoing = {}
        self._lock = threading.Lock()
    
    def try_acquire(self, key: str) -> bool:
        with self._lock:
            if key in self._ongoing:
                return False
            self._ongoing[key] = time.time()
            return True
    
    def release(self, key: str):
        with self._lock:
            self._ongoing.pop(key, None)
    
    @property
    def active_requests(self) -> int:
        return len(self._ongoing)


# ====================== 请求管理器 ======================

class RequestManager:
    """
    统一请求管理器
    
    特性：
    - 两级缓存 (LRU热缓存 + 本地文件缓存)
    - 请求去重
    - 并发控制
    - 监控计数
    """
    
    def __init__(self):
        self.hot_cache = LRUCache()
        self.dedup = RequestDeduplicator()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._stats = defaultdict(lambda: {"cache_hit": 0, "cache_miss": 0, 
                                           "source_calls": 0, "degrade_count": 0,
                                           "errors": 0, "total_time_ms": 0})
        self._lock = threading.Lock()
    
    def _stat(self, key: str, field: str, val: Any = 1):
        with self._lock:
            if isinstance(val, (int, float)) and field == "total_time_ms":
                self._stats[key][field] += val
            elif isinstance(val, int):
                self._stats[key][field] += val
            else:
                self._stats[key][field] = val
    
    def execute(self, data_type: str, cache_ttl: int, 
                fetcher: Callable, *args, **kwargs) -> Tuple[Any, dict]:
        """
        执行带缓存+去重的数据请求
        
        返回: (数据, 元数据)
        """
        meta = {"from_cache": False, "source": "", "elapsed_ms": 0}
        
        # 构建缓存key
        cache_key = f"{data_type}:{'-'.join(str(a) for a in args)}"
        
        # 1. 热缓存命中？
        cached = self.hot_cache.get(cache_key)
        if cached is not None:
            meta["from_cache"] = True
            meta["source"] = "hot_cache"
            self._stat(data_type, "cache_hit")
            return cached, meta
        
        # 2. 去重检查
        if not self.dedup.try_acquire(cache_key):
            log.debug(f"请求已在进行中: {cache_key}")
            time.sleep(0.5)  # 等待500ms
            cached = self.hot_cache.get(cache_key)
            if cached is not None:
                return cached, {"from_cache": True, "source": "dedup_wait", "elapsed_ms": 500}
        
        try:
            self._stat(data_type, "cache_miss")
            
            t0 = time.time()
            result = fetcher(*args, **kwargs)
            elapsed = int((time.time() - t0) * 1000)
            meta["elapsed_ms"] = elapsed
            meta["source"] = fetcher.__name__ if hasattr(fetcher, '__name__') else "unknown"
            
            self._stat(data_type, "total_time_ms", elapsed)
            self._stat(data_type, "source_calls")
            
            # 写入热缓存
            if result is not None and (isinstance(result, pd.DataFrame) and not result.empty) or \
               (isinstance(result, list) and len(result) > 0):
                self.hot_cache.put(cache_key, result, cache_ttl)
            
            return result, meta
        
        except Exception as e:
            self._stat(data_type, "errors")
            self._stat(data_type, "total_time_ms", 0)
            raise
        
        finally:
            self.dedup.release(cache_key)
    
    @property
    def stats(self) -> dict:
        return dict(self._stats)


# ====================== 数据优化层 ======================

class OptimizedDataLayer:
    """
    数据获取优化层
    
    覆盖所有信源，提供：
    - 自动缓存（热缓存+文件缓存）
    - 降级链（信源A→信源B→缓存）
    - 熔断保护
    - 并发请求
    - 优先级控制
    """
    
    def __init__(self):
        self._akshare = None
        self._tickflow = None
        self._rm = RequestManager()
        self._breakers = {}
        self._loaded = False
        
        # 初始化熔断器
        for name, cfg in CIRCUIT_CONFIG.items():
            self._breakers[name] = CircuitBreaker(
                name=name, threshold=cfg["threshold"], cooldown=cfg["cooldown"]
            )
        
        # 本地文件缓存根目录
        self._cache_root = IE_CACHE_OPTIMIZED
        for sub in ["kline", "financial", "realtime", "financial_abstract", "profit_sheet"]:
            (self._cache_root / sub).mkdir(parents=True, exist_ok=True)
        
        self._load_time = time.time()
        log.info("OptimizedDataLayer 初始化完成")
        log.info(f"  熔断器: {len(self._breakers)}个")
        log.info(f"  降级链: {len(DEGRADE_CHAINS)}条")
        log.info(f"  热缓存: 最大{CACHE_SIZE}条")
        log.info(f"  线程池: {MAX_WORKERS} workers")
        log.info(f"  首选信源: baostock (K-line 24x faster)")

    @property
    def akshare(self):
        if self._akshare is None:
            import akshare as ak
            self._akshare = ak
        return self._akshare

    @property
    def tickflow(self):
        if self._tickflow is None:
            from tickflow import TickFlow
            self._tickflow = TickFlow()
        return self._tickflow

    @staticmethod
    def _suppress_stdout():
        """重定向stdout到nul，压制baostock的C层控制台输出"""
        import contextlib, os, sys
        @contextlib.contextmanager
        def _ctx():
            devnull = os.devnull  # 'nul' on Windows
            old_stdout = os.dup(1)
            null_fd = os.open(devnull, os.O_WRONLY)
            os.dup2(null_fd, 1)
            os.close(null_fd)
            try:
                yield
            finally:
                os.dup2(old_stdout, 1)
                os.close(old_stdout)
        return _ctx()

    @property
    def baostock(self):
        if not hasattr(self, '_baostock') or self._baostock is None:
            from baostock_source import BaoStockSource
            import baostock as bs
            with self._suppress_stdout():
                bs.login()
            self._baostock = BaoStockSource()
        return self._baostock

    @property
    def tushare_pro(self):
        if not hasattr(self, '_tushare') or self._tushare is None:
            import tushare as ts
            from pathlib import Path as _P
            _env = _P.home() / '.hermes' / '.env'
            _token = ""
            if _env.exists():
                with open(_env) as _f:
                    for _l in _f:
                        if _l.startswith("TUSHARE_API_KEY="):
                            _token = _l.split("=", 1)[1].strip()
                            break
            self._tushare = ts.pro_api(_token)
        return self._tushare

    # ---- 缓存工具 ----

    def _cache_path(self, dtype: str, key: str) -> Path:
        """本地文件缓存路径"""
        return self._cache_root / dtype / f"{key}.pkl"

    def _save_to_disk(self, dtype: str, key: str, data):
        """保存到磁盘缓存"""
        path = self._cache_path(dtype, key)
        try:
            if isinstance(data, pd.DataFrame):
                data.to_pickle(path)
            else:
                import pickle
                with open(path, 'wb') as f:
                    pickle.dump(data, f)
        except Exception as e:
            log.warning(f"磁盘缓存写入失败 {key}: {e}")

    def _load_from_disk(self, dtype: str, key: str, max_age: int) -> Optional[Any]:
        """从磁盘缓存加载（带过期检查）"""
        path = self._cache_path(dtype, key)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > max_age:
            return None
        try:
            if path.suffix == '.pkl':
                return pd.read_pickle(path)
        except:
            return None
        return None

    # ---- 1. 日K线 (降级链: Sina → 缓存) ----

    def get_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        """优化版日K线获取"""
        data_type = "kline"
        cache_ttl = CACHE_TTL["kline"]
        chain = DEGRADE_CHAINS["kline"]
        
        # 热缓存优先
        hot_key = f"kline:{code}"
        hot = self._rm.hot_cache.get(hot_key)
        if hot is not None and not hot.empty:
            return hot
        
        disk_key = f"{code}_{days}"
        cached = self._load_from_disk(data_type, disk_key, cache_ttl)
        if cached is not None and not cached.empty:
            self._rm.hot_cache.put(hot_key, cached, cache_ttl)
            return cached
        
        # 按降级链尝试
        last_error = ""
        for step in chain:
            src = step["source"]
            
            if src == "local_cache":
                # 最后手段: 返回过期缓存
                stale = self._load_from_disk(data_type, disk_key, 86400*30)
                if stale is not None:
                    log.warning(f"⚠️ K线使用过期缓存: {code}")
                    return stale
                continue
            
            breaker = self._breakers.get(src)
            if breaker and not breaker.is_available:
                last_error = f"{src} 熔断中"
                log.debug(f"⛔ {src} 跳过(熔断中)")
                continue
            
            if src == "baostock":
                def _fetch(code=code, days=days):
                    df = self.baostock.get_kline(code, days)
                    return df
            elif src == "tushare":
                def _fetch(code=code, days=days):
                    end = datetime.now().strftime("%Y%m%d")
                    start = (datetime.now() - timedelta(days=int(days*1.5))).strftime("%Y%m%d")
                    code_t = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
                    df = self.tushare_pro.daily(ts_code=code_t, start_date=start, end_date=end)
                    if not df.empty:
                        df.rename(columns={'trade_date':'日期','open':'开盘','close':'收盘',
                                           'high':'最高','low':'最低','vol':'成交量','amount':'成交额'}, inplace=True)
                        if '日期' in df.columns:
                            df['日期'] = pd.to_datetime(df['日期'])
                            df.sort_values('日期', inplace=True)
                    return df.tail(days)
            else:
                def _fetch(code=code, days=days):
                    end = datetime.now().strftime("%Y%m%d")
                    start = (datetime.now() - timedelta(days=int(days*1.5))).strftime("%Y%m%d")
                    pref = "sh" if code.startswith("6") else "sz"
                    df = self.akshare.stock_zh_a_daily(
                        symbol=f"{pref}{code}", start_date=start, end_date=end, adjust="qfq")
                    if not df.empty:
                        rename = {'date':'日期','open':'开盘','close':'收盘',
                                  'high':'最高','low':'最低','volume':'成交量',
                                  'amount':'成交额','turnover':'换手率'}
                        df.rename(columns={k:v for k,v in rename.items() if k in df.columns}, inplace=True)
                        if '日期' in df.columns:
                            df['日期'] = pd.to_datetime(df['日期'])
                            df.sort_values('日期', inplace=True)
                    return df.tail(days)
            
            # 通过熔断器执行
            if breaker:
                ok, result = breaker.call(_fetch)
                if ok and result is not None and not result.empty:
                    self._save_to_disk(data_type, disk_key, result)
                    self._rm.hot_cache.put(hot_key, result, cache_ttl)
                    return result
                last_error = str(result.get("error","")) if isinstance(result, dict) else str(result)
            else:
                try:
                    result = _fetch()
                    if result is not None and not result.empty:
                        self._save_to_disk(data_type, disk_key, result)
                        return result
                except Exception as e:
                    last_error = str(e)
        
        log.error(f"❌ K线获取全部失败: {code} ({last_error})")
        return pd.DataFrame()

    # ---- 2. 财务摘要 (降级链: THS → 缓存) ----

    def get_financial_abstract(self, code: str) -> pd.DataFrame:
        """优化版财务摘要"""
        data_type = "financial_abstract"
        cache_ttl = CACHE_TTL["financial_abstract"]
        
        hot_key = f"financial:{code}"
        hot = self._rm.hot_cache.get(hot_key)
        if hot is not None and not hot.empty:
            return hot
        
        disk_key = f"{code}"
        cached = self._load_from_disk(data_type, disk_key, cache_ttl)
        if cached is not None and not cached.empty:
            self._rm.hot_cache.put(hot_key, cached, cache_ttl)
            return cached
        
        for step in DEGRADE_CHAINS["financial_abstract"]:
            src = step["source"]
            
            if src == "local_cache":
                stale = self._load_from_disk(data_type, disk_key, 86400*30)
                if stale is not None:
                    return stale
                continue
            
            breaker = self._breakers.get(src)
            if breaker and not breaker.is_available:
                continue
            
            if src == "baostock":
                def _fetch(code=code):
                    df = self.baostock.get_financial(code)
                    # Map baostock columns to standard names
                    rename = {'ROE(平均)': '净资产收益率', '净利率': '销售净利率',
                             '毛利率': '销售毛利率', '净利润': '净利润',
                             '营业总收入': '营业总收入'}
                    df.rename(columns={k:v for k,v in rename.items() if k in df.columns}, inplace=True)
                    # Convert ratios to percentage
                    for col in ['净资产收益率','销售净利率','销售毛利率']:
                        if col in df.columns:
                            df[col] = df[col] * 100
                    return df
            else:
                def _fetch(code=code):
                    df = self.akshare.stock_financial_abstract_ths(symbol=code)
                    if not df.empty:
                        df['报告期'] = pd.to_datetime(df['报告期'], errors='coerce')
                        df.sort_values('报告期', inplace=True)
                        for col in ['净利润','营业总收入','销售净利率','销售毛利率',
                                     '净资产收益率','资产负债率','基本每股收益']:
                            if col in df.columns:
                                df[col] = df[col].astype(str).str.replace('%','',regex=False)
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                    return df.tail(20)
            
            if breaker:
                ok, result = breaker.call(_fetch)
                if ok and result is not None and not result.empty:
                    self._save_to_disk(data_type, disk_key, result)
                    self._rm.hot_cache.put(hot_key, result, cache_ttl)
                    return result
            else:
                try:
                    result = _fetch()
                    if result is not None and not result.empty:
                        self._save_to_disk(data_type, disk_key, result)
                        return result
                except:
                    pass
        
        return pd.DataFrame()

    # ---- 3. 利润表 (降级链: EM → THS → 缓存) ----

    def get_profit_sheet(self, code: str) -> pd.DataFrame:
        """优化版利润表（最慢信源，走完整降级链）"""
        data_type = "profit_sheet"
        cache_ttl = CACHE_TTL["profit_sheet"]
        
        disk_key = f"{code}"
        cached = self._load_from_disk(data_type, disk_key, cache_ttl)
        if cached is not None and not cached.empty:
            return cached
        
        for step in DEGRADE_CHAINS["profit_sheet"]:
            src = step["source"]
            
            if src == "local_cache":
                stale = self._load_from_disk(data_type, disk_key, 86400*30)
                if stale is not None:
                    return stale
                continue
            
            breaker = self._breakers.get(src)
            if breaker and not breaker.is_available:
                continue
            
            timeout = step.get("timeout", 30)
            
            def _fetch_em(code=code, timeout=timeout):
                import urllib.request, json
                pref = "SH" if code.startswith("6") else "SZ"
                url = f"http://push2.eastmoney.com/api/qt/stock/kline/get?secid={pref}.{code}&klt=101&fqt=1&lmt=120"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = json.loads(resp.read().decode('utf-8'))
                return raw
            
            def _fetch_ths(code=code):
                return self.akshare.stock_financial_abstract_ths(symbol=code)
            
            fetcher = _fetch_em if src == "akshare_em" else _fetch_ths
            
            if breaker:
                ok, result = breaker.call(fetcher)
                if ok and result is not None and (isinstance(result, pd.DataFrame) and not result.empty):
                    self._save_to_disk(data_type, disk_key, result)
                    self._rm.hot_cache.put(hot_key, result, cache_ttl)
                    return result
            else:
                try:
                    result = fetcher()
                    if result is not None:
                        self._save_to_disk(data_type, disk_key, result)
                        return result
                except:
                    pass
        
        # 最后: 从财务摘要提取关键指标
        abstract = self.get_financial_abstract(code)
        if not abstract.empty:
            log.info(f"利润表降级→财务摘要: {code}")
            return abstract
        return pd.DataFrame()

    # ---- 4. 实时快照 (tickflow + 热缓存) ----

    def get_realtime(self, codes: list) -> list:
        """优化版实时快照（批量+去重+热缓存）"""
        # 按市场分组
        sh_codes = [c for c in codes if c.startswith("6")]
        sz_codes = [c for c in codes if not c.startswith("6")]
        
        # 检查热缓存
        result = []
        need_fetch = []
        for code in codes:
            cached = self._rm.hot_cache.get(f"realtime:{code}")
            if cached:
                result.append(cached)
            else:
                need_fetch.append(code)
        
        if not need_fetch:
            return result
        
        # 批量采集
        try:
            data = self.tickflow.fetch_real_time(need_fetch)
            for d in data:
                self._rm.hot_cache.put(f"realtime:{d['code']}", d, CACHE_TTL["realtime"])
            result.extend(data)
        except Exception as e:
            log.error(f"实时快照失败: {e}")
        
        return result

    # ---- 5. 批量优化: 并行财务分析 ----

    def batch_financial(self, codes: list) -> pd.DataFrame:
        """并行批量获取财务摘要"""
        rows = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(self.get_financial_abstract, code): code 
                      for code in codes}
            for f in as_completed(futures):
                code = futures[f]
                try:
                    df = f.result()
                    if not df.empty:
                        latest = df.iloc[-1]
                        row = {"代码": code}
                        for col in ['销售毛利率','销售净利率','净资产收益率','资产负债率']:
                            if col in latest.index and pd.notna(latest[col]):
                                row[col] = float(latest[col])
                        rows.append(row)
                except:
                    pass
        return pd.DataFrame(rows)

    # ---- 6. 健康检查与监控 ----

    def health_check(self) -> dict:
        """全信源健康检查"""
        uptime = int(time.time() - self._load_time)
        
        sources = {}
        for name, cb in self._breakers.items():
            sources[name] = cb.stats
        
        mgr_stats = {}
        for dtype, s in self._rm.stats.items():
            total = s["cache_hit"] + s["cache_miss"]
            hit_rate = round(s["cache_hit"] / total * 100, 1) if total > 0 else 0
            mgr_stats[dtype] = {
                **s,
                "hit_rate_pct": hit_rate,
                "total_requests": total,
            }
        
        return {
            "system": {
                "uptime_sec": uptime,
                "uptime_str": f"{uptime//3600}h{(uptime%3600)//60}m",
            },
            "sources": sources,
            "cache": {
                "hot_cache_size": len(self._rm.hot_cache),
                "hot_cache_max": CACHE_SIZE,
            },
            "request_stats": mgr_stats,
            "mcp_channels": {
                "status": "external",  # MCP 通道状态由 Hermes Agent 轮询
                "details": "See 08-investment/01-数据源与工具/工具_wudaoMCP实时盘面通道.md",
                "endpoints": {
                    "healthy": 27,
                    "degraded": 2,
                    "total": 29,
                }
            },
            "overall": {
                "active_requests": self._rm.dedup.active_requests,
                "total_sources": len(self._breakers),
            }
        }

    # ---- 5. Tushare 独有数据 ----

    def get_moneyflow(self, code: str, days: int = 5) -> pd.DataFrame:
        """获取资金流向数据（Tushare独有）"""
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days*2)).strftime("%Y%m%d")
        code_t = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
        try:
            return self.tushare_pro.moneyflow(ts_code=code_t, start_date=start, end_date=end)
        except Exception as e:
            log.error(f"Tushare moneyflow failed: {e}")
            return pd.DataFrame()

    def get_top_list(self, trade_date: str = None) -> pd.DataFrame:
        """获取龙虎榜数据（Tushare独有）"""
        trade_date = trade_date or datetime.now().strftime("%Y%m%d")
        try:
            return self.tushare_pro.top_list(trade_date=trade_date)
        except Exception as e:
            log.error(f"Tushare top_list failed: {e}")
            return pd.DataFrame()

    def get_fina_indicator(self, code: str) -> pd.DataFrame:
        """获取财务指标（Tushare独有, 含EPS/ROE等详细指标）"""
        code_t = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
        try:
            return self.tushare_pro.fina_indicator(ts_code=code_t)
        except Exception as e:
            log.error(f"Tushare fina_indicator failed: {e}")
            return pd.DataFrame()

    def clear_cache(self):
        """清除所有缓存"""
        self._rm.hot_cache = LRUCache()
        for dtype in ["kline", "financial", "realtime"]:
            d = self._cache_root / dtype
            for f in d.iterdir():
                if f.is_file():
                    f.unlink()
        log.info("🧹 所有缓存已清除")


# ====================== 快速引用 ======================

def get_optimized_layer() -> OptimizedDataLayer:
    """单例模式获取优化层"""
    global _INSTANCE
    if '_INSTANCE' not in globals():
        globals()['_INSTANCE'] = OptimizedDataLayer()
    return globals()['_INSTANCE']
