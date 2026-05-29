# 07 - AIHOT 信源指南

## 概述

AI行业资讯聚合平台，实时追踪模型发布/行业动态/论文。

## 接口速查

```python
import urllib.request, json

UA = "Mozilla/5.0 aihot-skill/0.2.0"

# 最新精选
url = "https://aihot.virxact.com/api/public/items?mode=selected&take=20"
req = urllib.request.Request(url, headers={"User-Agent": UA})
data = json.loads(urllib.request.urlopen(req).read())

# 今日日报
url = "https://aihot.virxact.com/api/public/daily"
req = urllib.request.Request(url, headers={"User-Agent": UA})
data = json.loads(urllib.request.urlopen(req).read())
```

## 关键指标

| 项目 | 值 |
|:-----|:----|
| 延迟 | ~164ms |
| 更新频率 | 实时滚动 / 日报08:00 UTC |
| 认证 | 匿名（需User-Agent头） |
| 限流 | 600 req/min/IP |
