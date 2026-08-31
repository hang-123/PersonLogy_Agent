# P5 首版交付说明

## 范围

本次 P5 以 PDF 为首个数据源，跑通：

```text
PDF 上传 → PDF 解析 → ContentBlock → knowledge.compile
→ Concept / Claim / Relation / Citation 候选 → OKF v0.2 Bundle
```

候选默认保持 `candidate`，不会绕过后续治理直接发布。

## 已交付

- `KnowledgeCompiler` Port：隔离后续 LLM Provider。
- `DocumentHeuristicCompiler`：本地、可重复、无需 GEL/外部模型即可生成候选。
- `CompilationService`：校验候选来源关系、写入 SQLite、生成 OKF 文件。
- PDF Worker 链路：`pdf.parse` 成功后幂等提交 `knowledge.compile`。
- P5 元数据：Prompt 版本、模型名、任务 ID、生成时间。
- SQLite 兼容升级：为 Citation、Claim、Relation 补充 metadata 字段。

## 本地验证

在 `apps/api` 目录执行：

```text
uv run ruff check app tests ../../packages/personlogy_core/src/personlogy
uv run pytest
uv run mypy app ../../packages/personlogy_core/src/personlogy
uv run ruff check ../../apps/worker/src
```

当前结果：19 项测试通过，类型检查通过，API 与独立 Worker 静态检查通过。

## 输出位置

OKF 文件写入 `PKS_PDF_STORAGE_ROOT` 下的：

```text
projects/{project_id}/compilations/{compile_job_id}.okf.json
```

## 使用方式

待实现。

## 后续 GEL 接入

GEL 恢复后，替换 `UnitOfWork` / Repository / Queue 和 `ObjectStorage` 装配即可；P5 的编译器、任务编排和 API/Worker 业务链路不需要绑定 GEL。若接入真实 LLM，只需新增 `KnowledgeCompiler` 实现并在组合根替换 `DocumentHeuristicCompiler`。
