# P10-B 补全计划

## 目标

补齐 P10-B 的剩余验收范围，使治理、Schema、检索、索引构建和工具调用均能产生可查询、可校验且不泄露敏感原文的审计事实。

## 阶段

- [x] 盘点缺口与依赖边界
- [x] 补齐 `AuditEvent` 前后摘要字段和敏感元数据隔离
- [x] 接入 Governance、Schema、Retrieval 与 IndexBuild 审计
- [x] 实现 `AuditedToolExecutor`、`AuditorProvider`、`AuditPolicyEngine`
- [x] 补充验收测试并运行 Ruff、Mypy、Pytest

## 关键决策

- 业务服务只依赖 `AuditSink`/工具端口，不直接依赖 SQLite 实现。
- 审计元数据默认白名单化；发现原文、Prompt、密钥等字段时 fail-closed，不写入审计表。
- `before_digest`/`after_digest` 只保存确定性摘要，不保存原始状态。
- Tool Gateway 的审计链写入、审计 AI 超时/非法结果和策略拒绝均采用 fail-closed。
- P10-C 的 `LineageLink` 不作为本阶段前置依赖。

## 当前状态

已完成：P10-B 剩余验收范围已落地并通过全量验证。
