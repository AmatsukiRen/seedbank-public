# 意志：兴趣、计划、边界、主动

2026-11-03 安静自主活动修正：空 reply 不再丢弃有来源的 memory_writes、learning_updates、life_story 或 corrections；仍经过现有校验，只在实际发言时写入主动对话。自主选择次数包含安静决定，不能称为开口次数。自动活动上下文优先利用精简规则和去重数据保留反馈，不提高默认预算。详见 [安静活动与反馈保留](../docs/85-quiet-initiative-learning.md)。

2026-11-02 跨日选择扩展（未测试）：prior_choices 提供来源有效的先前专注意图；daily_plan.continuity 明确继续、调整或放下，保存父事件版本与理由，使用 plans@4。休息不自动放弃，旧成果不移交新计划，来源裁减与隐私规则继续适用。见 [跨日的打算](../docs/53-cross-day-intentions.md)。

2026-11-02 结束条件扩展（未测试）：focus 可选 checkpoint={criteria_id}，只接受实际提供且有效的完整目标条件。保存为 plans@3 事件，绑定条件记录指纹；按该计划版本下的同目标/条件成果与当前反馈核对，满足后暂缓自动创作/反思，等待新选择。旧 done 与自由文字不自动认证，详见 [结束条件与下一次选择](../docs/50-plan-checkpoints.md)。

2026-11-02 尝试计数扩展（未测试）：运行器预排使用来源有效且已知进入执行流程的创作/反思次数；未开始、旧失败未知和已失效来源不冒充已知练习。已作出的模型选择和等待重新选择规则继续优先。见 [行动阶段与统计](../docs/48-action-attempt-states.md)。

2026-11-02 跨渠道扩展（未测试）：focus/rest 与待重新选择约束所有当前渠道的模型自动创作/反思；外部只得到不含私人依据的结果。awaiting_choice 与旧 decision_basis_changed 触发记录保持当天等待状态，后台刷新不替代明确选择。详见 [跨渠道选择](../docs/47-cross-channel-choices.md)，替代下方此前仅私人自动动作的范围。

2026-11-02 行动关联扩展（未测试）：执行前捕获私人计划版本，回执可选 plan_reference 保存单条事件指纹与 automatic/requested 来源；plan_review 汇总目前可用的确切关联，旧回执不按日页或目标补配。详见 [计划与实际行动](../docs/46-plans-and-action-links.md)。

2026-11-02 每日选择扩展（未测试）：可选 daily_plan 提交 focus/rest/open、具体安排、简短理由及可见来源。接受后追加 plans@2 decision 与来源事件，后台刷新保留当天有效选择；私人自动创作/反思遵循此选择。旧数据继续可读，新 decision 需要新版运行器。详见 [每日选择](../docs/45-daily-choices.md)。

2026-11-02 计划历史扩展（未测试）：新选择追加到 `mind/plans.jsonl`（`seedbank/plans@1`），首次变更保存完整旧计划 baseline；后续 selection/import/legacy_flag 通过 previous 连接同日上一版本。`agency.json` 的 plan_store 标记权威历史，plans 为兼容投影。没有 90 条保存上限；同日刷新保留历史。详见 [计划历史、分页与兼容](../docs/44-plan-history.md)。以下旧规则中与此冲突的内容视为历史设计。

> 当前兴趣来自有来源的偏好提案；每日计划承接长期目标，主动开口与动作成功都不自动代表计划完成。2026-11-02：行动回执与完成判定分开，旧 done 只显示为待核对，显式刷新不再受它阻止。以下旧词频与固定计划规则已被 [development.md](development.md) 覆盖，详细变更见 [行动回执与计划](../docs/43-action-outcomes-and-plans.md)。

**状态：v1.0（1.11）**

这条鱼不只是被叫醒才说话。她可以自己在意某些事（兴趣）、给自己定计划（计划）、
不想聊的东西就不聊（边界），还会在你没有说话的时候先开口（主动）。

这一层只依赖本地文件、不依赖模型能力，所以换脑、离线、关掉窗口之后它都还在。

## 1. 文件

`mind/agency.json`（可选；孵化器**不**创建它，第一次用到时才写）：

```json
{
  "format": "seedbank/agency@1",
  "interests": [
    { "topic": "灯塔", "weight": 0.3, "source": "日子", "day": 3, "updated_at": "2026-11-01T21:00:00Z" }
  ],
  "plans": [
    { "day": 4, "plan": "读点什么", "created_at": "2026-11-01T21:00:00Z", "done": false }
  ],
  "boundaries": ["离开"],
  "last_initiated_at": "2026-11-01T21:10:00Z",
  "initiated": { "2026-11-01": 1 }
}
```

| 字段 | 说明 |
| --- | --- |
| `interests` | 她自己在意的主题；最多 8 个，`weight` 0–1（重复遇到会加一点） |
| `plans` | 每天一个计划（来自固定选项；按出生 seed + 天数确定性选择，不靠模型） |
| `boundaries` | 她不想聊的话题；命中时由脑拒绝，并写一条 `kind: feeling` 的记忆 |
| `last_initiated_at` | 她上一次主动开口的时间（用来控制频率） |
| `initiated` | 按本地日期记的主动次数 |

文件缺失可使用默认空配置。现有文件的顶层或计划结构损坏、计划日志缺失或版本链断裂会报错并保留，不按空配置继续覆盖；`check` 使用同一读取规则。

## 2. 兴趣：只从「她读到的 / 听到的」里长

- 素材只取当天生活文件里的 `## 见闻` 条目与 `## 对话` 里的主人发言（不含她自己主动说的）。
- 从素材里切 2–4 个汉字的候选片段，出现 **≥ 2 次** 且不在停用词/句尾碎片里的才算话题；
  每天最多长 **2 个**新兴趣。
- 不从日记模板词、心情词、系统词里学（早期实现会学到「了自己一」这类碎片，已换算法）。
- 兴趣的来源写 `source: "日子"`，并记 `day`；之后可以用 `seed agency --interest` 手动补。

这样她的兴趣是非虚构的：她只在意真的见过、读过、听过的东西。

## 3. 计划：每天一个，确定性选择

可选计划：`读点什么`、`整理记忆`、`发呆`、`等主人来`、`写点东西`。

选择方式：`rng = rng_from(f"{seed}|plan|{day}")` → 取一项；同一条鱼同一天永远同一项。
每天收尾（`run_days` 最后一天）时给明天定计划。`mark_plan_done` 仅保留为旧 API 的未核实标记写入器，不再由运行器动作调用；读取不会把它当作完成依据，也不会自动改写旧标记。当前文字计划尚无专门完成条件或确认入口，显示“完成待核对”，不与长期目标的条件核对混用。

## 4. 边界：她可以说不

- `boundaries` 是话题词列表（≤ 12 个，每个 ≤ 40 字）。
- 说话前先做子串匹配；命中时：
  - 真实模型的提示词里写明边界 → 模型自己委婉拒绝；
  - `stub` 保证行为一致：「……{话题}这个，我现在不想说。」并在记忆里写一条
    `kind: feeling`、`tags: ["边界"]`。
- 拒绝之后**不**把这条对话当作她的记忆内容（只留「她不想聊」这件事）。

## 5. 主动：没人说话时也会开口

满足全部条件才主动：

1. 现在是「她醒着」的时段（默认 7:00–23:00，本地时间）；
2. 最后一天是开着的（没有 `## 今天`）且日期 = 今天；
3. 今天主动次数 < 3；
4. 距上次主动 ≥ 2 小时（脚本/测试可传 `idle_seconds=0` 或 `force=True`）。

主动说的话落款是 `**<名字>（主动）**：`（不是主人），同时：
- 写一条 `kind: thought` 的记忆（她自己的想法）；
- `journal/loop.jsonl` 记 `"mode": "initiate"`；
- `last_initiated_at` 与 `initiated[date]` 更新。

主动内容由脑生成：`brain.build_initiate_prompt(ctx)`；`stub` 会从计划/兴趣里挑一句，
保证离线也能有主动行为。

## 6. 运行器职责

| 函数 | 时机 |
| --- | --- |
| `cognition.maybe_initiate(pack, brain=None, *, now=None, idle_seconds=7200, max_per_day=3, force=False)` | 窗口每 60 秒看钟时、终端 `seed initiate` 时 |
| `cognition.run_days(...)` | 每天收尾时 `learn_from_day` + `plan_for_day(day+1)` |
| `cognition.build_context(...)` | 注入 `interests` / `boundaries` / `plan` 给脑 |
| `cognition.append_transcript(..., who="fish", initiated=True)` | 写 `（主动）` 落款 |

命令行：

```
seed agency <包>                         # 看她的兴趣、计划、边界、今天主动了几次
seed agency <包> --interest 灯塔         # 手动加一个兴趣
seed agency <包> --boundary 离开         # 加一条边界
seed agency <包> --clear-boundaries      # 清空边界
seed agency <包> --history --limit 20    # 查看计划历史，next_before 用于继续分页
seed initiate <包> [--force]              # 让她主动说一句（--force 可绕过时段/间隔）
```

## 7. 不做什么

- 不读心：兴趣只来自她见过的文字，不做画像、不联网采集。
- 不替主人做决定：计划只是她自己的小安排，不驱动任何外部动作。
- 不越界：边界命中只影响对话，不改写历史。
- 不伪造主动：主动必须真的写进当天的生活文件，并带时间；不能后台刷屏（每天 ≤ 3 次）。

## 8. 版本记录

- v1.0（1.11）：兴趣 / 计划 / 边界 / 主动；`mind/agency.json`；`seed agency`、`seed initiate`；
  窗口每 60 秒看钟时尝试主动。
