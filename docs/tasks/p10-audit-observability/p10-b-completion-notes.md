# P10-B 补全记录

## 已确认缺口

- `GovernanceService`、`SchemaChangeService`、`RetrievalService` 构造函数没有接收 `AuditSink`。
- `SQLiteRetrievalIndexer` 只维护 `retrieval_index_build` 状态，没有 `IndexBuild` 审计事件。
- `AuditEvent` 没有 `before_digest`/`after_digest`，且 `metadata` 未做白名单或敏感字段隔离。
- Tool Gateway、审计 AI 提供者和确定性策略引擎尚未实现。

## 已完成实现

- `AuditEvent` 增加 `before_digest`/`after_digest`，SQLite 旧表可迁移。
- `AuditEvent` 元数据采用白名单、深度和大小限制；未知字段（包括 `prompt`）fail-closed。
- Governance、Schema proposal、Retrieval request、IndexBuild 和 Job 状态均写入审计事件。
- Tool Gateway 记录 requested/review/denied/started/succeeded/failed，并在审计 AI 异常时 fail-closed。

## 依赖边界

上述缺口属于 P10-B；分别挂接既有 P6 治理、Schema 管理和 P8 检索实现，但不需要等待 P10-C 血缘回溯。
