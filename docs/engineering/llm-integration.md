# LLM / Embedding / Rerank 接入指南（OpenAI 兼容）

> 状态：适配器骨架已落地（`packages/personlogy_core/src/personlogy/adapters/llm_openai.py`），
> 配置项与装配已接好；**知识编译已可切换真实 LLM**，向量检索与重排的 provider 实例已装配、
> 等待混合检索 reader 接入消费。

## 1. 快速开始：启用 LLM 知识编译

在 `.env`（复制自 `.env.example`）中设置：

```dotenv
PKS_LLM_PROVIDER=openai_compatible
PKS_LLM_BASE_URL=https://api.deepseek.com/v1
PKS_LLM_API_KEY=sk-你的key
PKS_LLM_MODEL=deepseek-chat
```

重启 API + Worker 后，新的 PDF/对话导入在 `knowledge.compile` 阶段会调用真实 LLM
生成候选知识（替代原来的本地启发式 `DocumentHeuristicCompiler`）。

常用供应商示例：

| 供应商 | PKS_LLM_BASE_URL | PKS_LLM_MODEL |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 本地 Ollama | `http://localhost:11434/v1` | `qwen2.5:7b`（无需 API key） |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |

> 任何 OpenAI 兼容的 `/chat/completions` 网关都可接入；`PKS_LLM_API_KEY` 留空时
> 不发送 Authorization 头（适用于无鉴权的本地服务）。

## 2. 可用的配置项（全部可选）

| 配置 | 用途 | 缺省 |
|---|---|---|
| `PKS_LLM_PROVIDER` | `none`（启发式）\| `openai_compatible` | `none` |
| `PKS_LLM_BASE_URL` / `PKS_LLM_API_KEY` / `PKS_LLM_MODEL` | 知识编译模型 | 空 |
| `PKS_EMBEDDING_PROVIDER` | `none` \| `openai_compatible` | `none` |
| `PKS_EMBEDDING_BASE_URL` / `PKS_EMBEDDING_API_KEY` / `PKS_EMBEDDING_MODEL` | 向量模型 | 空 |
| `PKS_RERANK_PROVIDER` | `none` \| `openai_compatible` | `none` |
| `PKS_RERANK_BASE_URL` / `PKS_RERANK_API_KEY` / `PKS_RERANK_MODEL` | 重排模型 | 空 |

## 3. 适配器行为说明

### 3.1 知识编译（`OpenAICompatCompiler`）

- 输入：ContentBlock 列表；输出：`KnowledgeNode` / `Claim` / `Relation` / `Citation` 候选。
- 系统提示词要求模型只输出 JSON；解析失败抛 `DomainValidationError`（任务失败、不发布）。
- `quote` 必须能在输入块中匹配到；找不到引用的声明/关系会被丢弃（保守策略）。
- 关系类型限定为 `INITIAL_RELATION_TYPES`（is_a/part_of/depends_on/supports/contradicts/related_to/derived_from）。
- 候选状态保持 `candidate`，后续治理（P6）统一处理 `machine_checked`/审核。

### 3.2 向量 Embedding（`OpenAICompatEmbeddingProvider`）

- 调用 `POST {base_url}/embeddings`，请求体 `{"model": ..., "input": [...]}`。
- 当前 provider 实例已在 `runtime.py` 装配（`runtime.embedding_provider`），
  **尚未接入检索链路**——混合检索 reader（BM25 + 向量）是下一步工作。

### 3.3 重排（`OpenAICompatReranker`）

- 调用 `POST {base_url}/rerank`（Cohere 兼容：`{"model", "query", "documents"}`）。
- 已装配（`runtime.reranker`），同样等待混合检索 reader 消费。

## 4. 验证方式

```bash
# 1) 确认装配生效（模型名应显示你的模型）
PKS_LLM_PROVIDER=openai_compatible PKS_LLM_BASE_URL=... PKS_LLM_MODEL=... \
  python -c "from app import runtime; print(runtime.compilation_service._compiler.model_name)"

# 2) 单元测试（mock HTTP，不消耗 token）
pytest apps/api/tests/test_llm_adapters.py -v

# 3) 端到端：上传一个 PDF → 观察任务队列中 knowledge.compile 的 model_name
curl -F "project_name=测试" -F "project_slug=llm-test" -F "title=示例" \
     -F "file=@sample.pdf" http://localhost:8000/v1/pdfs/upload
```

## 5. 注意事项

- **API key 不要提交到 git**：只在 `.env`（已被 .gitignore 忽略）中配置。
- 编译是**同步**调用（`KnowledgeCompiler.compile`），worker 内串行执行；长文档注意
  超时（`timeout_seconds` 默认 60s）与 token 上限（默认 `max_tokens=8192`）。
- 未配置 LLM 时系统保持原启发式行为，不影响现有链路。
- 向量/重排 provider 目前只装配不消费；接入混合检索时在 `runtime.py` 中组合
  `SQLiteRetrievalReader` + `SemanticRetriever` + `Reranker` 即可。
