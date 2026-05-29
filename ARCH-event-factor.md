# ARCH: 事件因子模块

> 生成: 2026-05-27 | 评审: delegate_task V4 Flash

## 目标

激活 config.json 中预留的 event_factor 维度（weight=15%），基于现有数据源构建事件因子评分。

## FactorHub 参考

| 因子 | Sharpe | 年化 | 回撤 | 含义 |
|:-----|:-----:|:----:|:----:|:-----|
| EVT009 分红除权 | 1.18 | 13% | -13% | 高分红股票跑赢 |
| EVT004 回购 | 1.11 | 20% | -22% | 回购公告后上涨 |
| EVT006 并购重组 | 1.00 | 32% | -38% | 并购事件驱动 |
| EVT007 高管增减持 | 1.00 | 19% | -22% | 高管增持信号 |
| EVT012 评级变动 | 1.00 | 17% | -20% | 券商评级上调 |
| EVT001 业绩预告 | 0.96 | 22% | -28% | 业绩超预期 |

## 可用数据源

| 数据 | 来源 | 可用性 |
|:-----|:-----|:-------|
| 分红数据 | baostock.query_dividend_data | ✅ |
| 业绩预告 | baostock.query_forecast_report | ✅ |
| 业绩快报 | baostock.query_performance_express_report | ✅ |
| 公司公告 | 沃道MCP official_announcements | ✅ |
| 回购公告 | 沃道MCP + 关键词"回购" | ✅ |

## 方案

### 文件

```
strategies/
├── factor_event.py         ← NEW: 事件因子评分模块
│   ├── EventScorer        — 主类
│   ├── score_dividend()   — 分红评分
│   ├── score_forecast()   — 业绩预告评分
│   ├── score_buyback()    — 回购评分（MCP公告搜索）
│   └── total_event_score()— 综合事件评分
│
├── build_features.py      ← 修改: 添加 event 因子通道
└── config.json            ← 修改: event_factor weight 0.00→0.15
```

### 评分逻辑

```
score_dividend(stock):
  1. 获取近2年分红记录
  2. 计算股息率 = 年分红总额 / 市值
  3. 股息率 > 3% → 高分 (80-100)
  4. 股息率 1-3% → 中分 (40-80)
  5. 股息率 < 1% → 低分 (0-40)
  6. 分红频率稳定 → 加分

score_forecast(stock):
  1. 获取最新业绩预告
  2. 预增/扭亏 → 高分
  3. 预减/亏损 → 低分

score_buyback(stock):
  1. 搜索近期回购公告
  2. 有回购 → 加分

total_event_score = dividend*0.4 + forecast*0.4 + buyback*0.2
```

### 风险

| 风险 | 对策 |
|------|------|
| baostock 数据延迟 | 降级到 akshare |
| 无公告数据时影响评分 | 默认为 50 分（中性） |
| 全市场扫描耗时 | 仅对候选池评分 |
