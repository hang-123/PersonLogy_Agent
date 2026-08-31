# PersonLogy Agent 系统验收清单（Acceptance Checklist）

> 依据：`docs/plans/development-plan.md`（现行 v0.1 计划，P0–P11）与各阶段功能 Spec（`docs/features/<feature>/spec.md` 的 Given/When/Then 验收标准）。
> 验收方式：代码核对 + 文档核对 + 可执行验证（pytest API 层含 tmp_path、mypy、ruff、web typecheck）。
> 验收日期：2026-08-31（基于当前工作区 & git HEAD `226f9f0`，含 Gel 迁移补充）。
>
> **验收总评（2026-08-31 修订）：** 在上一版清单基础上，**P7 受控回写（`226f9f0`）、P10 Schema 审批/执行/回滚（`c6a0698`）、P9 前端新工作台与契约对齐（`bd89ba3`/`61f98df`/`3fe12ec`）均已落地并通过测试**；**同日补充 Gel 迁移：`00003-m1idqkc`（审计，取代无法解析的手写迁移）、`00004-m1srqqu`（Writeback + Conversation）已生成并应用到真实 Gel 实例，对话导入与受控回写均在真实 Gel 后端验证通过**。当前系统已形成 SQLite 主链的完整纵向闭环：PDF/对话导入 → 解析 → 启发式编译 → 治理/审核 → **受控回写发布（OKF + 索引触发）** → BM25 检索 + 带证据问答 + 前端工作台 + Schema 管理面 + 审计/监控/血缘/回放，且 Gel 后端的主要缺口（Conversation schema、Writeback 迁移、真实实例验证）已补齐。**剩余明确缺口**：向量/重排检索、真实 LLM 编译、完整多用户权限（RBAC）、MinIO/S3、P11 部署收尾。

---

## 0. 鉴证方式与运行环境说明（重要）

本次验收在本机沙箱环境执行，受沙箱限制以下项无法在本机直接复跑，结论依据"代码存在性 + 项目自有文档 + 可复现验证"：

| 验证项 | 本机结果 | 说明 |
|---|---|---|
| pytest 全量（`apps/api/tests`，含 tmp_path 与真实 Gel 集成用例） | ✅ **71 passed**（exit 0） | 需 `PYTEST_DEBUG_TEMPROOT` 指向工作区 + 临时插件把 tmp 目录 mode 0o700→0o755（沙箱 POSIX 权限模拟下 0o700 目录不可枚举，属环境限制，非代码缺陷）；`PKS_GEL_TEST_DSN` 指向真实本地 Gel（localhost:5656） |
| gel adapter 集成测试（真实实例） | ✅ **8 passed** | PDF 导入、知识/治理仓储、回滚、get/save、Job 队列、**Conversation、Writeback** 均真实实例通过 |
| gel schema contract 测试 | ✅ 4 passed | 含审计、Writeback、Conversation 契约断言 |
| mypy（`app`） | ✅ Success, 48 files（strict） | |
| ruff（`app tests` + `worker src`） | ✅ All checks passed | |
| ruff（`personlogy_core/src`） | ⚠️ 17 errors（10 可自动修复） | 多为 I001 导入排序；少量 TRY004/BLE001 语义问题——上版清单未覆盖此目录 |
| web typecheck（`tsc --noEmit`） | ✅ passed | |

> 上述 ✋ 环境限制请勿理解为功能失败；判定以代码与文档为准。

---

## 1. 阶段（P0–P11）完成度总览

| 阶段 | 状态 | 关键证据 |
|---|---|---|
| P0 规范固化 | ✅ 完成 | PRD v0.4/v1.0、架构书、SVG、ADR、Ontology/关系字典、计划表 |
| P1 现状盘点与重构 | ✅ 完成 | `packages/personlogy_core` 分层 domain/ports/adapters/application；API/Worker 入口 |
| P2 领域与 Schema | ✅ 完成（Gel 迁移 00001–00004 已应用真实实例） | `GEL/dbschema/default.gel`（23 类型+枚举）、迁移 00001/00002/00003/00004、seed；SQLite 同步建表 |
| P3 PDF 导入闭环 | ✅ 完成 | `/v1/pdfs/upload`、upload/validate/hash-dedup/SourceVersion/ContentBlock/`pdf.parse` |
| P4 对话导入 | ✅ **完成（Gel 后端已补齐）** | `/v1/conversations/import`；Gel schema 新增 Conversation/ConversationMessage（迁移 00004），真实实例验证通过 |
| P5 知识编译 | ✅ 完成（本地启发式，非真实 LLM） | `DocumentHeuristicCompiler`、OKF v0.2 导出、`knowledge.compile`、候选不自动发布 |
| P6 数据治理与审核 | ✅ 完成（首版） | 结构/来源校验、精确去重、保守冲突、ReviewTask、`/v1/review-tasks`、decision API、版本保护 |
| P7 受控回写 | ✅ **完成（`226f9f0`）** | `WritebackService`（授权/幂等/Schema/依赖闭包/状态闸门）、`WritebackRecord`/`WritebackItem`、`POST /v1/writebacks`、`knowledge.writeback.effects` Worker、OKF 发布产物、`retrieval.index` 触发、审计/血缘 |
| P8 混合检索 | 🟡 第一梯队完成 | FTS5/BM25、项目范围过滤、一跳关系扩展、证据组装、`/retrieval/search`、`/retrieval/answer`（retrieval-grounded）、`retrieval.index`；**无向量、无重排** |
| P9 前端交互 | ✅ **FE-00..FE-07 落地（`bd89ba3`/`61f98df`/`3fe12ec`）** | 导入/任务/审核/检索/带来源问答 5 工作台接当前端点；api.ts 无旧契约残留；旧组件与陈旧文案已清理 |
| P10 Schema 管理面 | ✅ **Schema 审批/执行/回滚已补齐（`c6a0698`）** | Schema Snapshot/Proposal/差异校验/Registry + `/v1/schema-proposals` 的 propose/validate/approve/execute/rollback；审计/监控/回放/血缘已落地 |
| P11 稳定性与部署 | 🟡 部分 | Dockerfile×3、compose.yaml（gel/api/worker/web）、health；审计/指标/回放已落地；**备份恢复、完整可观测、完善部署未完成** |

---

## 2. 验收清单（按阶段 + Spec 标准，每项 Given/When/Then）

### ✅ P2–P3：PDF 导入闭环（`docs/features/pdf-ingestion/spec.md`）

- [x] **有效 PDF**：上传有效 PDF → 保存原文、创建 Source/SourceVersion/IngestionJob，返回任务 ID（202）。`/v1/pdfs/upload`（multipart）。
- [x] **格式校验失败**：非法/损坏/超限文件 → 拒绝并返回原因，不创建可用知识。
- [x] **重复上传**：同项目同内容哈希 → 复用/标记已有版本，不产生重复 SourceVersion（hash 去重）。
- [x] **原文定位**：解析成功 → ContentBlock 保留 page/paragraph/ordinal/content_hash。
- ⚠️ PDF 保存是本地文件（`LocalFileStorage`），**非 MinIO/S3**；OCR/扫描版未覆盖（已声明边界）。

### ✅ P4：对话导入（`conversation-import/spec.md`）

- [x] **有效对话**：标准 JSON → 创建会话/消息并返回任务 ID。
- [x] **结构保留**：多条消息/角色/分支 → 顺序、角色、时间、会话 ID、父消息不丢失。
- [x] **非法数据**：缺会话 ID/角色/内容 → 字段级错误拒绝。
- [x] **幂等导入**：同消息 ID 重复提交 → 不产生重复，返回已有结果。
- ✅ **Gel 后端可用（2026-08-31 补齐）**：`GEL/dbschema/default.gel` 新增 `Conversation`/`ConversationMessage` 类型（迁移 00004），真实 Gel 实例对话导入 + 幂等 + 父消息链接端到端验证通过（新增 `test_conversation_repository_roundtrip_on_gel`）。

### ✅ P5：知识编译（`knowledge-compilation/spec.md`）

- [x] **候选知识生成**：ContentBlock → 生成 Concept/Claim/Relation/Citation 候选（candidate 状态）。
- [x] **Claim 来源绑定**：每个 Claim 关联至少一个 ContentBlock 证据（Citation）。
- [x] **Relation 语义**：关系含类型/方向/起终点/置信度/来源。
- [x] **失败不发布**：编译失败 → 任务失败/待修订，不发布正式知识。
- ⚠️ **Prompt 可追踪**：当前为确定性 `DocumentHeuristicCompiler`，**非真实 LLM**，Prompt 版本/模型链路未实质落地。

### ✅ P6：数据治理与审核（`data-governance/spec.md`）

- [x] **结构校验**：非法类型/缺来源/缺关系端点 → 不发布。
- [x] **治理记录**：生成带 rule_version/task_id/candidate_id/时间的 GovernanceRun；问题的 code/severity/message/来源。
- [x] **重复检测**：精确重复 → DuplicateGroup 并保留原候选。
- [x] **语义冲突（保守版）**：同主题相反 Claim → ConflictRecord，不静默覆盖。
- [x] **人工审核**：确认/驳回/修改 → 记录审核者/时间/修改内容/before-after 版本。
- [x] **审核并发**：旧版本提交 → 拒绝，不覆盖已有结果（expected_version 校验）。
- [x] **状态隔离**：未人工确认的知识明确标注 candidate/machine_checked/human_verified。
- ⚠️ **语义/LLM 去重未做**（仅保守否定词冲突 + 精确重复）；向量/LLM 去重为后续 Port。

### ✅ P7：受控回写（`knowledge-writeback/spec.md`）— `226f9f0` 落地

- [x] **受控写入**：`WritebackService.submit` 只接受 `project_id` + 明确 `candidate_ids` + `governance_run_id` + `expected_review_versions` + `idempotency_key` + Schema 版本；`LocalWritebackAuthorizer` 无权限即拒绝（生产 fail-closed）；无任意 SQL/EdgeQL。
- [x] **事务一致**：候选状态推进（`human_verified → ready_for_writeback`）、WritebackRecord/Item、effects Job 在同一 UoW 提交；任一失败整体回滚。
- [x] **幂等写入**：`idempotency_key` + `request_digest`，同键同摘要返回原记录，同键不同摘要 409 冲突；`WritebackRepository.get_by_idempotency_key` 原子契约。
- [x] **预检**：项目边界、审核状态（仅 `human_verified`/`ready_for_writeback`）、ReviewTask 版本、Citation 存在、Relation 端点/类型/依赖闭包、Schema 快照（`RegistrySchemaWritebackValidator`）。
- [x] **OKF 导出（回写侧）**：effects Worker 生成版本化发布产物 `projects/{project_id}/writebacks/{writeback_id}/okf-v{schema_version}.json`（含 provenance/writeback_id/governance_run_id/candidate_digest），不覆盖 P5 编译版。
- [x] **副作用与恢复**：OKF 写失败 → 记录 `retryable_failed` 可重试；成功后触发 `retrieval.index` Job；审计事件（`writeback.committed/effects_succeeded/failed`）+ 血缘边（derived_from/publishes/materialized_as/scheduled_as）。
- [x] **API**：`POST /v1/writebacks`（202，需 `X-Idempotency-Key`）、`GET /v1/writebacks/{id}`、`GET /v1/writebacks/{id}/items`。
- [x] **测试**：`apps/api/tests/test_writeback.py` 覆盖幂等发布、失败补偿、OKF 内容、血缘——**本机通过**。
- ⚠️ **授权是开发用**：`LocalWritebackAuthorizer` 仅 local/test 放行，生产未接完整 RBAC（属 P11 访问控制范围）；对象存储仍是 `LocalFileStorage`（MinIO/S3 未接入，不宣称跨系统事务）。

### 🟡 P8：混合检索（`hybrid-retrieval/spec.md`）

- [x] **混合召回（第一梯队）**：全文（SQLite FTS5/BM25）组合关系扩展；**无向量、无重排**。
- [x] **关系扩展**：一跳关系展开，返回类型/方向（`expand_relations`）。
- [x] **证据组装**：命中带 citation/evidence/原文定位。
- [x] **无证据回答**：`/retrieval/answer` 明确标记 `retrieval-grounded`，无来源不确定/不伪造引用（当前不接 LLM）。
- [ ] **权限过滤（多用户）**：当前仅项目 ID 过滤，**无真实多用户鉴权/权限系统**。

### ✅ P9：前端交互（`frontend-interaction/spec.md`）— `bd89ba3`/`61f98df`/`3fe12ec` 落地

- [x] **上传反馈**：ImportDesk 展示上传结果、任务 ID、状态（走 `/v1/pdfs/upload`）。
- [x] **任务进度**：JobDesk 列表/详情、轮询、阶段/进度/失败原因/重试。
- [x] **人工审核**：ReviewDesk 确认/驳回/修改 + 版本校验（`/v1/review-tasks/{id}/decision`）。
- [x] **检索与问答**：SearchDesk/AnswerDesk 走真实 `/v1/retrieval` 链路，Evidence/原文正文可回溯（`/source-versions/{id}/content` 内联）。
- [x] **契约对齐**：`api.ts` 全部指向当前端点（health/pdfs/conversations/jobs/review-tasks/retrieval/source-versions/evidence/lineage）；**无 `/sources`、`/candidates`、`/objects` 旧契约残留**。
- [x] **死代码清理**：旧 `CandidateDesk`/`SourceDesk` 组件已移除；App.tsx 陈旧 "PostgreSQL/求职知识域" 文案已更新为 "Evidence before inference / 个人知识工作台"。
- [x] **导航**：5 视图（导入/任务/审核/检索/问答）+ ProjectContextBar 项目上下文。
- 🔸 **引用定位**：PDF 内容端点可读原文（浏览器内联），对话消息定位仍受限。

### 🟡 P10：Schema 管理面 + 审计/可观测（Schema 执行侧 `c6a0698` 补齐）

- Schema：
  - [x] **变更提案/差异校验**：SchemaChangeService + Registry 持久化 + diff/validation。
  - [x] **审批/执行/回滚 API**：`POST /v1/schema-proposals`（create/validate/approve/execute/rollback）已实现，状态机 `proposed → validated → approved → applied / rolled_back`，含版本冲突防护。
  - [x] **SQLite 沙盒迁移执行**：`execute` 经 `migration_executor` 应用，失败记录 execution failure 审计。
  - ⚠️ **Gel Migration Executor**：仍未实现（迁移执行是 SQLite 侧；Gel schema 变更仍需 Gel CLI 流程）。
  - [x] **运行时隔离**：运行时导入不动态建表删表。
- 审计/可观测/血缘（`301ae6a`–`a0a5517`）：
  - [x] 不可变审计流（AuditEvent 哈希链 / SQLite + Gel）、Trace/Span、Metrics/Prometheus、血统 Lineage、回放 Replay、备份恢复一致性校验（`/v1/lineage`、`/v1/metrics`、`/v1/metrics/prometheus`、`/v1/replay`）。
  - [x] 对应测试（test_p10_b/c/d/e/f）**本机通过**。

### 🟡 P11：稳定性与部署

- [x] Dockerfile（api/worker/web）、compose.yaml（gel/api/worker/web）、health live/ready。
- [x] 审计、指标、回放（部分已达到 P11 的"可观测"目标）。
- [ ] 完整权限/审计覆盖、备份恢复运维流程、CI/部署打磨未收尾。

### ✅ 纵向切片（开发计划 §2：PDF 上传 → 存储 → 解析 → ContentBlock → 编译 → Claim+Cita → 存储 → 全文 → 页码）

- 该切片在 **SQLite** 后端已打通并验证（上传→解析→ContentBlock→候选编译+治理→**审核→P7 受控回写发布**→检索→原文页码）。
- ⚠️ 其中对象存储以本地 `LocalFileStorage` 替代 MinIO；**Gel 全链路**仅部分在真实实例验证。

---

## 3. 数据 / 知识 / 检索质量门槛（开发计划 §四）

### 数据正确性
- [x] 重复导入不产生重复来源（hash 去重）。 ⚠️ 原文按本地文件（不可变语义在）。
- [x] SourceVersion 用内容哈希区分。 [x] ContentBlock 可回到 PDF 页码。
- ⚠️ 删除/更新的引用完整性：依赖候选快照而非引用级联校验，未验证静默破坏场景。

### 知识正确性
- [x] Claim 均有 Citation；Relation 有类型/方向/状态与证据。
- [x] 机器生成与人工确认状态分离（candidate/machine_checked/human_verified）。
- ⚠️ "Schema 不匹配进入变更审批"：Schema 审批/执行/回滚已落地（`c6a0698`），但 Gel 侧迁移执行仍需 Gel CLI 流程；回写已实现（P7）。

### 检索质量
- [x] 全文+关系可组合；回答可返回证据片段；冲突来源可标识；索引可从 SQLite 主数据重建（`retrieval.index`）。
- [ ] 向量检索、重排未做；"AI 只能访问授权项目"（多用户权限）未做。

---

## 4. 建议下一步（按风险/缺口排序）

1. **P8 向量/重排 + 访问控制**：接入 Embedding/Reranker Port；落地多用户项目权限与"原文/知识分离"鉴权（当前 `LocalWritebackAuthorizer` 仅为开发用）。
2. **core 包 ruff 清理**：`personlogy_core/src` 17 个 lint 问题（10 个 I001 导入排序可 `--fix`；5 个 TRY004 建议改为 `TypeError`；1 个 BLE001 盲捕获需人工确认）。
3. **P11 收尾**：备份恢复运维流程、CI/部署打磨、完整可观测。
4. **真实 LLM 编译**：`DocumentHeuristicCompiler` 目前是本地启发式；接入 LLM Port 与 Prompt 版本管理。
5. **Gel 侧运维**：Writeback 服务在真实 Gel 后端的全链路（含 effects/OKF/索引触发）建议补端到端用例；Gel 迁移生成流程可固化到 CI 脚本（当前需真实 CLI/实例）。

---

## 5. 结论（2026-08-31 修订）

系统已具备一个**完整可运行的 v0.1 纵向闭环**（SQLite 主链 + Gel 后端补齐：PDF/对话导入 → 解析 → 启发式编译 → 治理/审核 → **P7 受控回写发布（OKF + 索引）** → BM25 检索 + 带证据问答 + 前端工作台 + Schema 管理面 + 审计/监控/血缘/回放）。本机实测：**pytest 71 passed（含 8 个真实 Gel 集成用例）、mypy 48 files 通过、ruff（app/tests/worker）通过、web tsc 通过**；**Gel 迁移 00001–00004 全部应用到真实实例，对话导入与受控回写在 Gel 后端验证通过**。

**按开发计划"退出标准"逐条对齐：**
- P0–P10（含 P4 Gel 后端、P7 回写、Schema 执行侧）**基本满足**；
- **P8 向量/重排、全量访问控制（RBAC）、P11 完整部署、真实 LLM 编译** 未达到阶段退出标准；`personlogy_core/src` 有 17 个 ruff lint 问题待清理。

因此**当前系统可验收为 v0.1 完整纵向闭环（Sprint 0–10 主体，SQLite 主链 + Gel 后端可用），但不可整体验收为"全部 P0–P11 完成"**。验收清单中的 ⚠️/🟡 项即为剩余工作量清单。
