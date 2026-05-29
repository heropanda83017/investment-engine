# ARCH: 策略决策层强化
> 生成: 2026-05-27

## 现状

| 文件 | 行数 | 已有 | 缺失 |
|:-----|:----:|:-----|:------|
| position_sizing.py | 195 | 线性插值仓位计算 | 无凯利公式、无波动率动态调整 |
| risk_manager.py | 191 | 单股止损、行业检查 | 无 VaR、无相关性约束、无组合风险 |
| score_stocks.py | 102 | 基础评分引擎 | 权重硬编码，不可配置 |
| strategy_optimizer.py | 240 | 风险平价加权、市场状态识别 | 无多目标优化 |
| strategy_pipeline.py | 549 | 流水线调度、IC加权开关 | 无信号融合入口 |
| **signal_fusion.py** | ❌ | — | **信号融合层完全缺失** |

## 设计方案

### 新增文件

#### signal_fusion.py — 信号融合引擎
将多路信号统一为标准格式后融合为综合评分。

信号源:
- 因子信号 (Factor IC / alpha191 输出)
- 分析信号 (deep_analysis / stock_scanner 输出)
- 风控信号 (risk_manager 输出)
- 市场状态信号 (MarketRegime 输出)

融合方式: 加权投票 + 置信度校准

### 改造文件

#### position_sizing.py
- 新增凯利公式仓位 `kelly_position(cfg)`
- 新增波动率调整 `volatility_adjusted_position(base_pct, atr_ratio)`
- 旧接口 `calculate_position` 保持兼容

#### risk_manager.py
- 新增 VaR 计算 `compute_var(returns, level=0.95)`
- 新增相关性约束 `check_correlation(holdings, price_data)`
- 新增组合风险评分 `portfolio_risk_score(holdings)`

#### score_stocks.py
- 权重从硬编码改为可配置 (config.json)
- 接入 ICIR 加权结果作为动态权重来源

#### strategy_optimizer.py
- 新增多目标优化 `multi_objective_optimize(objectives)`
- 目标: 最大化夏普 / 最小化回撤 / 最大化胜率

## 影响范围

新增: 1 文件 (signal_fusion.py)
改造: 4 文件 (position_sizing.py, risk_manager.py, score_stocks.py, strategy_optimizer.py)
不影响: 数据源、因子计算、回测、复盘报告、流水线
依赖: ic_analyzer (ICIR权重)

## 风险点

- 凯利公式在高杠杆下激进 → 加入 fraction_kelly=0.25 保守参数
- VaR 在正态假设下低估尾部风险 → 加入历史模拟法作为补充
- 多目标优化计算开销 → 限制迭代次数
