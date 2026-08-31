# Gel 对接与新增接口覆盖：调整清单

> 依据：工作区未提交更新（`git status`）+ TP-05/TP-06 新接口（Governance、Compilation、knowledge get/save）。
> 未提交变更：`packages/personlogy_core/src/personlogy/adapters/gel.py`（+440 行）、
> `GEL/dbschema/migrations/00002-m15svfs.edgeql`（新增）、`GEL/README.md`、
> `apps/api/app/runtime.py`、`apps/worker/src/personlogy_worker/main.py`、`apps/api/tests/test_gel_adapter.py`。

## 0. 本次更新摘要

| 文件 | 变更 |
| --- | --- |
| `gel.py` | 新增 `GelGovernanceRepository`（8 个方法）；`KnowledgeRepository` 补齐 `get_node/save_node/get_claim/save_claim/get_relation/save_relation/get_relation_type`；Citation/Claim/Relation 写入 `metadata`/`status`；`GelUnitOfWork` 暴露 `governance`；`GelJobQueue.dequeue` 修复 retrying + `next_attempt_at` 为空时的取单逻辑 |
| `00002-m15svfs.edgeql` | 治理类型（GovernanceRun/Issue、DuplicateGroup、ConflictRecord、ReviewTask）+ 枚举（CandidateKind、ReviewTaskStatus、GovernanceRunStatus、GovernanceIssueSeverity）+ Citation/Claim/Relation 增 `metadata`、Relation 增 `status`、VerificationStatus 扩为 7 值 |
| `GEL/README.md` | `--non-interactive` 迁移、已知坑（`MissingRequiredError`、Conversation 缺类型）、迁移状态 |
| `runtime.py` | gel store 的 `aclose()` 挂入 `shutdown()`（`main.py` lifespan 已调用） |
| `worker/main.py` | 独立 worker 接入 `CompilationService`（`knowledge.compile` 消费链）；gel 模式 GelStore 生命周期（finally 中 aclose） |
| `compose.yaml` | worker 服务补 `PKS_GEL_DSN` 透传 |
| `test_gel_adapter.py` | 移除 JobStatus 断言（改为容忍独立 worker 消费） |

## 0.1 验证状态更新（真实实例已验证）

| 条目 | 状态 | 说明 |
| --- | --- | --- |
| P0-2 集成测试真实实例运行 | ✅ 完成 | `pytest tests/test_gel_adapter.py` 3/3 通过（连本机 my-gel personlogy 库） |
| P1-3 UoW `_Rollback` 语义 | ✅ 完成 | `test_gel_rolls_back_uncommitted_uow` 通过，未 commit 干净退出静默回滚 |
| P1-4 dequeue coalesce | ✅ 完成 | 用 `?? <datetime>` 兜底可选字段（Gel 7 的 `or`/`and` 遇空集合结果为 `{}`），真实 Worker 取单验证通过；新增 `test_job_queue_dequeue_retrying_on_gel`（JobService.start_next 认领语义 + retrying 到期/为空/未到期三态） |
| P1-5 save_* 空结果错误路径 | ✅ 完成 | `update` 无匹配行抛 `DomainValidationError`；`test_knowledge_get_save_roundtrip_on_gel` 覆盖 node/claim/relation 三条缺失行路径 |
| P1-9 独立 worker GelStore 生命周期 | ✅ 完成 | `_build_services` 返回 store，`finally` 中 `aclose()` |
| P1-10 compose worker gel 环境变量 | ✅ 完成 | worker 补 `PKS_GEL_DSN` 透传 |
| P1-11 worker 静态检查重跑 | ✅ 完成 | ruff / mypy 全绿（73 文件） |
| P2-12 gel-adapter.md 补内容 | ✅ 完成 | 端口表、驱动 API、Gel 7 语法坑、治理覆盖均已补 |
| P2-14 GEL/README 已知坑 | ✅ 完成 | 已覆盖 |
| 端到端 | ✅ 完成 | API + Worker(gel) 上传 PDF → `pdf.parse` succeeded → ContentBlock 落 Gel → `knowledge.compile` succeeded → GovernanceRun(needs_review) + 2 ReviewTask 落 Gel；pytest 24 passed |
| P0-1 Conversation 缺 Gel schema 类型 | ⏳ 待办 | 需补 `dbschema` 类型并生成 00003，或 gel 后端 fail-fast |
| P1-6 治理闭环 pytest | ✅ 完成 | 新增 `test_governance_repository_roundtrip_on_gel`：run/issue/duplicate/conflict/review task 落库 + get/save/list + 直接 save 版本号 + `GovernanceService.decide_review_task` 三候选（approve→human_verified / reject→rejected / revise→needs_revision） |
| P1-7 schema 契约测试扩展 | ✅ 完成 | `test_gel_schema_contract.py` 补 5 治理类型、4 枚举、metadata/status、VerificationStatus 7 值断言 |
| P1-8 恢复 JobStatus 断言 | ⏳ 待办（有取舍） | 测试进程与独立 Worker 共享 DB 时会竞争，保持放宽并注释 |
| 新发现：Gel confidence 用 float32、SQLite 用 float64 | ⚠️ 已知问题 | 0.42 经 float32 往返后 ≠ 0.42；测试用 `pytest.approx`。如需统一为 float64 需 schema 变更（TP-07 范畴） |

## 1. 接口 × 实现覆盖核对

| 端口 / 接口 | Gel 实现 | 覆盖状态 |
| --- | --- | --- |
| `SourceRepository`（Project/Source/Version/Block） | `GelSourceRepository` | ✅ 齐全 |
| `SourceRepository`（Conversation/Message） | `GelSourceRepository` | ⚠️ **方法存在但 Gel schema 无对应类型**（见 P0-1） |
| `KnowledgeRepository`（12 方法） | `GelKnowledgeRepository` | ✅ 齐全（get/save 本轮补齐） |
| `GovernanceRepository`（8 方法） | `GelGovernanceRepository` | ✅ 齐全 |
| `JobRepository` | `GelJobRepository` | ✅ 齐全 |
| `JobQueue` | `GelJobQueue` | ✅ dequeue 与 SQLite 语义对齐 |
| `UnitOfWork`（governance 属性） | `GelUnitOfWork` | ✅ |
| `CompilationService` / `GovernanceService` 装配 | runtime.py / worker | ✅ 已接线 |

## 2. 调整项清单

### P0 —— 阻塞 Gel 后端可用性

**P0-1. Conversation/ConversationMessage 无 Gel schema 类型**
- 现状：`GelSourceRepository.add_conversation/get_conversation/add_message/get_message`
  （`gel.py:207-326`）写入的 `Conversation`/`ConversationMessage` 类型在 `GEL/dbschema/default.gel`
  与迁移中不存在；`ConversationImportService`（`ingestion/service.py:79,103`）在 gel 后端下
  必然抛 "type does not exist"。
- 建议（二选一）：
  - 方案 A：`default.gel` 补两类型并生成迁移 00003（新表无历史数据，无 `MissingRequiredError` 坑）；
  - 方案 B：gel 后端在装配期或导入入口 fail-fast，返回清晰错误而非 EdgeQL 报错。
- 涉及：`GEL/dbschema/default.gel`、`GEL/README.md`、`docs/engineering/gel-adapter.md`（端口表声称支持 Conversation/Message）。
- 验证：真实实例 `POST /v1/conversations`。

**P0-2. Gel 集成测试从未在真实实例运行（新增代码零覆盖）**
- 现状：`test_gel_adapter.py` 三个用例在无 `PKS_GEL_TEST_DSN` 时全部 skip；本轮新增的
  `GelGovernanceRepository`、knowledge get/save、dequeue 修复均无运行验证。
- 建议：用 `compose.yaml` 的 `gel` 服务（geldata/gel:7.1, :5656）建立可复现验证步骤
  （见 §4 命令），并把 `PKS_GEL_TEST_DSN` 的集成测试纳入本地验证/CI 可选 job。
- 涉及：`apps/api/tests/test_gel_adapter.py`、CI（`.github/workflows`）。

### P1 —— 验证与测试补齐

**P1-3. UoW `_Rollback` 哨兵语义需真实实例确认**
- `GelUnitOfWork.__aexit__`（`gel.py:1170-1191`）在未 commit 的干净退出时向事务传入 `_Rollback`
  哨兵强制回滚；需确认驱动不会把该异常重抛给调用方（"干净退出 = 静默回滚"）。
- 现有 `test_gel_rolls_back_uncommitted_uow` 正好覆盖，跑一次真实实例即可。

**P1-4. dequeue 的 coalesce 写法与 retrying 语义**
- `gel.py:1227-1229` 用 `(.next_attempt_at ?? <datetime>'1970-01-01T00:00:00Z') <= <datetime>$now`
  对齐 SQLite 的 `next_attempt_at IS NULL OR next_attempt_at <= now`；需在 Gel 7 验证语法
  与行为，并补 retrying + `next_attempt_at` 为空的集成测试。

**P1-5. knowledge `save_*` 空结果错误路径**
- `save_node/save_claim/save_relation` 在 `update` 无匹配行时应抛
  `DomainValidationError`（`gel.py:534,643,733`）；补"不存在行"测试。

**P1-6. 治理闭环集成测试（本轮缺口最大）**
- 建议新增：Project → `GovernanceRun` → `GovernanceIssue`/`DuplicateGroup`/`ConflictRecord`/
  `ReviewTask` → `get_review_task`/`save_review_task`/`list_review_tasks` →
  `GovernanceService.decide_review_task`（approve 后 candidate 变 `human_verified`，
  覆盖 NODE/CLAIM/RELATION 三条 `_save_candidate_status` 路径）。
- 可复用 `test_knowledge_compilation.py` 的编排方式（sqlite 版已有，gel 版补一份）。

**P1-7. schema 契约测试扩展**
- `test_gel_schema_contract.py` 目前只断言旧类型；补充 GovernanceRun/ReviewTask/
  ConflictRecord/DuplicateGroup/GovernanceIssue 类型、CandidateKind/ReviewTaskStatus 枚举、
  Relation 的 `metadata`/`status`、VerificationStatus 7 值，防止 schema 回退。

**P1-8. 恢复 JobStatus 断言**
- `test_gel_adapter.py:88-92` 删除的 `job.status is JobStatus.QUEUED`：测试内无 worker 消费，
  任务应保持 queued，建议恢复（或断言 `in (queued, running)` 并注释），保持"入队即持久化"断言强度。

**P1-9. 独立 worker 的 GelStore 生命周期**
- `apps/worker/src/personlogy_worker/main.py`：gel 模式创建的 `GelStore` 无关闭钩子，
  `run_worker` 无 shutdown（Ctrl+C 直接退出）。建议 `KeyboardInterrupt` 分支
  `await store.aclose()`（把 store 从 `_build_services` 带出）。

**P1-10. compose worker 缺 gel 环境变量**
- `compose.yaml` 的 `worker` 服务未设 `PKS_GEL_DSN`/`PKS_STORAGE_BACKEND`（默认 sqlite）；
  gel 后端部署时需补环境变量或文档注明。

**P1-11. worker 静态检查重跑**
- 独立 worker 新 import `CompilationService` 等，需重跑 ruff/mypy 并更新
  `docs/tasks/tp-06-governance/delivery.md` 的验证结论（当前写的是旧状态）。

### P2 —— 文档 / 契约同步

**P2-12. `docs/engineering/gel-adapter.md`**
- §1 端口映射表补 `GovernanceRepository → GelGovernanceRepository` 与 knowledge get/save；
- §2.4 补 Gel 7 验证点（`??` coalesce + `<datetime>` cast）；
- §4 验证章节补治理闭环与真实实例运行方式。

**P2-13. `docs/tasks/tp-06-governance/delivery.md`**
- "SQLite 持久化，同时保留未来 GEL Repository 替换接口" → 更新为 Gel 治理仓储已落地（待实例验证）。

**P2-14. `GEL/README.md`**
- 已知坑已覆盖；确认 Conversation 缺口与有数据库迁移兜底步骤均有写明（当前已写，保持同步）。

## 3. 代码级核查结论（review 已确认 OK，无需改动）

- `update ... set { }` 均未给 `id` 赋值（符合 Gel 7 约束，`gel-adapter.md` §2.4）。
- `_constraint_error` 已映射 `MissingRequiredError` → `DomainValidationError`（配合迁移坑）。
- 治理决策回写依赖的 `get_node/get_claim/get_relation` + `save_*` 已全部实现。
- Relation 的 `status`/`metadata` 在 add/get/save 三处一致；`save_relation` 不更新 citations，
  与 sqlite 适配器语义一致。
- `Job.idempotency_key` exclusive 冲突已映射为 `DomainValidationError`（编译幂等）。
- `runtime.py` shutdown 钩子已接入 `main.py` lifespan。

## 4. 验证命令（真实 Gel 实例）

```text
# 1) 起 Gel 服务
docker compose up -d gel

# 2) 迁移 + 种子（GEL/ 目录内，DSN 按需替换）
gel migration create --non-interactive --dsn <DSN>
gel migrate --dsn <DSN>
gel query -f seed.edgeql --dsn <DSN>
gel query "configure current database set allow_user_specified_id := true" --dsn <DSN>

# 3) 跑 Gel 集成测试（apps/api 目录内）
set PKS_GEL_TEST_DSN=gel://edgedb@localhost:5656/personlogy?tls_security=insecure
pytest tests/test_gel_adapter.py -v

# 4) gel 后端端到端：API + 独立 worker + 治理审核
#    PKS_STORAGE_BACKEND=gel PKS_QUEUE_BACKEND=gel PKS_GEL_DSN=<DSN>
#    API: uvicorn app.main:app --port 8000
#    Worker: python -m personlogy_worker.main
#    导入 test-data/sample.pdf → 观察 pdf.parse → knowledge.compile → 治理落库
#    GET /v1/review-tasks → POST /v1/review-tasks/{id}/decision
```

## 5. 建议执行顺序

1. P0-1 决策（补 schema 或 fail-fast）→ 2. P0-2 建立实例验证环境 → 3. P1-6/7/5 补测试 →
4. P1-3/4 实例验证 → 5. P1-9/10/11 生命周期与 CI → 6. P2 文档同步。
