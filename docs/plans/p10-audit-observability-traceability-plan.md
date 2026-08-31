# P10 审计、监控与回溯基础设施开发计划（收敛版）

版本：v0.2
定位：跨 P6/P7/P8/P9 的公共基础设施，不改变业务模块职责

> P10 的最小记录原子、模块边界和第一版范围以[收敛架构说明](p10-minimal-record-architecture.md)为准；本文保留详细的接口、工具闸门、血缘和实施拆分。

## 1. 建设目标

P10 负责回答四类问题：

1. 谁在什么时候批准、修改、发布或执行了什么？
2. 某个任务、索引或模型调用为什么成功或失败？
3. 一个 Claim 或回答最终来自哪份原始资料、哪一段内容和哪次处理？
4. 给定一个来源版本或任务，能否安全地重新运行并比较结果？

P10 不负责知识编译、治理规则、Gel 回写或检索排序，只提供这些模块使用的公共记录和查询能力。

## 2. 三类能力边界

### 2.1 审计 Audit

审计是面向责任和变更的 append-only 事件流，不等同于普通日志。

需要覆盖：

- Schema Snapshot/Proposal 的创建、校验、审批、执行、回滚；
- ReviewTask 的领取、批准、驳回、修改和并发冲突；
- P7 未来的正式回写、事务结果和失败回滚；
- P8 检索策略、索引版本、模型版本和证据组装结果；
- P9 用户操作和权限拒绝；
- Job 的提交、领取、重试、成功、失败和取消。

建议统一事件结构：

```text
AuditEvent
  event_id
  occurred_at
  action
  actor_type / actor_id
  entity_type / entity_id
  project_id
  request_id / trace_id / job_id
  schema_version / model_version / index_version
  before_digest / after_digest
  reason
  metadata
```

第一阶段不把完整 PDF、完整 Prompt、API Key 或完整模型响应写入审计表；默认保存摘要、哈希、引用 ID 和脱敏元数据。

### 2.2 监控 Observability

监控分为日志、指标和 Trace 三层：

```text
结构化日志：具体事件和错误上下文
Metrics：可聚合的数量、时延、失败率、积压和新鲜度
Trace：一次请求/任务跨 API、Worker、模型、索引和检索的时间线
```

第一阶段建议：

- 延续现有 structlog；
- 将 `request_id` 统一传播到 Job 和 Worker attempt；
- 增加 metrics registry 和只读 metrics/health 输出；
- 预留 OpenTelemetry exporter，不强制引入外部服务；
- SQLite 环境先记录聚合快照，不把高频指标无限写入主知识表。

### 2.4 如何保证每个环节都有记录

不能依赖业务开发者在每个函数里手写几条日志。P10 采用四层保障：

1. **入口层**：API middleware 创建根上下文，所有请求自动记录开始、结束、状态码和耗时；
2. **任务层**：`JobService`/统一 `JobRunner` 自动记录 Job 提交、领取、每次 attempt 开始、成功、失败和重试；
3. **阶段层**：解析、编译、治理、审核、索引、embedding、检索等长流程必须通过 `StageRunner` 执行，由它统一产生 `stage.started`、`stage.succeeded`、`stage.failed` 和 timer metric；
4. **验证层**：建立 job kind → required stages → required events 的覆盖矩阵，并用故障注入测试检查异常路径也会产生 failed 事件。

业务模块只实现阶段动作本身，不直接负责事件格式、计时、trace 传播或哈希计算。内部普通 SQL 查询不逐条审计，只有状态变化、外部调用、重要决策和阶段边界进入审计/Trace。

审计与业务事务尽量使用同一 Unit of Work：知识状态和对应审计事件一起提交；失败回滚时，失败事件在独立的审计事务中追加。这样既不会出现“状态成功但没有审计”，也不会把失败原因丢掉。

### 2.5 `trace_id` 的语义和传播

建议明确区分四个 ID：

```text
trace_id   一次逻辑工作流，跨 API、子 Job 和重试保持不变
request_id 一次 HTTP 请求，查询任务状态时每次请求可不同
job_id     一个持久化 Job，跨进程和重试保持不变
attempt_id 一次实际执行尝试，每次 retry 重新生成
```

示例：

```text
上传 PDF 请求：trace=T1, request=R1
  → pdf.parse Job：job=J1, trace=T1
      → Worker attempt：attempt=A1
      → 编译子 Job：job=J2, trace=T1, parent_job=J1
          → retrieval.index Job：job=J3, trace=T1, parent_job=J2
```

Job 失败重试时仍使用 `trace_id=T1` 和相同 `job_id`，但生成新的 `attempt_id`；这样可以区分“同一任务的多次尝试”和“不同任务”。独立用户检索会创建新的 trace，但通过 `source_version_id`、`claim_id`、`index_version` 和 `retrieval_request_id` 与历史数据血缘关联。

Trace 上下文需要持久化到 Job 的执行上下文或专用字段，不能只放在进程内的 contextvar；contextvar 只负责当前调用栈传播，跨进程必须依赖 Job/审计数据恢复。

### 2.6 统一工具闸门与审计 AI

P10 增加一个独立的 `AuditedToolExecutor`（也可称 Tool Gateway）作为所有工具调用的唯一入口。业务模块、Job Handler 和阶段执行器不直接调用具体工具适配器，只向工具闸门提交结构化的 `ToolIntent`。

一次工具调用按以下顺序执行：

```text
ToolIntent
  -> 创建子 span，继承 trace_id
  -> 记录 tool.requested（参数仅保存脱敏摘要/哈希）
  -> 读取只读审计上下文快照
  -> 调用无工具审计 AI
  -> AuditPolicyEngine 做确定性策略校验
  -> 拒绝：记录 tool.denied，不调用实际工具
  -> 放行：记录 tool.started，调用工具
  -> 记录 tool.succeeded 或 tool.failed，以及耗时、结果摘要、副作用摘要
```

审计 AI 的隔离要求：

- 模型请求中不注册任何工具，固定使用 `tools=[]`，不能访问工具分发器、工具注册表或应用服务。
- 不授予数据库、文件系统、网络、密钥或写入凭证；它不主动查询系统，只判断 P10 模块传入的有限 `ReadOnlyAuditContext`。
- 输入只包含 `ToolIntent`、调用方身份/权限摘要、工具风险等级、相关 trace/job 状态和必要的只读资源摘要；默认不传完整密钥、Prompt 原文或未脱敏业务数据。
- 输出必须符合严格 JSON Schema，例如 `decision: allow|deny|review`、`risk_level`、`reasons`、`violated_policies`、`required_checks`；解析失败、超时或内容不完整都视为未获批准。
- 审计 AI 不能授予调用方额外权限。最终决策由确定性的 `AuditPolicyEngine` 完成：硬规则拒绝优先，AI 的 `deny/review` 不能被业务模块覆盖。

工具按风险分类，至少包括 `read`、`write`、`external_side_effect`、`schema_migration` 和 `secret_access`。第一版所有类别都必须经过审计 AI；审计 AI 不可用时统一 fail-closed。稳定后可以单独评估低风险、无副作用只读工具的降级放行，但必须保留 `audit_degraded` 事件和指标。

审计 AI 自身不经过 Tool Gateway，否则会形成递归调用。它通过专用的无工具 `AuditorProvider` 端口调用，调用前后记录 `auditor.review.started/succeeded/failed`，并把模型标识、策略版本、输出摘要和输出哈希写入同一条审计哈希链。这样既能回溯“为什么放行/拒绝”，又不会给审计 AI 留下调用工具的路径。

### 2.7 如何保证不存在绕过审计的调用路径

“每次工具调用都被记录”不能只靠约定，需要在架构、代码入口和测试三层保证：

1. **架构入口唯一化**：应用层只依赖 `ToolExecutor` 端口；具体工具适配器放在 adapters 层，由 Tool Gateway 持有和分发。
2. **执行器集中化**：`AuditedToolExecutor` 负责 trace/span 创建、preflight、审计 AI、策略判断、工具执行和 postflight，业务代码不拼接审计日志。
3. **静态与运行时约束**：禁止业务层导入具体工具适配器；测试扫描 import/依赖边界，并对 Tool Gateway 注入调用计数器，验证每个工具请求都有对应的请求、审查、执行结果事件。
4. **故障注入覆盖**：分别模拟审计链写入失败、审计 AI 超时、审计 AI 返回非法 JSON、策略拒绝、工具异常和进程重启，确认工具不会在缺少必要审计事件时继续执行。
5. **跨进程持久化**：`trace_id`、`parent_span_id`、`job_id`、`attempt_id` 和工具意图摘要写入 Job/事件上下文，不能只放在内存上下文变量中。

需要区分两类“记录”：不要求把每条内部 SQL 或每个函数调用都作为审计事件；要求所有对外部工具、状态变化、阶段边界和模型调用都从统一执行器进入，并且能在覆盖矩阵中证明没有漏掉关键边界。

### 2.8 最小记录原子与元数据

P10 的记录原子定义为一条不可变 `AuditEvent`，表示一个已经发生或被明确拒绝的事实。一次工具调用不是一条可更新的记录，而是多个事件组成的生命周期：`tool.requested`、审查结果、`tool.denied` 或 `tool.started`，以及最终的 `tool.succeeded/failed`。这样可以保留中途崩溃、超时和拒绝等部分事实，不能依赖事后更新一行记录来“补齐”。

最小事件可以抽象为：

```text
AuditEvent
  identity:   event_id, occurred_at, event_type, schema_version
  context:    trace_id, span_id, actor_type, actor_id
  target:     entity_type, entity_id
  outcome:    status, reason_code/error_code
  integrity:  sequence, prev_hash, event_hash
  evidence:   metadata (受控 JSON，含必要摘要/哈希)
```

其中前五组构成通用最小信封：

- `event_id`：事件唯一标识；
- `occurred_at`：事件发生时间，统一 UTC；
- `event_type`：事件词典中的稳定类型，如 `job.started`、`tool.denied`；
- `schema_version`：事件结构版本；
- `trace_id`：所属逻辑链路；
- `span_id`：本次阶段/审查/工具执行的具体节点；
- `actor_type`、`actor_id`：谁触发或代表谁执行，系统事件使用 `system`；
- `entity_type`、`entity_id`：事件作用对象；工具调用使用 `tool_invocation` 和调用 ID；
- `status`：`requested`、`started`、`succeeded`、`failed`、`denied` 等有限枚举；
- `reason_code` 或 `error_code`：拒绝、失败和降级的机器可检索原因；
- `sequence`、`prev_hash`、`event_hash`：全局哈希链所需的顺序和完整性字段。

以下字段不是所有事件都必须有，而是按场景条件必填：

| 场景 | 条件字段 |
| --- | --- |
| HTTP 入口 | `request_id`、`route`、`http_status` |
| Job/Worker | `job_id`、`attempt_id`、`parent_job_id` |
| 工具调用 | `tool_invocation_id`、`tool_name`、`tool_version`、`risk_class`、`args_digest`、`result_digest` |
| 状态变化 | `before_digest`、`after_digest`、`version` |
| 模型调用 | `model_name`、`model_version`、`prompt_digest`、`response_digest` |
| 血缘关系 | `source_ref`、`derived_ref`、`relation_type` |

`metadata` 不能作为无限制的原文容器，而应是经过字段白名单和大小限制的受控 JSON。默认只保存 ID、版本、枚举、错误码、脱敏摘要和哈希；完整 Prompt、原文、密钥和工具返回内容不进入审计事件。

因此，“最小可审计事实”可以概括为：**谁，在什么 trace/span 中，于何时，对什么对象，尝试做了什么，结果如何，并且这条记录是否能通过哈希链验证。** `request_id`、`job_id`、`attempt_id` 等是用于跨边界定位的条件元数据，不应被误认为每条事件都必须填充。

重点指标：

- API 请求量、错误率、P50/P95 延迟；
- Job 队列深度、等待时长、重试率、失败率；
- PDF/对话导入、编译、治理、索引耗时；
- Schema 校验失败、审批等待和迁移失败；
- embedding 调用耗时、错误率、缓存命中率和模型版本；
- 检索 lexical/semantic 命中数量、融合耗时、证据覆盖率和无证据比例；
- 索引最新版本、最后成功时间和重建耗时；
- 数据库大小、备份时间和恢复验证结果。

### 2.3 回溯 Traceability / Lineage

回溯不是只查日志，而是查询稳定 ID 之间的派生关系：

```text
Project
  → Source
  → SourceVersion
  → ContentBlock
  → Citation
  → Claim / Relation
  → ReviewTask / AuditEvent
  → RetrievalDocument / Embedding
  → RetrievalRequest / EvidenceSet
```

至少支持四种查询：

1. `trace_claim(claim_id)`：Claim 的来源、审核、索引和当前状态；
2. `trace_source_version(source_version_id)`：该版本产生的知识、任务、索引和失败记录；
3. `trace_job(job_id)`：任务所有状态变化、attempt、错误、输入输出版本；
4. `trace_retrieval(request_id)`：查询、召回通道、融合版本、命中 Claim 和证据。

## 3. 推荐接口边界

```text
AuditSink
  append(event)

LineageStore
  add_link(link)
  trace_entity(entity_type, entity_id)

MetricsSink
  increment(name, value, tags)
  observe(name, value, tags)
  snapshot()

TraceContext
  current()
  child(...)
```

业务模块通过这些端口写入，不直接依赖 SQLite、structlog、Prometheus 或 OpenTelemetry。

## 4. SQLite 第一版数据结构

建议新增独立表，不污染知识事实表：

```text
audit_event
- event_id
- occurred_at
- action
- actor_type
- actor_id
- entity_type
- entity_id
- project_id
- request_id
- trace_id
- job_id
- schema_version
- model_version
- index_version
- before_digest
- after_digest
- reason
- metadata

lineage_link
- link_id
- project_id
- from_type / from_id
- relation_type
- to_type / to_id
- created_at
- metadata

metric_snapshot
- id
- metric_name
- value
- tags
- captured_at
```

`audit_event` 和 `lineage_link` 采用追加式写入；更新和删除通过新事件表达。`metric_snapshot` 只保存低频聚合或快照，高频指标交给未来的 Metrics 后端。

审计链建议增加：

```text
sequence
prev_hash
event_hash
```

`event_hash = SHA256(canonical_event + sequence + prev_hash)`。SQLite 追加时使用写事务锁定当前 head，插入事件并更新 head；普通业务 API 不提供更新/删除审计事件的能力，并提供链校验命令/接口。

## 5. 分阶段开发计划

### P10-A：事件词典与上下文

- 固化事件命名规范和实体类型；
- 定义 actor、request、trace、job、attempt 字段；
- 制定敏感数据脱敏、哈希和保留策略；
- 让 Job、ReviewTask、Schema Proposal、Index Build 使用同一套上下文；
- 固化 `trace_id/request_id/job_id/attempt_id/parent_job_id` 的传播规则。

退出标准：同一条处理链路可以用 `trace_id` 串起 API、Job 和 Worker。

### P10-B：审计核心与工具闸门

- 实现 `AuditEvent` 领域对象；
- 实现 `AuditSink` 和 SQLite append-only adapter；
- 在 JobService、GovernanceService、SchemaChangeService、RetrievalService 的关键状态变化处写事件；
- 记录 before/after digest 和 reason，不保存敏感原文。
- 为事件增加 sequence、prev_hash、event_hash 和全局 audit head；
- 增加链完整性校验和篡改检测结果。
- 实现 `AuditedToolExecutor`、无工具 `AuditorProvider` 和确定性的 `AuditPolicyEngine`；
- 统一记录工具调用的 requested、审查、denied、started、succeeded/failed 事件。

退出标准：审核决策、任务状态和 Schema Proposal 生命周期均可查询。

### P10-C：血缘和回溯查询

- 实现 `LineageLink`；
- 在编译、治理、审核、索引和检索环节写入派生链接；
- 增加 Claim、SourceVersion、Job、RetrievalRequest 四类回溯查询；
- 支持按项目过滤和时间范围过滤。

退出标准：从 Claim 能回到原文，从 SourceVersion 能找到所有派生 Claim 和索引，从检索请求能解释命中证据。

### P10-D：监控基础

- 在 API 中统一传播 request/trace ID；
- 为 Job、索引、embedding、检索记录计数和耗时；
- 增强 readiness，增加队列积压、索引新鲜度和数据库状态；
- 提供本地 metrics snapshot 或只读 metrics endpoint；
- 预留 OpenTelemetry exporter。
- 用 StageRunner 统一生成阶段耗时、成功率和失败指标，而不是依赖手写埋点。

退出标准：不查看代码和数据库，也能判断系统是否积压、失败或索引过期。

### P10-E：回放与诊断

- 通过 SourceVersion 生成 replay plan，而不是直接覆盖线上数据；
- replay 使用新的 Job/trace，保留原结果；
- 支持新旧 Schema、编译器、embedding 模型和索引版本对比；
- 默认先生成候选差异，人工确认后再发布。
- 回放创建新的 trace/job/attempt，并记录 parent_trace_id/parent_job_id，不覆盖历史链路。

退出标准：可以安全重跑一条链路，并解释差异来自输入、规则、Schema、模型还是索引。

### P10-F：外部后端适配

- Gel 审计持久化适配器；
- OpenTelemetry Trace exporter；
- Prometheus/OTel Metrics exporter；
- 审计导出、归档和校验工具；
- 备份恢复后审计和血缘一致性验证。

## 6. 关键安全约束

- 审计记录不可通过普通业务 API 修改；
- 普通用户不能查看其他项目的审计和血缘；
- Prompt、原文和模型响应默认脱敏或只存摘要；
- 回放不得覆盖原任务、原 Claim 或原索引；
- 审计事件需带 schema/model/index 版本，避免无法复现；
- 指标标签不得包含原文、用户输入全文或高基数敏感值。

## 7. 建议的第一批范围

第一批不要一次性做完整监控平台，建议只做：

1. AuditEvent + SQLite append-only 表；
2. request_id/trace_id/job_id 统一传播；
3. `AuditedToolExecutor` + 无工具审计 AI + 确定性策略闸门；
4. Job、ReviewTask、SchemaProposal、IndexBuild 四类审计接入；
5. Claim/SourceVersion/Job 的只读回溯查询；
6. 队列、索引新鲜度、任务失败率三组基础指标。

第一批还必须包含：

7. 审计哈希链写入和校验；
8. Job/Worker 的 trace 上下文持久化；
9. 阶段覆盖矩阵、Tool Gateway 覆盖矩阵和异常路径故障注入测试。

向量召回、P9 前端和 P7 回写只接入 P10 端口，不把各自业务实现塞进 P10。
