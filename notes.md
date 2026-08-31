# Notes: P7 受控回写

## Sources

### 现有阶段与需求文档
- `docs/tasks/tp-08-writeback/task.md`：P7 负责 Write Tool、Domain Command→EdgeQL、Gel UoW、MinIO 原文/OKF、审计；不负责任意 SQL/EdgeQL、未治理候选发布、搜索排序。
- `docs/features/knowledge-writeback/spec.md`：验收要求权限检查、Schema 校验、Gel 事务、多对象失败整体回滚、幂等返回已有 ID、OKF 生成/更新及来源与验证元数据。
- `docs/features/data-governance/spec.md`、`docs/tasks/tp-06-governance/task.md`：状态流为 `candidate → machine_checked → pending_review → human_verified / rejected / needs_revision → ready_for_writeback`；P6 明确不触发正式回写。
- `docs/plans/project-status-overview.md`、`docs/acceptance/acceptance-checklist.md`：P7 当前未实现；P8 已有 SQLite FTS5/BM25 首版，P10 审计/血缘/监控/回放已落地。
- `docs/plans/p8-sqlite-transition-plan.md`：建议保留 `WritebackAdapter` 边界，P8 不依赖 Gel/EdgeQL；索引是可重建派生数据。
- `docs/features/access-control/spec.md`、`docs/tasks/tp-11-access-control/task.md`：项目隔离、原文/知识分级、AI 写入工具授权属于全局约束，但当前访问控制阶段尚未完整落地。

### 当前代码基线
- `packages/personlogy_core/src/personlogy/application/writeback/__init__.py` 只有 docstring，尚无回写应用服务。
- `KnowledgeRepository` 已有 Node/Citation/Claim/Relation 的 add/get/save；`UnitOfWork` 已同时暴露 sources/knowledge/governance/jobs，SQLite 与 Gel 均有实现。
- `GovernanceService.decide_review_task` 在 approve 时将候选置为 `human_verified`，并写审计/血缘；未实现 `ready_for_writeback` 或正式发布记录。
- `CompilationService.process_compile_job` 已将候选对象和治理记录写入当前 UoW，并将 OKF 先写入 `ObjectStorage`；因此 P7 不能无条件再次插入相同对象。
- `SQLiteStore` 的知识表包含 `knowledge_node`、`citation`、`claim`、`relation` 及关联表；当前没有 writeback/publish 表。
- `GelStore/GelUnitOfWork` 已支持知识和治理仓储，Gel UoW 以 transaction 为边界，未 commit 会回滚；已有真实实例适配器验证记录，但没有 P7 回写链路。
- `SQLiteFeatureStore` 已有 `retrieval_indexer.rebuild_project(project_id, job_id=...)`，索引只收录 `human_verified` 与 `ready_for_writeback`；worker 已处理 `retrieval.index`，但没有由 P7 统一触发的发布事件。
- `AuditedToolExecutor`/`ToolIntent`/`AuditPolicyEngine` 已实现 fail-closed 工具闸门；审计事件是不可变、哈希链追加式记录，metadata 有白名单和大小限制。
- 现有对象存储只有安全的 `LocalFileStorage`；MinIO/S3 尚未接入。
- 当前工作树存在用户已有的 P10 Schema 管理等未提交变更；本次规划不修改这些变更。

## Synthesized Findings

### P7 首版推荐定位
- 把 P7 首版实现为“受控发布事务”：校验审核状态/项目权限/Schema/依赖闭包/幂等键，在同一知识 UoW 内把候选发布为 `ready_for_writeback` 并写入 `WritebackRecord`；不把已有候选对象重复插入知识表。
- `human_verified` 表示人工审核通过但尚未正式发布；`ready_for_writeback` 表示 P7 发布事务完成后的正式可见状态。若业务必须让候选在 P7 前完全不可见，应在后续拆出 staging 与 formal 两套表，而不是靠状态语义长期掩盖存储混用。
- P7 的数据库事实提交与外部 OKF/索引副作用不能伪装成一个跨系统事务：先完成知识事务，再异步生成/更新 OKF 与索引；失败可重试，主数据不回滚但发布记录进入可恢复失败态。

### 必须新增的边界
- Domain：`WritebackRequest`、候选快照/依赖闭包、`WritebackRecord`/状态机、幂等指纹和发布结果。
- Ports：`WritebackService` 使用 `UnitOfWork`；新增 `WritebackRepository` 或 feature store 记录发布状态；`ObjectStorage` 复用；`ToolExecutor`/授权端口作为唯一工具入口；可选 `SchemaProvider`/`SchemaValidator` 与 `RetrievalIndexer`/JobService 端口。
- API：回写预检、提交、查询回写记录，均需项目与 actor 上下文；不提供任意 SQL/EdgeQL。
- Worker：`knowledge.writeback` 作业负责异步副作用或长事务，使用现有 JobService/StageRunner/审计链路。

### 主要风险
- 审核 approve 与回写之间的并发/重复提交；必须用 expected version、幂等 key、唯一约束和项目范围校验。
- 多对象依赖不完整、跨项目引用、引用缺失、relation type 不存在；必须在事务开始前构建并验证闭包。
- P5 已写入候选且 Gel/SQLite 共享仓储；若不先冻结“发布而非重复插入”的语义，会出现重复对象或状态失真。
- SQLite/Gel/对象存储没有天然分布式事务；需要 outbox/回写记录、补偿重试和一致性检查。
- `ready_for_writeback` 当前索引白名单已允许，但 `human_verified` 也被索引；需要明确 P8 过渡期策略。
- 当前没有真正项目级授权实现；P7 不能把 `actor_id` 日志字段误当权限校验。

## Implementation Log

### 2026-08-31
- 用户确认按 `p7_controlled_writeback_plan.md` 开始实施。
- 本轮先落地首版“同表候选 + 受控发布状态 + WritebackRecord”，不做 staging/formal 大迁移。
- 保留用户工作树中既有 P10 Schema 管理相关未提交变更，不覆盖、不回退。
- 新增 `WritebackRecord`/`WritebackItem` 领域模型、仓储端口及 SQLite/InMemory/Gel 适配器；提交事务内完成项目/审核/依赖/Schema/幂等校验，并将候选推进到 `ready_for_writeback`。
- 新增 `/v1/writebacks` 提交、查询、明细 API；API/独立 Worker 均接入 `knowledge.writeback.effects`，异步生成带 provenance 的 OKF 并创建 `retrieval.index` 作业。
- 接入受控授权端口（local/test 允许，production fail-closed）、审计事件和血缘边；对象存储失败会把回写记录置为 `retryable_failed`，支持作业重试。
- 验证结果：P7 测试与核心测试 12 passed；全量 API 测试 65 passed、6 skipped；ruff/mypy 全部通过。
- Gel CLI/Docker 当前不可用，未伪造迁移文件；`GEL/dbschema/default.gel` 已更新，正式 migration 需在具备 Gel CLI 与数据库的环境中生成/执行。
