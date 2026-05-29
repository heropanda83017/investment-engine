# ARCH: 因子实验室 — 持续实现→测试→优化闭环
> 生成: 2026-05-27 | 评审: V4 Flash + V4 Pro

## 现状

| 维度 | 数据 |
|:-----|:------|
| alpha191 已实现 | 10/191 个 |
| FactorHub 参考数据 | 208 因子定义+Sharpe+类别 |
| IC 追踪框架 | factor_tracker.py 已有 |
| 因子权重调优 | ICIR 加权已有（默认关闭） |
| 因子淘汰机制 | 无 |
| 因子优先级排序 | 无 |

## 设计方案

### 新增: factor_lab.py — 因子实验室引擎

一条命令完成：获取 FactorHub 推荐 → 生成 alpha 代码 → IC 追踪 → 淘汰决策。

```
factor-lab 三个子命令:
  python -m factor_lab recommend     # 基于FactorHub推荐下一批实现的因子
  python -m factor_lab implement     # 生成未实现alpha的代码骨架
  python -m factor_lab report        # 当前因子IC表现报告 + 淘汰建议
```

### 核心逻辑

#### 1. recommend — 推荐实现优先级

```
factor_lab.recommend()
  ├─ 从 FactorHub 获取 208 因子参考数据
  ├─ 按 Sharpe 降序排列
  ├─ 排除已在 alpha191_factors.py 中实现的
  ├─ 按类别分组（动量/价值/质量/...）
  ├─ 输出 Top 20 待实现因子清单
  └─ 标注: 实现难度(简单/中等/复杂) + 期望Sharpe
```

#### 2. implement — 生成 alpha 代码

```
factor_lab.implement(factor_code)
  ├─ 从 FactorHub 获取因子定义
  ├─ 解析: name/description/category/公式思路
  ├─ 基于公式思路生成 alpha_XXX() 函数代码
  ├─ 追加到 alpha191_factors.py
  └─ 输出新函数代码，人工审核后合并
```

#### 3. report — IC 表现报告

```
factor_lab.report()
  ├─ 从 factor_tracker 读取各 alpha IC 数据
  ├─ 计算: 20日/60日/120日 RankIC
  ├─ 标记: 有效(IC>0.02) / 无效(IC<0) / 待观察
  ├─ 淘汰建议: 连续120日IC<0 → 移除
  ├─ 权重建议: ICIR 加权
  └─ 输出: 因子健康报告
```

### 依赖

- factorhub_source.py (208参考数据)
- factor_tracker.py (IC追踪)
- alpha191_factors.py (目标文件)
- build_features.py (权重配置)

### 验收标准

- [ ] `factor_lab recommend` 输出 Top 10 推荐因子
- [ ] `factor_lab report` 输出因子 IC 健康报告
- [ ] 因子淘汰建议可以自动生效
