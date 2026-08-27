# TP-06 数据治理与审核

## 目标

保证知识结构、来源、重复、冲突和审核状态满足发布要求。

P6 首版以 P5 的 PDF 候选为输入，在 SQLite 上完成“机器治理 → ReviewTask → 人工决策”
最小闭环；GEL、动态 Schema/Migration 和正式回写不进入本任务。

## 负责范围

- Schema 和规则校验；
- 精确、版本和语义去重；
- Claim/Relation 来源验证；
- 冲突检测；
- ReviewTask 和人工确认；
- GovernanceRun、GovernanceIssue、DuplicateGroup 和 ConflictRecord 持久化；
- 治理规则版本和候选 task_id 追踪。

## 不负责

- 原始文件解析；
- 数据库迁移；
- 检索排序；
- Gel Schema/Migration 管理（TP-07）；
- Gel/MinIO 正式回写（TP-08）；
- 向量或 LLM 语义去重服务。

## 状态机

```text
candidate → machine_checked → pending_review
pending_review → human_verified / rejected / needs_revision
human_verified → ready_for_writeback
```

机器治理只能把候选送入待审核状态，不能直接发布或回写。

## 最小交付

1. 固定知识契约校验：节点类型、Claim 来源、Relation 端点/类型/来源和置信度。
2. 精确重复检测：同批节点标题、Claim 文本、Relation 端点。
3. 保守冲突检测：同主题 Claim 的明确否定词配对，双方均保留。
4. 生成治理运行、问题、重复组、冲突记录和每候选一个 ReviewTask。
5. 提供 ReviewTask 查询与 approve/reject/revise 决策，并使用版本号防止覆盖。
6. 审核结果写回候选状态，但不触发正式知识写入。

## 验收

- Given Claim 没有 Citation
- When 执行治理
- Then Claim 不得进入正式写回

- Given 两个 Claim 互相冲突
- When 执行治理
- Then 系统保留双方并创建冲突标记

- Given 用户确认候选
- When 提交审核结果
- Then 系统记录审核者、时间和版本变化

- Given 候选存在精确重复
- When 执行治理
- Then 生成 DuplicateGroup，双方保留且进入人工审核

- Given 同一主题存在互相否定的 Claim
- When 执行治理
- Then 生成 ConflictRecord，不静默删除或覆盖任一 Claim

- Given ReviewTask 已被更新
- When 使用旧 version 再次提交审核
- Then 操作失败且原审核结果不变

- Given ReviewTask 被批准
- When 系统保存审核结果
- Then 候选状态变为 human_verified，并记录审核者、原因、时间和前后快照

## 退出标准

- P5 PDF 编译任务成功后自动生成机器治理记录和 ReviewTask；
- 每个 P5 候选都有可追踪的 GovernanceRun；
- 无 Citation、非法 Relation、重复和冲突候选不会直接进入正式回写；
- 审核 approve/reject/revise 可重复验证并具备并发版本保护；
- 语义去重未实现时，系统明确标记为后续能力，而非误报通过。
