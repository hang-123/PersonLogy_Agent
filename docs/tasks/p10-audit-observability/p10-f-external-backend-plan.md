# P10-F 外部后端与运维工具落地计划

状态：开发中  
范围：Gel 审计持久化、Trace/Metrics 导出、审计运维工具、备份恢复一致性校验

## 1. 收敛目标

P10-F 只把已经稳定的 P10 端口接到外部后端和运维流程，不改变业务模块的职责，也不把外部 SDK 变成 SQLite 本地运行的强制依赖。

本阶段交付五项能力：

1. `GelAuditStore`：在 Gel 中以追加方式保存 `AuditEvent`，维护全局 sequence/hash head，并提供查询和链校验；
2. `OpenTelemetryTraceExporter`：将 P10 `TraceContext` 和阶段边界映射为 OTel span，SDK 不可用时显式失败；
3. `PrometheusMetricsExporter` 与 `OpenTelemetryMetricsExporter`：从 P10 指标快照输出 Prometheus exposition 或调用 OTel Meter，指标标签保持低基数且不包含原文；
4. 审计导出、归档、校验：输出受控 JSONL，归档使用 gzip，校验重新计算事件哈希链；
5. 备份/恢复一致性：对 SQLite 或导出的快照生成审计链、血缘行数、端点和稳定指纹报告，并比较恢复前后差异。

## 2. 实施顺序

### F1：边界盘点与 schema

- 复用现有 `AuditSink`、`LineageStore`、`MetricSnapshot`；
- 新增 Gel `AuditEvent`、`AuditChainHead` 类型和迁移；
- Gel adapter 保持可选运行路径，未配置 Gel 时不影响 SQLite/memory。

### F2：运维工具

- 通用 `AuditOperations` 依赖 `AuditSink`，不直接依赖 SQLite；
- 导出字段来自 `AuditEvent` 的 canonical envelope，metadata 继续经过既有白名单；
- 归档不删除活动审计记录，校验报告包含 checked count、head hash 和失败原因。

### F3：Trace/Metrics 外部适配

- Trace 使用注入的 tracer 或 OTel 全局 tracer；
- Metrics 使用 P10 快照作为唯一输入；
- `opentelemetry-*` 和 `prometheus-client` 作为可选能力，不污染核心依赖。

### F4：恢复校验与验收

- 校验审计 sequence、prev/event hash、head；
- 校验血缘重复行、项目边界、端点存在性；
- 比较恢复前后 stable fingerprint；
- 增加 Gel adapter、导出/归档/校验、Trace/Metrics 和恢复差异测试。

## 3. 退出标准

- Gel 可以 append、按 trace/entity 查询并验证 audit chain；
- 任意一批审计记录可以导出、gzip 归档并独立校验；
- OTel/Prometheus 适配器不要求业务代码直接调用 SDK；
- 恢复后的数据库可以给出明确的 `valid`、差异表和失败原因；
- 全量测试、Ruff、mypy、`git diff --check` 通过。
