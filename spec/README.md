# 协议索引

Seedbank 的价值在协议，不在某个具体实现。协议优先，实现可以有多个。

| 文档 | 状态 | 内容 |
|---|---|---|
| [development.md](development.md) | v0.1 | 开放出生、信念修订、偏好、跨天目标、行动回执与数字精力；覆盖下列旧周期与词频规则 |
| [seed.md](seed.md) | v0.2 | 蛋的格式：一颗蛋由什么组成、必须遵守什么 |
| [life-pack.md](life-pack.md) | v0.20 | 生命包的格式：一条生命的一生怎么存 |
| [hatch.md](hatch.md) | v1.0 | 孵化协议：从蛋到个体的确定性过程 |
| [cognition.md](cognition.md) | v0.8（本轮未测试） | 经历来源、关联更正、原档检索、输入容量与放下规则 |
| [clock.md](clock.md) | v1.1 | 生命时钟协议：只有真实的一天，一天怎么开、怎么被睡过去 |
| [i18n.md](i18n.md) | v1.0 | 界面语言：语言包、回退、占位符、不翻译清单 |
| [persona.md](persona.md) | v1.0 | 人格回归协议：换脑时用她过去的话验证"还是不是她" |
| [agency.md](agency.md) | v1.0 | 意志协议：兴趣、计划、边界、主动 |
| [live.md](live.md) | v1.0 | 生活流：`inbox/` 事件队列、三种事件语义、`seed live` 常驻循环 |
| [bonds.md](bonds.md) | v1.0 | 关系协议：熟悉度、承诺的生命周期、感谢 / 道歉 / 争执 / 和好 |
| [memorial.md](memorial.md) | v1.0 | 有限性协议：纪念日、遗憾、告别、缺席天数 |
| [inner.md](inner.md) | v1.0 | 内在协议：沉默权、自我更正、梦、自我叙事 |
| [works.md](works.md) | v1.0 | 作品协议：诗、信、字符画（全部是文字） |
| [hands.md](hands.md) | v1.0 | 手与代价：提醒的生命周期、模型动作、错过进遗憾 | 1.17 |
| [friends.md](friends.md) | v1.1 | 他者与传承：来访、失去、给后来人的信 | 1.18 |
| [senses.md](senses.md) | v1.2 | 感官协议：新生儿的离线光感与声感（原图不落盘）+ 可选视觉翻译层 |
| [brain.md](brain.md) | v1.5 | 脑适配协议：怎么接模型、怎么降级、怎么留档；视觉翻译传输 |
| [channel.md](channel.md) | v1.4 | 载体协议：一行 JSON 进、一行 JSON 出（桥与各种窗口） |
| [runtime.md](runtime.md) | v1.0 | 运行器协议：能力等级 L1–L4、字节级一致性、跨实现验算 |
| [onboarding.md](onboarding.md) | v1.0 | 第一次启动：初次见面向导、`config.json`、本地模型接入、离线成长 |
| `vectors/` | v1.0 | 协议向量：跨实现验算的标准答案 |
| `lineage.md` | 待写 | 谱系、出生证链、遗传（繁殖暂缓，先留接口） |
| `exchange.md` | 待写 | 生命包的交换与相遇 |

## 设计原则

1. **纯文本优先。** 人的肉眼能读懂，不需要专有工具。
2. **目录即格式。** 一个文件夹就是一个完整单位，压缩、拷贝、放进 SD 卡都不改变语义。
3. **自包含。** 不得引用包外的东西（除声明过的运行时）。
4. **可复现。** 给了同样的输入（蛋、种子、时间、机器），就应该得到同样的结果。
5. **实现无关。** 任何人可以用任何语言写运行器；协议不绑定 Python，也不绑定任何厂商。

## 版本记录

- 1.9：`senses.md` v1.1（可选视觉翻译层，默认关）、`brain.md` v1.4（视觉翻译传输与 `mind/vision.json` 设置）、`life-pack.md` v0.9（`mind/vision.json`；感知段可选 `看：` 行）。
- 1.10：`cognition.md` v0.7（见闻：`## 见闻`、`hearsay`、`feed`/`news`）、`life-pack.md` v0.10（一天的第四段：见闻）、`channel.md` v1.2（`feed` 操作与见闻纪律）。
- 1.11：`agency.md` v1.0（意志：兴趣 / 计划 / 边界 / 主动）、`life-pack.md` v0.11（`mind/agency.json`，可选）。
- 1.12：`bonds.md` v1.0（关系：熟悉度、承诺、事件）、`life-pack.md` v0.12（`mind/bonds.json`，可选；`check` 校验承诺结构）。
- 1.13：`memorial.md` v1.0（有限性：纪念日 / 遗憾 / 告别 / 缺席天数；失约自动进遗憾、时钟缺口自动记缺席）、`life-pack.md` v0.13（`mind/memorial.json`，可选）。
- 1.14：`inner.md` v1.0（内在：沉默权 / 自我更正 / 梦 / 自我叙事）、`life-pack.md` v0.14（`mind/inner.json`，可选；`check` 校验结构）。
- 1.15：`works.md` v1.0（作品：诗 / 信 / 字符画；日循环每 4 天写一首诗）、`life-pack.md` v0.15（`mind/works.json`，可选）。
- **1.17（手与代价）**：`spec/hands.md` v1.0；`spec/life-pack.md` v0.17（`mind/hands.json`）。
- 1.17：`hands.md` v1.0（手与代价：提醒生命周期、到期说出口、错过进遗憾）、`life-pack.md` v0.17（`mind/hands.json`，可选）。
- 1.18：`friends.md` v1.0（他者与传承：`mind/friends.json` 来访与失联、`legacy/letter.md` 给后来人的信）、`life-pack.md` v0.18（`mind/friends.json` 与可选 `legacy/`）。
- 1.19：`onboarding.md` v1.0（初次见面向导、配置、本地模型、离线成长）；生命包新增可选 `mind/growth.jsonl`。
