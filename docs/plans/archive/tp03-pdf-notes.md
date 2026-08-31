# Notes: TP-03 本地 PDF 导入

## Existing Foundation

- `SourceVersion` 已包含 `source_id`、`version`、`content_hash`、`object_key`。
- `ContentBlock` 已包含 `source_version_id`、`ordinal`、`content`、`content_hash`、`locator`。
- SQLite 已有 `source_version` 和 `content_block` 表，并对同一 Source 的 hash 和 version 建立唯一约束。
- Job/UoW/SQLite queue 已可持久化异步任务。

## Required Additions

- PDF 上传 API 和 multipart 文件接收。
- PDF MIME、扩展名、文件头、损坏、大小校验。
- 本地文件存储端口，路径必须限制在配置的 storage root 内。
- PDF 解析器，至少输出页级和段落级 ContentBlock，并为表格保留 locator。
- Source/SourceVersion 的查询与 hash 复用服务。
- 针对成功、非法 PDF、超限、重复上传和解析结果的测试。

## Answer to Database Question

需要连接数据库，但不是把 PDF 二进制直接放进数据库。数据库记录 hash、Source、SourceVersion、object_key、解析任务和 ContentBlock；原始文件先放本地目录，未来可把同一存储端口替换成 MinIO/S3。
