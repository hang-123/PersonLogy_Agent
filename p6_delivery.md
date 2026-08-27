# P6 数据治理与审核首版交付说明

## 已落地链路

```text
P5 候选 → 机器治理 → GovernanceRun / Issue / Duplicate / Conflict
→ ReviewTask → approve / reject / revise
```

机器治理不会直接发布知识。审核通过后候选状态为 `human_verified`，后续正式回写仍由
TP-08 负责。

## 已交付

- 固定知识契约和来源关系校验。
- 同批节点、Claim 和 Relation 的精确重复检测。
- 同主题 Claim 的保守否定词冲突检测，双方保留。
- GovernanceRun、GovernanceIssue、DuplicateGroup、ConflictRecord 和 ReviewTask。
- ReviewTask 版本保护，避免旧审核结果覆盖新结果。
- API：`GET /v1/review-tasks`、`POST /v1/review-tasks/{task_id}/decision`。
- SQLite 持久化，同时保留未来 GEL Repository 替换接口。

## 当前边界

向量相似度、LLM 语义去重、复杂事实冲突判断和正式回写尚未纳入本版；这几类能力会在
后续 Port 和 TP-08 中接入。

## 验证

- 21 项测试通过。
- Ruff、Mypy 和独立 Worker 静态检查通过。
