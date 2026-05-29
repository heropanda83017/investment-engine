# 02 - Baostock 信源指南

## 概述

免费、高速（~30ms）的A股K线+财务数据信源。系统首选信源。

## 接口速查

```python
from baostock_source import BaoStockSource
bs = BaoStockSource()

# 日K线（默认前复权）
kline = bs.get_kline("600519", days=120)
# -> DataFrame: [日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 涨跌幅, 换手率, 市盈率, 市净率]

# 财务摘要
fin = bs.get_financial("600519")
# -> DataFrame: [ROE(平均), 净利率, 毛利率, 净利润, 每股收益TTM, ...]

# 批量同步
report = bs.batch_sync(["600519", "000858", "002371"])

# 信源状态
status = bs.get_status()

bs.close()
```

## 关键指标

| 项目 | 值 |
|:-----|:----|
| 延迟 | 32ms (K线) / 270ms (财务) |
| 数据范围 | K线2005~至今，财务2006~至今 |
| 覆盖 | 5100+ A股 |
| 认证 | 免费，无需API Key |
| 限制 | T+1无实时，单线程连接 |
| 稳定性 | 极高（专用服务器） |

## 相对akshare的优势

baostock K线比akshare Sina快24倍，财务比akshare THS快14倍。
