# ARCH: Cronjob Workdir 中文路径修复
> 生成: 2026-05-28 | 评审: delegate_task V4 Flash -> Claude Code V4 Pro FINAL REVIEW

## 现状

**问题**: 全部 10 个 cronjob 的 `last_run_at: null` --- 调度器从未成功执行过任何 job。

**根因**: 各 job 的 `workdir` 参数使用了含中文的路径 `E:\AIGC-KB\输出\...`，导致 cron 调度器在解析路径时失败。

**已修复的前提（2026-05-27）**: junction `E:\AIGC-KB\output` -> `E:\AIGC-KB\输出` 已创建且 verified。文件系统层面英文路径可直达。

## 受影响的 Job 清单

共 10 个 cronjob，其中 7 个含工作目录参数需更新：

| # | Job ID | 名称 | 目标 workdir |
|---|--------|------|-------------|
| 1 | 9768bcc27709 | ie-daily-pipeline | E:\AIGC-KB\output\investment-engine |
| 2 | 60dd48f0c2f6 | ie-daily-report | E:\AIGC-KB\output\investment-engine |
| 3 | 04ea51299177 | ie-industry-intel | E:\AIGC-KB\output\investment-engine |
| 4 | ab1910fda411 | ie-weekly-tracking-scan | E:\AIGC-KB\output\investment-engine |
| 5 | e2b7af48eaa3 | ie-news-morning | E:\AIGC-KB\output\investment-engine\system |
| 6 | d8cb04408b7b | ie-news-evening | E:\AIGC-KB\output\investment-engine\system |
| 7 | 7478abf4877a | ie-evolution-saturday | E:\AIGC-KB\output\investment-engine |

剩余 3 个无中文路径，无需修改。

## 方案

使用 `cronjob(action='update', job_id=..., workdir=...)` 逐一更新 7 个含中文路径的 job。

## 验收标准

1. `cronjob list` 中所有 workdir 不包含中文
2. script-based job 的目标路径存在且含对应脚本文件
3. 手动运行至少一个 job 确认调度器能正常触发
