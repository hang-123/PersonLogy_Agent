# Task Plan: P3 本地持久化数据链路

## Goal

在 GEL 暂不可用时，先用本地 SQLite 持久化打通可运行的任务链路，并通过适配器保留后续切换 GEL 的边界。

## Phases

- [x] Phase 1: 读取现有领域模型、端口、API 和测试
- [x] Phase 2: 实现本地持久化适配器与配置装配
- [x] Phase 3: 接入 API/Worker 并补充端到端测试
- [x] Phase 4: 运行静态检查、测试和启动验证
- [x] Phase 5: 更新说明与交付记录
- [x] Phase 6: 建立 Conversation/Message 领域模型与本地存储
- [x] Phase 7: 接入对话导入应用服务和 API
- [x] Phase 8: 补充幂等、冲突和接口测试
- [x] Phase 9: 更新说明并完成质量验证

## Decisions

- 本阶段使用 SQLite，不改变领域层，不引入 GEL 依赖。
- 原始任务和任务状态先持久化；现有领域实体继续通过 Repository/UoW 端口访问。
- 默认本地运行使用 `PKS_STORAGE_BACKEND=sqlite`；测试显式使用内存适配器。
- GEL 适配器暂不实现连接逻辑，后续只替换基础设施装配层。

## Errors Encountered

- 初次终端进程启动失败；改用授权的本地项目检查后恢复。
- 首次跨进程验证命令因 Python `-c` 不支持直接定义异步函数而失败；改用 `exec` 多行代码后通过。

## Status

**Currently complete** - 已完成本地持久化和对话导入闭环，测试、静态检查和交付说明均已完成。
