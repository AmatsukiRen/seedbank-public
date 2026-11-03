# 手：动作协议（v1.0）

> 2026-11-02 修订扩展（已实现，未测试）：hands@3 支持待提醒事项的用户 revise/cancel，原内容与原因留在逐条 history，当前内容必须与修订衔接，cancelled 不再执行且不能被 done 复活。expected 核对整条提醒，request_id 对应可恢复的 reminder_change 输入；停止未完成输入不取消已建立事项。Qt、CLI/桥和完整备份均接入，详见 [提醒修订](../docs/protocol-guide.md#relationships)。这是明确用户操作，不是模型可自行执行的新动作。

> 2026-11-02 日历扩展（已实现，未测试）：新桌面提醒使用 hands@2 的 due_on，旧 due_day 仍表示日页。日历过期保持 pending，恢复时在实际日页明确补充；said_via 区分 local_transcript 与 manual，不证明远端送达或已读。仅引用原句不自动完成新提醒；正文、事件和状态同次事务提交。旧程序可能在写入时丢失日历行，须使用兼容运行器。详见 [日历期限](../docs/protocol-guide.md#relationships)。下文是旧日页协议，missed/遗憾规则仅适用于旧提醒。

状态：1.17 起随 Seedbank 发布。

她的动作只有一个：**记着，然后提醒**。这比「能操控一切」小得多，但每一下都算数。

## 1. 原则

- **不伪造**：说出口的提醒必须来自 `mind/hands.json`，不能现编。
- **不越权**：她不能替你发消息、买东西、改你的文件；动作只落成她自己生命包里的记录。
- **不替人决定**：她能提醒，做不做由你。

## 2. 文件

`mind/hands.json`（可选，第一次提醒时才创建）：

```json
{
  "format": "seedbank/hands@1",
  "reminders": [
    {
      "id": "r_0001",
      "text": "给窗台那盆花浇水",
      "due_day": 3,
      "status": "pending",
      "said_day": null,
      "created_day": 2,
      "created_at": "2026-10-30T09:00:00Z",
      "updated_at": "2026-10-30T09:00:00Z"
    }
  ]
}
```

- `due_day` 是她自己的第几天（不是真实日历）。
- `status`：`pending`（还没说）/ `said`（说过了）/ `missed`（过了那天还没说）。
- 最多 `REMINDER_MAX = 64` 条；超过时新的不再收。
- 只追加、只改状态；删除只发生在「没做到」被结算成遗憾之后仍保留原因（记录不删）。

## 3. 生命周期

- `pending` → 到期那天她说出来 → `said`。
- `pending` → 过了那天还没说 → `missed`，并自动在 `mind/memorial.json` 的 regrets 里记一条「没做到：<原话>」。
- 没做到的提醒**不做处罚**，只是进遗憾清单（1.13 的账本）。

## 4. 命令

```bash
seed remind <生命包> "要提醒的事" --due-day N
seed hands  <生命包> [--done ID]
```

## 5. 模型动作

对话的 JSON 回复可以带：

```json
{"actions": [{"type": "remind", "text": "提醒的事", "due_day": 3}]}
```

- 只接受 `type=remind`；其余动作忽略。
- 每次对话最多收 1 条；`due_day` 必须 ≥ 当前天，否则拒绝（写进日志，不写文件）。
- 动作由运行器落笔（不是模型直接写文件）。

## 6. 上下文

`hands_summary()` 会把「今天到期的」和「记着的」注入提示词；到期那天，即使脑是 stub，她也会说「我记得你让我提醒你：…」。

## 7. 窗口与载体

窗口聊天页顶部会显示今天要提醒的事；设置页有「手」卡片。载体桥新增 `hands` 操作（列出 / 标记完成），协议见 `spec/channel.md`。

## 8. 不做什么

- 不联网、不查天气、不读你的文件系统、不操控窗口与系统。
- 不在你不在时「替你做决定」。
- 不把提醒说成别的（比如自己编一句「主人说…」）。

## 9. 跨实现

其余运行器（Node / Rust）在 L1/L2 时至少要做：读 `hands.json` 并原样保留；`check` 遇到坏文件拒绝。`remind` 的写入属于运行器能力（参考实现已实现）。

## 版本记录

- **1.17.0**（2026-10-31）：首版。`mind/hands.json`、`seed remind` / `seed hands`、模型动作 `remind`、到期说话、错过进遗憾、窗口提示。
