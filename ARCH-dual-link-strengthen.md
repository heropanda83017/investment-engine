# ARCH: 投资体系双链路强化
> 生成: 2026-05-27 | 评审: delegate_task V4 Flash + V4 Pro

## 总体策略

双链路同时推进，每条链路独立模块、独立交付、互不阻塞。

```
方向A: 因子IC量化      方向B: 复盘报告引擎
  ├─ IC追踪仪表盘          ├─ 日复盘报告
  ├─ IC衰减曲线            ├─ 周复盘报告
  ├─ 因子淘汰机制          ├─ 信号vs实际对比
  └─ 因子权重动态调整      └─ 改进建议闭环
```

---

## 方向A: 因子IC量化体系

### 现状

| 文件 | 已有 | 缺失 |
|:-----|:-----|:------|
| factor_tracker.py (299行) | 基础IC计算、RankIC、ICIR框架 | 无衰减曲线、无滚动窗口 |
| ic_backfill.py (118行) | 回填IC到历史数据 | 无可视化、无报告输出 |
| strategy_pipeline.py (505行) | 流水线调度 | 因子权重仍为静态 |

### 设计方案

**新增文件:**
1. `ic_analyzer.py` — IC衰减曲线 + 滚动IC + 因子稳定性评分
2. `ic_report.py` — 生成IC报告 + 可视化图表

**改造文件:**
3. `factor_tracker.py` — 集成ic_analyzer, 输出IC滚动指标
4. `strategy_pipeline.py` — 因子权重从静态改为IC动态加权（IC加权开关，默认关闭）

### 验收标准
- [ ] 每周输出IC报告（含衰减曲线、RankIC、ICIR）
- [ ] 可查看每个因子的3月/6月/12月滚动IC
- [ ] 因子权重支持IC动态加权（开关可控）
- [ ] 报告输出为HTML可视化

---

## 方向B: 复盘报告引擎

### 现状

| 文件 | 已有 | 缺失 |
|:-----|:-----|:------|
| weekly_tracker.py (65行) | 周报模板 | 无实际数据填充 |
| daily_archive.py (38行) | 归档目录结构 | 无内容框架 |
| signal_generator.py (45行) | 信号输出 | 信号vs实际对比 |
| trade_ledger.py (87行) | 交易记录 | 无分析聚合 |
| report.py (19行) | 仅有框架 | 未实现 |
| visualization.py (58行) | 图表工具 | 未集成到报告 |

### 设计方案

**新增文件:**
1. `daily_review.py` — 日复盘报告（信号命中率、因子表现TOP/BOTTOM、市场状态）
2. `weekly_review.py` — 周复盘报告（IC周报、策略盈亏、调整建议）

**改造文件:**
3. `signal_generator.py` — 增加信号vs实际对比日志
4. `report.py` — 实现报告渲染引擎（复用visualization.py）
5. `weekly_tracker.py` — 集成report引擎输出完整HTML报告

### 验收标准
- [ ] 每日流水线末尾自动生成日复盘（信号命中率 + 因子日排名）
- [ ] 每周五输出周复盘（IC周变化、策略表现、下周调整建议）
- [ ] 报告以HTML格式保存到 reports/ 目录
- [ ] 支持"信号发出→实际走势"回溯对比

---

## 影响范围

```
受影响文件: 8个（4新增 + 4改造）
不影响: 数据源层、因子计算逻辑、回测引擎
```

## 风险点

- IC动态加权可能引入过拟合 → 开关默认关闭，只在分析模式下启用
- 复盘报告依赖流水线输出 → 日复盘挂接到daily_pipeline末尾


---

## 设计决策（2026-05-27 ARCH REVIEW 确认）

### D1: IC加权公式 → ICIR加权
**选型：** ICIR加权（IC / IC标准差）
**理由：** 惩罚波动大的因子，平衡信号强度与稳定性，量化策略主流实践。
**实现：** `weight_i = ICIR_i / sum(ICIR_j)`，当 ICIR_i < 0 时权重设为 0（反向因子不参与多头组合）。
**保护：** 开关 `use_ic_weighting` 默认关闭，开启时要求每个因子至少 20 期历史 IC 数据。

### D2: 报告渲染引擎 → Jinja2 + matplotlib PNG
**选型：** Jinja2 模板引擎 + matplotlib 静态图表 → 合并为 HTML 报告
**理由：** 轻量无额外依赖（Jinja2/matplotlib 已安装），避免 Plotly 文件膨胀，HTML 报告可在浏览器直接打开。
**存储：** reports/YYYY-MM/YYYY-MM-DD-{type}.html，保留 90 天自动清理。

### D3: 方向A → 方向B 依赖 → 并行解耦
**策略：** 方向B 的 IC 周报部分设计为独立模块 `ic_weekly_inserter`，预留接口 `get_ic_weekly_summary()`。方向A 的 ic_analyzer 完成后对接该接口，方向B 不阻塞。
**数据契约：** `ic_weekly_summary = {"factor": str, "rank_ic_5d": float, "rank_ic_20d": float, "icir_20d": float, "stability": float}`


### 补充: 因子稳定性评分算法
**公式：** `stability_score = ICIR_60d × sign(RankIC_60d) × min(1.0, n_samples/120)`
**解释：** 
- ICIR_60d：60日滚动ICIR，衡量信号强度与一致性的比值
- sign(RankIC_60d)：方向一致性惩罚（60%以上同向才给正分）
- min(1.0, n_samples/120)：冷启动保护，至少120个样本点才给满分
- 评分范围 [-1.0, 1.0]

### 补充: 滚动IC窗口配置
默认三档（3月=60交易日 / 6月=120交易日 / 12月=240交易日），通过 `ic_windows = [60, 120, 240]` 配置，支持自定义。

### 补充: 非交易日处理
- 日复盘：仅交易日生成，通过 trading_calendar 判断
- 周复盘：每周最后一个交易日生成（不硬编码周五）
- IC报告：每周最后一个交易日生成周度IC

### 补充: 报告存储策略
- 目录结构：`reports/daily/YYYY-MM/` 和 `reports/weekly/YYYY-MM/`
- 保留策略：日报告保留 30 天，周报告保留 12 个月
- 清理：每次生成新报告时触发旧报告清理
