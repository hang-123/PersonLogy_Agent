# P10-D 监控投影开发记录

## 边界盘点

- `AuditSink` 已提供事件追加、列表和链校验能力，但需要补充按 sequence 增量读取能力。
- `StageRunner` 已统一产生 `stage.started`、`stage.succeeded`、`stage.failed` 和 `duration_ms`，适合作为阶段指标事实源。
- `JobService` 已产生 `job.submitted`、`job.started`、`job.retrying`、`job.succeeded`、`job.failed` 事件。
- `SQLiteJobQueue` 的队列事实由 `job` 表状态体现；排队深度可由 `queued/retrying` 状态查询。
- 索引版本和成功时间保存在 `retrieval_index_build`，可直接用于新鲜度检查。
- API 请求的 `request_id/trace_id` 中间件已存在，本阶段补充请求计数和耗时事件/指标投影，不重复建设 Trace 系统。

## 初始指标口径

- `jobs.submitted_total`、`jobs.succeeded_total`、`jobs.failed_total`、`jobs.retrying_total`；
- `jobs.failure_rate` = failed / (succeeded + failed)，无分母时为 0；
- `stages.duration_ms` 按 stage 记录累计次数、总耗时和最后一次耗时；
- `queue.backlog` = queued + retrying；
- `index.last_success_at`、`index.age_seconds`；
- `audit.chain_valid`、`audit.events_checked`；
- `tools.unknown_state_total` 统计审计失败/降级/未知状态事件。

## 安全约束

- 指标标签只允许事件类型、阶段名、任务类型、工具名等有限枚举字段；
- 不把 `trace_id`、`request_id`、原文、Prompt、错误全文写入 tags 或 snapshot；
- 健康接口只返回摘要状态和计数，不返回审计原文。

## 实现结果

- 新增 MetricSnapshot、ProjectionFailure 和 MetricsProjectionStore/OperationalProbe 端口。
- SQLite 新增 metric_snapshot、metrics_projection_checkpoint、metrics_projection_failure 三张派生表。
- MetricsProjector 支持批量增量投影、checkpoint 续投、失败停留、失败重放和全量重建。
- MonitoringService 汇总任务失败率、工具未知态、队列积压、索引新鲜度、数据库状态和审计链状态。
- 新增只读 /v1/metrics，并扩展 /v1/health/ready 的 monitoring 摘要。
- StageRunner 已有的阶段开始/成功/失败及 duration_ms 事件成为阶段指标事实源；检索和索引成功/失败事件补充 duration_ms。

## 验证结果

- P10-D 专项测试：4 passed
- 全量测试：48 passed, 6 skipped
- Ruff：通过
- mypy：通过（106 个源文件）
- SQLite 运行时烟测：/v1/health/ready 和 /v1/metrics 均返回 200
