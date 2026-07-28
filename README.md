# 个人知识关系系统

面向求职知识域的个人知识关系系统 P0。项目以对象、语义关系、证据来源和推导链为核心，帮助用户管理岗位资料、个人经历与判断依据，并从 Claim 或 Decision 反向追溯至原始 Evidence 和 SourceDocument。

> 当前状态：工程基线已完成，业务模型和完整接口将按照 [P0 开发规划](./DEVELOPMENT_PLAN.md) 逐步实现。

## 1. 系统概要

系统主要解决以下问题：

- 岗位要求、个人能力与证明材料之间缺少稳定关联；
- AI 分析、第三方评价和客观事实容易混淆；
- 投递判断形成后，难以追溯当时使用的来源和证据；
- JD 或上游知识变化后，既有 Claim 和 Decision 难以及时复核；
- 外部 AI 缺少结构清晰、范围可控、可验证的上下文。

P0 同时承担两个目标：

1. **产品闭环**：跑通“来源 → Evidence → Candidate → 人工审核 → Published → Claim → Decision → 反向追溯”。
2. **技术论证**：验证 PostgreSQL 递归查询与 Neo4j 图查询在证据链、影响分析、关系拓扑和 Context Pack 场景中的适用性。

| 层级 | 技术 |
|---|---|
| Web 管理端 | React 19、TypeScript、Vite、Ant Design、React Flow |
| API / Worker | Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 权威数据库 | PostgreSQL 17、`pg_trgm` |
| 图查询投影 | Neo4j Community 2026.06 |
| 工程与部署 | uv、npm、Docker Compose、GitHub Actions |

## 2. 系统精简架构图

```mermaid
flowchart LR
    User["用户"] --> Web["React Web 管理端"]
    Client["外部 AI / 脚本"] --> API["FastAPI REST / OpenAPI"]
    Web --> API
    API --> App["应用命令与查询服务"]
    Worker["单后台 Worker"] --> App
    App --> Domain["Ontology 领域核心"]
    Domain --> PG[("PostgreSQL 17\n唯一权威数据源")]
    App --> Files[("本地原始文件")]
    PG --> Events["processing_job / graph_projection_event"]
    Events --> Worker
    Worker --> Neo4j[("Neo4j\n可重建图投影")]
    Neo4j --> App
    LLM["LLM Provider Adapter\n规划中"] -. "只生成 Candidate" .-> App
```

核心边界：

- PostgreSQL 是正式知识的唯一权威来源。
- Neo4j 只保存 Published 知识的异步查询投影，不允许独立业务写入。
- LLM 只能生成 Candidate，不得绕过人工审核发布正式知识。
- Neo4j 不可用时，正式知识写入和 PostgreSQL 基础查询仍可运行。

## 3. 项目代码结构

```text
PersonLogy_Agent/
├─ apps/
│  ├─ api/                         # FastAPI 模块化单体与 Worker
│  │  ├─ app/
│  │  │  ├─ api/                   # REST 路由
│  │  │  ├─ application/           # 应用命令、查询与端口
│  │  │  ├─ core/                  # 配置、日志
│  │  │  ├─ domain/                # 领域模型和规则
│  │  │  ├─ infrastructure/        # 数据库、图、文件适配器
│  │  │  └─ modules/               # ingestion、review、query 等模块
│  │  ├─ migrations/               # Alembic 迁移
│  │  ├─ tests/                    # 后端测试
│  │  ├─ pyproject.toml
│  │  └─ uv.lock
│  └─ web/                         # React 管理端
│     ├─ src/
│     ├─ package.json
│     └─ vite.config.ts
├─ packages/contracts/             # OpenAPI / Context Pack 契约
├─ infra/
│  ├─ postgres/                    # PostgreSQL 初始化
│  └─ neo4j/                       # Neo4j 约束与 Mapping
├─ docs/
│  ├─ architecture/                # ADR、Ontology、关系字典
│  └─ experiments/                 # Topology 实验方案
├─ data/                            # 本地数据，不提交敏感资料
├─ compose.yaml
├─ .env.example
├─ DEVELOPMENT_PLAN.md
└─ README.md
```

## 4. 快速开始

推荐使用 Docker Compose 启动完整环境。仅开发单个模块时，也可以分别启动后端和前端。

### 4.1 环境要求

#### Docker Compose 模式（推荐）

- Git
- Docker Desktop 或 Docker Engine
- Docker Compose v2.24+
- 至少 8 GB 可用内存
- Chrome 或 Edge 最新两个主要版本

Docker 会准备 Python、Node.js、PostgreSQL 和 Neo4j 环境。

#### 本地开发模式

- Python `3.12.x`
- uv `0.11+`
- Node.js `22.13+`
- npm
- PostgreSQL `17`
- Neo4j Community `2026.06`

> Vite 8 要求 Node.js 20.19+ 或 22.12+；本项目统一建议 Node.js 22.13 及以上版本。

### 4.2 创建环境

克隆并进入项目：

```bash
git clone <repository-url>
cd PersonLogy_Agent
```

复制配置模板：

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

修改 `.env` 中的数据库和 Neo4j 密码。不要提交真实密码、Token 或 API Key。

凭据在基础设施配置和应用连接配置中各出现一次，必须同步修改：

- `POSTGRES_PASSWORD` 与 `PKS_DATABASE_URL` 中的密码保持一致；
- `NEO4J_AUTH` 中的密码与 `PKS_NEO4J_PASSWORD` 保持一致。

创建后端虚拟环境：

```bash
cd apps/api
uv sync --extra dev --locked
```

### 4.3 依赖包安装指令

Docker 模式不需要在宿主机单独安装依赖：

```bash
docker compose build
```

后端开发依赖：

```bash
cd apps/api
uv sync --extra dev --locked
```

后端仅安装生产依赖：

```bash
uv sync --locked
```

前端依赖：

```bash
cd apps/web
npm install
```

首次安装生成 `package-lock.json` 后，CI 和其他开发者应使用：

```bash
npm ci
```

### 4.4 安装说明

- `uv.lock` 已纳入工程，用于锁定本地 uv 安装与后端验证依赖；当前 API Dockerfile 仍使用 `pip install .`，尚未消费该锁文件。
- 前端尚未生成 `package-lock.json`，首次成功执行 `npm install` 后应提交该文件。
- Docker 使用 `apps/api/Dockerfile` 和 `apps/web/Dockerfile` 构建应用镜像。
- PostgreSQL 首次创建数据卷时会启用 `pg_trgm`。
- Neo4j 约束脚本位于 `infra/neo4j/constraints.cypher`，当前 Mapping 仍待 M0 评审。
- `.venv`、`node_modules`、数据库卷、本地原始材料和 `.env` 不提交到 Git。

### 4.5 启动说明

启动完整 Docker 环境：

```bash
docker compose up --build
```

后台启动、查看状态和日志：

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f api worker web
```

停止服务：

```bash
docker compose down
```

> `docker compose down -v` 会删除 PostgreSQL、Neo4j 等本地卷的数据，仅在明确不再需要数据时使用。

混合开发模式可只通过 Docker 启动数据库：

```bash
docker compose up -d postgres neo4j
```

然后把 `.env` 中的连接主机改为 `localhost`，再在宿主机启动 API、Worker 和 Web。PostgreSQL 的 `pg_trgm` 会在首次创建 Docker 数据卷时初始化。

本地启动 API：

```bash
cd apps/api
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

本地启动 Worker：

```bash
cd apps/api
uv run python -m app.worker
```

> 当前 Worker 只完成进程基线，`processing_job` 任务领取将在后续里程碑实现。

本地启动前端：

```bash
cd apps/web
npm run dev
```

本地分别启动服务时，应将数据库主机改为 `localhost`：

```dotenv
PKS_DATABASE_URL=postgresql+psycopg://knowledge:your-password@localhost:5432/knowledge
PKS_NEO4J_URI=bolt://localhost:7687
```

### 4.6 配置说明

配置模板为根目录 `.env.example`。后端通过 `PKS_` 前缀读取配置。

| 配置项 | 默认值或示例 | 说明 |
|---|---|---|
| `POSTGRES_DB` | `knowledge` | PostgreSQL 数据库名 |
| `POSTGRES_USER` | `knowledge` | PostgreSQL 用户名 |
| `POSTGRES_PASSWORD` | `local-only-change-me` | PostgreSQL 密码 |
| `NEO4J_AUTH` | `neo4j/local-only-change-me` | Neo4j 用户名和密码 |
| `PKS_ENVIRONMENT` | `local` | `local/test/staging/production` |
| `PKS_LOG_LEVEL` | `INFO` | 后端日志级别 |
| `PKS_DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL 连接地址 |
| `PKS_NEO4J_URI` | `bolt://neo4j:7687` | Neo4j Bolt 地址 |
| `PKS_NEO4J_USERNAME` | `neo4j` | Neo4j 用户名 |
| `PKS_NEO4J_PASSWORD` | `local-only-change-me` | Neo4j 密码 |
| `PKS_CORS_ORIGINS` | `["http://localhost:5173"]` | 允许访问 API 的来源，使用 JSON 数组 |
| `VITE_API_BASE_URL` | `http://localhost:8000/v1` | 前端 API 基础地址 |

生产环境必须更换默认密码、限制数据库端口、收紧 CORS，并避免在日志中记录密码、Token、API Key 或完整敏感原文。

### 4.7 大模型 API 配置

当前工程尚未实现 LLM Provider Adapter。以下变量是后续 AI 辅助抽取模块的建议约定，暂未接入 `Settings`；仅写入 `.env` 不会立即启用模型调用。

```dotenv
PKS_LLM_PROVIDER=openai-compatible
PKS_LLM_BASE_URL=https://api.example.com/v1
PKS_LLM_API_KEY=replace-with-your-api-key
PKS_LLM_MODEL=replace-with-model-name
PKS_LLM_TIMEOUT_SECONDS=60
PKS_LLM_MAX_RETRIES=2
```

接入大模型时必须遵守：

1. 模型输出只能进入 Candidate 区。
2. Candidate 必须人工审核后才能发布。
3. API Key 不得写入代码、日志、测试快照或 Git。
4. Provider 通过适配器接入，领域核心不得依赖具体厂商 SDK。
5. 请求内容需要执行敏感信息裁剪，默认不发送 Sensitive 原文。
6. 模型调用失败不得影响原始来源材料保存。

## 5. 服务入口

| 服务 | 地址 |
|---|---|
| Web 管理端 | <http://localhost:5173> |
| API 文档 | <http://localhost:8000/docs> |
| API 健康检查 | <http://localhost:8000/v1/health/live> |
| API 就绪检查（当前为占位，不检查数据库/Neo4j） | <http://localhost:8000/v1/health/ready> |
| Neo4j Browser | <http://localhost:7474> |
| PostgreSQL | `localhost:5432` |
| Neo4j Bolt | `localhost:7687` |

## 6. 开发检查

后端：

```bash
cd apps/api
uv run ruff check app tests migrations
uv run mypy app
uv run pytest --cov=app --cov-report=term-missing
uv lock --check
```

前端：

```bash
cd apps/web
npm run typecheck
npm run build
```

## 7. 关键架构约束

- 外部 AI 不得直接新增、修改或删除 Published 知识。
- 发布事务必须同时保存正式知识、审计记录和图投影事件。
- Candidate、Archived 和无权限内容默认不进入只读 API 与 Context Pack。
- `derived_from` 与 `based_on` 依赖链必须无环。
- 关系、Claim 和 Decision 使用状态变更与追加版本，不执行无审计物理删除。
- 图投影失败时应显示滞后或降级状态，不回滚 PostgreSQL 正式知识。
- P0 不引入 Redis、消息队列、微服务、Kubernetes 或独立向量数据库。

## 8. 当前开发状态

已经完成：

- Git 与单仓工程结构；
- FastAPI、配置、日志、健康检查和测试入口；
- React、TypeScript、Vite 和 Ant Design 前端骨架；
- Docker Compose、PostgreSQL 扩展和 Neo4j 约束基线；
- Python 依赖锁、CI、Context Pack Schema 和架构文档；
- 后端 Ruff、Mypy、Pytest 与静态配置验证。

后续优先事项：

1. 冻结 Ontology 数据字典和关系字典；
2. 建立 PostgreSQL 核心 Schema 与首个 Alembic 迁移；
3. 实现来源、Evidence、Candidate、审核和发布事务；
4. 实现 Claim、Decision、反向追溯和影响分析；
5. 实现 Neo4j 投影、校验、重建与 Topology 对照实验；
6. 实现 Context Pack、只读 REST 和可插拔 LLM Provider Adapter。

更多信息：

- [P0 开发规划](./DEVELOPMENT_PLAN.md)
- [架构决策 ADR-0001](./docs/architecture/ADR-0001-modular-monolith-and-graph-projection.md)
- [Ontology 数据字典](./docs/architecture/ontology-dictionary.md)
- [关系字典](./docs/architecture/relation-dictionary.md)
- [Topology 对照实验计划](./docs/experiments/topology-benchmark-plan.md)

