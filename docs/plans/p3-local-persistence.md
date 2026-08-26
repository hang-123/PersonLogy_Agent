# P3 本地持久化落地说明

## 目标

在 GEL 暂不可用期间，先打通可运行、可重复验证的数据任务链路。GEL 只保留为后续可替换的基础设施适配器，不进入当前运行时关键路径。

## 当前链路

```text
API 提交任务
  → SQLite job 表持久化
  → SQLite 队列视图发现 queued/retrying 任务
  → 独立 Worker 领取任务
  → 更新 running/progress/succeeded/failed 状态
```

当前 SQLite 适配器同时覆盖 Source、Knowledge 和 Job 的 Repository/UoW 端口，为后续导入、知识抽取和索引任务提供本地存储基础。

## 运行配置

```text
PKS_STORAGE_BACKEND=sqlite
PKS_SQLITE_PATH=../../data/personlogy.sqlite3
PKS_QUEUE_BACKEND=sqlite
```

API 与 Worker 必须指向同一个 SQLite 文件。Compose 环境默认将 `./data` 挂载到两个容器的 `/workspace/data`。

## 本地验证

在 `apps/api` 目录执行：

```text
uv run pytest
uv run ruff check app tests ../../packages/personlogy_core/src
uv run mypy app ../../packages/personlogy_core/src/personlogy
```

## GEL 接入边界

后续 GEL 恢复后，只需要新增/替换 GEL Repository、UoW 和 Queue 装配，不修改领域模型、JobService 或 API 契约。SQLite 数据也可以作为本地样例和迁移联调数据源。

## 下一步

1. 增加统一导入事件与原始资料 Repository。
2. 将 PDF/对话解析结果写入 Source、SourceVersion、ContentBlock。
3. 增加知识抽取任务处理器，并保留来源与 Citation 追溯。
4. 在本地 SQLite 链路稳定后，再接入向量索引和 GEL 适配器。
