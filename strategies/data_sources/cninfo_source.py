"""
cninfo_source.py — _cninfo_ts_to_date, cninfo_announcements
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
from datetime import datetime


def _cninfo_ts_to_date(ts):
    """巨潮 announcementTime 返回 Unix 毫秒整数，需转换为日期字符串。"""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)[:10] if ts else ""


def cninfo_announcements(code: str, page_size: int = 30) -> list[dict]:
    """巨潮公告全文检索。

    返回: [{title, type, date, url}]
    """
    # TODO: 从测试块中恢复实现
    # 构造 orgId（巨潮 2026 新格式）
    # if code.startswith("6"):
    #     org_id = f"gssh0{code}"
    # elif ...
    # url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    # payload = {...}
    # r = requests.post(url, data=payload, headers=headers, timeout=15)
    # d = r.json()
    # rows = []
    # for item in d.get("announcements", []) or []:
    #     rows.append({...})
    # return rows
    return []
