# P10：基于最小记录原子的审计、监控与记录架构

> 状态：已收敛。本文作为架构推演与决策依据，当前执行入口见 [P10 最小记录原子架构](p10-minimal-record-architecture.md) 和 [P10 任务包](../tasks/p10-audit-observability/task.md)。

## 1. 总体结论

P10 不应该先搭三套互相独立的“日志表、审计表、监控表”。更稳妥的分层是：

```text
                 ┌────────────────────┐
                 │  业务 / Job / Tool  │
                 └─────────┬──────────┘
                           │
             ┌─────────────▼─────────────┐
             │ 统一执行入口               │
             │ StageRunner / ToolGateway  │
             └─────────────┬─────────────┘
                           │ append
             ┌─────────────▼─────────────┐
             │ RecordStore                │
             │ 不可变事件 + 哈希链         │
             └───────┬───────────┬────────┘
                     │           │
          ┌──────────▼───┐   ┌───▼────────────┐
          │ Audit         │   │ Monitoring     │
          │ 同步准入/审查  │   │ 指标/健康投影   │
          └───────────────┘   └────────────────┘
```

记录系统是事实源；审计系统和监控系统是两种不同的消费者。这样三者共享同一个最小原子，但不会共享全部业务职责。

## 2. 最小记录原子

### 2.1 覆盖边界

`EventAtom` 可以覆盖所有需要被解释、追踪、审计或回放的**语义事件**，但不应被定义成“所有日志和所有指标的唯一格式”。稳妥的做法是：统一事件外壳，类型化载荷；不同场景共享关联字段，但只要求自己需要的字段。

因此需要区分：

- **语义事件**：Job、阶段、工具、模型、状态变更、审核、血缘，统一进入 `EventAtom`；
- **运行日志**：调试信息、异常堆栈、第三方库输出，可以携带相同 `trace_id/span_id`，但不一定进入哈希链；
- **基础设施指标**：CPU、内存、连接池、进程存活等使用 Metric 采集，不能强行伪装成审计事件；
- **业务指标**：请求量、失败率、工具耗时等优先由 `EventAtom` 投影生成，避免业务代码重复埋点。

所以，`EventAtom` 是统一的**事实和语义操作记录原子**，不是把所有可观测数据都塞进同一张宽表。

一条 `AuditEvent`/`RecordEvent` 表示一个已经发生、正在开始或被明确拒绝的事实。它不可更新，只能追加。

```text
event_id
occurred_at
event_type
schema_version

trace_id
span_id
actor_type / actor_id
entity_type / entity_id

status
reason_code / error_code

sequence
prev_hash
event_hash
metadata
```

`span_id` 同时承担一次操作实例的关联 ID；同一个工具调用的 requested、started、succeeded/failed 事件共享一个 span。`parent_span_id` 用于表示嵌套调用。

这里的通用外壳不应强制所有场景都填写 actor、entity 和 status。审计/操作事件通常需要这些字段，但基础设施指标和诊断记录可能没有业务对象或结果状态，应通过类型化载荷表达。

`metadata` 只允许受控 JSON，保存摘要、哈希、版本、枚举和关联 ID，不保存完整 Prompt、原文、密钥或工具返回全文。

按场景增加：

```text
HTTP:       request_id, route, http_status
Job:        job_id, attempt_id, parent_job_id
Tool:       tool_invocation_id, tool_name, tool_version, risk_class,
            args_digest, result_digest, idempotency_key
State:      before_digest, after_digest, version
Model:      model_name, model_version, prompt_digest, response_digest
Lineage:    source_ref, derived_ref, relation_type
```

## 3. 记录系统：只负责保存事实

RecordStore 的职责只有五项：

1. 规范化和脱敏：把调用方事件变成稳定的 canonical event；
2. 幂等追加：相同 `event_id` 或 `idempotency_key` 重试时不产生重复事实；
3. 哈希链：在 SQLite `BEGIN IMMEDIATE` 下锁定 head，写入 `sequence/prev_hash/event_hash`；
4. 事务边界：关键状态变化与对应事件尽量同一 Unit of Work 提交；
5. 查询和回放：按 trace、Job、工具调用和时间范围读取，投影可以从事件重建。

它不负责判断业务是否允许，也不负责生成 P95。它只回答“发生了什么”。structlog 可以由它或执行器同步输出，但只是展示通道，不是事实源。

## 4. 审计系统：同步准入，不重复造事实

工具调用由 `ToolGateway` 统一处理：

```text
ToolIntent
  → append tool.requested
  → 生成只读审计上下文
  → 调用无工具 Auditor AI
  → append auditor.review.*
  → AuditPolicyEngine 最终判断
  → deny：append tool.denied
  → allow：append tool.started → 执行工具
  → append tool.succeeded / tool.failed / tool.unknown
```

审计 AI 只接收结构化输入，不注册工具、不访问系统、不持有写权限。它的结果是建议；硬性策略、权限和风险分类由确定性的 `AuditPolicyEngine` 最终决定。

审计 AI 超时、返回非法结构、上下文不完整或审计事件无法写入时，第一版统一拒绝工具调用。

对于外部副作用，要特别承认一个边界：工具成功后，进程可能在写入 succeeded 事件前崩溃。因此不能保证跨外部系统的绝对 exactly-once。解决方案是：

- 每次工具调用生成稳定 `tool_invocation_id` 和 idempotency key；
- 没有终态的调用由 reconciler 标记为 `unknown`；
- 可重试工具按幂等键重试；不可重试工具进入人工诊断；
- 任何未知态都不能被监控系统默认为成功。

## 5. 监控系统：从事件派生指标

监控不再要求业务模块手写计数器，而是由 `MetricsProjector` 消费事件：

```text
RecordEvent
  → 计数器：请求量、成功量、拒绝量、失败量
  → 直方图：耗时、队列等待、审计 AI 延迟、工具延迟
  → 状态视图：Job 积压、索引新鲜度、未知态调用
  → 健康快照：数据库、Worker、审计链和投影延迟
```

指标只使用低基数标签，例如 event_type、status、tool_name、job_kind、model_version。不能把 `trace_id`、原文或用户输入作为指标标签。

SQLite 第一版可以把指标投影表和事件表放在同一数据库，但逻辑上仍是派生数据：

- 每个投影维护 checkpoint；
- 投影失败时不丢事件，只暂停 checkpoint；
- 可从 sequence 重新构建指标；
- 监控查询只读投影，不直接扫描全部事件作为常规接口。

## 6. 三套系统的边界

| 系统 | 事实来源 | 是否同步阻塞业务 | 是否允许更新 | 核心问题 |
| --- | --- | --- | --- | --- |
| 记录 | 自己接收事件 | 关键事件必须同步 | 不允许 | 发生了什么？ |
| 审计 | 记录事件 + 只读上下文 | 工具执行前同步 | 决策事件追加，不改历史 | 是否允许发生？ |
| 监控 | RecordStore 事件 | 通常异步 | 只更新派生投影 | 系统现在是否健康？ |

## 7. 第一版落地顺序

1. 冻结 `RecordEvent` 字段、事件词典和 canonical/hash 规则；
2. 实现 SQLite `RecordStore`、链头和幂等追加；
3. 实现 `TraceContext`、`StageRunner` 和 `ToolGateway`；
4. 接入无工具 `AuditorProvider` 和 `AuditPolicyEngine`；
5. 实现 `MetricsProjector`、checkpoint 和投影重建；
6. 增加开放调用 reconciler、`unknown` 状态和故障注入测试；
7. 最后再提供审计查询、监控快照和回溯 API。

## 8. 需要先讨论并冻结的点

- 是否把 `span_id` 作为操作生命周期关联 ID，还是单独增加 `operation_id`；
- 外部副作用工具是否强制要求 idempotency key；
- 审计 AI 不可用时是否所有工具都 fail-closed；
- 指标投影是事务内同步更新，还是统一采用 checkpoint 异步投影；
- 哈希链是全局链，还是按项目/租户分链。
