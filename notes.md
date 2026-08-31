# Notes: 前端交互落地

## Plan Source

- 用户指定跟随 `D:\PersonLogy\_Agent\docs\plans\development-plan.md` 的 P9。
- 该路径在当前环境不存在；实际读取的是工作区等价文件 `docs/plans/development-plan.md`。
- P9 目标：上传、任务进度、知识浏览、关系图、引用定位、问答；退出标准是用户可完成导入、审核、检索和回溯。
- P9 前置依赖：P3、P8；开发计划特别指出关系图应在检索和证据链路之后加入。

## Repository Findings

### Existing web app

- 技术栈：React 19、Vite 8、TypeScript、Ant Design 6；已安装 `@xyflow/react`，可用于关系图。
- 入口：`apps/web/src/App.tsx`，当前只有 `review` 和 `source` 两个工作台视图。
- 已有组件：`CandidateDesk.tsx`、`SourceDesk.tsx`；视觉方向已采用“研究档案台”暖纸色、墨色、朱砂和深绿色。
- 已有 API client：`apps/web/src/api.ts`，但主要调用 `/sources`、`/candidates`、`/objects`、`/evidence` 旧契约。
- 已有状态覆盖：加载、空态、错误提示、成功提示、审核动作 loading、移动端纵向布局。

### Current backend contract

- 已注册并可作为 P9 基础的模块：PDF 上传、对话导入、Job 查询、ReviewTask 决策、Retrieval 搜索、Lineage 追溯。
- PDF 上传：`POST /v1/pdfs/upload`，multipart 字段 `project_name`、`project_slug`、`title`、`file`，返回 `job_id`、source/version 信息和页数。
- 对话导入：`POST /v1/conversations/import`，接收标准化消息 JSON，返回 `project_id`、`source_id`、`job_id`。
- 任务：`GET /v1/jobs`、`GET /v1/jobs/{job_id}`，返回 status、progress、stage、attempt、failure_reason。
- 审核：`GET /v1/review-tasks`、`GET /v1/review-tasks/{task_id}`、`POST /v1/review-tasks/{task_id}/decision`；详情 DTO 已返回 before/after 候选快照，尚未返回来源正文和 Evidence 详情。
- 检索：`GET /v1/retrieval/search`，返回 hit、evidence、relation path；需要 `project_id` 和 `q`。
- 追溯：`GET /v1/lineage/...`；当前没有可直接打开 PDF 页码/对话消息的来源内容或文件流端点。

### Gaps and risks

- `docs/plans/project-status-overview.md` 已明确记录前端与后端契约脱节；当前 `api.ts` 不能直接驱动现有后端。
- 当前没有项目选择/创建的前端入口，而 PDF、对话、检索都需要项目上下文。
- 当前审核接口不足以重建原有三栏审核台，需要后端补充 Candidate/ReviewTask 详情 DTO，或调整成新的 ReviewTask 详情接口。
- 当前没有问答 endpoint；P9 可先落地带 Citation 的检索工作台，问答 UI 需要 P8 answer contract 后接入。
- `npm run typecheck` 基线未执行成功：`apps/web/node_modules` 未安装，系统找不到 `tsc`。

## User Flows

1. 设置/确认项目上下文 → 选择 PDF 或对话 JSON → 提交导入 → 展示 source/version/job → 自动进入任务详情。
2. 任务详情轮询状态 → 展示阶段、进度、尝试次数和失败原因 → 完成后进入审核/检索入口。
3. 审核队列 → 查看候选 payload 与来源证据 → 修改/批准/驳回 → 展示版本与状态变化。
4. 输入检索问题 → 浏览知识命中 → 展开关系 → 点击 Citation → 打开 PDF 页码或对话消息定位。
5. 问答输入 → 展示回答、引用、关系路径和不确定性；等 P8 问答接口可用后接通。

## Interaction Decisions

- P9 第一个实现切片必须是 API client 对齐和项目上下文，因为它决定后续所有页面是否能接真实后端。
- 任务状态使用服务器状态为真相；前端只轮询、展示和导航，不自行推断完成状态。
- 审核动作使用明确的确认/成功/冲突/失败反馈；重复提交和版本冲突不能静默覆盖。
- Citation 定位统一抽象为 `source_type + source_version_id + locator`，PDF 使用 page/paragraph，对话使用 message_id/ordinal。
- 关系图只消费检索或追溯返回的数据，不在前端凭空生成业务关系。
- 先完成桌面端闭环，再补移动端细节；现有“研究档案台”视觉系统继续沿用。

## Implementation Progress

- FE-00/FE-01/FE-02 已实现：API client、项目上下文、PDF/对话导入中心、Job 列表/详情和轮询。
- FE-04/FE-05 已实现基础真实链路：Retrieval 搜索、Citation locator 展示、关系路径和当前结果局部 React Flow 图。
- FE-03 已实现基础真实链路：新增 ReviewTask 详情 API，返回 before/after 候选快照；前端支持批准、驳回、要求修改和 expected_version 版本校验。原文 Evidence 预览仍待来源详情接口。
- FE-06 暂缓：当前后端未提供问答 endpoint。
- 验证通过：`npm ci --no-audit --no-fund`、`npm run typecheck`、`npm run build`、Vite HTTP smoke、`npm audit --omit=dev`。
- 后端验证通过：`uv run pytest -q`（含 6 个既有条件跳过项）、`uv run mypy app`、治理模块 Ruff 检查。
- 构建提示主 JS chunk 约 759 KB，关系图依赖接入后体积上升；后续多页面阶段应做动态分包。
- 浏览器 Playwright smoke 未执行：当前 Python 环境缺少 `playwright`，且未向项目新增该依赖。

## Errors Encountered

- `npm ci` 首次失败：`package.json` 与 `package-lock.json` 不同步；使用 `npm install --no-audit --no-fund` 安装并同步本地依赖。
- 首次 Playwright smoke 脚本工作目录错误；修正路径后发现环境未安装 Python Playwright。
