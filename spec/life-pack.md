# 生命包格式（Life Pack）· v0.20

> 目标历史回查（2026-11-03）：已有 `development@1 goal` 按原事件只读投影为 `goal_history`，保留原始编号、时间和依据；最新可见状态是临时注释，不写回账本。派生索引 v11 从旧缓存重建，不改变正式档案或补写旧理由。引用与撤回规则见 [旧目标与修订理由](../docs/103-past-goals-and-revision-reasons.md)。

> 行动理由回查（2026-11-03）：原 `development@1 outcome.data.proposal` 可只读投影为可引用的档案候选；不新增正式账本、不修改原回执。`mind/search.sqlite3` 缓存升级 v10 并可重建，人生回顾引用原 `d_` 编号及账本锚点，来源撤回继续约束派生内容。见[全档案回查](../docs/101-action-reason-archive-recall.md)。

> 行动说明扩展（2026-11-03）：`development@1 outcome.data.proposal` 增加可选 `seedbank/action-proposal@1`，保存提出时的理由、时间、来源、依据与生成信息；具体字段及保护规则见 [成长协议](development.md) 和 [本轮证据](../docs/100-action-reasons-and-sources.md)。不迁移、回填旧行，原备份包含完整记录；旧运行器没有新增说明的来源投影规则，请使用当前版本。

> 经验取舍扩展（2026-11-02，未测试）：development@1 的 outcome.practice.strategy_choices 和 creation.metadata.strategy_choices 增加相同的可选 strategy-choices@1 数据块，包含候选、模型自述、经验摘要、未说明/拒收状态。不迁移旧行，不改变既有学习格式。读取核对实际提供、源事件、经验版本和作品；旧运行器可能忽略字段，见 [创作取舍](../docs/40-strategy-choices.md)。

> 提醒修订扩展（2026-11-02，未测试）：首次修改/取消待提醒事项将 hands.json 保存为 hands@3，新增 cancelled 及逐条 history（revision/action/reason/request_id/day/on/at/before/after）。历史衔接与当前内容不符时停止写入；reminder_change 输入与完成回执随原请求机制持久化，提醒发出事件注明 reminder_revision。旧日页不自动换成日历，旧版本读取不迁移。兼容和恢复见 [提醒修订](../docs/39-reminder-revisions.md)。

> 纠错读取扩展（2026-11-02，未测试）：已有 facts@1 resolve/correction 参与旧生成内容退出计算，保留原始文件；fact_notes 是当前、按范围计算的投影，不信任存档或缓存自带的旧标注。没有格式迁移，但旧运行器不具备新读取规则。运行器固定回查说明的生成来源增加 runtime_guard，见 [纠错贯通](../docs/38-corrections-through-recall.md)。

> 日历期限扩展（2026-11-02，未测试）：hands@2 日历提醒使用 due_on/created_on/said_on/said_via，due_day=null，允许混合旧日页行；relationships@2 agreement 使用可空 due_on。request.kind=reminder_edit 支持恢复和明确取消未完成输入；本地提醒经历标记 runtime 与 local_transcript。旧运行器不安全兼容，新格式、事务、备份与限制见 [日历期限](../docs/37-calendar-deadlines.md)。

> 经验观察扩展（2026-11-02，未测试）：learning@3 feedback 增加 lesson_observations、lesson_hashes、input_hash，绑定实际提供的经验与用户输入。新回执 practice.lesson_observation_ids 记录随候选提供的反馈版本，scope 区分创作已提供与执行时可用。旧 @1/@2 继续读取，新写入需要新版运行器。见 [经验观察](../docs/36-experience-observations.md)。

> 经验复用扩展（2026-11-02，未测试）：`mind/learning.jsonl` 新策略使用 learning@2 adjustment，含版本、transfer 边界、反馈/标准/输入摘要，与旧 @1 行共存。新增 learning_strategy 经历和 learning_edit.strategy；新创作回执 practice 含 lesson_ids、task，旧回执不补造。旧运行器不具备这些语义，见 [可复用经验](../docs/35-reusable-experience.md)。

> 提取撤回扩展（2026-11-02，未测试）：`mind/facts.jsonl` 可追加 facts@3 的 retract 行，绑定当前模型 claim 和私人 fact_retraction 用户事件的摘要；request.kind=fact_edit、action=retract。新提取将同轮回复编号另存为 generation.extraction_reply_ids，不把同轮输出视为输入证据；旧行读取时兼容处理，不重写。旧运行器不具备这些语义，完整备份保留记录与待完成请求，见 [撤回误读](../docs/34-mistaken-extractions.md)。

> 日期修订扩展（2026-11-02，未测试）：`mind/facts.jsonl` 可追加 facts@2 的 timing 行，与原 facts@1 行共存，绑定原目标/用户输入摘要及日期版本链。新经历类型 fact_time_revision；request.kind=fact_time_edit。旧运行器不具备本轮语义，旧 Python 会拒绝未知格式。完整备份保留记录与请求，见 [日期修订](../docs/33-date-revisions-and-derived-memory.md)。

> 单项日期扩展（2026-11-02，未测试）：facts@1 claim 可选 `starts_on`，仅表示有来源的明确生效起日，不取代记录时刻 `at`；现有 resolve.effective_on 提供变化边界。旧无日期记录不改写、不补齐。只读时间投影应用当前来源/放下/范围规则，备份继续保存原事实账本。见 [时间回查](../docs/32-memory-time-and-effective-dates.md)。

> 材料接收扩展（2026-11-02，未测试）：media@1 接收行可含 `intake_id`；request@1 的 `payload.kind=media_intake` 保存原件编号/摘要、随附说明事件、实际范围、接收时间及外部路径摘要。pending 请求与原件同次接收提交，完成回执与解释同次处理提交；停止处理保留原件，备份必须保留请求。见 [材料接收与恢复](../docs/31-media-intake-and-recovery.md)。

> 原始材料扩展（2026-11-02，未测试）：可选 `mind/media.jsonl`（`seedbank/media@1`）保存接收与放下记录，`media/<SHA前缀>/<SHA>.<扩展名>` 保存不可变原件，均属正式档案。`mind/media-cache.sqlite3` 及其旁文件是可重建缓存，备份排除。接收事件摘要绑定账本，原件状态参与回忆与连续性样本。见 [原始材料与后来的理解](../docs/30-original-media-and-reinterpretation.md)。

> 备份扩展（2026-11-02，未测试）：默认导出 `seedbank/backup@2`，ZIP 中增加 `seedbank-files.jsonl` 分行清单，头部保存清单摘要与总数，读取仍兼容 `backup@1`。生命包内部格式及出生身份不因此改写；恢复仅发布到新目录。见 [长期备份与恢复](../docs/29-long-term-backup-and-restore.md)。

> 人生回顾与日期扩展（2026-11-02，未测试）：可选 `mind/life_story.jsonl` 为 `seedbank/life-story@1`，保存有来源、可修订的章节与转折解释，完整备份保留。日页逻辑编号仍连续；Python 支持带准确 `runtime_gap` 经历的前向日期间隔以及 `## 记录暂停`，旧运行器尚未接入。原日期与出生证不改写。[实现与限制](../docs/28-life-chapters-and-time.md)。

> 披露扩展（2026-11-02，未测试）：可选 `mind/disclosure.jsonl` 保存明确摘录、对外介绍及撤回的版本历史，属于档案而非缓存。新经历/生成记录使用 audience_id / disclosure_version / context_dependencies；旧无范围记录保持私人。完整备份保留这些数据，派生搜索索引可重建。见 [分享范围](../docs/27-disclosure-and-private-memory.md)。

> 长期存储扩展（2026-11-02，未测试）：天数至少四位，可超过 9999；Python 的主要 JSONL 日志使用 `transaction@2` 追加恢复，同时支持旧 `@1` 待恢复事务。缓存可重建，旧档案不迁移。见 [长期存储说明](../docs/20-lifetime-storage.md)。

> 恢复扩展（2026-11-02，未测试）：可选 `mind/.transactions/` 保存活动事务的旧内容与意图；`mind/requests/pending/` 保存未完成输入，`mind/requests/completed/` 保存分目录的完成回执。事务恢复前不得将当前文件视作完整快照；这些输入/回执属于档案，不能当作缓存清理。搜索索引可重建。协议与限制见 [恢复说明](../docs/19-recovery-and-backup.md)。

> 当前扩展见 [development.md](development.md)：可选出生档案、成长事件与数字精力；旧包不重写出生数据。

> 一个生命包 = 一条生命。
> 她的一生是一个文件夹，不在任何服务器上。

## 目录结构

```
<name>.life/
├── birth.json           出生证。写入后不可修改
├── deps.lock            出生时的依赖快照（蛋的副本）
├── genome/              出厂基因（只读）
├── world/               她的世界（只读）
├── life/
│   └── NNNN-YYYY-MM-DD.md   第 N 天，天数至少四位（可为 10000）。一天一篇
├── mind/
│   ├── self.md          她现在的自我认知（派生）
│   ├── traits.json      出生时抽中的特征（派生，日循环用）
│   ├── beliefs.md       她相信的事（派生）
│   ├── mood.json        此刻的心情与体力（派生）
│   ├── brain.json       她现在接的脑（配置，不含密钥）
│   ├── memory.json      记忆设置（去重、每轮提炼上限；旧键 daily_max 保留）
│   ├── vision.json      视觉翻译设置（可选；1.22 起看图自动，见 [senses.md](senses.md) §7）
│   ├── memories.jsonl   记忆流（可修订、可记错；放下以墓碑追加，属于持久档案）
│   ├── experiences.jsonl  原始经历事件、来源与生成方式（可选）
│   ├── development.jsonl  信念、偏好、目标与行动结果版本（可选）
│   ├── search.sqlite3   可重建检索索引（缓存）
│   ├── persona.json     固定样本与基线表现（可选；persona@2；不是人格证明）
│   ├── continuity/      旧基线 archive、逐次 reports 与 latest.json；不参与召回
│   ├── semantic.json    可选嵌入服务配置，默认关闭；密钥只存环境变量名
│   ├── facts.jsonl      可选单项说法、人物和核对历史（权威记录，不是缓存）
│   ├── learning.jsonl   可选目标条件、用户反馈与策略版本（权威记录，不是缓存）
│   ├── relationships.jsonl 可选相处记录、分歧后续、约定与自主联系设置（权威记录）
│   ├── agency.json      意志（兴趣 / 计划 / 边界 / 今天主动了几次；可选，见 [agency.md](agency.md)）
│   ├── bonds.json       关系（熟悉度 / 承诺 / 感谢道歉争执和好；可选，见 [bonds.md](bonds.md)）
│   ├── memorial.json    有限性（纪念日 / 遗憾 / 告别 / 缺席天数；可选，见 [memorial.md](memorial.md)）
│   ├── inner.json       内在（沉默权 / 自我更正 / 梦 / 自我叙事；可选，见 [inner.md](inner.md)）
│   ├── works.json       作品（诗 / 信 / 字符画；可选，见 [works.md](works.md)）
│   ├── hands.json       她替你记着的提醒（可选，见 [hands.md](hands.md)）
│   ├── friends.json     他者（来过的别的鱼 / 谁不在了；可选，见 [friends.md](friends.md)）
│   └── clock.json       生命时钟（只记「上次看到她」；她的时间固定按真实的一天走）
├── friends/             相遇过的生命（只读切片）
├── legacy/              留给后来人的信（`legacy/letter.md`，由 `seed legacy` 生成；可选）
├── lineage.json         谱系
└── journal/             运行日志（可选，不参与人格）
├── inbox/            事件队列（*.json，处理完即删；不属于生命包必需项，见 live.md）
```

## birth.json

```json
{
  "format": "seedbank/life@1",
  "name": "小蓝",
  "born_at": "2026-10-30T08:00:00Z",
  "local_date": "2026-10-30",
  "seed": "<64 位十六进制>",
  "species": { "id": "dafeiyu", "name": "大肥鱼", "version": "0.1.0" },
  "egg": { "id": "dafeiyu", "version": "0.1.0", "sha256": "<蛋的内容哈希>" },
  "deps": { "runtime": { "name": "python", "version": ">=3.10" }, "dependencies": [], "network_required": false },
  "requires": { "python": ">=3.10" },
  "genome": { "identity": "...", "values": "...", "quirks": "...", "traits": "..." },
  "genesis": { "file": "life/0001-2026-10-30.md", "day": 1 },
  "clock": "realtime",
  "hashes": { "pack": "<sha256>", "genome": "<sha256>", "deps": "<sha256>" },
  "ethics": "one-life-pack-one-fish",
  "birth_hash": "<出生证自哈希>"
}
```

## 规则

1. **只追加**：`life/` 只能新增，不能改写已有的一天。勘误另写一条，不覆盖。
2. **只读**：`genome/` 与 `world/` 出生后不可修改。它们是她的出厂设置。
3. **派生**：`mind/` 由历史推导。可以被重置、重建，**不可以手改**。
4. **一个生命包 = 一条生命**：禁止复制运行同一个包（会产生两个"她"）。要延续，重新孵化一颗蛋。
5. **可运行**：`seed check` 通过 = 她仍可被运行。
6. **可携带**：放到任何设备都能运行，不得依赖出生机器。
7. **不存密钥**：`mind/brain.json` 与 `mind/vision.json` 只记配置，API key 永远只从环境变量读。

## 一天的格式

- `life/NNNN-YYYY-MM-DD.md`，其中 `NNNN` 是第几天（4 位补零），日期是**本机日期**。
- 一天包含 `## 对话`、`## 感知`（可缺省）、`## 见闻`（可缺省，1.10）和 `## 今天`（收尾日记）四段，顺序固定为 对话 → 感知 → 见闻 → 今天。
- 感知段是她的**新生儿感官记录**：`- 光：…` / `- 声：…` / `- 主人：…`。原图与录音不进生命包（见 [senses.md](senses.md)）。
- 见闻段是她**读到的**（不是她经历的）：`- 摘要（来源：谁/哪里）`，原文不落盘，只留摘要与来源（见 [cognition.md](cognition.md) §4.1）。
- 若显式开启视觉翻译，感知段还可多一行 `- 看：…`：这是画面**翻译成她的话**之后的结果，原图仍不落盘（见 [senses.md](senses.md) §7）。
- 有 `## 今天` = 这一天已结束；没有 = 还开着。第 1 天在孵化时就已闭合，并自带一次出生光感。
- 只允许一天的对话、感知与见闻追加在 `## 今天` 之前。收尾后不可再改。

## 完整 = 不缺损 / 不中断 / 可重放

- **不缺损**：必需文件齐全，没有断档。
- **不中断**：天数从 1 开始连续，日期逐日递增，没有缺口。
- **可重放**：给了同样的输入与脑，能重演出她的判断。

`check` 会验证：格式、必需文件、**出生证指纹（`birth_hash`）**、`deps.lock` 快照哈希、基因组哈希、
历史连续（天数与日期）、**每一天文件的标题行与结束标记**、**`memories.jsonl` 每一行都能解析且 id 不重复**、
心情文件（`mood` 与 `energy` 的类型和范围）、脑配置（`brain.json` 必须是合法 JSON）；以及**当前 Python 是否满足 `requires`**（支持 `>=` / `>` / `<=` / `<` / `==` / `!=`，可用逗号组合多个条件）——这是「依赖不可得」的检测。
`mind/vision.json` 是可选的：缺失按默认处理（1.22 起看图自动），不影响 `check`。

- 当前 Python 运行时严格读取主要 JSONL：坏行、非对象行或编码错误会报错并保留原文件，不再跳过后继续写入。旧 Node 辅助读取仍采用历史宽容规则。
- 校验是严格的：坏行、断档、被改过的出生证都算「数据损坏」，必须被发现。
- **`check` 不重算 `hashes.pack`**：它是「出生那一刻的整包快照」，用于跨实现验算（`tools/conformance.py`），
  不是历史完整性证明——`life/` 正文后来会长大，用 git / 备份保护它，不靠这个哈希防篡改。
  出生证本身由 `birth_hash` 防篡改，`deps.lock` 与 `genome/` 由快照哈希防篡改。

## 生命时钟

`mind/clock.json`（可选，见 [clock.md](clock.md)）只记录 `last_seen_date`——上一次「她醒着」的本地日期。

**没有模式可选**：每过一个凌晨，她就过完一天；关掉窗口的日子不补写，只记「她睡了几天」。
窗口、网页窗口、载体桥、终端都会自动看钟。老包里的 `mode` 字段（1.7.0 遗留）被忽略。

`birth.json.clock` 是出生证里的历史字段（保留，不影响运行）；运行时一律按真实的一天走。

## 死亡

生命包不会"过期"，但可能死。死亡只有三个条件：

1. 格式不可读（没人能解析了）
2. 依赖不可得（跑不起来了）
3. 全部副本丢失（没有任何拷贝）

**项目使命是推迟它。** 心跳检查（`seed check` + CI）就是在检测死亡是否已经发生。

## 版本记录

- v0.1：初稿。
- v0.2：`deps.lock`、`mind/brain.json`、可运行性与死亡定义。
- v0.3：一天加入 `## 感知` 段；第 1 天自带出生光感。
- v0.4：`mind/memory.json`（记忆卫生）；旧包没有这个文件时按默认严格模式运行。
- v0.5：`mind/persona.json`（人格基线，可选）；`memories.jsonl` 备注忘记墓碑语义。
- v0.6：`mind/clock.json`（生命时钟：事件驱动 / 真实时间）；旧包没有时按事件驱动运行。
- v0.7（1.7.1）：时钟去掉模式，固定按真实的一天走；`mode` 字段作废（忽略）；入口自动看钟。
- v0.8（1.8.1）：`check` 变严格——校验 `birth_hash`、每一天文件的标题行与「非最后一天必须已结束」、`memories.jsonl` 严格解析与 id 唯一、心情与脑配置；`requires` 支持版本区间；孵化遇到非法路径时给中文错误而不是 traceback。
- v0.9（1.9）：`mind/vision.json`（可选视觉翻译设置，默认关）；感知段可选多一行 `看：…`（只写翻译后的文字，原图不落盘）。
- v0.10（1.10）：一天的格式加入 `## 见闻` 段（她读到的，带来源；原文不落盘），段序固定为 对话 → 感知 → 见闻 → 今天。
- v0.11（1.11）：`mind/agency.json`（可选，意志：兴趣 / 计划 / 边界 / 主动次数）；旧包没有时按默认空意志运行，孵化器不写入（不影响出生证哈希）。
- v0.12（1.12）：`mind/bonds.json`（可选，关系：熟悉度 / 承诺 / 事件）；旧包没有时按「刚认识」运行，孵化器不写入；`check` 遇到坏 JSON 或缺 id 的承诺必须失败。
- v0.13（1.13）：`mind/memorial.json`（可选，有限性：纪念日 / 遗憾 / 告别 / 缺席天数）；旧包没有时按「没有特别的日子」运行；`check` 遇到坏 JSON 或列表字段不是数组必须失败；承诺失约与时钟缺口会由运行器自动写入。
- v0.14（1.14）：`mind/inner.json`（可选，内在：沉默权 / 自我更正 / 梦 / 自我叙事）；旧包没有时按「愿意说话、没做过梦」运行；`check` 遇到坏 JSON、列表字段不是数组或 narrative/silence 不是对象必须失败。
- v0.15（1.15）：`mind/works.json`（可选，作品：诗 / 信 / 字符画）；旧包没有时按「还没写过东西」运行；`check` 遇到坏 JSON、`works` 不是数组、缺 id/正文或不认识的 kind 必须失败。

- v0.16（1.16）：可选 `inbox/` 事件队列（`news` / `sense` / `note`），由 `seed live` 或窗口的时钟循环消费；坏事件进 `inbox/failed/`。事件不属于生命包必需项，只读运行器可忽略。

- **v0.17**（2026-10-31，1.17）：`mind/hands.json`（她替你记着的提醒；可选，懒创建）；错过写入 `memorial.json` 的遗憾。

- **v0.18**（2026-10-31，1.18）：`mind/friends.json`（他者：来访记录 / 失联；可选，懒创建）与可选 `legacy/letter.md`（给后来人的信，由运行器生成）；旧包没有时按「还没有别人来过」运行；`check` 遇到坏 JSON、`friends` 不是数组、缺名字或不认识的 status 必须失败。


- **v0.19**（2026-10-31，1.21.1）：`check` 对可选 `mind/*` 文件统一口径：`memory.json` / `vision.json` / `persona.json` 坏 JSON 或字段类型不对必须失败；`growth.jsonl` / `vision.jsonl` 每行必须是 JSON 对象；`clock.json` 坏值必须失败。

- **v0.20**（2026-11-01，1.22）：看图自动——`mind/vision.json` 的 `enabled` 字段作废（保留兼容，不再控制开关）；感知段不再写视觉失败的提示行。
