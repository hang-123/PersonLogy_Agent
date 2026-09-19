# 系统优化实施与真实开发环境验收

日期：2026-09-06。依据：`docs/superpowers/plans/2026-09-06-system-optimization.md`。

## 实施结果

四个任务已完成。实现保留模块化单体边界，领域层不引入 FastAPI、Gel 或 HTTP 客户端。

1. **模型与编译契约**：模型 JSON 错误统一为领域校验错误；LLM 引文按原文逐字匹配并记录字符偏移，关系独立生成引用；OKF v0.2 包含节点、断言、关系和引用标识。编译服务独立校验引用与偏移，启发式引文保留原始空白，截断不添加省略号。
2. **任务可靠性与项目范围**：重试归零进度；基于开始时间与执行期限识别超时；API 启动、Worker 轮询持续恢复；Worker 使用每次执行期限。任务过滤下沉至 SQLite / Gel / 内存仓库，在 LIMIT 前执行；审核列表按治理运行关联项目，前端传递当前项目。
3. **共享运行时与部署**：配置、服务组装、日志、审计、血缘和任务执行集中至 `personlogy.runtime`。两个 Worker 入口保留兼容。Core 声明实际运行依赖；Compose 两个后端服务都读取环境文件；CI 安装本地包，移除旧 Alembic/PostgreSQL 步骤，加入真实进程与生产容器 smoke。
4. **能力与验证**：健康接口公开检索/索引能力。Gel 和内存后端的检索、问答、索引请求明确报错。迁移默认验证 TLS，密码通过标准输入传递。临时目录和容器构建上下文忽略生成物及 `.env`。

真实联调额外发现：启用审计的受控回写会因 `governance_run_id`、`schema_namespace`、`index_job_id` 不在审计允许清单中失败。已补齐合法字段，并将真实 SQLite 审计存储加入回写回归测试。

## 验收证据

| 验证 | 环境与覆盖 | 结果 |
| --- | --- | --- |
| 完整后端测试 | Python 3.12.10；包含真实 Gel 的 10 个测试 | **91 passed，0 skipped**；运行时报告 1 个 warning |
| Ruff | API、测试、Core、独立 Worker | 通过 |
| mypy | 141 个源文件 | 通过 |
| Web | TypeScript 类型检查与 Vite 生产构建 | 通过；现有主 bundle 大于 500 kB 提示仍存在 |
| Gel 初始化 | 独立 Docker 实例，本机端口 15656 | 00001–00004 迁移、7 个关系类型 seed、用户指定 UUID 配置通过 |
| Gel 集成 | 来源、知识、治理、任务、回写、对话；新增项目过滤与过期恢复 | 全部通过 |
| Gel API | 真实 Uvicorn 进程连接真实 Gel | readiness 为 ok；search/index 返回明确不支持错误 |
| TLS 默认行为 | 对隔离实例不传 insecure 选项 | 按预期拒绝未受信任自签名证书；显式开发选项可连接 |
| 外部模型全链路 | 真实 API + 独立 Worker + SQLite + `.env` 中 DeepSeek 配置 | PDF → 解析 → 模型编译 → 审核 → 回写 → 索引 → 带证据检索通过 |
| 启发式全链路 | 相同真实进程与 SQLite，禁用外部模型 | 通过 |
| 崩溃恢复 | 预置已过期 running 任务，由真实 Worker 恢复并领取 | 第 2 次执行成功 |
| 执行期限 | SQLite 任务 + 可取消慢解析器 + 共享 Worker 循环 | 1 秒期限结束任务，错误被持久化 |
| 生产容器 | Dockerfile 从纯 Python 镜像安装生产依赖；API/Worker 共享独立数据卷 | 健康检查、HTTP 提交、Worker 消费、API 查询成功 |

外部模型成功样本：

- 模型：`deepseek-v4-flash`。
- 编译任务：`00d9ab11-badd-4038-9150-276abd6101da`。
- 2 条知识断言、2 条带证据检索命中、41 条审计事件、52 条血缘链接。
- 报告：`.tmp/live-smoke-9ef5434bba/report.json`。
- 启发式报告：`.tmp/live-smoke-653e126e34/report.json`。
- 全量测试 JUnit：`.tmp/optimization-final-junit.xml`。
- 最终容器 smoke 任务：`4aa2c3ef-0182-4274-8939-6556a38e3206`。

`.tmp` 中保留测试数据库、输出和日志，便于本机复核；它们不会进入版本库。只向模型发送脚本生成的合成文本，没有修改 `.env` 或使用已有业务资料。

## 复现

后端（工作目录 `apps/api`）：

```powershell
$env:PKS_GEL_TEST_DSN = 'gel://edgedb@localhost:15656/main?tls_security=insecure'
../../.venv/Scripts/python.exe -m pytest tests -p no:cacheprovider --basetemp=../../.tmp/recheck
../../.venv/Scripts/python.exe -m ruff check app tests ../../packages/personlogy_core/src ../worker/src --config pyproject.toml
../../.venv/Scripts/python.exe -m mypy app ../../packages/personlogy_core/src ../worker/src
```

未设置 `PKS_GEL_TEST_DSN` 时会跳过真实 Gel 测试；本次验收设置了该变量。

初始化专用 Gel 测试实例（工作目录：项目根目录；容器名已存在时先使用该实例，不重复创建）：

```powershell
docker run --detach --name personlogy-optimization-gel --publish 127.0.0.1:15656:5656 --env GEL_SERVER_SECURITY=insecure_dev_mode geldata/gel
./GEL/scripts/gel-migrate.ps1 -Dsn 'gel://edgedb@localhost:15656/main' -AllowInsecureLocal -Seed
```

该安全例外仅用于绑定本机的隔离测试实例。正式环境应配置受信任证书。

真实进程与容器测试（项目根目录）：

```powershell
.venv/Scripts/python.exe tests/live_development_smoke.py
.venv/Scripts/python.exe tests/live_development_smoke.py --external-llm
docker build -t personlogy-optimization-api -f apps/api/Dockerfile .
docker build -t personlogy-optimization-worker -f apps/worker/Dockerfile .
.venv/Scripts/python.exe tests/container_smoke.py
```

每次进程 smoke 创建独立 SQLite 数据目录，设置初始 Schema 快照，结束后停止自己启动的 API/Worker。容器 smoke 删除自身创建的容器和临时数据卷。外部模型开关会产生实际模型请求。前端检查在 `apps/web` 执行 `npm run typecheck` 和 `npm run build`。

## 范围与限制

- 本轮按四任务实施计划收尾。向量召回、中文改写召回评估、增量索引和统一流水线视图仍属于建议清单中的后续工作。
- Gel 检索/索引仍不支持；本轮实现的是显式能力反馈。
- 项目过滤不是身份认证或权限授权。本次验证未覆盖多 Worker 高并发竞争或外部副作用 exactly-once。
- 执行期限可以取消异步应用流程，不能强制终止已运行的同步第三方调用线程；HTTP 调用另有客户端超时。LLM 编译结束后的持久化位于可取消应用流程内。
- 前端完成类型与构建验证；本轮未进行浏览器视觉验收。
- 本次没有修改现有业务库、提交 Git、推送或部署到远程服务。
