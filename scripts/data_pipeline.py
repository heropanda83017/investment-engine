#!/usr/bin/env python3
"""
data_pipeline — 数据获取管线统一入口
====================================

将 data_optimizer + monitor + stock_analyst + tickflow 整合为一条命令。

架构:
  data_pipeline.py
      |-- DataLayer (优化层: 缓存+降级+熔断)
      |-- Monitor (监控+告警+看板)
      |-- StockAnalyst (分析+可视化)
      |-- CLI (一键执行)

用法:
  # CLI
  python data_pipeline.py kline 600519          # 获取K线(自动缓存)
  python data_pipeline.py finance 600519         # 获取财务摘要
  python data_pipeline.py analyze 600519         # 综合分析+可视化
  python data_pipeline.py batch 600519 000858    # 批量对比
  python data_pipeline.py realtime 600519 002371 # 实时快照
  python data_pipeline.py monitor                # 状态看板
  python data_pipeline.py dashboard              # 生成HTML看板
  python data_pipeline.py clear                  # 清除缓存

  # Python API
  from data_pipeline import get_pipeline
  pl = get_pipeline()
  kline = pl.kline("600519")
  report = pl.analyze("600519")
  pl.dashboard()  # 生成HTML看板
"""

import sys, os, time, json
from datetime import datetime
from pathlib import Path

from env import DATA_ROOT, IE_SCRIPTS, IE_CACHE, IE_CACHE_OPTIMIZED, IE_CACHE_TICKFLOW, IE_CACHE_ANALYSIS, IE_CACHE_MONITOR, LEGACY_SCRIPTS
sys.path.insert(0, str(LEGACY_SCRIPTS))

from data_optimizer import OptimizedDataLayer
from monitor import get_monitor



class DataPipeline:
    """统一数据获取管线"""

    def __init__(self):
        self.data = OptimizedDataLayer()
        self.monitor = get_monitor()
        self._analyst = None
        print("[pipeline] DataPipeline ready")
        print("  Cache: hot+disk | Degrade: 4 chains | Breaker: 4 sources")

    @property
    def analyst(self):
        if self._analyst is None:
            from stock_analyst import StockAnalyst
            self._analyst = StockAnalyst()
        return self._analyst

    # ---- 数据获取 ----

    def kline(self, code, days=120):
        """日K线（带监控）"""
        t0 = time.time()
        try:
            df = self.data.get_kline(code, days)
            lat = (time.time() - t0) * 1000
            if not df.empty:
                self.monitor.record_request("akshare_sina", "kline", lat, True)
                print(f"[kline] {code}: {len(df)} bars, last={df['收盘'].iloc[-1]:.2f} ({lat:.0f}ms)")
            else:
                self.monitor.record_failure("akshare_sina", "kline", "empty")
            return df
        except Exception as e:
            self.monitor.record_failure("akshare_sina", "kline", str(e))
            raise

    def financial(self, code):
        """财务摘要（带监控）"""
        t0 = time.time()
        try:
            df = self.data.get_financial_abstract(code)
            lat = (time.time() - t0) * 1000
            if not df.empty:
                self.monitor.record_request("akshare_ths", "financial", lat, True)
                latest = df.iloc[-1]
                print(f"[financial] {code}: {len(df)} periods, "
                      f"ROE={latest.get('净资产收益率','-'):.1f}% "
                      f"gross_margin={latest.get('销售毛利率','-'):.1f}%")
            else:
                self.monitor.record_failure("akshare_ths", "financial", "empty")
            return df
        except Exception as e:
            self.monitor.record_failure("akshare_ths", "financial", str(e))
            raise

    def realtime(self, codes):
        """实时快照（带监控）"""
        t0 = time.time()
        try:
            data = self.data.get_realtime(codes)
            lat = (time.time() - t0) * 1000
            if data:
                self.monitor.record_request("tickflow", "realtime", lat, True)
                for d in data:
                    chg = d.get("change_pct", 0)
                    arrow = "+" if chg >= 0 else ""
                    print(f"  {d['code']}: {d.get('price','-')} ({arrow}{chg:.2f}%)")
            return data
        except Exception as e:
            self.monitor.record_failure("tickflow", "realtime", str(e))
            raise

    # ---- 分析 ----

    def analyze(self, code, name=""):
        """综合分析"""
        r = self.analyst.analyze(code, name)
        print(f"\n{r['summary']}")
        if r.get("growth"):
            print(f"  Growth: {r['growth']}")
        # 生成图表
        img_k = self.analyst.plot_kline(code)
        img_f = self.analyst.plot_financial(code)
        print(f"  Charts: {img_k}, {img_f}")
        return r

    def batch(self, codes):
        """批量分析"""
        t0 = time.time()
        df = self.analyst.batch_analyze(codes)
        lat = (time.time() - t0) * 1000
        print(f"[batch] {len(codes)} stocks, {lat:.0f}ms")
        print(df.to_string())
        return df

    # ---- 监控 ----

    def show_monitor(self):
        """显示状态"""
        self.monitor.show_status()

    def dashboard(self):
        """生成HTML看板"""
        path = self.monitor.generate_dashboard()
        print(f"Dashboard: {path}")
        return path

    def clear(self):
        """清除缓存"""
        self.data.clear_cache()
        print("[pipeline] All caches cleared")


_INSTANCE = None
def get_pipeline():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DataPipeline()
    return _INSTANCE


# ================== CLI ==================

def cli():
    import argparse
    parser = argparse.ArgumentParser(description="Data Pipeline - Unified data acquisition")
    parser.add_argument("command", nargs="?", default="help",
                       choices=["kline","finance","realtime","analyze","batch",
                                "monitor","dashboard","clear","help"])
    parser.add_argument("args", nargs="*", help="stock codes or params")
    parser.add_argument("--days", type=int, default=120, help="K-line days")
    
    args = parser.parse_args()
    pl = get_pipeline()
    
    if args.command == "help" or args.command is None:
        print(__doc__)
    
    elif args.command == "kline":
        for code in args.args:
            pl.kline(code, args.days)
    
    elif args.command == "finance":
        for code in args.args:
            pl.financial(code)
    
    elif args.command == "realtime":
        pl.realtime(args.args)
    
    elif args.command == "analyze":
        for code in args.args:
            pl.analyze(code)
    
    elif args.command == "batch":
        pl.batch(args.args)
    
    elif args.command == "monitor":
        pl.show_monitor()
    
    elif args.command == "dashboard":
        pl.dashboard()
    
    elif args.command == "clear":
        pl.clear()


if __name__ == "__main__":
    cli()
