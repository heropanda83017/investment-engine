# ARCH: 回测验证层补强
> 生成: 2026-05-27 | 评审: delegate_task V4 Flash + V4 Pro

## 现状

| 文件 | 行数 | 已有 | 缺失 |
|:-----|:----:|:-----|:------|
| backtest.py | 372 | 完整回测引擎+PerformanceMetrics(7项指标) | 无回测报告输出、无过拟合检测 |
| backtest_engine.py | 167 | BacktestEngine+WF+策略对比 | 无报告集成 |
| walkforward.py | 78 | 基础WF调度 | 无结果可视化、无报告 |
| benchmark.py | 61 | 基础基准对比 | 无对比报告 |

## 设计方案

### 新增文件

#### 1. backtest_report.py
基于 report.py 渲染引擎，将 PerformanceMetrics.all_metrics() 输出为 HTML 报告。

内容:
- 净值曲线图（复用 plot_pnl_curve）
- 指标卡片（夏普/索提诺/卡玛/最大回撤/胜率/盈亏比）
- 滚动收益曲线
- 月度收益热力图
- 回撤分析图

#### 2. overfit_detector.py
过拟合检测工具集。

检测方法:
- 夏普比衰减: IS vs OOS 夏普比衰减率
- 交叉验证: 滚动窗口的夏普比分布
- 夏普比标准误: 置信区间估计
- 参数敏感性: 随机参数扰动后的表现稳定性

### 改造文件

#### 3. backtest.py
- run_portfolio 集成 overfit_detector
- run_single 输出扩展含 overfit_risk

#### 4. walkforward.py
- run() 输出扩展 + WF可视化报告

#### 5. benchmark.py
- 输出标准化为 dict
- 支持多基准对比

## 影响范围

新增: 2 文件 (backtest_report.py, overfit_detector.py)
改造: 3 文件 (backtest.py, walkforward.py, benchmark.py)
不影响: ic_analyzer, daily_review, pipeline, factor_tracker
依赖: report.py（渲染引擎已就绪）

## 风险点

- overfit_detector 统计方法需小心：要求至少 60 个交易日的 OOS 数据
- backtest.py 已有 372 行，以追加方法为主，不重构现有接口


## 补充：ARCH REVIEW 修正（2026-05-27）

### 验收标准
- [ ] backtest_report.py 能接收 PerformanceMetrics 输出，生成含净值曲线/指标卡片/月度热力的有效 HTML
- [ ] overfit_detector 在已知过拟合策略上检出风险，在无过拟合策略上给出低风险
- [ ] OOS < 60 日时静默跳过检测并输出 warning，不中断回测
- [ ] backtest.py run_portfolio 集成后全流程能传递 overfit_risk
- [ ] 存量 backtest.py 接口不变，调用方不受影响

### 降级策略
- OOS < 60 交易日: 跳过 overfit_detector，输出 "OOS insufficient" warning
- 渲染引擎异常: backtest_report.py 报错不影响回测主流程
- 参数敏感性测试: 默认最多遍历 50 组参数组合防指数爆炸

### 数据流
backtest.py(输出收益序列) → PerformanceMetrics(7指标) → backtest_report.py(HTML报告)
                                     ↓
                              overfit_detector.py(风险评估)
                                     ↓
                              backtest.py(输出扩展含overfit_risk)
