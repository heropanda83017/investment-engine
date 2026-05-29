# ARCH: 投资能力进化系统 v1.1 (REVIEW反馈修复版)

## Claude Code REVIEW 发现的9个问题及修复

| # | 问题 | 严重度 | 修复方案 |
|---|------|--------|----------|
| 1 | 信号规则引用了未定义的组件 | HIGH | signal_generator.py: 明确定义5项框架检查(护城河/安全边际/周期/偏差/量价),每项有PASS/FAIL标准 |
| 2 | 模块间缺少JSON schema定义 | MEDIUM | 每模块顶部docstring包含输入输出schema定义 |
| 3 | 权重更新缺少归一化 | MEDIUM | evolution_engine.py: update_w()后增加sum=1.0归一化步骤 |
| 4 | per-factor accuracy难以计算 | MEDIUM | 改用macro-averaged accuracy + hash-based proxy分配, doc说明限制 |
| 5 | 框架PASS阈值是magic number | MEDIUM | 阈值配置化: tracker_config.json中可调, signal_generator.py使用>=而非> |
| 6 | score=55边界歧义 | LOW | 使用>=55 (BUY), >=40 (HOLD), <40 (SELL) |
| 7 | 输出目录未定义 | LOW | 每模块硬编码: impacts/, signals/, evolution/ 均在system/下 |
| 8 | 冷启动策略缺失 | LOW | 预置default_scores字典, 有新闻数据则叠加, 无则用纯因子评分 |
| 9 | 无mock数据测试计划 | LOW | 已内置cold-start数据, 可脱离外部API运行 |