# P10：审计、监控与回溯基础设施任务包

## 目标

以不可变的最小记录原子为共同事实源，建立跨 P6/P7/P8/P9 使用的审计、运行监控、数据血缘和可回放能力。P10 不替代普通日志、业务数据库或指标平台，也不承载知识编译、治理、回写和检索排序等业务职责。

## 核心边界

- `RecordStore`：负责规范化、脱敏、幂等追加、哈希链和持久化。
- `Audit`：负责关键动作和工具调用的准入审查、决策记录和责任追踪。
- `Monitoring`：从记录事件派生低基数指标、健康视图和告警。
- `Lineage`：记录 SourceVersion、ContentBlock、Claim、Job、Index 和 Retrieval 之间的派生关系。

业务模块只依赖端口，不直接依赖 SQLite、structlog、Prometheus 或 OpenTelemetry。

## 最小记录原子

通用事件外壳至少包含：

```text
event_id, occurred_at, event_type, schema_version
trace_id, span_id, actor, target
status, reason_code/error_code
sequence, prev_hash, event_hash
metadata
```

`request_id`、`job_id`、`attempt_id`、工具/模型版本、before/after digest 和血缘引用按场景条件必填。完整 Prompt、原文、密钥和工具返回全文不进入审计事件。

一次工具调用由多个追加事件组成：`tool.requested`、审查结果、`tool.denied` 或 `tool.started`，以及最终的 `tool.succeeded` / `tool.failed` / `tool.unknown`。

## 阶段与验收

### P10-A：事件词典与上下文

- 冻结事件命名、实体类型、字段白名单和留存策略。
- 固化 `trace_id/request_id/job_id/attempt_id/parent_job_id` 传播规则。
- 退出标准：同一处理链可用 `trace_id` 串起 API、Job 和 Worker。

### P10-B：RecordStore 与审计核心

- 实现 `AuditEvent`、`AuditSink`、SQLite append-only adapter 和哈希链校验。
- 实现 `StageRunner`、`ToolGateway`、`AuditorProvider` 和确定性的 `AuditPolicyEngine`。
- 退出标准：Job、ReviewTask、SchemaProposal、IndexBuild 和工具调用均可审计。

### P10-C：血缘与只读回溯

- 实现 `LineageLink` 及 Claim、SourceVersion、Job、RetrievalRequest 四类查询。
- 退出标准：可从 Claim 回到原始资料，也可从来源版本找到全部派生结果。

### P10-D：监控投影

- 实现 `MetricsProjector`、checkpoint、失败重放和健康快照。
- 首期覆盖任务失败率、队列积压、索引新鲜度、审计链状态和工具未知态。
- 退出标准：可以判断系统是否失败、积压、过期或存在未收敛调用。

### P10-E：回放与诊断

- 基于 SourceVersion 生成新的 replay trace/job/attempt。
- 保留原结果，支持 Schema、规则、模型和索引版本对比。
- 退出标准：可以安全重跑并解释差异来源，不覆盖历史事实。

### P10-F：外部后端与运维工具（代码交付完成，Gel 在线迁移待目标环境执行）

- [x] Gel 审计持久化适配器与 schema migration；
- [x] OpenTelemetry Trace bridge；
- [x] Prometheus / OTel Metrics bridge；
- [x] 审计导出、gzip 归档与离线链校验；
- [x] 备份恢复后的审计、血缘一致性报告与指纹比较。

## 第一版范围

1. SQLite `RecordStore`、幂等追加、哈希链和校验器；
2. `TraceContext`、`StageRunner`、`ToolGateway`；
3. 无工具审计 AI + 确定性策略闸门，第一版 fail-closed；
4. Job、ReviewTask、SchemaProposal、IndexBuild 事件接入；
5. Claim、SourceVersion、Job 的只读回溯查询；
6. 任务失败率、队列积压、索引新鲜度和审计完整性指标；
7. 覆盖矩阵、故障注入、哈希链和投影重建测试。

## 明确不做

- 不记录每条内部 SQL 或每个函数调用；
- 不把 CPU、内存和普通 DEBUG 日志强行塞入审计事件；
- 不承诺不可事务化外部系统的绝对 exactly-once；
- 不在回放时覆盖线上知识、索引或历史审计；
- 不在 P10 内实现业务审批、知识编译、正式回写或检索排序。

## 关联文档

- [P10 最小记录原子架构](../../plans/p10-minimal-record-architecture.md)
- [P10 审计、监控与回溯开发计划](../../plans/p10-audit-observability-traceability-plan.md)
- [P10 架构重新推演](../../plans/p10-minimal-architecture-rethink.md)
