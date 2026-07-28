# 关系字典（M0/M1 基线）

对象到对象的正式关系由
`apps/api/app/domain/relations.py` 定义。关系发布前必须通过端点类型、
证据数量和无环规则校验。

## 正式对象关系

| 关系 | 起点 | 终点 | 至少一条证据 | 无环 |
| --- | --- | --- | --- | --- |
| `has_department` | `company` | `department` | 是 | 否 |
| `offers` | `department` | `position` | 是 | 否 |
| `has_version` | `position` | `jd_version` | 是 | 否 |
| `supersedes` | `jd_version` | `jd_version` | 是 | 是 |
| `requires` | `jd_version` | `skill` | 是 | 否 |
| `prefers` | `jd_version` | `skill` | 是 | 否 |
| `demonstrates` | `experience` | `skill` | 是 | 否 |

`validate_relation` 负责端点与证据门禁；`assert_acyclic_dependency`
负责检测新增依赖边是否成环。数据库同时禁止关系起点和终点使用同一对象 ID。

## 非对象关系的落库边界

PRD 中的其他语义不写入 `knowledge_relation`：

| 语义 | 权威存储 |
| --- | --- |
| 来源包含证据、证据来源 | `evidence.source_document_id` |
| `supports` / `refutes` / `qualifies` | `evidence_link` |
| Claim 的 `derived_from` | `claim_basis` |
| Decision 的 `based_on` | `decision_basis` |
| 抽取来源 | `candidate.source_document_id` |
| 图谱投影与重建 | `graph_projection_event` / `graph_projection_checkpoint` |

这种拆分保留明确外键与聚合边界，防止多态业务关系污染核心对象图。
`related_to` 仍只允许作为 Candidate 原始载荷存在，不进入正式关系字典。

## 发布约束

- 正式关系默认状态为 `candidate`，审核确认后才能成为 `confirmed`。
- 关键关系至少绑定一条 Evidence；EvidenceLink 可表达支持、反驳或限定。
- `supersedes` 发布前必须执行无环校验。
- 对关系的修订追加 `object_version`，并在同一事务写入 `audit_log`。
- PostgreSQL 提交后产生幂等图投影事件；Neo4j 失败不回滚权威事实。
