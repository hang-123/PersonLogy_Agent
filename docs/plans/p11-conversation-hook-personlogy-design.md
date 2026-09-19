# 对话 Hook 与 PersonLogy 增量知识管理设计

状态：设计定稿（v0.1）  
范围：Codex 对话 Hook、其他对话工具适配器、本地可靠队列、PersonLogy 增量接收与个人知识治理

## 1. 设计结论

本方案采用：

> 对话工具 Hook 负责捕获和轻量筛选；本地 SQLite 负责保存证据事件与投递状态；PersonLogy 负责幂等接收、知识抽取、治理审核和数字分身视图。

JSON 不是本地持久化技术选型。JSON 只作为事件载荷格式，嵌入 SQLite 的 payload_json 字段中，用于容纳不同对话工具的差异化内容。

本方案明确采用以下可靠性语义：

- 捕获链路：尽量做到持久化前不丢失；无法证明捕获完整时，记录不完整状态并支持补采。
- 网络投递：至少一次（at-least-once）。网络超时、进程崩溃后允许重发。
- PersonLogy 接收效果：通过事件身份和数据库唯一约束实现幂等，重复投递不得产生重复的原始消息或重复的处理任务。
- 知识更新：不以“收到较晚”或“模型置信度较高”为理由自动覆盖历史陈述；变化通过新陈述、时间关系和人工治理表达。

不承诺跨操作系统、跨设备、跨工具的绝对 exactly-once 捕获。系统通过稳定来源身份、事务、回执、补采和冲突记录，把丢失与重复风险变成可检测、可恢复的状态。

## 2. 背景与目标

PersonLogy 的目标是建立用户个人的长期数字分身基础。对话中可能出现以下与个人知识有关的信息：

- 当前目标、项目计划和执行优先级；
- 未来想法、探索方向和暂时性的可能性；
- 明确表达的价值观、判断原则和取舍逻辑；
- 偏好、习惯、边界和不希望发生的事情；
- 决策、决策背景、约束条件和后续复盘；
- 个人经历、技能、知识积累和学习方式；
- 工作方式、沟通方式和对 Agent 的协作偏好；
- 兴趣、长期关注主题、关系与责任；
- 个人状态、阶段性限制以及观点随时间发生的变化。

目标不是把所有对话复制到 PersonLogy，也不是把每一句话都自动解释成稳定人格。系统需要保留足够的原始证据，让后续抽取、审核和纠错可追溯。

非目标包括：

- 在 Hook 中调用大模型完成知识抽取；
- 在本地插件中直接生成最终人格结论；
- 把一般技术问答、角色扮演、辩论假设自动当成用户本人的观点；
- 在没有证据的情况下推断敏感属性、政治或宗教立场、人格标签等。

## 3. 总体架构

    ┌────────────────────┐
    │ Codex / 其他对话工具 │
    └─────────┬──────────┘
              │ Hook / 来源适配器
              ▼
    ┌────────────────────┐
    │ 捕获模块            │ 规则匹配、轻量归一化、来源定位
    └─────────┬──────────┘
              │ 本地短事务
              ▼
    ┌──────────────────────────────────┐
    │ 本地 SQLite 事件库                  │
    │ capture_events / deliveries       │
    │ checkpoints / stream_state        │
    └─────────┬────────────────────────┘
              │ 独立发送进程，事务外网络请求
              ▼
    ┌────────────────────┐
    │ PersonLogy 接收端    │ 认证、幂等、原始消息落库
    └─────────┬──────────┘
              │ 同一服务端事务创建后续任务
              ▼
    ┌────────────────────┐
    │ 编译与治理流水线     │ 个人陈述抽取、证据、冲突、审核
    └─────────┬──────────┘
              ▼
    ┌────────────────────┐
    │ 数字分身查询视图     │ 目标、偏好、原则、计划和时间状态
    └────────────────────┘

模块边界如下：

| 模块 | 负责 | 不负责 |
|---|---|---|
| 捕获模块 | 监听 Hook、选择候选、归一化、生成稳定事件身份 | 最终知识判断、网络重试 |
| 本地事件库 | 原始证据、去重、序号、待投递状态、断点和重试 | 判断个人观点真伪 |
| PersonLogy 接收 | 认证、接收幂等、原始对话和来源映射 | 假设客户端一定只发一次 |
| 编译与治理 | 结构化个人陈述、引用、时间、冲突、审核 | 把未经确认的推断当成事实 |
| 数字分身视图 | 聚合当前有效信息，供查询和 Agent 使用 | 取代历史证据和审计记录 |

## 4. 捕获策略

### 4.1 Codex 事件选择

Codex Hook 的首选采集对象是用户提交的提示词。它最直接地表达用户的目标、计划、判断和偏好。

- UserPromptSubmit：主事件。捕获用户实际提交的 prompt，并执行本地规则筛选。
- Stop：可选上下文事件。保存最终助手回复的摘要或引用关系，帮助 PersonLogy 理解用户陈述的上下文，但不把它当作用户事实来源。
- SessionEnd：补采和收尾触发点。用于检查本地游标和可读取的 transcript 是否存在未入队内容。
- transcript：只作为恢复和补采输入，不作为稳定 API 契约。Codex 文档明确提示 transcript 格式可能变化，因此适配器必须版本化解析器并保留不可解析记录。

Hook 命令应尽快完成本地入队后返回。不得在同步 Hook 中直接访问 PersonLogy、调用大模型或等待网络。Codex 的 Hook 还可能在多个配置来源合并后并发触发，因此全局 Hook 和项目 Hook 必须进入同一个本地 Collector，通过唯一约束去重。

### 4.2 其他工具适配

后续接入 ChatGPT、DeepSeek Harness 或其他工具时，每个工具只实现 SourceAdapter，输出统一的内部事件：

    SourceEnvelope
      source_kind
      source_account
      source_scope
      conversation_key
      message_key
      revision
      role
      content
      occurred_at
      parent_key
      metadata

适配器必须说明：消息 ID 是否稳定、是否允许编辑、能否读取历史、能否给出连续序号、是否存在多个分支。适配器不能用随机 UUID 代替缺失的来源身份，否则每次重扫都会被当成新消息。

### 4.3 本地规则

规则分为“是否捕获”和“捕获分类”两层。规则版本写入每个事件，以便将来解释某条内容为什么被选中。

推荐的初始分类：

    goal                  当前目标
    plan                  已形成或正在执行的计划
    future_idea           未来想法、探索方向、可能性
    value_or_principle    明确表达的价值判断或原则
    preference            偏好、习惯、边界
    decision              决策及其取舍
    experience_or_skill   经历、能力、学习积累
    work_style            工作或协作方式
    interest              长期兴趣和关注主题
    constraint_or_state   阶段性状态、限制和资源条件
    reflection            复盘、观点变化和自我认识
    agent_preference      希望数字分身如何协作或表达

规则输出的只是候选标签，不是最终语义结论。至少区分以下表达：

- 用户明确谈论自己；
- 用户询问一般知识；
- 用户转述别人或引用资料；
- 用户提出假设、角色扮演或辩论立场；
- 用户让模型给建议，但没有表达自己已经采纳；
- 用户表达暂时想法、承诺、已完成事实或长期偏好。

默认分层：

- 高确定性：明确的个人计划、已做决定、明确偏好、明确自我陈述，自动进入待投递队列。
- 中确定性：可能对数字分身有价值，但语义依赖上下文，进入候选队列或低优先级投递。
- 低确定性：普通技术问答、纯模型输出、无个人归属的信息，默认不投递，但允许用户手动标记或以后重扫。

规则可以设置宽泛，但宽泛只意味着“多保留候选证据”，不能意味着“多做人格推断”。

## 5. 本地持久化选型

### 5.1 结论

本地使用 SQLite 单文件数据库，包含事件载荷、投递状态、采集断点和流状态。SQLite 适合桌面应用和本地文件格式，能够协调多个线程或进程访问；它只有一个数据库写入者，因此写事务必须短小，不能包含网络请求。[SQLite 官方适用场景](https://www.sqlite.org/whentouse.html)

建议配置：

    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = FULL;
    PRAGMA foreign_keys = ON;
    PRAGMA busy_timeout = 3000;

WAL 便于采集进程和发送进程并行读写；synchronous=FULL 用于提高已提交事务在系统崩溃或断电后的耐久性。WAL 不应放在网络文件系统上，并且所有访问进程应在同一台主机上。[SQLite WAL 文档](https://www.sqlite.org/wal.html) [SQLite 同步级别](https://sqlite.org/pragma.html#pragma_synchronous)

JSON 只用于 payload_json：它适合携带不同来源的消息结构、规则命中详情和未来可扩展字段。需要去重、排序、状态过滤或建立唯一约束的字段必须是 SQLite 列。

### 5.2 核心表

#### capture_events

保存一次本地捕获的不可变证据事件。建议字段：

    event_id              全局事件 ID，重试不变
    producer_id           设备/安装实例身份
    source_kind           codex、chatgpt、deepseek 等
    source_scope          账号、项目或全局作用域
    session_key           来源会话身份
    source_item_key       来源消息/事件身份
    source_revision       来源版本，初始为 0
    stream_id             本地投递流
    sequence              流内序号
    occurred_at           来源发生时间，可为空
    captured_at           本地捕获时间
    rule_version          捕获规则版本
    schema_version        载荷版本
    payload_hash          归一化载荷哈希
    payload_json          事件内容和规则命中详情
    created_at

关键唯一约束：

    UNIQUE(source_kind, source_scope, session_key, source_item_key, source_revision)
    UNIQUE(producer_id, stream_id, sequence)
    UNIQUE(event_id)

如果同一来源身份和版本再次出现完全相同的载荷，视为重复捕获；如果载荷不同，视为来源冲突，保留冲突记录并停止自动覆盖。

#### deliveries

保存一个事件向一个 PersonLogy 目标的投递状态：

    event_id
    destination_id
    status                  pending/in_flight/retry_wait/received/blocked
    attempt_count
    next_attempt_at
    lease_owner
    lease_until
    server_receipt_id
    last_error_code
    last_error_summary
    first_sent_at
    received_at
    updated_at

UNIQUE(event_id, destination_id) 保证同一事件不会为同一目标创建两条投递任务。租约过期后可以重新领取 in_flight 任务。

#### capture_checkpoints

保存来源扫描断点：

    source_kind
    source_scope
    source_document_key
    parser_version
    last_byte_offset
    last_ordinal
    last_source_item_key
    coverage_status       complete/incomplete/needs_reconcile
    updated_at

采集断点和发送游标必须分开。断点表示“读到了哪里”，不能表示“已经成功发送到哪里”。

#### stream_state

保存本地流序号和确认进度：

    producer_id
    stream_id
    next_sequence
    last_contiguous_received_sequence
    updated_at

只有新事件真正写入 capture_events 时才分配序号。被规则跳过的内容可以推进来源扫描断点，但不占用投递流序号。

## 6. 增量一致性与幂等协议

### 6.1 事件身份

event_id 解决请求重试问题；来源复合键解决全局 Hook、项目 Hook 和 transcript 重放问题；sequence 解决中间缺口检测问题。不能只使用 session + turn 作为身份，因为一个 turn 可能包含多个消息、多个工具事件或继续生成的分支。

同一来源消息的合法编辑必须生成新的 source_revision。同一来源键、同一版本却对应不同哈希时，PersonLogy 和本地 Collector 都必须报告冲突，不得采用“最后写入覆盖”。

### 6.2 客户端写入流程

    Hook 收到 SourceEnvelope
      -> 规则匹配和轻量归一化
      -> 计算 source_key、revision、payload_hash、event_id
      -> SQLite 短事务：
           检查重复/冲突
           写 capture_events
           写 deliveries(pending)
           更新 capture_checkpoints（如果是扫描）
           分配 sequence（仅新事件）
      -> 事务提交成功后立即返回

如果 SQLite 提交失败，Hook 必须报告捕获失败或留下可重试的临时输入；不能先推进 checkpoint 再写事件。

### 6.3 服务端接收流程

PersonLogy 新增面向事件的接收接口，例如：

    POST /v1/capture/events
    Idempotency-Key: <batch-id>

每个事件至少包含：

    {
      "schema_version": 1,
      "event_id": "...",
      "producer_id": "...",
      "stream_id": "...",
      "sequence": 42,
      "source": {
        "kind": "codex",
        "scope": "global",
        "session_key": "...",
        "item_key": "...",
        "revision": 0
      },
      "rule_version": "...",
      "payload_hash": "...",
      "payload": {}
    }

服务端在一个事务中完成：

1. 根据 event_id 和来源复合键查找已接收事件。
2. 新事件写入接收表和原始对话映射。
3. 创建后续知识编译任务，任务幂等键使用事件或事件批次身份。
4. 提交事务。

响应必须逐事件给出结果：

    accepted          新事件已经持久化
    already_received  事件之前已持久化，可视为成功
    conflict          相同身份但内容不同，需要人工处理
    rejected          不可重试的数据或权限问题
    retryable         服务暂时不可用，客户端保留任务

只有收到 accepted 或 already_received，客户端才能把 deliveries.status 更新为 received。请求超时不等于失败，也不等于成功；应保留任务并重试。

### 6.4 缺失检测与补采

发送端不能简单地把“最高尝试过的 sequence”当作进度。它只推进服务端已经确认的连续区间：

    已确认：41
    收到：43
    结果：43 暂存，但确认游标仍为 41，等待 42

如果事件 42 长期缺失，系统应暴露 gap，而不是静默发送 43 后认为队列完整。对最后一条丢失事件，仅凭序号无法判断，需要来源适配器提供高水位、transcript 扫描或 SessionEnd 收尾信号。

补采流程：

    启动/定时/手动 reconcile
      -> 读取仍可用的来源记录
      -> 使用同一 source_key 和适配器版本重新归一化
      -> 重新进入本地 Collector
      -> 依靠唯一约束消除已存在事件

如果 transcript 不存在、格式无法解析或权限不足，标记 coverage_status=incomplete，并展示给用户。系统不能声称“没有遗漏”。

## 7. PersonLogy 数据模型调整

当前项目已经有 Conversation、ConversationMessage、KnowledgeNode、Claim、Citation 和 Relation。这些模型能支撑一般知识工程，但还不足以表达数字分身中的“谁说的、以什么语气说的、何时有效、后来是否改变”。

### 7.1 保留三层数据

    原始层：Conversation / ConversationMessage / Citation
    陈述层：PersonalAssertion（用户关于自己的可追溯陈述）
    视图层：PersonaSnapshot（按时间和治理状态聚合出的当前画像）

原始层是证据，不随模型重跑而丢失。陈述层是结构化解释，可被修订和标记冲突。视图层是可重建的派生结果，不能成为唯一真相来源。

### 7.2 最小新增/扩展

建议把 PersonalAssertion 作为个人陈述概念，而不是把所有内容直接塞入通用 KnowledgeNode：

    PersonalAssertion
      id
      person_id
      project_id / scope
      assertion_type       goal/plan/future_idea/value/preference/decision/...
      statement
      speaker              user/assistant/quoted_other/unknown
      origin               self_report/source_assertion/derived_inference
      modality             fact/commitment/intention/possibility/question/hypothesis
      adoption_status      expressed/considering/adopted/rejected/unknown
      lifecycle            active/completed/paused/abandoned/superseded
      effective_from/to
      condition_json
      confidence
      verification_status
      supersedes_id
      metadata_json

至少要满足以下语义：

- “我准备做 X”与“我可能做 X”不能落成同一种确定性计划；
- “我现在优先 A，未来再考虑 B”应保留优先级和时间，而不是只保留 A、B 两个关键词；
- 后来改变想法时新增陈述并建立 supersedes 或冲突关系，旧记录保留；
- AI 建议、引用他人观点和用户自述必须有不同的 speaker/origin；
- verification_status 表示证据治理状态，不能代替计划的生命周期。

### 7.3 Person 身份与范围

需要引入明确的 Person 或用户身份映射，不再把 Project 当作个人身份本身。个人知识可以从多个项目、多个工具进入，但必须有明确 scope：

- personal：用户的个人数字分身范围；
- project：仅与项目相关的局部知识；
- private：不允许进入一般 Agent 上下文的内容；
- 其他未来可配置的访问范围。

默认不把一个项目中的个人信息泄漏给所有项目。查询数字分身时按照 scope 和允许用途过滤。

### 7.4 编译和治理调整

现有编译链以 PDF 的 ContentBlock 和通用 Claim 为主，需要增加对 ConversationMessage 的输入路径，并让解析结果能够传递上述字段。仅修改 LLM prompt 不够，还需要同步调整：

- 编译器输出解析；
- Claim/PersonalAssertion 持久化；
- Citation 与原始消息的定位；
- 治理评估和审核任务快照；
- Gel/SQLite schema；
- API 查询和审核界面；
- 重跑和回放的幂等键。

知识编译幂等键建议为：

    compile:{event_id}:{rule_version}:{compiler_version}:{prompt_version}

同一版本重试复用已有结果；编译器或规则版本变化时创建新的分析版本，但不能重复创建原始事件。

## 8. 隐私与安全

对话捕获天然包含高敏感个人信息，必须把“能捕获”与“允许进入数字分身”分开：

- 默认只采集用户消息和必要上下文；助手全文不是默认必须保存的字段。
- 规则命中信息记录原因，但不把完整系统提示、工具参数、密钥或认证头写入事件载荷。
- 本地数据库使用当前用户应用数据目录和操作系统权限保护，不放仓库、不放网络共享目录、不放实时同步目录。
- 支持本地黑名单、敏感字段遮盖和手动删除/撤回；删除动作也应留下不含正文的审计记录。
- PersonLogy 的查询接口按 scope 和用途授权；数字分身摘要不能自动暴露所有原始引用。
- 失败日志只记录事件 ID、错误码和摘要，不重复输出对话正文。

## 9. 分阶段实施

### Phase 0：契约与模型

- 固化 SourceEnvelope、事件身份规则和服务端接收协议。
- 增加 PersonalAssertion 最小模型及身份/scope 设计。
- 确认当前 conversation.import 与新事件接收接口的兼容策略。

### Phase 1：本地 Collector

- 实现 Codex UserPromptSubmit 适配器。
- 实现本地规则、归一化、SQLite schema、唯一约束和事件入队。
- 实现单独 sender、租约、指数退避和可见错误状态。
- 先使用模拟接收端进行崩溃、重复、并发和断电恢复测试。

### Phase 2：PersonLogy 接收端

- 增加 capture inbox 和逐事件幂等响应。
- 将“接收原始事件”和“知识编译完成”分为两个状态。
- 在同一服务端事务内写入原始消息映射并创建编译任务。
- 补齐断点查询、gap 查询和冲突查询。

### Phase 3：个人知识编译与治理

- 增加 ConversationMessage 到 PersonalAssertion 的编译路径。
- 加入 speaker、origin、modality、lifecycle、effective time 和 supersedes。
- 让引用、审核快照和回放完整携带新字段。
- 增加数字分身当前视图和历史变化视图。

### Phase 4：恢复和多工具适配

- 实现 Codex transcript reconcile。
- 增加 ChatGPT、DeepSeek Harness 等来源适配器。
- 增加规则配置 UI、采集范围开关、撤回和人工标记。
- 根据实际数据量和并发量再评估是否需要独立服务端队列；本地端不提前引入消息中间件。

## 10. 验收标准

可靠性：

- 同一事件发送十次，PersonLogy 只有一条原始接收记录和一份对应的编译任务。
- 服务端已提交但客户端未收到响应时，客户端重试后返回 already_received，不产生重复数据。
- Hook 在写库前退出，事件不存在于“已扫描”状态；重启后可以重新捕获。
- sender 在写回执前退出，重启后可以安全重试。
- 序号中间缺失时能显示 gap，不能把后续事件误报为连续完整。
- 同一来源身份同一版本的哈希冲突会阻止覆盖并生成可处理冲突。
- 全局 Hook 与项目 Hook 同时触发只产生一个事件。

知识治理：

- 用户自述、助手建议、引用他人和假设辩论能够区分。
- “可能”“考虑”“准备”“已经决定”“已经完成”不会被归为同一状态。
- 后续观点变化保留历史，并能指向被替代的旧陈述。
- 每条进入数字分身的陈述都能回到原始对话引用。
- 规则、编译器或 prompt 版本变化可以重跑知识分析，但不会重复导入原始对话。

## 11. 已确定与暂缓决定

已确定：

1. 本地持久化采用 SQLite。
2. JSON 仅作为事件载荷格式，不作为队列状态管理方式。
3. 本地捕获与网络发送解耦。
4. 投递使用至少一次语义，服务端以幂等接收保证效果不重复。
5. 用户发言是主要采集对象，助手回复只作为可选上下文。
6. 规则可以宽泛地保留候选，但不能把候选直接当作稳定人格事实。
7. 原始证据、个人陈述和数字分身视图分层保存。

暂缓：

1. 本地 SQLite 是否采用加密扩展，待明确设备安全和备份策略后决定。
2. 是否自动投递中确定性候选，待首轮规则误报率测试后决定。
3. PersonalAssertion 是独立实体还是 Claim 的专门化类型，待现有 Gel/SQLite 迁移成本评估后决定；语义字段和行为契约先按本文固定。
4. 是否引入服务端消息中间件，待实际事件量、在线率和多设备需求出现后决定。

## 12. 参考实现与现有项目衔接点

- Codex Hook 配置和事件生命周期：<https://learn.chatgpt.com/docs/hooks>
- 当前对话导入入口：apps/api/app/modules/conversations/router.py
- 当前对话导入服务：packages/personlogy_core/src/personlogy/application/ingestion/service.py
- 当前通用知识模型：packages/personlogy_core/src/personlogy/domain/knowledge/models.py
- 当前对话源模型：packages/personlogy_core/src/personlogy/domain/source/conversation.py
- 当前知识编译服务：packages/personlogy_core/src/personlogy/application/compilation/service.py
- 当前知识编译计划：docs/plans/p3-conversation-import.md

