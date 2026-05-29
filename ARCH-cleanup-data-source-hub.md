# ARCH: data-source-hub 旧目录清理
> 生成: 2026-05-27 | 评审: delegate_task V4 Flash

## 背景

`E:/AIGC-KB/输出/data-source-hub/` 已重命名为 `investment-engine/`，
旧目录仅剩 README.md shim（619 bytes）。现需彻底清理。

## 扫描结果

### 需要操作的部分

| 文件 | 问题 | 操作 |
|:-----|:-----|:-----|
| data-source-hub/ 旧目录 | 仅剩 README.md shim | **删除** |
| daily_pipeline.py L15 | 硬编码 data-source-hub 路径 | **修复** 为 investment-engine |
| config_loader.py + 12个文件 | DSH_PATH 变量名 (值已指向新路径) | **重命名** 为 IE_SCRIPTS |

### 已知但本次不处理

| 范围 | 原因 |
|:-----|:------|
| SKILL.md / wiki 引用 | 路径引用是文档说明性质，不影响运行 |
| Sessions JSON / pastes | 历史记录，无需修改 |

## 验收标准

1. 旧 data-source-hub/ 目录被删除
2. daily_pipeline.py 路径指向 investment-engine
3. config_loader.py + 12个消费者文件的 DSH_PATH → IE_SCRIPTS 重命名完成
4. 所有文件 YAML/Python 语法正确
5. 现有 cronjobs 正常工作
