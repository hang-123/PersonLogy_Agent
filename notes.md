# Notes: P5 PDF-first integration

## Sources

### Local repository
- P3 已提供 PDF 上传、SourceVersion、ContentBlock、SQLite 和本地文件存储。
- P5 原先只有领域模型和空的 compilation 模块。

## Synthesized Findings

### Current implementation
- 新增 `KnowledgeCompiler` Port、`DocumentHeuristicCompiler` 和 `CompilationService`。
- PDF 解析成功后幂等创建 `knowledge.compile` 任务。
- 编译任务校验候选的来源块、节点端点和 Citation 关系，再写入 SQLite。
- 生成 OKF v0.2 JSON；候选保持 `candidate`，不直接发布。
- Citation、Claim、Relation 增加 metadata，保留 Prompt、模型、任务和生成时间。

### Integration decisions
- GEL 暂不接入当前运行时；SQLite + 本地文件是当前可运行替身。
- 未来 LLM 只需实现 `KnowledgeCompiler` Port，应用层不绑定模型供应商。
- OKF Bundle 和原始 PDF 共用 `ObjectStorage` Port，未来可换 MinIO/S3。
