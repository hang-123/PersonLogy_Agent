# P10-E 回放与诊断开发计划

## 目标

基于 SourceVersion 创建不可覆盖原事实的 replay plan，审批后生成新的 replay Job/Trace/attempt，并对原任务与回放结果做版本化候选差异比较。

## 范围

- ReplayPlan：输入 SourceVersion、父 Job/Trace、Schema/编译器/embedding/索引版本快照和目标版本；
- replay Job：使用新的 Job/Trace，保留 parent_job_id/parent_trace_id，不复用原 Job；
- ReplayComparison：记录输入、Schema、编译器、embedding、索引五个差异维度；
- 候选差异：只保存摘要和 digest，不自动写入正式知识；
- 人工发布闸门：P10-E 只提供审批状态和候选结果，不执行正式发布。

## 阶段

- [ ] 盘点 SourceVersion、Job、编译器、Schema 和索引版本边界
- [x] 实现 ReplayPlan/ReplayComparison 领域模型、端口和 SQLite 存储
- [x] 实现计划创建、审批生成新 Job/Trace 和版本快照
- [x] 实现回放结果登记及五维候选差异诊断
- [x] 接入 API、审计/血缘并补充不覆盖原事实的测试

## 关键决策

- 创建计划是只读诊断动作；审批前不创建 Job，不触发重跑。
- 审批只生成新的 queued Job，不修改原 Job、Claim、SourceVersion、IndexBuild 或审计事件。
- parent_trace_id 和 parent_job_id 同时保存在 ReplayPlan、回放 Job payload、审计 metadata 和血缘边中。
- 版本差异采用摘要字段：schema_version、compiler_version、embedding_version、index_version、input_content_hash。
- 回放结果先登记为 candidate comparison；人工发布由后续业务审批模块负责。
- 当前 SQLite 版本完成结构和诊断闭环，Gel/外部模型执行适配留在后续后端工作。

## 退出标准

- 可从 SourceVersion 创建 replay plan，并能查询计划状态；
- 审批后产生新的 replay Job/Trace/attempt，原 Job 保持不变；
- 可登记 replay 结果并得到按输入、规则、Schema、模型、索引归因的候选差异；
- 测试证明回放不会覆盖历史业务事实。

## 当前状态

已完成：回放计划、审批生成新 Job/Trace、版本差异诊断、候选比较、API、审计/血缘和不覆盖原事实测试均已落地。

## Errors Encountered

- 初次血缘测试发现比较结果使用 replay_job 类型，无法从普通 job 根节点回溯；已统一为 job 实体类型并通过测试。
- API 和领域层初次检查发现 import 顺序、类型注解和 payload 类型问题，已修复并通过 Ruff/mypy。
