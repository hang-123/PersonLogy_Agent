# Notes: P8+ SQLite 开发路径

## Sources

### 原始开发计划
- Path: `docs/plans/development-plan.md`
- P7 原计划：Gel 受控回写、OKF 导出、全文/向量/关系索引。
- P8 原计划：BM25/全文、向量、关系扩展、重排、证据组装。
- P9 原计划：前端上传、任务进度、知识浏览、关系图、引用定位和问答。
- P10 原计划：Schema Proposal、差异检查、沙盒测试、审批与执行。
- P11 原计划：权限、审计、日志、指标、备份恢复和部署。

### 当前项目状态
- P1-P6 已有首版实现，当前状态文档将 P7、P8、P10 标为未开始，P9、P11 标为部分完成。
- `packages/personlogy_core` 已按 domain / ports / adapters / application 分层。
- SQLite 已实现 Source、Knowledge、Governance、Job Repository、Unit of Work 和 Job Queue。
- `application/indexing`、`application/retrieval`、`application/writeback` 当前主要是模块占位。
- 默认运行后端为 SQLite，Gel 为可选后端；两者共用 Repository/UoW/Queue 端口。

## Synthesized Findings

### 依赖拆分
- 原始计划把 P7 作为 P8 的硬前置，因为 P8 需要正式知识库和索引。
- 当前可将 P7 拆成两件事：正式 Gel 回写，以及知识数据进入检索层的发布/索引流程。
- P8 可以先消费 P6 产出的、通过审核的候选知识，并将其写入 SQLite 检索数据集；这不是绕过治理，而是绕过 Gel 写回实现。

### 推荐边界
- `KnowledgeReadPort`：提供项目、Claim、Relation、Citation、ContentBlock 和来源定位读取。
- `IndexStore`：提供全文索引、向量索引、关系邻接和索引版本状态。
- `EmbeddingProvider`：封装 embedding 生成，允许先使用空实现或本地实现。
- `RetrievalService`：负责查询解析、召回融合、关系扩展、权限过滤和证据组装。
- `WritebackAdapter`：保留 P7 的正式回写接口，当前不参与 P8 主流程。

### 实现顺序
1. 固化 P6 审核通过知识的读取契约和 SQLite 投影表。
2. 先实现 SQLite FTS5/BM25 与关系邻接查询。
3. 再接入向量索引和可配置重排。
4. 输出带 Claim、Citation、原文片段、页码/消息定位和关系路径的检索结果。
5. 以 Retrieval API 为稳定边界修正 P9 前端。
6. P10 作为公共基础设施并行实现 Schema Proposal、Snapshot、校验、迁移编译和审计能力。
7. P11 中先实现不依赖 Gel 的审计、备份、恢复和索引重建能力。

### P10 解耦原则
- P10 不调用 P7、P8 或 P9 的业务服务。
- P8/P9 只读取不可变的 Schema Snapshot，不直接读取 P10 内部表结构。
- P7 未来通过 `SchemaValidator` / `MigrationExecutor` 端口使用 P10 能力。
- Schema Proposal 的生成、审批、执行和回滚记录必须独立审计。
- P10 可以先在 SQLite 上实现，再增加 Gel migration executor；上层契约保持不变。

## Implemented in the first increment
- Added schema domain models and pure diff/validation service.
- Added SQLite Feature Store for retrieval documents, FTS5 index builds, schema snapshots and proposals.
- Added retrieval ports, `RetrievalService`, SQLite index rebuild and evidence/one-hop relation assembly.
- Added `/v1/retrieval/search` and `/v1/retrieval/index` API routes.
- `/v1/retrieval/index` now submits an idempotent `retrieval.index` job; both API and standalone Worker handle the job.
- Added vector retrieval contracts (`EmbeddingProvider`, `EmbeddingVector`, `SemanticRetriever`, `SemanticHit`) without binding a model vendor.
- Detailed semantic retrieval design is in `docs/plans/vector-retrieval-plan.md`.
- Existing full test suite passes with the new increment; Gel integration tests remain skipped when no DSN is configured.
