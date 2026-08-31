# P10-F 开发记录

## 2026-08-31：启动

- 已确认 P10-B～E 的审计、血缘、指标和回放端口可复用；
- 现有 Gel schema 只有业务对象，没有 `AuditEvent`/`AuditChainHead`；
- SQLite 审计链已经具备 sequence、prev_hash、event_hash、before_digest、after_digest；
- 当前策略是新增外部适配，不把 OTel/Prometheus SDK 设为核心必装依赖；
- 后续记录每轮测试、异常和 schema 迁移结果。

## 2026-08-31：实现与验证

- 已新增 Gel `AuditEvent`/`AuditChainHead` schema、migration 和 `GelAuditStore`；
- 已接入 Gel runtime 审计 sink；
- 已新增 JSONL/gzip 审计运维工具、SQLite 备份恢复一致性校验；
- 已新增 OTel Trace、OTel Metrics、Prometheus exposition 适配器及 `/v1/metrics/prometheus`；
- 本地测试结果：58 passed、6 skipped；Ruff 和 mypy 通过；
- 6 个 skipped 为既有 Gel integration tests，原因是 `PKS_GEL_TEST_DSN` 未设置；本机也未运行 Gel 服务，因此 00003 migration 仅完成文件交付，待目标环境执行。
