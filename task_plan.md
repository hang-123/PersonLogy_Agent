# Task Plan: Candidate 合并与人工审核工作台

## Goal
实现 Candidate 关联已有对象/别名合并命令，并交付可实际操作来源录入、证据创建、候选筛选和审核发布的 Web 工作台，为后续 Neo4j 投影提供稳定 Published 数据入口。

## Phases
- [x] Phase 1: 复核前端工程、API 契约与 PRD 审核交互
- [x] Phase 2: 实现后端对象合并命令、对象检索与测试
- [x] Phase 3: 实现前端 API Client、类型模型与页面信息架构
- [x] Phase 4: 实现来源录入、Evidence 创建、Candidate 审核交互
- [x] Phase 5: 执行后端/前端测试、浏览器验收与文档交付

## Key Questions
1. 如何在不删除历史引用的前提下，把 Object Candidate 合并为已有对象别名？
2. 审核工作台如何同时呈现来源上下文、候选 Payload、证据门禁和审核动作？
3. 如何让 PostgreSQL/API 可用而 Neo4j 未启动时，工作台仍能完整运行？

## Scope
- 按类型、规范名和别名检索正式对象
- Object Candidate 合并为已有对象，追加别名、版本、审计和投影事件
- React 来源录入、Evidence 创建、Candidate 列表和审核详情
- 接受、拒绝、合并操作及错误/加载/空状态
- 响应式布局、无障碍基础与真实 API 联调

## Non-Goals
- 本增量不消费图投影事件，不写 Neo4j。
- 不实现 Claim/Decision、AI 抽取、文件上传或复杂图可视化。
- 不引入新的前端状态管理框架。

## Design Direction
- 采用“研究档案台 / editorial intelligence desk”视觉方向：纸张暖灰底、墨色正文、朱砂操作色和结构化证据标签。
- 强调来源—证据—候选—发布的纵向工作流，而非通用 SaaS 卡片堆叠。
- 使用现有 Ant Design 组件承载可访问交互，自定义布局、排版和状态语言。

## Decisions Made
- Neo4j 继续保持可选；API 仅依赖 PostgreSQL。
- 合并只适用于 Object Candidate，目标对象类型必须一致。
- 合并通过追加 aliases、版本和审计实现，不创建第二个正式对象。
- 前端使用原生 fetch 与 React hooks，避免为 P0 引入额外状态库。

## Errors Encountered
- apply_patch 在 Windows 工作区存在已知 helper_unknown_error；使用受控 UTF-8 写入并执行完整验证。
- Web 镜像首次 npm install 在 WSL 中耗时约 5 分钟；构建最终成功，后续检查复用缓存镜像。
- 当前 Docker Compose 版本不支持 run --no-build；移除该参数后使用缓存镜像完成类型检查。

## Status
**Completed** - Candidate 合并与人工审核工作台已实现并通过前后端、数据库和浏览器验收。
