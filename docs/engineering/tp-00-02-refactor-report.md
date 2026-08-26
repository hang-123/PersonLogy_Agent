# TP-00～TP-02 重构报告

## 交付结果

### TP-00 工程基础

- API 入口：`apps/api/app/main.py`
- 独立 Worker 入口：`apps/worker/src/personlogy_worker/main.py`
- 统一配置、结构化日志、请求 ID、错误响应和健康检查。
- `/v1/health/live` 报告进程存活；`/v1/health/ready` 在 Gel 未配置时报告 `degraded` 和依赖状态。

### TP-01 领域模型与 Gel Schema

- `Project`、`Source`、`SourceVersion`、`ContentBlock`、`KnowledgeNode`、`Claim`、`Citation`、`Relation`、`ReviewRecord`。
- Claim 和 Relation 强制至少关联 Citation；关系端点、置信度、版本号和哈希均有领域约束。
- `GEL/dbschema/default.gel` 定义枚举、继承基类、对象链接、唯一约束和任务对象。
- Repository、Unit of Work、Queue 均以 Protocol 形式定义，核心包不绑定基础设施。

### TP-02 任务编排

- Job 状态：`queued → running → retrying/succeeded/failed`，并支持 `cancelled`。
- 状态转换不可变、带进度、阶段、尝试次数、失败原因和下次重试时间。
- `JobService` 提供提交、幂等查询、领取、进度、成功、失败/重试和任务列表。
- API 提供 `POST/GET /v1/jobs`，使用 `X-Idempotency-Key` 防重复提交。

## 旧代码处理

直接删除了旧 SQLAlchemy/PostgreSQL/Neo4j/Alembic 实现、招聘领域对象、旧工作流测试和占位 Worker；没有做兼容迁移层。

## 验证

Ruff、mypy 和 9 个 pytest 均通过。Gel CLI 已安装但本机没有初始化项目实例；Docker CLI 不可用，因此 Compose 仅完成静态重写，未做容器启动测试。

## 边界说明

TP-02 当前使用内存队列适配器作为可测试基线。它不支持 API 与独立 Worker 跨进程共享任务；TP-03 前必须接入共享持久队列/基于 Gel 的任务 Repository，不能直接用于生产。
