# Task Plan: TP-00、TP-01、TP-02 直接重构

## Goal

删除被新架构替代的旧实现，完成可启动的工程基础、核心领域模型与 Gel Schema、异步任务编排，并通过测试验证。

## Phases

- [x] Phase 1: 盘点现有代码、入口、依赖、测试和可删除目标
- [x] Phase 2: 落地 TP-00 工程基础
- [x] Phase 3: 落地 TP-01 领域模型与 Gel Schema
- [x] Phase 4: 落地 TP-02 任务状态机与编排端口
- [x] Phase 5: 删除被替代旧代码并修复引用
- [x] Phase 6: 运行静态检查、单元测试和启动验证
- [x] Phase 7: 输出重构报告

## Decisions

- 采用模块化单体，不迁移旧目录结构。
- Domain 不依赖 FastAPI、Gel、MinIO、LLM 或队列实现。
- Gel Schema 是权威数据模型；TP-01 交付 Schema 和 Repository/UoW 端口。
- TP-02 交付可测试的内存队列适配器；跨进程持久队列留给后续基础设施任务。
- 已被替代的 PostgreSQL、Neo4j、Alembic 和招聘领域实现直接删除。

## Verification

- `uv run ruff check app tests ../../packages/personlogy_core/src`：通过。
- `uv run mypy app ../../packages/personlogy_core/src/personlogy`：通过。
- `uv run pytest`：9 passed。
- Worker 启动探针打印 `worker_started` 并进入等待循环；主动超时结束。
- Gel CLI 可用，但本机未初始化 Gel project/server，未执行远端 Schema migration。
- Docker CLI 未安装，未执行 Compose 启动验证。

## Status

已完成 TP-00～TP-02。后续进入 TP-03 PDF 导入前，应先实现共享持久化队列和 Gel Repository adapter。
