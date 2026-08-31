# Task Plan: P10 最小原子架构重新推演

## Goal
以不可变最小记录原子为共同底座，重新划分记录、审计和监控三套能力，避免重复写入、职责混淆和工具调用绕过审计。

## Phases
- [x] Phase 1: 确认最小事件原子与生命周期语义
- [x] Phase 2: 推导记录系统、审计系统和监控系统的职责边界
- [x] Phase 3: 设计 SQLite 下的写入、投影、失败恢复和回放关系
- [ ] Phase 4: 讨论并冻结数据表、端口和 fail-closed 细节
- [ ] Phase 5: 实现 RecordStore、Tool Gateway、AuditPolicy 和 Metrics Projector
- [ ] Phase 6: 验证覆盖率、故障恢复、哈希链和投影重建

## Key Questions
1. 最小事件是否包含 `operation_id/span_id`，如何关联一次调用的多个生命周期事件？
2. 外部副作用在 postflight 记录失败时，是否统一通过 idempotency key + `unknown` 状态处理？
3. 监控指标是否全部作为事件投影，还是保留少量同步计数器？
4. 第一版是否所有工具都采用审计 AI 不可用即拒绝？

## Decisions Made
- 记录系统保存不可变事实，是三套能力共同的事实源。
- 审计系统是同步准入控制 + 审计决策投影，不复制一套独立事实表。
- 监控系统是从事件流派生的低基数指标和健康视图，不把指标混入审计事件。
- 一次工具调用由多个事件组成，不更新单行生命周期记录。
- 所有关键执行都必须有终态；没有终态的调用由 reconciler 标记为 `unknown`，不能被当作成功或失败吞掉。
- `EventAtom` 统一覆盖语义事件，采用统一外壳 + 类型化载荷；普通调试日志和基础设施指标不强行进入同一审计事件模型。
- 业务指标由事件投影生成，CPU/内存等基础设施指标保留独立 Metric 采集，但可共享 trace/span 关联信息。

## Errors Encountered
- 无。

## Status
**Currently in Phase 4** - 已完成覆盖边界重新推演，等待冻结 EventAtom 外壳、类型注册表、SQLite 表结构和异常恢复策略。
