# Notes: P10 审查、监控与回溯基础设施

## Current Evidence

- API 已有请求 ID 中间件：`apps/api/app/main.py`。
- API/Worker 使用 structlog：`apps/api/app/core/logging.py`、`apps/api/app/worker.py`。
- Job 已保存状态、进度、阶段、尝试次数、失败原因和时间：`packages/personlogy_core/src/personlogy/domain/job.py`。
- ReviewTask 已保存审核前后内容、审核者、版本和审核时间：`packages/personlogy_core/src/personlogy/domain/governance/models.py`。
- Schema Proposal 已保存状态和版本，但当前没有完整的 Proposal 审计事件流。
- SQLite Feature Store 已保存索引构建状态，但当前没有统一的 lineage/audit 关联。

## Gaps

- request_id 没有统一进入 Job、审计和血缘记录。
- Job 状态变化没有独立的 append-only 审计事件。
- ReviewTask 决策没有统一事件类型和 actor/context 字段。
- Schema Proposal 的创建/校验/审批/执行没有完整事件序列。
- SourceVersion → ContentBlock → Citation → Claim/Relation → Review → Index → Retrieval 的链路需要统一查询模型。
- 当前健康检查主要反映进程和依赖状态，缺少队列积压、失败率、索引新鲜度和 embedding 状态。

## Proposed Concepts

### AuditEvent

记录谁在什么请求/任务中，对什么对象执行了什么动作，以及动作前后状态摘要。

核心字段：`event_id`、`occurred_at`、`actor_type`、`actor_id`、`action`、`entity_type`、`entity_id`、`project_id`、`request_id`、`job_id`、`trace_id`、`schema_version`、`model_version`、`before_digest`、`after_digest`、`metadata`。

### LineageLink

记录对象之间的来源和派生关系，例如 `derived_from`、`cites`、`reviewed_by`、`indexed_from`、`retrieved_by`。

### TraceContext

贯穿 API 请求、Job、Worker attempt、模型调用、索引构建和检索响应，最少包括 `request_id`、`trace_id`、`job_id`、`attempt`、`project_id`。

### Metrics

记录数值型运行状态，不写入审计事件：任务延迟/失败率、队列深度、索引新鲜度、embedding 延迟、检索耗时、证据覆盖率等。

## 2026-08-28：统一工具闸门与审计 AI 方案

- 用户确认希望采用“中心记录模块 + 每次工具调用前经过专用审计 AI”的模式。
- 所有工具调用统一经过 `AuditedToolExecutor`/Tool Gateway，业务模块不得直连具体工具适配器。
- 调用前记录 `tool.requested`，由 P10 读取只读上下文并调用无工具审计 AI；随后由确定性的 `AuditPolicyEngine` 做最终放行判断。
- 审计 AI 不注册工具，不访问数据库/文件系统/网络，不持有任何写入或工具调用凭证；只能处理 P10 传入的结构化上下文。
- 调用被拒绝时只写 `tool.denied`；调用被放行时记录 `tool.started` 和 `tool.succeeded/failed`，并保存耗时、结果摘要和副作用摘要。
- 审计 AI 自身通过专用 `AuditorProvider` 调用，记录 `auditor.review.started/succeeded/failed`，不经过 Tool Gateway，避免递归。
- 第一版采用 fail-closed：审计 AI 超时、输出非法、审计链失败时，工具不执行。低风险只读降级放行暂不启用。
- `trace_id` 贯穿完整逻辑链；`span_id`/`parent_span_id` 表达审查与工具执行的嵌套关系；跨进程恢复依赖 Job/事件中持久化的执行上下文。
