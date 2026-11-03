# 种子格式（Seed Format）· v0.2

> 一颗蛋 = 一个自包含目录。
> 它必须能在断网、没有 Seedbank 服务器、没有账号的情况下被孵化。

## 目录结构

```
<breed>.egg/
├── species.json         必需   物种身份：名字、外貌、语气、对「脑」的要求
├── genome/
│   ├── identity.md      必需   她出厂时的自我认知（第一人称）
│   ├── values.md        必需   她的原则
│   ├── traits.json      必需   可继承的特征池，孵化时抽取 → 个体差异的来源
│   └── quirks.md        可选   习惯的人话说明
├── world/
│   └── bible.md         必需   她的世界：她知道什么、不知道什么
├── genesis.md           必需   她记得的第一天
├── hatch/               可选   孵化器附加配置
├── deps.lock            必需   最低依赖声明
└── README.md            可选   给领养者看的话
```

## species.json

```json
{
  "format": "seedbank/seed@1",
  "id": "dafeiyu",
  "name": "大肥鱼",
  "aliases": ["蓝色大肥鱼", "鲸鱼娘"],
  "version": "0.1.0",
  "locale": "zh-CN",
  "summary": "一只住在小房间里的蓝色鲸鱼，觉得自己大概来自海里。",
  "appearance": { "body": "蓝色圆润的小鲸鱼", "eyes": "大而亮" },
  "voice": { "tone": "软、慢、有点笨拙的温柔", "forbidden": ["自称 AI", "谈论模型"] },
  "brain": { "adapter": "any", "required_capabilities": ["chat", "structured-output"] },
  "license": "CC-BY-SA-4.0"
}
```

| 字段 | 说明 |
|---|---|
| `format` | 格式版本，必填。孵化器据此判断能不能读 |
| `id` | 物种 ID，ASCII、小写、连字符 |
| `name` | 物种名，可任意语言 |
| `brain.adapter` | `any` = 不绑定模型；也可指定首选适配器 |
| `license` | 物种内容（基因、世界、第一天）的授权 |

## deps.lock

```json
{
  "format": "seedbank/deps@1",
  "runtime": { "name": "python", "version": ">=3.10" },
  "dependencies": [],
  "network_required": false
}
```

`deps.lock` 决定这颗蛋还能被孵多久。依赖越少，蛋活得越久。
**声称要联网的蛋，必须写明原因，并在无网环境证明可孵化。**

## 铁律

1. **自包含**：不得引用蛋之外的资源（除声明的运行时）。
2. **离线可孵**：断网、无账号、无服务器，也必须能孵出来。
3. **可复现**：同样的种子 + 同样的名字 + 同样的时间 → 同样的个体。
4. **无私有依赖**：不得依赖不可替代的私有服务或账号。
5. **蛋只读**：孵化不得修改蛋本身。
6. **版本化**：`format` 字段必须声明，格式变更必须升版本。

## 换脑不换种

模型不是物种。

| 你换的东西 | 结果 |
|---|---|
| 模型（DeepSeek → Claude → OpenAI → 本地） | 还是同一种鱼，换了个脑子；必须通过人格回归测试 |
| 蛋 | 换了一个物种 |
| 生命包 | 换了一个个体 |

物种由 `species.json` + `genome/` 定义，脑由运行时决定。
**同一颗蛋 + 不同的脑 = 同一种大肥鱼。**

## 与生命包的关系

蛋只定义「她出厂时是谁」。
孵化之后，她的一切都在生命包里，蛋不再参与她的人生。
蛋可以被无限次孵化——每孵一次，就是一条**新的、不同**的生命。
