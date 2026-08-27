# PDF 数据导入

## 功能边界

接收 PDF、校验格式、保存原始文件、创建来源版本并生成异步解析任务。

存储后端按配置切换：默认 SQLite（`PKS_STORAGE_BACKEND=sqlite`）保存来源、版本、hash、
对象 key、ContentBlock 和任务状态；配置 `PKS_STORAGE_BACKEND=gel` 时由 Gel 适配器
（`personlogy.adapters.gel`）承载同样的端口。PDF 二进制一律先保存到
`PKS_PDF_STORAGE_ROOT` 指定的本地目录，后续可替换为 MinIO/S3 适配器。

上传接口：`POST /v1/pdfs/upload`（multipart/form-data，字段为
`project_name`、`project_slug`、`title` 和 `file`）。

## 验收标准

### 有效 PDF

- Given 用户拥有目标项目的写入权限且上传有效 PDF
- When 调用 PDF 上传接口
- Then 系统保存原始文件，创建 Source、SourceVersion 和 IngestionJob，并返回任务 ID

### 格式校验失败

- Given 上传文件不是合法 PDF、文件损坏或超过大小限制
- When 调用 PDF 上传接口
- Then 系统拒绝文件，返回明确原因，且不创建可用知识数据

### 重复上传

- Given 相同项目中已经存在内容哈希相同的 PDF 版本
- When 用户再次上传该文件
- Then 系统复用或标记已有版本，不产生重复 SourceVersion

### 原文定位

- Given PDF 解析任务成功
- When 系统生成 ContentBlock
- Then 每个可引用片段保留页码、段落顺序和内容哈希
