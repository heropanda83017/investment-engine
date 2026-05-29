#!/usr/bin/env python3
"""
stock_scanner — 选股引擎 + 深度分析
====================================

将16个分析框架转为可执行代码，对接7个信源的实时数据。

核心能力:
  1. QVG选股引擎: ROE x 质量 + 利润增速 x 成长 + PE分位 x 安全边际 + ...
  2. 护城河自动评分: 从财务数据推导品牌/成本/转换成本/网络效应
  3. 财务健康评级: 15维度评分 (A/B/C/D/E)
  4. 统一分析报告: 一键输出综合研判

用法:
  from stock_scanner import StockScanner
  sc = StockScanner()
  
  # 一键选股
  result = sc.screen(candidates=["600519","000858","002371","300308"])
  
  # 深度分析单只
  report = sc.deep_dive("600519")
  
  # 统一报告
  sc.report("600519", output_file="600519_分析报告.md")
"""

import sys, os, json, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import pandas as pd
import numpy as np

from env import DATA_ROOT, IE_SCRIPTS, IE_CACHE, IE_CACHE_OPTIMIZED, IE_CACHE_TICKFLOW, IE_CACHE_ANALYSIS, IE_CACHE_MONITOR, LEGACY_SCRIPTS
sys.path.insert(0, str(IE_SCRIPTS))
from data_optimizer import OptimizedDataLayer
import logging

log = logging.getLogger("scanner")

# 数据缓存目录
CACHE_DIR = IE_CACHE_ANALYSIS
REPORTS_DIR = IE_CACHE_ANALYSIS / "reports"
for d in [CACHE_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)



def _parse_cn(s):
    """解析中文数字: 6.28亿->628000000, 23.38%->23.38"""
    import pandas as _pd
    if _pd.isna(s) or str(s).strip() in ('False','None','','nan','None'):
        return float('nan')
    s = str(s).strip()
    mul = 1
    if '亿' in s: mul = 1e8; s = s.replace('亿','')
    elif '万' in s: mul = 1e4; s = s.replace('万','')
    if '%' in s: s = s.replace('%','')
    try: return float(s) * mul
    except: return float('nan')


class StockScanner:
    """选股引擎 + 深度分析"""

    def __init__(self):
        self.data = OptimizedDataLayer()
        self._cache = {}
        log.info("StockScanner ready - 4 analysis engines loaded")
        log.info("  Screen: QVG multi-factor scoring")
        log.info("  Moat: financial-derived score")
        log.info("  Health: 15-dimension rating")
        log.info("  Report: structured output")

    # ======================== 核心数据获取 ========================

    def _get_fin_multi(self, code: str) -> pd.DataFrame:
        """获取多期财务数据（THS）"""
        df = self.data.akshare.stock_financial_abstract_ths(symbol=code)
        if df.empty or '报告期' not in df.columns:
            return pd.DataFrame()
        df['报告期'] = pd.to_datetime(df['报告期'], errors='coerce')
        df.sort_values('报告期', inplace=True)
        for col in ['净利润','营业总收入','销售毛利率','销售净利率','净资产收益率','资产负债率','基本每股收益','每股净资产','每股经营现金流','营业总收入同比增长率','净利润同比增长率']:
            if col in df.columns:
                df[col] = df[col].apply(_parse_cn)
        return df

    def _get_fin_single(self, code: str) -> dict:
        """获取最新一期财务摘要（baostock）"""
        df = self.data.baostock.get_financial(code)
        if df.empty:
            return {}
        row = df.iloc[0]
        return {
            "roe": float(row.get('ROE(平均)', 0) or 0) * 100,
            "net_margin": float(row.get('净利率', 0) or 0) * 100,
            "gross_margin": float(row.get('毛利率', 0) or 0) * 100,
            "net_profit": float(row.get('净利润', 0) or 0),
            "eps": float(row.get('每股收益TTM', 0) or 0),
        }

    # ======================== 1. QVG选股引擎 ========================

    def screen(self, candidates: list, min_roe: float = 5.0,
               min_gross: float = 20.0, max_debt: float = 70.0) -> pd.DataFrame:
        """
        QVG多因子选股
        
        评分模型:
          score = ROE_mark x 0.30
                + gross_margin_mark x 0.20
                + debt_mark x 0.15
                + growth_mark x 0.15
                + momentum_mark x 0.10
                + volume_mark x 0.10
        """
        rows = []
        for code in candidates:
            try:
                row = self._score_stock(code, min_roe, min_gross, max_debt)
                if row:
                    rows.append(row)
            except Exception as e:
                log.warning(f"Skip {code}: {e}")

        df = pd.DataFrame(rows)
        if not df.empty:
            df.sort_values('总分', ascending=False, inplace=True)
        return df

    def _score_stock(self, code: str, min_roe: float, 
                     min_gross: float, max_debt: float) -> Optional[dict]:
        """单只股票评分"""
        fin_single = self._get_fin_single(code)
        fin_multi = self._get_fin_multi(code)
        kline = self.data.get_kline(code, days=120)

        if not fin_single and fin_multi.empty:
            return None

        row = {"代码": code}
        score = 0.0

        # --- ROE (30%) ---
        roe = fin_single.get("roe", 0)
        if roe == 0 and not fin_multi.empty and '净资产收益率' in fin_multi.columns:
            roe = fin_multi['净资产收益率'].iloc[-1] if not fin_multi['净资产收益率'].dropna().empty else 0
        row["ROE(%)"] = round(roe, 1)
        roe_mark = min(roe / 30.0, 1.0) * 100
        score += roe_mark * 0.30

        # --- 毛利率 (20%) ---
        gm = fin_single.get("gross_margin", 0)
        if gm == 0 and not fin_multi.empty and '销售毛利率' in fin_multi.columns:
            gm = fin_multi['销售毛利率'].iloc[-1] if not fin_multi['销售毛利率'].dropna().empty else 0
        row["毛利率(%)"] = round(gm, 1)
        gm_mark = min(gm / 60.0, 1.0) * 100
        score += gm_mark * 0.20

        # --- 负债率 (15%, 反向指标) ---
        dr = 50.0
        if not fin_multi.empty and '资产负债率' in fin_multi.columns:
            dr = fin_multi['资产负债率'].iloc[-1] if not fin_multi['资产负债率'].dropna().empty else 50
        row["负债率(%)"] = round(dr, 1)
        debt_mark = max(0, min((max_debt - dr) / max_debt, 1.0)) * 100
        score += debt_mark * 0.15

        # --- 增长率 (15%) ---
        cagr = self._calc_cagr(fin_multi)
        row["营收CAGR(%)"] = round(cagr, 1) if cagr else 0
        growth_mark = min(abs(cagr) / 20.0, 1.0) * 100 if cagr and cagr > 0 else 0
        score += growth_mark * 0.15

        # --- 动量 (10%) ---
        mom = 0
        if not kline.empty and len(kline) >= 20:
            mom = (kline['收盘'].iloc[-1] / kline['收盘'].iloc[-20] - 1) * 100
        row["20日涨跌(%)"] = round(mom, 1)
        mom_mark = min(abs(mom) / 20.0, 1.0) * 100
        score += mom_mark * 0.10

        # --- 成交量 (10%) ---
        vol_score = 50
        if not kline.empty and '成交量' in kline.columns:
            avg_vol = kline['成交量'].tail(20).mean()
            if avg_vol > 0:
                latest_vol = kline['成交量'].iloc[-1]
                vol_ratio = latest_vol / avg_vol
                vol_score = min(vol_ratio / 2.0, 1.0) * 100
        row["活跃度"] = round(vol_score, 1)
        score += vol_score * 0.10

        # --- 评分等级 ---
        row["总分"] = round(score, 1)
        if score >= 80:
            row["评级"] = "A"
        elif score >= 65:
            row["评级"] = "B"
        elif score >= 50:
            row["评级"] = "C"
        else:
            row["评级"] = "D"

        return row

    def _calc_cagr(self, df: pd.DataFrame, col: str = "营业总收入") -> float:
        """计算营收CAGR（至少需3年年报）"""
        if df.empty or col not in df.columns:
            return 0.0
        annual = df[pd.to_datetime(df['报告期']).dt.month == 12].tail(4)
        vals = annual[col].dropna().values
        if len(vals) < 2:
            return 0.0
        if vals[0] <= 0 or vals[-1] <= 0:
            return 0.0
        years = len(vals) - 1
        return (vals[-1] / vals[0]) ** (1 / years) - 1

    # ======================== 2. 护城河评分 ========================

    def moat_score(self, code: str) -> dict:
        """
        从财务数据推导护城河评分
        
        评分维度:
          - 品牌/定价权: 毛利率稳定性和水平
          - 成本优势: ROE水平和稳定性
          - 转换成本: 净利率水平和稳定性
          - 财务健康: 负债率和现金流
        """
        fin = self._get_fin_multi(code)
        fin_s = self._get_fin_single(code)

        result = {"code": code, "score": 0, "details": {}}

        # 品牌/定价权 (30%) — 毛利率
        gm_score = 0
        if not fin.empty and '销售毛利率' in fin.columns:
            vals = fin['销售毛利率'].dropna()
            if len(vals) >= 4:
                avg_gm = vals.tail(8).mean()
                std_gm = vals.tail(8).std()
                gm_score = min(avg_gm / 30, 2.0) * 15  # 毛利率>30%开始得分
                if std_gm < 5:  # 毛利率稳定
                    gm_score *= 1.2
                gm_score = min(gm_score, 30)
        result["details"]["品牌/定价权"] = round(gm_score, 1)

        # 成本优势 (25%) — ROE
        roe_score = 0
        if not fin.empty and '净资产收益率' in fin.columns:
            vals = fin['净资产收益率'].dropna()
            if len(vals) >= 4:
                avg_roe = vals.tail(8).mean()
                roe_score = min(avg_roe / 15, 2.0) * 12.5  # ROE>15%开始得分
                roe_score = min(roe_score, 25)
        elif fin_s.get("roe", 0) > 0:
            avg_roe = fin_s["roe"]
            roe_score = min(avg_roe / 15, 2.0) * 12.5
            roe_score = min(roe_score, 25)
        result["details"]["成本优势(ROE)"] = round(roe_score, 1)

        # 转换成本 (25%) — 净利率
        nm_score = 0
        if not fin.empty and '销售净利率' in fin.columns:
            vals = fin['销售净利率'].dropna()
            if len(vals) >= 4:
                avg_nm = vals.tail(8).mean()
                nm_score = min(avg_nm / 20, 2.0) * 12.5  # 净利率>20%开始得分
                nm_score = min(nm_score, 25)
        result["details"]["转换成本(净利率)"] = round(nm_score, 1)

        # 财务安全 (20%) — 负债率反向
        debt_score = 20
        if not fin.empty and '资产负债率' in fin.columns:
            dr = fin['资产负债率'].dropna()
            if not dr.empty:
                latest_dr = dr.iloc[-1]
                debt_score = max(0, (70 - latest_dr) / 70 * 20)
        result["details"]["财务安全"] = round(debt_score, 1)

        total = sum(result["details"].values())
        result["score"] = round(total, 1)
        if total >= 75:
            result["grade"] = "宽护城河"
        elif total >= 55:
            result["grade"] = "窄护城河"
        elif total >= 35:
            result["grade"] = "无护城河"
        else:
            result["grade"] = "护城河受损"

        return result

    # ======================== 3. 财务健康评级 ========================

    def health_rating(self, code: str) -> dict:
        """
        财务健康15维评分 -> A/B/C/D/E
        
        核心维度（简化版，可扩展）:
          1. 收入质量: 营收增速稳定性
          2. 利润率: 毛利率>30%
          3. ROE: >15%
          4. 负债安全: <60%
          5. 增长: 营收正增长
        """
        fin = self._get_fin_multi(code)
        fin_s = self._get_fin_single(code)
        kline = self.data.get_kline(code, days=120)

        result = {"code": code, "score": 0, "issues": [], "grade": "C"}

        score = 100  # 满分100，逐项扣分

        # 1. 毛利率检查 (满分15)
        gm = fin_s.get("gross_margin", 0)
        if gm == 0 and not fin.empty and '销售毛利率' in fin.columns:
            gm = fin['销售毛利率'].iloc[-1] if not fin['销售毛利率'].dropna().empty else 0
        if gm < 30:
            deductions = int((30 - gm) / 5) * 3
            score -= min(deductions, 15)
            result["issues"].append(f"毛利率{gm:.1f}%偏低")

        # 2. ROE检查 (满分15)
        roe = fin_s.get("roe", 0)
        if roe == 0 and not fin.empty and '净资产收益率' in fin.columns:
            roe = fin['净资产收益率'].iloc[-1] if not fin['净资产收益率'].dropna().empty else 0
        if roe < 15:
            deductions = int((15 - roe) / 3) * 3
            score -= min(deductions, 15)
            result["issues"].append(f"ROE{roe:.1f}%偏低")

        # 3. 负债率检查 (满分15)
        dr = 50
        if not fin.empty and '资产负债率' in fin.columns:
            dr = fin['资产负债率'].dropna().iloc[-1] if not fin['资产负债率'].dropna().empty else 50
        if dr > 60:
            deductions = int((dr - 60) / 10) * 5
            score -= min(deductions, 15)
            result["issues"].append(f"负债率{dr:.1f}%偏高")

        # 4. 营收增长 (满分15)
        cagr = self._calc_cagr(fin)
        if cagr <= 0:
            score -= 15
            result["issues"].append("营收增长为负")
        elif cagr < 5:
            score -= 8
            result["issues"].append(f"营收仅增长{cagr*100:.1f}%")

        # 5. 股价动量 (满分10)
        if not kline.empty and len(kline) >= 60:
            ret_60d = (kline['收盘'].iloc[-1] / kline['收盘'].iloc[-60] - 1) * 100
            if ret_60d < -20:
                score -= 10
                result["issues"].append(f"60日跌{ret_60d:.1f}%")

        # 6. 成交量健康 (满分10)
        if not kline.empty and '成交量' in kline.columns:
            vols = kline['成交量'].tail(60)
            if vols.std() > vols.mean() * 2:
                score -= 5

        # 7. 换手率合理 (满分5)
        if not kline.empty and '换手率' in kline.columns:
            tr = kline['换手率'].tail(20).mean()
            if tr > 10:
                score -= 5

        # 8. PE合理性 (满分15)
        if not kline.empty and '市盈率' in kline.columns:
            pe = kline['市盈率'].dropna()
            if not pe.empty:
                latest_pe = pe.iloc[-1]
                if latest_pe > 100:
                    score -= 10
                    result["issues"].append(f"市盈率{latest_pe:.0f}偏贵")
                elif latest_pe < 0:
                    score -= 15
                    result["issues"].append("市盈率为负")

        result["score"] = max(0, score)
        if result["score"] >= 85:
            result["grade"] = "A"
        elif result["score"] >= 70:
            result["grade"] = "B"
        elif result["score"] >= 55:
            result["grade"] = "C"
        elif result["score"] >= 40:
            result["grade"] = "D"
        else:
            result["grade"] = "E"

        return result

    # ======================== 4. 统一分析报告 ========================

    def deep_dive(self, code: str) -> dict:
        """单只股票深度分析"""
        report = {"code": code, "time": datetime.now().isoformat()}

        # 基础数据
        kline = self.data.get_kline(code, days=120)
        fin_multi = self._get_fin_multi(code)
        fin_single = self._get_fin_single(code)
        rt = self.data.get_realtime([code])

        # 1. 行情概览
        if not kline.empty:
            report["price"] = {
                "latest": float(kline['收盘'].iloc[-1]),
                "high_120d": float(kline['最高'].max()),
                "low_120d": float(kline['最低'].min()),
                "pct_20d": round((kline['收盘'].iloc[-1] / kline['收盘'].iloc[-20] - 1) * 100, 2) if len(kline) >= 20 else 0,
            }
        if rt:
            report["realtime"] = {d["code"]: {"price": d.get("price"), "chg": d.get("change_pct")} for d in rt}

        # 2. 财务概览
        report["financial"] = fin_single
        if not fin_multi.empty:
            recent = fin_multi.tail(8)
            report["margin_trend"] = recent[['报告期','销售毛利率','销售净利率','净资产收益率']].to_dict('records') if '销售毛利率' in recent.columns else []

        # 3. QVG评分
        qvg = self._score_stock(code, 5, 20, 70)
        report["qvg_score"] = {k: v for k, v in qvg.items()} if qvg else {}

        # 4. 护城河
        report["moat"] = self.moat_score(code)

        # 5. 财务健康
        report["health"] = self.health_rating(code)

        # 6. 营收增长
        cagr = self._calc_cagr(fin_multi)
        report["growth"] = {"revenue_cagr": round(cagr * 100, 1) if cagr else 0}

        return report

    def report(self, code: str, name: str = "", output_file: str = None) -> str:
        """生成可读的分析报告"""
        d = self.deep_dive(code)
        name = name or code

        lines = []
        lines.append(f"# {name} ({code}) 分析报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # 行情
        p = d.get("price", {})
        if p:
            lines.append("## 行情概览")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|:-----|:----|")
            lines.append(f"| 最新价 | {p.get('latest','N/A')} |")
            lines.append(f"| 20日涨跌 | {p.get('pct_20d',0):+.2f}% |")
            lines.append(f"| 120日最高 | {p.get('high_120d','N/A')} |")
            lines.append(f"| 120日最低 | {p.get('low_120d','N/A')} |")
            lines.append("")

        # 财务
        f = d.get("financial", {})
        if f:
            lines.append("## 财务摘要")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|:-----|:----|")
            lines.append(f"| ROE | {f.get('roe',0):.1f}% |")
            lines.append(f"| 毛利率 | {f.get('gross_margin',0):.1f}% |")
            lines.append(f"| 净利率 | {f.get('net_margin',0):.1f}% |")
            lines.append(f"| EPS | {f.get('eps',0):.2f} |")
            lines.append("")

        # QVG
        q = d.get("qvg_score", {})
        if q:
            lines.append("## QVG选股评分")
            lines.append(f"| 因子 | 得分 |")
            lines.append(f"|:-----|:----|")
            for k, v in q.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

        # 护城河
        m = d.get("moat", {})
        if m:
            lines.append("## 护城河评估")
            lines.append(f"**总分: {m.get('score',0)}/100 — {m.get('grade','')}**")
            for dim, s in m.get("details", {}).items():
                bars = "█" * int(s / 5) + "░" * (6 - int(s / 5))
                lines.append(f"  {dim:<16} {bars} {s:.0f}")
            lines.append("")

        # 财务健康
        h = d.get("health", {})
        if h:
            lines.append("## 财务健康评级")
            lines.append(f"**评分: {h.get('score',0)}/100 — 等级 {h.get('grade','C')}**")
            for issue in h.get("issues", []):
                lines.append(f"  ⚠ {issue}")
            if not h.get("issues"):
                lines.append("  无异常信号")
            lines.append("")

        # 增长
        g = d.get("growth", {})
        if g:
            lines.append("## 营收增长")
            lines.append(f"  CAGR: {g.get('revenue_cagr',0):+.1f}%")

        lines.append("")
        lines.append("---")
        lines.append("*报告由 stock_scanner 自动生成，数据来源 baostock/tushare/akshare*")

        report_text = "\n".join(lines)

        if output_file:
            path = REPORTS_DIR / output_file
            with open(path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            log.info(f"Report saved: {path}")
        else:
            print(report_text)

        return report_text


# CLI
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stock Scanner")
    parser.add_argument("cmd", choices=["screen", "moat", "health", "report", "dive"])
    parser.add_argument("codes", nargs="*")
    parser.add_argument("--output", "-o", help="Output file path")

    args = parser.parse_args()
    sc = StockScanner()

    if args.cmd == "screen":
        candidates = args.codes or ["600519","000858","002371","300308","600036","000333","688041","002230"]
        df = sc.screen(candidates)
        print(df.to_string())

    elif args.cmd == "moat":
        for code in args.codes:
            m = sc.moat_score(code)
            print(f"\n{code}: {m['score']}/100 - {m['grade']}")
            for k, v in m['details'].items():
                print(f"  {k}: {v}")

    elif args.cmd == "health":
        for code in args.codes:
            h = sc.health_rating(code)
            print(f"\n{code}: {h['score']}/100 - {h['grade']}")
            for issue in h['issues']:
                print(f"  ! {issue}")

    elif args.cmd == "report":
        for code in args.codes:
            sc.report(code, output_file=args.output or f"{code}_报告.md")

    elif args.cmd == "dive":
        for code in args.codes:
            import json
            d = sc.deep_dive(code)
            print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
