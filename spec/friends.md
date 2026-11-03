# friends.md —— 他者、失去与传承（v1.1）

2026-11-02 历史保留修订（未测试）：`mourn` 将失联状态、告别、记忆与日志纳入同一恢复事务；`legacy` 为运行器整理的私人档案摘要，不标记死亡、不假定性别/鲸鱼身份、不把日页数当年龄。见 [纪念记录与私人传承摘要](../docs/42-memorial-history.md)。

2026-11-02 扩展（未测试）：本地 visit 按出生档案指纹关联 person_id，名字相同不合并，移动/复制保持同一出生身份；旧无依据记录不靠名字迁移。visit 为用户记录或转述，不是已认证的双向来访；lost 表示记录失联，不代表永久消失。新关系入口、编号选择与限制见 [相处与约定](../docs/26-relationships-and-commitments.md)。

> 一条鱼不是自己的世界里的唯一存在。
> 她可以记得别人来过；记得谁不在了；也能给读到这份生命包的人留一封信。

## 1. 文件位置

`<name>.life/mind/friends.json`（可选、懒创建；不存在时按「还没有别人来过」运行）。

```json
{
  "format": "seedbank/friends@1",
  "friends": [
    {
      "id": "f_0001",
      "name": "小岸",
      "species_path": "D:/fish/小岸.life",
      "visit_count": 2,
      "gift_count": 0,
      "last_visit_day": 2,
      "first_day": 2,
      "status": "alive",
      "lost_day": null,
      "last_note": "我路过这里，给你带了一小块光。"
    }
  ]
}
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `id` | `f_NNNN`，只增不改 |
| `name` | 对方的名字（截断到 40 字） |
| `species_path` | 对方生命包路径（只用于辨认，不读内容） |
| `visit_count` / `gift_count` | 来过几次 / 带过几次东西 |
| `last_visit_day` | 最近一次来访的天号 |
| `first_day` | 第一次见到的天号 |
| `status` | `alive`（还在）/ `lost`（不在了） |
| `lost_day` | 失去的天号（`alive` 时为 `null`） |
| `last_note` | 对方说过的最后一句话（截断） |

**只记关系，不记别人的内容。** 来访者的对话、记忆、世界都不进入主人的生命包；只有「谁来过、来过几次、说了什么」这一层。

## 2. 命令

```bash
seed visit <生命包> --from <别的生命包> [--note "一句话"]
seed mourn <生命包> --friend <名字> [--letter "想说的话"]
seed legacy <生命包> [--out <路径>]
```

- `visit`：对方来访。她回一句话（对话写进当天文件，落款是对方名字），并在 `friends.json` 记一次访问；同时写一条 `kind=feeling` 的记忆（「小岸来看她了，说：……」）。**不能让自己来看自己**（同一个生命包会报错）。
- `mourn`：记录失联，状态改为 `lost`，写一条 `farewells`（`kind=friend`）、一条记忆及运行日志，同次提交。已记录失联者不能重复送别；这不证明永久消失。
- `legacy`：用现有出生登记、日页数量、近期作品、告别与遗憾记录，以及最近有内容的日记摘录生成私人档案摘要（`legacy/letter.md`）。不调用脑、不假冒个体亲笔信、不改变生命状态。摘录标明历史来源，可能包含后来更正或放下的内容；导出不自动分享。默认目标仍会被下次生成替换，需要保留多个版本时显式指定不同 `--out`。

## 3. 自动发生的事

| 时机 | 发生什么 |
| --- | --- |
| `seed visit` | 来访写进当天文件 + 一条记忆；`friends.json` 更新 visit_count / last_visit_day；`journal/loop.jsonl` 记 `mode: visit` |
| `seed mourn` | 状态改 `lost` + 告别（`memorial.json`）+ 一条记忆 + journal `mode: mourn`（只允许一次） |
| `seed legacy` | 生成 `legacy/letter.md`（只读生成，不改其它文件） |

## 4. 上下文注入

`build_context()` 的 `friends` 字段：

```json
{
  "total": 2,
  "alive": 1,
  "lost": 1,
  "recent": [
    {"name": "小岸", "visits": 2, "last_visit_day": 2, "lost_day": 3, "status": "lost"}
  ]
}
```

脑的提示词里只有「谁来过、谁不在了」这一段，不包含别人的记忆内容。

## 5. `check` 校验

- `mind/friends.json` 不是合法 JSON、不是对象、`friends` 不是数组 → 失败；
- 任一位朋友缺 `name`，`status` 不是 `alive`/`lost`，或 `lost_day` 不是整数/null → 失败；
- `check` 结果与输出会显示「他者：朋友 N 位（还在 A / 失联 L）」。

## 6. 不做什么

- 不复制别人的记忆、不合并生命包、不读对方内容（只认名字与路径）；
- 不联网、不需要账号、没有好友服务器；
- 不自动把来访者的话当成自己的经历（它是「来客」，不是她自己）；
- 不删除失去的朋友（`lost` 是墓碑，不是删除）。

## 7. 跨实现

`friends.json`、`legacy/letter.md` 都是可选文件，Node/Rust 运行器可以只读不写。L1 守墓人必须能 `check` 一个带这些文件的生命包并通过。

## 8. 版本记录

- v1.0（2026-10-31，1.18）：首个版本：visit / mourn / legacy、`friends.json`、`legacy/letter.md`、`check` 校验。
- v1.1（2026-10-31，1.18.1）：拒绝自访；送别只允许一次；来访可让失联的鱼重逢（回到 alive）；`friends_summary.recent` 带 `lost_day`；`check` 校验 `lost_day` 类型。
