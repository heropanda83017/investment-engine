# ARCH: 投资能力进化系统 v1.0

## 1. 系统目标
构建从新闻采集 -> 因子分析 -> 信号生成 -> 结果验证 -> 权重自调完整闭环。

## 2. 现有资产（已建成待审核）

| 组件 | 路径 | 状态 |
|------|------|:----:|
| 新闻流水线(L1) | system/news_pipeline.py | 语法通过，待REVIEW |
| 跟踪系统配置 | tracking/tracker_config.json | 已运行 |
| 初始预测基准 | tracking/predictions/ (6条) | 已写入 |
| 周度扫描 | blackhorse-ai/scripts/weekly_tracker.py | 已就绪 |
| 验证脚本 | blackhorse-ai/scripts/verify_predictions.py | 已就绪 |
| 周度CronJob | weekly-tracking-scan (周日20:00) | 已注册 |

## 3. 待建设组件

### 3.1 Phase 3: 新闻->因子映射器 (news_factor_mapper.py)
路径: system/news_factor_mapper.py
功能: 读取 news_db/{date}.json -> 每条新闻映射到因子权重调整 -> 输出 news_impact_{date}.json

映射规则:
| 新闻类别 | 影响因子 | 强度 | 示例 |
|----------|---------|:----:|------|
| 模型发布(利好) | 趋势+ | +1~+5 | Qwen3.7发布 -> 趋势+3 |
| 产品发布(利好) | 量能+ | +1~+3 | Kling新功能 -> 量能+2 |
| 行业动态(利好) | 资金+ | +1~+4 | AI渗透金融 -> 资金+2 |
| 制裁(利空) | 基本面- | -1~-5 | 出口管制升级 -> 基本面-4 |
| 技术突破 | 趋势+/Alpha+ | +2~+5 | 5nm突破 -> Alpha+4 |

### 3.2 Phase 4: 信号生成器 (signal_generator.py)
路径: system/signal_generator.py
功能: 因子评分 + 新闻冲击 + 框架分析 -> 交叉决策 -> BUY/HOLD/SELL

决策逻辑:
  signal = f(因子评分_新闻调整, 框架验证, 风险检查)
  因子评分_新闻调整 = base_score + sum(news_boost) - sum(news_drag)

信号规则:
  - 因子分>55 + 安全边际>=中 + 框架PASS>=3 -> BUY
  - 因子分40-55 + 框架PASS>=2 -> HOLD
  - 因子分<40 OR 安全边际=极低 OR 周期=派发 -> SELL

### 3.3 Phase 5: 进化引擎 (evolution_engine.py)
路径: system/evolution_engine.py
功能: 每2周回顾 -> 准确率计算 -> 因子归因 -> 权重贝叶斯更新 -> 审计标记

权重更新: w_new[f] = w_old[f] * (1 + eta * (acc[f] - baseline))
  eta=0.1, baseline=0.6, 限制[0.05, 0.40]

审计规则:
  - 连续3次准确率<40% -> 标记人工审查
  - 某因子连续5次负偏差 -> 建议替换
  - 新闻方向错误率>50% -> 更新映射表

### 3.4 Phase 6: CronJob编排

| 任务 | 频率 | 执行 |
|------|:----:|------|
| news-fetch-morning | 每日08:00 | news_pipeline.py |
| news-fetch-evening | 每日20:00 | news_pipeline.py --force |
| news-analyze | 采集后30min | news_factor_mapper.py |
| weekly-scan | 周日20:00 | 现有cronjob |
| evolution-review | 每2周周日 | evolution_engine.py |

## 4. 模块间契约

news_pipeline -> news_factor_mapper: news_db/{date}.json
news_factor_mapper -> signal_generator: news_impact_{date}.json
signal_generator -> evolution_engine: signals/{date}.json
evolution_engine -> tracker_config.json: 权重更新

## 5. 验证标准
每次交付须: py_compile语法检查 -> 模块导入测试 -> 功能断言 -> 真实数据运行
