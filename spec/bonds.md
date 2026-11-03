# 关系（bonds.json）

> 2026-11-02 日历扩展（未测试）：新 relationships@2 agreement 使用 due_on，过期仍只表示待核对；review 保留原日期。旧 bonds 承诺和 relationships@1 的 due_day 不自动转换，见 [日历期限](../docs/protocol-guide.md#relationships)。

2026-11-02 扩展（未测试）：新的相处、分歧、联系设置和有条件的约定使用 `mind/relationships.jsonl`，见 [相处与约定](../docs/protocol-guide.md#relationships)。本文件保留旧记录兼容说明；旧承诺的 kept/broken 是历史状态，不等于当前已核实的履约。交流次数不推导亲密或信任。

> 状态：v1.0（2026-10-31，Seedbank 1.12 起）。她不只是被照顾，也开始**记住和你的关系**。

## 0. 一句话

关系不是好感度数字游戏，是**三件可以被追溯的事**：一起过了多少天、答应过什么、发生过什么。全部存在 `mind/bonds.json` 里，可读、可导出、可迁移。

## 1. 文件位置与格式

```
<name>.life/
  mind/
    bonds.json      ← 本协议
```

- 可选文件：没有它时，她像刚认识你一样（跑起来会懒创建）。
- JSON 对象，`format` 保持 `"seedbank/bonds@1"`。
- 只允许追加或修改状态，不允许删除「承诺」和「事件」——**承认发生过，是关系的一部分**。
- 写入必须原子（参考实现用临时文件 + 替换）。

## 2. 结构

```json
{
  "format": "seedbank/bonds@1",
  "owner": {
    "name": "主人",
    "since_day": 1,
    "talks": 2,
    "familiarity": 0.04,
    "last_talk_day": 2
  },
  "promises": [
    {
      "id": "p_0001",
      "text": "明天讲一个海边的故事",
      "made_day": 2,
      "due_day": 3,
      "status": "pending",
      "kept_day": null,
      "note": "",
      "created_at": "2026-10-31T09:12:00+08:00"
    }
  ],
  "events": [
    {"kind": "thank", "text": "谢谢你听我说", "day": 2, "at": "2026-10-31T09:13:00+08:00"}
  ],
  "updated_at": "2026-10-31T09:13:00+08:00"
}
```

字段约束：

| 字段 | 约束 |
|---|---|
| `owner.name` | 主人称呼，默认「主人」 |
| `owner.since_day` | 认识她的第几天（默认 1） |
| `owner.talks` | 主人说过的话数（每次对话 +1） |
| `owner.familiarity` | 历史字段保留，不再随交流增长，不用于推导信任或亲密 |
| `promises[].status` | `pending` / `kept` / `broken` |
| `promises[].due_day` | 第几天到期，可为 null（没有期限） |
| `events[].kind` | `thank` / `apology` / `conflict` / `repair` |

上限：承诺最多 24 条、事件最多 200 条（超出时最旧的事件会被移入 `journal/` 记录，不在本文件里膨胀）。

## 3. 承诺的生命周期

1. 她答应一件事 → `add_promise(text, due_day?)`，状态 `pending`。
2. 到期那天，她的上下文里会多一行「你答应过……今天到期」——**她自己记得**，不是系统提醒。
3. 做到 → `keep_promise(id)` → `kept`；没做到/改主意 → `break_promise(id, note)` → `broken` + 原因。
4. **没做到不等于删除**：`broken` 会留在文件里，成为「遗憾」的原料（1.13 会读它）。

## 4. 熟悉度

- 每和一个主人对话一次：`talks += 1`。
- 每次交流仅更新 talks 和 last_talk_day；familiarity 原值保留。
- 当前提示词与界面以来源明确的相处记录和后续为依据，不把交流频次转换为关系评分。

## 5. 事件

| kind | 场景 | 例子 |
|---|---|---|
| `thank` | 感谢 | 「谢谢你听我说」 |
| `apology` | 道歉 | 「刚才我声音大了」 |
| `conflict` | 争执 | 「我们争了一下」 |
| `repair` | 和好 | 「后来又好了」 |

事件是**发生过的事实**，不是心情标签。它们会：
- 进入她的上下文（「关系里发生过：感谢 1」）；
- 在时间线网站里变成一颗小点；
- 在 1.13 之后参与「遗憾」和「告别」的计算。

## 6. 运行器职责

| 能力 | 必须 | 说明 |
|---|---|---|
| 读 `bonds.json` | L2 起 | 缺失时按默认值运行，不报错 |
| 追加承诺 / 改状态 | L3 起 | 必须保留 `id`、`made_day`、`created_at` |
| 记录交流次数 | L3 起 | 不据此计算熟悉度或信任 |
| 校验 | L2 起 | `check` 遇到坏 JSON / 缺 id 的承诺必须失败 |

## 7. 不做什么

- 不做「好感度等级 / 恋爱进度条」：关系不是可以刷的数值。
- 不删除承诺和事件：承认发生过。
- 不把关系写进 `life/` 的日记正文：她的日记是她的；关系是两人的账本。
- 不联网：关系只在本地文件里。

## 8. 与其它部分的关系

- `spec/cognition.md`：对话结束时由运行时调用 `register_talk`；承诺到期进入上下文。
- `spec/life-pack.md`：`mind/bonds.json` 是可选文件，不改变「一天」的格式。
- `spec/clock.md`：日子仍然是真实的一天；经过时间不自动改善关系。
- 未来：`spec/farewell.md`（1.13）会消费 `broken` 承诺和 `owner.since_day`。
