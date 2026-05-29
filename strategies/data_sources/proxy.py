"""
proxy.py — Shim: 保持向后兼容的 re-export
所有函数现已从 data_sources 各模块直接导出。
"""

from .baidu_source import baidu_concept_blocks
from .dragon_tiger import block_trade, dragon_tiger_board, holder_num_change, margin_trading
from .eastmoney_source import eastmoney_reports
from .northbound import hsgt_realtime
from .tencent_source import tencent_quote
from .ths_source import ths_eps_forecast, ths_hot_reason
from .valuation_utils import full_valuation
