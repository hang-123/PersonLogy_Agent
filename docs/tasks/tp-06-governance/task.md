# TP-06 数据治理与审核

## 目标

保证知识结构、来源、重复、冲突和审核状态满足发布要求。

## 负责范围

- Schema 和规则校验；
- 精确、版本和语义去重；
- Claim/Relation 来源验证；
- 冲突检测；
- ReviewTask 和人工确认。

## 不负责

- 原始文件解析；
- 数据库迁移；
- 检索排序。

## 验收

- Given Claim 没有 Citation
- When 执行治理
- Then Claim 不得进入正式写回

- Given 两个 Claim 互相冲突
- When 执行治理
- Then 系统保留双方并创建冲突标记

- Given 用户确认候选
- When 提交审核结果
- Then 系统记录审核者、时间和版本变化

