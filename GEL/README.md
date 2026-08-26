# Gel 数据层

`dbschema/` 是唯一的业务 Schema 来源，`seed.edgeql` 只负责初始化关系类型。Schema 变更必须通过 Gel migration 生成、审阅和执行，不允许由普通导入任务自动建表或删表。

本机安装 Gel CLI 后，在本目录执行：

```text
gel project init --server-version 7.1
gel migration create
gel migrate
gel query -f seed.edgeql
```

当前仓库只提交 Schema 和种子脚本；没有绑定开发机实例或提交运行时数据库数据。
