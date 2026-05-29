# Hermes Skills → investment-engine 代码映射

> 目的：清晰标出每个 Hermes Skill 对应的 investment-engine 代码模块，
> 避免代码与技能描述的双份维护，保持"Skill = 使用指南，investment-engine = 执行代码"的架构原则。

---

## 核心投资 Skills

### stock-research

**角色：** 数据层入口 — 告诉 Agent 怎么获取 K 线/财务/实时行情

| Skill 功能 | investment-engine 对应 | 关系 |
|:-----------|:-----------------------|:-----|
| K 线数据（首选 baostock） | scripts/baostock_source.py | Skill 描述降级链，脚本实现数据获取 |
| 多源数据统一调度 | scripts/data_optimizer.py | Skill 列出信源优先级，脚本实现两级缓存+熔断+降级 |
| 简捷数据管道 | scripts/data_pipeline.py | Skill 给出调用示例，脚本实现 get_pipeline() |
| 实时逐笔数据 | scripts/tickflow.py | Skill 描述 TickFlow 能力，脚本实现轮询+K 线聚合 |
| 个股综合分析 | scripts/stock_analyst.py | Skill 引用 StockAnalyst 用法 |
| 全市场批量筛选 | scripts/stock_scanner.py | Skill 引用 StockScanner 用法 |
| 环境配置 | scripts/env.py | Skill 描述路径常量，脚本定义 IE_ROOT/IE_SCRIPTS 等 |
| MCP 失效降级 | scripts/alternative_data_sources.py | Skill 列出降级方案，脚本实现 akshare 替代 |

**数据流向：** Agent 请求 → stock-research skill 选择信源 → scripts/ 脚本执行 → 结果

---

### investment-analysis

**角色：** 分析引擎 — 回测/估值/因子评分/风控

| Skill 功能 | investment-engine 对应 | 关系 |
|:-----------|:-----------------------|:-----|
| 量化回测 | strategies/backtest.py | Skill 提供 backtrader 模板，脚本实现 run_portfolio/walk_forward_cv |
| 回测引擎桥接 | strategies/backtest_engine.py | 策略优化器与回测系统的桥梁 |
| 因子评分 | strategies/build_features.py | Skill 描述因子方法论，脚本实现 FactorScorer + score_by_boundaries |
| 选股打分排序 | strategies/score_stocks.py | Skill 引用 ScoringEngine，脚本实现 daily_rank + 预测记录 |
| 策略流水线 | strategies/strategy_pipeline.py | 权重优化 → 验证回测 → 决策采纳 |
| 策略自学习 | strategies/evolution_engine.py | 预测记录 → 验证 → 贝叶斯更新 → 审计标记 |
| 权重优化 | strategies/strategy_optimizer.py | 贝叶斯优化 + 模拟退火因子权重搜索 |
| 仓位管理 | strategies/position_sizing.py | 信号强度 → 仓位比例映射 + P1-P5 风控约束 |
| 策略风控 | strategies/risk_manager.py | P1 单股上限 / P2 行业集中度 / P3 最大回撤 / P4 流动性 / P5 预交易 |
| 绩效追踪 | strategies/factor_tracker.py | IC 追踪 / 因子共线性 / 衰减分析 |
| 因子 Alpha191 | strategies/alpha191_factors.py | 191 个技术因子计算 |
| 分析框架评分 | strategies/analysis_frameworks.py | 19 大框架的自动化评分实现 |
| 估值模型 | strategies/data_sources/a_stock_data.py | DCF/PE-band/PB-band 估值实现 |
| 可视化 | strategies/visualization.py | K线图 / 估值带 / 行业热力图 |

**数据流向：** Agent 请求 → investment-analysis skill 选择分析类型 → strategies/ 脚本执行 → 结果

---

### analysis-frameworks

**角色：** 投资分析框架库 — 方法论 vs 代码实现

| 框架 | 代码位置 | 实现方式 |
|:-----|:---------|:---------|
| 护城河评估 | strategies/analysis_frameworks.py | 定量评分（4 维度加权） |
| 财务拆解（杜邦/浑水） | strategies/analysis_frameworks.py | 15 维度财务健康评分 |
| 周期定位 | strategies/analysis_frameworks.py | 五周期温度计打分 |
| 行业研究四步法 | strategies/industry_intel.py | PEST+三维定位+产业链+资金流 |
| 行为金融检视 | strategies/analysis_frameworks.py | 五偏误自检 + 市场情绪观测 |
| 尽调六步法 | strategies/analysis_frameworks.py | ERM 风险矩阵 + 数据资产入表 |
| 量价分析 | strategies/analysis_frameworks.py | 道氏三阶段 + 成交量四法则 |

**关系：** Skill 描述 19 个框架的方法论和公式，analysis_frameworks.py 实现可调用的评分函数

---

### financial-news

**角色：** 财经资讯采集

| Skill 功能 | investment-engine 对应 | 关系 |
|:-----------|:-----------------------|:-----|
| 官方公告（巨潮） | system/news_pipeline.py | Skill 列出源，脚本实现采集+落库 |
| 实时快讯（财联社） | system/news_pipeline.py | 同上 |
| 社会情绪（雪球/微博） | system/news_factor_mapper.py | 新闻 → 因子信号映射 |
| 关键词权重评估 | system/news_factor_mapper.py | 行业词库 + 权重衰减 |

**关系：** Skill 定义采集策略，system/ 脚本执行采集+因子化

---

### morning-routine

**角色：** 每日早间检查与简报

| Skill 功能 | investment-engine 对应 | 关系 |
|:-----------|:-----------------------|:-----|
| 系统健康检查 | system/startup_pipeline.py | Skill 描述检查项，脚本实现环境验证 |
| cronjob 验证 | — | Skill 直接调用 cronjob list |
| MCP 数据源抽检 | scripts/monitor.py | Skill 调用 monitor 脚本 |
| 昨日信号回顾 | system/signals/ | 信号 JSON 文件 |
| AI 新闻拉取 | — | 外部 API（aihot），无代码在 investment-engine |
| 待办清单 | tracking/ | 跟踪状态 JSON |

**关系：** Skill 编排流程，各步骤委托对应脚本执行

---

## 辅助 Skills

### aihot / ai-news

- 无 investment-engine 对应代码，直接调用外部 API
- 采集结果可存档到 system/news_db/ 目录

### investment-report

- 无 investment-engine 对应代码，纯 Skill 级别（prompt 模板）
- 输出文件存入 E:/AIGC-KB/输出/02-投资研究/

### wechat-article-scraper

- 无 investment-engine 对应代码，独立工具链
- 采集内容供 system/news_factor_mapper.py 做因子映射

---

## 架构总览

```
Hermes Agent
  |
  +-- Skills（使用指南）
  |   +-- stock-research         -> scripts/ 数据管线
  |   +-- investment-analysis    -> strategies/ 分析引擎
  |   +-- analysis-frameworks    -> strategies/analysis_frameworks.py
  |   +-- financial-news         -> system/news_*.py
  |   +-- morning-routine        -> pipelines/ + system/startup_pipeline.py
  |
  +-- MCP Servers（实时通道）
  |   +-- wudao                  实时盘面
  |   +-- stockstar              ESG/调研/DCF
  |   +-- finance-mcp            分钟K线/美股/港股
  |
  +-- investment-engine/（执行层）
      +-- scripts/               数据获取 + 分析
      +-- strategies/            因子 + 回测 + 风控
      +-- pipelines/             定时流水线
      +-- system/                系统服务
```

## 变更规则

| 变更场景 | 需要更新的文件 |
|:---------|:---------------|
| 新增数据源 | scripts/{name}_source.py + stock-research SKILL.md 降级链 |
| 新增因子 | strategies/factor_{name}.py + investment-analysis SKILL.md 因子列表 |
| 新增框架 | strategies/analysis_frameworks.py + analysis-frameworks SKILL.md |
| 纯 Skill 变更（无代码） | 只改 SKILL.md，不碰 investment-engine |
