# ARCH: 全系统健康检查 + 缺陷修复 v1.3

**日期**: 2026-05-27
**状态**: APPROVED（Claude Code审核 4.5/10 → 已修正）
**审核人**: Claude Code (V4 Pro)
**审核反馈**: Windows兼容性3/10 → 全Python实现; 自身崩溃检测缺失 → 增加哨兵文件

---

## 一、背景与目标

### 1.1 背景
今晨早间检查发现3个异常：
1. **watchdog_check.py 脚本缺失** — cronjob引用但不存在
2. **news_pipeline 今早可能未成功输出** — news_db/ 无今日文件
3. **blackhorse-ai/outputs/ 目录不存在**

### 1.2 目标
- **P0**: 创建全Python实现的watchdog_check.py（不依赖shell命令）
- **P1**: 手动触发news_pipeline验证输出
- **P1**: 创建blackhorse-ai缺失目录结构
- **P2**: 验证ccswitch + Claude Code 5个新Skill

---

## 二、修订后方案

### 2.1 watchdog_check.py（全Python实现）

**架构变更**:
- 纯Python + stdlib（urllib + subprocess + os），零shell依赖
- 模块化检查函数，各自try/except隔离
- sentinel文件机制：每次运行时在脚本同级写入timestamp文件，cron调度器可通过检验sentinel判定watchdog是否实际执行过
- 退出码规范：0=静默（全部正常），1=有告警输出

**检查项**:
1. **ccswitch进程存活** — `subprocess.run('tasklist', capture_output=True)` + 查找字符串
2. **DeepSeek API连通** — `urllib.request.urlopen('https://api.deepseek.com/v1/models', timeout=10)`
3. **API Key有效性** — 检查config.yaml中api_key_env对应的环境变量非空
4. **昨日信号检查** — `os.path.exists(signals_dir)` + 匹配昨日日期
5. **system目录可写** — `os.access(path, os.W_OK)`
6. **磁盘空间** — `shutil.disk_usage()` 检查剩余空间

**告警分组**:
- CRITICAL（进程异常/API不通）→ 必输出
- WARNING（信号缺失/磁盘低）→ 输出
- INFO（全部正常）→ 静默，仅更新sentinel

### 2.2 news_pipeline 检查

手动执行 `python news_pipeline.py`，观察 import/dependency 错误，检查输出写入 news_db/

### 2.3 blackhorse-ai 目录修复

创建 outputs/ 目录树

### 2.4 ccswitch 修复验证

检查5个Claude Code Skill是否在列表中

---

## 三、修订后执行计划

```
Step 1: [ENGINE] 创建 watchdog_check.py（全Python）
Step 2: [ENGINE] 更新cronjob watchdog-daily引用新脚本
Step 3: [ENGINE] 手动执行 news_pipeline.py → 检查输出
Step 4: [ENGINE] 创建 blackhorse-ai outputs/ 目录树
Step 5: [ENGINE] 验证 ccswitch + Claude Code Skill
Step 6: [FINAL REVIEW] Claude Code V4 Pro 审核全部变更
---
