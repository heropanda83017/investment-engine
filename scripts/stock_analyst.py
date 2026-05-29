#!/usr/bin/env python3
"""
stock_analyst — A股数据分析系统
================================

集成 tickflow（实时快照）+ akshare（日K线+财务数据）

功能：
  1. 日K线获取 (akshare Sina后端)
  2. 实时快照 (tickflow)
  3. 财务数据 (利润表/资产负债表/财务摘要)
  4. 自动存储 + 缓存
  5. 财务指标计算 (ROE杜邦分解/毛利率趋势/营收增速)
  6. 可视化 (K线图/财务指标趋势)

使用：
  from stock_analyst import StockAnalyst
  sa = StockAnalyst()
  
  # 日K线
  kline = sa.get_kline("600519", days=120)
  
  # 财务
  info = sa.get_financial_summary("600519")
  
  # 分析
  analysis = sa.analyze("600519")
  
  # 可视化
  sa.plot_kline("600519")
  sa.plot_financial("600519")
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import defaultdict

import pandas as pd
import numpy as np

from env import DATA_ROOT, IE_SCRIPTS, IE_CACHE, IE_CACHE_OPTIMIZED, IE_CACHE_TICKFLOW, IE_CACHE_ANALYSIS, IE_CACHE_MONITOR, LEGACY_SCRIPTS


# 添加 tickflow 路径
TICKFLOW_DIR = LEGACY_SCRIPTS
sys.path.insert(0, str(TICKFLOW_DIR))

# --- 配置 ---
DATA_ROOT = IE_CACHE_ANALYSIS
DATA_ROOT.mkdir(parents=True, exist_ok=True)

for sub in ["kline", "financial", "reports", "charts"]:
    (DATA_ROOT / sub).mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M")
log = logging.getLogger("stock_analyst")

# ======================== 股票代码映射 ========================

def sina_code(code: str) -> str:
    """akshare Sina 格式: sh600519 / sz000858"""
    if code.startswith("6") or code.startswith("9"):
        return f"sh{code}"
    return f"sz{code}"

def em_code(code: str) -> str:
    """东方财富 format: SH600519 / SZ000858"""
    if code.startswith("6") or code.startswith("9"):
        return f"SH{code}"
    return f"SZ{code}"

# ======================== 数据层 ========================

class DataLayer:
    """统一数据获取层（基于 OptimizedDataLayer，带缓存+降级+熔断）"""

    def __init__(self):
        self._optimizer = None

    @property
    def opt(self):
        if self._optimizer is None:
            from data_optimizer import OptimizedDataLayer
            self._optimizer = OptimizedDataLayer()
        return self._optimizer

    @property
    def tickflow(self):
        return self.opt.tickflow

    @property
    def akshare(self):
        return self.opt.akshare

    def get_kline(self, code, days=120):
        """日K线（自动baostock→Sina→缓存降级）"""
        return self.opt.get_kline(code, days)

    def get_financial_abstract(self, code):
        """财务摘要（走akshare THS，返回多期趋势数据）"""
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

    def get_realtime(self, codes):
        """实时快照（带热缓存）"""
        return self.opt.get_realtime(codes)

    def get_profit_sheet(self, code):
        """利润表（自动baostock→EM→THS→缓存降级）"""
        return self.opt.get_profit_sheet(code)

    def get_balance_sheet(self, code):
        """资产负债表（走akshare EM）"""
        return self.akshare.stock_balance_sheet_by_report_em(symbol=f"SH{code}" if code.startswith("6") else f"SZ{code}")


class Storage:
    """数据缓存与持久化"""

    def __init__(self):
        self.root = DATA_ROOT

    def save_kline(self, code: str, df: pd.DataFrame):
        """缓存日K线"""
        if not df.empty:
            path = self.root / "kline" / f"{code}.csv"
            df.to_csv(path, index=False, encoding="utf-8")
            log.info(f"K线已缓存: {path} ({len(df)}条)")

    def load_kline(self, code: str) -> pd.DataFrame:
        """读取缓存的K线"""
        path = self.root / "kline" / f"{code}.csv"
        if path.exists():
            df = pd.read_csv(path, encoding="utf-8")
            if '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'])
            return df
        return pd.DataFrame()

    def save_financial(self, code: str, df: pd.DataFrame):
        """缓存财务数据"""
        if not df.empty:
            path = self.root / "financial" / f"{code}.csv"
            df.to_csv(path, index=False, encoding="utf-8")
            log.info(f"财务数据已缓存: {path}")

    def load_financial(self, code: str) -> pd.DataFrame:
        """读取缓存的财务数据"""
        path = self.root / "financial" / f"{code}.csv"
        if path.exists():
            return pd.read_csv(path, encoding="utf-8")
        return pd.DataFrame()

    def list_cached(self) -> Dict[str, List[str]]:
        """列出所有缓存数据"""
        result = {}
        for dtype in ["kline", "financial"]:
            d = self.root / dtype
            if d.exists():
                codes = [f.stem for f in d.iterdir() if f.suffix == ".csv"]
                result[dtype] = codes
        return result


# ======================== 分析层 ========================

class Analyzer:
    """财务指标计算与基本面分析"""

    @staticmethod
    def calc_roe_dupont(profit_df: pd.DataFrame, balance_df: pd.DataFrame) -> pd.DataFrame:
        """
        杜邦分析: ROE = 净利率 x 资产周转率 x 权益乘数
        
        需要利润表(TOTAL_OPERATE_INCOME, NETPROFIT) 
        和资产负债表(TOTAL_ASSETS, TOTAL_EQUITY)
        """
        if profit_df.empty or balance_df.empty:
            return pd.DataFrame()
        
        # 提取关键指标
        p = profit_df[['REPORT_DATE', 'TOTAL_OPERATE_INCOME', 'NETPROFIT', 
                       'TOTAL_OPERATE_COST']].copy()
        b = balance_df[['REPORT_DATE', 'TOTAL_ASSETS', 'TOTAL_EQUITY']].copy()
        
        # 按报告期合并
        merged = pd.merge(p, b, on='REPORT_DATE', how='inner')
        if merged.empty:
            return merged
        
        # 计算杜邦分解
        for col in ['TOTAL_OPERATE_INCOME', 'NETPROFIT', 'TOTAL_ASSETS', 'TOTAL_EQUITY']:
            merged[col] = pd.to_numeric(merged[col], errors='coerce')
        
        merged['净利率'] = merged['NETPROFIT'] / merged['TOTAL_OPERATE_INCOME'] * 100
        merged['资产周转率'] = merged['TOTAL_OPERATE_INCOME'] / merged['TOTAL_ASSETS']
        merged['权益乘数'] = merged['TOTAL_ASSETS'] / merged['TOTAL_EQUITY']
        merged['ROE_杜邦'] = merged['净利率'] * merged['资产周转率'] * merged['权益乘数']
        
        return merged[['REPORT_DATE', '净利率', '资产周转率', '权益乘数', 'ROE_杜邦']]

    @staticmethod
    def calc_growth(fin_df: pd.DataFrame, years: int = 3) -> Dict[str, float]:
        """
        计算营收/利润增长率
        
        返回:
            { '营收CAGR_3y': xx, '净利CAGR_3y': xx, '营收同比': xx, ... }
        """
        if fin_df.empty or '营业总收入' not in fin_df.columns:
            return {}
        
        result = {}
        df = fin_df.copy()
        
        # 年报数据筛选
        df['报告期'] = pd.to_datetime(df['报告期'], errors='coerce')
        annual = df[df['报告期'].dt.month == 12].tail(years + 1)
        if len(annual) >= 2:
            rev = annual['营业总收入'].values
            profit = annual['净利润'].values
            years_span = len(annual) - 1
            
            if rev[0] > 0 and rev[-1] > 0:
                result['营收CAGR'] = ((rev[-1] / rev[0]) ** (1 / years_span) - 1) * 100
            
            if profit[0] > 0 and profit[-1] > 0:
                result['净利CAGR'] = ((profit[-1] / profit[0]) ** (1 / years_span) - 1) * 100
        
        return result

    @staticmethod
    def calc_margin_trend(fin_df: pd.DataFrame) -> pd.DataFrame:
        """毛利率/净利率趋势"""
        if fin_df.empty:
            return pd.DataFrame()
        cols = ['报告期', '销售毛利率', '销售净利率', '净资产收益率', '资产负债率']
        cols = [c for c in cols if c in fin_df.columns]
        result = fin_df[cols].dropna(subset=cols[:2]).tail(12).copy()
        if '报告期' in result.columns:
            result['报告期'] = pd.to_datetime(result['报告期'], errors='coerce')
        return result


# ======================== 可视化层 ========================

class Visualizer:
    """数据可视化"""

    def __init__(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        import matplotlib.font_manager as fm
        
        self.plt = plt
        self.mticker = mticker
        self.output_dir = DATA_ROOT / "charts"
        self.output_dir.mkdir(exist_ok=True)
        
        # 尝试设置中文字体
        try:
            # 查找系统可用中文字体
            fonts = [f.name for f in fm.fontManager.ttflist if any(k in f.name for k in ['Hei', 'Song', 'YaHei', 'Fang', 'Kai', 'Microsoft'])]
            if fonts:
                self.plt.rcParams['font.sans-serif'] = [fonts[0]] + self.plt.rcParams['font.sans-serif']
            else:
                self.plt.rcParams['font.sans-serif'] = ['SimHei']
            self.plt.rcParams['axes.unicode_minus'] = False
        except:
            pass

    def plot_kline(self, code: str, df: pd.DataFrame, title: str = "") -> str:
        """
        绘制K线图
        
        返回: 图片路径
        """
        if df.empty or '收盘' not in df.columns:
            return ""
        
        fig, (ax1, ax2) = self.plt.subplots(2, 1, figsize=(12, 7), 
                                             gridspec_kw={'height_ratios': [3, 1]})
        
        dates = df['日期'] if '日期' in df.columns else range(len(df))
        close = df['收盘'].values
        
        # 上子图：K线
        ax1.plot(dates, close, color='#333333', linewidth=1.5, label='收盘价')
        
        # 均线
        for ma, color, label in [(5, '#FF6B6B', 'MA5'), (20, '#4ECDC4', 'MA20'), (60, '#45B7D1', 'MA60')]:
            if len(df) >= ma:
                ax1.plot(dates, df['收盘'].rolling(ma).mean(), 
                        color=color, linewidth=0.8, alpha=0.7, label=label)
        
        # 阳线/阴线标记
        if '开盘' in df.columns:
            colors = ['#FF4444' if df['收盘'].iloc[i] >= df['开盘'].iloc[i] else '#00AA00' 
                     for i in range(len(df))]
            ax1.bar(dates, abs(df['收盘'] - df['开盘']), 
                   bottom=df[['开盘', '收盘']].min(axis=1),
                   color=colors, width=0.6, alpha=0.6)
        
        ax1.set_title(f"{title or code} 日K线", fontsize=14, fontweight='bold')
        ax1.set_ylabel('价格')
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        # 下子图：成交量
        if '成交量' in df.columns:
            vol = df['成交量'].values
            ax2.bar(dates, vol, color='#2196F3', alpha=0.5, width=0.8)
            ax2.set_ylabel('成交量')
            ax2.grid(True, alpha=0.3)
        
        self.plt.tight_layout()
        path = self.output_dir / f"{code}_kline.png"
        fig.savefig(path, dpi=150, bbox_inches='tight')
        self.plt.close(fig)
        log.info(f"K线图已保存: {path}")
        return str(path)

    def plot_financial(self, code: str, fin_df: pd.DataFrame, title: str = "") -> str:
        """
        绘制财务指标趋势图
        
        返回: 图片路径
        """
        if fin_df.empty:
            return ""
        
        fig, axes = self.plt.subplots(2, 2, figsize=(14, 8))
        fig.suptitle(f"{title or code} 财务指标趋势", fontsize=14, fontweight='bold')
        
        metrics = [
            ('销售毛利率', '毛利率 (%)', axes[0, 0]),
            ('销售净利率', '净利率 (%)', axes[0, 1]),
            ('净资产收益率', 'ROE (%)', axes[1, 0]),
            ('资产负债率', '资产负债率 (%)', axes[1, 1]),
        ]
        
        for col, ylabel, ax in metrics:
            if col in fin_df.columns:
                data = fin_df[['报告期', col]].dropna().tail(12)
                if not data.empty:
                    dates = pd.to_datetime(data['报告期'])
                    vals = pd.to_numeric(data[col], errors='coerce')
                    ax.plot(dates, vals, 'o-', linewidth=2, markersize=5)
                    ax.set_title(col, fontsize=11)
                    ax.set_ylabel(ylabel)
                    ax.grid(True, alpha=0.3)
                    ax.tick_params(axis='x', rotation=45)
        
        self.plt.tight_layout()
        path = self.output_dir / f"{code}_financial.png"
        fig.savefig(path, dpi=150, bbox_inches='tight')
        self.plt.close(fig)
        log.info(f"财务趋势图已保存: {path}")
        return str(path)


# ======================== 主控制器 ========================

class StockAnalyst:
    """
    StockAnalyst — A股数据分析系统主控制器
    
    用法:
        sa = StockAnalyst()
        
        # 获取日K线 + 自动缓存
        kline = sa.get_kline("600519")
        
        # 获取财务摘要
        fin = sa.get_financial_summary("600519")
        
        # 综合分析
        rpt = sa.analyze("600519")
        
        # 可视化
        sa.plot_kline("600519")
        sa.plot_financial("600519")
        
        # 批量分析
        results = sa.batch_analyze(["600519", "000858", "002371"])
    """

    def __init__(self):
        self.data = DataLayer()
        self.storage = Storage()
        self.analyzer = Analyzer()
        self.visualizer = Visualizer()
        self.plt = self.visualizer.plt
        log.info(f"StockAnalyst 初始化完成，数据存储: {DATA_ROOT}")

    # ----- 1. 数据获取 -----

    def get_kline(self, code: str, days: int = 120, use_cache: bool = True) -> pd.DataFrame:
        """
        获取日K线（缓存优先）
        
        参数:
            code: 6位股票代码
            days: 获取近N天
            use_cache: 是否使用缓存
        """
        if use_cache:
            cached = self.storage.load_kline(code)
            if not cached.empty and len(cached) >= days * 0.8:
                log.info(f"使用缓存K线: {code} ({len(cached)}条)")
                return cached.tail(days)
        
        df = self.data.get_kline(code, days)
        self.storage.save_kline(code, df)
        return df

    def get_financial_summary(self, code: str, use_cache: bool = True) -> pd.DataFrame:
        """获取财务摘要（缓存优先）"""
        if use_cache:
            cached = self.storage.load_financial(code)
            if not cached.empty and len(cached) >= 8:
                return cached
        
        df = self.data.get_financial_abstract(code)
        self.storage.save_financial(code, df)
        return df

    def get_realtime(self, codes: List[str]) -> List[Dict]:
        """获取实时快照"""
        return self.data.get_realtime(codes)

    # ----- 2. 分析 -----

    def analyze(self, code: str, name: str = "") -> Dict[str, Any]:
        """
        综合分析一只股票
        
        返回:
            {
                "code": "600519",
                "name": "贵州茅台",
                "kline": DataFrame (最近120日),
                "financial": DataFrame (财务摘要最近20期),
                "growth": {营收CAGR, 净利CAGR},
                "dupont": DataFrame (杜邦分解),
                "summary": str (文字总结)
            }
        """
        log.info(f"分析: {code}")
        
        kline = self.get_kline(code)
        fin = self.get_financial_summary(code)
        
        result = {
            "code": code,
            "name": name or code,
            "kline": kline,
            "financial": fin,
            "growth": {},
            "dupont": pd.DataFrame(),
            "summary": "",
        }
        
        # 增长率计算
        if not fin.empty:
            result["growth"] = Analyzer.calc_growth(fin)
        
        # 杜邦分析
        try:
            profit = self.data.get_profit_sheet(code)
            balance = self.data.get_balance_sheet(code)
            if not profit.empty and not balance.empty:
                result["dupont"] = Analyzer.calc_roe_dupont(profit, balance)
        except Exception as e:
            log.warning(f"杜邦分析跳过: {e}")
        
        # 文字总结
        result["summary"] = self._generate_summary(code, kline, fin, result["growth"])
        
        # 保存报告
        self._save_report(code, result)
        
        return result

    def _generate_summary(self, code: str, kline: pd.DataFrame, 
                          fin: pd.DataFrame, growth: dict) -> str:
        """生成分析摘要"""
        lines = [f"【{code} 基本面概览】"]
        
        # 股价
        if not kline.empty and '收盘' in kline.columns:
        # 最新价
            last_price = kline['收盘'].iloc[-1]
            pct_20d = ((kline['收盘'].iloc[-1] / kline['收盘'].iloc[-20]) - 1) * 100 if len(kline) >= 20 else 0
            lines.append(f"最新价: {last_price:.2f} | 20日涨跌: {pct_20d:+.2f}%")
        
        # 财务
        if not fin.empty:
            latest = fin.iloc[-1]
            for col, label in [('销售毛利率', '毛利率'), ('销售净利率', '净利率'),
                               ('净资产收益率', 'ROE'), ('资产负债率', '负债率')]:
                if col in latest.index:
                    val = latest[col]
                    if pd.notna(val):
                        lines.append(f"{label}: {float(val):.1f}%")
        
        # 成长
        if growth:
            for k, v in growth.items():
                lines.append(f"{k}: {v:+.1f}%")
        
        lines.append("\n— 数据来源: akshare + tickflow —")
        return "\n".join(lines)

    def _save_report(self, code: str, result: dict):
        """保存分析报告"""
        report = {
            "code": result["code"],
            "name": result["name"],
            "time": datetime.now().isoformat(),
            "price_summary": {},
            "growth": result["growth"],
            "summary": result["summary"],
        }
        
        if not result["kline"].empty:
            k = result["kline"]
            report["price_summary"] = {
                "latest": float(k['收盘'].iloc[-1]),
                "high_120d": float(k['最高'].max()),
                "low_120d": float(k['最低'].min()),
                "avg_volume": float(k['成交量'].tail(20).mean()),
            }
        
        path = DATA_ROOT / "reports" / f"{code}_report.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        log.info(f"报告已保存: {path}")

    # ----- 3. 批量分析 -----

    def batch_analyze(self, codes: List[str]) -> pd.DataFrame:
        """
        批量分析多只股票，输出横向对比
        
        返回: DataFrame (每行一只股票)
        """
        rows = []
        for code in codes:
            try:
                r = self.analyze(code)
                row = {"代码": code}
                
                if not r["kline"].empty:
                    k = r["kline"]
                    row["最新价"] = float(k['收盘'].iloc[-1])
                    row["20日涨跌%"] = round((k['收盘'].iloc[-1] / k['收盘'].iloc[-20] - 1) * 100, 2) if len(k) >= 20 else None
                
                if not r["financial"].empty:
                    fin = r["financial"].iloc[-1]
                    for col in ['销售毛利率', '销售净利率', '净资产收益率', '资产负债率']:
                        if col in fin.index and pd.notna(fin[col]):
                            row[col] = float(fin[col])
                
                row.update(r["growth"])
                rows.append(row)
                log.info(f"批量分析完成: {code}")
            except Exception as e:
                log.error(f"批量分析失败 {code}: {e}")
        
        df = pd.DataFrame(rows)
        path = DATA_ROOT / "reports" / f"batch_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(path, index=False, encoding='utf_8_sig')
        log.info(f"批量分析报告已保存: {path}")
        return df

    # ----- 4. 可视化 -----

    def plot_kline(self, code: str, days: int = 120) -> str:
        """绘制K线图"""
        kline = self.get_kline(code, days)
        return self.visualizer.plot_kline(code, kline.tail(days), title=f"{code}")

    def plot_financial(self, code: str) -> str:
        """绘制财务指标趋势"""
        fin = self.get_financial_summary(code)
        return self.visualizer.plot_financial(code, fin)

    # ----- 5. 缓存管理 -----

    def clear_cache(self, code: Optional[str] = None):
        """清除缓存"""
        for dtype in ["kline", "financial", "reports", "charts"]:
            d = DATA_ROOT / dtype
            if d.exists():
                if code:
                    for f in d.glob(f"{code}.*"):
                        f.unlink()
                else:
                    for f in d.iterdir():
                        if f.is_file():
                            f.unlink()
        log.info(f"缓存已清除{' ('+code+')' if code else ''}")

    def list_cached(self) -> dict:
        """列出缓存"""
        return self.storage.list_cached()


# ======================== CLI ========================

def cli():
    import argparse
    
    parser = argparse.ArgumentParser(description="StockAnalyst — A股数据分析系统")
    parser.add_argument("command", nargs="?", default="help",
                       choices=["kline", "financial", "analyze", "batch", "plot", "realtime", "cache"])
    parser.add_argument("codes", nargs="*", help="股票代码")
    parser.add_argument("--days", type=int, default=120, help="K线天数")
    parser.add_argument("--name", default="", help="股票名称")
    parser.add_argument("--freq", default="1min", help="聚合频率")
    
    args = parser.parse_args()
    sa = StockAnalyst()
    
    if args.command == "help":
        print("StockAnalyst 命令:")
        print("  kline <code> [--days N]           获取K线")
        print("  financial <code>                  获取财务摘要")
        print("  analyze <code> [--name NAME]      综合分析")
        print("  batch <code1> <code2> ...         批量分析")
        print("  plot <code> [--days N]            绘制K线图")
        print("  realtime <code1> <code2> ...      实时快照")
        print("  cache [code]                      缓存信息/清除")
    
    elif args.command == "kline":
        for code in args.codes:
            df = sa.get_kline(code, args.days)
            if not df.empty:
                print(f"\n{code} 近{args.days}日K线 ({len(df)}条):")
                print(df.tail(10)[['日期','开盘','收盘','最高','最低','成交量']].to_string())

    elif args.command == "financial":
        for code in args.codes:
            df = sa.get_financial_summary(code)
            if not df.empty:
                cols = ['报告期','营业总收入','净利润','销售净利率','销售毛利率','净资产收益率','资产负债率']
                cols = [c for c in cols if c in df.columns]
                print(f"\n{code} 财务摘要:")
                print(df[cols].tail(8).to_string())

    elif args.command == "analyze":
        for code in args.codes:
            r = sa.analyze(code, args.name)
            print(f"\n{r['summary']}")

    elif args.command == "batch":
        if args.codes:
            df = sa.batch_analyze(args.codes)
            print(df.to_string())

    elif args.command == "plot":
        for code in args.codes:
            path = sa.plot_kline(code, args.days)
            print(f"K线图: {path}")

    elif args.command == "realtime":
        if args.codes:
            data = sa.get_realtime(args.codes)
            for d in data:
                print(f"{d['code']}: 价格={d.get('price','-')} 涨跌={d.get('change_pct',0):+.2f}%")

    elif args.command == "cache":
        if args.codes:
            sa.clear_cache(args.codes[0])
        else:
            info = sa.list_cached()
            for dtype, codes in info.items():
                print(f"  {dtype}: {len(codes)} 只缓存")


if __name__ == "__main__":
    cli()
