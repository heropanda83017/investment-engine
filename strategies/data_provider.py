"""数据提供者抽象接口 — 依赖注入解耦investment-engine"""

import sys, logging
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Any
from datetime import datetime, timedelta
from config_loader import IE_SCRIPTS

log = logging.getLogger("data_provider")


class DataProvider(Protocol):
    """数据提供者协议 — 所有数据获取操作的标准接口"""

    def get_kline(self, code: str, days: int = 120) -> "pd.DataFrame":
        """获取日K线"""
        ...

    def get_financial(self, code: str) -> "pd.DataFrame":
        """获取财务摘要"""
        ...

    def get_all_stocks(self) -> list:
        """获取全市场股票列表"""
        ...

    def get_stock_name(self, code: str) -> str:
        """获取股票名称"""
        ...


class OptimizedDataProvider:
    """基于OptimizedDataLayer的数据提供者实现"""

    def __init__(self):
        self._ol = None
        self._name_map = {}
        self._init_layer()

    def _init_layer(self):
        try:
            from data_optimizer import OptimizedDataLayer
            self._ol = OptimizedDataLayer()
        except Exception as e:
            log.warning(f"OptimizedDataLayer初始化失败: {e}")

    def get_kline(self, code: str, days: int = 120):
        if self._ol is None:
            return __import__("pandas").DataFrame()
        try:
            return self._ol.get_kline(code, days)
        except Exception as e:
            log.debug(f"K线获取失败 {code}: {e}")
            return __import__("pandas").DataFrame()

    def get_financial(self, code: str):
        if self._ol is None:
            return __import__("pandas").DataFrame()
        try:
            return self._ol.get_financial_abstract(code)
        except Exception as e:
            log.debug(f"财务获取失败 {code}: {e}")
            return __import__("pandas").DataFrame()

    def get_all_stocks(self) -> list:
        return []

    def get_stock_name(self, code: str) -> str:
        return self._name_map.get(code, "")


class MockDataProvider:
    """测试用模拟数据提供者"""

    def __init__(self):
        import pandas as pd
        import numpy as np
        self._pd = pd

    def get_kline(self, code: str, days: int = 120):
        import numpy as np
        dates = self._pd.date_range(end=datetime.now(), periods=days, freq="B")
        return self._pd.DataFrame({
            "日期": dates, "开盘": np.random.randn(days) * 2 + 100,
            "收盘": np.random.randn(days) * 2 + 100,
            "最高": np.random.randn(days) * 3 + 102,
            "最低": np.random.randn(days) * 3 + 98,
            "成交量": np.random.randint(1000000, 10000000, days),
            "成交额": np.random.randint(100000000, 1000000000, days),
            "换手率": np.random.rand(days) * 5,
        })

    def get_financial(self, code: str):
        return self._pd.DataFrame()

    def get_all_stocks(self) -> list:
        return ["600519", "000858", "002371", "300308"]

    def get_stock_name(self, code: str) -> str:
        names = {"600519": "贵州茅台", "000858": "五粮液",
                 "002371": "北方华创", "300308": "中际旭创"}
        return names.get(code, "")


# 全局单例（向后兼容）
_default_provider = None

def get_provider(use_mock: bool = False):
    """获取数据提供者实例"""
    global _default_provider
    if use_mock:
        return MockDataProvider()
    if _default_provider is None:
        _default_provider = OptimizedDataProvider()
    return _default_provider
