# 投资能力进化系统架构 v1.0

## 系统分层

```
┌──────────────────────────────────────────────────────────┐
│                     Layer 4: 进化引擎                      │
│   evolution_engine.py                                     │
│   ├── 准确率追踪 (修正率/偏差方向/框架归因)                 │
│   ├── 权重自调 (贝叶斯更新: P(正确|历史)×新证据)           │
│   └── 系统审计 (建议框架升级/因子增删)                     │
└──────────────────────┬───────────────────────────────────┘
                       │ 读取: signal_log + verification_log
                       │ 写入: 更新因子权重/框架权重
┌──────────────────────▼───────────────────────────────────┐
│                     Layer 3: 信号生成器                     │
│   signal_generator.py                                     │
│   ├── 因子评分 (复用blackhorse-ai因子管道)                  │
│   ├── 新闻冲击乘数 (新闻→因子权重倍增/衰减)                 │
│   ├── 框架交叉验证 (护城河/安全边际/周期/偏差四维)           │
│   └── 最终信号: BUY/HOLD/SELL + 置信度 + 关键依据          │
└──────────────────────┬───────────────────────────────────┘
                       │ 读取: factor_scores + news_impact
                       │ 写入: signal_{date}.json
┌──────────────────────▼───────────────────────────────────┐
│                     Layer 2: 新闻→因子映射                   │
│   news_factor_mapper.py                                   │
│   ├── 新闻分类引擎 (关键词→{行业/公司/技术/政策})           │
│   ├── 影响方向判断 (利好/利空/中性 + 强度1-5)              │
│   └── 因子权重映射 (新闻类别→影响哪个因子/幅度)            │
└──────────────────────┬───────────────────────────────────┘
                       │ 读取: news_db
                       │ 写入: news_impact_{date}.json
┌──────────────────────▼───────────────────────────────────┐
│                     Layer 1: 新闻流水线                      │
│   news_pipeline.py                                         │
│   ├── 定时采集 (aihot API, 每日08:00/20:00)                │
│   ├── 健康监控 (采集成功率/时效延迟/接口状态)                │
│   ├── 自动重试 (失败3次→降级→告警)                         │
│   └── 结构化存储 (news_db/YY/MM/YYYY-MM-DD.json)           │
└──────────────────────────────────────────────────────────┘
```

## 数据流

```
[aihot API] ──每日08:00/20:00──> news_pipeline ──> news_db/{date}.json
                                                         │
                    ┌────────────────────────────────────┘
                    ▼
        news_factor_mapper ──> news_impact_{date}.json
                    │                           │
                    │     ┌─────────────────────┘
                    ▼     ▼
        signal_generator ──> signals/{date}.json
                    │
                    ▼
        evolution_engine (每周/每月运行)
                    │
        ┌───────────┴─────────┐
        ▼                     ▼
  权重更新(动态)        系统审计报告

         ┌─────────────────────────────┐
         │  反馈闭环                    │
         │  signal → 实际走势 → 偏差    │
         │    → 修正权重 → 下轮改进     │
         └─────────────────────────────┘
```

## 文件结构

E:/AIGC-KB/输出/02-投资研究/system/
├── news_db/                  # 新闻数据库
│   └── 2026/05/
│       └── 2026-05-27.json   # 每日新闻缓存
├── impacts/                  # 新闻影响分析
├── signals/                  # 日度信号输出
├── evolution/                # 进化分析结果
├── news_pipeline.py          # L1
├── news_factor_mapper.py     # L2
├── signal_generator.py       # L3
├── evolution_engine.py       # L4
└── run_all.py                # 一键执行

## 关键接口定义 (模块间契约)

### news_pipeline → news_factor_mapper
{
  "date": "2026-05-27",
  "fetch_status": "success/degraded/failed",
  "items": [
    {
      "id": "...",
      "title": "...",
      "source": "...",
      "category": "ai-models/ai-products/industry/paper/tip",
      "summary": "...",
      "published_at": "ISO-8601"
    }
  ]
}

### news_factor_mapper → signal_generator
{
  "date": "2026-05-27",
  "impacts": [
    {
      "news_id": "...",
      "title": "...",
      "direction": "利好/利空/中性",
      "strength": 1-5,
      "affected_sectors": ["半导体/AI/消费电子"],
      "factor_adjustments": {
        "趋势": +5,    # 因子权重临时偏移(百分比)
        "量能": +3,
        "基本面": -2
      },
      "affected_stocks": ["000725","688981"],
      "reasoning": "Qwen3.7发布→AI推理需求→利好国产芯片"
    }
  ]
}

### signal_generator → evolution_engine
{
  "date": "2026-05-27",
  "signals": [
    {
      "stock_code": "000725",
      "signal": "BUY/HOLD/SELL",
      "confidence": 0.72,
      "base_score": 59.8,
      "news_boost": +3.2,
      "framework_verdict": "通过/警告/驳回",
      "risk_level": "低/中/高",
      "key_drivers": ["低估值", "AI显示需求", "量能放大"],
      "contra_signals": ["板块过热"]
    }
  ]
}

## 进化闭环

每轮完整周期:
  新闻采集 ──→ 影响映射 ──→ 信号生成 ──→ 等待t+14验证
                                                    │
               ┌────────────────────────────────────┘
               ▼
         evolution_engine:
         1. 对比预测 vs 实际
         2. 准确率 = 正确信号 / 总信号
         3. 归因分析: 哪个因子/框架贡献最大偏差?
         4. 权重更新: 
            w_new = w_old × (1 + η × (accuracy - 0.5))
            其中 η = 学习率(默认0.1)
         5. 系统审计: 连续3次准确率<50% → 标记该框架需人工审查
