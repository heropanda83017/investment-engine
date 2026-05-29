# ARCH: FactorHub 208因子集成到评分体系
> 生成: 2026-05-27 | 评审: V4 Flash + V4 Pro

## 现状

| 问题 | 说明 |
|:-----|:------|
| `/factors/values` 端点不存在 | 无法获取个股因子值 |
| `fetch_factor_values` 已改为返回参考数据 | 208因子定义+分类+Sharpe |
| `batch_factorhub_scores(codes)` 仍按个股因子值逻辑 | 调用时返回空 |
| `factorhub_score()` 期望个股因子值 | 无法处理参考数据 |
| build_features.py 中 `w.factorhub=0.05` | 死代码，永远得0分 |

## 设计方案

### 改造方向

把 FactorHub 的 208 因子参考数据用于**因子质量评分**，而非个股因子值评分。

### 具体改动

#### 1. factorhub_source.py
- 新增 `factorhub_quality_score()` — 基于208因子参考数据计算市场整体因子质量
- 改造 `batch_factorhub_scores()` — 不再传 codes，返回整体质量分
- 删除已废弃的 `_use_cache_fallback`、`_get_cached_response`

#### 2. build_features.py
- 修改 `factor_frameworks()` 或新增 FactorHub 调用点
- 改为每日取一次 FactorHub 质量分，加入总评分

#### 3. ScoringEngine
- 在 batch_score 中增加 factorhub 维度

### 评分逻辑

```
factorhub_quality_score(ref_data):
  1. 统计高Sharpe因子数 (sharpe > 0.5) → 得分1
  2. 因子类别覆盖度 (覆盖几类) → 得分2
  3. 平均Sharpe → 得分3
  综合 = 得分1*0.4 + 得分2*0.3 + 得分3*0.3
  归一化到 [0, 100]
```

### 验收标准
- [ ] `factorhub_quality_score(ref)` 返回有意义的分数
- [ ] `batch_factorhub_scores()` 不报错
- [ ] build_features.py 中 FactorHub 权重实际生效
- [ ] daily_rank.csv 中出现 factorhub 列且非空
