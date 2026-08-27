# 数据治理

## 功能边界

负责结构规则、重复检测、语义去重、冲突检测、来源验证、可信度和人工审核。

P6 首版只校验固定知识契约和可解释规则；Gel Schema/Migration 属于 TP-07，正式知识
回写属于 TP-08。机器治理通过后仍进入人工审核，不因结构合法而自动发布。

## 状态流转

```text
candidate → machine_checked → pending_review
pending_review → human_verified / rejected / needs_revision
human_verified → ready_for_writeback
```

## 验收标准

### 结构校验

- Given 知识候选提交治理
- When 系统执行 Schema 和必填字段校验
- Then 非法类型、缺失来源或缺失关系端点的候选不得发布

### 治理记录

- Given P5 生成一批候选
- When 系统执行治理
- Then 系统生成带规则版本、任务 ID、候选 ID 和时间的 GovernanceRun
- And 每个问题都有 code、severity、message 和候选来源

### 重复检测

- Given 两个候选具有相同内容、来源版本或稳定标识
- When 系统执行规则去重
- Then 系统标记重复对象并保留来源和版本信息

### 语义冲突

- Given 两个 Claim 对同一主题给出相反结论
- When 系统执行语义治理
- Then 系统创建冲突标记，不静默覆盖任一 Claim

### 重复与冲突保留

- Given 候选之间存在精确重复或潜在冲突
- When 系统执行治理
- Then 系统分别生成 DuplicateGroup 或 ConflictRecord，并保留所有原候选

### 人工审核

- Given 候选知识需要人工确认
- When 用户执行确认、驳回或修改
- Then 系统记录审核者、时间、修改内容和审核前后版本

### 审核并发

- Given ReviewTask 已被其他审核操作更新
- When 用户使用旧版本提交审核
- Then 系统拒绝该操作，不覆盖已有审核结果

### 状态隔离

- Given 知识尚未人工确认
- When AI 或用户检索知识
- Then 结果明确显示 candidate、machine_checked 或 human_verified 状态

### 当前首版边界

- 精确重复覆盖同批节点标题、Claim 文本和 Relation 端点。
- 冲突检测首版只做同主题 Claim 的保守否定词配对。
- 向量/LLM 语义去重通过后续 Port 接入，不在本版伪装为已完成。
