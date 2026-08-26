# TP-01 领域模型与 Gel Schema

## 目标

建立稳定的 Project、Source、Version、ContentBlock、KnowledgeNode、Claim、Relation、Citation 和审核对象。

## 负责范围

- Domain 实体和值对象；
- RelationType 和关系约束；
- Gel Schema、迁移和种子数据；
- Repository 和 Unit of Work 接口。

## 不负责

- 具体 PDF 解析；
- LLM Prompt；
- 检索排序。

## 交付物

- 初版领域模型；
- Gel Schema/Migration；
- 关系类型初始集合；
- Schema 约束测试。

## 验收

- Given 合法的 Claim 和 Citation
- When 执行事务写入
- Then 数据可以保存并保持来源关联

- Given 没有来源的 Claim
- When 执行 Schema 或领域校验
- Then 写入被拒绝

