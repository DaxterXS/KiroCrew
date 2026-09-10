# Q7 决策备忘：worker 能否看到兄弟的 `summary`

背景：[rfc-conductor-work-ledger.md](../rfc-conductor-work-ledger.md) 的 Open questions Q7。今天 `work_brief` 只返回调用者自己的 item。

## 利

- 兄弟的 `summary` 常是 B 了解 A 做了什么最省的一手材料。
- 省掉 conductor 逐条转述的人工中转。

## 弊

- 一个 agent 的自由文本直接进入另一个 agent 的上下文，中间没有任何闸门。
- 与「不让 `session_send` 到 worker」的理由同源：转述会变成劝说。
- 需要 prose 时可由 conductor 开 channel，让 A 主动说，需求并未落空。

## 结论

不开放。worker 只看到自己的 item，兄弟只暴露 `title`、`status`、`artifacts`、`last_report_at` 这类指针与枚举。
