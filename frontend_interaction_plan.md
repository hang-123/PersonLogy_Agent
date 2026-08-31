# 前端交互落地计划

> 对齐来源：`docs/plans/development-plan.md` 的 P9；当前状态：FE-00/FE-01/FE-02/FE-03/FE-04/FE-05 已完成，FE-06 等待问答接口。

## 1. P9 目标与退出标准

实现一个可连接真实 API 的 Web 第一版，让用户完成：

```text
项目上下文
  → PDF / 对话导入
  → 查看任务进度
  → 人工审核候选
  → 检索知识与关系
  → 点击 Citation 回到原始材料
```

P9 退出标准：用户能够完成导入、审核、检索和回溯；关系图和问答作为检索链路之上的交互能力接入。

## 2. 当前基线

### 已有能力

- React 19 + Vite + TypeScript + Ant Design 6。
- `App.tsx` 已有审核台/来源录入台导航、API 健康状态和刷新动作。
- `CandidateDesk` 已有筛选、列表、来源/证据展示、Payload 编辑、发布/合并/拒绝交互，但依赖旧接口。
- `SourceDesk` 已有来源表单、Evidence 创建和 Candidate 草稿交互，但当前不是 PDF/对话导入入口。
- `@xyflow/react` 已在依赖中，可复用实现关系图。
- 暖纸色“研究档案台”视觉语言和桌面/移动响应式样式已存在。

### 必须先处理的事实

当前 `apps/web/src/api.ts` 调用的 `/sources`、`/candidates`、`/objects`、`/evidence` 与实际后端路由不一致。P9 的第一个切片必须重写 API client 和 DTO 类型，否则已有页面无法接入真实数据。

另外，项目状态栏没有现成的项目列表/选择 API，因此需要先提供可配置的项目上下文：项目名称、slug，以及导入后缓存的 project_id。

## 3. 实现切片与顺序

### FE-00：API 契约对齐与项目上下文

目标：建立前端对当前 `/v1` API 的单一访问层。

- 重写 `apps/web/src/api.ts`，优先接入：
  - `POST /pdfs/upload`
  - `POST /conversations/import`
  - `GET /jobs`、`GET /jobs/{job_id}`
  - `GET /review-tasks`、`POST /review-tasks/{task_id}/decision`
  - `GET /retrieval/search`
  - `GET /lineage/...`
- 在 `types.ts` 建立 PDF 导入、对话导入、Job、ReviewTask、RetrievalHit、Citation、RelationPath、Lineage 的 DTO 类型。
- 新增 `ProjectContext`：表单输入 `project_name/project_slug`，导入成功后保存 `project_id`；刷新后从 localStorage 恢复。
- 统一错误解析、HTTP 409 冲突、网络离线和取消请求处理。
- 清理旧 endpoint 的调用，避免新旧 API 并存造成误判。

验收：浏览器可读取 health；PDF/对话请求的请求体和响应类型与后端一致；缺少项目上下文时所有依赖项目的动作明确阻止并提示。

### FE-01：导入中心

目标：完成 P3/P4 的用户入口和上传反馈。

- 新增“导入中心”视图，包含 PDF 上传和对话 JSON 导入两个 tab。
- PDF：拖拽/选择文件、仅允许 PDF、展示文件名和大小、标题、项目上下文、提交 loading。
- 对话：支持 JSON 文件选择和文本粘贴；提交前做字段级校验，至少提示 conversation_id、title、messages、role、content 缺失。
- 提交成功后显示 source_id/source_version_id/job_id、复用版本标记、页数或消息导入统计。
- 提供“查看任务”入口，并把 job_id 交给 FE-02。
- 错误态区分格式错误、超限、重复/复用和网络错误；不丢失用户已填写内容。

验收：合法 PDF 提交后用户能看到任务 ID、初始状态和来源信息；非法文件不会进入成功态；对话重复导入显示 duplicate count。

### FE-02：任务进度与结果导航

目标：让异步导入链路可观察。

- 新增任务列表和任务详情面板，展示 kind、status、stage、progress、attempt/max_attempts、created/started/finished 时间和 failure_reason。
- 对进行中的任务按固定间隔轮询 `GET /jobs/{job_id}`；终态停止轮询，组件卸载时取消请求。
- 状态映射：queued/running/retrying/succeeded/failed/cancelled 使用统一颜色和文案。
- 成功态提供“去审核”“去检索”；失败态保留失败原因和“重新查看/重新导入”动作。
- 当前后端没有明确 retry endpoint，暂不在前端伪造重试写入；待契约确定后再接入。

验收：任务进度不会因切换页面丢失；失败原因可见；轮询在终态和卸载后停止。

### FE-03：审核工作台重接真实 ReviewTask

目标：保留现有三栏“队列—证据—决策”体验，但切换到 P6 当前契约。

本轮已补齐：

- `GET /v1/review-tasks/{task_id}` 返回 `before/after` 候选快照和版本号。
- 前端已接入批准、驳回、要求修改，以及 `expected_version` 版本校验。

仍需 API 补齐：

- ReviewTask 详情还需要返回 source/version、evidence/citation，才能恢复中栏原文与 Evidence 展示。
- 需要明确 approved/rejected/revised 与候选状态的映射，以及审核后是否写入正式知识。
- 如果要保留“合并到已有对象”，需要恢复对象搜索和 merge endpoint；当前 API 清单中未发现可直接使用的对象/候选接口。

前端实现：

- 待审核/已处理筛选、队列数量、键盘可达的列表选择。
- 中栏展示原文摘要、Evidence、locator、来源版本和证据有效性。
- 右栏编辑 Payload/changes，填写 reviewer_id、reason，按决策展示不同动作。
- 提交前确认；提交中锁定动作；成功后刷新任务并保留结果摘要。
- 对 409/version mismatch 显示“数据已更新，请重新加载”，禁止覆盖当前服务端版本。

验收：批准、驳回、修改都能提交正确的 decision body；审核结果与队列状态同步；无证据候选不能被 UI 误显示为可发布。

### FE-04：知识检索与 Citation 回溯

目标：接入 P8 的检索结果，使用户能从知识回到证据。

- 新增“知识检索”视图：项目上下文、关键词输入、limit、是否展开关系。
- 展示 statement、subject、score、证据片段、来源标题、locator 和关系路径。
- Citation 统一处理：
  - PDF：打开来源预览，并定位 `page/paragraph`；若后端只返回 locator，先展示定位信息并等待文件流/预览 endpoint。
  - 对话：打开消息阅读器，定位 `message_id/ordinal`；若无消息读取 endpoint，显示可追溯 ID，不伪造正文。
- 展示无结果、索引未就绪、项目不匹配、网络失败等状态。
- 结果 URL 使用 query/hash 保存检索词和选中的 citation，支持刷新后恢复。

前置 API 补齐项：来源详情/原始文件或消息读取接口，以及 Citation locator 的稳定 schema。

验收：一次检索可显示知识命中及其证据；点击 Citation 后用户至少能得到稳定的来源和定位信息，具备可打开原文时完成精确定位。

### FE-05：关系图

目标：在 FE-04 的结果之上提供可验证的关系视图。

- 使用 `@xyflow/react`，将 subject、target 映射为节点，将 relation path 映射为边。
- 节点显示名称、对象类型和验证/来源状态；边显示 relation_type 和 direction。
- 支持节点选中、聚焦对应检索结果、展开关联 Citation；无关系时显示解释性空态。
- 初始只渲染当前检索结果涉及的关系，避免一次加载全库；后续再考虑分层展开。
- 节点和边颜色遵循现有研究档案台色板，不引入独立视觉主题。

前置 API：优先使用 `/retrieval/search?expand_relations=true`；若需要跨查询展开，再增加专用 graph endpoint。

验收：关系方向与 API 一致；节点选中能回到来源证据；大结果集不会阻塞主页面。

### FE-06：带来源问答

目标：完成 P9 功能边界中的问答入口。

- 先复用 FE-04 的结果卡片和 Citation 组件，避免重复实现证据展示。
- 接入 P8 提供的 answer endpoint；响应至少需要 answer、citations、relation paths、uncertainty/conflicts、project scope。
- UI 展示回答正文、引用编号、来源列表、关系路径和冲突/不确定性提示。
- 明确加载中、部分结果、失败和空回答状态；不在前端执行 Prompt，不把检索结果伪装成模型回答。

前置 API：当前仓库未发现问答 endpoint，因此 FE-06 排在 FE-04/FE-05 之后，接口未定前只做组件边界和数据类型，不接假数据。

### FE-07：整体验收与质量门

- 依赖安装后执行 `npm run typecheck`、`npm run build`。
- 浏览器验收：导入、任务轮询、审核、检索、Citation、关系图、移动端无横向溢出。
- API 异常验收：离线、4xx 字段错误、409 并发审核、空数据、索引未就绪。
- 可访问性：按钮和表单有 label；键盘可操作；状态变化可被辅助技术感知；颜色不是唯一状态表达。
- 记录 P9 退出证据：截图/录屏、接口请求摘要、构建结果和未完成后端契约清单。

## 4. 建议开发节奏

按 P9 所在 Sprint 7 的 5–7 天估算：

| 天数 | 切片 | 结果 |
|---:|---|---|
| 1 | FE-00 | API client、DTO、项目上下文可用 |
| 2 | FE-01 | PDF/对话导入成功反馈 |
| 3 | FE-02 | Job 任务进度闭环 |
| 4 | FE-03 | ReviewTask 审核链路可提交 |
| 5 | FE-04 | 检索与 Citation 展示 |
| 6 | FE-05 | 关系图和响应式细化 |
| 7 | FE-06/07 | 问答接入（若 API 已就绪）与验收 |

若来源详情接口或 FE-06 问答接口未及时补齐，保留当前已完成的真实链路，并将阻塞项记录为 P9 依赖，不使用生产假数据掩盖缺口。

## 5. 暂不纳入 P9 第一版

- Neo4j 投影管理和投影重试操作。
- 完整权限/角色管理；前端只保留 reviewer 字段和后端错误反馈。
- 向量检索、重排、复杂多跳图布局。
- 前端直接执行 LLM Prompt 或绕过领域工具写入。
- 依赖未定义 API 的自动重试、批量审核和全库知识目录。

## 6. 验证清单

- [x] API client 与当前 `/v1` 路由和 DTO 对齐。
- [x] 项目上下文可以设置、恢复和清除。
- [x] PDF 上传结果显示 source/version/job。
- [x] 对话导入显示 imported/duplicate message count。
- [x] Job 进度轮询、终态和失败原因可见。
- [x] ReviewTask 决策提交、版本冲突处理和结果刷新完成。
- [x] 检索结果含 evidence/citation/relation path。
- [x] Citation 能明确展示来源定位；精确原文打开待来源接口。
- [x] 关系图节点、边、方向和来源一致。
- [ ] 问答仅在 P8 answer contract 明确后接入。
- [ ] TypeScript、Vite build、浏览器主流程和移动端验证通过。
