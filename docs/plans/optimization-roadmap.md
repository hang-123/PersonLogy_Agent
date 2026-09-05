# PersonLogy Agent 优化实施计划

版本：v0.1  
计划类型：可靠性、数据正确性与检索能力优化  
依据：当前代码审查、19 项后端测试、前端类型检查及离线边界复现  
目标：先修复会造成错误数据或任务卡死的问题，再补齐 Gel 检索、项目隔离和可观测性，最后提升混合检索质量。

## 一、现状与范围

当前项目已经具备 PDF/对话导入、异步任务、候选治理、受控回写、SQLite 检索和前端工作台。审查确认以下问题仍在当前版本存在：

1. 容器 Worker 固定使用 `DocumentHeuristicCompiler`，API 中的 LLM 配置不会真正作用于后台编译任务；`httpx` 仅在 API 的开发依赖中声明。
2. LLM 返回不存在于原文的 quote 时，适配器会把它绑定到第一段内容；关系引用如果没有对应 Claim 引用，会直接失败。
3. 任务在高进度失败后重试时可能发生进度回退异常；进程重启后，超时的 `running` 任务不会自动回收。
4. API 使用 Gel 存储时，检索 reader 是始终返回空结果的占位实现。
5. Embedding 与 Reranker 已实例化但没有接入检索链路；当前回答只是拼接检索到的 Claim。
6. 任务列表和审核列表没有按当前项目过滤；CI 仍保留不存在的 Alembic/migrations 流程。

本计划不包含多人权限体系、复杂图算法、外部服务迁移和大规模微服务拆分。原始资料不可变、主数据可重建、所有正式结论可回溯是整个计划的约束。

## 二、优先级与执行顺序

| 优先级 | 阶段 | 重点 | 建议顺序 | 预估工作量 |
|---|---|---|---:|---:|
| P0 | 依赖与运行时一致性 | API、Worker、容器使用同一套配置和服务组合 | 1 | 1–2 天 |
| P0 | 证据与 OKF 契约 | 拒绝虚假引用，统一 Claim/Relation/OKF 结构 | 2 | 2–3 天 |
| P0 | 任务可靠性 | 重试、超时、租约、进程恢复 | 3 | 2–4 天 |
| P1 | Gel 检索闭环 | Gel 索引、检索和能力状态 | 4 | 3–5 天 |
| P1 | 项目隔离与前端流程 | 后端 project scope、任务链路展示 | 5 | 2–3 天 |
| P1 | CI/CD 与可观测性 | CI 对齐实际架构，增加启动和恢复检查 | 6 | 1–2 天 |
| P2 | 混合检索质量 | Embedding、Reranker、增量索引和评测集 | 7 | 4–7 天 |

依赖关系：P0 阶段完成后才能稳定评估 P1；P2 依赖检索结果契约和证据绑定已经固定。

## 三、阶段计划

### P0-1 统一 API 与 Worker 运行时

目标：API 和 Worker 对存储、队列、LLM、Embedding、Reranker、审计和 lineage 的配置保持一致。

工作项：

- 抽取共享的 service composition，避免 `apps/api/app/runtime.py` 与 `apps/worker/src/personlogy_worker/main.py` 各自拼装依赖。
- Worker 根据 `PKS_LLM_PROVIDER`、`PKS_LLM_BASE_URL` 和 `PKS_LLM_MODEL` 选择编译器，并透传 prompt/model 配置。
- 为 Worker 补齐 stage runner、审计 sink、lineage store 和 replay 所需的可选依赖。
- 将 `httpx` 声明到实际使用它的运行时包依赖，重新生成锁文件。
- 启动时输出脱敏后的 provider、storage、queue 和 capability 状态；缺少必要配置时快速失败。

交付物：共享运行时构造模块、更新后的 API/Worker 入口、依赖和容器配置、配置说明。

验收标准：

- Given `PKS_LLM_PROVIDER=openai_compatible` 且模型配置完整，When Worker 执行 `knowledge.compile`，Then 使用 OpenAI-compatible compiler，并在结果中记录 model 与 prompt version。
- Given生产镜像只安装项目运行依赖，When导入 `llm_openai`，Then不依赖开发环境专有包。
- Given API 与 Worker 使用同一 SQLite 数据目录，When API 提交任务，Then Worker 能领取并写入同一审计链路。

### P0-2 修复证据绑定与 OKF 契约

目标：任何正式候选都只能引用真实输入内容，并让 Claim、Relation、Citation 与 OKF 导出保持同一语义。

工作项：

- 将 quote 匹配改为严格匹配：空 quote、未命中或超过允许长度时拒绝该候选并记录治理问题，不再回退到 `blocks[0]`。
- 保留 quote 的 `content_block_id`、locator、字符偏移（能计算时）和规范化策略，方便 UI 精确定位。
- Relation 使用独立 Citation；不能借用“某个 Claim 已有引用”作为关系证据存在性的前提。
- 统一 LLM 编译器与 heuristic 编译器的 OKF 字段：Claim 使用稳定 ID、subject/node ID、status、citation IDs；Relation 包含稳定端点和 citation IDs。
- 为 malformed JSON、字段类型错误、非法 relation type、重复标题和引用错配增加领域错误映射及审计摘要。

交付物：OKF/CompilationBundle 契约、严格 quote resolver、迁移兼容说明、适配器和治理测试。

验收标准：

- Given quote 不存在于任何 ContentBlock，When 编译器解析响应，Then 候选被丢弃或标记为治理错误，绝不绑定第一段。
- Given只有关系证据块、没有 Claim 证据，When编译关系，Then仍能创建独立 Citation 和 Relation。
- Given编译结果写入 OKF，When用 JSON 解析并重新加载，Then不丢失候选 ID、状态、端点和证据关联。

### P0-3 加固任务重试、超时与恢复

目标：任务在异常、重启和并发 Worker 场景下可恢复、可追踪且不会重复执行造成脏数据。

工作项：

- 将“总任务进度”和“当前尝试进度”分开，重试时允许当前尝试从 0 重新开始；对外仍展示整体阶段。
- 在队列领取时建立 lease/claim 信息，记录 `worker_id`、`lease_expires_at` 和 heartbeat。
- 在 `start_next` 中回收超过 `timeout_seconds` 或 lease 已过期的 running 任务：可重试任务转为 retrying，超过次数转为 failed。
- 对 SQLite 领取过程增加原子更新或事务锁，避免两个 Worker 同时领取同一任务。
- 为长任务增加心跳和取消检查；失败原因向用户展示可读摘要，详细内容只进入审计日志。
- 设计幂等副作用：编译、索引、回写在重试时不能产生重复 Citation、ReviewTask 或索引文档。

交付物：任务状态扩展、队列租约实现、恢复命令/后台扫描、并发和故障注入测试。

验收标准：

- Given任务在90%进度失败，When进入下一次尝试，Then当前尝试可从有效的初始进度开始并最终成功。
- Given Worker在任务执行期间退出，When另一个 Worker 在 lease 到期后启动，Then任务被重新领取或明确失败，不会永久停留在 running。
- Given两个 Worker 同时领取同一队列，When执行领取事务，Then最多一个 Worker 获得该任务 lease。

### P1-1 补齐 Gel 检索闭环

目标：切换到 Gel 后，用户仍能获得与 SQLite 一致的项目级检索和证据回溯能力。

工作项：

- 在 Gel Schema 中增加检索文档、索引版本、构建状态和必要的查询索引。
- 实现 Gel retrieval indexer/reader，覆盖已发布 Claim、Citation、SourceVersion 和 Relation 展开。
- API 启动时根据能力状态明确显示“可检索”或“尚未配置索引”，不再静默返回空数组。
- 将 retrieval index 构建作为可重试 Job，并记录 build version、document count、耗时和失败原因。
- 为 SQLite 与 Gel 编写同一组契约测试，比较结果字段和项目隔离行为。

交付物：Gel adapter、索引构建任务、能力检查、跨后端契约测试。

验收标准：

- Given Gel 中存在已发布 Claim 和 Citation，When按项目搜索，Then返回 Claim、证据定位和可选关系。
- Given项目没有索引，When调用检索 API，Then返回明确的 index-not-ready 状态或可操作错误。
- Given查询项目 A，When数据库同时存在项目 B 的同词 Claim，Then结果不包含项目 B。

### P1-2 项目隔离与前端流程

目标：用户在一个项目工作台内只看到相关任务、审核项和证据，并能理解导入到发布的完整状态。

工作项：

- 为 jobs、review-tasks、sources 和 retrieval 相关列表增加必需或可选的 `project_id` 过滤。
- 后端校验 project scope，避免仅依赖前端传入的当前项目。
- 前端切换项目时清理旧的选中任务、审核项和检索结果，并重新加载数据。
- 将 PDF 解析、知识编译、治理、回写、索引串成可视化阶段；显示失败节点和下一步动作。
- 给空结果、索引未就绪、任务重试和权限错误提供明确操作提示。

交付物：项目过滤 DTO/API、前端数据刷新策略、导入流水线状态视图、接口测试。

验收标准：

- Given当前项目为 A，When打开任务或审核页面，Then只显示 A 的记录。
- Given用户切换到项目 B，When页面完成刷新，Then不会继续显示 A 的选中任务或审核结果。
- Given索引未就绪或任务失败，When用户查看工作台，Then能看到原因和可执行的下一步。

### P1-3 对齐 CI/CD 与运行检查

目标：CI 检查真实使用的包、入口和数据库后端，避免“CI 通过但容器不能运行”。

工作项：

- 删除或替换当前不存在的 Alembic/migrations 检查，改为安装 `packages/personlogy_core`、运行 API/Worker 测试和 schema 合同检查。
- 增加干净环境下的 API 启动、Worker 导入和最小任务处理 smoke test。
- 增加引用严格性、任务恢复、项目过滤、Gel/SQLite 检索契约测试。
- 将 Ruff、Mypy、Pytest、前端 typecheck/build 与容器构建分成可定位的 CI job。
- 检查提交内容，确保 `.tmp/`、数据库、PDF 测试产物和凭据不会进入版本库；历史中的敏感凭据按安全流程轮换和清理。

交付物：更新后的 CI 配置、smoke test、提交检查规则和部署检查清单。

验收标准：

- Given全新 checkout，When运行 CI，Then不引用不存在的目录或旧数据库配置。
- Given API 和 Worker 镜像构建完成，When执行最小导入任务，Then服务可启动、可领取任务并完成一次可追踪流程。
- Given提交包含临时数据库或凭据文件，When执行检查，Then提交被拒绝并给出文件路径。

### P2-1 接入混合检索与质量评测

目标：在证据正确的前提下，提高中文同义问法、长文本和关系问题的召回质量。

工作项：

- 定义 Embedding、BM25、Relation expansion 和 Reranker 的统一 RetrievalReader 契约。
- 先做候选召回，再批量调用 Embedding/Reranker；设置超时、重试、费用/Token 上限和降级路径。
- 将索引改为增量更新：只重建发生变化的 Claim/Citation，保留完整重建命令作为修复手段。
- 建立小型评测集：问题、期望 Claim、必需 Citation、项目范围和不可接受结果。
- 记录 Recall@k、MRR、证据覆盖率、空答率、平均延迟和模型成本；将基线写入发布门槛。
- 问答输出明确区分“检索到的事实”“证据不足”和“存在冲突”，避免把 Claim 拼接误认为生成式回答。

交付物：混合检索实现、增量索引、评测数据和指标面板、回归门槛。

验收标准：

- Given中文同义问题，When执行混合检索，Then目标 Claim 在约定的 top-k 内，且返回至少一条可定位 Citation。
- Given Embedding 或 Reranker 不可用，When执行查询，Then自动降级到全文检索并记录降级原因。
- Given存在相互冲突的 Claim，When生成回答，Then显式列出冲突及各自来源，不合并成单一确定结论。

## 四、测试与发布门槛

每个阶段都需要先补失败用例，再实现修复。最低检查集如下：

- 后端：`pytest` 全量、Ruff、Mypy；重点包含 LLM quote、任务租约/恢复、SQLite/Gel 检索契约和项目过滤。
- 前端：TypeScript typecheck、生产构建，以及项目切换、空状态、任务失败和引用定位的浏览器验收。
- 运行时：API/Worker 使用同一份环境变量时完成一次 PDF → 编译 → 治理 → 回写/索引 smoke test。
- 数据：随机抽样核对每个 Claim/Relation 的 Citation 能回到原文 ContentBlock；检查重复导入和重试后的幂等性。

发布前必须满足：P0 全部完成；不存在虚假引用回退；没有永久 running 任务；Gel 能力状态不会静默返回空结果；CI 与容器入口一致。

## 五、建议迭代节奏

| 迭代 | 内容 | 可演示结果 |
|---|---|---|
| Sprint 1 | P0-1 + P0-2 | 配置的 LLM 真正参与 Worker 编译，所有引用均可回到原文 |
| Sprint 2 | P0-3 | 模拟 Worker 崩溃后任务自动恢复，重试不重复写入 |
| Sprint 3 | P1-1 + P1-2 | Gel/SQLite 均能按项目检索，前端展示完整导入链路 |
| Sprint 4 | P1-3 | 干净环境可构建、启动、处理最小任务，CI 结果可信 |
| Sprint 5 | P2-1 | 中文同义问题可召回带证据的结果，并有质量指标基线 |

## 六、风险与决策点

| 风险 | 影响 | 应对 |
|---|---|---|
| Gel 与 SQLite 能力差异较大 | 迁移期间检索结果不一致 | 先定义跨后端契约测试，再实现 Gel adapter |
| LLM 输出格式不稳定 | 候选数量下降或治理任务增加 | 严格 schema 校验、保留原始响应摘要、允许重试和人工审核 |
| 租约回收与副作用并发 | 重复编译或重复回写 | 以幂等键、唯一约束和版本检查兜底 |
| 混合检索成本和延迟上升 | 用户体验和运行费用受影响 | 批量调用、限额、超时、全文降级及指标监控 |
| 现有数据已包含旧格式 | 升级后读取失败 | 提供 OKF 版本迁移/兼容读取，并在发布前跑一次数据审计 |

## 七、当前下一步

从 P0-1 开始：先抽取 API/Worker 共享运行时构造并补充运行依赖，然后用一个真实的 `knowledge.compile` smoke test 证明 Worker 配置已经生效。完成后再进入引用契约修复，避免在错误的执行路径上继续堆功能。
