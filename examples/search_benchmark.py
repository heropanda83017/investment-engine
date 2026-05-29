#!/usr/bin/env python3
"""
AnySearch vs DuckDuckGo vs web_extract 多通道搜索质量对比测试
Phase 0 Pilot — 验证连通性、响应格式、基本质量
输出: 结构化对比报告到 ${AIGC_DATA_ROOT:-E:/AIGC-KB/output}/02-投资研究/
"""

import sys, os, json, time, urllib.request
from pathlib import Path
from datetime import datetime
from typing import Dict

RESULT_DIR = Path("${AIGC_DATA_ROOT:-E:/AIGC-KB/output}/02-投资研究")

TEST_QUERIES = {
    "fact_en": {"query": "AAPL Q2 2026 earnings revenue", "lang": "en", "type": "fact"},
    "fact_cn": {"query": "贵州茅台 2026年一季度 营收净利润", "lang": "cn", "type": "fact"},
    "news_en": {"query": "NVIDIA latest news May 2026", "lang": "en", "type": "news"},
    "analysis_en": {"query": "Fed interest rate decision June 2026 impact", "lang": "en", "type": "analysis"},
    "sector_cn": {"query": "新能源汽车 销量数据 2026年5月", "lang": "cn", "type": "sector"},
}

TEST_URLS = [
    "https://en.wikipedia.org/wiki/Apple_Inc.",
    "https://www.investopedia.com/",
]

class SearchBenchmark:
    def __init__(self):
        self.results: Dict = {}
    
    def anysearch_search(self, query, max_results=5):
        start = time.time()
        try:
            payload = json.dumps({
                "method": "tools/call",
                "params": {"name": "search", "arguments": {"query": query, "max_results": max_results}}
            }).encode()
            req = urllib.request.Request(
                "https://api.anysearch.com/mcp", data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            latency = round((time.time() - start) * 1000)
            return {"channel": "anysearch", "status": "ok", "latency_ms": latency, "raw_raw": str(data)[:2000]}
        except Exception as e:
            return {"channel": "anysearch", "status": "error", "error": str(e),
                    "latency_ms": round((time.time() - start) * 1000)}
    
    def anysearch_extract(self, url):
        start = time.time()
        try:
            payload = json.dumps({
                "method": "tools/call",
                "params": {"name": "extract", "arguments": {"url": url}}
            }).encode()
            req = urllib.request.Request(
                "https://api.anysearch.com/mcp", data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=20)
            data = json.loads(resp.read().decode("utf-8"))
            latency = round((time.time() - start) * 1000)
            cl = len(str(data))
            return {"channel": "anysearch_extract", "status": "ok", "latency_ms": latency,
                    "content_length": cl, "raw_raw": str(data)[:1000]}
        except Exception as e:
            return {"channel": "anysearch_extract", "status": "error", "error": str(e),
                    "latency_ms": round((time.time() - start) * 1000)}
    
    def duckduckgo_search(self, query, max_results=5):
        start = time.time()
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                region = "cn-zh" if any(c > "\u4e00" for c in query) else "wt-wt"
                results = list(ddgs.text(query, region=region, max_results=max_results))
            latency = round((time.time() - start) * 1000)
            return {"channel": "duckduckgo", "status": "ok", "latency_ms": latency, "results": results}
        except Exception as e:
            return {"channel": "duckduckgo", "status": "error", "error": str(e),
                    "latency_ms": round((time.time() - start) * 1000)}
    
    def web_extract_direct(self, url):
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            content = resp.read()
            cl = len(content)
            latency = round((time.time() - start) * 1000)
            return {"channel": "web_extract", "status": "ok", "latency_ms": latency,
                    "content_length": cl, "preview": content[:200].decode("utf-8", errors="replace")}
        except Exception as e:
            return {"channel": "web_extract", "status": "error", "error": str(e),
                    "latency_ms": round((time.time() - start) * 1000)}
    
    def run_all(self):
        print("=" * 60)
        print("Phase 0: AnySearch vs DuckDuckGo 搜索质量对比")
        print("=" * 60)
        
        search_results = []
        for key, q in TEST_QUERIES.items():
            print(f"\n[{key}] {q['query']}")
            a = self.anysearch_search(q["query"])
            d = self.duckduckgo_search(q["query"])
            search_results.append({"key": key, **q, "anysearch": a, "duckduckgo": d})
            as_ok = "+" if a["status"] == "ok" else "X"
            ddg_ok = "+" if d["status"] == "ok" else "X"
            print(f"  AnySearch [{as_ok}] {a.get('latency_ms',0)}ms")
            print(f"  DDG       [{ddg_ok}] {d.get('latency_ms',0)}ms")
        
        print("\n" + "=" * 60)
        print("内容提取对比: AnySearch extract vs web_extract")
        print("=" * 60)
        
        extract_results = []
        for url in TEST_URLS:
            print(f"\n{url}")
            a = self.anysearch_extract(url)
            w = self.web_extract_direct(url)
            extract_results.append({"url": url, "anysearch": a, "web_extract": w})
            as_ok = "+" if a["status"] == "ok" else "X"
            w_ok = "+" if w["status"] == "ok" else "X"
            as_len = a.get("content_length", 0) if a["status"] == "ok" else 0
            w_len = w.get("content_length", 0) if w["status"] == "ok" else 0
            print(f"  AnySearch [{as_ok}] {a.get('latency_ms',0)}ms ({as_len}B)")
            print(f"  web_extract [{w_ok}] {w.get('latency_ms',0)}ms ({w_len}B)")
        
        self._report(search_results, extract_results)
    
    def _report(self, search_results, extract_results):
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M")
        path = RESULT_DIR / f"search_benchmark_{now}.md"
        
        lines = ["# 搜索通道质量对比报告 (Phase 0)", f"> 生成: {now}", ""]
        
        as_ok = sum(1 for r in search_results if r["anysearch"]["status"] == "ok")
        ddg_ok = sum(1 for r in search_results if r["duckduckgo"]["status"] == "ok")
        as_lat = [r["anysearch"]["latency_ms"] for r in search_results if r["anysearch"]["status"] == "ok"]
        ddg_lat = [r["duckduckgo"]["latency_ms"] for r in search_results if r["duckduckgo"]["status"] == "ok"]
        
        lines.append("## 总体统计\n")
        lines.append(f"| 指标 | AnySearch | DuckDuckGo |")
        lines.append(f"|------|:---------:|:----------:|")
        lines.append(f"| 成功率 | {as_ok}/{len(search_results)} | {ddg_ok}/{len(search_results)} |")
        if as_lat:
            lines.append(f"| P50延迟 | {sorted(as_lat)[len(as_lat)//2]}ms | {sorted(ddg_lat)[len(ddg_lat)//2]}ms |")
            lines.append(f"| 平均延迟 | {sum(as_lat)/len(as_lat):.0f}ms | {sum(ddg_lat)/len(ddg_lat):.0f}ms |")
        lines.append("")
        
        lines.append("## 逐查询详情\n")
        for r in search_results:
            lines.append(f"### {r['key']}: {r['query']}")
            lines.append(f"- 类型: {r['type']} | 语言: {r['lang']}\n")
            a = r["anysearch"]
            lines.append(f"**AnySearch** ({'OK' if a['status']=='ok' else 'FAIL'} {a.get('latency_ms','?')}ms):")
            lines.append(f"```\n{a.get('raw_raw', a.get('error',''))[:500]}\n```\n")
            d = r["duckduckgo"]
            lines.append(f"**DuckDuckGo** ({'OK' if d['status']=='ok' else 'FAIL'} {d.get('latency_ms','?')}ms):")
            if d["status"] == "ok":
                for res in d.get("results", [])[:3]:
                    lines.append(f"- {res.get('title','')[:60]}")
            else:
                lines.append(f"Error: {d.get('error','')}")
            lines.append("")
        
        ext_as_ok = sum(1 for r in extract_results if r["anysearch"]["status"] == "ok")
        ext_we_ok = sum(1 for r in extract_results if r["web_extract"]["status"] == "ok")
        lines.append(f"## 内容提取\n")
        lines.append(f"AnySearch extract: {ext_as_ok}/{len(extract_results)} | web_extract: {ext_we_ok}/{len(extract_results)}\n")
        for r in extract_results:
            lines.append(f"- {r['url']}")
            a = r["anysearch"]
            w = r["web_extract"]
            lines.append(f"  AnySearch: {'OK' if a['status']=='ok' else 'FAIL'} {a.get('latency_ms','?')}ms")
            lines.append(f"  web_extract: {'OK' if w['status']=='ok' else 'FAIL'} {w.get('latency_ms','?')}ms\n")
        
        report = "\n".join(lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport: {path}")
        print(report)

if __name__ == "__main__":
    SearchBenchmark().run_all()
