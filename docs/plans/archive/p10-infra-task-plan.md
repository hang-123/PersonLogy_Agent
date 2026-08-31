# Task Plan: P10 审查、监控与回溯基础设施

## Goal
建立独立于 P7/P8/P9 业务模块的审计、运行监控、数据血缘和可回放基础设施，让每次知识变化、任务执行、模型调用和检索结果都可解释、可定位、可重放。

## Phases
- [x] Phase 1: 盘点现有日志、请求 ID、Job、ReviewTask 和 Schema 基础
- [x] Phase 2: 拆分审计、监控、回溯三类能力及解耦边界
- [ ] Phase 3: 确认事件词典、数据保留和敏感信息策略
- [ ] Phase 4: 实现 AuditEvent、TraceContext、LineageLink 端口与 SQLite 适配器
- [ ] Phase 5: 接入 API、Job、审核、索引和模型调用链路
- [ ] Phase 6: 实现查询、回溯、重放和监控输出
- [ ] Phase 7: 验证、性能评估并预留 Gel/OpenTelemetry 适配器

## Key Questions
1. 审计记录是否需要不可篡改校验链，还是当前阶段 append-only 即可？
2. 检索问题、LLM Prompt 和原文是否记录原文，还是只记录哈希/脱敏摘要？
3. SQLite 阶段的监控是否先采用结构化日志 + metrics API，后续再接 Prometheus/OpenTelemetry？
4. 回溯是否需要支持从 SourceVersion 重新运行整条链路，还是先支持只读血缘查询？
5. 审计 AI 不可用时，低风险只读工具是否允许降级放行，还是所有工具统一拒绝？

## Decisions Made
- P10 是公共基础设施，不被 P7/P8/P9 任何一个业务模块反向依赖。
- 业务模块只依赖 `AuditSink`、`MetricsSink`、`LineageStore` 和 `TraceContext` 端口。
- 审计、运行监控、数据血缘分开建模，不能用普通日志替代审计，也不能用审计表替代时序指标。
- 当前先以 SQLite + 结构化日志落地；未来可替换为 Gel 审计表、OpenTelemetry 和 Prometheus 适配器。
- 审计默认记录元数据、状态、ID、版本和差异摘要，不默认保存完整原文、密钥或未脱敏 Prompt。
- 审计事件采用全局 append-only 哈希链：每条事件包含 sequence、prev_hash 和 event_hash，并通过单独的校验器验证链完整性。
- `trace_id` 表示一次逻辑处理链路；`request_id` 表示单次 HTTP 请求；`job_id` 表示持久化任务；`attempt_id` 表示一次具体执行尝试。
- 每个阶段必须通过统一 StageRunner/JobRunner 进入，自动产生 started/succeeded/failed 事件和耗时指标；不允许业务模块自行拼接审计日志。
- 成功任务必须同时存在阶段完成事件；通过故障注入测试和事件覆盖矩阵检查漏记。
- 所有工具调用必须经过统一 `AuditedToolExecutor`/Tool Gateway；业务模块和 Job Handler 不得直接调用具体工具适配器。
- 工具调用采用 preflight/postflight 两段式记录：执行前记录意图、参数摘要和审计 AI 决策；执行后记录 started、succeeded/failed、耗时、结果摘要和副作用摘要。
- 审计 AI 是无工具、无写权限的专用决策子代理：请求中不注册任何工具，不访问数据库、文件系统、网络或工具注册表，只接收结构化审计意图和由 P10 读取后提供的只读上下文快照。
- 审计 AI 只能给出 `allow/deny/review` 建议，不能提升权限；最终放行由确定性的 `AuditPolicyEngine` 兜底，硬性策略拒绝优先于 AI 建议。
- 第一版默认 fail-closed：审计 AI 超时、输出格式错误或审计链写入失败时，不执行工具；后续只有在明确批准后，才考虑对低风险纯只读工具做降级策略。
- 审计 AI 自身的调用也要记录为 `auditor.review.started/succeeded/failed`，但不再经过 Tool Gateway，避免递归；它使用无工具的专用 `AuditorProvider` 端口。
- `trace_id` 贯穿请求、阶段、审计 AI 审查和实际工具执行；`span_id`/`parent_span_id` 表达嵌套关系，`job_id`/`attempt_id` 负责跨进程任务与重试定位。当前调用栈用上下文传播，跨进程恢复则把执行上下文持久化到 Job 和审计事件。
- 最小记录原子是一条不可变 `AuditEvent`，至少包含事件身份、时间/类型、trace/span、actor、目标、结果、原因和哈希链字段；请求、Job、工具、模型和血缘字段按场景条件必填。
- 一次工具调用不更新单行记录，而是追加 requested、审查、denied/started、succeeded/failed 等事件，确保中途崩溃和拒绝也可回溯。

## Errors Encountered
- 无。

## Status
**Currently in Phase 3** - 已确认哈希链、摘要/哈希脱敏、SQLite + structlog、先只读回溯；已确定统一工具闸门 + 无工具审计 AI 的架构，下一步细化端口、策略和覆盖测试。
