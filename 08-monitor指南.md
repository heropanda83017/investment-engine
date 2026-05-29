# 08 - 监控与告警指南

## 概述

信源健康状态实时监控 + 延迟告警 + HTML看板。

## 接口速查

```python
from monitor import get_monitor
dm = get_monitor()

# 记录请求
dm.record_request("baostock", "kline", 32, True)
dm.record_request("tickflow", "realtime", 176, True)

# 记录失败
dm.record_failure("akshare_em", "profit_sheet", "Connection reset")

# 查看状态
dm.show_status()

# 生成HTML看板
dm.generate_dashboard()
```

## 告警阈值

| 级别 | 延迟 | 失败率 |
|:-----|:-----|:-------|
| WARNING | >2000ms | >10% |
| CRITICAL | >5000ms | >30% |
