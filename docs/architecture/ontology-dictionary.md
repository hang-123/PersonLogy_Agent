# Ontology 数据字典（M0 待评审）

## 评审要求

每种对象必须定义稳定 ID、规范名称、扩展属性 Schema、状态机、归档规则、查重线索和敏感级别。首批对象：Company、Department、Position、JDVersion、Skill、Experience、SourceDocument、Evidence、Claim、Decision。

## 交付检查

- [ ] 字段类型、必填性、默认值与索引
- [ ] Candidate/Published/Archived 等状态转换
- [ ] 新版本追加与 `supersedes` 规则
- [ ] Public/Private/Sensitive 数据分级
- [ ] PostgreSQL 字段与 Neo4j 属性白名单
