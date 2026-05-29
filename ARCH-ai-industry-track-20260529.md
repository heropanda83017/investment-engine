# ARCH: AI 产业追踪体系设计方案

> 生成: 2026-05-29 | 评审: Claude Code V4 Pro

## 背景

用户同时进行 AI 学习 + 股票投资，希望通过学习 AI 技术的过程，同步发现投资机会。现有体系：

| 体系 | 用途 | 文件数 |
|:-----|:-----|:------:|
| AIGC-KB wiki | AI 学习笔记 | ~35 篇 |
| KMS engine | 知识管理（融合/图谱/同步） | 13 脚本 |
| investment-engine | 量化选股/信号/报告 | 74 .py |
| data channels | 8 个数据源 | --- |
| cronjobs | 9 个定时任务 | --- |

## 需求

不想把「AI 学习」和「投资研究」当成两件事做——学一个概念时同步知道它对产业和投资的影响。

## 方案选项

### 方案 A: 轻量化（在 wiki 加一篇追踪页）

08-investment/04-AI产业追踪.md + 每次 AI 新闻简报时多输出「A 股映射」段落

```
优点: 零代码、今天就能做
缺点: 纯文本、无结构化、不能反馈到信号模型
冗余风险: 低（wiki 08-investment/ 目前为空）
```

### 方案 B: 中等（新增 system/ai_intel.py 模块）

新增 system/ai_intel.py，功能：
- 读取 news_db 最新 AI 新闻
- 按标签聚类（芯片/模型/应用/融资）
- 输出结构化 JSON: {sector, trend, beneficiary_stocks, signal_impact}
- signal_generator 可选读取调整权重

```
优点: 结构化、可反馈到信号
缺点: 需 2-3 天开发、测试
冗余风险:
  - ie-industry-intel cronjob（存在但未定义具体逻辑）-> 不冗余，可复用
  - KMS smart_fuse（做知识融合，不做投资映射）-> 不冗余
  - anysearch_source（做个股舆情，不做产业分析）-> 不冗余
  - 部分重叠但定位不同
```

### 方案 C: 全量（扩展现有框架分析）

在 analysis_frameworks.py 中已有 ai_compute_structure() 和 export_control_chain()
新增 ai_industry_landscape() 框架，输出每个 AI 赛道的评分

```
优点: 复用现有 21 框架体系、框架评分自动进入 signal adjustment
缺点: 开发量最大(3-5天)、可能造成框架数量膨胀
冗余风险: 中（现有框架已有 AI 相关）
```

## 冗余判断

| 已有组件 | 与 AI 产业追踪的关系 | 是否冗余 |
|:---------|:-------------------|:--------:|
| ie-industry-intel cronjob | 同名但未实现具体逻辑 | 不冗余，可复用此 cronjob |
| KMS smart_fuse | 融合 wiki 笔记，不做投资映射 | 定位不同 |
| anysearch_source | 个股情绪，非产业趋势 | 定位不同 |
| analysis_frameworks | 已有 2 个 AI 框架，可扩展 | 方案 C 直接复用 |
| news_pipeline | 采集新闻，不分析 | 上下游关系 |

## 推荐方案

**方案 B**（中等投入），理由：
1. 现有 ie-industry-intel cronjob（周一 09:00）可以直接承载此模块的执行
2. 结构化 JSON 输出可被 signal_generator 消费（刚建好的 framework_score_cli 模式可复用）
3. 不膨胀 wiki（wiki 做学习笔记，不是数据库）
4. 与已有组件是上下游/互补关系，非冗余

## 验收标准

1. system/ai_intel.py 存在，可从 news_db 读取最新 AI 新闻
2. 按 5 个赛道聚类输出（算力/模型/应用/融资/政策）
3. 每个赛道输出受益 A 股标的
4. framework_score_cli.py 可调用 ai_intel 的输出
5. ie-industry-intel cronjob 可调度此模块
6. 零冗余—不重复已有任何模块的功能