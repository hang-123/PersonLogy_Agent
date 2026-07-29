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


## M0/M1 落地结果（2026-07-28）
- 新增可执行 Ontology：6 类知识对象、对象状态策略、认知类型、证据/候选/任务/投影等受控枚举。
- 新增 7 类正式对象关系及端点、证据门禁；提供通用依赖无环检测。
- 建立 15 张 PostgreSQL 权威存储表，覆盖正式知识、来源证据、候选审核、版本审计、后台任务和图投影。
- 首个 Alembic 迁移支持离线 SQL 审阅，启用 pg_trgm 并保留共享扩展的安全降级策略。
- 元数据契约测试验证表集合、关系外键、枚举存储值、JSONB 与投影幂等唯一约束。

## 来源—审核发布闭环设计结论（2026-07-28）
- AC-01/03 要求来源保留正文、URL、采集时间、指纹，Evidence 保留摘录、来源和定位。
- Candidate 创建时允许保留尚未规范化的原始 payload；只有人工接受时才按正式 Object/Relation Schema 严格校验。
- 关系发布必须验证起终点对象类型、Evidence 存在且有效，并为正式 Relation 建立 supports EvidenceLink。
- 接受命令在一个 PostgreSQL 事务内锁定 Candidate，并同时写正式聚合、版本快照、审计和图投影事件。
- Candidate 仅允许从 pending_review 进入 accepted/rejected，重复命令返回冲突，防止重复发布。
- 本增量先覆盖新建对象/关系与拒绝；关联已有对象及别名合并在后续审核增强中实现。

## 来源—审核发布闭环落地结果（2026-07-28）
- 新增 9 个 REST 命令/查询端点，覆盖来源、Evidence、Candidate 列表、接受与拒绝。
- 发布命令通过 FOR UPDATE 锁定 Candidate，并原子写正式聚合、EvidenceLink、ObjectVersion、AuditLog 与 GraphProjectionEvent。
- 新增 0002 迁移，对对象规范名、关系三元组和来源内容指纹增加唯一约束；开发库和 knowledge_test 均已升级到 20260728_0002。
- 真实 PostgreSQL 集成测试覆盖成功发布、缺 Evidence 阻断、非法端点阻断、重复审核冲突和失败事务保持 PendingReview。
- 最终验证：18 tests passed，覆盖率 87%，Ruff/Mypy/uv lock/Alembic offline SQL 全部通过。

## Candidate 合并与审核工作台设计结论（2026-07-28）
- 现有 Web 仅有健康检查展示且中文文本编码损坏，需要重构为真实工作台。
- 审核页必须同时提供 Candidate 列表、来源/Evidence 上下文、Payload 和审核动作，避免脱离证据确认。
- Object Candidate 合并目标必须与候选 object_type 一致；合并只追加 alias，不删除或重定向已有对象 ID。
- 合并事务追加 ObjectVersion、AuditLog 和 REVISE GraphProjectionEvent，并将 Candidate 标记 merged。
- 为支持审核匹配，新增正式对象搜索；为支持来源回看，新增来源列表。
- 视觉采用研究档案台方向，以暖纸色、墨色和朱砂色表达“证据先于结论”。

## Candidate 合并与审核工作台落地结果（2026-07-28）
- 新增正式对象搜索、来源列表和 Object Candidate merge 命令。
- 合并事务追加 aliases、对象版本、审计和 revise 投影事件，不创建重复正式对象。
- Web 从乱码占位页重构为来源录入和三栏候选审核工作台，API/Neo4j 状态边界清晰。
- 前端 package-lock 已生成；TypeScript 与 Vite build 通过，生产依赖审计 0 漏洞。
- 浏览器桌面/移动验收通过，无横向溢出，控制台 0 error/warning。
- 后端 18 tests passed，真实 PostgreSQL 集成测试包含 merge 与 alias 搜索，覆盖率 87%。
