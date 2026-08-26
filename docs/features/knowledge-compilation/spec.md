# 知识编译

## 功能边界

将 ContentBlock 编译为 LLMWiki 风格的 Concept、Claim、Relation、Citation 候选，并生成 OKF 表达。

## 验收标准

### 候选知识生成

- Given 解析成功的 ContentBlock
- When Worker 执行知识编译任务
- Then 系统生成结构化 Concept、Claim、Relation 和 Citation 候选

### Claim 来源绑定

- Given 编译任务生成 Claim
- When 系统保存候选结果
- Then 每个 Claim 至少关联一个具体 ContentBlock 证据

### Relation 语义

- Given 编译任务生成知识关系
- When 系统保存 Relation 候选
- Then 关系包含类型、方向、起点、终点、置信度和来源信息

### Prompt 可追踪

- Given 任意知识候选由 LLM 生成
- When 系统写入候选记录
- Then 记录 Prompt 版本、模型名称、生成时间和任务 ID

### 编译失败

- Given LLM 调用失败、输出格式非法或无法定位来源
- When Worker 处理编译任务
- Then 任务进入失败或待修订状态，不发布为正式知识

