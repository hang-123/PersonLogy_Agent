# P0-P6 完成度审查

审查日期：2026-08-28  
审查分支：`develop`  
审查结论：P0-P6 已形成可运行的首版纵向切片，但不是“全部产品能力完成”。按当前 TP-00～TP-06 的首版范围等权粗算约 **91%**；主要未闭环项是 Gel 下的对话导入、旧文档/进度表同步，以及无法在本机重新执行的 Gel 实例验证。

## 1. 阶段进度表

| 阶段 | 当前判断 | 粗略完成度 | 已核实证据 | 本机验证 | 剩余问题 |
|---|---|---:|---|---|---|
| P0 规范固化 | 基本完成 | 90% | PRD v0.4/v1.0、架构书、ADR、Ontology/关系字典、SVG 图稿 | 文件与内容已核对 | 部分文档仍引用已删除的旧 PostgreSQL 模块；总览仍提及已删除的根目录 `DEVELOPMENT_PLAN.md` |
| P1 现状盘点与重构 | 已完成 | 100% | `packages/personlogy_core` 分层、API/Worker 入口、Repository/UoW/Queue Protocol、重构报告 | Ruff、Mypy 通过；测试通过 | 旧报告中的“9 个 pytest”已过时，应更新为当前测试统计 |
| P2 领域与 Schema | 首版完成，实例证据待本机复核 | 90% | Gel `default.gel`、迁移 `00001/00002`、seed、领域模型和 schema contract tests | 领域/schema 契约测试通过；Gel 实例无法启动 | 关系端点/类型约束的测试仍偏少；本机无法重跑迁移和真实 Gel 集成 |
| P3 PDF 导入闭环 | 首版完成 | 95% | 上传校验、哈希复用、本地原文存储、SourceVersion、pdfplumber、ContentBlock、`pdf.parse` | API/单元/SQLite 链路通过；Gel 用例未在本机运行 | 当前是本地文件存储，不是 MinIO/S3；扫描版 PDF/OCR 未覆盖，均属已声明边界 |
| P4 对话导入 | SQLite 完成，Gel 不完整 | 80% | Conversation/Message 模型、顺序/父消息/附件、消息幂等、`POST /v1/conversations/import` | 单元/API 测试通过 | Gel schema 没有 `Conversation`/`ConversationMessage` 类型；Gel 后端会在该入口失败 |
| P5 知识编译 | 首版完成 | 95% | `KnowledgeCompiler` Port、`DocumentHeuristicCompiler`、候选 Node/Claim/Relation/Citation、OKF v0.2、元数据、编译任务 | 编译持久化与 OKF 测试通过；整体链路测试通过 | 当前为可重复的本地启发式编译器，不是真实 LLM；候选不会自动进入正式库，这是设计边界 |
| P6 数据治理与审核 | 首版完成 | 90% | 结构/来源校验、精确重复、保守冲突、GovernanceRun/Issue/Duplicate/Conflict/ReviewTask、审核 API、版本保护 | SQLite 治理和审核测试通过；Gel 治理测试有另一设备记录但本机未复跑 | 语义/LLM 去重、复杂冲突判断、正式回写不在本版；审核 `changes` 当前记录在 after 快照，未形成正式对象内容更新 |

**综合判断：** 这不是 7 个阶段都“100% 完成”，而是 P0-P6 的首版骨架和 SQLite 主链已打通，Gel 大部分适配已补齐；P4 的 Gel schema 缺口是唯一明确的后端功能阻断点。

## 2. 实际测试与工具结果

- API/core 测试共收集 30 项：**24 passed，6 skipped，0 failed**。
- 被跳过的 6 项全部来自 `apps/api/tests/test_gel_adapter.py`，原因是未设置 `PKS_GEL_TEST_DSN`。
- Ruff：API/core 与独立 Worker 均通过。
- Mypy：API/core 通过，覆盖 71 个源文件。
- Gel CLI 版本可见，但 `gel instance list` 因 WSL2 初始化失败；没有在本机安装、迁移或改动 Gel 数据库。
- 前端 `npm run build` 未能进入源码编译阶段：`apps/web/node_modules` 缺少 TypeScript/Vite 可执行依赖。

## 3. 现有 Excel 进度表的真实含义

工作簿 `个人知识关系系统_P0开发计划表.xlsx` 当前统计为：

| 口径 | 数量/状态 |
|---|---|
| 细项总数 | 46 |
| 已完成 | 2 |
| 未开始 | 44 |
| 旧表显示完成率 | 4.3% |
| 里程碑 | M0“进行中”，M1-M5“未开始” |

这个 4.3% 与代码实际状态明显不一致，说明工作簿停留在旧 P0 计划快照，不能用来代表当前 P0-P6 完成度。建议后续把它改成按 TP-00～TP-06 的阶段表，保留“代码完成”和“验证完成”两列。

## 4. 需要优先处理的事项

1. **P0：补 Gel 的 Conversation/ConversationMessage schema 与 00003 migration，或在 Gel 后端明确 fail-fast。**
2. **P1：把旧进度表和文档状态同步到当前 TP-00～TP-06；删除/修正指向旧模块的引用。**
3. **P1：在具备可用 WSL2/Gel 实例的设备上复跑 6 个 Gel integration tests，并保留命令与结果。**
4. **P2：补关系类型、端点约束和审核修改内容的测试；再考虑前端依赖恢复后的构建验证。**

未修改原有 Excel、业务代码或 Gel 数据库；本次只新增/更新审查记录与本报告。