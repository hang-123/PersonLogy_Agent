# 来源、证据与候选发布闭环

## 已实现范围

本增量实现 PRD AC-01、AC-03、AC-04、AC-06 和 AC-08 所需的后端最小闭环：

1. 保存 SourceDocument，服务端生成 SHA-256 内容指纹并检测重复内容。
2. 从来源创建 Evidence，保存摘录、定位、可信层级和可见性。
3. 提交 Object 或 Relation Candidate，默认状态为 `pending_review`。
4. 人工接受或拒绝 Candidate。
5. 接受对象/关系时，在单一 PostgreSQL 事务内写入正式聚合、版本、审计和图投影事件。
6. 关系发布时校验起终点类型、对象状态、Evidence 存在性与有效性。
7. Candidate 审核命令使用行锁；重复接受或拒绝返回 `409 conflict`。

## REST API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/v1/sources` | 创建来源 |
| GET | `/v1/sources/{source_id}` | 查询来源及其 Evidence |
| POST | `/v1/sources/{source_id}/evidence` | 创建 Evidence |
| GET | `/v1/evidence/{evidence_id}` | 查询 Evidence |
| POST | `/v1/candidates` | 提交 Candidate |
| GET | `/v1/candidates` | 分页筛选待审核项 |
| GET | `/v1/candidates/{candidate_id}` | 查询候选详情 |
| POST | `/v1/candidates/{candidate_id}/accept` | 接受并发布 |
| POST | `/v1/candidates/{candidate_id}/reject` | 拒绝并保留原因 |

完整请求 Schema 以运行时 OpenAPI 文档 `/docs` 为准。

## Object Candidate Payload

```json
{
  "candidate_kind": "object",
  "source_document_id": "可选来源 UUID",
  "created_by": "operator",
  "payload": {
    "object_type": "skill",
    "canonical_name": "python",
    "display_name": "Python",
    "status": "active",
    "aliases": [],
    "attributes": {},
    "visibility": "private"
  }
}
```

## Relation Candidate Payload

```json
{
  "candidate_kind": "relation",
  "source_document_id": "来源 UUID",
  "created_by": "operator",
  "payload": {
    "source_object_id": "JDVersion UUID",
    "relation_type": "requires",
    "target_object_id": "Skill UUID",
    "epistemic_type": "source_assertion",
    "status": "confirmed",
    "evidence_ids": ["Evidence UUID"]
  }
}
```

接受请求可以通过 `changes` 对 Candidate Payload 做审核后的浅层字段修订：

```json
{
  "reviewed_by": "reviewer",
  "reason": "已对照原始来源核验",
  "changes": {}
}
```

## 发布事务

```text
SELECT Candidate FOR UPDATE
→ 校验 Candidate 状态与正式 Payload
→ 校验对象状态 / 关系端点 / Evidence
→ 写 KnowledgeObject 或 KnowledgeRelation
→ 关系写 EvidenceLink
→ 追加 ObjectVersion
→ 写 AuditLog
→ 写 GraphProjectionEvent
→ Candidate 标记 accepted
→ COMMIT
```

任一步骤失败都会回滚整笔事务。Neo4j 不参与该事务。

## 数据库与测试

迁移 `20260728_0002` 增加以下去重约束：

- Object：`object_type + canonical_name`
- Relation：`source_object_id + relation_type + target_object_id`
- SourceDocument：`content_fingerprint`

集成测试只允许连接数据库名以 `_test` 结尾的数据库，并通过外层事务回滚测试数据。
GitHub Actions 使用 PostgreSQL 17 创建 `knowledge_test`、执行 Alembic 迁移后运行完整发布链路测试。

## 后续边界

下一增量再实现 Candidate 关联已有对象、别名合并、Claim/Decision 发布以及 Web 审核工作台。
