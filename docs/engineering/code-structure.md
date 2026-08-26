# 代码目录与重构约定

## 1. 目标目录

```text
apps/
├── api/                         # HTTP API 入口
└── worker/                      # 异步任务入口

packages/personlogy_core/
└── src/personlogy/
    ├── domain/                  # 领域对象和业务规则
    ├── application/             # 用例和流程编排
    ├── ports/                   # 外部能力接口
    ├── adapters/                # Gel、MinIO、LLM、PDF 等实现
    ├── contracts/               # API 和 Tool DTO
    └── shared/                  # 错误、ID、时间、日志

infra/
├── gel/schema/
├── gel/migrations/
├── minio/
├── docker/
└── config/

prompts/                         # 版本化 Prompt
tests/                           # unit / integration / e2e
docs/                            # Spec、架构、图稿和计划
scripts/                         # 初始化、迁移、验证脚本
```

## 2. 目录职责

`domain` 不依赖任何框架和外部服务；`application` 只编排用例；`ports` 定义接口；`adapters` 实现外部服务；`apps` 负责入口和协议转换。

## 3. 模块命名

代码模块使用业务能力命名：`ingestion`、`compilation`、`governance`、`schema_management`、`writeback`、`indexing`、`retrieval`。

不要使用含义过宽的 `utils`、`service1`、`common_service` 作为业务模块名。

## 4. 重构顺序

1. 建立当前代码清单和测试基线；
2. 抽取 Source、SourceVersion、KnowledgeNode、Relation 等领域模型；
3. 把现有 Gel 访问包到 Repository 和 Adapter；
4. 建立 PDF 单链路；
5. 建立对话导入链路；
6. 加入治理和人工审核；
7. 加入索引与混合检索；
8. 最后迁移前端和旧入口。

每一步都应保持旧功能可运行，不进行一次性大规模搬迁。

