#!/usr/bin/env python3
"""实盘台账模块 — CSV格式交易记录 + 信号对比

记录每笔"信号→操作"的完整链路，支持增删改查和信号对比分析。

CSV Schema:
    date, code, name, signal, action, position_pct, price, volume, 
    reason, status, created_at, updated_at

信号枚举: BUY / HOLD / SELL / ADD / REDUCE / SKIP
状态枚举: PENDING / EXECUTED / PARTIAL / CANCELLED / EXPIRED
"""

import csv, logging, os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

log = logging.getLogger("trade_ledger")

# CSV 列定义
COLUMNS = [
    "date", "code", "name", "signal", "action", "position_pct",
    "price", "volume", "reason", "status", "created_at", "updated_at"
]

SIGNAL_ENUM = {"BUY", "HOLD", "SELL", "ADD", "REDUCE", "SKIP"}
STATUS_ENUM = {"PENDING", "EXECUTED", "PARTIAL", "CANCELLED", "EXPIRED"}

# 默认台账路径
DEFAULT_LEDGER_DIR = Path(os.environ.get("BLACKHORSE_LEDGER_DIR", 
    os.path.join(os.path.dirname(__file__), "..", "data", "ledger")))


class TradeLedger:
    """CSV 实盘台账"""

    def __init__(self, ledger_dir: str = None):
        self.ledger_dir = Path(ledger_dir) if ledger_dir else DEFAULT_LEDGER_DIR
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self._ledger_file = self.ledger_dir / "trade_ledger.csv"
        self._init_file(self._ledger_file)

    def _init_file(self, path: Path):
        """如果文件不存在，写入表头"""
        if not path.exists():
            with open(path, 'w', newline='', encoding='utf_8_sig') as f:
                writer = csv.writer(f)
                writer.writerow(COLUMNS)

    def _read_all(self, path: Path = None) -> List[Dict]:
        """读取全部记录"""
        path = path or self._ledger_file
        rows = []
        if not path.exists():
            return rows
        with open(path, 'r', encoding='utf_8_sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def _write_all(self, rows: List[Dict], path: Path = None):
        """覆写全部记录"""
        path = path or self._ledger_file
        with open(path, 'w', newline='', encoding='utf_8_sig') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def add_record(self, record: Dict) -> str:
        """新增一条交易记录"""
        if not isinstance(record, dict):
            raise TypeError(f"record must be dict, got {type(record).__name__}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "date": record.get("date", datetime.now().strftime("%Y-%m-%d")),
            "code": record.get("code", ""),
            "name": record.get("name", ""),
            "signal": record.get("signal", "HOLD"),
            "action": record.get("action", ""),
            "position_pct": str(record.get("position_pct", 0)),
            "price": str(record.get("price", 0)),
            "volume": str(record.get("volume", 0)),
            "reason": record.get("reason", ""),
            "status": record.get("status", "PENDING"),
            "created_at": now,
            "updated_at": now,
        }

        # 校验枚举值
        if entry["signal"] not in SIGNAL_ENUM:
            log.warning(f"未知信号: {entry['signal']}，使用 HOLD")
            entry["signal"] = "HOLD"
        if entry["status"] not in STATUS_ENUM:
            log.warning(f"未知状态: {entry['status']}，使用 PENDING")
            entry["status"] = "PENDING"

        with open(self._ledger_file, 'a', newline='', encoding='utf_8_sig') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writerow(entry)

        log.info(f"台账记录: {entry['code']} {entry['signal']}->{entry['action']} @{entry['position_pct']}%")
        return f"{entry['date']}_{entry['code']}"

    def query(self, code: str = None, date: str = None, 
              signal: str = None, status: str = None,
              limit: int = 50) -> List[Dict]:
        """查询记录，支持按代码/日期/信号/状态过滤"""
        rows = self._read_all()
        filtered = []
        for r in rows:
            if code and r.get("code") != code:
                continue
            if date and r.get("date") != date:
                continue
            if signal and r.get("signal") != signal:
                continue
            if status and r.get("status") != status:
                continue
            filtered.append(r)
            if limit and len(filtered) >= limit:
                break
        return filtered

    def update_record(self, code: str, date: str, updates: Dict) -> bool:
        """更新指定记录（按 code + date 匹配）"""
        rows = self._read_all()
        updated = False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            if r.get("code") == code and r.get("date") == date:
                for k, v in updates.items():
                    if k in COLUMNS and k not in ("date", "code", "created_at"):
                        r[k] = str(v)
                r["updated_at"] = now
                updated = True
                break
        if updated:
            self._write_all(rows)
            log.info(f"台账更新: {code} {date}")
        return updated

    def delete_record(self, code: str, date: str) -> bool:
        """删除指定记录"""
        rows = self._read_all()
        before = len(rows)
        rows = [r for r in rows if not (r.get("code") == code and r.get("date") == date)]
        if len(rows) < before:
            self._write_all(rows)
            log.info(f"台账删除: {code} {date}")
            return True
        return False

    def log_signal(self, code: str, signal: str, position_pct: float,
                   reason: str = "") -> str:
        """快捷记录信号（不区分持仓/买卖明细）"""
        return self.add_record({
            "code": code, "signal": signal, "action": signal,
            "position_pct": position_pct, "reason": reason,
            "status": "PENDING"
        })

    def confirm_execution(self, code: str, date: str, 
                          actual_price: float, actual_volume: int) -> bool:
        """确认执行：更新成交价、成交量、状态为 EXECUTED"""
        return self.update_record(code, date, {
            "price": actual_price, "volume": actual_volume,
            "status": "EXECUTED"
        })

    def signal_comparison(self, days: int = 30) -> Dict:
        """信号对比分析：信号 vs 实际执行

        返回:
            {"total": N, "executed": N, "pending": N, "cancelled": N,
             "execution_rate": float, "by_signal": {signal: {...}}}
        """
        rows = self._read_all()
        cutoff_date = datetime.now() - timedelta(days=days) if days else datetime(2000, 1, 1)
        
        # 按信号类型统计
        by_signal: Dict = defaultdict(lambda: {"total": 0, "executed": 0, "pending": 0})
        
        for r in rows:
            try:
                row_date = datetime.strptime(r.get("date", ""), "%Y-%m-%d")
                if row_date < cutoff_date:
                    continue
            except ValueError:
                pass
            sig = r.get("signal", "UNKNOWN")
            by_signal[sig]["total"] += 1
            
            status = r.get("status", "PENDING")
            if status == "EXECUTED":
                by_signal[sig]["executed"] += 1
            elif status == "PENDING":
                by_signal[sig]["pending"] += 1
        
        total = sum(s["total"] for s in by_signal.values())
        executed = sum(s["executed"] for s in by_signal.values())
        
        return {
            "total": total,
            "executed": executed,
            "pending": sum(s["pending"] for s in by_signal.values()),
            "cancelled": sum(1 for r in rows if r.get("status") == "CANCELLED"),
            "execution_rate": round(executed / total, 4) if total > 0 else 0,
            "by_signal": dict(by_signal),
        }

    def summary(self) -> str:
        """生成台账摘要"""
        comparison = self.signal_comparison()
        lines = [
            f"📊 实盘台账摘要",
            f"  总记录: {comparison['total']} 条",
            f"  已执行: {comparison['executed']} 条 ({comparison['execution_rate']:.1%})",
            f"  待处理: {comparison['pending']} 条",
            f"  已取消: {comparison['cancelled']} 条",
        ]
        for sig, stats in comparison["by_signal"].items():
            lines.append(f"  {sig}: {stats['total']}条 (已执行{stats['executed']}条)")
        return "\n".join(lines)
