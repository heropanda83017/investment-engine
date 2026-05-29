# ARCH: AnySearch MCP 接入与多通道搜索质量对比
> 生成: 2026-05-27 | 评审: delegate_task V4 Flash

## 背景
AnySearch MCP (anysearch-ai/anysearch-mcp-server, 639 stars) 是云端搜索基础设施，
支持通用搜索/垂域搜索/并行搜索/URL提取。需接入并与现有 DuckDuckGo + web_extract 对比。

## 测试方案

### 被测通道
| 通道 | 方式 | 定位 |
|:-----|:-----|:------|
| AnySearch search | MCP Streamable HTTP | 通用搜 + 垂搜 |
| AnySearch extract | MCP Streamable HTTP | URL正文提取 |
| DuckDuckGo (web_search_utils) | Python ddgs库 | 通用搜索 |
| web_extract (Hermes工具) | MCP | URL正文提取 |

### 测试查询 (5个投资相关)
1. "AAPL Q2 2026 earnings revenue" — 美股基本面
2. "AI chip market share 2026 NVIDIA AMD" — 行业竞争格局
3. "美联储利率决议 2026年6月" — 宏观政策
4. "新能源汽车销量 2026年5月" — 行业数据
5. "600519 贵州茅台 2026年一季度财报" — A股基本面

### 评估维度
| 维度 | 指标 | 权重 |
|:-----|:-----|:----:|
| 结果相关度 | 前3条是否命中目标 | 40% |
| 数据时效 | 结果是否最新 | 20% |
| 速度 | 端到端延迟 | 15% |
| 结果丰富度 | 是否有摘要/来源/结构化 | 15% |
| 稳定性 | 成功率 | 10% |

## 实施计划
1. 配置 AnySearch MCP (Streamable HTTP, 匿名)
2. 编写对比测试脚本
3. 运行5组查询对比
4. 输出对比报告

## 验收标准
1. AnySearch MCP 配置语法正确
2. 对比测试脚本可独立运行
3. 输出结构化对比报告
