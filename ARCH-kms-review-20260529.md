# ARCH: KMS 模块全面检查

> 生成: 2026-05-29 | 评审: Claude Code V4 Pro

## 现状

KMS 引擎位于 E:/AIGC-KB/kms-engine/，管理 wiki 知识库 E:/AIGC-KB/wiki-AIGC-KB/ (140篇笔记)。

### 资产清单

| 类型 | 数量 | 说明 |
|:-----|:----:|:------|
| Python 脚本 | 13 | kms.py(入口) + 12 个工具脚本 |
| 配置 | 1 | config/ (空 __init__) |
| 测试 | 58行 | test_kms.py |
| 导航页 | 7 篇 | 均在 导航/ 目录，链接数=0 |
| Cronjob | 1 | kms-sync-check 每日09:00 |

### 已知问题

1. _path_setup.py 使用旧中文路径 E:/AIGC-KB/输出 (junction存在但应改为纯英文)
2. 7篇导航页链接数为0 (应链接到各自的笔记)
3. 无 CI/测试覆盖 (仅58行基础测试)
4. health_check 未覆盖 link_registry 完整性

## 检查范围

1. **代码健康**: 语法/导入/异常处理/硬编码
2. **架构合理性**: 模块间依赖/职责划分/冗余
3. **wiki 健康**: 孤岛笔记/链接完整性/导航页
4. **工程规范**: 测试/文档/配置管理

## 验收标准

1. 所有 .py 语法通过
2. 无硬编码路径 (除 env.py 外)
3. 7篇导航页链接数 > 0
4. health_check 覆盖 > 90%
5. cronjob kms-sync-check 可执行
