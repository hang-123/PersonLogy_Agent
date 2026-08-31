# P7 受控回写功能落地规划

版本：v0.1（基于 2026-08-31 工作区）
状态：可进入实施拆解
适用范围：P6 治理通过后的知识发布、Gel/SQLite 持久化、OKF 发布产物、审计/血缘和索引触发

## 1. 结论先行

建议把 P7 首版定义为“受控发布事务”，而不是再次复制 P5 已经落入知识表的候选对象：

```text
P6 ReviewTask approved
  → human_verified
  → P7 预检：权限 + 治理 + Schema + 依赖闭包 + 幂等
  → 知识 UoW 原子提交：发布状态 + WritebackRecord + effects Job
  → Worker：OKF 发布产物 + 索引任务
  → completed / retryable_failed
```

理由是当前 `CompilationService` 已把候选 Node/Claim/Relation 写入 `KnowledgeRepository`；如果 P7 继续无条件 `add_*`，会造成重复对象或无法区分“候选已存在”和“正式发布”。首版用独立发布记录和状态闸门表达正式发布，后续若产品要求“候选在正式发布前对 Gel 完全不可见”，再拆分 staging/formal 表。

P7 首版的正式语义：

- `human_verified`：人工审核通过，但尚未完成 P7 正式发布；
- `ready_for_writeback`：P7 主数据发布事务已成功提交，可被正式检索/下游消费；
- `WritebackRecord.completed`：主数据、OKF 产物和索引触发链路均已完成；
- 失败不删除知识事实，不修改审计链；使用回滚或补偿记录恢复可重试状态。

## 2. 目标与边界

### 2.1 P7 必须交付

1. 结构化 Write Tool / Writeback Application Service，禁止任意 SQL/EdgeQL。
2. 只允许来自指定项目、指定治理运行和指定 ReviewTask 的候选集合进入回写。
3. 回写前检查 actor、项目权限、候选状态、审核版本、Schema、Citation、Relation 端点和跨项目引用。
4. 多对象写入使用同一个 `UnitOfWork`；任一对象失败则数据库事务整体回滚。
5. 通过唯一幂等键和请求摘要避免重复发布；同键不同内容返回冲突。
6. 保存 `WritebackRecord`、逐项结果、候选快照摘要、Schema 版本、治理运行和 OKF 路径。
7. 复用 P10 `AuditSink`、`ToolGateway` 和 `LineageStore`，记录请求、拒绝、提交、失败、重试和完成。
8. 主数据提交后异步触发 OKF 发布/更新和 `retrieval.index`，索引仍是可重建派生数据。
9. SQLite 与 Gel 适配器保持同一领域契约，并完成至少一轮真实 Gel 集成验证。

### 2.2 P7 不负责

- LLM 最终回答、全文/向量排序算法和检索 API 设计；
- 未经治理的候选自动发布；
- 任意用户自定义 EdgeQL/SQL 执行；
- Schema Migration 的生成、审批和执行（由 P10 Schema 管理面负责）；
- 把审计 AI 当成授权系统；最终权限与硬规则必须由确定性策略决定。

## 3. 当前基线与差距

| 领域 | 当前已有 | P7 缺口 | 依据 |
|---|---|---|---|
| 候选与审核 | Node/Claim/Relation、Citation、ReviewTask；approve 后状态为 `human_verified` | 缺少“审核通过→正式发布”的应用服务和状态保护 | `packages/personlogy_core/src/personlogy/application/governance/service.py:39` |
| 持久化 | `KnowledgeRepository` 的 add/get/save；SQLite/Gel UoW | 缺少回写记录、逐项状态和幂等唯一约束 | `packages/personlogy_core/src/personlogy/ports/repositories.py:44` |
| 事务 | SQLite/Gel UoW 未 commit 回滚，Gel 已有真实适配器验证 | 缺少 P7 多对象事务测试和条件更新 | `packages/personlogy_core/src/personlogy/adapters/sqlite.py:1083`、`packages/personlogy_core/src/personlogy/adapters/gel.py:1211` |
| OKF | P5 已生成编译 OKF 到 `ObjectStorage` | 缺少发布版 OKF、回写元数据和失败补偿 | `packages/personlogy_core/src/personlogy/application/compilation/service.py:98` |
| 工具控制 | `AuditedToolExecutor`、`ToolIntent`、`AuditPolicyEngine` 已 fail-closed | 尚未注册 `knowledge.writeback` 工具及项目级授权策略 | `packages/personlogy_core/src/personlogy/application/tool_gateway.py:82` |
| 审计/血缘 | P10 审计哈希链、LineageStore、Job trace 已存在 | 缺少 P7 事件词典、发布血缘和指标 | `packages/personlogy_core/src/personlogy/domain/audit/models.py:147` |
| 索引 | SQLite FTS5/BM25，已支持 `retrieval.index` 重建；当前收录 `human_verified` 与 `ready_for_writeback` | 需明确 P7 发布后触发策略，避免未正式发布内容进入正式索引 | `packages/personlogy_core/src/personlogy/adapters/sqlite_features.py:90` |
| 存储 | 只有安全的 `LocalFileStorage`；Gel 知识仓储已接入 | MinIO/S3 未接入，无法宣称跨系统事务 | `packages/personlogy_core/src/personlogy/adapters/local_files.py:1` |
| 权限 | Trace 有 actor 字段；P11 访问控制尚未完整实现 | P7 不能把 actor 记录当作授权，生产需 fail-closed | `docs/tasks/tp-11-access-control/task.md` |

另一个需要冻结的事实：当前 P5 在同一知识表中保存候选，P7 不能设计为“从 SQLite 候选表直接复制同 ID 到 Gel”的隐式操作。若后续要做 SQLite→Gel 投影，应另建明确的 `CandidateSource`/`WritebackAdapter` 边界和迁移任务。

## 4. 目标架构

```text
HTTP / AI Tool
    │  typed request + actor/project context
    ▼
Writeback API / ToolGateway
    │  audit.requested → authorization/policy → audit.started
    ▼
WritebackService
    ├─ Load candidate closure from UnitOfWork
    ├─ Verify ReviewTask + expected versions
    ├─ Verify Schema snapshot + Citation/Relation constraints
    ├─ Check idempotency / request digest
    └─ One UoW transaction
         ├─ status: human_verified → ready_for_writeback
         ├─ WritebackRecord + items
         └─ Job: knowledge.writeback.effects
    │ commit / rollback
    ▼
Worker effects stage
    ├─ publish versioned OKF artifact to ObjectStorage
    ├─ append lineage and completion audit
    └─ enqueue retrieval.index with project + writeback version
```

依赖方向保持：API/Worker → Application → Domain/Ports → Adapters。`WritebackService` 不直接导入 FastAPI、Gel 客户端、SQLite 或具体对象存储实现。

## 5. 领域契约与状态机

### 5.1 请求契约

建议新增 `WritebackRequest`，外部只允许提交以下字段：

- `project_id`：项目边界；
- `candidate_ids`：明确的 Node/Claim/Relation ID 集合，不能提交任意对象 JSON 作为事实来源；
- `governance_run_id`：绑定 P6 治理运行；
- `expected_review_versions`：每个 ReviewTask 的期望版本，防止并发覆盖；
- `schema_namespace` / `expected_schema_version`：回写采用的 Schema 快照；
- `idempotency_key`：调用方唯一键，建议由 Header 传入并持久化摘要；
- `actor`：由认证上下文注入，禁止客户端自行伪造权限身份。

服务端返回 `WritebackResult`：`writeback_id`、`status`、`job_id`、`published_candidate_ids`、`okf_object_key`、`index_job_id`、失败码和可重试标记。返回中不放审计原文和敏感内容。

### 5.2 允许的状态转移

```text
candidate / machine_checked / pending_review / needs_revision / rejected
    └─ 禁止进入 P7

human_verified ──P7 预检通过+事务提交──> ready_for_writeback
ready_for_writeback ──effects 成功──> completed（记录状态，不改变知识对象状态）
主事务失败 ──> 数据库全部回滚，记录为 preflight_failed 或 retryable_failed
已发布需要撤回 ──> 新增补偿/撤回记录，禁止物理删除和修改历史审计
```

同一批次必须满足：所有显式候选属于同一项目；Relation 的端点、RelationType、Citation 存在且项目一致；Claim/Relation 至少有一个 Citation；依赖候选若未在本批次中，则必须已经处于可发布状态。

### 5.3 失败语义

- `preflight_failed`：权限、状态、Schema、依赖或版本检查失败，不产生主数据变化；
- `commit_failed`：知识事务失败，整个 UoW 回滚；保留失败审计；
- `effects_pending`：主数据已提交，但 OKF/索引等副作用尚未完成；
- `retryable_failed`：对象存储或索引暂时失败，Worker 按现有 Job 重试；
- `completed`：发布记录、OKF 发布产物和索引任务均达到成功条件。

## 6. 持久化设计

### 6.1 `writeback_record`

建议作为独立 feature 表/领域类型，不污染 Node/Claim/Relation：

| 字段 | 说明 |
|---|---|
| `id` | 回写记录 ID |
| `project_id` | 项目隔离键 |
| `idempotency_key` | 项目内或全局唯一，按产品选择；建议全局唯一 |
| `request_digest` | 规范化请求摘要；同键不同摘要必须冲突 |
| `governance_run_id` | P6 治理运行 |
| `schema_namespace` / `schema_version` | 预检采用的 Schema |
| `candidate_ids` | 有序、规范化的候选 ID 集合 |
| `candidate_digest` | 候选完整快照摘要 |
| `status` | preflight_failed / committing / effects_pending / retryable_failed / completed / reverted |
| `okf_object_key` | 发布版 OKF 路径 |
| `effects_job_id` / `index_job_id` | 副作用任务关联 |
| `error_code` / `error_digest` | 脱敏失败信息 |
| `created_at` / `committed_at` / `completed_at` | 生命周期时间 |

### 6.2 `writeback_item`

建议增加逐项表，记录 `record_id`、`candidate_id`、`candidate_kind`、`before_status`、`after_status`、`before_digest`、`after_digest`、`result`。它用于解释批次内哪类对象被发布，不用于部分提交；任何 item 失败都必须回滚主事务。

### 6.3 适配器落地

- SQLite：扩展 `FEATURE_SCHEMA`，增加表、唯一索引、查询/保存接口和旧库初始化逻辑。
- Gel：在 `GEL/dbschema/default.gel` 增加 `WritebackRecord`/`WritebackItem` 及状态枚举，生成下一迁移（预计 00004，不要手写错误的迁移基线）。
- Repository：增加 `get_by_idempotency_key`、`create_if_absent`、`save_if_version` 等原子契约；不要依赖先查后写来模拟幂等。
- 知识仓储：补充带期望状态/摘要的条件更新，例如只允许 `human_verified` 更新为 `ready_for_writeback`，避免并发审核/回写覆盖。

## 7. 应用服务与 API

### 7.1 `WritebackService` 核心流程

1. 从认证/调用上下文取得 actor，解析项目权限；无权限或无认证上下文直接拒绝。
2. 规范化候选 ID 顺序并计算 request digest；查询幂等记录：同键同摘要返回既有结果，同键不同摘要返回冲突。
3. 在一个 UoW 中加载候选、ReviewTask、GovernanceRun、依赖闭包和当前 Schema snapshot。
4. 执行确定性预检：项目边界、审核状态/版本、Citation、Relation、Schema、候选快照未变化。
5. 创建 `WritebackRecord`/items，条件更新候选状态，并在同一 UoW 写入 `knowledge.writeback.effects` Job；然后 commit。
6. 通过 `AuditedToolExecutor` 记录 `tool.requested`、审查、策略放行/拒绝、`tool.started` 和 `tool.succeeded/failed`。
7. Worker 消费 effects Job，写发布版 OKF、更新记录、添加血缘，再提交 `retrieval.index` Job。
8. 所有重试以 `writeback_id` 为主键；副作用写入使用固定对象键和内容摘要，避免重复文件/重复索引。

### 7.2 建议 API

- `POST /v1/writebacks/preflight`：只做检查，返回候选摘要、阻断原因、Schema 版本；不修改知识。
- `POST /v1/writebacks`：提交正式回写，Header 必须带 `X-Idempotency-Key`，返回 `202` 和回写/Job 状态。
- `GET /v1/writebacks/{writeback_id}`：查询回写状态、失败码、OKF/索引任务引用。
- `GET /v1/writebacks/{writeback_id}/items`：查询逐项结果，仅返回授权项目内的摘要。
- 后续可加 `POST /v1/writebacks/{id}/revert`：逻辑撤回，不做物理删除；首版可先由内部运维命令提供。

错误映射建议：无权限 `403`；状态/版本/幂等冲突 `409`；结构或 Schema 不合法 `422`；不存在或不属于项目 `404`/`403`，要避免通过响应差异泄露项目存在性。

## 8. OKF、索引、审计和血缘

### 8.1 OKF

保留 P5 编译版 OKF，不覆盖原文件；P7 生成版本化发布产物，例如：

```text
projects/{project_id}/writebacks/{writeback_id}/okf-v{schema_version}.json
```

发布版至少包含 `okf_version`、`writeback_id`、`governance_run_id`、`source_version_id`、`schema_version`、`candidate_digest`、`reviewer` 摘要、候选对象引用和 Citation 定位。原始 PDF/对话对象保持不可变，只保存 `object_key`、内容哈希和来源引用。

当前只有 `LocalFileStorage`，因此 P7 本地/测试环境可先复用它；生产门槛必须补 MinIO/S3 适配器或明确将 P7 生产范围限制在本地单节点，不能声称数据库与对象存储是同一事务。

### 8.2 索引

P7 主事务成功后提交 `retrieval.index` Job，按项目和发布版本重建/增量更新。建议在 P7 完成过渡后把正式检索白名单收敛为 `ready_for_writeback`；如果 P8 仍要支持 `human_verified`，必须在 API/文档中明确那是“审核后预览集”，不是正式发布集。

### 8.3 审计事件词典

至少新增：

- `writeback.requested`
- `writeback.preflight_succeeded` / `writeback.preflight_failed`
- `writeback.committed` / `writeback.commit_failed`
- `writeback.effects_started` / `writeback.effects_succeeded` / `writeback.effects_failed`
- `writeback.reverted`

事件 metadata 只保存 ID、版本、枚举、计数和摘要；使用现有 digest 机制，不能写入 Claim 原文、PDF 内容、Prompt 或密钥。关键血缘建议为：`governance_run → writeback_record → okf_artifact → retrieval_index_build`，并保留候选/来源关系。

## 9. 实施路线与拆分

以下是建议的一个纵向切片，按 1 名后端开发估算约 9–13 个工作日；真实 Gel/MinIO/生产权限若同时补齐，另需预留集成时间。

### P7-0：冻结语义与兼容策略（0.5–1 天）

- 冻结 `human_verified`、`ready_for_writeback` 和 `completed` 的语义；
- 决定首版采用“同表受控发布”，并记录 staging/formal 未来演进；
- 决定 P8 是否收敛为只检索 `ready_for_writeback`；
- 冻结 WritebackRecord 状态、API 错误码、OKF 路径和审计事件词典。

退出条件：产品/架构确认 P7 不做隐式候选复制，且 P7/P8/P10 的责任边界一致。

### P7-1：领域契约与预检（1.5–2 天）

建议文件：

- `domain/writeback/models.py`：请求、记录、逐项结果、状态；
- `ports/writeback.py`：回写仓储、授权、Schema 校验和副作用端口；
- `application/writeback/service.py`：预检、幂等、依赖闭包、状态条件更新；
- 扩展 `KnowledgeRepository` 或增加专用条件更新端口。

退出条件：内存/SQLite 单元测试覆盖所有非法状态、跨项目、缺 Citation、缺端点、过期版本和同键冲突。

### P7-2：SQLite/Gel 持久化（2–3 天）

- SQLite `FEATURE_SCHEMA` 增加回写记录/逐项表和唯一索引；
- Gel schema 增加类型、枚举和迁移；
- 两个 UoW 实现原子创建/条件更新；
- 验证未 commit、对象中途失败、多次重试和并发幂等。

退出条件：SQLite/Gel 契约测试一致；真实 Gel 环境至少跑通一批 Node + Citation + Claim + Relation 的 commit/rollback。

### P7-3：Tool Gateway、API 与 Worker（2–3 天）

- 注册 `knowledge.writeback`，风险等级为 `write` 或 `external_side_effect`；
- 增加项目级 `WritebackAuthorizer`，权限缺失 fail-closed；
- 新增 API router/schemas，runtime 装配服务；
- worker 增加 `knowledge.writeback.effects`，复用 JobService、StageRunner 和 trace context；
- 用同一事务写回记录和 effects Job，避免“记录已提交但任务未创建”。

退出条件：API 返回 202；无权限无法触发写入；同一幂等键返回同一回写记录；worker 重启后可继续处理。

### P7-4：OKF、索引、审计/血缘/监控（1–2 天）

- 生成发布版 OKF，不覆盖 P5 编译版；
- 补 P7 审计事件与 LineageLink；
- 以发布版本触发 `retrieval.index`；
- 在 P10 MetricsProjector 增加成功率、预检拒绝、回写耗时、effects 延迟和重试指标。

退出条件：从回写记录可追溯到 GovernanceRun、来源、OKF、索引构建和失败审计。

### P7-5：验收、灰度与上线（2 天）

- 完成 API、应用、适配器、并发、故障注入、真实 Gel 和恢复测试；
- 先只开放内部/管理员项目，默认关闭批量全量回写；
- 按项目白名单灰度，观察失败率、重复率、索引延迟和对象存储失败；
- 达到门槛后再开放普通审核者的发布操作。

## 10. 测试矩阵与验收标准

### 10.1 必测场景

| 场景 | 期望 |
|---|---|
| 未认证/无项目写权限 | `403`，不改变知识、不创建回写记录，产生拒绝审计 |
| candidate/machine_checked/pending_review/rejected | `409` 或预检失败，不进入主事务 |
| ReviewTask 版本过期 | `409`，原审核结果不被覆盖 |
| 跨项目候选、Citation、Relation 端点 | 拒绝且不泄露另一项目存在性 |
| 缺 Citation/非法 Relation/Schema 不匹配 | 预检失败，不产生部分数据 |
| 多对象中途写入失败 | UoW 整体回滚，无部分 `ready_for_writeback` |
| 同键同请求重试 | 返回原 `writeback_id`，不重复对象、OKF 或 Job |
| 同键不同请求 | `409 idempotency_conflict` |
| Worker 在 OKF 前崩溃 | 回写记录保持 `effects_pending`/可重试，主数据不回滚 |
| OKF 成功但索引失败 | 主数据与 OKF 保留，索引 Job 可重试/重建 |
| 发布后逻辑撤回 | 不物理删除，产生补偿记录并触发索引更新 |
| Gel 真实实例 | commit、rollback、唯一约束、迁移和重试语义通过 |
| 审计链损坏/审计不可用 | Tool Gateway fail-closed，知识写入不继续 |

### 10.2 上线门槛

- P7 相关测试全绿，至少包含 1 个 API 端到端回写用例；
- SQLite 与 Gel 核心契约测试通过，真实 Gel 集成不再全量 skip；
- 未授权写入成功数为 0；
- 主事务部分提交数为 0；
- 幂等重复执行不新增 `WritebackRecord`、OKF 或索引 Job；
- 回写记录 100% 可通过 trace/lineage 关联到治理和来源；
- 失败 Job 可重试，索引可从主数据重建；
- P8 对 `human_verified` 的过渡兼容策略已写入 API 和验收文档；
- 生产若仍使用 LocalFileStorage，必须明确单节点限制；否则先完成 MinIO/S3 适配器和恢复演练。

## 11. 风险、决策与后续演进

### 11.1 首版必须确认的决策

1. **正式主数据位置**：生产是否以 Gel 为事实源，SQLite 仅用于本地/测试；禁止两者同时充当事实源。
2. **候选可见性**：接受同表状态发布，还是必须 staging/formal 分表。推荐首版接受同表状态发布。
3. **索引可见状态**：推荐 P7 后收敛到 `ready_for_writeback`；过渡期保留 `human_verified` 时需标注为预览。
4. **权限来源**：P7 是否等待 P11 完整 RBAC；若不等待，至少提供内部 `ProjectAccessPolicy`，无策略时生产 fail-closed。
5. **对象存储**：本地首版只做开发验收，生产是否纳入 MinIO/S3 和恢复演练。

### 11.2 后续 P7.1/P7.2

- true staging/formal：候选知识只写 staging，P7 在 Gel 事务中投影到 formal；
- 发布版本与撤回版本：引入不可变 `KnowledgeRelease`，检索按 release 读取；
- 批量发布与审批：多个 ReviewTask 聚合审批，但仍以项目/Schema/版本为原子边界；
- 事件驱动 outbox：当 Job 表无法与外部副作用形成可靠投递时，引入 outbox relay；
- MinIO/S3 版本化、保留策略、校验和和跨节点恢复；
- 将 WritebackRecord 纳入 P10 replay，支持按候选摘要重放而非重放真实副作用。

## 12. 建议的第一批实现文件

```text
packages/personlogy_core/src/personlogy/domain/writeback/models.py
packages/personlogy_core/src/personlogy/ports/writeback.py
packages/personlogy_core/src/personlogy/application/writeback/service.py
packages/personlogy_core/src/personlogy/application/writeback/__init__.py
packages/personlogy_core/src/personlogy/adapters/sqlite_features.py
packages/personlogy_core/src/personlogy/adapters/sqlite.py
packages/personlogy_core/src/personlogy/adapters/gel.py
apps/api/app/modules/writebacks/{__init__.py,schemas.py,router.py}
apps/api/app/runtime.py
apps/api/app/worker.py
apps/worker/src/personlogy_worker/main.py
GEL/dbschema/default.gel
GEL/dbschema/migrations/00004-*.edgeql
apps/api/tests/test_writeback.py
apps/api/tests/test_writeback_api.py
apps/api/tests/test_writeback_gel.py
```

当前工作树已有未提交的 P10 Schema 管理相关变更；实施时应在独立分支/提交中落地 P7，避免将 P7 数据模型与未完成的 Schema Migration 执行链路混在同一提交。
