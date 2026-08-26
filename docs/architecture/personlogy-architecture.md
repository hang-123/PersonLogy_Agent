# PersonLogy Agent 系统架构书

## 1. 架构目标

系统采用模块化单体作为 v0.1 的实现形态：一个 API、一个 Worker、一个 Gel 主数据库和一个对象存储。代码按业务能力隔离，未来可以在不改变领域接口的情况下拆分服务。

## 2. 总体分层

```text
接入层
  反向代理 / API 网关 / 认证 / 限流 / 审计

应用层
  数据导入 / 任务编排 / 知识编译 / 数据治理
  Schema 管理 / 数据回写 / 索引构建 / 模型检索

领域层
  来源模型 / 知识对象 / 关系类型 / 证据模型
  验证状态 / 生命周期 / 项目权限 / 领域工具协议

基建层
  Gel / MinIO / LLM / Embedding / Queue / Worker
  日志 / 指标 / Trace / 配置 / 备份
```

## 3. 关键模块边界

### 数据导入

负责 PDF 和对话的格式识别、内容解析、元数据提取、哈希和来源版本。不得负责知识关系判断。

### 任务编排

负责异步任务、状态机、队列、重试、幂等和失败恢复。长耗时 LLM 调用和索引任务必须通过 Worker 执行。

### 知识编译

负责 LLMWiki 整理、Concept/Claim/Relation/Citation 候选生成和 OKF 导出。输出候选，不直接绕过治理写库。

### 数据治理

负责 Schema 校验、规则去重、语义去重、冲突检测、来源验证、可信度和人工审核。

### Schema 管理

负责 LLM 生成 Gel Schema/Migration、差异检查、沙盒测试、审批和 Migration Tool 执行。该模块属于管理面，不属于普通数据导入面。

### 数据回写

负责将经过治理的知识对象通过 Repository/Unit of Work 写入 Gel，同时保存 MinIO 原文、OKF 和审计事件。

### 索引构建

负责全文、向量和关系索引。索引必须异步、可重试、可重建。

### 模型检索

负责权限过滤、BM25/全文检索、向量检索、关系扩展、结果重排、证据组装和 RAG 上下文生成。

## 4. 存储边界

```text
MinIO：PDF、对话原文、OKF Bundle、导出文件
Gel：来源、版本、内容块、知识、关系、证据、任务、权限
索引：Gel 主数据的可重建派生数据
```

不引入 SQL + Neo4j 双主存储，也不让索引成为事实来源。

## 5. 依赖规则

```text
API / Worker
    ↓
Application
    ↓
Domain + Ports
    ↓
Adapters
    ↓
Gel / MinIO / LLM / Queue
```

领域层不得依赖 FastAPI、Gel、MinIO、模型供应商或队列；API 路由不得直接执行数据库查询；LLM 不得拥有任意数据库连接。

## 6. 运行时关键链路

```text
Upload API
→ IngestionJob
→ Worker
→ Parser
→ Knowledge Compiler
→ Governance
→ Writeback Transaction
→ Index Job
→ Retrieval API
→ Frontend
```

## 7. 安全边界

- 项目级数据隔离；
- 原始文件访问和知识访问分离；
- AI 只能通过领域工具读取；
- Schema Migration 仅管理员可审批执行；
- 所有写入、模型调用和原文访问都记录审计事件；
- 机器生成和人工确认状态必须分离。

