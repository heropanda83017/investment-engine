"""
deep_analysis.py — 完整投资分析框架
含行业分类/量价分析/18框架/芒格思维/逆向排除
"""
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

logger = logging.getLogger("deep_analysis")
CACHE = Path(__file__).resolve().parent.parent / "_cache" / "analysis"
CACHE.mkdir(parents=True, exist_ok=True)

_INDUSTRY_CACHE = None

def _load_industries():
    global _INDUSTRY_CACHE
    if _INDUSTRY_CACHE is not None:
        return _INDUSTRY_CACHE
    
    m = {}
    cache_file = CACHE / "industry_cache.json"
    
    # Tier 1: baostock (fastest, ~30ms)
    try:
        import baostock as bs
        bs.login()
        try:
            rs = bs.query_stock_industry()
            while rs.next():
                row = rs.get_row_data()
                if len(row) >= 4 and row[3]:
                    m[row[1]] = row[3]
            if m:
                logger.info(f"[industry] baostock loaded {len(m)} industries")
        finally:
            bs.logout()
    except:
        logger.warning("[industry] baostock failed")
    
    # Tier 2: tushare fallback (5523 stocks with industry)
    if not m:
        try:
            import tushare as ts
            pro = ts.pro_api()
            df = pro.stock_basic(exchange='', list_status='L',
                                 fields='ts_code,symbol,name,industry')
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    ind = r.get('industry', '')
                    if ind and str(ind) != 'nan' and str(ind).strip():
                        ts_code = str(r['ts_code'])
                        sym, exch = ts_code.split('.')
                        bs_key = f"{exch.lower()}.{sym}"
                        m[bs_key] = str(ind).strip()
                logger.info(f"[industry] tushare fallback loaded {len(m)} industries")
        except:
            logger.warning("[industry] tushare fallback failed")
    
    # Tier 3: local cache
    if not m and cache_file.exists():
        try:
            import json
            with open(cache_file, 'r', encoding='utf-8') as f:
                m = json.load(f)
            logger.info(f"[industry] cache loaded {len(m)} industries")
        except:
            pass
    
    # Save to cache if we got data from network
    if m and not cache_file.exists():
        try:
            import json
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(m, f, ensure_ascii=False)
            logger.info(f"[industry] saved {len(m)} industries to cache")
        except:
            pass
    
    _INDUSTRY_CACHE = m
    return _INDUSTRY_CACHE

def get_industry(code):
    bs_code = "sh." + code if code.startswith(("6","9")) else "sz." + code
    return _load_industries().get(bs_code, "")

def _get_financials(code, ol):
    try:
        fin = ol.get_financial(code)
        if fin is not None and not fin.empty:
            row = fin.iloc[-1]
            def _safe_float(key):
                v = row.get(key)
                return float(v if pd.notna(v) else 0)
            return {
                "debt_ratio": _safe_float("资产负债率"),
                "roe_ttm": _safe_float("净资产收益率"),
                "gross_margin": _safe_float("销售毛利率"),
                "net_margin": _safe_float("销售净利率"),
                "net_profit": _safe_float("净利润"),
                "eps_ttm": _safe_float("每股收益TTM"),
                "revenue": _safe_float("营业总收入"),
            }
    except:
        pass
    return {}

def _get_market_data(ol):
    m = {"pmi": 49.5, "credit_growth": 8.5, "rate_trend": "stable", "pe_percentile": 50}
    try:
        k = ol.get_kline("000001.SH", days=120)
        if k is not None and not k.empty:
            c = k.get("close") or k.get("收盘")
            if c is not None and len(c) > 0:
                cur = float(c.iloc[-1])
                m["pe_percentile"] = int(sum(1 for v in c if v <= cur) / len(c) * 100)
    except:
        pass
    return m

def _volume_price_analysis(kline):
    if kline is None or kline.empty:
        return {}
    try:
        c = kline.get("close") if kline is not None else None
        if c is None:
            c = kline.get("收盘")
        v = kline.get("volume") if kline is not None else None
        if v is None:
            v = kline.get("成交量")
        if c is None or v is None or len(c) < 20:
            return {}
        c = c.astype(float)
        v = v.astype(float)
        ret = (c.iloc[-1] / c.iloc[-20] - 1) * 100
        v_ratio = v.iloc[-5:].mean() / v.iloc[-20:-5].mean() if v.iloc[-20:-5].mean() > 0 else 1
        stage = "unknown"
        if ret > 15 and v_ratio < 0.8:
            stage = "\u26a0\ufe0f 派发(量价背离)"
        elif ret > 10 and v_ratio > 1.3:
            stage = "\u2764\ufe0f 公众参与(主升)"
        elif ret > 5 and v_ratio > 1.1:
            stage = "\u25b6 吸筹减速"
        elif ret < -5 and v_ratio > 1.3:
            stage = "\U0001f4a5 恐慌抛售"
        else:
            stage = "\u632f\u8361"
        return {"return_20d": round(ret, 1), "vol_ratio": round(v_ratio, 2), "stage": stage}
    except:
        return {}

def _reverse_check(code, name, industry):
    checks = []
    checks.append("\u9006\u5411\u95ee\u98981: \u5047\u8bbe2\u5e74\u5185\u7834\u4ea7,\u6700\u53ef\u80fd\u539f\u56e0?")
    if "\u96f6\u552e" in industry and "\u7535\u5546" not in industry:
        checks.append("  -> \u4f20\u7edf\u96f6\u552e\u6301\u7eed\u840e\u7f29,\u88ab\u7535\u5546\u66ff\u4ee3 -> \u7ed3\u6784\u5931\u610f,\u96be\u4ee5\u7ffb\u8eab")
    elif "\u623f\u5730\u4ea7" in industry:
        checks.append("  -> \u884c\u4e1a\u5468\u671f\u4e0b\u884c,\u9ad8\u67a0\u6746\u98ce\u9669 -> \u5468\u671f\u5931\u610f,\u7b49\u5f85\u53cd\u8f6c")
    elif "\u94f6\u884c" in industry:
        checks.append("  -> \u4fe1\u7528\u98ce\u9669\u66b4\u9732,\u51c0\u606f\u5dee\u6536\u7a84 -> \u7cfb\u7edf\u6027\u98ce\u9669")
    else:
        checks.append("  -> \u65e0\u660e\u663e\u7ed3\u6784\u6027\u98ce\u9669,\u9700\u6301\u7eed\u8ddf\u8e2a")
    checks.append("\u9006\u5411\u95ee\u98982: \u5047\u8bbe\u4e70\u5165\u903b\u8f91\u5b8c\u5168\u9519\u4e86,\u6700\u53ef\u80fd\u9519\u5728\u54ea?")
    checks.append("  -> \u8d8b\u52bf\u5ef6\u7eed\u5047\u8bbe\u53ef\u80fd\u88ab\u7a81\u53d1\u4e8b\u4ef6\u6253\u65ad")
    checks.append("\u9006\u5411\u95ee\u98983: \u5982\u679c\u4eca\u5929\u7a7a\u4ed3,\u8fd8\u613f\u610f\u5728\u8fd9\u4e2a\u4ef7\u683c\u4e70\u5165\u5417?")
    checks.append("  -> \u9700\u7ed3\u5408\u4f30\u503c\u548c\u5b89\u5168\u8fb9\u9645\u5224\u65ad")
    return checks

def _munger_analysis(code, name, industry, vp, fw_scores, fin):
    views = []
    ret = vp.get("return_20d", 0)
    if ret:
        mo = "\u6570\u5b66: 20\u65e5\u6da8\u5e45" + str(ret) + "%"
        if abs(ret) > 20:
            mo += ", \u8b66\u60d5\u5747\u503c\u56de\u5f52"
        views.append(mo)
    bf = fw_scores.get("\u884c\u4e3a\u91d1\u878d", {}).get("score", 5)
    if bf < 5:
        views.append("\u5fc3\u7406: \u884c\u4e3a\u91d1\u878d" + str(bf) + "\u5206,\u5b58\u5728\u8ba4\u77e5\u504f\u5dee\u98ce\u9669")
    else:
        views.append("\u5fc3\u7406: \u884c\u4e3a\u91d1\u878d" + str(bf) + "\u5206,\u65e0\u660e\u663e\u504f\u5dee")
    if industry:
        views.append("\u5386\u53f2: " + industry + ", \u9700\u7814\u7a76\u884c\u4e1a\u751f\u547d\u5468\u671f\u9636\u6bb5")
    roe = fin.get("roe_ttm", 0)
    if roe > 15:
        views.append("\u751f\u7269: ROE" + str(roe) + "%,\u62a4\u57ce\u6cb3\u8f83\u5bbd")
    elif roe > 8:
        views.append("\u751f\u7269: ROE" + str(roe) + "%,\u6709\u4e00\u5b9a\u7684\u7ade\u4e89\u529b")
    else:
        views.append("\u751f\u7269: ROE" + str(roe) + "%,\u7ade\u4e89\u4f18\u52bf\u5f85\u9a8c\u8bc1")
    return views

def analyze_stock_full(code, name, ol):
    from analysis_frameworks import apply_all_frameworks
    industry = get_industry(code)
    kline = ol.get_kline(code, days=60) if ol else None
    fin = _get_financials(code, ol)
    market = _get_market_data(ol)
    fw = apply_all_frameworks(df=kline, stock_name=name, code=code,
        industry=industry, financials=fin, market_data=market)
    vp = _volume_price_analysis(kline)
    rc = _reverse_check(code, name, industry)
    munger = _munger_analysis(code, name, industry, vp, fw.get("framework_scores", {}), fin)
    return {
        "code": code, "name": name,
        "industry": industry[:30] if industry else "\u672a\u77e5",
        "total_score": fw.get("total_score", 0),
        "hard_reject": fw.get("hard_reject", False),
        "frameworks": fw.get("framework_scores", {}),
        "signals": fw.get("signal_summary", {}),
        "volume_price": vp,
        "reverse_checks": rc,
        "munger": munger,
        "financials": fin,
    }



def get_framework_scores(code: str) -> dict:
    """返回某只股票的各框架评分摘要，供 signal_generator 使用
    直接使用 data_optimizer 替代 data_provider（避免长依赖链）
    
    Returns
    -------
    dict:
        composite: float  -1~1  框架综合评分
        hard_reject: bool        是否硬拒绝
        vp_stage: str            量价阶段(吸筹/公众参与/派发)
        moat_score: float        护城河评分
        behavioral_bias: int     行为偏误数
        reverse_flags: int       逆向排除标记数
        adjustment: float        -0.15~0.15 信号调分系数
    """
    try:
        from scripts.data_optimizer import OptimizedDataLayer
        ol = OptimizedDataLayer()
        result = analyze_stock_full(code, "", ol)
        fw = result.get("frameworks", {})
        vp = result.get("volume_price", {})
        rc = result.get("reverse_checks", [])
        
        try:
            from strategies.framework_scorer import score_all_frameworks
            scored = score_all_frameworks(fw)
            composite = scored.get("composite", 0.0)
        except Exception:
            composite = 0.0
        
        hard_reject = result.get("hard_reject", False)
        vp_stage = vp.get("stage", "未知")
        behavioral_bias = len(fw.get("行为金融", {}).get("biases", [])) if "行为金融" in fw else 0
        reverse_flags = len(rc)
        
        adj = composite * 0.10
        if hard_reject:
            adj = -0.15
        if vp_stage == "派发":
            adj -= 0.05
        elif vp_stage == "吸筹":
            adj += 0.03
        if reverse_flags > 2:
            adj -= 0.05
        adjustment = max(-0.15, min(0.15, adj))
        
        return {
            "composite": round(composite, 3),
            "hard_reject": hard_reject,
            "vp_stage": vp_stage,
            "moat_score": round(fw.get("护城河", {}).get("total_score", 0) if "护城河" in fw else 0, 1),
            "behavioral_bias": behavioral_bias,
            "reverse_flags": reverse_flags,
            "adjustment": round(adjustment, 3),
        }
    except Exception as e:
        logger.warning(f"[framework] get_framework_scores({code}) failed: {e}")
        return {"composite": 0.0, "hard_reject": False, "vp_stage": "未知",
                "moat_score": 0.0, "behavioral_bias": 0, "reverse_flags": 0, "adjustment": 0.0}

def generate_deep_report(rank_df, stock_names, top_n=5):
    from strategies.data_provider import get_provider
    ol = get_provider()
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    out.append("# \u6df1\u5ea6\u6295\u8d44\u5206\u6790\u62a5\u544a | " + today)
    out.append("> \u8292\u683c\u591a\u5143\u601d\u7ef4 + \u9006\u5411\u6392\u9664 + 18\u6846\u67b6 + \u91cf\u4ef7\u5206\u6790")
    
    # 校验列名
    code_col = "code" if "code" in rank_df.columns else ("stock_code" if "stock_code" in rank_df.columns else None)
    score_col = "total" if "total" in rank_df.columns else ("score" if "score" in rank_df.columns else None)
    if code_col is None or score_col is None:
        return "# \u62a5\u544a\u751f\u6210\u5931\u8d25: \u65e0\u6548\u5217\u540d\n"
    
    for i in range(min(top_n, len(rank_df))):
        row = rank_df.iloc[i]
        c = str(int(row[code_col])).zfill(6)
        n = stock_names.get(c, "?")
        a = analyze_stock_full(c, n, ol)
        out.append("---")
        out.append("## " + str(i+1) + ". " + n + " (" + c + ") | " + str(round(row.get(score_col, 0), 1)))
        out.append("")
        out.append("\u884c\u4e1a: " + a["industry"])
        vp = a.get("volume_price", {})
        if vp:
            out.append("### \u91cf\u4ef7\u5206\u6790(\u9053\u6c0f)")
            out.append("- 20\u65e5: " + str(vp.get("return_20d", "?")) + "% | \u91cf\u6bd4: " + str(vp.get("vol_ratio", "?")))
            out.append("- \u9636\u6bb5: " + vp.get("stage", "\u672a\u77e5"))
        fin = a.get("financials", {})
        if fin:
            out.append("### \u8d22\u52a1\u5feb\u7167")
            out.append("- ROE: " + str(fin.get("roe_ttm",0)) + "% | \u6bdb\u5229\u7387: " + str(fin.get("gross_margin",0)) + "%")
            out.append("- \u8d1f\u503a\u7387: " + str(fin.get("debt_ratio",0)) + "% | EPS: " + str(fin.get("eps_ttm",0)))
        out.append("### 18\u6846\u67b6\u8bc4\u5206")
        for fn, fs in sorted(a.get("frameworks", {}).items()):
            if isinstance(fs, dict):
                s = str(fs.get("score", "-"))
                sigs = "; ".join([x.get("msg","")[:40] for x in fs.get("signals",[])[:2]]) if fs.get("signals") else ""
                out.append("- " + fn + ": " + s + (" | " + sigs if sigs else ""))
        # -- Framework Scoring Standardization --
        try:
            from framework_scorer import score_all_frameworks, format_score_summary
            scored = score_all_frameworks(a.get("frameworks", {}))
            summary = format_score_summary(scored)
            for line in summary.split("\n"):
                out.append("  " + line)
        except Exception:
            pass
        m = a.get("munger", [])
        if m:
            out.append("### \u8292\u683c\u591a\u5143\u601d\u7ef4")
            for line in m:
                out.append("- " + line)
        rcs = a.get("reverse_checks", [])
        if rcs:
            out.append("### \u9006\u5411\u6392\u9664")
            for r in rcs:
                out.append("- " + r)
        sigs = a.get("signals", {})
        if sigs and isinstance(sigs, dict):
            for k, vlist in sigs.items():
                if vlist:
                    for v in vlist[:2]:
                        msg = v.get("msg", str(v)) if isinstance(v, dict) else str(v)
                        out.append("- [" + k + "] " + str(msg)[:60])
        if a.get("hard_reject"):
            out.append("> HARD REJECT")
    report = "\n".join(out)
    rp = CACHE / ("deep_report_" + datetime.now().strftime("%Y%m%d") + ".md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("\u6df1\u5ea6\u62a5\u544a\u5df2\u4fdd\u5b58: " + str(rp))
    return report
