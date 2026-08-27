# P4：Gel 接入与本地安装配置指南

> 目的：记录"Gel 与 PDF 导入打通"的接入设计与**本机安装配置步骤**，供当前设备完成验证，
> 也供另一台（无 Gel 环境、用 SQLite 开发的）设备复现与切换。

## 1. 当前已完成（本仓库）

- **Schema 已部署到本机 `my-gel` 的 `personlogy` 库**：
  - 迁移 `GEL/dbschema/migrations/00001-m1kj56k.edgeql`（TP-01 业务类型）与
    `00002-m15svfs.edgeql`（TP-05/06 治理与编译：GovernanceRun/Issue/DuplicateGroup/
    ConflictRecord/ReviewTask，Citation/Claim/Relation 的 metadata/status，
    VerificationStatus 扩展）均已生成并应用；
  - `seed.edgeql` 已执行（7 个关系类型）；
  - 已配置 `allow_user_specified_id := true`（领域对象 UUID 由 Python 生成，必须开启）。
- **Gel 适配器已实现**：`packages/personlogy_core/src/personlogy/adapters/gel.py`
  （GelStore / GelSourceRepository / GelKnowledgeRepository / GelGovernanceRepository /
  GelJobRepository / GelUnitOfWork(+Factory) / GelJobQueue，端口语义与 SQLite 适配器一致，
  含 get/save 与治理方法）。
- **装配已接线**：
  - `apps/api/app/runtime.py`：`PKS_STORAGE_BACKEND=gel` / `PKS_QUEUE_BACKEND=gel` 分支；
  - `apps/api/app/main.py`：关停时释放 Gel 客户端（`runtime.shutdown()`）；
  - `apps/api/app/api/routes/health.py`：gel 后端时做真实连通性检查；
  - `apps/worker/src/personlogy_worker/main.py`：支持 gel/sqlite 双后端，并处理
    `pdf.parse` → `knowledge.compile`（治理）链路；
  - `.env.example` 增加 `PKS_GEL_DSN` 示例。
- **集成测试已编写**：`apps/api/tests/test_gel_adapter.py`（设 `PKS_GEL_TEST_DSN` 才运行）。
- **端到端已验证**（真实 API + Worker + Gel）：上传 PDF → `pdf.parse` succeeded →
  ContentBlock 落 Gel → `knowledge.compile` succeeded → GovernanceRun（needs_review）+
  2 条 ReviewTask 落 Gel。
- **质量检查**：`pytest` 24 passed、`ruff`、`mypy` 全绿。

## 2. 前置要求

- Python 3.12（本机：`C:\Users\Zayn\AppData\Local\Programs\Python\Python312`）；
- 一个可达的 Gel 服务端。本机为 Docker 容器 `my-gel`（`geldata/gel`，端口 5656，
  insecure dev 模式，`gel://edgedb@localhost:5656/personlogy?tls_security=insecure`）。

## 3. 安装步骤（在仓库根目录执行）

```powershell
# 1) 创建虚拟环境（若已存在可跳过）
py -m venv .venv

# 2) 升级 pip
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# 3) 安装项目依赖（personlogy-core、api[dev]、worker，含 gel 驱动）
.\.venv\Scripts\pip.exe install -e packages/personlogy_core -e "apps/api[dev]" -e apps/worker
```

说明：

- `gel` Python 驱动（PyPI 包 `gel`，>=3.0）会随 `personlogy-core` 一起安装；
- **该包自带 `gel.exe` CLI**（装在 `.venv\Scripts`），因此不需要单独安装 Gel CLI。
  若希望全局使用，可把 `.venv\Scripts` 加入 PATH，或直接调用
  `.venv\Scripts\gel.exe`。

## 4. 配置（启用 Gel 后端）

在 `apps/api/.env`（或仓库根 `.env`，配置读取顺序为 `../../.env` 再 `.env`）写入：

```text
PKS_ENVIRONMENT=local
PKS_LOG_LEVEL=INFO
PKS_STORAGE_BACKEND=gel
PKS_QUEUE_BACKEND=gel
PKS_GEL_DSN=gel://edgedb@localhost:5656/personlogy?tls_security=insecure
PKS_PDF_STORAGE_ROOT=../../data/files
PKS_PDF_MAX_SIZE_BYTES=26214400
```

> 保持 SQLite 默认的机器（另一台开发设备）不需要这些，继续用
> `PKS_STORAGE_BACKEND=sqlite` 即可，代码同时支持两种后端。

## 5. 验证

### 5.1 回归测试（不依赖 Gel）

```powershell
cd apps\api
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check app tests ..\..\packages\personlogy_core\src
..\.venv\Scripts\python.exe -m mypy app ..\..\packages\personlogy_core\src\personlogy
```

（若 mypy 对 `gel` 模块报 missing stub，在 `apps/api/pyproject.toml` 增加
`[[tool.mypy.overrides]] module = ["gel", "gel.*"]` + `ignore_missing_imports = true`。）

### 5.2 Gel 集成测试（覆盖 PDF 导入 → Gel 落库 → 解析 → 版本复用 + 知识库 + 事务回滚）

```powershell
cd apps\api
$env:PKS_GEL_TEST_DSN = "gel://edgedb@localhost:5656/personlogy?tls_security=insecure"
..\.venv\Scripts\python.exe -m pytest tests\test_gel_adapter.py -v
```

### 5.3 端到端（可选：API + Worker 真实链路）

```powershell
# 终端 A：API
cd apps\api
$env:PKS_STORAGE_BACKEND="gel"; $env:PKS_QUEUE_BACKEND="gel"
$env:PKS_GEL_DSN="gel://edgedb@localhost:5656/personlogy?tls_security=insecure"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 终端 B：Worker
cd apps\api
..\.venv\Scripts\python.exe -m app.worker

# 终端 C：上传一个 PDF
curl.exe -X POST http://127.0.0.1:8000/v1/pdfs/upload `
  -F "project_name=演示项目" -F "project_slug=demo-gel" -F "title=演示文档" `
  -F "file=@C:\path\to\sample.pdf;type=application/pdf"

# 核对 Gel 数据
.\.venv\Scripts\gel.exe query "select Project { slug }; select Source { title }; select ContentBlock { content, locator }; select Job { kind, status };" --dsn $env:PKS_GEL_DSN --tls-security insecure
```

预期：上传返回 202 + `job_id`；Worker 日志出现 `content_blocks_written:N`；Gel 中
`Project/Source/SourceVersion/ContentBlock/Job` 均有记录，Job 状态 `succeeded`。

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| pip 卡在下载或报 `PermissionError: [Errno 13] ...pip-unpack-*` | 沙箱/杀软拦截了 mkdtemp 临时目录写入；普通开发机不会遇到。必要时把 `TEMP`/`TMP` 指向可写目录再装。 |
| 连接报 TLS handshake / InvalidIssuer | dev 实例为自签名证书，DSN 必须带 `?tls_security=insecure`（或 CLI 加 `--tls-security insecure`）。 |
| 插入报 `cannot assign to property 'id'` | 目标库未开启 `allow_user_specified_id`，执行 `configure current database set allow_user_specified_id := true;`。 |
| `type 'empty' does not exist` | Gel 7 中判断可选字段为空用 `exists`（`not exists .x`），不是 `is empty`。 |
| 迁移文件在哪 | Gel CLI 约定放在 `dbschema/migrations/`（不是 `GEL/migrations/`，旧占位目录已删除）。 |
| 本机没有 Gel 服务端 | 用 SQLite 继续开发：默认配置即可；Gel 集成测试会因未设 `PKS_GEL_TEST_DSN` 自动跳过。 |

## 7. 另一台设备（无 Gel）如何继续开发

- 无需任何 Gel 依赖：默认 `sqlite` 后端即可运行全部现有功能与测试；
- `gel` 驱动随依赖安装（不连库也能 import），代码在 `storage_backend != "gel"` 时不会
  创建 Gel 连接；
- 需要切到 Gel 时：按 `GEL/README.md` 初始化数据库（建库 → migration create →
  migrate → seed → 配置 `allow_user_specified_id`），再按第 4 节改配置即可；
- 本仓库的 `GEL/dbschema/migrations/`、`docs/engineering/gel-adapter.md`、
  `docs/plans/p4-gel-integration.md` 是切换依据。
