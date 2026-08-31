# P10-D 监控投影完成报告

## 交付结论

P10-D 已完成 SQLite 第一版落地。系统现在可以从审计事件派生低基数监控快照，并通过 checkpoint 继续投影；投影失败会停留在失败序列，不会静默跳过，修复后可以重放。

## 主要能力

| 能力 | 实现 |
| --- | --- |
| 任务指标 | submitted、started、succeeded、retrying、failed、failure rate |
| 阶段指标 | runs、成功/失败、累计耗时、最近耗时 |
| 检索/索引指标 | 请求结果、耗时、索引成功/失败次数 |
| 工具未知态 | 审计审查失败、未知或降级事件计数 |
| 队列状态 | queued/retrying 任务积压 |
| 索引状态 | 最近成功版本、成功时间和过期判断 |
| 审计状态 | 哈希链 valid、checked events |
| 投影状态 | checkpoint、失败序列、失败摘要指纹 |

## 接口

- GET /v1/metrics
- GET /v1/health/ready

指标接口支持按 metric_name 和 limit 查询；健康接口只返回摘要，不返回原文、Prompt、完整错误或用户输入。

## 验证

- 48 passed, 6 skipped
- Ruff 通过
- mypy 通过
- SQLite 运行时烟测通过

## 范围边界

本报告覆盖 SQLite 本地适配。Prometheus/OpenTelemetry exporter、Gel 监控存储和分布式指标后端留给 P10-F。
