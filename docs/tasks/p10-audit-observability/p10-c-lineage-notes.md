# P10-C 开发记录

## 状态

已完成，SQLite 版本通过测试、Lint 和类型检查。

## 已落地内容

- 新增 `LineageLink`、`LineageStore` 和 `SQLiteLineageStore`，支持项目隔离、幂等写入及连通分量回溯。
- 新增 `LineageService`，提供 claim、source version、job、retrieval 四类追踪入口。
- 编译、PDF 导入、治理决策、索引构建和检索请求已接入统一血缘记录。
- 新增四类只读 API 路由：`/lineage/claims`、`/lineage/source-versions`、`/lineage/jobs`、`/lineage/retrieval`。
- 血缘元数据复用审计元数据白名单，不写入敏感原文。

## 验证结果

- `44 passed, 6 skipped`
- Ruff 检查通过
- mypy 检查通过（98 个源文件）
- `git diff --check` 无空白错误

## 范围边界

本阶段完成 SQLite 适配。Gel 后端适配及更完整的跨后端一致性验证留给后续 P10-F / 后端适配工作。

## 现有派生边界

- SourceVersion -> ContentBlock -> Citation -> Claim
- Job -> 由任务产生的 SourceVersion、Claim、ReviewTask、IndexBuild
- ReviewTask -> candidate Node/Claim/Relation
- Claim -> RetrievalDocument -> RetrievalRequest 命中结果

## 当前实现约束

- 现有业务表已经保存大部分外键关系，P10-C 增加统一查询投影，不替换原有关系。
- `retrieval_request` 目前没有持久化业务表，需要先以血缘关系和审计事件中的请求 ID 作为回溯入口。
