#!/usr/bin/env python3
# monitor.py - Data acquisition monitoring & alerting

import sys, os, json, time, logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque

from env import DATA_ROOT, IE_SCRIPTS, IE_CACHE, IE_CACHE_OPTIMIZED, IE_CACHE_TICKFLOW, IE_CACHE_ANALYSIS, IE_CACHE_MONITOR, LEGACY_SCRIPTS


sys.path.insert(0, str(LEGACY_SCRIPTS))
log = logging.getLogger("monitor")

ALERT_THRESHOLDS = {
    "latency_ms": {"warning": 2000, "critical": 5000},
    "failure_rate_pct": {"warning": 10, "critical": 30},
    "cache_hit_rate_pct": {"warning": 50, "critical": 20},
}

MONITOR_ROOT = IE_CACHE_MONITOR
MONITOR_ROOT.mkdir(parents=True, exist_ok=True)
class DataMonitor:
    def __init__(self):
        self._start_time = time.time()
        self._history = defaultdict(lambda: deque(maxlen=1000))
        self._alerts = deque(maxlen=100)

    def record_request(self, source, data_type, latency_ms, success, cached=False):
        entry = {"ts": time.time(), "source": source, "type": data_type,
                 "latency": latency_ms, "success": success, "cached": cached}
        self._history[source].append(entry)
        if not cached and latency_ms > ALERT_THRESHOLDS["latency_ms"]["critical"]:
            self._alert("CRITICAL", f"{source} delay {latency_ms:.0f}ms")
        elif not cached and latency_ms > ALERT_THRESHOLDS["latency_ms"]["warning"]:
            self._alert("WARNING", f"{source} delay {latency_ms:.0f}ms")

    def record_failure(self, source, data_type, error):
        entry = {"ts": time.time(), "source": source, "type": data_type,
                 "latency": 0, "success": False, "error": str(error)[:100]}
        self._history[source].append(entry)
        recent = [e for e in self._history[source] if time.time() - e.get("ts", 0) < 300]
        failures = sum(1 for e in recent if not e.get("success", True))
        total = len(recent)
        if total >= 5 and failures / total > 0.3:
            self._alert("CRITICAL", f"{source} 5min failure {failures}/{total}")

    def _alert(self, level, message):
        alert = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message}
        self._alerts.append(alert)
        print(f"  [{alert['time']}] [{level}] {message}")

    def source_stats(self, source, window_sec=3600):
        cutoff = time.time() - window_sec
        entries = [e for e in self._history.get(source, []) if e.get("ts", 0) > cutoff]
        if not entries:
            return {"source": source, "requests": 0, "successes":0, "failures":0, "cached":0, "success_rate":0, "cache_rate":0, "avg_latency_ms":0, "max_latency_ms":0}
        total = len(entries)
        successes = sum(1 for e in entries if e.get("success"))
        failures = total - successes
        cached = sum(1 for e in entries if e.get("cached"))
        lats = [e["latency"] for e in entries if e.get("success") and not e.get("cached")]
        return {
            "source": source, "requests": total, "successes": successes,
            "failures": failures, "cached": cached,
            "success_rate": round(successes / total * 100, 1),
            "cache_rate": round(cached / total * 100, 1) if total > 0 else 0,
            "avg_latency_ms": round(sum(lats) / len(lats), 1) if lats else 0,
            "max_latency_ms": round(max(lats), 1) if lats else 0,
        }

    def overall_stats(self, window_sec=3600):
        all_sources = ["akshare_sina", "akshare_ths", "akshare_em", "tickflow"]
        s_stats = [self.source_stats(s, window_sec) for s in all_sources]
        tr = sum(s["requests"] for s in s_stats)
        tf = sum(s["failures"] for s in s_stats)
        tc = sum(s["cached"] for s in s_stats)
        return {
            "uptime": int(time.time() - self._start_time),
            "total_requests": tr,
            "failure_rate": round(tf/tr*100,1) if tr else 0,
            "cache_hit_rate": round(tc/tr*100,1) if tr else 0,
            "sources": s_stats, "alerts": len(self._alerts),
        }

    def show_status(self):
        o = self.overall_stats()
        print()
        print("=" * 55)
        print("  Data Monitor | Uptime: %dh%dm" % (o["uptime"]//3600, o["uptime"]%3600//60))
        print("=" * 55)
        print("%-16s %5s %5s %5s %5s %6s" % ("Source","Req","OK","Fail","Cache","Lat"))
        print("-" * 55)
        for s in o["sources"]:
            if s["requests"] == 0:
                continue
            print("  %-14s %5d %5d %5d %5d %6d" % (
                s["source"], s["requests"], s["successes"],
                s["failures"], s["cached"], s["avg_latency_ms"]))
        print("-" * 55)
        print("  Total: %dreq | Fail: %s%% | Cache: %s%% | Alerts: %d" % (
            o["total_requests"], o["failure_rate"], o["cache_hit_rate"], o["alerts"]))
        if self._alerts:
            print("\n  Recent alerts:")
            for a in list(self._alerts)[-5:]:
                print("    [%s] [%s] %s" % (a["time"], a["level"], a["message"]))

    def generate_dashboard(self):
        o = self.overall_stats(300)
        rows = ""
        for s in o["sources"]:
            if s["requests"] == 0:
                continue
            color = "green" if s["success_rate"] > 95 else "orange"
            status = "OK" if s["success_rate"] > 95 else "WARN"
            rows += "<tr><td>%s</td><td>%d</td><td>%s%%</td><td>%sms</td><td style='color:%s'>%s</td></tr>\n" % (
                s["source"], s["requests"], s["success_rate"], s["avg_latency_ms"], color, status)
        
        alerts_rows = ""
        for a in list(self._alerts)[-10:]:
            alerts_rows += "<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (
                a["time"], a["level"], a["message"])
        if not alerts_rows:
            alerts_rows = "<tr><td colspan='3' style='color:gray'>No alerts</td></tr>"
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = "%dh%dm" % (o["uptime"]//3600, o["uptime"]%3600//60)
        
        html = "<!DOCTYPE html>\n"
        html += "<html><head><meta charset='utf-8'><title>Data Monitor</title>\n"
        html += "<style>\n"
        html += "body{font-family:-apple-system,'Microsoft YaHei',sans-serif;margin:20px;background:#f5f5f5;}\n"
        html += ".card{background:white;border-radius:8px;padding:16px;margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);}\n"
        html += "h2{margin:0 0 5px 0;}.sub{color:gray;font-size:13px;margin:0 0 15px 0;}\n"
        html += "table{width:100%;border-collapse:collapse;}\n"
        html += "th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #eee;}\n"
        html += "th{color:gray;font-weight:normal;font-size:12px;}\n"
        html += "</style></head><body>\n"
        html += "<h2>Data Acquisition Monitor</h2>\n"
        html += "<p class='sub'>Updated: %s | Uptime: %s</p>\n" % (now, uptime)
        html += "<div class='card'><h3>Source Status</h3>\n"
        html += "<table><tr><th>Source</th><th>Requests</th><th>Success</th><th>Latency</th><th>Status</th></tr>\n"
        html += rows
        html += "</table></div>\n"
        html += "<div class='card'><h3>Recent Alerts</h3>\n"
        html += "<table><tr><th>Time</th><th>Level</th><th>Message</th></tr>\n"
        html += alerts_rows
        html += "</table></div>\n"
        html += "<p style='color:gray;font-size:11px;'>Total: %dreq | Fail: %s%% | Cache: %s%%</p>\n" % (
            o["total_requests"], o["failure_rate"], o["cache_hit_rate"])
        html += "</body></html>"
        
        path = MONITOR_ROOT / "dashboard.html"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        print("Dashboard: %s" % path)
        return str(path)


_INSTANCE = None
def get_monitor():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DataMonitor()
    return _INSTANCE


if __name__ == "__main__":
    dm = get_monitor()
    dm.show_status()
    dash = dm.generate_dashboard()
