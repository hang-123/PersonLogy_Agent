# Notes: 个人知识关系系统

## Sources

### Source 1: 个人知识关系系统_PRD_v0.4.md
- 版本 v0.4.0，P0 求职域，讨论稿，预计 3～5 周。
- 双目标：交付个人知识关系产品闭环；完成 PostgreSQL/Neo4j Topology 技术论证。
- P0 主链：来源 → Evidence → Candidate → 人工审核 → Published → Claim/Decision → 反向追溯。
- PostgreSQL 17 是唯一权威源；Neo4j 是已发布知识的异步、可校验、可重建查询投影。
- 架构：模块化单体；React + TypeScript + Vite + Ant Design + React Flow；Python 3.12 + FastAPI + Pydantic + SQLAlchemy + Alembic。
- 长任务：`processing_job` + 单 Worker；不引入 Redis、消息队列、微服务、Kubernetes、向量数据库。
- P0 API 只读，AI 仅能生成 Candidate，禁止绕过人工审核写正式知识。
- 核心非功能：默认私有、日志脱敏、Sensitive 不默认导出/投影、软删除与审计原子性。
- 容量假设：对象 ≤10,000、关系 ≤50,000、来源 ≤5,000、并发 ≤5。
- 验收：AC-01～AC-27；核心用例通过率 100%，阻断级/严重级缺陷为 0。

### Source 2: 个人知识关系系统_P0开发计划表.xlsx
- 工作表：`P0开发计划`（46 项任务）、`里程碑`（M0～M5）。
- P0 日程：2026-07-28 至 2026-08-31。
- 已完成：PRD 基线与范围、总体技术架构；其余 P0 任务待启动。
- P1 项：PDF 导入、AI 辅助抽取、只读 MCP；不纳入 P0 关键路径。
- M0 方案定版：07-28～08-02；M1 工程与模型基线：08-03～08-09。
- M2 知识发布闭环：08-10～08-16；M3 关系核验闭环：08-14～08-23。
- M4 图拓扑与外部消费：08-10～08-26；M5 技术论证与交付：08-25～08-31。

## Synthesized Findings

### 产品范围
- Must：来源/证据、候选审核发布、对象关系、版本新鲜度、追溯影响、搜索、Context Pack、只读 REST、审计、Neo4j 投影与对照实验。
- Should/P1：PDF、AI 抽取、MCP、批量导入、高级图交互。
- Won't：多租户、自动投递、全网爬取、内部决策 Agent、通用 Ontology 编辑器。

### 技术与工程约束
- 领域核心不依赖 FastAPI、数据库驱动、Neo4j 或具体 LLM；通过端口/适配器隔离。
- 写入事务只提交 PostgreSQL 正式数据、审计和投影事件；Neo4j 失败不回滚正式知识。
- 关系是一等实体，关键关系必须有 Evidence 或上游依据；`derived_from`/`based_on` 无环。
- 配置必须环境化；部署目标为 Docker Compose；Web、API/Worker 共用后端镜像。

### 里程碑与依赖
- 关键路径：数据/关系字典 → Schema/领域约束 → 来源与候选发布 → 追溯与影响分析 → Context Pack/REST → 验收交付。
- 图实验路径：映射设计 → 投影事件/Worker → 校验与重建 → 四类查询 → 数据生成 → CTE/Cypher 基准 → 技术报告。
- 两条路径共享领域模型、样本数据、查询契约和测试基线，必须先锁定 M0 契约。
