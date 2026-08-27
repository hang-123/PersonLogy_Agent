# Gel 适配器设计（Gel ↔ Repository/UoW/Queue）

> 对应 `packages/personlogy_core/src/personlogy/adapters/gel.py`。
> 设计目标：在不修改领域模型、JobService 与 API 契约的前提下，把 PDF/对话导入的持久化
> 从 SQLite 切换到 Gel（见 `docs/plans/p3-local-persistence.md` 的接入边界）。

## 1. 端口映射

| Port | Gel 实现 | 说明 |
|---|---|---|
| `SourceRepository` | `GelSourceRepository` | Project/Source/SourceVersion/ContentBlock/Conversation/Message |
| `KnowledgeRepository` | `GelKnowledgeRepository` | KnowledgeNode/Citation/Claim/Relation/RelationType |
| `JobRepository` | `GelJobRepository` | Job 增改查、幂等键查询、列表 |
| `UnitOfWork(+Factory)` | `GelUnitOfWork(+Factory)` | 每个 UoW = 一个 Gel 事务 |
| `JobQueue` | `GelJobQueue` | 基于已提交 Job 行的持久队列（enqueue 为 no-op） |

## 2. 关键设计决策

### 2.1 事务语义（UoW ↔ Gel transaction）

- `GelUnitOfWork.__aenter__` 通过 `client.transaction()` 的 `__aenter__` 显式开启事务，
  把同一个 transaction 对象注入三个 Repository；
- `commit()` 只置位标记；`__aexit__` 无异常且已 commit 时，把 `(None, None, None)` 传给
  驱动 context manager → 提交；否则传入一个内部 `_Rollback` 哨兵异常 → 回滚。
  这与 SQLite/内存适配器"未 commit 即回滚"的语义完全一致；
- 若业务代码在 commit 后又抛异常，同样回滚（与 SQLite 行为一致）。

### 2.2 ID 与配置依赖

- 领域对象 UUID 由 Python 生成（`uuid4`），并进入 object_key、Job payload 等，
  因此插入时显式指定 id → 目标库必须 `allow_user_specified_id := true`（见 `GEL/README.md`）。

### 2.3 类型映射

| Python | EdgeQL 参数 | 说明 |
|---|---|---|
| `uuid.UUID` | `<uuid>$x` | 直接传 |
| `datetime`（UTC aware） | `<datetime>$x` | 驱动自动转换 |
| `str` | `<str>$x` | |
| 枚举（StrEnum） | `<default::JobStatus>$x` 等 | 传 `.value`（成员名） |
| `dict` / JSON 属性 | `<json>$x` | 传 `json.dumps(...)` 字符串；读取时返回 `str` 再 `json.loads` |
| `int` | `<int16>/<int32>/<int64>` | 按字段精度 cast |
| `float \| None` | `<optional float32>$x` | 可空字段用 `<optional T>` 参数 cast |
| 多链接（Claim.citations 等） | `array_unpack(<array<uuid>>$ids)` + `select ... filter .id in ...` | |

### 2.4 Gel 7 语法注意点（已在实例上验证）

- 可选字段判空：`not exists .next_attempt_at`（**`is empty` 在 Gel 7 已不存在**）；
- 枚举比较可直接用字面量：`.status = default::JobStatus.queued`；
- `update ... set { ... }` 中**不能给 `id` 赋值**，只更新其余字段；
- 迁移文件按 CLI 约定存放于 `dbschema/migrations/`。

### 2.5 错误映射

- `gel.errors.ConstraintViolationError` / `MissingRequiredError` → `DomainValidationError`
  （消息与 SQLite 适配器对齐，如 "project slug already exists"）；
- 其余 Gel 错误原样抛出。

### 2.6 队列

- `GelJobQueue.enqueue` 是 no-op：Job 行随 UoW 提交即入队（与 `SQLiteJobQueue` 一致）；
- `dequeue` 轮询查询 `queued` 或到期 `retrying` 的 Job，供 API 与独立 Worker 跨进程共享。

## 3. 装配（apps/api）

- `runtime.py`：`storage_backend == "gel"` 时创建 `GelStore(PKS_GEL_DSN)` 与
  `GelUnitOfWorkFactory`；`queue_backend == "gel"` 时创建 `GelJobQueue`；
  未配置 `PKS_GEL_DSN` 时启动即报错（fail-fast）；
- gel 相关导入放在分支内（惰性导入），保证 `sqlite/memory` 模式下不依赖 Gel 驱动连接；
- `main.py` lifespan 关停时调用 `runtime.shutdown()` 释放客户端；
- `health/ready`：gel 后端时用 `GelStore.ping()` 做真实连通性检查。

## 4. 验证

- `apps/api/tests/test_gel_adapter.py`：PDF 导入闭环、知识库写读、UoW 未提交回滚
  （设 `PKS_GEL_TEST_DSN` 运行，未设置自动 skip）；
- 端到端步骤见 `docs/plans/p4-gel-integration.md` 第 5 节。
