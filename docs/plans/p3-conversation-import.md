# P3 对话导入落地说明

## 已完成

已在 GEL 不可用期间打通本地对话导入闭环：

```text
标准化 JSON
  → 项目/Conversation/Message 本地持久化
  → 消息级幂等与冲突校验
  → conversation.import Job 入队
  → Worker 后续处理
```

接口：

```text
POST /v1/conversations/import
```

请求包含项目、会话、消息角色、顺序、时间、父消息和附件引用。首次导入创建 Source、Conversation 和 Message；重复消息不会重复写入；同一消息 ID 内容发生变化时请求失败。

## 当前边界

- 已保存原始对话结构和来源关系；
- 已创建异步导入任务；
- 暂不进行知识抽取、正式发布或向量化；
- 不依赖 GEL，后续可由 GEL Repository 替换 SQLite Repository。

## 下一步

为 `conversation.import` 注册实际处理器，补充消息分块、Citation 生成和知识编译任务；PDF 导入沿用同一套 Source/Job 边界。
