# P10 Schema 管理面补齐计划

## Goal

补齐 Schema Proposal 的审批、执行、回滚闭环，并确保每个状态变化都有审计、版本并发控制和失败可解释性。

## Phases

- [x] Phase 1：盘点现有 Schema registry/service/API/test 边界
- [x] Phase 2：实现审批、执行、回滚状态机与审计
- [x] Phase 3：补 API、测试和文档
- [ ] Phase 4：运行全量验证并交付

## Key Questions

1. 当前 SchemaProposal 已有哪些状态和持久化字段？
2. “执行”是本地 registry 应用还是 Gel/数据库迁移？
3. 回滚是否要求恢复旧定义，还是只记录反向 Proposal？

## Decisions Made

- 复用现有 `SchemaRegistry` 端口，不把 Gel migration 执行器硬编码进业务服务；
- 审批、执行、回滚均通过新的不可变审计事件表达；
- 回滚生成新的反向变更事实，不覆盖原 Proposal/审计记录；
- 执行和回滚使用 expected version 做乐观并发控制。

## Errors Encountered

- 暂无。

## Status

**Currently in Phase 4** - 已完成实现与专项测试，正在执行全量验证。
