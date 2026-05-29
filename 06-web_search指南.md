# 06 - 网络搜索信源指南

## 概述

基于DuckDuckGo的免费网络搜索，无需API Key。

## 接口速查

```python
from web_search_utils import search, search_news, US_market

# 通用搜索
results = search("A股 AI板块 2026年5月", max_results=5)
for r in results:
    print(r["title"], r["url"], r["snippet"][:100])

# 新闻搜索
news = search_news("AI investment", max_results=5, timelimit="d")

# 美股汇率备选
us = US_market()
# -> {"USD_CNY_rate": 7.1771}
```

## 关键指标

| 项目 | 值 |
|:-----|:----|
| 延迟 | ~1s |
| 认证 | 免费，无需Key |
| 限制 | 连续搜索需加0.5s间隔 |
| 稳定性 | 高 |
