# P10 Schema 管理面补齐记录

## 2026-08-31：启动

- 用户指出 Schema 审批、执行、回滚仍待补齐；
- 先以当前代码和文档为准核对，不假设旧实现已经满足闭环；
- 所有中间记录继续收敛在 `docs/tasks/p10-schema-management/`。

## 2026-08-31：实现发现

- `SchemaChangeService` 原先只有 `propose` 与 `validate`；
- 新状态链为 `draft → validated → approved → applied → rolled_back`，拒绝仍为终态；
- 回滚创建更高版本的历史定义快照，不删除或覆盖旧快照；
- SQLite 原有 `(namespace, checksum)` 唯一约束会阻止合法回滚，已改为只保证 `(namespace, version)` 唯一，并在启动时保留数据迁移；
- `MigrationExecutor` 作为端口注入，默认 `RegistryMigrationExecutor` 只提交逻辑 Schema Registry 快照，物理 Gel migration 可后续替换；
- 新增 `/v1/schema-proposals` 管理 API 和完整生命周期测试。
