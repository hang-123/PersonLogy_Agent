# Gel 数据层

`dbschema/` 是唯一的业务 Schema 来源（`default.gel`、`extensions.gel`、`futures.gel`），
`dbschema/migrations/` 存放由 Gel CLI 生成的迁移文件，`seed.edgeql` 只负责初始化关系类型。
Schema 变更必须通过 Gel migration 生成、审阅和执行，不允许由普通导入任务自动建表或删表。

> 历史说明：早期占位的 `migrations/` 目录已删除，迁移统一按 Gel CLI 约定放在
> `dbschema/migrations/` 下。

## 数据库要求

- 目标数据库必须开启 `allow_user_specified_id`：领域模型在 Python 侧生成对象 UUID
  （object_key、Job payload 等都引用这些 ID），Gel 默认禁止显式指定 id：

  ```text
  configure current database set allow_user_specified_id := true;
  ```

- 连接使用 DSN 形式：`gel://user@host:port/database?tls_security=insecure`
  （本地 dev 实例为自签名证书，需要 `tls_security=insecure`）。

## 首次初始化（已执行，供其他设备复现）

在 Gel CLI 可用且服务端已运行的前提下，在 `GEL/` 目录执行：

```text
gel migration create --non-interactive --dsn <DSN>
gel migrate --dsn <DSN>
gel query -f seed.edgeql --dsn <DSN>
gel query "configure current database set allow_user_specified_id := true" --dsn <DSN>
```

其中 `<DSN>` 形如 `gel://edgedb@localhost:5656/personlogy?tls_security=insecure`。
执行顺序：先建库（`gel database create personlogy` 或 `gel branch create`），再生成/应用迁移，
再 seed，最后配置 `allow_user_specified_id`。

### 推荐：用 `scripts/gel-migrate.ps1` 一键执行（Windows）

在仓库根目录运行（自动应用现有迁移、可选生成新迁移与 seed、校验配置）：

```powershell
$env:GEL_PASSWORD = "<实例密码>"            # 或 -Password 参数
.\GEL\scripts\gel-migrate.ps1                # 仅应用现有迁移
.\GEL\scripts\gel-migrate.ps1 -Create        # 应用 + 基于 dbschema 差异生成新迁移
.\GEL\scripts\gel-migrate.ps1 -Create -Seed  # 应用 + 生成 + 执行 seed
```

- 迁移文件**必须由 CLI 生成**；手写迁移名无法被 CLI 解析（见"已知坑"）。
- `-Create` 在无 schema 差异时输出 "no schema changes" 并正常退出（CLI exit 4 已处理）。
- 本机开发实例：容器 my-gel（`F:\middleware\docker-compose.yml`），DSN
  `gel://edgedb:<密码>@localhost:5656/personlogy?tls_security=insecure`。

### 本机 Docker 实例（my-gel）说明

开发机没有独立安装 Gel CLI 时，可直接使用容器内自带 CLI（需先把 `GEL/` 拷入容器，
生成的文件再拷回仓库提交）：

```text
docker cp GEL\. my-gel:/tmp/gel-project/
docker exec -w /tmp/gel-project my-gel gel migration create --non-interactive --dsn <DSN> --tls-security insecure
docker exec -w /tmp/gel-project my-gel gel migrate --dsn <DSN> --tls-security insecure
docker exec my-gel gel query -f seed.edgeql --dsn <DSN> --tls-security insecure
docker cp my-gel:/tmp/gel-project/dbschema/migrations\. GEL\dbschema\migrations\
```

### 已知坑

- `gel migration create` 默认**交互式**提问；自动化必须加 `--non-interactive`（或 `--expert`）。
- 给**已有数据**的类型增加 `required` 字段（如 00002 给 Citation/Claim 加 `metadata`）会报
  `MissingRequiredError`。开发库可先清数据再迁移；有数据的库需先兜底默认值或分步迁移。
- 手写迁移文件的迁移名必须是 Gel CLI 可解析的格式（`m` + base32，与 `00001`/`00002` 一致）；
  早前手写的 `00003-p10f-audit.edgeql`（迁移名 `p10f_audit`）CLI 无法解析，已由 CLI 生成的
  `00003-m1idqkc.edgeql` 取代。

## 迁移状态

- `dbschema/migrations/00001-m1kj56k.edgeql`：TP-01 领域模型初版（Project、Source、
  SourceVersion、ContentBlock、KnowledgeNode、Claim、Relation、RelationType、Citation、
  Job、ReviewRecord）。
- `dbschema/migrations/00002-m15svfs.edgeql`：TP-05/TP-06 治理与编译（GovernanceRun、
  GovernanceIssue、DuplicateGroup、ConflictRecord、ReviewTask；Citation/Claim/Relation 增加
  `metadata`/`status`；VerificationStatus 扩展为 7 值）。
- `dbschema/migrations/00003-m1idqkc.edgeql`：P10-F 审计（AuditEvent + AuditChainHead 哈希链）。
- `dbschema/migrations/00004-m1srqqu.edgeql`：P7 受控回写 + P4 对话导入（WritebackStatus 枚举、
  WritebackRecord、WritebackItem、Conversation、ConversationMessage）。
- 全部迁移（00001–00004）已应用到本地 `personlogy` 库（2026-08-31 真实实例验证）。

## 运行时接入

- API/Worker 通过 `PKS_GEL_DSN` 连接，`PKS_STORAGE_BACKEND=gel`、`PKS_QUEUE_BACKEND=gel`
  启用 Gel 后端（见 `docs/engineering/gel-adapter.md` 与 `.env.example`）。
- 业务适配器实现位于 `packages/personlogy_core/src/personlogy/adapters/gel.py`，P10 审计适配器位于
  `packages/personlogy_core/src/personlogy/adapters/gel_audit.py`；应用新迁移后才可启用 Gel 审计。

## 查看数据 / 打开 Gel UI

Gel 自带官方浏览器工具 **Gel UI**（schema 图形视图 + 数据表格浏览 + 查询 REPL）。
开发实例默认启用；设了 `GEL_SERVER_PASSWORD` 的实例属生产模式，需在服务器开启 UI：

- 用 `compose.yaml` 启动时已配好（gel 服务含 `GEL_SERVER_ADMIN_UI: enabled`）；
- 手动 `docker run` 的实例需自己加环境变量 `GEL_SERVER_ADMIN_UI=enabled` 后重启容器。
  （Docker 镜像的环境变量带 `GEL_SERVER_` 前缀；官方文档省略前缀写作 `SERVER_ADMIN_UI`，
  直接照文档写会不生效。）

UI 启用后，任选一种方式打开（DSN 形如
`gel://edgedb@localhost:5656/personlogy?tls_security=insecure`）：

```text
# 方式一：本机已装 Gel CLI（PowerShell 安装：irm https://www.geldata.com/ps1 | iex）
gel ui --dsn <DSN>

# 方式二：没有本机 CLI，用容器内 CLI 打印 URL，再贴到宿主机浏览器
docker exec my-gel gel ui --print-url --dsn <DSN> --tls-security insecure

# 方式三：npx 免安装（临时拉取 CLI）
npx gel ui --dsn <DSN>
```

不装 UI 时的替代查看方式：

```text
# 命令行交互 REPL
gel --dsn <DSN>

# 一次性查询
gel query --dsn <DSN> "select Project { name, slug } limit 5"

# Python 驱动（项目 .venv 已带 gel 驱动，无需安装）
.venv\Scripts\python.exe -c "import asyncio,gel; c=gel.create_async_client(dsn='<DSN>'); print(asyncio.run(c.query('select Project { name } limit 5'))); asyncio.run(c.aclose())"
```

> 备注：Gel 没有 JDBC/ODBC 驱动，DBeaver/TablePlus/DataGrip 等通用 GUI 客户端基本
> 不支持；查看/操作请使用 Gel UI 或上述命令行方式。
