# TP-03 PDF 导入

## 目标

完成 PDF 上传、格式校验、原文保存、版本建立和结构化解析。

## 负责范围

- PDF 接收和 MIME 校验；
- MinIO 原文保存；
- Source/SourceVersion 创建；
- 页码、标题、段落和表格解析；
- ContentBlock 输出。

当前落地顺序：上传接口同步完成校验、hash 去重、原文落盘、SourceVersion 和解析任务
创建；Worker 异步完成 PDF 解析并写入 ContentBlock。GEL 未接通期间使用 SQLite + 本地
文件存储，数据库不保存 PDF 二进制。

## 不负责

- 知识点和关系抽取；
- 语义去重；
- 最终知识发布。

## 验收

- Given 有效 PDF
- When 用户上传
- Then 原文件、哈希、版本和解析任务均被创建

- Given 解析成功
- When 用户查看 ContentBlock
- Then 每个片段可定位到页码和段落
