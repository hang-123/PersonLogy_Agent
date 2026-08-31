# Task Plan: TP-03 本地 PDF 导入链路

## Goal

在 GEL 尚未接通的情况下，完成 TP-03 的本地可运行闭环：上传校验、原文落盘、哈希去重、SourceVersion、PDF 解析、ContentBlock 和解析任务持久化。

## Phases

- [x] Phase 1: 盘点现有 Source、Job、SQLite 和 API 基础
- [x] Phase 2: 设计本地文件存储、PDF 解析和去重边界
- [x] Phase 3: 实现 PDF 领域持久化与应用服务
- [x] Phase 4: 接入上传接口和任务链路
- [x] Phase 5: 增加测试并完成静态检查
- [x] Phase 6: 更新交付记录

## Key Questions

1. 文件 hash 去重和 SourceVersion 复用是否需要数据库？
2. GEL 不可用时，原始 PDF 是否可以先用本地文件存储？
3. 解析结果如何保留页码、段落顺序和表格定位？

## Decisions Made

- 数据库保存 Source、SourceVersion、ContentBlock、hash、object_key、解析任务状态；原始 PDF 本体先使用受控本地目录保存。
- 文件内容 hash 是数据库去重和版本复用的依据；同一 project + hash 复用已有 SourceVersion。
- PDF 解析在 Worker 中执行，上传接口只负责校验、保存、建版本和创建任务。

## Errors Encountered

- Worker 项目未声明 ruff/mypy 开发依赖；使用 API 项目环境对 Worker 源码执行同等检查，结果通过。

## Status

**Completed** - TP-03 本地 PDF 上传、持久化、解析和 ContentBlock 任务链路已落地并通过验证。
