# PersonLogy Agent 项目全景（截至当前工作区）

> 基于 `docs/plans/development-plan.md`（现行 v0.1 计划，P0–P11）、交付文档、git 历史与代码核对。
> 注意：根目录 `DEVELOPMENT_PLAN.md` 是**旧 P0 计划**（PostgreSQL/Neo4j 时代），已被 `docs/plans/development-plan.md` 取代，不要混淆。

## 1. 阶段落地总览（P0–P11）

| 阶段 | 状态 | 落地内容 | 验证/备注 |
| --- | --- | --- | --- |
| P0 规范固化 | ✅ 已完成 | PRD v0.4/v1.0、架构/流程图 SVG、ADR、Ontology/关系字典、开发计划表、工程骨架 | git `538896a` 起 |
| P1 现状盘点与重构 | ✅ 已完成 | 模块化单体重构：domain / ports / adapters / application 分层，旧代码迁移 | `8de4289`“重构项目，完成 00-02 任务包” |
| P2 领域与 Schema | ✅ 已完成 | Project/Source/Version/Block/Node/Citation/Claim/Relation/RelationType/Job + 治理类型；**Gel Schema + migration 00001/00002 + seed**；SQLite 同步建表 | 双后端 schema 就绪 |
| P3 PDF 导入闭环 | ✅ 已完成（TP-03） | 上传校验、本地落盘（非 MinIO）、hash 去重、SourceVersion、pdfplumber 解析、ContentBlock、`pdf.parse` 任务、`POST /v1/pdfs/upload` | 测试覆盖成功/复用/损坏/超限 |
| P4 对话导入 | ✅ 已完成 | Conversation/Message 领域模型、标准化解析器、幂等导入、`POST /v1/conversations` | 见 `docs/plans/archive/p3-local-persistence-task-plan.md`（P3-local 阶段 6–9） |
| P5 知识编译 | ✅ 已完成 | `KnowledgeCompiler` Port + `DocumentHeuristicCompiler`（本地启发式）、`CompilationService`、OKF v0.2 导出、`knowledge.compile` 任务、编译元数据 | 候选保持 `candidate`，不自动发布 |
| P6 数据治理与审核 | ✅ 已完成（首版） | 机器治理（结构/来源校验、精确重复、保守冲突检测）、GovernanceRun/Issue/DuplicateGroup/ConflictRecord/ReviewTask、`GET /v1/review-tasks`、`POST .../decision` | **语义/LLM 去重未做**（留 Port）；审核不自动回写 |
| P7 受控回写 | ❌ 未开始 | `application/writeback` 仅 docstring 空壳；治理通过后不自动发布（TP-08） | |
| P8 混合检索 | 🚧 第一批已落地 | SQLite FTS5/BM25、项目范围过滤、一跳关系扩展、Citation 证据组装；`/v1/retrieval/search`；`retrieval.index` 异步索引 Job 和 Worker 处理 | **向量检索、重排、权限系统未做** |
| P9 前端交互 | 🚧 部分 | web 有最小工作台（CandidateDesk/SourceDesk），但 **api.ts 指向旧版端点**（/sources、/candidates、/objects），与当前后端路由脱节 | 见 §2.5 |
| P10 Schema 管理面 | 🚧 基础骨架已落地 | Schema Snapshot、Proposal、差异校验、SQLite Registry 持久化 | **审批/执行/回滚 API、SQLite 沙盒迁移、Gel Migration Executor 未做** |
| P11 稳定性与部署 | 🚧 部分 | compose.yaml（gel/api/worker/web）、Dockerfile、健康检查；审计/指标/备份恢复未做 | |

## 2. 模块结构与接口接入

### 2.1 分层

```text
apps/web (React 工作台) ── HTTP /v1 ──▶ apps/api (FastAPI 模块化单体)
                                            ├─ app/worker.py   进程内 Worker
apps/worker (独立 Worker 进程) ◀── Job 行(队列) ──┘
packages/personlogy_core
  ├─ domain      source / knowledge / relation / governance / job（纯模型 + 不变量）
  ├─ ports       repositories(4) / unit_of_work / queue / compilation / ingestion
  ├─ adapters    sqlite / memory / gel / local_files / pdf
  └─ application ingestion / orchestration / compilation / governance（+ indexing/retrieval/schema_management/writeback 空壳）
GEL/  EdgeDB schema、migrations、seed
```

### 2.2 端口 → 适配器覆盖矩阵

| 端口（Protocol） | SQLite | 内存 | Gel |
| --- | --- | --- | --- |
| `SourceRepository`（15 方法） | ✅ | ✅ | ⚠️ 会话 4 方法无 schema 类型 |
| `KnowledgeRepository`（12 方法，含 get/save） | ✅ | ✅ | ✅（本轮补齐） |
| `GovernanceRepository`（8 方法） | ✅ | ✅ | ✅（本轮新增） |
| `JobRepository`（5 方法） | ✅ | ✅ | ✅ |
| `UnitOfWork`（sources/knowledge/governance/jobs） | ✅ | ✅ | ✅ |
| `JobQueue`（enqueue no-op / dequeue 轮询） | ✅ | ✅ | ✅（retrying 语义已对齐） |
| `KnowledgeCompiler` | — | — | `DocumentHeuristicCompiler`（唯一实现，可替换 LLM） |
| `ObjectStorage` | `LocalFileStorage` | — | 同左（本地文件，非 MinIO） |

### 2.3 应用服务与装配（组合根）

- `apps/api/app/runtime.py`：按 `PKS_STORAGE_BACKEND`（memory/sqlite/gel）选 UoW factory、
  `PKS_QUEUE_BACKEND` 选 queue，实例化 JobService / ConversationImportService / PdfImportService /
  CompilationService / GovernanceService；`main.py` lifespan 调 `runtime.shutdown()`（gel store aclose）。
- 服务依赖关系：`JobService(UoW, Queue)`；导入/编译服务依赖 JobService 提交任务；
  `CompilationService` 内部用 `GovernanceEvaluator` 并写治理记录；`GovernanceService` 走
  `uow.knowledge.get/save_*` 回写候选状态。

### 2.4 API 路由清单（当前 /v1，共 9 个端点）

| 端点 | 模块 |
| --- | --- |
| `GET /health/live`、`GET /health/ready` | health |
| `POST /conversations` | conversations（P4） |
| `POST /pdfs/upload` | pdfs（P3） |
| `POST /jobs`、`GET /jobs`、`GET /jobs/{id}` | jobs（任务编排） |
| `GET /review-tasks`、`POST /review-tasks/{task_id}/decision` | governance（P6） |

### 2.5 Worker 链路与前端现状

- 队列即 Job 行（enqueue no-op），Worker 轮询 dequeue；`idempotency_key` 幂等。
- 链路：`pdf.parse`（PDF 导入服务）→ 成功后 `submit_for_version` 幂等提交 `knowledge.compile`
  → 编译 + 治理同一事务落库（候选 `machine_checked`/`rejected` + ReviewTask）。
- **前端脱节**：`apps/web/src/api.ts` 仍调用旧契约端点（/sources、/candidates、/objects、
  /evidence），当前后端没有这些路由；web 无法实际对接 P3–P6 能力，需按当前 /v1 重写。

## 3. Gel 使用情况

### 3.1 Schema 与迁移

- `GEL/dbschema/default.gel`：16 个类型 + 9 个枚举（VerificationStatus 7 值、JobStatus、
  SourceKind、ReviewDecision、GovernanceRunStatus、GovernanceIssueSeverity、CandidateKind、ReviewTaskStatus）。
- 迁移：`00001`（TP-01 领域模型初版）、`00002`（TP-05/06 治理与编译：Citation/Claim/Relation
  增 metadata/status、治理 5 类型、VerificationStatus 扩 7 值）——README 声明均已应用本地 `personlogy` 库。
- seed：7 个 RelationType。
- 运行要求：`allow_user_specified_id := true`（领域 UUID 由 Python 生成）；迁移需 `--non-interactive`。

### 3.2 适配器（`packages/.../adapters/gel.py`，约 1240 行）

- `GelStore`（dsn / aclose / ping）、`GelUnitOfWork`（每 UoW 一个 Gel 事务，未 commit 即回滚）、
  `GelUnitOfWorkFactory`、6 个 Repository、`GelJobQueue`。
- JSON 字段 `json.dumps` 传参、读回 `json.loads`；可选字段 `<optional T>`；错误映射
  `ConstraintViolationError/MissingRequiredError → DomainValidationError`。

### 3.3 使用现状与缺口

| 项 | 状态 |
| --- | --- |
| 装配（runtime / 独立 worker） | ✅ `storage_backend=gel` + `queue_backend=gel` 可用；shutdown 钩子已接 |
| 默认运行后端 | 仍是 **sqlite**（默认值）；Gel 是"可选后端" |
| 集成测试 | ⚠️ 依赖 `PKS_GEL_TEST_DSN`，**从未在真实实例运行**（治理/get-save 零运行覆盖） |
| 会话导入 | ❌ Gel schema 无 Conversation/ConversationMessage 类型，gel 后端下不可用 |
| 独立 worker 生命周期 | ⚠️ GelStore 无关闭钩子（Ctrl+C 直接退出） |
| compose 部署 | ⚠️ worker 服务未设 `PKS_GEL_DSN`；gel 服务（geldata/gel:7.1 :5656）已就绪 |
| 迁移工具链 | ✅ README 已记录容器内 CLI + `docker cp` 方案 |

## 4. 关键风险与下一步建议

1. **Gel 是"写好了但没验证过"**：端口齐全，但真实实例零覆盖 → 先跑通
   `PKS_GEL_TEST_DSN` 的集成测试（见 `docs/engineering/gel-integration-checklist.md` P0-2/P1-3~8）。
2. **前端与后端契约脱节**：web 还对着旧 P0 契约，P9 实际未接通。
3. **P7 回写是产品闭环缺口**：目前审核通过只改候选状态（human_verified），不会写正式知识。
4. **会话导入在 Gel 后端不可用**：需补 schema 类型或明确 fail-fast。
5. 详细调整项见 `docs/engineering/gel-integration-checklist.md`。
