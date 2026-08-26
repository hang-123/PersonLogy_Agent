# 知识回写

## 功能边界

将治理通过的知识对象通过受控工具写入 Gel，并保存 OKF 和审计结果。

## 验收标准

### 受控写入

- Given Claim、Relation 和 Citation 已通过治理
- When Write Tool 接收结构化写入请求
- Then 工具执行权限检查、Schema 校验和 Gel 事务写入

### 事务一致

- Given 一次写入包含多个相互依赖的知识对象
- When 任一对象写入失败
- Then 整个事务回滚，不产生部分正式知识

### 幂等写入

- Given 相同候选对象已经成功写入
- When Write Tool 再次接收相同请求
- Then 系统不产生重复对象，并返回已有对象 ID

### OKF 导出

- Given 知识事务写入成功
- When 回写流程完成
- Then 系统生成或更新对应 OKF 文档，并保留来源、生成和验证元数据

