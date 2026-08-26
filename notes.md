# Notes: TP-00～TP-02 重构

## Findings

旧 API 将 FastAPI、SQLAlchemy/PostgreSQL、Neo4j 投影和招聘领域对象直接耦合在 `apps/api/app` 中，无法作为个人知识系统的稳定核心。新实现将领域实体、状态机、端口和内存适配器放入 `packages/personlogy_core`，API 只负责 HTTP 装配。

## Deletion Log

删除了旧 API 领域/基础设施模块、旧测试、Alembic migrations、PostgreSQL 初始化脚本、Neo4j 约束及占位 Worker。删除前已检查引用，`apps`、`packages`、`GEL` 和 Compose 中无旧 SQLAlchemy/Neo4j/PostgreSQL 运行时代码残留。

## Known Follow-up

当前 API/Worker 的 TP-02 适配器是进程内内存实现，适合单元测试和本地骨架，不承担跨进程可靠投递。TP-03 之前需要增加基于 Gel 的 Job Repository/Queue adapter，或明确引入独立队列服务；不能把内存队列用于生产部署。
