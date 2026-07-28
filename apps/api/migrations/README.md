# Database migrations

M0 完成 Ontology 与关系字典评审后，使用 Alembic 创建首个核心 Schema 迁移。迁移必须支持空库重复执行，并避免在同一版本中直接执行不可逆的破坏性字段删除。
