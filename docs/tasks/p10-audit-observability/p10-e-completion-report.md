# P10-E 回放与诊断完成报告

## 交付结论

P10-E 已完成 SQLite 第一版安全回放闭环：从 SourceVersion 创建 replay plan，人工审批后才生成新的 replay Job/Trace，执行结果以候选比较保存，不修改原 Job、SourceVersion、Claim、IndexBuild 或历史审计。

## 回放流程

SourceVersion → 创建 ReplayPlan（proposed） → 人工审批 → 新 Job/新 Trace/新 attempt → 复用编译执行路径 → ReplayComparison（candidate） → 后续人工发布流程

## 诊断维度

- input：输入 content hash 是否变化；
- schema：基线与目标 Schema 版本是否变化；
- compiler：编译器/Prompt 版本是否变化；
- embedding：embedding 版本是否变化；
- index：索引版本是否变化；
- output：提供新旧输出 digest 后判断结果是否变化。

比较记录只保存版本字段、差异维度和 digest，不保存 Prompt、原文、模型响应或完整错误。

## 接口

- POST /v1/replay/plans
- GET /v1/replay/plans/{plan_id}
- POST /v1/replay/plans/{plan_id}/approve
- POST /v1/replay/plans/{plan_id}/compare

所有查询和变更接口要求 project_id，跨项目 SourceVersion 会被拒绝。

## 验证

- 50 passed, 6 skipped
- Ruff 通过
- mypy 通过
- SQLite API 路由烟测通过

## 范围边界

本阶段提供安全计划、隔离执行和候选诊断，不自动发布回放结果。实际 embedding provider、Gel 适配和人工发布工作流留给后续阶段。
