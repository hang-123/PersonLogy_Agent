# Task Plan: P7 受控回写功能实施

## Goal
在现有 P0-P10 基础上落地 P7 首版受控发布事务：实现领域契约、SQLite/Gel 回写记录、幂等与事务闸门、API/Worker、OKF/索引副作用、审计血缘和测试验证。

## Phases
- [x] Phase 1: 规划与实施边界冻结
- [x] Phase 2: 领域契约与回写持久化（Gel migration 生成待环境补齐）
- [x] Phase 3: 应用服务、API 与 Worker 链路
- [x] Phase 4: OKF、索引、审计与血缘接入
- [x] Phase 5: 测试、验证与交付

## Key Questions
1. 如何在不重复插入 P5 候选的前提下表达 P7 正式发布？
2. 如何在 SQLite/Gel 两个适配器中保持回写记录、幂等和条件状态更新一致？
3. 如何保证主数据事务与 OKF/索引等外部副作用可恢复？
4. 当前缺失完整 RBAC/MinIO 时，如何实现安全的本地/测试降级并避免误称生产就绪？

## Decisions Made
- 先以仓库现状和已有术语为准，不在缺乏证据时臆造 P7 业务含义。
- 首版采用“同表候选 + 受控发布状态 + WritebackRecord”，不重复插入已有候选；staging/formal 分表作为后续演进。
- 当前缺少完整项目级授权时，P7 先实现可注入的授权端口；生产装配无授权策略则 fail-closed。
- 先完成 SQLite 可验证闭环，再用 Gel 适配器和真实实例做契约/集成验证；不把 LocalFileStorage 宣称为跨系统事务。

## Errors Encountered
- 系统 Python 未安装 pytest/ruff，已改用 `apps/api/.venv` 完成验证。
- 一次从 `apps/api` 目录执行 Worker 路径检查时使用了错误相对路径，已修正为仓库根目录执行。
- 本机 Docker 不可用；Gel CLI 首次启动尝试下载 CLI 时因 SSL `UNEXPECTED_EOF` 失败，因此未生成手写迁移文件。

## Status
**Implementation complete with one environment gate** - SQLite/API/Worker/OKF/索引/审计/血缘闭环已落地并通过测试；Gel schema source 已更新，但必须在可用 Gel CLI/实例环境中生成并执行正式 migration 后才能启用 Gel 运行时。
