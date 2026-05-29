"""
sina_source.py — sina_financial_report
Auto-generated from a_stock_data.py refactoring (2026-05-28)
"""

import requests
from datetime import datetime


def sina_financial_report(code: str, report_type: str = "lrb") -> list[dict]:
    """新浪财报三表。

    code: 6位代码
    report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
    返回: 按报告期排序的财务数据列表
    """
    # TODO: 从测试块中恢复实现
    # prefix = "sh" if code.startswith("6") else "sz"
    # paper_code = f"{prefix}{code}"
    # url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    # params = {"paperCode": paper_code, "source": report_type, "type": "0", "page": "1"}
    # r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    # d = r.json()
    # rows = []
    # result = d.get("result", {}).get("data", {})
    # items = result.get(report_type, [])
    # if isinstance(items, list):
    #     rows = items
    # return rows
    return []
