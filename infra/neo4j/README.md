# Neo4j projection

Neo4j 只保存 PostgreSQL Published 知识的可重建查询投影。

- 当前 Mapping：`v1-draft`，M0 评审前不得用于生产迁移。
- 业务服务不暴露 Neo4j 通用写接口。
- 所有节点、边使用 PostgreSQL 稳定 ID；名称不得作为主键。
- 敏感 Evidence 只投影必要元数据与定位，不复制完整原文。
- 正式发布失败与图投影失败相互隔离；图查询不可用时回退 PostgreSQL。
