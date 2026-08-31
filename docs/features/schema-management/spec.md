# Schema 管理

## 功能边界

管理 Gel Schema、EdgeQL Migration 的生成、校验、审批和执行。该功能属于管理面。

## 验收标准

### 生成变更提案

- Given 当前知识对象无法匹配现有 Schema
- When 管理员请求 Schema 变更建议
- Then LLM 生成可审阅的 Gel Schema/Migration 提案，并记录生成模型和版本

### 变更校验

- Given 存在一份 Schema/Migration 提案
- When 系统执行差异检查和沙盒测试
- Then 系统返回语法、约束、兼容性和迁移影响结果

### 审批执行

- Given 提案通过校验且管理员已审批
- When 调用 Migration Tool
- Then 系统执行迁移、更新 Schema 版本并记录完整审计事件

当前实现：`draft → validated → approved → applied`；未进入 `approved` 的提案不能执行，
执行前校验当前版本仍等于 `base_version`，执行后产生新的不可变 Snapshot。

### 回滚

- Given 一份已执行的 Schema Proposal 且当前版本仍是该提案的目标版本
- When 管理员请求回滚
- Then 系统调用回滚执行器，以更高版本生成原 base definition，不覆盖历史 Snapshot，并记录 `rolled_back` 审计事件
- Given 当前已经存在更高版本
- When 请求回滚旧提案
- Then 系统拒绝回滚，避免越过后续 Schema 变更

### 未审批禁止执行

- Given Schema/Migration 提案未通过审批
- When 任意普通任务请求执行该提案
- Then 系统拒绝执行且不改变数据库结构

### 运行时隔离

- Given 用户导入一批新的 PDF 或对话
- When 系统执行知识编译和写回
- Then 系统使用当前 Schema 写入数据，不自动建表或删表
