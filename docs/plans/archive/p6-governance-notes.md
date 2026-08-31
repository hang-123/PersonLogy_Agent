# Notes: P6 数据治理与审核规划

## Existing Foundation

- P5 已有 `KnowledgeNode`、`Claim`、`Relation`、`Citation`、`VerificationStatus`。
- `Claim` 已强制至少一个 Citation；`Relation` 已强制至少一个 citation、置信度范围和部分端点约束。
- `ReviewRecord` 已存在，但尚未形成 ReviewTask、审核命令和持久化闭环。
- 当前 P5 的候选对象仍通过现有 KnowledgeRepository 保存，需要在 P6 明确候选与正式对象的隔离策略。
- SQLite 已有知识对象、Claim、Relation、Citation 和 Job 表，可作为本地治理实现基础。

## P6 Acceptance Mapping

| Requirement | Implementation direction |
| --- | --- |
| Schema validation | Candidate bundle validation + domain invariants + field-level findings |
| Provenance validation | Citation must point to an existing ContentBlock and valid locator |
| Exact/version dedupe | Normalized fingerprint and source-version/content hash indexes |
| Semantic dedupe | Pluggable matcher; first version only creates review flags |
| Conflict detection | Same subject/opposing claims or contradiction relations become conflict records |
| Human review | ReviewTask with approve/reject/revise, reviewer, time, before/after snapshot |
| Publish gate | Candidate or invalid/flagged result cannot enter P8 writeback |

## Key Risk

“语义去重”不能只靠字符串相等。第一版应采用保守策略：规则去重自动标记，语义相似仅进入待审核，不自动合并或删除任一条 Claim。
