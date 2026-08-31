# Task Plan: P6 数据治理与审核

## Goal

在 P5 产生候选知识后，建立可重复、可追溯、不可绕过的治理闸门：结构合法、来源有效、重复可标记、冲突不覆盖、人工审核可审计，只有通过审核的结果才允许进入 P8 正式回写。

## Phases

- [ ] Phase 1: 冻结候选/正式对象边界和治理结果模型
- [ ] Phase 2: 实现结构、来源和关系规则校验
- [ ] Phase 3: 实现精确去重、版本去重和冲突检测
- [ ] Phase 4: 实现 ReviewTask、审核命令和审核 API
- [ ] Phase 5: 接入 `knowledge.governance` Worker 任务和幂等重跑
- [ ] Phase 6: SQLite 验收、回归测试和 P6 交付文档

## Decisions Made

- GEL 尚未接通期间，P6 先基于 SQLite 落地，Repository/UoW 继续保持可替换，后续再接 GEL。
- 治理是 P5 和 P8 之间的阻断层；P5 只能产生 candidate，治理通过也不等于直接回写正式知识。
- 精确重复可以自动标记；语义相似和冲突只生成治理结果与审核任务，不自动覆盖或合并事实。
- 每个 Claim 至少一条 Citation；每个 Relation 必须有合法端点、关系类型和证据。

## Status

**Currently in Phase 1** - 已完成 P5/P6 边界盘点，下一步先冻结候选隔离、治理结果和审核状态模型。
