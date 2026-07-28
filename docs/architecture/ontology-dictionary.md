# Ontology 数据字典（M0/M1 基线）

本文件记录首批可执行领域模型。枚举与状态校验的唯一代码入口位于
`apps/api/app/domain/ontology.py`，数据库映射位于
`apps/api/app/infrastructure/postgres/models.py`。

## 核心原则

- PostgreSQL 是权威事实源；Neo4j 仅保存可重建的查询投影。
- 对象、关系、来源、证据、主张、决策和候选项分别建模，避免把不同语义塞进通用节点。
- 业务数据采用状态变更、版本快照和审计记录，不以物理删除表达归档。
- 枚举在 PostgreSQL 中使用字符串列与 CHECK 约束，便于迁移和兼容演进。
- UUID 为主键；结构化扩展字段使用 JSONB；时间字段使用带时区时间戳。

## 知识对象

| 对象类型 | 允许状态 |
| --- | --- |
| `company` | `active`, `inactive`, `archived` |
| `department` | `active`, `unknown`, `archived` |
| `position` | `draft`, `active`, `closed`, `unknown`, `archived` |
| `jd_version` | `current`, `historical`, `disputed`, `archived` |
| `skill` | `active`, `merged`, `archived` |
| `experience` | `draft`, `verified`, `archived` |

所有对象包含规范名、展示名、别名、扩展属性、可见性、版本、有效期、
采集/核验时间和创建/审核人。对象状态组合由
`validate_object_status` 在领域层校验。

## 权威存储表

| 分组 | 表 |
| --- | --- |
| 对象与关系 | `knowledge_object`, `knowledge_relation` |
| 来源与证据 | `source_document`, `evidence`, `evidence_link` |
| 主张与决策 | `claim`, `claim_basis`, `decision`, `decision_basis` |
| 人工审核 | `candidate` |
| 版本与审计 | `object_version`, `audit_log` |
| 后台任务 | `processing_job` |
| 图投影 | `graph_projection_event`, `graph_projection_checkpoint` |

## 通用语义

- 认知类型：`direct_fact`、`source_assertion`、`derived_inference`、
  `personal_judgment`。
- 可见性：`public`、`private`、`sensitive`，默认 `private`。
- 证据方向：`supports`、`refutes`、`qualifies`。
- 新鲜度：`fresh`、`verification_due`、`stale`、
  `source_unreachable`、`superseded`。
- Candidate 与正式对象分表保存；审核通过后才写入权威业务表。
- `object_version` 对同一聚合的版本号设置唯一约束，确保历史快照只追加。
- 图投影事件以“聚合类型 + 聚合 ID + 事件类型 + 目标版本 + 映射版本”
  作为幂等键。

## 数据库迁移

首个迁移为
`apps/api/migrations/versions/20260728_0001_authoritative_schema.py`。
迁移创建 15 张表、外键、CHECK/UNIQUE 约束和查询索引，并启用
`pg_trgm` 支持规范名模糊检索。降级不会删除共享的 `pg_trgm` 扩展。
