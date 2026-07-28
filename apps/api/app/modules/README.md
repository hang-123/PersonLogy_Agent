# Domain modules

后端按 PRD 保持模块化单体边界：

- `ingestion`：来源接入与原文保存
- `knowledge`：对象、关系、版本
- `review`：候选审核与发布
- `reasoning`：Claim、Decision、追溯、影响分析
- `query`：搜索、拓扑与 Context Pack
- `projection`：PostgreSQL → Neo4j 投影、校验、重建
- `experiment`：CTE/Cypher 对照与基准
- `integration`：REST、MCP、LLM、文件适配
- `audit`：审计、归档与恢复

模块只能通过 application ports 协作，领域代码不得导入 FastAPI 或具体数据库驱动。
