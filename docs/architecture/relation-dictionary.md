# 关系字典（M0 待评审）

每种关系必须明确：关系名、起点类型、终点类型、方向、基数、认识类型、Evidence/上游依据要求、有效期、是否参与追溯、是否允许成环，以及 Neo4j 映射名称。

P0 首批关系：`has_department`、`offers`、`has_version`、`supersedes`、`requires`、`prefers`、`demonstrates`、`contains_evidence`、`extracted_from`、`supports`、`refutes`、`about`、`derived_from`、`conflicts_with`、`targets`、`based_on`。

`related_to` 只能临时存在于 Candidate，不能进入 P0 关键正式链路。`derived_from` 与 `based_on` 发布前必须执行无环校验。
