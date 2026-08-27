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
gel migration create --dsn <DSN>
gel migrate --dsn <DSN>
gel query -f seed.edgeql --dsn <DSN>
gel query "configure current database set allow_user_specified_id := true" --dsn <DSN>
```

其中 `<DSN>` 形如 `gel://edgedb@localhost:5656/personlogy?tls_security=insecure`。
执行顺序：先建库（`gel database create personlogy` 或 `gel branch create`），再生成/应用迁移，
再 seed，最后配置 `allow_user_specified_id`。

### 本机 Docker 实例（my-gel）说明

开发机没有独立安装 Gel CLI 时，可直接使用容器内自带 CLI：

```text
docker exec my-gel gel migration create --dsn <DSN> --tls-security insecure
docker exec my-gel gel migrate --dsn <DSN> --tls-security insecure
docker exec my-gel gel query -f seed.edgeql --dsn <DSN> --tls-security insecure
```

注意：容器内 CLI 需要能读到 `dbschema/`。若容器未挂载项目目录，可先 `docker cp`
把 `GEL/` 拷入容器（如 `/tmp/gel-project`），执行完再把生成的 `dbschema/migrations/`
拷回仓库提交。

## 迁移状态

- `dbschema/migrations/00001-m1kj56k.edgeql`：TP-01 领域模型初版迁移（Project、Source、
  SourceVersion、ContentBlock、KnowledgeNode、Claim、Relation、RelationType、Citation、
  Job、ReviewRecord），已应用到本地 `personlogy` 库。

## 运行时接入

- API/Worker 通过 `PKS_GEL_DSN` 连接，`PKS_STORAGE_BACKEND=gel`、`PKS_QUEUE_BACKEND=gel`
  启用 Gel 后端（见 `docs/engineering/gel-adapter.md` 与 `.env.example`）。
- 适配器实现位于 `packages/personlogy_core/src/personlogy/adapters/gel.py`。
