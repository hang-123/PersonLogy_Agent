# P10-E 回放与诊断开发记录

## 现有边界

- SourceVersion 已有稳定 ID、content_hash、object_key 和 version。
- Job 已有 trace_id、request_id、attempt、payload 和审计状态事件，但没有 parent_job_id 字段。
- CompilationBundle 和 KnowledgeCompiler 已暴露 prompt_version、model_name；当前实现为本地启发式编译器。
- Schema 管理已有 namespace/version；索引构建已有 project/version 和 audit event。
- P10-C 已提供 SourceVersion/Job 的血缘查询，可复用回放父子关系。

## 本阶段口径

- replay 不直接复制或更新业务事实表；
- 回放 Job payload 保存受控版本快照和父级引用，不保存原文；
- 差异诊断使用 input content hash 和各版本字符串比较，不保存 Prompt、原文或模型响应；
- 没有可执行 embedding provider 时，embedding_version 允许为 null，并在诊断中标记为 unavailable。

## 实现结果

- 新增 ReplayPlan、ReplayVersionSet、ReplayComparison 和五类差异维度模型。
- 新增 SQLite replay_plan、replay_comparison 存储及 ReplayStore 端口。
- SourceRepository 增加按项目读取 SourceVersion 的契约，阻断跨项目回放。
- ReplayService 支持 create_plan、approve、compare；审批后使用新的 trace 和新的 queued Job。
- replay Job payload、Job 审计事件和血缘关系记录 replay_plan_id、parent_job_id、parent_trace_id。
- Worker 复用现有 knowledge.compile 执行路径，并在 replay 编译完成后登记候选比较。
- 新增 replay API：创建计划、查询计划、审批计划、提交候选比较。
- 候选比较默认保持 candidate 状态，P10-E 不提供自动发布和正式知识覆盖能力。

## 验证结果

- P10-E 专项测试：2 passed
- 全量测试：50 passed, 6 skipped
- Ruff：通过
- mypy：通过（114 个源文件）
- SQLite API 烟测：跨项目/不存在 SourceVersion 返回受控 422
