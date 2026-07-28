# 个人知识关系系统：P0 开发规划

> 基线：PRD v0.4.0 与《个人知识关系系统_P0开发计划表》；周期 2026-07-28～2026-08-31。

## 1. 交付目标

P0 同时交付两条可独立验收的成果：

1. **产品闭环**：真实岗位资料可沿“来源 → Evidence → Candidate → 人工审核 → Published → Claim → Decision”流转，并能从决策反向追溯到原始证据。
2. **技术论证**：PostgreSQL 作为唯一权威源，将 Published 知识异步投影到 Neo4j；完成四类 Topology 查询、投影校验/重建，以及至少两类递归 CTE/Cypher 对照实验。

P1 的 PDF、AI 辅助抽取和 MCP 不进入 P0 关键路径。优先保证人工录入与审核闭环可用。

## 2. 工程原则与边界

- 采用模块化单体，不拆微服务。
- PostgreSQL 17 承担唯一权威写入、版本、状态、任务和审计。
- Neo4j 只接受投影 Worker 写入，可关闭、可降级、可从 PostgreSQL 全量重建。
- Candidate 与 Published 逻辑隔离；AI 或外部接口不能直接发布正式知识。
- 领域规则独立于 FastAPI、SQLAlchemy、Neo4j 和 LLM Provider。
- 关系是一等实体；关键关系必须绑定 Evidence 或上游依据。
- `derived_from`、`based_on` 必须无环；普通关系查询限制深度、节点数和超时。
- 长任务使用 `processing_job` + 单 Worker，不引入 Redis 或消息队列。
- 敏感数据默认私有；日志不记录 Token、密码或大段原文；Context Pack 最小披露。

## 3. 仓库布局

```text
apps/
  api/                 FastAPI 模块化单体与 Worker
  web/                 React 管理端
packages/
  contracts/           跨端 REST / Context Pack 契约
infra/
  postgres/            PostgreSQL 初始化与扩展
  neo4j/               版本化约束、索引和 Mapping
docs/
  architecture/        ADR、Ontology、关系字典
  api/                 OpenAPI 与 Context Pack 说明
  experiments/         数据集、查询口径与实验报告
scripts/               开发、校验、基准和运维入口
```

## 4. 里程碑与验收出口

| 里程碑 | 日期 | 主要交付 | 验收出口 |
|---|---|---|---|
| M0 方案定版 | 07-28～08-02 | Ontology 字典、关系字典、REST/Context Pack 契约、Topology 实验方案 | 模型、边界、查询假设可进入开发 |
| M1 工程与模型基线 | 08-03～08-09 | 工程脚手架、Compose、迁移、核心 Schema、领域约束、样本数据 | 小样本可录入并通过领域校验 |
| M2 知识发布闭环 | 08-10～08-16 | 来源、Evidence、Candidate、审核、发布、Worker | 正式知识可发布、可审计、不可绕过审核 |
| M3 关系核验闭环 | 08-14～08-23 | 对象/关系、Claim/Decision、追溯、版本、新鲜度、影响分析 | 决策能回到证据，上游变化可定位影响 |
| M4 图拓扑与外部消费 | 08-10～08-26 | Neo4j 投影/重建、四类查询、搜索、Context Pack、只读 REST | 投影可重建，查询正确，外部只读可消费 |
| M5 技术论证与交付 | 08-25～08-31 | CTE/Cypher 基准、AC-01～27、安全检查、部署手册、实验报告 | 核心用例 100% 通过并给出 Neo4j 去留结论 |

## 5. 建议迭代顺序

### Iteration 0：契约冻结与工程基线

- 完成对象类型、状态、关系端点/基数/证据要求、无环规则。
- 冻结 `/v1` 错误结构、分页、稳定 ID、Context Pack Schema。
- 建立前后端、配置、迁移、日志、测试、Compose 和 CI 基线。

### Iteration 1：权威写入与发布闭环

- 实现 `knowledge_object`、`knowledge_relation`、`source_document`、`evidence`、`claim`、`decision`、`candidate`、`object_version`、`audit_log`。
- 以应用命令实现 capture/review/publish；发布事务同时写审计与 `graph_projection_event`。
- 建立 3 公司、5 岗位、10 技能、2 经历的小样本。

### Iteration 2：查询、追溯与影响

- 实现结构化检索和 `pg_trgm` 查重/模糊匹配。
- 实现一/二跳查询、Decision/Claim 反向追溯、版本/新鲜度、待复核队列。
- PostgreSQL 递归 CTE 作为基础实现与 Neo4j 降级路径。

### Iteration 3：图投影与外部消费

- Worker 幂等消费投影事件，维护 Mapping Version 与 Checkpoint。
- 实现差异校验、DEGRADED、有限重试和全量重建。
- 完成四类 Topology 查询、Context Pack JSON/Markdown 与只读 REST。

### Iteration 4：实验与交付

- 生成固定随机种子的 1,000 对象/5,000 关系数据集。
- 两类核心查询预热后各运行不少于 30 次，记录 P50/P95/最大值、结果规模和表达复杂度。
- 执行 AC-01～AC-27、安全/隐私、降级/回滚和部署验收。

## 6. 质量门禁

- 每个业务命令具备单元测试；发布、审计、投影事件具备事务集成测试。
- 每个 API 具备成功、鉴权、校验、无结果、超限和敏感字段裁剪测试。
- Candidate 不得出现在正式只读 API；Neo4j 失败不得阻断 PostgreSQL 发布。
- 迁移可在空库重复执行；投影可清空重建；种子数据可重复生成。
- 阻断级/严重级缺陷为 0，AC-01～AC-27 核心用例通过率 100%。

## 7. 当前初始化范围

本次初始化只建立可运行工程基线：目录、配置示例、FastAPI 健康检查、React 占位页、测试入口、Docker Compose、数据库扩展初始化、Neo4j Mapping 占位和基础文档。领域表与业务接口将在 M0 字典冻结后通过 Alembic 正式实现，避免脚手架阶段固化尚未确认的模型细节。
