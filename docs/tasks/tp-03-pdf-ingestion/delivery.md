# TP-03 交付记录

当前文件用于记录本次 TP-03 本地 PDF 导入实现的范围、验证结果和已知边界。

## Status

## 已完成

- `POST /v1/pdfs/upload` multipart 上传接口。
- PDF 扩展名、MIME、文件头、大小和可解析性校验。
- 本地原始文件存储，使用安全的对象 key 和原子写入。
- SQLite 中保存 Project、Source、SourceVersion、hash、object key 和 Job。
- 同一项目按内容 hash 复用 SourceVersion，重复上传不会新增版本。
- Worker 的 `pdf.parse` 任务使用 pdfplumber 生成页、段落和表格 ContentBlock，并保留定位信息。
- 测试覆盖成功导入、文件持久化、版本复用、损坏/超限拒绝和 API 返回。

## 已知边界

- 当前本地存储不是 MinIO/S3；替换存储适配器即可迁移。
- 扫描版 PDF 暂不做 OCR；无可提取文本/表格的 PDF 会在解析任务阶段失败。
- 同一文件只保证同一项目内按 hash 复用，不包含语义去重和知识抽取。
