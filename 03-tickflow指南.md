# 03 - TickFlow 信源指南

## 概述

基于东方财富push2 API的A股实时逐笔/快照数据采集管线。

## 接口速查

```python
from tickflow import TickFlow
tf = TickFlow()

# 实时快照（盘中秒级）
data = tf.fetch_real_time(codes=["600519", "002371"])
# -> [{"code": "600519", "price": 1290, "change_pct": -0.06, ...}]

# 单次采集+存储
n = tf.collect_once()

# 轮询采集60秒
n = tf.collect_loop(duration_sec=60)

# CLI
# python tickflow.py collect
# python tickflow.py loop 60
# python tickflow.py fetch 600519
```

## 关键指标

| 项目 | 值 |
|:-----|:----|
| 延迟 | 单只176ms / 批量5只519ms |
| 更新频率 | 秒级（实时） |
| 认证 | 无需Key |
| 限制 | 非官方API，~50req/sec |
| 保护机制 | 3次重试 + 10次熔断 + 5min冷却 |
| 配置 | E:/AIGC-KB/输出/tickflow_config.json |

## 监控标的（15只）

```
600519 贵州茅台  000858 五粮液  002415 海康威视
600036 招商银行  300750 宁德时代 002371 北方华创
688981 中芯国际  601138 工业富联 002230 科大讯飞
300124 汇川技术  000333 美的集团 688041 海光信息
603501 韦尔股份  300308 中际旭创 002594 比亚迪
```
