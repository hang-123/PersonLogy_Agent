# Notes: P10 最小原子架构重新推演

## Synthesized Findings

### 最小事实

- 记录原子是一条不可变事件，不是请求、Job 或工具调用的汇总对象。
- 通用事件需要表达：身份、时间、类型、trace/span、actor、target、结果、原因和哈希链完整性。
- `request_id`、`job_id`、`attempt_id`、工具/模型版本和 before/after digest 属于条件元数据。

### 三套系统的关系

- RecordStore：append-only 事实源，负责规范化、脱敏、幂等、哈希链和持久化。
- Audit：在副作用发生前同步审查 ToolIntent，输出决策事件；AuditPolicyEngine 是最终闸门，Auditor AI 不能提升权限。
- Monitoring：订阅/投影事件，生成计数、延迟、失败率、积压和新鲜度等低基数指标；可以从 RecordStore 重建。

### 关键可靠性约束

- 工具执行前必须先持久化请求、审查结果和 started 事件。
- 工具执行后的记录可能因崩溃失败；外部副作用必须带 `tool_invocation_id`/idempotency key，并由 reconciler 把无终态调用标记为 `unknown`。
- 不能承诺对不可事务化外部系统做到绝对 exactly-once，只能做到 durable intent + 幂等重试 + 可诊断未知态。
- structlog 是展示和调试通道，不是审计事实源；metrics 是投影，不是第二套事实源。

### 覆盖边界修正

- `EventAtom` 可以覆盖所有需要解释、追踪、审计和回放的语义事件，但不能要求 CPU/内存等基础设施指标、调试堆栈和第三方原始日志都符合审计字段。
- 推荐采用“统一外壳 + 类型化载荷”：通用字段包含身份、类型、版本、时间、来源、上下文、载荷和完整性；actor/entity/status 等按事件类型启用。
- `trace_id` 对业务语义事件通常必填；独立系统指标可以为空，但必须有 source 和采集时间。不能为了统一而伪造业务 trace。
