# Investment Engine — A 股量化投资体系

多因子量化选股系统，覆盖**数据采集 → 因子生成 → 信号融合 → 风控过滤 → 回测验证 → 每日流水线**全链路。

## 系统架构

```
数据层 (scripts/)          →   因子层 (strategies/)       →   决策层 (system/)
  baostock (30ms K线)           趋势/资金流/量能               信号生成 (BUY/HOLD/SELL)
  tickflow (实时逐笔)           波动率/Alpha191                风控 (P1-P5 防线)
  wudao MCP (行情/资金)         情绪/行业/事件                 仓位管理
  tushare/akshare (财务)        18 分析框架评分                 AI 新闻分析
                                IC 量化评估                    组合优化

  ↓
流水线层 (pipelines/)       →   输出
  每日 15:30 选股               信号清单
  每周跟踪扫描                  因子效能报告
  Walkforward 回测              回测报告
  IC 回填                       日报/周报
```

## 目录结构

```
investment-engine/
│
├── _path_setup.py          统一导入入口
├── env.py                  单一路径源（IE_ROOT / IE_STRATEGIES / ...）
├── requirements.txt        依赖清单
│
├── scripts/                数据采集层（13 模块）
│   ├── baostock_source.py      ← 首选K线信源（~30ms）
│   ├── tickflow.py             实时逐笔流水线（东方财富 push2）
│   ├── stock_analyst.py        个股一站式分析
│   ├── stock_scanner.py        一键选股 + 护城河 + 健康评级
│   ├── data_optimizer.py       6 信源降级链
│   ├── data_pipeline.py        生产级批量数据管道
│   ├── wudao_mcp_reader.py     悟道 MCP 行情读取器
│   ├── env.py                  路径/环境变量定义
│   └── ...
│
├── strategies/             量化策略模块（43 模块）
│   ├── fetch_data.py           数据层（全市场获取）
│   ├── build_features.py       因子层（6 大类 + Alpha191 + 18 框架）
│   ├── score_stocks.py         模型层（打分排序 + LLM 排雷）
│   ├── factor_tracker.py       IC 量化追踪（RankIC/xIC/ICIR）
│   ├── backtest_engine.py      回测引擎（多股组合 + 再平衡）
│   ├── risk_manager.py         风控（P1-P5 五道防线）
│   ├── evolution_engine.py     进化（贝叶斯权重更新）
│   ├── signal_fusion.py        多信号融合
│   ├── position_sizing.py      仓位管理（Kelly + 风险预算）
│   ├── analysis_frameworks.py  18 框架量化评分
│   ├── alpha191_factors.py     Alpha191 因子库
│   ├── strategy_pipeline.py    策略执行管道
│   ├── ic_analyzer.py          IC 深度分析
│   ├── overfit_detector.py     过拟合检测
│   ├── deep_analysis.py        深度个股分析
│   └── ...
│
├── pipelines/              自动化流水线（7 模块）
│   ├── daily_pipeline.py       每日 15:30 选股（S01-S05 五步）
│   ├── weekly_tracker.py       每周跟踪扫描
│   ├── walkforward.py          Walkforward 回测
│   ├── ic_backfill.py          IC 历史回填
│   ├── verify_predictions.py   预测验证
│   └── benchmark.py            基准测试
│
├── system/                 信号/风控/新闻（12 模块）
│   ├── signal_generator.py     信号生成（BUY/HOLD/SELL）
│   ├── news_pipeline.py        AI 新闻采集（08:00/20:00）
│   ├── news_factor_mapper.py   新闻 → 因子权重映射
│   ├── ai_intel.py             AI 智能分析
│   ├── daily_archive.py        每日归档
│   └── ...
│
├── tracking/               预测跟踪
│   └── __init__.py
│
├── config/
│   ├── config.json             统一配置（层级结构）
│   └── backup/                 修复前快照（不含仓库）
│
├── examples/               快速上手
│   ├── quick_start.py
│   ├── batch_analysis.py
│   └── search_benchmark.py
│
├── reports/                自动生成报告（不在仓库）
├── _cache/                 缓存（不在仓库）
└── logs/                   日志（不在仓库）
```

## 数据源

| 信源 | 用途 | 延迟 | 获取方式 |
|------|------|------|---------|
| **baostock** | A 股日 K 线 | ~30ms | Python SDK 直连 |
| **tickflow** | 实时逐笔/快照 | 5 秒级轮询 | 东方财富 push2 API |
| **wudao MCP** | 实时行情/资金流/龙虎榜 | 实时 | MCP 流式接口 |
| **tushare** | 财务报表/估值/北向资金 | T+1 | HTTP API |
| **akshare** | 基金/期货/宏观/行业指数 | 实时 | HTTP API |

## 因子体系

### 六大核心因子

| 因子 | 权重 | 说明 |
|------|:----:|:-----|
| **资金流** | ~20% | 主力资金净流入/流出，大单追踪 |
| **趋势** | ~14% | 动量指标、均线排列、52 周新高 |
| **量能** | ~10% | 成交量变化、换手率异常 |
| **波动率** | ~10% | 波动率收缩/扩张，ATR |
| **基本面** | ~14% | ROE、毛利率、营收增速 |
| **Alpha191** | ~14% | 101 个因子精选子集 |

### IC 量化评估

每个因子通过 **RankIC / xIC / ICIR** 三维评估预测力：

```
RankIC → 方向正确性（>0.02 有效）
xIC    → 区分度（>0.05 可交易）
ICIR   → 稳定性（>0.5 持续有效）
```

因子权重通过 **贝叶斯进化引擎** 动态更新，优胜劣汰。

## 信号生成

### 五级信号

| 信号 | 置信度 | 说明 |
|:----:|:------:|:-----|
| **BUY** | ≥0.70 | 多因子共振 + 风控通过 |
| **HOLD** | 0.40-0.69 | 持有观察，不加仓 |
| **SELL** | ≤0.39 | 触发止盈/止损/风控 |

### 道氏三阶段识别

系统自动识别个股所处阶段：
- **吸筹** → 建仓窗口
- **公众参与** → 主升持有
- **派发** → 减仓/卖出

## 风控体系（P1-P5）

| 防线 | 检查项 | 处罚 |
|:----:|:-------|:----:|
| P1 | 大盘风险（指数破位/系统风险） | 禁止买入，强制减仓 |
| P2 | 行业/板块风险 | 降低行业权重 |
| P3 | 个股基本面（财报/质押/商誉） | 排除/减仓 |
| P4 | 个股技术面（破位/异常量/ST） | 排除/减仓 |
| P5 | 仓位/组合集中度 | 超限强制再平衡 |

## 每日流水线

系统每日 15:30 自动执行：

```
S01: 更新全市场数据          → baostock + tickflow
S02: 计算所有因子值          → 6 因子 + Alpha191
S03: 因子打分 + IC 校准      → IC 加权
S04: 信号生成 + 风控过滤    → BUY/HOLD/SELL
S05: 输出信号清单            → 日报 + JSON
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量（复制然后填入 API Key）
cp .env.example .env

# 运行每日流水线
python pipelines/daily_pipeline.py

# 回测
python pipelines/walkforward.py

# 个股分析
python scripts/stock_analyst.py --code 000725

# 查看因子效能
python strategies/ic_report.py

# 全量扫描选股
python scripts/stock_scanner.py
```

```python
# 或代码中调用
from _path_setup import ensure_dsh_paths
ensure_dsh_paths()

from env import IE_ROOT, IE_STRATEGIES
from fetch_data import DataEngine
from score_stocks import StockScorer

engine = DataEngine()
scorer = StockScorer()
```

## 配置

`config/config.json` 层级结构：

```json
{
  "version": "3.0",
  "blackhorse": {
    "project": { "name": "blackhorse-ai", "version": "1.0.0" },
    "data": { "cache_ttl_hours": 6 },
    "screening": {
      "min_price": 3,
      "min_volume_20d": 50000000,
      "max_gain_20d": 80
    },
    "factors": { "trend": {"weight": 0.1429}, "volume": {"weight": 0.0952} }
  },
  "signals": {
    "buy_threshold": 0.70,
    "sell_threshold": 0.39
  },
  "risk_management": {
    "max_positions": 10,
    "max_single_weight": 0.15,
    "stop_loss": -0.08,
    "max_sector_weight": 0.30
  }
}
```

## API Key 配置

所需 API Key（写入 `.env`）：

| 变量 | 来源 | 用途 |
|:-----|:-----|:-----|
| `DEEPSEEK_API_KEY` | DeepSeek | LLM 分析/因子打分 |
| `TUSHARE_API_TOKEN` | Tushare Pro | 财务/基本面数据 |
| `MCP_WUDAO_API_KEY` | 悟道数据 | 实时行情/资金流 |

## 依赖

```
pandas>=2.0
numpy>=1.24
matplotlib>=3.7
backtrader>=1.9
scipy>=1.10
jinja2>=3.1
requests>=2.31
python-dotenv>=1.0
```

---

> **免责声明：** 本系统仅供学习和研究参考，不构成任何投资建议。股市有风险，投资需谨慎。所有信号和数据仅供参考，使用者应独立判断并承担投资风险。
