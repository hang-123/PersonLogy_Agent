# PersonLogy Agent v0.1 Spec

状态：Draft baseline  
版本：v0.1  
目标：验证“资料导入 → 知识编译 → 治理验证 → 结构化回写 → 混合检索 → 来源追溯”的完整闭环。

## 1. 产品目标

PersonLogy Agent 面向个人项目和长期主题，将 PDF 文档、大模型对话等资料整理为结构清晰、关系可追溯、可被 AI 和用户共同访问的个人知识库。

第一版聚焦 PDF 上传和大模型对话导入，不处理本地文件夹自动同步、飞书同步或多人协作。

## 2. 核心原则

1. 原始资料不可变，知识和索引均可追溯、可重建。
2. 每个 Claim 至少关联一个 Citation；重要 Relation 也必须有证据。
3. Gel 是结构化知识主数据库；MinIO 保存原始资料；OKF 是可迁移知识表达。
4. LLM 不直接拥有数据库连接，只能通过受控工具访问。
5. Schema 变化和数据导入是两条不同路径。
6. 索引是派生数据，不是唯一事实来源。

## 3. 范围

### v0.1 包含

- PDF 上传与格式校验；
- 大模型对话标准 JSON 导入；
- 原始文件、来源、版本和内容片段保存；
- PDF/对话内容解析；
- LLMWiki 风格知识编译；
- Concept、Claim、Relation、Citation 提取；
- 规则校验、去重、冲突检测和人工审核；
- Gel 事务写入；
- OKF v0.2 导出；
- 全文、向量和关系索引；
- 混合检索、证据组装和带引用问答；
- 基础 Web 交互和项目级权限。

### v0.1 不包含

- 本地文件夹监听；
- 飞书自动同步；
- 多人协作；
- Neo4j；
- 独立向量数据库；
- 复杂图算法；
- 原生移动端 App；
- 无需审核的全自动知识发布。

## 4. 两条受控路径

### Schema 管理路径

用于初始化或知识模型不匹配时：

```text
领域需求 / Schema 不匹配
→ LLM 读取当前 Schema
→ 生成 Gel Schema / EdgeQL Migration
→ 差异检查、沙盒测试
→ 人工或管理员审批
→ Migration Tool 执行
→ 更新 Schema 版本
```

### 数据导入路径

用于日常 PDF 和对话导入：

```text
导入
→ 格式识别
→ 原始资料保存
→ 内容解析
→ LLMWiki 编译
→ 数据治理
→ 生成结构化写入请求
→ 受控工具编译为 EdgeQL
→ Gel 事务写入
→ 索引构建
```

运行时导入不按每批资料动态建表或删表。

## 5. 核心对象

```text
Project
Source
SourceVersion
ContentBlock
KnowledgeNode
  ├── Concept
  ├── Claim
  ├── Question
  └── Decision
RelationType
KnowledgeRelation
Citation
IngestionJob
ReviewTask
SchemaChangeProposal
```

稳定业务关系使用 Gel 原生 Link；需要独立身份、证据、置信度、验证状态和生命周期的动态知识关系使用 `KnowledgeRelation` 对象。

## 6. 第一版关系类型

- `parent_of`
- `depends_on`
- `supports`
- `contradicts`
- `references`
- `similar_to`

关系必须保存起点、终点、类型、方向、来源证据、置信度、生成者、生成时间和验证状态。

## 7. 导入接口

```http
POST /v1/projects/{project_id}/sources/pdf
POST /v1/projects/{project_id}/sources/conversations
GET  /v1/ingestion-jobs/{job_id}
```

导入任务状态：

```text
queued → uploaded → extracted → compiled → validated → indexed → ready
```

任务必须支持幂等、增量、重试、失败恢复、软删除和来源版本化。

## 8. AI 检索

```text
问题解析
→ 项目与权限过滤
→ 全文检索 + 向量检索 + 关系扩展
→ 结果融合与重排
→ 证据补齐
→ 上下文组装
→ RAG 生成带引用回答
```

AI 通过以下领域工具访问知识：

```text
describe_knowledge_schema
search_knowledge
get_knowledge_node
expand_relations
trace_evidence
find_conflicts
get_source_excerpt
```

## 9. 验收标准

### 必须满足

- 重复导入不会产生重复来源；
- 原始资料和版本可追踪；
- Claim 可定位到具体原文片段；
- 重要 Relation 有类型、方向和来源；
- Schema Migration 经过校验和审批；
- 数据写入经过权限和事务校验；
- 索引可以从主数据重建；
- AI 只能检索授权范围；
- 回答返回引用和来源位置。

### 重点测量

- 来源召回率；
- 关系类型和方向准确率；
- 引用支持率；
- 冲突识别率；
- 一至两跳关系查询延迟；
- 混合检索延迟；
- AI 回答一致性。

