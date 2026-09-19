# PersonLogy Agent

PersonLogy Agent 是一个面向个人项目和长期主题的知识系统，目标是把 PDF 文档、大模型对话等分散资料整理为结构清晰、关系可追溯、可检索、可多端访问的个人知识库。

## 项目目标

```text
资料导入 → 内容解析 → LLMWiki 知识编译 → 数据治理
→ Gel 结构化回写 → 全文/向量/关系索引 → 带证据检索
```

第一版聚焦 PDF 上传和大模型对话导入，暂不处理本地文件夹同步、飞书自动同步、多人协作和复杂图算法。

## v0.1 技术栈

| 类别 | 选择 | 用途 |
|---|---|---|
| API | Python API（当前工程沿用） | 文件、对话、知识和检索接口 |
| 异步任务 | Worker + Queue | PDF 解析、LLM 编译、治理和索引 |
| 结构化数据库 | Gel | 业务对象、知识节点、关系、证据和权限 |
| 查询语言 | Gel Schema / EdgeQL | Schema、Migration 和结构化查询 |
| 原始存储 | MinIO / S3 兼容对象存储 | PDF、对话原文和版本文件 |
| 知识格式 | OKF v0.2 + PersonLogy 扩展 | 可读、可迁移的知识表达 |
| 模型能力 | LLM / Embedding / Reranker Provider | 编译、向量化、重排和问答 |
| 检索 | 全文 + 向量 + 关系混合检索 | 召回知识、关系和证据 |
| 前端 | Web UI | 上传、审核、浏览、关系图和问答 |

具体模型供应商、队列实现和前端框架通过 Adapter/Port 隔离，避免绑定单一供应商。

## 整体架构

```text
接入层：反向代理、API 网关、认证、限流、审计
    ↓
应用层：导入、任务编排、知识编译、治理、Schema 管理、回写、索引、检索
    ↓
领域层：Source、Claim、Relation、Citation、权限和生命周期
    ↓
基建层：Gel、MinIO、LLM、Embedding、Queue、Worker、可观测性
```

Schema 管理和日常数据导入是两条受控路径：

```text
Schema：LLM 生成 Gel Migration → 校验/审批 → Migration Tool 执行
数据：LLM 生成知识对象 → 治理 → 受控 Tool → Gel 事务写入
```

## 文档入口

- [功能 Spec](docs/features/README.md)
- [初版总 Spec](docs/spec/personlogy-v0.1-spec.md)
- [系统架构书](docs/architecture/personlogy-architecture.md)
- [代码目录与重构约定](docs/engineering/code-structure.md)
- [项目开发计划](docs/plans/development-plan.md)
- [系统图稿](docs/architecture/diagrams.md)
- [LLM / Embedding / Rerank 接入指南](docs/engineering/llm-integration.md)

## 开发约定

- 功能验收标准统一写在 `docs/features/<feature>/spec.md`；
- 验收标准统一使用 Given/When/Then；
- 领域层不得直接依赖 Gel、MinIO、LLM 或 Web 框架；
- API/Worker 通过 Application 调用 Domain 和 Ports；
- 原始资料不可变，索引必须可重建；
- Schema Migration、知识写入和索引构建分别审计。

## 本地启动（一键脚本）

Windows / PowerShell（在仓库根目录）：

```powershell
.\start.ps1              # 启动全部服务（API + Worker + Web，后台运行）
.\start.ps1 -Service api # 只启动某个服务
.\start.ps1 -Status      # 查看服务状态
.\start.ps1 -Stop        # 停止全部
.\start.ps1 -Foreground  # 前台运行（调试用）
```

- 服务日志写入 `.logs\`（api.log / worker.log / web.log）
- 启动前需：`.venv` 已装依赖、`apps/web` 已 `npm install`、可选复制 `.env.example` 为 `.env`
- 访问：API 文档 `http://127.0.0.1:8000/docs`，前端 `http://localhost:5173`
- Docker 部署见 `compose.yaml`

## 系统优化与开发环境验收（2026-09-06）

API 和两个 Worker 入口共用 `personlogy.runtime`：相同的配置、模型、审计、血缘和任务处理。
`personlogy_worker.main` 与 `app.worker` 均保留为兼容入口；Compose 的 API/Worker 均加载 `.env`。

- 任务重试时进度归零。每次执行受 `timeout_seconds` 限制，Worker 每轮领取前恢复已超时的运行任务；API 启动时也执行恢复。恢复遵守重试次数与等待时间。
- LLM 引文须逐字来自内容块，记录 `quote_start` / `quote_end` 字符偏移（左闭右开）；关系拥有独立引用。启发式引用保留原始空白，不向引文添加省略号。
- 任务和审核列表支持 `project_id`，前端自动传递选中项目。此参数是数据筛选，不替代访问控制。
- `/v1/health/live` 与 `/v1/health/ready` 的 `dependencies` 包含 `retrieval` / `indexing` 能力；Gel 和内存后端的检索、问答及索引请求返回明确错误。
- Gel 迁移默认校验证书，密码通过标准输入传递；只有本机自签名开发环境才使用 `-AllowInsecureLocal`。首次集成测试应加 `-Seed` 初始化关系字典。

在 `apps/api` 下运行后端检查：

```powershell
../../.venv/Scripts/python.exe -m pytest tests
../../.venv/Scripts/python.exe -m ruff check app tests ../../packages/personlogy_core/src ../worker/src --config pyproject.toml
../../.venv/Scripts/python.exe -m mypy app ../../packages/personlogy_core/src ../worker/src
```

在项目根目录运行真实 API/Worker 全流程测试；每次使用独立 `.tmp` 数据目录，结束后停止测试进程：

```powershell
.venv/Scripts/python.exe tests/live_development_smoke.py                 # 启发式，无外部模型调用
.venv/Scripts/python.exe tests/live_development_smoke.py --external-llm  # 使用 .env 的模型配置
docker build -t personlogy-optimization-api -f apps/api/Dockerfile .
docker build -t personlogy-optimization-worker -f apps/worker/Dockerfile .
.venv/Scripts/python.exe tests/container_smoke.py
```

真实模型测试仅发送脚本生成的合成资料。脚本会初始化测试所需 Schema 快照；正常开发库需先登记目标 Schema 快照，审核和回写才可形成闭环。
完整结果、Gel 测试命令及范围说明见 [系统优化验收报告](docs/engineering/system-optimization-validation-2026-09-06.md)。

