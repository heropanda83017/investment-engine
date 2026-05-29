# ARCH: MCP 信源接入 --- StockStar + FinanceMCP
> 生成: 2026-05-27 | 评审: delegate_task V4 Flash

## 背景

新增两个金融数据 MCP 信源，通过 SSE 协议接入 Hermes Agent。

## 方案

### 配置变更

在 `~/.hermes/config.yaml` 的 `mcp_servers:` 段新增两项：

```yaml
mcp_servers:
  # ... 已有配置 (wudao, brave_search, firecrawl, puppeteer_browser, tavily)

  stockstar:
    enabled: true
    url: https://bdzxmcp.stockstar.com/sse?key=YOUR_KEY_HERE
    connect_timeout: 30
    timeout: 60
    # Key 申请: 发邮件至 sslink@stockstar.com，说明 MCP 接入用途

  finance-mcp:
    enabled: true
    url: http://106.14.205.176:3101/sse
    connect_timeout: 15
    timeout: 30
    # 免费公共云服务，无需 Key
```

### 数据流

Hermes Agent -> wudao MCP (实时盘面，已有)
Hermes Agent -> stockstar MCP (ESG/调研/DCF，新增)
Hermes Agent -> finance-mcp MCP (分钟K线/美股/港股，新增)

## 影响分析

- StockStar Key 未申请: 先配置占位
- FinanceMCP 第三方不稳定: 设 timeout(30s)
- 语法错误风险: 参照 wudao 格式

## 验收标准

1. finance-mcp 配置后 Hermes 可加载
2. StockStar 配置语法正确
3. 已有 MCP 不受影响
