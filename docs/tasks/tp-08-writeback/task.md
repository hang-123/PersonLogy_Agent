# TP-08 受控回写

## 目标

把治理通过的知识以事务方式写入 Gel，并保存原文和 OKF 结果。

## 负责范围

- Write Tool；
- Domain Command 到 EdgeQL 的编译；
- Gel Unit of Work；
- MinIO 原文和 OKF 导出；
- 审计事件。

## 不负责

- 任意 SQL/EdgeQL 执行接口；
- 未治理候选的正式发布；
- 搜索排序。

## 验收

- Given 治理通过的 Claim、Relation 和 Citation
- When 调用 Write Tool
- Then 系统完成权限、Schema 和事务校验后写入 Gel

- Given 一个对象写入失败
- When 多对象事务提交
- Then 整个事务回滚

