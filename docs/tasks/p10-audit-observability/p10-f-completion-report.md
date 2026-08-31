# P10-F 外部后端与运维工具交付报告

状态：代码交付完成，Gel 在线迁移待目标环境执行  
日期：2026-08-31

## 1. 已交付

### Gel 审计持久化

- `GEL/dbschema/default.gel` 增加 `AuditEvent` 与 `AuditChainHead`；
- 新增 `GEL/dbschema/migrations/00003-p10f-audit.edgeql`；
- 新增 `GelAuditStore`，支持幂等 append、按事件/trace 查询、增量读取和 hash chain 校验；
- `apps/api/app/runtime.py` 在 `storage_backend=gel` 时使用 `GelAuditStore`，已有 Job、治理、Schema、检索等审计路径可复用同一端口。

### Trace 与 Metrics

- `OpenTelemetryTraceExporter`：把 P10 `TraceContext`/AuditEvent 映射为 OTel span；外部 SDK 通过可选依赖启用；
- `PrometheusMetricsExporter`：无 SDK 依赖输出标准 Prometheus exposition，标签沿用 `MetricSnapshot` 的低基数约束；
- `OpenTelemetryMetricsExporter`：以 observable gauge 发布快照，重复 export 不会把累计值重复加算；
- API 增加 `GET /v1/metrics/prometheus`，仍由 `MonitoringService` 负责投影和读取。

### 审计运维与恢复校验

- `export_audit`：导出完整有序 JSONL；
- `archive_audit`：gzip 压缩 JSONL，不删除活动审计记录；
- `verify_audit_export`：离线解析、重新计算 sequence/prev_hash/event_hash；
- `SQLiteBackupConsistencyChecker`：只读检查审计链、血缘端点、项目边界、重复边和稳定指纹；
- `compare_sqlite_backups`：比较备份前与恢复后的行数、审计链、血缘指纹和总指纹。

## 2. 验收结果

在 `apps/api` 执行：

```text
uv run pytest -q
58 passed, 6 skipped

uv run ruff check app ../../packages/personlogy_core/src/personlogy
All checks passed!

uv run mypy app ../../packages/personlogy_core/src/personlogy
Success: no issues found in 118 source files

git diff --check
通过（仅有 Git 的 LF/CRLF 提示）
```

新增覆盖包括：JSONL/gzip 导出与篡改检测、备份复制与恢复后链校验、血缘端点检查、Prometheus 文本、Trace context 和 OTel gauge 去重；Gel schema contract 也已覆盖。

## 3. 上线前动作

本开发环境没有运行中的 Gel 服务，因此未宣称 00003 migration 已应用。目标 Gel 环境执行：

```text
cd GEL
gel migrate --dsn <DSN>
```

完成迁移后，运行设置 `PKS_STORAGE_BACKEND=gel`、`PKS_QUEUE_BACKEND=gel` 的 API/worker 集成测试，至少验证一条审计 append、重复 append、查询和链校验；失败时不应把旧库标记为已升级。

OTel/Prometheus 部署按需安装 `personlogy-core[observability]`，没有这些依赖时 SQLite 本地核心路径仍可运行，Prometheus 文本导出本身不依赖 `prometheus-client`。
