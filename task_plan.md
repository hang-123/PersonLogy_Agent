# Task Plan: P6 governance and review

## Goal
优化并落地 P6 最小治理闭环：P5 PDF 候选经过机器规则校验后生成治理记录、问题、重复/冲突标记和 ReviewTask，只有人工确认后才允许进入后续回写。

## Phases
- [x] Phase 1: 复核 P6 计划与上下游边界
- [x] Phase 2: 固化治理对象、状态机和验收口径
- [x] Phase 3: 实现机器治理与审核任务持久化
- [x] Phase 4: 接入 P5 Worker 并完成验证

## Key Questions
1. P6 如何区分结构错误、重复、冲突和需要人工判断的问题？
2. 治理记录如何与 P5 的 task_id、候选 ID 和来源证据关联？
3. 哪些状态可以被后续回写消费？

## Decisions Made
- P6 首版继续使用 P5 的 PDF 候选和 SQLite，不依赖 GEL。
- 固定 Schema 校验属于 P6；Gel Schema/Migration 管理仍属于 TP-07。
- 机器治理只产生 `machine_checked` / `needs_review` 结果和待审核任务，不直接发布。
- 同一候选的审核结果必须有审核人、时间、原因和前后快照；最终回写留给 TP-08。

## Errors Encountered
- 工作区终端服务首次启动失败，后续通过提升权限恢复。
- 一次 FastAPI 路由探测误将 `_IncludedRouter` 当作直接路由读取；改用应用加载/实际请求验证，代码无影响。

## Status
**Completed** - P6 首版治理和审核闭环已实现并完成验证。
