"""
a_stock_data.py — Shim: 保持向后兼容的统一 re-export
重构自 2026-05-28, 原 1,597行/59KB 拆分至 11 个模块
"""

from .common import get_prefix, _claw_headers, dedup_articles
from .tencent_source import tencent_quote
from .eastmoney_source import (eastmoney_datacenter, eastmoney_reports, download_pdf,
    eastmoney_fund_flow_minute, eastmoney_stock_news, eastmoney_global_news,
    eastmoney_stock_info, stock_fund_flow_120d)
from .baidu_source import baidu_kline_with_ma, baidu_concept_blocks
from .ths_source import ths_eps_forecast, ths_hot_reason, iwencai_search, iwencai_query
from .cninfo_source import cninfo_announcements, _cninfo_ts_to_date
from .sina_source import sina_financial_report
from .valuation_utils import forward_pe, pe_digestion, calc_peg, full_valuation, industry_comparison
from .dragon_tiger import (dragon_tiger_board, daily_dragon_tiger, lockup_expiry,
    margin_trading, block_trade, holder_num_change, dividend_history)
from .northbound import hsgt_realtime, _northbound_cache_path, _save_northbound_snapshot, _load_northbound_history
from .cls_source import cls_telegraph
