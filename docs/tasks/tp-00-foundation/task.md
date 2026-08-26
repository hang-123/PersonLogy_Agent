# TP-00 工程基础

## 目标

建立新的模块化单体入口、配置、错误、日志和测试基线。

## 负责范围

- API 和 Worker 启动入口；
- 配置加载和环境区分；
- 统一错误模型；
- 结构化日志和请求 ID；
- 基础测试运行方式。

## 不负责

- 具体业务对象；
- Gel Schema；
- PDF 或 LLM 处理。

## 交付物

- `apps/api` 可启动；
- `apps/worker` 可启动；
- `packages/personlogy_core` 可导入；
- 配置、日志和错误模块；
- 最小健康检查。

## 验收

- Given 空环境配置
- When 启动 API
- Then 系统返回健康状态并明确报告缺失的外部依赖

- Given Worker 配置完整
- When 启动 Worker
- Then Worker 可以连接任务队列并等待任务

