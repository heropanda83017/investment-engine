#!/usr/bin/env python3
"""
tickflow — A股逐笔成交/分笔数据流水线 (Tick Data Flow)

架构：
  东方财富 push2 API (实时) -> 采集器 -> 校验器 -> 存储器 -> 聚合器 -> 查询API
                                    |
                              tickflow_config.json (监控池配置)

数据存储：
  $AIGC_DATA_ROOT/investment-engine/_cache/tickflow/
  +-- ticks/           <- 逐笔成交 (YYYY-MM-DD/CODE.csv)
  +-- snapshots/       <- 盘口快照 (YYYY-MM-DD/CODE.csv)
  +-- bars/            <- 聚合K线 (CODE.csv, 1min/5min/30min)
  +-- meta.db          <- 元数据SQLite (可选)

使用方式：
  from tickflow import TickFlow
  tf = TickFlow()
  tf.fetch_real_time("600519")        # 实时拉取茅台逐笔
  tf.get_ticks("600519", "2026-05-25") # 查询历史逐笔
  tf.get_bars("600519", "1min")       # 查询1分钟K线
"""

import os
import json
import time
import csv
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import defaultdict

import pandas as pd
import numpy as np
import urllib.request

from env import DATA_ROOT, IE_SCRIPTS, IE_CACHE, IE_CACHE_OPTIMIZED, IE_CACHE_TICKFLOW, IE_CACHE_ANALYSIS, IE_CACHE_MONITOR, LEGACY_SCRIPTS


# -- 日志设置 --
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] tickflow.%(funcName)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tickflow")

# -- 常量 --
DATA_ROOT = Path(os.environ.get("TICKFLOW_DATA_DIR",
    str(IE_CACHE_TICKFLOW)))

CONFIG_PATH = Path(os.environ.get("TICKFLOW_CONFIG",
    str(DATA_ROOT.parent / "tickflow_config.json")))

EM_API = "http://push2.eastmoney.com/api/qt/stock/"
EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/"
}

TICK_FIELDS = [
    ("f43", "price", float),
    ("f44", "high", float),
    ("f45", "low", float),
    ("f48", "volume", int),
    ("f50", "amount", float),
    ("f60", "pe_ttm", float),
    ("f116", "total_mv", float),
    ("f162", "pb", float),
    ("f168", "turnover", float),
    ("f169", "change", float),
    ("f170", "change_pct", float),
]

# -- 默认配置 --
DEFAULT_CONFIG = {
    "version": "1.0.0",
    "created": datetime.now().isoformat(),
    "watchlist": [
        "600519", "000858", "002415", "600036", "300750",
        "002371", "688981", "601138", "002230", "300124",
        "000333", "688041", "603501", "300308", "002594",
    ],
    "storage": {"format": "csv"},
    "collector": {
        "interval_sec": 5,
        "max_retries": 3,
        "retry_delay": 2,
        "timeout": 10,
    },
    "bars": {
        "aggregations": ["1min", "5min", "30min", "1day"],
    },
    "error_handling": {
        "max_consecutive_failures": 10,
        "circuit_breaker_sec": 300,
        "max_retries": 3,
    },
}


# ========================= 配置管理 =========================

def load_config(path=None):
    path = path or CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        log.info(f"配置已加载: {path}")
        return cfg
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    log.info(f"默认配置已创建: {path}")
    return dict(DEFAULT_CONFIG)


# ========================= 网络客户端(带熔断) =========================

class EMClient:
    """东方财富API客户端"""

    def __init__(self, config):
        self.config = config
        self.consecutive_failures = 0
        self.circuit_open_until = 0
        self.max_failures = config["error_handling"]["max_consecutive_failures"]
        self.cooldown = config["error_handling"]["circuit_breaker_sec"]
        self.retries = config["collector"]["max_retries"]
        self.retry_delay = config["collector"]["retry_delay"]
        self.timeout = config["collector"]["timeout"]

    def _circuit_ok(self):
        if self.circuit_open_until > time.time():
            return False
        return True

    def _trip(self):
        self.circuit_open_until = time.time() + self.cooldown
        log.warning(f"熔断触发，冷却 {self.cooldown}s")

    def fetch_quote(self, code):
        """获取单只股票实时快照"""
        if not self._circuit_ok():
            return None

        market = "1" if code.startswith("6") else "0"
        fields = ",".join(f[0] for f in TICK_FIELDS)
        url = f"{EM_API}get?secid={market}.{code}&fltt=2&fields={fields}"

        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=EM_HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                data = raw.get("data")
                if not data:
                    raise ValueError("空响应")

                result = {"code": code, "_ts": int(time.time() * 1000)}
                for em_key, field_name, cast_type in TICK_FIELDS:
                    val = data.get(em_key)
                    if val is not None:
                        try:
                            result[field_name] = cast_type(val)
                        except (ValueError, TypeError):
                            result[field_name] = None
                    else:
                        result[field_name] = None

                self.consecutive_failures = 0
                return result

            except Exception as e:
                log.debug(f"重试 {code} ({attempt+1}/{self.retries}): {type(e).__name__}")
                if attempt < self.retries - 1:
                    time.sleep(self.retry_delay)

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            self._trip()
        return None

    def fetch_batch(self, codes):
        """批量获取"""
        return [r for r in (self.fetch_quote(c) for c in codes) if r is not None]


# ========================= 数据存储 =========================

class TickStore:
    """逐笔/快照/K线存储"""

    def __init__(self, config):
        self.config = config
        self.base = DATA_ROOT
        self.tick_dir = self.base / "ticks"
        self.snap_dir = self.base / "snapshots"
        self.bar_dir = self.base / "bars"
        for d in [self.tick_dir, self.snap_dir, self.bar_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _daily_path(self, base_dir, code, dt=None):
        dt = dt or datetime.now().strftime("%Y-%m-%d")
        day_dir = base_dir / dt
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{code}.csv"

    def append_snapshots(self, code, snapshots, dt=None):
        if not snapshots:
            return
        path = self._daily_path(self.snap_dir, code, dt)
        exists = path.exists()
        df = pd.DataFrame(snapshots)
        df.to_csv(path, mode="a" if exists else "w",
                  header=not exists, index=False, encoding="utf-8")
        log.info(f"存储 {len(snapshots)} 条快照 -> {path}")

    def read_snapshots(self, code, dt):
        path = self._daily_path(self.snap_dir, code, dt)
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path, encoding="utf-8")
        df["code"] = code
        return df

    def read_ticks(self, code, dt):
        path = self._daily_path(self.tick_dir, code, dt)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8")

    def list_available(self):
        result = {"ticks": [], "snapshots": [], "bars": []}
        for dtype, base_dir in [("ticks", self.tick_dir),
                                ("snapshots", self.snap_dir),
                                ("bars", self.bar_dir)]:
            if base_dir.exists():
                for day_dir in sorted(base_dir.iterdir()):
                    if day_dir.is_dir():
                        codes = [f.stem for f in day_dir.iterdir() if f.suffix == ".csv"]
                        if codes:
                            result[dtype].append({
                                "date": day_dir.name,
                                "codes": codes,
                                "count": len(codes)
                            })
        return result


# ========================= K线聚合 =========================

class BarAggregator:
    """快照数据 -> K线"""

    FREQ_MAP = {
        "1min": "1min",
        "5min": "5min",
        "30min": "30min",
        "1day": "1D",
    }

    def __init__(self, store, config):
        self.storage = store
        self.aggs = config["bars"]["aggregations"]

    def aggregate(self, code, dt, freq="1min"):
        if freq not in self.FREQ_MAP:
            raise ValueError(f"不支持 {freq}，可选: {list(self.FREQ_MAP)}")

        df = self.storage.read_snapshots(code, dt)
        if df.empty or "_ts" not in df.columns:
            return pd.DataFrame()

        df["datetime"] = pd.to_datetime(df["_ts"], unit="ms")
        df = df.sort_values("datetime").set_index("datetime")

        ohlc_dict = {"price": "ohlc", "volume": "sum", "amount": "sum",
                     "high": "max", "low": "min"}
        ohlc_dict = {k: v for k, v in ohlc_dict.items() if k in df.columns}

        try:
            bars = df.resample(self.FREQ_MAP[freq]).agg(ohlc_dict)
            if isinstance(bars.columns, pd.MultiIndex):
                bars.columns = [f"{c[0]}_{c[1]}" if c[1] else c[0] for c in bars.columns]
        except Exception as e:
            log.error(f"聚合失败: {e}")
            return pd.DataFrame()

        bars = bars.dropna(subset=[c for c in bars.columns
                                   if "close" in c or "price" in c], how="all")
        bars.reset_index(inplace=True)
        bars["code"] = code
        return bars

    def compute_all(self, code, dt):
        result = {}
        for freq in self.aggs:
            bars = self.aggregate(code, dt, freq)
            if not bars.empty:
                result[freq] = bars
                path = self.storage.bar_dir / f"{code}_{freq}.csv"
                bars.to_csv(path, index=False, encoding="utf-8")
                log.info(f"K线已保存: {path} ({len(bars)}条)")
        return result


# ========================= 主控制器 =========================

class TickFlow:
    """TickFlow 主控制器 — 逐笔数据流水线统一入口"""

    def __init__(self, config_path=None):
        self.config = load_config(config_path)
        self.client = EMClient(self.config)
        self.storage = TickStore(self.config)
        self.aggregator = BarAggregator(self.storage, self.config)
        self.watchlist = self.config["watchlist"]
        log.info(f"TickFlow 就绪: {len(self.watchlist)} 只监控标的")

    def fetch_real_time(self, codes=None):
        """实时采集快照"""
        targets = codes or self.watchlist
        log.info(f"采集 {len(targets)} 只标的...")
        data = self.client.fetch_batch(targets)
        log.info(f"采集完成: {len(data)}/{len(targets)} 成功")
        return data

    def save_data(self, data):
        """存储快照"""
        if not data:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        by_code = defaultdict(list)
        for d in data:
            by_code[d["code"]].append(d)
        for code, items in by_code.items():
            self.storage.append_snapshots(code, items, today)

    def collect_once(self):
        """单次采集+存储"""
        data = self.fetch_real_time()
        self.save_data(data)
        return len(data)

    def collect_loop(self, duration_sec=60):
        """轮询采集循环"""
        interval = self.config["collector"]["interval_sec"]
        cycles = max(1, duration_sec // interval)
        total = 0
        log.info(f"轮询开始: {cycles} 次 x {interval}s")
        for i in range(cycles):
            n = self.collect_once()
            total += n
            if i < cycles - 1:
                time.sleep(interval)
        log.info(f"轮询完成: {total} 条")
        return total

    def get_ticks(self, code, dt):
        """查询逐笔"""
        return self.storage.read_ticks(code, dt)

    def get_snapshots(self, code, dt):
        """查询快照"""
        return self.storage.read_snapshots(code, dt)

    def get_bars(self, code, freq="1min"):
        """查询K线(缓存优先)"""
        path = self.storage.bar_dir / f"{code}_{freq}.csv"
        if path.exists():
            return pd.read_csv(path, encoding="utf-8")
        return pd.DataFrame()

    def aggregate(self, code, dt):
        """聚合K线"""
        return self.aggregator.compute_all(code, dt)

    def info(self):
        """数据源元数据"""
        available = self.storage.list_available()
        return {
            "name": "tickflow",
            "version": self.config["version"],
            "status": "active",
            "watchlist": {"count": len(self.watchlist), "codes": self.watchlist},
            "storage": str(DATA_ROOT),
            "config": str(CONFIG_PATH),
            "available": available,
            "sources": [
                {"name": "东方财富 push2 API", "type": "REST", "auth": "无",
                 "coverage": "全A股实时行情+盘口",
                 "limitations": "非官方，连接不稳定时自动重试/熔断"},
                {"name": "CSV本地存储", "type": "文件", "format": "CSV",
                 "retention": "按日存储"},
            ],
        }


# ========================= 数据源元数据 =========================

METADATA = {
    "data_source": {
        "name": "tickflow",
        "display_name": "TickFlow 逐笔数据流水线",
        "description": "基于东方财富push2 API的A股实时逐笔/快照数据采集管线，"
                       "支持自动熔断、K线聚合、历史查询",
        "version": "1.0.0",
        "created": "2026-05-25",
        "maintainer": "Hermes Agent / ai-investor profile",
    },
    "data_schema": {
        "snapshot": {
            "description": "股票实时快照(含盘口)",
            "fields": {
                "code": "str - 股票代码(6位)",
                "price": "float - 最新成交价",
                "high": "float - 当日最高",
                "low": "float - 当日最低",
                "volume": "int - 成交量(手)",
                "amount": "float - 成交额(万元)",
                "pe_ttm": "float - 市盈率TTM",
                "total_mv": "float - 总市值",
                "pb": "float - 市净率",
                "turnover": "float - 换手率(%)",
                "change": "float - 涨跌额(元)",
                "change_pct": "float - 涨跌幅(%)",
                "_ts": "int - Unix时间戳(毫秒)",
            }
        },
        "bar_1min": {
            "description": "1分钟K线",
            "fields": {
                "datetime": "datetime - K线时间",
                "price_open": "float - 开盘价",
                "price_high": "float - 最高价",
                "price_low": "float - 最低价",
                "price_close": "float - 收盘价",
                "volume": "int - 成交量",
                "amount": "float - 成交额",
                "code": "str - 股票代码",
            }
        }
    },
    "error_handling": {
        "retry": "最多3次重试，间隔2秒",
        "circuit_breaker": "连续10次失败后熔断300秒",
        "logging": "标准Python logging (INFO/WARNING/ERROR)",
        "empty_response": "检查API响应数据有效性，无效则跳过",
    },
    "data_quality": {
        "latency": "网络延迟通常<500ms",
        "accuracy": "数据来自东方财富，与交易所官方数据可能存在秒级延迟",
        "completeness": "非交易日和盘中休市期间无数据",
    },
    "api_endpoints": {
        "TickFlow.info()": "获取数据源元数据",
        "TickFlow.fetch_real_time(codes)": "实时采集快照",
        "TickFlow.collect_once()": "单次采集+存储",
        "TickFlow.collect_loop(sec)": "轮询采集",
        "TickFlow.get_snapshots(code, dt)": "查询历史快照",
        "TickFlow.get_bars(code, freq)": "查询K线",
        "TickFlow.aggregate(code, dt)": "聚合生成K线",
    },
}


# ========================= CLI入口 =========================

def cli():
    import sys
    tf = TickFlow()

    if len(sys.argv) < 2:
        print("tickflow <command> [args]")
        print("  collect          单次采集")
        print("  loop <sec>       轮询采集(默认60s)")
        print("  info             数据源元数据")
        print("  fetch <code>     采集指定股票")
        print("  bars <code> <freq> 聚合K线")
        return

    cmd = sys.argv[1]

    if cmd == "collect":
        n = tf.collect_once()
        print(f"采集 {n} 条")

    elif cmd == "loop":
        dur = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        n = tf.collect_loop(dur)
        print(f"轮询完成: {n} 条")

    elif cmd == "info":
        import pprint
        pprint.pprint(tf.info())

    elif cmd == "fetch":
        code = sys.argv[2] if len(sys.argv) > 2 else "600519"
        data = tf.fetch_real_time([code])
        for d in data:
            print(json.dumps(d, ensure_ascii=False, default=str, indent=2))

    elif cmd == "bars":
        code = sys.argv[2] if len(sys.argv) > 2 else "600519"
        freq = sys.argv[3] if len(sys.argv) > 3 else "1min"
        dt = datetime.now().strftime("%Y-%m-%d")
        bars = tf.aggregate(code, dt)
        for f, df in bars.items():
            print(f"\n{f} K线 ({len(df)}条):")
            print(df.tail(5).to_string() if not df.empty else "(空)")


if __name__ == "__main__":
    cli()
