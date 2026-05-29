# 04 - Akshare 信源指南

## 概述

多后端金融数据源（Sina/THS/EM），作为baostock的降级备选。

## 三后端对比

| 后端 | 用途 | 延迟 | 稳定性 | 调用方式 |
|:-----|:-----|:-----|:-------|:---------|
| Sina | A股日K线 | ~830ms | 高 | ak.stock_zh_a_daily() |
| THS | 财务摘要 | ~420ms | 中 | ak.stock_financial_abstract_ths() |
| EM | 利润表 | ~7030ms | 低 | ak.stock_profit_sheet_by_report_em() |

## 接口速查

```python
import akshare as ak

# 日K线（Sina后端，稳定）
df = ak.stock_zh_a_daily(symbol="sh600519", start_date="20260501",
                          end_date="20260525", adjust="qfq")

# 财务摘要（THS后端）
df = ak.stock_financial_abstract_ths(symbol="600519")

# 利润表（EM后端，不稳定）
df = ak.stock_profit_sheet_by_report_em(symbol="SH600519")

# 人民币汇率
df = ak.currency_boc_sina(symbol="美元")
```

## 限流说明

- Sina后端：连续请求可能返回456
- EM后端：经常RemoteDisconnect，建议通过降级链调用
