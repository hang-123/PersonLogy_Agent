# Candidate 合并与人工审核工作台

## 本增量定位

本增量不消费 Neo4j 投影事件。目标是让维护者能够通过真实 Web 界面建立并审核
Published 数据，为后续 Neo4j 投影提供稳定输入。

## 后端能力

新增正式对象查询：

- `GET /v1/objects`：按 object_type、规范名、展示名或 alias 搜索。
- `GET /v1/objects/{object_id}`：查询正式对象详情。
- `GET /v1/sources`：搜索和分页读取来源档案。

新增审核合并命令：

- `POST /v1/candidates/{candidate_id}/merge`

合并规则：

1. 只允许 Object Candidate。
2. Candidate object_type 必须与目标对象一致。
3. 归档对象不能作为合并目标。
4. Candidate 规范名、展示名、候选 aliases 和审核补充 aliases 去重后追加到目标。
5. 目标对象版本号加一。
6. 同一事务写入 ObjectVersion、AuditLog、REVISE GraphProjectionEvent。
7. Candidate 状态更新为 merged，并记录正式目标 ID。
8. 重复审核由 Candidate 行锁和状态机阻止。

## Web 工作台

工作台地址：`http://localhost:5173/`。

### 候选审核台

- 按状态和 Candidate 类型筛选。
- 左侧展示审核队列。
- 中部展示 Source 原文和 Evidence 定位。
- 右侧允许修改 JSON Payload 后发布。
- Object Candidate 可检索并合并到已有规范对象。
- 支持填写审核人、审核依据、拒绝原因。
- 发布、合并和拒绝后自动刷新队列。

### 来源录入台

- 保存标题、来源类型、URL、正文、可见性和录入人。
- 显示历史来源档案。
- 从当前来源截取 Evidence，记录段落与来源等级。
- 手工提交 Object/Relation Candidate。
- 明示 AI 未来也只能进入 Candidate 入口。

## 视觉与交互

采用“研究档案台”视觉语言：

- 暖纸色档案背景、墨色标题、朱砂审核动作和深绿色导航。
- 用纵向知识链路呈现 Source → Evidence → Candidate → Published → Topology。
- 桌面端采用三栏审核结构，移动端自动转为纵向阅读。
- Ant Design 提供表单、键盘焦点、状态提示和基础无障碍语义。

## 验证结果

- 后端：Ruff、Mypy、18 项测试和真实 PostgreSQL 集成测试通过。
- 前端：TypeScript 类型检查与 Vite 生产构建通过。
- 运行时依赖：`npm audit --omit=dev` 为 0 漏洞。
- 浏览器：API online、主导航、来源表单填写、空状态和移动端无横向溢出通过。
- 浏览器控制台：0 error / warning。
- Vite 构建提示主包约 682 KB，后续进入多页面或图可视化阶段时再进行路由级代码分包。

## Neo4j 后续入口

正式发布或合并已经产生 `graph_projection_event`：

- 新对象/关系：`publish`
- 对象 alias 合并：`revise`

下一阶段可实现 Worker 领取这些事件、按 mapping_version 幂等写 Neo4j，并维护投影检查点。
