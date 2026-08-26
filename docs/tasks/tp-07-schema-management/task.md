# TP-07 Schema 管理

## 目标

建立 LLM 生成 Gel Schema/Migration、校验、审批和执行的管理面流程。

## 负责范围

- SchemaChangeProposal；
- 当前 Schema 读取；
- Gel Schema/EdgeQL Migration 生成；
- 差异检查、沙盒测试和影响评估；
- Migration Tool 执行和审计。

## 不负责

- 普通资料导入；
- 每批数据动态建表；
- 知识候选生成。

## 验收

- Given Schema 不匹配
- When 管理员请求变更建议
- Then 系统生成可审阅的 Migration 提案

- Given 提案未审批
- When 普通任务请求执行
- Then Migration 不得执行

