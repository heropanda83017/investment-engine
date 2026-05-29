# ARCH: 全系统健康检查 + 缺陷修复 v1.2

**日期**: 2026-05-27
**状态**: DRAFT（待Claude Code审核）
**关联**: 承接 ccswitch 修复 + 三角色流水线 v2.3

---

## 一、背景与目标

### 1.1 背景
昨晚（5/26）完成 ccswitch 配置修复 + Claude Code 集成强化 + blackhorse-ai 系统审计修复。今晨早间检查发现3个异常：

1. **watchdog_check.py 脚本缺失**：cronjob `watchdog-daily`（job_id: 7f909f40def3）引用此脚本，但 `~/.hermes/profiles/ai-investor/scripts/` 下仅存在 `daily_pipeline.py`。该 job 配置为 `no_agent: true` + 9:00 触发，当前脚本不存在将导致运行失败。
2. **news_pipeline 今早可能未成功输出**：`news_db/` 无今日（20260527）文件，但昨日 signal 已生成（signal_2026-05-26.json）。
3. **blackhorse-ai/outputs/ 目录不存在**：需要确认是否为目录结构问题，或是新系统尚未首次运行。

### 1.2 目标
- **P0**：创建 `watchdog_check.py` 脚本，覆盖：ccswitch进程存活、DeepSeek API连通性、API Key 有效性、昨日pipeline是否执行成功
- **P1**：手动触发 news_pipeline 验证输出，确认 pipeline 是否正常
- **P1**：检查 blackhorse-ai 目录结构完整性，创建缺失的 outputs/ 目录
- **P2**：验证 ccswitch 修复后 Claude Code 5个新 Skill 是否可调用

---

## 二、方案设计

### 2.1 watchdog_check.py

```
输出: stdout（no_agent模式，空stdout=静默，非空=发送给用户）
调度: 工作日9:00，通过cronjob no_agent模式执行
检查项:
  1. ccswitch 进程存活 → ps aux | grep ccswitch
  2. DeepSeek API 连通 → curl -s -o /dev/null -w "%%{http_code}" https://api.deepseek.com/v1/models
  3. API Key 有效性 → 检查 config.yaml 中 api_key 是否存在
  4. 昨日信号检查 → 检查 signals/ 下是否有昨天日期的文件
  5. 系统时间校准 → 输出当前时间对比
```

### 2.2 news_pipeline 检查

手动执行 news_pipeline.py，观察 import/dependency 错误 + 输出写入 news_db/

### 2.3 blackhorse-ai 目录修复

创建 outputs/ 目录树：outputs/ outputs/raw/ outputs/reports/ logs/

### 2.4 ccswitch 修复验证

检查5个Claude Code Skill是否在skill列表中：claude-env-health, claude-review-automation, claude-iteration-loop, claude-context-inject, claude-agent-watchdog

---

## 三、风险与预案

| 风险 | 概率 | 预案 |
|------|------|------|
| news_pipeline 缺少依赖 | 中 | pip install 缺失包 |
| ccswitch 配置未持久化 | 低 | 重新执行 ccswitch reconcile |
| Claude Code Skill 路径错误 | 低 | 从昨晚会话提取内容重建 |
| watchdog 脚本路径不对（Windows git-bash） | 中 | 用 Python 替代 bash，保持 no_agent 兼容 |

---

## 四、执行计划

```
Step 1: [ENGINE] 创建 watchdog_check.py + 更新 cronjob
Step 2: [ENGINE] 手动触发 news_pipeline + 检查输出
Step 3: [ENGINE] 修复 blackhorse-ai 目录结构
Step 4: [ENGINE] 验证 ccswitch + Claude Code Skill
Step 5: [FINAL REVIEW] Claude Code V4 Pro 审核全部变更
---
