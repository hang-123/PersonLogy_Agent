# PersonLogy Agent 系统验收清单（Acceptance Checklist）

> 依据：`docs/plans/development-plan.md`（现行 v0.1 计划，P0–P11）与各阶段功能 Spec（`docs/features/<feature>/spec.md` 的 Given/When/Then 验收标准）。
> 验收方式：代码核对 + 文档核对 + 可执行验证（pytest API 层、mypy、ruff、web typecheck）。
> 验收日期：2026-09（基于当前工作区 & git HEAD）。
>
> **验收总评：** P0–P6 已经形成可运行的首版纵向闭环（SQLite 主链），P8 检索第一梯队与 P9 前端、P10 审计/可观测已落地；**P7 受控回写、向量/重排检索、真实 LLM 编译、访问控制（多用户权限）、Schema 管理与 Gel 后端的部分能力仍是明确缺口**。整体为"可运行的 v0.1 切片"，尚不构成"全部产品能力已验收通过"。

---

## 0. 鉴证方式与运行环境说明（重要）

本次验收在本机沙箱环境执行，受沙箱限制以下项无法在本机直接复跑，结论依据"代码存在性 + 项目自有文档 + 可复现验证"：

| 验证项 | 本机结果 | 说明 |
|---|---|---|
| pytest API 层（无 tmp_path：health/jobs/governance/conversation/retrieval API、core domain、gel schema contract） | ✅ 16 passed（exit 0） | 内存后端 |
| pytest 全量（含 `tmp_path` 用例） | ⚠️ 沙箱阻止 runner 动态建目录（`WinError 5`），**非代码缺陷** | 项目文档记录正常环境为 24 passed / 6 skipped |
| mypy（`app`） | ✅ Success, 42 files | 缓存目录指向 .tmp 后通过 |
| ruff（`app tests`） | ✅ All checks passed | `--no-cache` |
| web typecheck（`tsc --noEmit`） | ✅ passed | |
| web `vite build` | ⚠️ 沙箱 `spawn EPERM`（环境限制，非代码错误） | |
| Gel 集成测试（需 `PKS_GEL_TEST_DSN`） | ⚠️ 本机未连真实实例 | 项目文档 `gel-integration-checklist.md` 记录真实实例 3/3 通过 |

> 上述 ✋ 环境限制请勿理解为功能失败；判定以代码与文档为准。

---

## 1. 阶段（P0–P11）完成度总览

| 阶段 | 状态 | 关键证据 |
|---|---|---|
| P0 规范固化 | ✅ 完成 | PRD v0.4/v1.0、架构书、SVG、ADR、Ontology/关系字典、计划表 |
| P1 现状盘点与重构 | ✅ 完成 | `packages/personlogy_core` 分层 domain/ports/adapters/application；API/Worker 入口 |
| P2 领域与 Schema | ✅ 完成（Gel 集成部分待真实实例复跑） | `GEL/dbschema/default.gel`（17 类+枚举）、迁移 00001/00002/00003、seed；SQLite 同步建表 |
| P3 PDF 导入闭环 | ✅ 完成 | `/v1/pdfs/upload`、upload/validate/hash-dedup/SourceVersion/ContentBlock/`pdf.parse` |
| P4 对话导入 | 🟡 SQLite 完成，**Gel 后端不可用** | `/v1/conversations/import`；Gel schema 缺 Conversation 类型 |
| P5 知识编译 | ✅ 完成（本地启发式，非真实 LLM） | `DocumentHeuristicCompiler`、OKF v0.2 导出、`knowledge.compile`、候选不自动发布 |
| P6 数据治理与审核 | ✅ 完成（首版） | 结构/来源校验、精确去重、保守冲突、ReviewTask、`/v1/review-tasks`、decision API、版本保护 |
| P7 受控回写 | ❌ **未实现** | `application/writeback` 仍是 docstring 空壳；无正式知识写入/OKF 回写闭环 |
| P8 混合检索 | 🟡 第一梯队完成 | FTS5/BM25、项目范围过滤、一跳关系扩展、证据组装、`/retrieval/search`、`/retrieval/answer`（retrieval-grounded）、`retrieval.index`；**无向量、无重排** |
| P9 前端交互 | 🟡 FE-00..FE-07 落地 | 导入/任务/审核/检索/带来源问答工作台接当前端点；遗留旧契约组件与文案待清理 |
| P10 Schema 管理面 | 🟡 部分 | Schema Snapshot/Proposal/差异校验/Registry；**审批/执行/回滚 API 与 Gel Migration Executor 待补**；同阶段审计/监控/回放/血缘已落地 |
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
- ❌ **Gel 后端不可用**：Gel schema 无 `Conversation`/`ConversationMessage` 类型，`PKS_STORAGE_BACKEND=gel` 时导入会失败（P0-1 待办）。

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

### ❌ P7：受控回写（`knowledge-writeback/spec.md`）

- [ ] **受控写入**：非法 → `application/writeback` 无实现。
- [ ] **事务一致**：无写入事务（回写不存在）。
- [ ] **幂等写入**：无。
- [ ] **OKF 导出（回写侧）**：无。
- ❌ **阶段退出标准不满足**：P7 是"治理通过 → 正式知识"的产品闭环缺口，目前审核通过只改候选状态，不写正式知识库。

### 🟡 P8：混合检索（`hybrid-retrieval/spec.md`）

- [x] **混合召回（第一梯队）**：全文（SQLite FTS5/BM25）组合关系扩展；**无向量、无重排**。
- [x] **关系扩展**：一跳关系展开，返回类型/方向（`expand_relations`）。
- [x] **证据组装**：命中带 citation/evidence/原文定位。
- [x] **无证据回答**：`/retrieval/answer` 明确标记 `retrieval-grounded`，无来源不确定/不伪造引用（当前不接 LLM）。
- [ ] **权限过滤（多用户）**：当前仅项目 ID 过滤，**无真实多用户鉴权/权限系统**。

### 🟡 P9：前端交互（`frontend-interaction/spec.md`）

- [x] **上传反馈**：导入中心展示上传结果、任务 ID、状态。
- [x] **任务进度**：Job 列表/详情、进程轮询、阶段/进度/失败原因/重试。
- [x] **人工审核**：ReviewDesk 确认/驳回/修改 + 版本校验。
- [x] **检索与问答**：SearchDesk/AnswerDesk 走真实 `/retrieval` 链路，Evidence/原文正文可回溯。
- 🔸 **引用定位**：PDF 内容端点 `/source-versions/{id}/content` 可读原文（浏览器内联），对话消息定位受限。
- ⚠️ **遗留代码**：`CandidateDesk.tsx`/`SourceDesk.tsx` 与 `api.ts` 中旧契约方法（`/sources`、`/candidates`、`/objects`、`/evidence` 写路径）指向当前后端不存在的路由——**这两个旧工作台未接入新导航，属死代码/契约脱节残留**。
- ⚠️ **陈旧文案**：App.tsx 仍显示 "PostgreSQL · authoritative / 求职知识域 / P0" 等旧品牌与错误后端声明（当前实际主链为 SQLite+Gel），易误导。

### 🟡 P10：Schema 管理面 + 审计/可观测

- Schema：
  - [x] **变更提案/差异校验**：SchemaChangeService + Registry 持久化 + diff/validation。
  - [ ] **审批/执行/回滚 API**：未实现。
  - [ ] **Gel Migration Executor / 沙盒迁移**：未实现。
  - [x] **运行时隔离**：运行时导入不动态建表删表。
- 审计/可观测/血缘（同阶段已落地，git `301ae6a`–`a0a5517`）：
  - [x] 不可变审计流（AuditEvent 哈希链 / SQLite + Gel）、Trace/Span、Metrics/Prometheus、血统 Lineage、回放 Replay、备份恢复一致性校验（`/v1/lineage`、`/v1/monitoring/metrics`、`/v1/replay`）。
  - 本机未复跑其测试（沙箱 `tmp_path`）；测试文件存在，项目文档记录通过。

### 🟡 P11：稳定性与部署

- [x] Dockerfile（api/worker/web）、compose.yaml（gel/api/worker/web）、health live/ready。
- [x] 审计、指标、回放（部分已达到 P11 的"可观测"目标）。
- [ ] 完整权限/审计覆盖、备份恢复运维流程、CI/部署打磨未收尾。

### ✅ 纵向切片（开发计划 §2：PDF 上传 → MinIO → 解析 → ContentBlock → 编译 → Claim+Cita → Gel → 全文 → 页码）

- 该切片在 **SQLite** 后端已打通并验证（上传→解析→ContentBlock→候选编译+治理→检索→原文页码）。
- ⚠️ 其中 **MinIO** 以本地 `LocalFileStorage` 替代；**Gel 回写**未打通（P7）；**Gel 全链路**仅部分在真实实例验证。

---

## 3. 数据 / 知识 / 检索质量门槛（开发计划 §四）

### 数据正确性
- [x] 重复导入不产生重复来源（hash 去重）。 ⚠️ 原文按本地文件（不可变语义在）。
- [x] SourceVersion 用内容哈希区分。 [x] ContentBlock 可回到 PDF 页码。
- ⚠️ 删除/更新的引用完整性：依赖候选快照而非引用级联校验，未验证静默破坏场景。

### 知识正确性
- [x] Claim 均有 Citation；Relation 有类型/方向/状态与证据。
- [x] 机器生成与人工确认状态分离（candidate/machine_checked/human_verified）。
- ⚠️ "Schema 不匹配进入变更审批"：Schema 审批执行链路未落地，实际回写也未实现。

### 检索质量
- [x] 全文+关系可组合；回答可返回证据片段；冲突来源可标识；索引可从 SQLite 主数据重建（`retrieval.index`）。
- [ ] 向量检索、重排未做；"AI 只能访问授权项目"（多用户权限）未做。

---

## 4. 建议下一步（按风险/缺口排序）

1. **P7 受控回写**：把"审核通过 → 正式知识 + OKF"的写回闭环落地（产品主链缺口）。
2. **P0-1（Gel 对话导入）**：补 `Conversation`/`ConversationMessage` schema + migration 00004，或 gel 后端入口 fail-fast。
3. **前端遗留清理**：删除/改写 `CandidateDesk`/`SourceDesk` 与旧契约 `api.ts` 方法；修正陈旧 "PostgreSQL/求职知识域" 文案。
4. **P8 向量/重排 + 访问控制**：接入 Embedding/Reranker Port；落地多用户项目权限与"原文/知识分离"鉴权。
5. **P10 Schema 执行侧**：补审批/执行/回滚 + Gel Migration Executor。
6. **真实实例复跑**：在 `docker compose up -d gel` 上复跑 `PKS_GEL_TEST_DSN` 集成测试与 gel 后端端到端，消除"写好了没复跑"的风险。

---

## 5. 结论

系统已具备一个**可运行的 v0.1 纵向闭环**（SQLite 主链：PDF/对话导入 → 解析 → 启发式编译 → 治理/审核 → BM25 检索 + 带证据问答 + 前端工作台 + 审计/监控/血缘），静态质量门（mypy、ruff、web typecheck、API 层测试）通过。

**但按开发计划"退出标准"逐条对齐：**
- P0–P6、P9（主要）、P10 审计侧 基本满足；
- **P7、P8 向量/重排、全量访问控制、P10 Schema 执行侧、P11 完整部署** 未达到阶段退出标准。

因此**当前系统可验收为首版切片（Sprint 0–6 大部分），但不可整体验收为"全部 P0–P11 完成"**。验收清单中的 ❌/🟡 项即为剩余工作量清单。
