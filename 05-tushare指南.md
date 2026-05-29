# 05 - Tushare 信源指南

## 概述

A股结构化数据源，提供资金流向、龙虎榜等独特数据。

## 当前状态

| 项目 | 状态 |
|:-----|:-----|
| API Key | 已配置（56位Token） |
| 连接 | 正常（实测239ms） |
| 在优化层中 | **已加入降级链** (K线: baostock->tushare->akshare) |

## 接口速查

```python
import tushare as ts
import os

# Token从.env读取
token_path = os.path.expanduser("~/.hermes/.env")
with open(token_path) as f:
    for line in f:
        if line.startswith("TUSHARE_API_KEY="):
            token = line.split("=", 1)[1].strip()

pro = ts.pro_api(token)

# 日线
df = pro.daily(ts_code='600519.SH', start_date='20260520', end_date='20260525')

# 资金流向
df = pro.moneyflow(ts_code='600519.SH', start_date='20260520', end_date='20260525')

# 龙虎榜
df = pro.top_list(trade_date='20260525')
```

## 独特价值

- 资金流向（主力/北向）— `get_moneyflow()`
- 龙虎榜数据 — `get_top_list()`
- 财务指标（EPS/ROE等）— `get_fina_indicator()`
- 概念板块分类
- 财务三表

> 以上为Tushare独有数据，其它信源无法替代。
