# P8 向量语义召回与真正混合检索方案（讨论稿）

版本：v0.1  
前置：SQLite FTS5/BM25 检索已落地，索引任务已接入 Job/Worker

## 1. 目标

让用户使用不同措辞提问时，系统仍能召回语义相近的 Claim，同时保留全文检索对专有名词、数字、代码和精确短语的优势。最终结果必须回到原始 Citation，而不是只返回向量相似文本。

## 2. 真正的混合检索链路

```text
用户问题
  → 项目/权限过滤
  ├─ 查询规范化 → FTS5/BM25 召回 Top-Klex
  └─ Embedding → 向量召回 Top-Ksem
        ↓
按 Claim/Document ID 合并去重
  → RRF 或归一化分数融合
  → 关系扩展（一至两跳）
  → 证据完整性过滤
  → 可选重排
  → EvidenceAssembler
  → Claim + Citation + 原文定位 + 知识路径
```

第一版建议使用 Reciprocal Rank Fusion（RRF），不直接相加 BM25 和 cosine 原始分数，因为两者量纲不同：

```text
hybrid_score = α / (k + lexical_rank)
             + β / (k + semantic_rank)
             + γ / (k + relation_rank)
```

其中 `α/β/γ` 和 `k` 配置化并记录在检索结果元数据中。

## 3. 向量索引数据设计

向量属于派生数据，不能成为知识事实来源。建议在 SQLite 中增加：

```text
retrieval_embedding
- id
- retrieval_document_id
- model_name
- model_version
- dimensions
- vector_blob
- content_hash
- created_at
```

开发阶段可以将 float32 向量存为 BLOB，在 Python 中做小规模 cosine 计算；数据规模增大后，把 `SemanticRetriever` 替换为 sqlite-vec、FAISS 或独立向量库，P8 上层接口不变。

## 4. Embedding 任务生命周期

索引任务不应把模型调用放在 API 请求中：

```text
retrieval.index
  → 重建文本/FTS 索引
  → 按 content_hash 检查 embedding 是否可复用
  → 提交 retrieval.embed 子任务
  → 写入 model/version/dimensions/vector
  → 更新 index build 状态
```

模型调用失败时：

- FTS 索引和知识主数据保持可用；
- embedding 任务单独失败并可重试；
- 检索结果标记当前使用的召回通道；
- 更换模型版本时只重建对应 embedding，不修改 Claim/Citation。

## 5. Provider 解耦

核心层只定义：

- `EmbeddingProvider`：批量文本转向量；
- `SemanticRetriever`：按项目范围进行向量召回；
- `EmbeddingVector`：携带模型名、版本和维度；
- `SemanticHit`：只返回派生召回结果。

实现层再提供：

1. `NullEmbeddingProvider`：开发/降级用，不声称具备语义能力；
2. 本地模型 Provider：适合离线开发；
3. HTTP Provider：接入外部 embedding 服务；
4. SQLite brute-force Retriever：小数据集验证用；
5. sqlite-vec/FAISS Retriever：规模扩大后的替换实现。

## 6. 证据和安全约束

- 语义召回只能扩大候选集合，不能绕过项目权限过滤；
- Claim 没有 Citation 时不得进入最终证据集合；
- Relation 扩展必须在同一项目和授权范围内执行；
- 不能因为相似度高就自动把候选知识变成正式知识；
- 最终回答上下文必须携带 Citation、SourceVersion 和 locator；
- 记录 `retrieval_strategy`、`embedding_model`、`index_version`，保证结果可复现。

## 7. 分阶段实现

### V1：端口与数据契约

- 已完成 `EmbeddingProvider`、`EmbeddingVector`、`SemanticRetriever`、`SemanticHit` 端口定义；
- 固化检索文档内容和 content hash；
- 为索引构建记录模型版本。

### V2：SQLite 小规模语义召回

- 增加 embedding 表和 `retrieval.embed` Job；
- 实现一个可配置的本地/HTTP Provider；
- Python cosine brute-force 召回；
- 与 FTS5 通过 RRF 合并；
- 增加无模型时的明确降级状态。

### V3：重排与评估

- 对融合后的 Top-N 使用可选 reranker；
- 建立标注查询集；
- 评估 Recall@K、MRR/nDCG、证据命中率和无证据误答率；
- 通过配置调整 α/β/γ，而不是把权重写死。

### V4：规模化替换

- 评估 sqlite-vec、FAISS 或独立向量服务；
- 保持 `EmbeddingProvider` 和 `SemanticRetriever` 不变；
- 支持按模型版本重建和回滚。

## 8. 下一步编码顺序

1. 将当前索引接口完全纳入 Job/Worker（本轮进行中）；
2. 增加 `retrieval.embed` 任务和 embedding 持久化；
3. 实现 SQLite brute-force semantic retriever；
4. 将 `RetrievalService` 改为 lexical + semantic RRF 融合；
5. 补充混合检索评估样例和证据约束测试。
