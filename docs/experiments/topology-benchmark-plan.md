# Topology 对照实验计划

## 固定变量

- 数据集：真实小样本 + 固定随机种子的 ≥1,000 对象、≥5,000 关系合成集
- 环境：记录 CPU、内存、PostgreSQL/Neo4j 版本、索引与 Mapping Version
- 查询：固定起点、关系类型、最大深度、节点上限和正确性基线
- 轮次：预热与正式结果分开；正式执行每类/每后端不少于 30 次

## 必做查询

1. Decision/Claim → Evidence → SourceDocument 反向追溯
2. Skill → Position 与 Experience 多跳能力匹配
3. 上游 JDVersion/Evidence/Claim 变化影响范围
4. 以 Position 为中心的受限 Context 子图导出

前两类中的“反向追溯”和“影响分析”必须同时实现递归 CTE 与 Cypher。

## 输出

记录正确性、查询表达长度、环路/去重复杂度、P50、P95、最大值、返回规模、模型变更成本、同步/恢复成本，并分别标注测量结果、观察与判断。结论允许长期保留、限定保留或移除 Neo4j。
