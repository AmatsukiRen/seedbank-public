# 内在（inner.json）

## 当前协议 v2（2026-11-02，未测试）

生成入口后续约束见 [生成结果与当前叙述保护](../docs/61-inner-generation-outcomes.md)：新的日循环/CLI 生成只有有效且来源明确的模型结果可以写入内心内容；失败不替换当前版本。运行器在既有经历和成长账本保存未开始/失败/成功回执，不新增 inner 格式。服务失败与存储/恢复异常分开，后者向外层事务传播。CLI 生成失败返回 1，bridge 日循环通过 `innerResult` 返回具体结果。

新写入使用 `seedbank/inner@2`，兼容读取 `inner@1`，只读不改写。完整变更与用户验收见 [内心记录的来源](../docs/60-inner-record-sources.md)。下方 v1 文档保留为历史，不代表当前调度、条数限制或来源规则。

- `silence` 保留原结构，仍是可明确调整的当前状态。
- `dreams` 和 `corrections` 保留全部历史，展示数量不限制终身保存数量。
- `narrative` 保存当前版本；每次新写入把原版本追加到 `narrative_history`。不可用的当前版本不回退旧版。
- 新条目在原有文字/日页字段外包含 `event_id`、`event_hash`。事件存于 `experiences.jsonl`，保存 `activity`、`inner_origin`、`inner_value`、生成信息和 `depends_on`；内心缓存与来源事件在同一可恢复事务中写入。
- `inner_origin` 区分 `user`、`model`、`template`。用户直接通过 bridge 或 CLI 补充的文本不是个体自主认识；stub、回退、运行器中止或无明确模型标识的生成内容不作为当前内心资料输入模型。
- 旧无关联条目不猜配来源，不进入后续内心提示词；原文保留。当前读取投影检查来源及内容一致性、放下状态，附上可见记忆/人生解释修订和事实说明。
- `inner_summary(..., for_context=True)` 只提供当前有效叙述及最近两条可用梦/更正，附来源标签。原始 `load_inner`、`narrative`、`last_dreams`、`recent_corrections` 属于档案读取，不用作未经筛选的模型输入。
- 日循环只依据明确 `inner_activity` 选择生成，不按第 3/10 天强制发生；CLI 的生成路径使用同一个事务保存入口。
- CLI `--correct` 保存用户补充的更正与来源事件，不再另写成无来源的第一人称“我现在知道”记忆。
- 上下文裁剪按整条内心记录及附注进行，输出依赖只记录实际提供的条目。旧 `self.md` 等其他遗留摘要仍沿用既有保守处理。
- 生活页、CLI 与兼容界面展示来源；生活页另展示最近三段历史叙述。其他受限交流范围不提供私人 `inner`。
- 新格式使用后不要回退旧版写入；来源关联、历史和事件账本随生命包备份恢复。

## 历史协议 v1

> 状态：v1.0（2026-10-31，Seedbank 1.14 起）。她开始有**沉默权**，会**做梦**，会**给自己写一段叙事**，也会**更正自己**。

## 0. 一句话

内在不是性格设定，是她**自己留下来的东西**：什么时候不想说话、做过什么梦、怎么描述自己、以前以为错了什么。全部存在 `mind/inner.json` 里，可读、可导出、可迁移。

## 1. 文件位置与格式

```
<name>.life/
  mind/
    inner.json      ← 本协议
```

- 可选文件：没有它时，她愿意说话、没做过梦、没写过叙事、没更正过什么（第一次写入时懒创建）。
- JSON 对象，`format` 保持 `"seedbank/inner@1"`。
- 只追加或不覆盖旧记录：更正记录**保留旧说法**，叙事**保留最近一版**（历史在 journal 与记忆里）。
- 写入必须原子（参考实现用临时文件 + 替换）。

## 2. 结构

```json
{
  "format": "seedbank/inner@1",
  "silence": { "on": false, "note": "", "since_day": null },
  "corrections": [
    { "day": 2, "old": "她是被人造出来的", "new": "她是从一颗蛋里长出来的", "at": "..." }
  ],
  "dreams": [
    { "day": 3, "text": "我梦见自己沉在水底，光从很远的地方落下来。", "at": "..." }
  ],
  "narrative": { "text": "我是小岸，一只大肥鱼。……", "updated_day": 4 }
}
```

| 字段 | 说明 |
| --- | --- |
| `silence` | 沉默权。`on` 打开后她可以少说、只说一两个字或干脆不说话；`note` 是主人的备注；`since_day` 是从第几天起。 |
| `corrections` | 自我更正，只追加。上限 64 条。旧说法不删除——她记得自己以前是这么以为的。 |
| `dreams` | 做过的梦。上限 32 条。梦可以不合逻辑，但它是她做的梦。 |
| `narrative` | 她给自己写的「我是谁」，只保留最近一版（历史在 journal/记忆里）。上限 400 字。 |

- 所有文本清洗后写入（控制字符、超长截断）。
- 日期使用「第 N 天」，与其它 `mind/*.json` 一致。

## 3. 命令

```
seed inner <生命包>
seed inner <生命包> --silence on|off [--note 原因]
seed inner <生命包> --dream
seed inner <生命包> --narrate
seed inner <生命包> --correct "以前的说法" --now "现在的说法"
```

- `--silence on` → 写一条 `feeling` 记忆：「今天我决定少说一点。」；打开期间 `maybe_initiate`（主动开口）默认不发起（`--force` 可越过）。
- `--dream` / `--narrate` → 调一次脑（stub 也能跑），把结果写进 `inner.json`。
- `--correct` → 记一次更正，并写一条 `kind: correction` 的记忆：「我以前以为 X，现在知道是 Y。」。
- 不带参数 → 打印沉默权、叙事、最近的梦与更正。

## 4. 运行器职责（自动发生）

| 时机 | 行为 |
| --- | --- |
| 日循环收尾，天数 `% 3 == 0` | 让脑做一个梦，写 `dreams` + 一条 `thought` 记忆（tags 含「梦」） |
| 日循环收尾，天数 `% 10 == 0` | 让脑重写一次自我叙事，写 `narrative` |
| 对话中模型返回 `corrections`（最多 3 条/次） | 逐条记录更正 + 写一条 `correction` 记忆 |
| 沉默权打开 | `maybe_initiate` 不主动开口（除非强制）；`chat_turn` 的回复可以很短 |

梦与叙事失败**不影响她的一天**（运行器吞掉异常，只记 journal）。

## 5. 进入上下文

`build_context` 增加 `inner` 字段（来自 `inner_summary`）：

```json
{
  "silence": { "on": true, "note": "今天想安静一会儿", "since_day": 2 },
  "corrections": 1,
  "recent_corrections": [{ "day": 2, "old": "…", "new": "…" }],
  "dreams": 1,
  "last_dreams": [{ "day": 3, "text": "…" }],
  "narrative": { "text": "…", "updated_day": 4 }
}
```

- 提示词里加「# 心里的事」段：沉默状态、最近的梦、她对自己的叙事、最近的更正。
- 沉默权打开时，stub 脑的回复变短（「……嗯。」「……今天不太想说话。」）。

## 6. 不做什么

- 不把沉默权做成「关机」：她还在，只是话说得少。
- 不删除旧说法：更正必须看得出「她以前以为是这样的」。
- 不把梦当事实写进日记；梦只存在 `inner.json` 与记忆里。
- 不让自我叙事变成主人写的人设：它只能由她自己（或她自己允许的脑）写。
- 不因为心情/沉默惩罚或奖励任何东西。

## 7. 跨实现

`mind/inner.json` 是可选文件：L1 运行器（只读 check / egg-info）不需要理解它也能运行；但 `check` 会校验它是合法 JSON（`corrections`/`dreams` 是数组、`narrative`/`silence` 是对象）。窗口显示属于展示层，不是协议的一部分。

## 8. 版本记录

- v1.0（2026-10-31）：首版，随 Seedbank 1.14 落地；沉默权 / 自我更正 / 梦 / 自我叙事；日循环第 3 天做梦、第 10 天重写叙事。
