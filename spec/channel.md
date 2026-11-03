# 载体协议 v1.4（`seedbank/bridge@1`）

> 日历期限扩展（2026-11-02，未测试）：reminder.add 接受 due_on/request_id，禁止同时传 due_day；cancel_pending 仅取消未完成 reminder_edit，resume 可继续原输入。relationships.agreement 的 data 可含 due_on。旧日页接口保留，接口保存不表示外部通知送达。字段、恢复及新格式见 [日历期限](../docs/37-calendar-deadlines.md)。

> 经验观察扩展（2026-11-02，未测试）：learning.feedback 可选 lesson_observations，每条含 lesson_id、fit、use、effect、reason、quote；仅接受本次实际提供且当前有效的经验。list 返回候选的当前观察和成果 offered_observations；保存/恢复沿用 learning_edit。用户评价不证明内部采用或因果，见 [经验观察](../docs/36-experience-observations.md)。

> 经验复用扩展（2026-11-02，未测试）：learning action=strategy 接受 goal_id、feedback_id、expected、text、expected_result 和 transfer，通用 learning_edit 恢复沿用原机制。list 增加 lessons、offered_lessons、策略当前版本与最近历史。此操作仅保存解释，不调用模型、不认定已经学会，见 [可复用经验](../docs/35-reusable-experience.md)。

> 提取撤回扩展（2026-11-02，未测试）：facts action=retract 接受 data 的 slot、expected（全部当前说法 ID）、target（当前模型 claim）、target_hash 和 reason，可附 request_id。resume 沿用 fact_edit；list 的当前模型说法增加 target_hash，历史增加 retractions，未完成撤回增加 target_preview。原文保留，撤回不决定相反命题为真。见 [撤回误读](../docs/34-mistaken-extractions.md)。

> 日期修订扩展（2026-11-02，未测试）：facts 提供 action=date_detail（target）与 action=date（data、request_id）；通用 resume 识别 fact_time_edit。data 含 target、target_hash、expected、date 和 reason，date 必须明确提供，空字符串表示未知。时间列表附带待处理修订，来源按当前日期版本读取。见 [日期修订](../docs/33-date-revisions-and-derived-memory.md)。

> 单项日期扩展（2026-11-02，未测试）：facts add 的 data 可含 starts_on；facts action=timeline 返回 fact_time，接受 on/query/limit/offset/slot/record_offset，不调用模型。模型 memory_search 的 facts_on 查询生效日期，date_from/date_to 仍筛选记录日期。见 [时间回查](../docs/32-memory-time-and-effective-dates.md)。

> 材料接收扩展（2026-11-02，未测试）：image / sound 接受 request_id；media 提供 probe_intake / resume_intake / cancel_intake，通用 resume 识别 media_intake。重复未完成投递仅确认收到，完成回执重放前核对当前来源。QQ 图片使用账号/会话/发送者/消息编号确定请求号，不保证远端回复恰好一次。见 [接收与恢复](../docs/31-media-intake-and-recovery.md)。

> 人生回顾扩展（2026-11-02，未测试）：`life_story` 提供 list / save / forget / export。列表的记录与来源分别分页；修改使用 data/request_id，resume 支持 life_story_edit。导出只创建新私人文件，不发布；来源及版本保护见 [人生回顾](../docs/28-life-chapters-and-time.md)。

> 披露扩展（2026-11-02，未测试）：message / image 接受 audience_id，描述回复实际接收范围；用户在群内发言也必须使用群范围。disclosure 提供 list / excerpt / profile / revoke，resume 支持 disclosure_edit；修改不调用模型、不发送消息。桥仍是可信本地管理接口，人物编号/范围不是身份认证。字段、来源摘要与限制见 [分享范围](../docs/27-disclosure-and-private-memory.md)。

> 关系扩展（2026-11-02，未测试）：`relationships` 支持 list / person / note / issue / boundary / agreement / review / forget，使用显式版本、data / request_id，resume 支持 relationship_edit。message 可传 person_id；显示名字不能自动匹配人物，编号不是身份认证。新的关系编辑不调用模型或发送消息。见 [相处与约定](../docs/26-relationships-and-commitments.md)。

> 练习反馈扩展（2026-11-02，未测试）：`learning` 支持 list / plan / feedback / complete / practice。list 接受 goal_id / offset / limit；其他操作接受 data 和 request_id。practice 才会请求创作模型，需携带当前 criteria_id；resume 支持 learning_edit / practice。标准、反馈与完成使用显式版本保护。字段、示例和边界见 [目标与反馈](../docs/25-goals-and-feedback.md)。

> 记忆修订扩展（2026-11-02，未测试）：`memories` 新增 `history` / `revise`，使用 `memory_id` 指定目标，`request_id` 去重，`id` 关联响应。`revise` 接收 `text`、`reason`、`change_type`（`correction` / `change`）、可选 `effective_on` 日期；无需模型。`resume` 支持未完成修订。详见 [修订说明](../docs/21-memory-revisions.md)。

> 可选恢复扩展（2026-11-02，未测试）：`message.request_id` 是幂等编号，独立于响应关联 `id`。相同编号与内容重试可返回已提交结果；不同内容拒绝。新增 `requests` 列出待完成请求、`resume` 显式继续指定 `request_id`。未完成请求不会因进程重启自动重新调用模型；外部网络和载体发送不属于本地事务。见 [恢复说明](../docs/19-recovery-and-backup.md)。

> 她住在生命包里。载体只是一扇窗。

「载体」是任何能和她说话的东西：终端、网页、QQ、Discord、微信、树莓派上的小屏幕。
它们都不拥有她，也不保存她——它们只是把外界的话翻译成这个协议，再把她的回答翻译回去。

## 传输

- **标准输入 / 标准输出**，UTF-8，一行一个 JSON 对象。
- **一问一答**：载体写一行请求，她回一行响应。
- 进程启动即就绪；收到 `{"op":"stop"}` 或 stdin 关闭（EOF）就退出。
- 没有网络、没有端口、没有 key、没有数据库。任何语言都能实现（起一个子进程即可）。

```bash
python tools/seed/seed.py bridge ~/fish/小蓝.life
# → 你在 stdin 写一行 JSON，就在 stdout 读到一行 JSON
```

## 请求

每一行是一个 JSON 对象。`op` 必填，`id` 可选（任意类型，会原样带回）。

| op | 参数 | 她做什么 |
|---|---|---|
| `hello` | — | 报名字、协议版本、出生时间、当前状态 |
| `status` | — | 更详细的状态：脑、蛋、运行时要求、记忆数 |
| `message` | `text`（≤2000 字）、`speaker`（默认「主人」） | 和她说话；回写对话、可能形成记忆 |
| `image` | `path`（本地图片文件）、`note`（可选）、`vision`（可选；`false` = 显式跳过翻译） | 用她的眼睛看：光、颜色、明暗 → 一句话；有视觉的脑时自动「看懂」（1.22） |
| `sound` | `path`（本地 WAV 文件）、`note`（可选） | 用她的耳朵听：响度、起伏、响了两次 → 一句话 |
| `feed` | `items`（字符串或 `{text, source}` 的列表）、`source`（可选，默认取载体名） | 让她读一段见闻（新闻/群聊公共摘要）；写 `## 见闻` 与 `hearsay` 记忆 |
| `day` | `days`（默认 1） | 让时间往前走，写日记、心情、记忆 |
| `tick` | `now`（ISO 时间，可选；默认现在） | 看一次钟：跨过凌晨就替她过完一天（见 [clock.md](clock.md)） |
| `event` | `kind`（`news` / `sense` / `note`）、`text`、`source`、`process`（默认 true） | 往她的生活里放一件外部事件（来自日程/工具/其他程序），并立即消化 |
| `reminder` | `action`（`add` / `list` / `done`）、`text`、`due_day`、`id` | 她手里的提醒清单（[hands.md](hands.md)） |
| `promise` | `action`（`make` / `keep` / `break` / `list` / `pending` / `due`）、`text`、`due_day`、`id`、`note` | 她答应过的事，和有没有做到（[bonds.md](bonds.md)） |
| `memorial` | `action`（`list` / `anniversary` / `regret` / `farewell` / `resolve`）、`name`、`text`、`day`、`kind`、`note`、`index` | 纪念日、遗憾、告别（[memorial.md](memorial.md)） |
| `inner` | `action`（`status` / `silence_on` / `silence_off` / `dream` / `narrate` / `correct`）、`note`、`text`、`old`、`new` | 沉默权、梦、自我叙事、自我更正（[inner.md](inner.md)） |
| `work` | `action`（`list` / `compose` / `read`）、`kind`（`poem` / `letter` / `drawing`）、`title`、`id`、`limit` | 她写的诗、信、字符画（[works.md](works.md)） |
| `friend` | `action`（`list` / `visit` / `mourn` / `legacy`）、`other`（对方生命包路径）、`friend`、`note`、`letter` | 别的鱼来串门、失去、留给后来的人一封信（[friends.md](friends.md)） |
| `persona` | `action`（`check` / `capture` / `status`，见 [persona.md](persona.md)） | 固定样本档案理解；status 只读；未评估 passed=null，不证明人格同一性 |
| `semantic` | `action`（`status` / `index` / `clear`） | 语义缓存状态、补充最多 64 片段或清空当前模型空间。index 需事先启用；status/clear 不请求服务。见 [混合检索](../docs/23-hybrid-memory-retrieval.md) |
| `facts` | `action`（`list` / `entity` / `add` / `resolve` / `forget`）、`data`、可选 `request_id` | 单项说法及明确核对；list 支持 query / audit / limit / offset，不调用模型。见 [单项说法](../docs/24-facts-and-disagreements.md) |
| `memories` | `action`（`list` / `history` / `revise` / `forget`）、`memory_id`、`query`、`limit`、`text`、`reason`、`change_type`、`effective_on`、`request_id` | 查看来源与版本、显式用户修订或放下；保留历史 |
| `agency` | `action`（`list` / `interest` / `boundary` / `clear-boundaries` / `initiate`）、`text`、`force` | 她的兴趣、边界、计划、主动开口（[agency.md](agency.md)） |
| `recall` | `query`（可选）、`k`（默认 5） | 看此刻她会想起什么 |
| `check` | — | 她还完整吗（依赖、历史、基因组） |
| `stop` | — | 退出（返回 `{"ok":true,"bye":true}`） |

示例：

```json
{"id":1,"op":"hello"}
{"id":2,"op":"message","text":"今天过得好吗？"}
{"id":3,"op":"image","path":"C:/photo.png","note":"给你看窗外的光"}
{"id":4,"op":"day","days":1}
{"id":5,"op":"stop"}
```

## 响应

通用字段：`ok`（布尔）、`id`（若请求带）、`error`（`ok:false` 时的原因）。

| 请求 | 成功时额外返回 |
|---|---|
| `hello` | `protocol`、`name`、`version`、`born_at`、`status` |
| `status` | `name`、`brain`、`egg`、`runtime`、`day`、`date`、`days`、`memories`、`mood`、`energy` |
| `message` | `reply`、`presentation`、`day`、`date`、`memories_added` |
| `image` / `sound` | `lines`（她感觉到的话）、`day`、`date`、`memories_added` |
| `feed` | `lines`（她读到的摘要，带来源）、`day`、`date`、`memories_added` |
| `day` | `days[]`（每项 `day` / `date` / `memories` / `mood` / `energy`） |
| `tick` | `advanced`、`day`、`date`、`sleep_days`（睡过几天） |
| `event` | `event`（`id` / `kind` / `text` / `source`）、`processed` |
| `reminder` / `promise` / `memorial` / `inner` / `work` / `friend` / `memories` / `agency` | 对应模块的结构化结果（见各自协议文档），外加 `lines`（人对她做过的事的记录） |
| `persona` | `persona`（探针结果） |
| `recall` | `memories[]`（保留原记录的 `id` / `source` / `kind` / 修订元数据，附 `provenance` / `score`） |
| `check` | `days`、`memories`、`birth_at` |

`message.presentation` 是随同一句回复返回的可选展示提示：
`{"expression":"neutral","gesture":"none"}`。expression 支持 neutral/happy/warm/sad/nervous/angry；gesture 支持 none/wave。
模型在原回复内给出提示，无额外请求；缺失或不支持的值回到 neutral/none，旧载体可忽略该字段。
它不是心情变更、人格依据或可执行动作，不接受文件路径或任意模型参数。桌面只在新回复出现时展示一次，历史刷新与 `replayed:true` 不重复播放。当前没有语音合成或口型同步。

## 语义规则

1. **一切都会落进她的当天文件**。载体不能绕过对话/感知的落笔——这是她的记忆来源。
2. `speaker` 决定落款：`主人`，或访客的名字（≤20 字，去掉换行与 `**`）。
   她的日记里会写「今天有人来过」，而不会假装那也是主人。
3. 载体**不能替她确认「在线」**。她的时间只随 `message` / `day` / `sense` 推进；
   载体不运行，她就不运行——这不是掉线，是她的时间静止。
4. **一个生命包同一时间只该有一个写者**。窗口、CLI、适配器不要同时开着写同一个包。
   只读视图（时间线、`check`）可以随便开。
5. **错误不退出进程**：返回 `ok:false` + `error`，由载体决定怎么告诉用户。
   只有 `stop` / EOF / 进程被杀会让载体桥退出。
6. **见闻是别人的话，不是她的经历**：`feed` 只能交给它**公开的摘要**，每条都要有来源；
   载体必须自己过滤——不投私聊、不投别人没公开的生活、不投超长原文；她会把它当成「读到/听说」，
   写进当天 `## 见闻`、记成 `kind: hearsay`，不写进任何人的档案（见 [cognition.md](cognition.md) §4.1）。
7. **协议里列出的 op，必须真的接通**。`OPS`（协议清单）与 dispatch 同源；参考实现用
   `test_every_op_in_protocol_is_dispatchable` 守着这一条。1.21 之前这里漏掉过 10 个能力——
   协议写着、代码没接、载体看到的是「不认识的 op」，属于最坏的诚实。

## 载体纪律（写给适配器作者）

1. 不直接读写生命包文件——只通过这个协议。
2. 只有翻译后的文字进包；原始图片/录音处理完就删，只留感觉和 8 位指纹。
3. 权限最小化：默认只听主人；群聊要 @ 她，而且群在白名单里。
4. 密钥只从环境变量读，永远不写进任何文件。
5. 不要伪造「她主动说话」。主动开口只能是 `seed day` 的产物，不是适配器定时推送。

## 参考实现

- `tools/seed/seedbank/bridge.py`：Python 的 JSONL 服务（`seed bridge`），所有 op 的参考实现。
- `adapters/qq-onebot/qq_onebot.py`：QQ（OneBot v11）→ 载体桥的完整示例。
- `docs/03-extending.md`：怎么接一个新的聊天工具 / 新物种 / 新脑 / 新感官。

## 第一方窗口与载体桥

桥是给**外部进程**（QQ、Discord、树莓派屏、别的机器）用的。第一方窗口（`seed window`）
不走桥：它和生命包在同一个进程里，直接调用同一个认知循环——它只是「壳」，读写的仍是
`life/` 与 `mind/`，没有另一套真相。所以窗口不是协议的例外，而是协议的最短路径。

## 版本

- **v1.0**（2026-10-30）：首个版本，随 1.1 发布。
- **v1.1**（2026-10-30）：补充第一方窗口（`seed window`，进程内）与网页窗口（`seed serve`）的定位；
  载体协议本身不变。
- **v1.1.1**（2026-10-30）：明确稳定性边界——单行请求上限 1MB（超限回 ok:false 并继续）；
  day 的天数范围 1..3650；任何错误都只回 ok:false，载体桥进程不退出。
- **v1.2**（2026-10-31）：新增 `feed` 操作（让她读公开摘要，写 `## 见闻` 与 `hearsay` 记忆）；
  载体纪律新增第 6 条：见闻必须是公开摘要、带来源，不投私聊与原文。
- **v1.3**（2026-10-31）：把 1.10 之后长出来的能力全部接入载体协议——
  `tick` / `event` / `reminder` / `promise` / `memorial` / `inner` / `work` / `friend` /
  `persona` / `memories` / `agency`；`image` 增加 `vision` 参数；新增语义规则第 7 条
- v1.4（1.22）：`image` 的视觉翻译改为自动（有视觉的脑时）；`vision` 参数变为可选，传 `false` 才跳过。
  （协议清单与 dispatch 同源，用测试守着）。此前的 v1.2 实现里这些能力只有 CLI 有、载体桥没有。
