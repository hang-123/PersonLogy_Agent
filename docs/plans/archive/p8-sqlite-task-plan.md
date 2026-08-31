# Task Plan: P8+ SQLite 开发路径

## Goal
在不依赖 P7 Gel 正式回写的前提下，基于现有 P1-P6 能力和 SQLite 适配器推进 P8 混合检索及后续模块，并保留未来接入 P7 的替换边界。

## Phases
- [x] Phase 1: 读取原始开发计划与当前项目状态
- [x] Phase 2: 确认 P7 与 P8 的依赖拆分方式
- [x] Phase 3: 确认 SQLite 临时主库/检索投影定位及接口契约
- [ ] Phase 4: 实现索引、混合检索和证据组装（第一批已完成全文、关系和证据组装）
- [ ] Phase 5: 接入前端、Schema 管理和稳定性能力
- [ ] Phase 6: 验证、补充文档并准备未来 Gel/P7 切换

## Key Questions
1. SQLite 在这一阶段是临时主数据源，还是只作为 Gel 知识数据的检索投影？
2. P8 第一版是否先交付全文 + 关系检索，向量检索随后接入？
3. P9 前端是否以当前 `/v1` API 为准同步重写旧接口调用？
4. P7 回写完成后，SQLite 是否继续作为本地缓存/索引源，还是完全切回 Gel？

## Decisions Made
- 保留 P7 的正式 Gel 回写边界，不让 P8 直接依赖具体 Gel 写入实现。
- P8 的开发入口采用稳定的读取端口和索引端口，SQLite 作为当前实现。
- 原始资料、Claim、Relation、Citation 的追溯关系必须在 SQLite 阶段保留。
- 不把检索索引当作事实来源；索引必须可以从知识数据重建。
- P10 作为独立的公共基础设施并行推进，不纳入 P8/P9 的串行依赖链。
- P10 对外提供 Schema Snapshot、Proposal、Validation、Migration 和 Audit 能力；业务模块只依赖端口，不依赖 P10 内部实现。
- P7 回写可调用 P10 的 Schema 校验/迁移端口，但 P10 不依赖 P7，也不负责知识业务写入。
- 当前 SQLite Feature Store 与现有 SQLite 主数据文件共用路径，作为本阶段的检索数据源；后续仍可切换为 Gel 投影。
- P8 第一批先交付 FTS5/BM25、项目范围过滤、一跳关系扩展和 Citation 证据返回；向量和复杂重排后续接入。
- P10 第一批先交付 Schema Snapshot、Proposal、差异校验和 SQLite 持久化；Gel Migration Executor 尚未实现。
- `/v1/retrieval/index` 改为提交 `retrieval.index` Job，由 API 内置 Worker 或独立 Worker 执行重建。
- 向量语义召回先通过 `EmbeddingProvider` / `SemanticRetriever` 端口解耦，SQLite 小规模 brute-force 和具体模型 Provider 后续接入。

## Errors Encountered
- 首次运行态路由检查直接读取了 FastAPI `_IncludedRouter.path`，脚本报属性不存在；改用 OpenAPI 路径检查后确认 `/v1/retrieval/search` 与 `/v1/retrieval/index` 已注册。

## Status
**Currently in Phase 4** - 已完成 `retrieval.index` 异步任务接入和向量召回端口设计；下一步是 embedding 持久化、SQLite 语义召回和 RRF 混合融合。
