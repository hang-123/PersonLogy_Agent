# P10 Schema 管理面补齐报告

状态：代码完成

## 已补齐

- 审批：仅 `validated` 提案可审批，记录 `approved_by`、`approved_at` 和 `schema.proposal.approved` 审计事件；
- 执行：仅 `approved` 提案可执行，检查 base version，调用可注入 `MigrationExecutor`，通过 expected version 写入新 Snapshot，并记录成功/失败审计；
- 回滚：仅 `applied` 提案可回滚，禁止回滚覆盖其后的新版本，以更高版本生成历史定义快照，原提案进入 `rolled_back`，保留完整历史；
- 并发控制：`SQLiteSchemaRegistry.save_snapshot_if_current` 使用 `BEGIN IMMEDIATE` 和 expected version 防止并发覆盖；
- API：新增 `/v1/schema-proposals`、`/{id}/validate`、`/{id}/approve`、`/{id}/execute`、`/{id}/rollback`；
- 数据迁移：补充审批和回滚时间字段，并移除阻止历史定义再次成为当前版本的 checksum 唯一约束。

## 验收

专项测试覆盖：未审批禁止执行、审批、执行、新版本快照、回滚新版本、保留旧快照和并发 stale proposal。

执行验证：

```text
uv run pytest tests/test_schema_management.py -q
4 passed

uv run ruff check app tests ../../packages/personlogy_core/src/personlogy
通过

uv run mypy app ../../packages/personlogy_core/src/personlogy
通过
```

Schema Registry 当前管理的是逻辑 Schema Contract；真实 Gel 物理 migration 不在本次 SQLite 管理面改动中，需要注入实现 `MigrationExecutor` 后接入目标环境。
