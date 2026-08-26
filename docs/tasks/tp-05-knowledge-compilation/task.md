# TP-05 知识编译

## 目标

使用 LLMWiki 方法将 ContentBlock 编译为知识候选和 OKF 表达。

## 负责范围

- Prompt 版本管理；
- Concept、Claim、Relation、Citation 候选；
- 关系方向和类型识别；
- OKF v0.2 与 PersonLogy 扩展输出；
- 模型、Prompt 和任务追踪。

## 不负责

- 最终可信度判定；
- 直接写入正式知识；
- Schema Migration 执行。

## 验收

- Given 可解析 ContentBlock
- When 执行编译任务
- Then 系统生成带来源的知识候选

- Given LLM 返回非法结构
- When 编译结果校验
- Then 候选进入失败或待修订状态，不得发布

