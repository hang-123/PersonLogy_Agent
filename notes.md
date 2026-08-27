# Notes: P6 governance and review

## Sources

### Local repository
- P5 已提供 PDF → ContentBlock → knowledge.compile → Concept/Claim/Relation/Citation + OKF。
- 当前知识对象已有 candidate、machine_checked、human_verified、rejected 状态；P6 需要补齐 pending_review / needs_revision / ready_for_writeback 或明确等价状态。
- 当前 GEL Schema 已有 ReviewRecord，但 Python/SQLite 治理对象尚未落地。

## Synthesized Findings

### P6 implementation decision
- P6 首轮交付机器治理、GovernanceRun、GovernanceIssue、Duplicate/Conflict 标记和 ReviewTask。
- 机器治理通过后仍进入人工审核；不存在“结构合法即自动回写”。
- 先用规则检测精确重复和保守的文本冲突；语义去重留出接口，不在本轮伪装成已完成。

### P6 implementation result
- P5 编译任务现在在同一事务中写入候选与治理记录，默认结果为 `needs_review`。
- 每个节点、Claim、Relation 都生成一个 ReviewTask；批准后对应候选变为 `human_verified`，驳回为 `rejected`，修改为 `needs_revision`。
- 新增 API：`GET /v1/review-tasks` 和 `POST /v1/review-tasks/{task_id}/decision`。
- 旧 SQLite 数据库会自动补齐 Relation status 和治理表。

### Integration decisions
- GEL 暂不接入当前运行时；SQLite + 本地文件继续作为可运行替身。
- P5 Worker 完成编译后提交/执行治理任务，治理结果和 ReviewTask 仍写入本地库。
- 真实向量/LLM 语义治理只通过 Port 接入，不改变治理状态机和审核边界。
