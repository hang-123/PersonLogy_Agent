# 初始工程目录初始化计划

## 已确定

- 使用模块化单体；
- API 与 Worker 分离入口；
- Gel 为结构化知识主数据库；
- MinIO 保存原始资料；
- Schema 管理与数据导入分离；
- 索引可重建；
- LLM 通过受控 Tool 访问数据。

## 初始化阶段

### Phase 0：目录和规范

- 建立 `apps`、`packages`、`infra`、`prompts`、`tests`、`docs`；
- 固化 v0.1 Spec 和架构书；
- 保存系统架构图和系统流程图；
- 建立基础配置和开发说明。

### Phase 1：领域骨架

- Project、Source、SourceVersion、ContentBlock；
- KnowledgeNode、Claim、Relation、Citation；
- IngestionJob、ReviewTask、SchemaChangeProposal；
- 定义 Repository、BlobStore、LLMProvider、JobQueue 接口。

### Phase 2：第一条可运行链路

```text
PDF 上传
→ MinIO
→ 解析
→ ContentBlock
→ Gel 写入
→ 任务状态查询
```

### Phase 3：知识编译

```text
ContentBlock
→ LLMWiki
→ Claim / Relation / Citation 候选
→ 治理
→ 受控写回
```

### Phase 4：检索闭环

```text
Gel 主数据
→ 全文 / 向量 / 关系索引
→ 混合检索
→ 证据组装
→ 带引用回答
```

## 当前不做

- 不迁移全部旧代码；
- 不立即拆分微服务；
- 不引入 Neo4j；
- 不让 LLM 直接连接数据库；
- 不在每次导入时动态建表。

