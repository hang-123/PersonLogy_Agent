# Task Plan: M0/M1 领域模型与权威存储基线

## Goal
将 PRD 中的核心 Ontology、关系约束和 PostgreSQL 表边界落地为可执行、可迁移、可测试的后端基础，为来源录入与人工审核发布闭环提供稳定底座。

## Phases
- [x] Phase 1: 复核 PRD、开发计划和现有工程边界
- [x] Phase 2: 实现对象类型、状态、认识类型与受控关系策略
- [x] Phase 3: 实现 SQLAlchemy 核心模型与首个 Alembic 迁移
- [x] Phase 4: 补齐 Ontology/关系字典和领域/元数据测试
- [x] Phase 5: 执行 Ruff、Mypy、Pytest、迁移离线 SQL 验证并交付

## Delivered Scope
- knowledge_object、knowledge_relation
- source_document、evidence、evidence_link
- claim、claim_basis、decision、decision_basis
- candidate、object_version、audit_log
- processing_job、graph_projection_event、graph_projection_checkpoint
- 对象端点约束、关键关系证据门禁、derived_from/based_on 无环校验基础
- PostgreSQL 首个可离线执行的 Alembic 迁移
- Ontology/关系字典及领域/数据库元数据契约测试

## Non-Goals
- 本增量不实现完整 CRUD、发布事务、Worker 任务领取、Neo4j 写入和 Web 业务页面。
- 不引入 Redis、消息队列、向量数据库或额外服务。
- 不把尚未评审的 AI 抽取流程写入正式知识路径。

## Decisions Made
- 使用 PostgreSQL UUID、JSONB 和显式索引；高频查询字段关系化，扩展属性保留在 JSONB。
- 数据库枚举使用字符串约束而非 PostgreSQL 原生 ENUM，降低 P0 频繁演进时的迁移成本。
- knowledge_relation 仅表达 Knowledge Object 之间的受控语义关系；Evidence/Claim/Decision 依赖使用独立关联表。
- 所有正式记录采用状态/版本/审计，不以物理删除作为业务操作。
- PostgreSQL 仍是唯一权威源；图投影表只记录派生任务与检查点。

## Errors Encountered
- 内置 apply_patch 在该 Windows 工作区持续触发沙箱刷新错误；使用受控 UTF-8 写入回退，并通过完整自动化检查防止文件损坏。

## Status
**Completed** - M0/M1 领域模型与权威存储基线已落地并通过质量门禁。
