# P8+ SQLite 过渡落地方案（讨论稿）

版本：v0.1-draft  
依据：`docs/plans/development-plan.md` 与当前 P1-P6 实现状态

## 1. 为什么可以拆开 P7 和 P8

原计划中 P7 同时承担两项职责：

1. 将治理通过的知识正式写入 Gel；
2. 为知识建立全文、向量和关系索引。

当前真正阻塞的是第一项，而 P8 需要的是第二项及稳定的知识读取能力。因此本阶段将 P7 拆成：

```text
P6 审核通过
  ├─ 当前阶段：发布到 SQLite 检索数据集 → 构建索引 → P8 检索
  └─ 后续阶段：正式写入 Gel → 从正式主数据重建索引
```

SQLite 方案必须保留来源、版本、ContentBlock、Claim、Relation、Citation 和项目边界，不能只存一份可搜索文本。

## 2. 调整后的开发顺序

### S0：最小契约冻结

- 明确 P6 哪些状态可以进入检索：建议只允许 `human_verified` 或 `ready_for_writeback`。
- 固化 Claim、Relation、Citation、SourceVersion、ContentBlock 的读取 DTO。
- 固化项目/来源权限过滤字段。
- 固化页码、段落、消息 ID 等证据定位结构。

这一阶段不实现 Gel 回写，只保证 P8 不依赖 Gel 类型和 EdgeQL。

### S1：SQLite 检索数据集与发布流程

在现有 SQLite Schema 基础上增加或补齐检索所需的派生表/视图，并通过 `retrieval.index` Job 在 Worker 中执行：

- 全文文档或文本块表；
- FTS5/BM25 虚拟表；
- 关系邻接表或查询视图；
- embedding 记录表；
- index version / build job 状态表；
- 从已审核知识生成或更新检索数据集的发布记录。

发布过程需要具备幂等键、版本号、失败重试和可重建能力。

### S2：P8 第一版检索

建议先交付确定性较强的最小闭环：

```text
查询
→ 项目/权限过滤
→ FTS5/BM25 召回
→ Claim/Citation 关联
→ 一至两跳 Relation 扩展
→ 证据片段组装
→ 返回知识路径和原文定位
```

向量召回和复杂重排作为同一接口下的可插拔策略，避免第一版被 embedding 服务阻塞。

### S3：向量与重排增强

- `EmbeddingProvider` 独立封装模型、维度和版本；
- embedding 生成失败不影响主知识数据；
- 同一查询可融合全文分数、向量分数和关系分数；
- 记录召回策略和 index version，便于评估与复现。

### S4：P9 前端接入

以 P8 Retrieval API 为中心重写前端旧契约，补齐：

- 检索输入和结果列表；
- Claim/Citation 展开；
- PDF 页码/段落定位；
- Relation 图或路径展示；
- 不确定性和无证据状态。

### S5：P10 公共基础设施（与 P8/P9 并行）

P10 不应作为 P8 或 P9 的后置页面功能，而应作为跨模块基础设施独立推进：

- Schema Registry / Schema Snapshot；
- Schema Proposal 和版本差异；
- 结构约束与兼容性检查；
- SQLite 沙盒迁移测试；
- 审批、执行、回滚和审计记录；
- `MigrationExecutor` 适配器，先支持 SQLite，未来支持 Gel。

P8 只依赖 `SchemaProvider` 获取当前有效 Snapshot，用于解析字段、过滤和结果解释；P9 只依赖 API 契约。P7 将来可以调用 Schema 校验和迁移端口，但 P10 不调用 P7。

向量语义召回与 RRF 融合的单独方案见 [vector-retrieval-plan.md](vector-retrieval-plan.md)。

### S6：P11 稳定性与部署

P11 可以先做 SQLite 环境的日志、审计、健康检查、备份、恢复和索引重建，再在 Gel 接入后补充双后端验证。

## 3. 建议的端口边界

```text
KnowledgeReadPort
IndexStore
EmbeddingProvider
RetrievalService
EvidenceAssembler
WritebackAdapter
```

其中：

- `KnowledgeReadPort` 不关心底层是 SQLite 还是 Gel；
- `IndexStore` 只管理派生索引，不拥有知识事实；
- `RetrievalService` 不直接执行 SQL；
- `EvidenceAssembler` 只接受带来源定位的数据；
- `WritebackAdapter` 暂时使用 No-op 或显式未实现适配器，不影响检索开发。
- `SchemaProvider` 只暴露当前有效 Schema Snapshot；
- `SchemaChangeService` 负责 Proposal、验证、审批和迁移生命周期；
- `MigrationExecutor` 屏蔽 SQLite/Gel 的执行差异。

## 4. 关键验收标准

- 只有审核允许的 Claim/Relation 才会进入检索数据集；
- 检索结果可回到 SourceVersion、ContentBlock 和原始定位；
- 项目权限过滤先于全文、向量和关系扩展；
- 没有足够 Citation 时返回不确定状态，不生成伪引用；
- 索引损坏或删除后，可以仅依赖 SQLite 知识数据重建；
- 重复发布和重复建索引不会产生重复结果；
- 将来切换到 Gel 时，P8 的领域接口和 API 契约不变。

## 5. 当前需要确认的决策

1. SQLite 是本阶段的临时主数据源，还是 Gel 知识数据的本地检索投影？
2. P8 第一版是否接受“全文 + 关系扩展”，向量检索作为第二个迭代？
3. `ready_for_writeback` 是否作为进入 SQLite 检索数据集的唯一状态，还是允许 `human_verified`？
4. P9 是否顺便修正当前前端与 `/v1` 后端路由不一致的问题？
5. P10 的第一版是否以 SQLite Schema Registry + 沙盒迁移为实现，暂不要求真实 Gel Migration 执行？
