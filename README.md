# PersonLogy Agent

PersonLogy Agent 是一个面向个人项目和长期主题的知识系统，目标是把 PDF 文档、大模型对话等分散资料整理为结构清晰、关系可追溯、可检索、可多端访问的个人知识库。

## 项目目标

```text
资料导入 → 内容解析 → LLMWiki 知识编译 → 数据治理
→ Gel 结构化回写 → 全文/向量/关系索引 → 带证据检索
```

第一版聚焦 PDF 上传和大模型对话导入，暂不处理本地文件夹同步、飞书自动同步、多人协作和复杂图算法。

## v0.1 技术栈

| 类别 | 选择 | 用途 |
|---|---|---|
| API | Python API（当前工程沿用） | 文件、对话、知识和检索接口 |
| 异步任务 | Worker + Queue | PDF 解析、LLM 编译、治理和索引 |
| 结构化数据库 | Gel | 业务对象、知识节点、关系、证据和权限 |
| 查询语言 | Gel Schema / EdgeQL | Schema、Migration 和结构化查询 |
| 原始存储 | MinIO / S3 兼容对象存储 | PDF、对话原文和版本文件 |
| 知识格式 | OKF v0.2 + PersonLogy 扩展 | 可读、可迁移的知识表达 |
| 模型能力 | LLM / Embedding / Reranker Provider | 编译、向量化、重排和问答 |
| 检索 | 全文 + 向量 + 关系混合检索 | 召回知识、关系和证据 |
| 前端 | Web UI | 上传、审核、浏览、关系图和问答 |

具体模型供应商、队列实现和前端框架通过 Adapter/Port 隔离，避免绑定单一供应商。

## 整体架构

```text
接入层：反向代理、API 网关、认证、限流、审计
    ↓
应用层：导入、任务编排、知识编译、治理、Schema 管理、回写、索引、检索
    ↓
领域层：Source、Claim、Relation、Citation、权限和生命周期
    ↓
基建层：Gel、MinIO、LLM、Embedding、Queue、Worker、可观测性
```

Schema 管理和日常数据导入是两条受控路径：

```text
Schema：LLM 生成 Gel Migration → 校验/审批 → Migration Tool 执行
数据：LLM 生成知识对象 → 治理 → 受控 Tool → Gel 事务写入
```

## 文档入口

- [功能 Spec](docs/features/README.md)
- [初版总 Spec](docs/spec/personlogy-v0.1-spec.md)
- [系统架构书](docs/architecture/personlogy-architecture.md)
- [代码目录与重构约定](docs/engineering/code-structure.md)
- [项目开发计划](docs/plans/development-plan.md)
- [系统图稿](docs/architecture/diagrams.md)

## 开发约定

- 功能验收标准统一写在 `docs/features/<feature>/spec.md`；
- 验收标准统一使用 Given/When/Then；
- 领域层不得直接依赖 Gel、MinIO、LLM 或 Web 框架；
- API/Worker 通过 Application 调用 Domain 和 Ports；
- 原始资料不可变，索引必须可重建；
- Schema Migration、知识写入和索引构建分别审计。

