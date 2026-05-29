# investment-engine — 投资体系统一代码底座

> 所有可执行代码统一归位于此。详见 `env.py` 路径定义和 `_path_setup.py` 导入入口。

## 目录结构

```
investment-engine/
│
├── _path_setup.py      ← 统一导入入口：ensure_dsh_paths() 替代所有 sys.path.insert
├── env.py               ← 单一路径源（IE_ROOT / IE_STRATEGIES / IE_PIPELINES ...）
├── config/
│   └── config.json      ← 统一配置（blackhorse + tracking 合并为层级结构）
│
├── scripts/             ← 数据采集层
│   ├── baostock_source.py     ← 首选K线信源（~30ms）
│   ├── tickflow.py            ← 实时逐笔流水线（东方财富push2）
│   ├── stock_analyst.py       ← 个股一站式分析
│   ├── stock_scanner.py       ← 一键选股+护城河+健康评级
│   ├── data_optimizer.py      ← 6信源降级链
│   ├── data_pipeline.py       ← 生产级批量管道
│   └── env.py                  ← 路径定义（所有模块共享）
│
├── strategies/          ← 原 blackhorse-ai/src/：量化策略模块
│   ├── fetch_data.py           ← 数据层（全市场获取+并发筛选）
│   ├── build_features.py       ← 因子层（6因子+Alpha191+18框架）
│   ├── score_stocks.py         ← 模型层（打分排序+LLM排雷）
│   ├── backtest.py             ← 回测层（多股组合+再平衡）
│   ├── risk_manager.py         ← 风控（P1-P5五道防线）
│   ├── evolution_engine.py     ← 进化（IC/IR/贝叶斯权重更新）
│   ├── analysis_frameworks.py  ← 18框架量化评分
│   └── ... (共26个.py文件)
│
├── pipelines/           ← 原 blackhorse-ai/scripts/：自动化流水线
│   ├── daily_pipeline.py       ← 每日15:30选股流水线
│   ├── weekly_tracker.py       ← 每周跟踪扫描
│   └── verify_predictions.py   ← 预测验证
│
├── tracking/            ← 预测跟踪系统
│   ├── predictions/            ← 每个预测独立JSON
│   └── tracker_config.json     ← 合并入 unified config
│
├── system/              ← 新闻管道+信号生成
│   ├── news_pipeline.py        ← AI新闻采集（08:00/20:00）
│   ├── news_factor_mapper.py   ← 新闻→因子权重映射
│   └── signal_generator.py     ← BUY/HOLD/SELL信号生成
│
└── _cache/              ← 统一缓存目录
```

## 导入方式

所有模块统一使用 `_path_setup.py`：

```python
from _path_setup import ensure_dsh_paths
ensure_dsh_paths()
# 然后直接 import 任何子模块
from env import IE_ROOT, IE_STRATEGIES
from fetch_data import DataEngine
```

## 配置层级

`config/config.json` 层级结构：

```json
{
  "version": "3.0",
  "blackhorse": { ... },    // 原 blackhorse-ai/config/config.json
  "tracking": { ... }       // 原 tracking/tracker_config.json
}
```

## 重要路径

| 路径 | env.py 变量 | 说明 |
|------|------------|------|
| `investment-engine/` | `IE_ROOT` | 代码底座根目录 |
| `investment-engine/scripts/` | `IE_SCRIPTS` | 数据采集层 |
| `investment-engine/strategies/` | `IE_STRATEGIES` | 策略层 |
| `investment-engine/pipelines/` | `IE_PIPELINES` | 流水线 |
| `investment-engine/tracking/` | `IE_TRACKING` | 跟踪系统 |
| `investment-engine/system/` | `IE_SYSTEM` | 新闻管道 |
| `investment-engine/config/` | `IE_CONFIG` | 配置目录 |
