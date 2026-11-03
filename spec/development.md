# 开放出生与经历驱动的成长 · v0.1

目标历史回查扩展（2026-11-03）：每个 goal 事件只读投影为 `goal_history/goal_archive`，引用物理事件编号与原时间，不把逻辑目标编号当作某一版本。检索旧版本时附上最新可见记录的状态、理由、时间和场景；最新来源不可用不回退旧 active 状态。原目标限主人范围，分享使用明确引用副本；后续来源、预算裁剪和人生回顾均保持原版本关联。原账本格式不变，派生索引 v11、提示 v39，详见 [旧目标与修订理由](../docs/protocol-guide.md#agency)。

行动理由回查扩展（2026-11-03）：有原始理由的 outcome 只读投影为 `kind=action_proposal/origin=action_archive`，沿用原 `d_` 回执编号与账本锚点。全档案检索、语义候选及人生回顾可引用；可见性与后续依赖按原提议和执行来源共同检查，模型纠错不能重写回执。v10 搜索索引为可重建缓存，账本无新格式、不回填旧行。v38 完整核心 343 项通过，见[行动理由全档案回查](../docs/protocol-guide.md#agency)。下条未接入检索是 07:18 历史状态。

行动说明扩展（2026-11-03）：`development@1` 的 `outcome.data.proposal` 可选保存 `seedbank/action-proposal@1`，字段为 `at/reason/reason_truncated/source/evidence/generation`。理由最多 1000 字，超长明确标记；提议的生成信息与执行/创作的生成信息分开，成功、失败和未开始均保存原提议。旧回执和直接请求创作不补写理由。来源与接收范围独立检查，未来引用继承提议依赖，裁减整条回执时同步移除。329 项核心与相关专项已通过，范围及更早理由尚未接入检索的限制见 [行动理由与来源](../docs/protocol-guide.md#agency)。下方各轮“未测试”是对应历史时点，当前证据见 [总表](../docs/acceptance.md)。

解释关联扩展（2026-11-02，未测试）：story_lineage 追溯旧 life_story 版本对看法/偏好/目标、对话及记忆的来源影响；读取投影 interpretation_updates 最多展开三项，保留总数，不自动改写状态。受限范围不透露后续私人版本，无效当前解释不恢复旧版。实际输入裁剪、来源依赖及回退提议限制同步，提示词 v28，无新账本。见 [旧理解与当前选择](../docs/protocol-guide.md#agency)。

分阶段提议扩展（2026-11-02，未测试）：私人 development.project 整组创建二到四个新目标，依据实际提供的输入、已有完整条件及局部阶段引用排序保存。goal_project 经历绑定原提议与真实编号，初始阶段条件使用 learning@5 并核对对应关系；不覆盖旧条件、不自动执行或完成。聊天回执与学习总览接入，提示词 v27。见 [分阶段安排](../docs/protocol-guide.md#agency)。

经验检索扩展（2026-11-02，未测试）：learning.for_goal 可接收本次 task，在当前可见且有效的同方向经验中做本地文字检索；retrieval 仅为读取投影。观察兼顾相关性与相反判断，预算裁剪保留高相关候选；实际提供编号与来源依赖沿用原协议。无新账本格式，提示词 v26。见 [按任务找回经验](../docs/protocol-guide.md#agency)。

前置目标扩展（2026-11-02，未测试）：用户可设置版本固定的前置目标，learning@4 保存关系；readiness 递进核对当前完成依据，创作/反思的来源事件保存执行前版本，完成时不倒推旧成果。见 [目标之间的先后关系](../docs/protocol-guide.md#agency)。

跨日选择扩展（2026-11-02，未测试）：development.prior_choices 展示完整历史中仍可回应的旧专注意图、回执与条件核对，并传播实际提供来源。新的 continue/revise/release 关联使用 plans@4，目标完成状态不自动改变。见 [跨日的打算](../docs/protocol-guide.md#agency)。

计划结束条件扩展（2026-11-02，未测试）：可选 checkpoint 固定一份完整目标条件，核对同计划版本下的成果及当前反馈；复用目标的内容指纹、条件与成果组规则，不自动完成长期目标。plan_review 可带当前 checkpoint 投影及来源依赖，新选择记录使用 plans@3，详见 [计划结束条件](../docs/protocol-guide.md#agency)。

用户创作失败扩展（2026-11-02，未测试）：直接 compose 的可识别适配器失败、空输出与回退模板保存 runtime action_attempt 经历及 failed/started 回执，无作品引用；practice.scope=available_at_execution 不表示材料已发送或采用。持久练习请求的 complete 表示处理完成，需另看 succeeded；同编号失败重放不重新执行。准备、保存与恢复错误仍传播。见 [用户创作与失败记录](../docs/protocol-guide.md#agency)。

行动阶段扩展（2026-11-02，未测试）：outcome 可选 attempt_state=started/not_started/unknown；新自动动作区分准备与执行，旧 failed 缺信息时为 unknown。skills.attempts 只计已进入流程，unknown_attempts 单列未知，completed 仍仅指动作成功；skill_dependencies 覆盖实际统计来源。见 [行动阶段与统计](../docs/protocol-guide.md#agency)。

跨渠道结果扩展（2026-11-02，未测试）：动作统一遵守日程，但目标/证据仍按接收范围过滤。聊天 reply 附运行器回执，actionReportEventIds 保留独立来源，外部重放逐一核对。等待重新选择不被当天刷新覆盖，外部错误不携带私人诊断。见 [跨渠道选择与结果](../docs/protocol-guide.md#agency)。

计划回顾扩展（2026-11-02，未测试）：development@1 outcome 可选 plan_reference（seedbank/plan-link@1）关联单条计划事件及执行来源。摘要 plan_review 区分模型提议与用户直接要求，进入私人生活页与有预算的上下文，不自动完成计划。详见 [计划版本与实际行动](../docs/protocol-guide.md#agency)。

每日选择扩展（2026-11-02，未测试）：daily_plan 独立于目标修订与 actions，允许选择已提供 active 目标、休息或留白。运行器记录模型意图及来源，依当前选择约束私人自动创作/反思；未执行的 blocked 回执不计作练习。具体字段、plans@2 与用户验收见 [每日选择](../docs/protocol-guide.md#agency)。

计划历史扩展（2026-11-02，未测试）：当天安排追加保存原选择、来源、目标版本及后续替代关系。用户目标建立/编辑/完成与重新安排同次事务，旧计划不被覆盖。计划依据失效不进入普通上下文，旧目标版本提示重新安排，见 [计划历史](../docs/protocol-guide.md#agency)。

行动扩展（2026-11-02，未测试）：四类自主动作的写入及成功回执同次事务；普通失败回退动作后记录失败，恢复冲突向上抛出。每日文字计划不再因关联动作成功自动完成，旧完成标记待核对，见 [行动回执与计划](../docs/protocol-guide.md#agency)。生命周期按用户明确选择，由经历与明确选择逐渐决定，暂不设固定寿命；具体终点尚未实现。

经验取舍扩展（2026-11-02，未测试）：创作回执 practice.strategy_choices 为可选 strategy-choices@1 数据，与 creation metadata 同存；基于实际裁剪后候选接受 adopt/adapt/skip/uncertain 和简短说明，绑定经验版本与作品。它是同次响应中的模型自述，不是内部思考、独立规划或能力证明。后续反馈/观察可以对照相反评价，来源不可用时不继续引用。见 [创作取舍](../docs/protocol-guide.md#agency)。

纠错读取扩展（2026-11-02，未测试）：成长提案的证据保留 fact_notes，用户明确的单项 correction 停用已知旧派生依据；新输出追踪从当天对话注释取得的核对来源。原话和独立事项保留，尚无精细语义失效保证，见 [纠错贯通](../docs/protocol-guide.md#memory)。

关系扩展（2026-11-02，未测试）：相处理解与用户报告追加保存于 relationships.jsonl；约定绑定本目标当前条件版本，履行需具体成果和有效反馈。期限经过不自动判失约，交流次数不再增加熟悉度。明确暂停自主开口优先于 force，提醒另行管理。详见 [相处与约定](../docs/protocol-guide.md#relationships)。

本扩展覆盖旧协议中“默认小鲸鱼”“词频直接生成兴趣”“逢三天做梦／四天作诗”“开口即完成计划”的规则。既有生命包不迁移出生身份，不改写出生证、基因组或历史日记。

## 出生身份

首次创建默认使用 `eggs/open.egg`。它不预设生物种族、性别、身体和童年；种子图形只是桌面入口，不是已经发生的生物事实。通用模型知识不属于个人亲历。初始倾向可发展，不设固定寿命或强制繁殖。

可选 `genome/profile.json`，格式 `seedbank/profile@1`：

| 字段 | 含义 |
| --- | --- |
| `identity_mode` | `open` 表示开放自我；`seeded` 表示种子指定背景 |
| `avatar` | 当前支持 `seed` / `dafeiyu`；未知值回落到种子图形 |
| `initial_self` | 初始自我记录，可含 `{name}` |
| `initial_belief` | 初始认识，可含 `{name}` |
| `birth_memory` | 出生记忆，可含 `{name}` |
| `initial_perception` | 已有出生输入；空字符串表示无感知输入 |

文件随孵化复制进基因组，并计入基因组哈希。它是出生背景，不是后天成长文件。Python 和 Node 孵化器均支持此扩展。没有 profile 的 `dafeiyu` 保留原孵化模板；其他种子使用中性默认值。旧 `dafeiyu` 生命包仍显示鲸鱼。

## 成长事件

权威记录为可选的 `mind/development.jsonl`。首次发生变化时建立，每行一个 `seedbank/development@1` 事件：

```json
{
  "format": "seedbank/development@1",
  "id": "d_随机UUID",
  "at": "ISO时间",
  "day": 2,
  "kind": "belief",
  "source": "life/0002-日期.md",
  "runner": "模型适配器名称",
  "data": {
    "id": "b_稳定ID",
    "text": "当前看法",
    "confidence": 0.5,
    "reason": "为何形成或修正",
    "evidence": [{"id": "current", "source": "life/0002-日期.md", "kind": "current_interaction"}]
  }
}
```

事件种类：

- `belief`：有依据的个人解释；包含 `text/confidence/reason/evidence`。confidence 是模型自评，不是统计校准概率。
- `preference`：`topic/stance/reason/evidence`；stance 为 `like/avoid/unsure`。
- `goal`：`title/next_step/status/reason/evidence/created_day`；status 为 `active/paused/completed/abandoned`。
- `outcome`：仅运行器生成；包含 `action/status/detail/goal_id/artifact`。

后续修订使用同一 data.id；新事件追加，旧解释可追溯。读取按 ID 归约为当前状态。历史格式损坏时停止追加，保留原文件。当前实现适合单进程、单生命包串行写入；桌面通过会话锁串行处理。多个独立进程同时写同一个包不受支持。

模型可在对话、主动决策和日记 JSON 中提交 `development`。每类每轮最多三条；新建不自编 ID。提案必须有具体理由和可引用的记忆 ID，或 `current`（本次对话／日记文件）。未知 ID、被忘记的记忆和梦不能作为可引用的亲历证据。见闻来源仍标为 hearsay，不能据此声称亲历。

运行器验证来源标识和结构，不验证自然语言解释的真假；有来源也可能误解，允许后续降低把握并修订。老 `self_edits` 与 `beliefs.md` 保留兼容，属于历史记录；新提示词优先使用结构化成长。

## 目标与行动

最多六个 active 目标。每日计划优先承接 active 目标的下一步；没有目标时允许留白。低精力优先休息。跨天保留目标，允许暂停或放下，已结束目标不原地重开。

`actions` 是 JSON 数组，每轮最多执行一项本地动作；无动作时省略或使用 `[]`。兼容单个非空对象并归一成一项数组，后续仍经原权限、前提及调用额度检查。提议说明不是运行器执行证明。

| type | 参数 | 成功回执代表什么 |
| --- | --- | --- |
| `compose` | kind、topic、reason、可选 goal_id | 作品已保存；不代表作品优质或技能已掌握 |
| `reflect` | memory_ids、text、reason、可选 goal_id | 引用实际记忆的反思文档已保存；解释仍可修正 |
| `remind` | text、due_on（旧版 due_day 保留原日页含义）、可选 goal_id | 提醒已建立，尚未送达 |
| `rest` | reason、可选 goal_id | 选择休息；不会立即恢复精力 |

创作与反思的自主执行最多每日四次，精力低于 0.15 暂不执行。失败留下失败回执，不自动完成目标。行动产物写入 `mind/works.json` 或 `art/reflections/`；作品不再按 120 件截断，避免目标回执失去引用。

主动说话和目标行动的成功回执都不自动完成当天文字计划。回执只表明动作实际结果，关联关系不证明动作满足文字计划；旧 done 标记只显示为依据待核对。长期目标还需满足 `mind/learning.jsonl` 中当前版本的逐项条件。`completion_evidence` 将每项条件关联到本目标成功回执：同成果名称必须使用同一次尝试，不同成果名称不能复用同一回执。作品需匹配原保存指纹；feedback 条件需当前版本的明确用户好评，artifact 条件只检查指定类型已保存。模型不能降低既有条件或改写目标含义。条件及评价仍非客观质量认证。新目标 ID 到下一轮才可由模型引用。

可选追加文件 `mind/learning.jsonl` 保存 criteria / feedback / adjustment。反馈修订不重写历史完成事件，但重新计算 `completion_current`。旧完成目标没有条件依据时显示历史未核实，不再把它当作能力证明。模型 `learning_updates` 仅可引用本次提供的当前反馈，形成下一次策略；创作可携带相同条件的历史反馈，不能用另一目标的成果完成自己。Qt / CLI / 桥操作、版本保护和请求恢复见 [目标与反馈](../docs/protocol-guide.md#agency)。

主动决策允许空回复，仍可行动；选择什么都不做也计入本轮决策节流，避免每次心跳重复请求模型。梦和自我叙事由日记的 `inner_activity` 选择，不按天数取模触发。

## 数字精力

可选 `mind/body.json`，格式 `seedbank/body@1`，含 energy、updated_at、resting、last_activity。每小时空档恢复 0.08，每次最多计入八小时；这是产品资源模型，不是生理或意识模型。

对话、主动决策、创作、反思、日记分别消耗 0.015、0.02、0.08、0.04、0.02。读取状态不落盘，活动结算时更新。不能由模型任意回填精力。系统时钟倒退不产生恢复奖励。

## 入口与兼容

- 桌面生活页展示长期目标、当前看法和行动结果，保留现有五页结构。
- `seed development <生命包>` 输出当前摘要；桥请求 `{"op":"development"}` 返回同样字段。
- 桥 message 响应增加 `development_changes` 和 `action_results`。
- `seed check` 增加可选成长记录和精力文件读取检查，旧包缺文件仍有效。
- 离线 stub 只提供确定性基础响应，不伪装为成熟推理。`seed grow` 只整理重复话题线索，不根据词频建立信念或喜欢；旧 growth.jsonl 保留。
- 旧人格措辞相似度工具仍在，其结果不能用于判定合理成长是“人格损坏”；成长前后的评估需要后续独立设计。

内核首次交付时未执行测试；用户后续授权后的回归结果与兼容修复见 `docs/17-diary-selection-fix.md`。体验步骤仍见 `docs/16-open-life-core.md`。

## 目标提出场景与首次来源

正常模型入口在 `generation.proposal_activity` 中记录 `conversation`、`initiative`、`forced_initiative` 或 `diary`，由运行器覆盖填入，不接受模型自行声明为真实场景。普通新目标的 `origin=model` 与分阶段目标一致，仅表示提交者，不证明独立意愿。

`current_state` 与摘要的目标可含只读 `provenance.first/latest`，分别来自该 ID 的首条和最新目标事件。每项含 `kind`、`event_id` 与实际依赖；`kind=user` 表示正式用户修改入口，`fixed` 表示明确的固定/回退生成，其余使用上述活动类型。没有当时活动记录为 `unrecorded`，不得从后续版本或模型名推断。

首条和最新条独立检查来源、生成依赖和交流范围；不可用时仅返回 `{"kind":"unavailable"}`，不暴露事件编号或依赖。投影不保存回原始目标事件，原 `development@1` 行格式保持兼容。活动类型只提供形成与修订的上下文，不能作为自然自主性、学习效果或人格完整性的证明。

## 同标准策略的后续观察

2026-11-03 扩展，尚未执行测试：`learning@3` 观察的 `lesson_id` 可指向成果回执实际提供的 `practice.adjustment_ids` 或 `practice.lesson_ids` 中的策略，仍需 `scope=provided_to_creator`、当前来源和原作品可核对。两个提供列表保留其原含义，不把同标准重复尝试写成跨任务迁移。

`adjustments` 与 `lessons` 均可附只读 `observations/observation_count/observation_evidence`。历史字段 `lesson_observation_ids` 记录本任务实际提供的这两类观察，生成依赖沿用其来源；裁剪和来源失效不补写原回执。列表投影 `offered_lessons` 兼容原界面字段名，展示两类已记录策略。模型取舍与用户观察仍分开，不自动升级为掌握或因果结论。见 [同目标观察](../docs/protocol-guide.md#agency)。

## 看法与偏好的历史引用

2026-11-03 扩展，尚未执行测试：每条原 belief/preference 事件可投影为 `belief_history` / `preference_history`，`origin=judgment_archive`，沿用原 `d_…` 事件编号；`judgment_id` 与 `judgment_kind` 指明逻辑记录。来源为 `mind/development.jsonl#事件编号`，正文明确是当时表达。该投影只读取原账本。

`judgment_version` 是动态的最新可见说明，记录当前可用性、最新事件、时间、理由与依赖。最新版本不可用时不回退旧态度；不把当前说明存入旧事件。历史来源遵循原撤回与主人范围，明确分享仅形成片段副本。人生回顾可引用历史表达；最终提示保留当前说明及其依赖，普通记忆纠错不覆写成长事件。索引 v12、提示 v41；见 [看法与偏好历史](../docs/protocol-guide.md#agency)。
