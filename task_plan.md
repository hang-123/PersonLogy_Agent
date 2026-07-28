# Task Plan: 个人知识关系系统规划与工程初始化

## Goal
基于 PRD 与 P0 开发计划，形成可执行的开发规划，并初始化一个可运行、可测试、可持续扩展的项目工程。

## Phases
- [x] Phase 1: 盘点输入文件与仓库状态，建立工作记录
- [x] Phase 2: 提取 PRD 与开发计划中的需求、范围、里程碑和约束
- [x] Phase 3: 输出工程化开发规划与关键技术决策
- [x] Phase 4: 初始化项目结构、配置与最小可运行骨架
- [x] Phase 5: 执行安装/构建/测试验证并完成交付

## Key Questions
1. P0 的产品边界、核心用户流程和验收标准是什么？
2. PRD 是否指定了技术栈、数据模型、AI 能力和部署约束？
3. 开发计划中的优先级与依赖关系如何映射到工程模块？
4. 当前环境能否直接完成依赖安装与运行验证？

## Decisions Made
- 以 PRD 为产品事实来源，以 P0 开发计划表为范围与排期事实来源。
- 初始化内容以“最小可运行 + 便于后续迭代”为目标，不提前实现未要求的完整业务功能。
- 采用 `apps/web + apps/api + packages/contracts + infra` 的单仓结构，后端保持模块化单体。
- PostgreSQL 是唯一权威写入源；Neo4j 仅作为可关闭、可重建的异步查询投影。
- 第一阶段只初始化健康检查、配置、测试入口和领域模块边界，不提前实现 P0 业务表。
- 工程默认使用 Python 3.12、FastAPI、SQLAlchemy、Alembic、React、TypeScript、Vite、Ant Design、React Flow。

## Errors Encountered
- 当前目录不是 Git 仓库：已在工程初始化阶段执行 `git init`。
- Initial environment lacked Python/Node/Docker; uv later installed isolated Python 3.12 and backend verification passed. Node and Docker remain unavailable, so frontend build and Compose startup require those runtimes.
- 工作区依赖加载器未暴露：开发计划表以只读 OOXML 方式解析，未修改原工作簿。
- 内置 `apply_patch` 连续触发 Windows 沙箱刷新错误，沙箱外同程序也被拒绝；改用 `git apply` 继续补丁式编辑。

## Status
**Completed** - Planning, initialization, dependency locking, and automated backend verification are complete.
