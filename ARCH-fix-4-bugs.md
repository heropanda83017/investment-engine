# ARCH: Fix 4 Pre-existing Bugs in investment-engine/strategies
> 生成: 2026-05-27 | 评审: delegate_task V4 Flash

## Bug 清单

| # | 文件 | 问题 | 严重 | 修复方案 |
|:-:|:-----|:-----|:----|:---------|
| 1 | score_stocks.py:62 | self.w 未初始化 | HIGH | self.w.get -> self.scorer.w.get |
| 2 | strategy_pipeline.py:273-277 | daily_std/daily_values 未定义 | HIGH | 从 result 提取或初始化默认值 |
| 3 | evolution_engine.py:157 | pred_scores 未定义 | HIGH | 改为 scores |
| 4 | strategy_pipeline.py:251-258 | walk_forward 非时间序列分割 | MEDIUM | 按时间窗口前80%/后20%分割 |

## 验收标准
1. 语法验证通过
2. 函数签名不变
3. walk_forward 使用时间序列分割
