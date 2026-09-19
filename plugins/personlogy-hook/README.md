# PersonLogy Hook

这是 PersonLogy 的 Codex 本地捕获插件第一版。它只做本地可靠入队和可选发送，不在 Hook 中调用大模型，也不直接生成最终人格结论。

## 工作方式

UserPromptSubmit 读取 Codex 通过 stdin 提供的 JSON 事件。命中 config/rules.json 中的个人信号规则后，插件会：

1. 对消息做最小归一化和常见凭据遮盖；
2. 生成稳定的来源键、事件 ID 和载荷哈希；
3. 在 PLUGIN_DATA 指向的 SQLite 数据库中写入 capture_events 和 deliveries；
4. 立即结束 Hook，不等待网络。

SessionStart 会异步尝试发送一小批待投递事件。需要持续发送时，可以运行：

    python3 scripts/sender.py --loop

Windows：

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_windows.ps1 sender.py --loop

## 配置

环境变量：

    PERSONLOGY_HOOK_DB
    PERSONLOGY_HOOK_DATA_DIR
    PERSONLOGY_HOOK_RULES
    PERSONLOGY_HOOK_SCOPE=project|global
    PERSONLOGY_HOOK_PRODUCER_ID
    PERSONLOGY_HOOK_STREAM_ID
    PERSONLOGY_DESTINATION_ID
    PERSONLOGY_ENDPOINT
    PERSONLOGY_TOKEN
    PERSONLOGY_HTTP_TIMEOUT

默认数据库位于 Codex 提供的 PLUGIN_DATA 目录下；如果该变量不可用，则回退到当前用户的本地应用数据目录。

规则可以直接复制 config/rules.json 后通过 PERSONLOGY_HOOK_RULES 指向用户自己的文件。修改规则不会改变已经写入的事件，事件会记录捕获时的 rule_version。

## 手动测试

在插件目录下运行：

    Get-Content tests/fixtures/user_prompt_submit.json -Raw | powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_windows.ps1 capture.py

检查 SQLite：

    .venv\Scripts\python.exe -c "import sqlite3, os; p=os.environ['PERSONLOGY_HOOK_DB']; c=sqlite3.connect(p); print(c.execute('select event_id, source_item_key, sequence from capture_events').fetchall())"

发送端默认请求 http://127.0.0.1:8000/v1/capture/events。PersonLogy 接收端尚未实现时，事件会保留在 pending 或 retry_wait，不会被删除。

## 当前边界

- 首版只捕获用户 prompt；助手回复和 transcript reconcile 留到后续迭代。
- Hook 失败不会阻塞 Codex 当前 prompt，但会输出错误并保留本地可见的失败信号。
- sender 使用至少一次投递语义；PersonLogy 必须按 event_id、来源复合键和 payload_hash 实现幂等接收。
- 本地库包含个人对话证据，应使用当前用户目录权限保护，不放仓库、不放网络共享目录。
