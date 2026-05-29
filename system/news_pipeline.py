#!/usr/bin/env python3
"""news_pipeline.py - Layer 1: 新闻流水线"""

import os, sys, json, time, argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.join(DIR, "news_db")
HEALTH = os.path.join(NEWS_DIR, "health.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 AppleWebKit/537.36 aihot-skill/0.2.0"

KW = {
    "OpenAI":("AI","OpenAI"),"Anthropic":("AI","Anthropic"),"英伟达":("chip","NVIDIA"),"NVIDIA":("chip","NVIDIA"),
    "华为":("chip","华为"),"苹果":("con","Apple"),"阿里":("AI","Alibaba"),"Qwen":("AI","Alibaba"),
    "腾讯":("AI","Tencent"),"混元":("AI","Tencent"),"百度":("AI","Baidu"),"GPT":("AI","OpenAI"),
    "制裁":("pol",""),"出口管制":("pol",""),"算力":("cmp",""),"芯片":("chip",""),
    "推理":("cmp",""),"训练":("cmp",""),"Agent":("agt",""),"智能体":("agt",""),
    "开源":("os",""),"发布":("prod",""),
}
BULL = ["发布","开源","突破","超越","升级","上线","融资","合作"]
BEAR = ["制裁","出口管制","泄露","故障","裁员","诉讼","禁止","安全风险"]

def api_get(path, retry=3):
    for i in range(retry):
        try:
            r = Request("https://aihot.virxact.com"+path, headers={"User-Agent":UA})
            with urlopen(r, timeout=15) as resp:
                return json.loads(resp.read()), None
        except Exception as e:
            if i==retry-1:
                return None, str(e)[:80]
            time.sleep(2**i)

def classify(title, summary):
    t = (title or "") + " " + (summary or "")
    tl = t.lower()
    secs=[]; cos=[]
    for k,(s,c) in KW.items():
        if k.lower() in tl:
            if s: secs.append(s)
            if c: cos.append(c)
    dr = "中性"
    for kw in BULL:
        if kw in t: dr="利好"; break
    if dr=="中性":
        for kw in BEAR:
            if kw in t: dr="利空"; break
    return {"tags":list(set(secs))[:3],"cos":list(set(cos))[:3],"dir":dr}

def fetch():
    now = datetime.now(timezone(timedelta(hours=8)))
    print("[pipe] Fetch: %s" % now.strftime("%Y-%m-%d"))
    items=[]
    since = (now-timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d1, e1 = api_get("/api/public/items?mode=selected&since=%s&take=100" % since)
    if d1:
        for it in d1.get("items",[]):
            c = classify(it.get("title",""), it.get("summary",""))
            items.append({
                "id":it.get("id"),"title":it.get("title"),"src":it.get("source"),
                "url":it.get("url"),"cat":it.get("category"),"pub":it.get("publishedAt"),
                "summary":it.get("summary"),"tags":c["tags"],"cos":c["cos"],"dir":c["dir"]
            })
        print("  selected: %d items" % len(d1.get("items",[])))
    else:
        print("  selected FAIL: %s" % e1)
        d2,e2 = api_get("/api/public/daily")
        if d2:
            for sec in d2.get("sections",[]):
                for it in sec.get("items",[]):
                    c = classify(it.get("title",""), it.get("summary",""))
                    items.append({
                        "id":it.get("id") or "d","title":it.get("title"),"src":it.get("sourceName"),
                        "url":it.get("sourceUrl"),"cat":"","pub":d2.get("date",""),
                        "summary":it.get("summary",""),"tags":c["tags"],"cos":c["cos"],"dir":c["dir"]
                    })
            print("  daily fallback: %d items" % len(items))
        else:
            print("  daily FAIL: %s" % e2)
    return items

def store(items):
    now = datetime.now(timezone(timedelta(hours=8)))
    td = now.strftime("%Y-%m-%d")
    d = os.path.join(NEWS_DIR, now.strftime("%Y"), now.strftime("%m"))
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, td+".json")
    entry = {"date":td,"at":now.isoformat(),"n":len(items),"items":items}
    with open(fp,"w",encoding="utf-8") as f:
        json.dump(entry,f,ensure_ascii=False,indent=2)
    print("  stored: %s (%d items)" % (fp, len(items)))

def save_health(n, errs):
    h = {}
    if os.path.exists(HEALTH):
        with open(HEALTH,"r",encoding="utf-8") as f: h=json.load(f)
    else:
        h = {"fetches":0,"ok":0,"fail":0,"cf":0,"total":0,"days":[]}
    h["fetches"] += 1
    if n>0:
        h["ok"]+=1; h["cf"]=0; h["total"]+=n
    else:
        h["fail"]+=1; h["cf"]+=1
    h["days"].append({"date":datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d"),"n":n,"ok":n>0})
    h["days"] = h["days"][-30:]
    h["rate"] = round(h["ok"]/h["fetches"]*100,1) if h["fetches"] else 0
    h["last"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
    h["alert"] = None
    if h["cf"]>=3:
        h["alert"] = "ALERT: %d consecutive fails" % h["cf"]
    with open(HEALTH,"w",encoding="utf-8") as f:
        json.dump(h,f,ensure_ascii=False,indent=2)
    return h

def show_health():
    if not os.path.exists(HEALTH):
        print("No health data"); return
    with open(HEALTH,"r",encoding="utf-8") as f: h=json.load(f)
    print("="*50); print(" News Pipeline Health"); print("="*50)
    print("  Fetches: %d (OK:%d Fail:%d)" % (h["fetches"],h["ok"],h["fail"]))
    print("  Rate: %s%%  ConsecFail: %d" % (h["rate"],h["cf"]))
    print("  Items: %d" % h["total"])
    if h.get("alert"): print("\n  !! %s" % h["alert"])
    print("\n  Last 7d:")
    for d in h["days"][-7:]:
        s = "OK" if d["ok"] else "FAIL"
        print("    %s [%s] %d" % (d["date"],s,d["n"]))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--health",action="store_true")
    ap.add_argument("--force",action="store_true")
    args = ap.parse_args()
    if args.health: show_health(); return
    now = datetime.now(timezone(timedelta(hours=8)))
    td = now.strftime("%Y-%m-%d")
    sp = os.path.join(NEWS_DIR, now.strftime("%Y"), now.strftime("%m"), td+".json")
    if os.path.exists(sp) and not args.force:
        with open(sp,"r",encoding="utf-8") as f:
            c = json.load(f)
        print("[pipe] Cached today (%d items), use --force to refetch" % c["n"])
        return
    items = fetch()
    if items: store(items)
    h = save_health(len(items), [])
    if h.get("alert"): print("\n!! %s" % h["alert"])
    if items:
        secs={}; dirs={}
        for it in items:
            for t in it["tags"]: secs[t]=secs.get(t,0)+1
            d=it["dir"]; dirs[d]=dirs.get(d,0)+1
        print("  Top sectors: %s" % dict(sorted(secs.items(),key=lambda x:-x[1])[:5]))
        print("  Sentiment: %s" % dirs)
    print("  Done: %s" % datetime.now(timezone(timedelta(hours=8))).isoformat()[:19])

if __name__=="__main__":
    main()
