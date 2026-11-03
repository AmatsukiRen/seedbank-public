# 脑适配协议（Brain Adapter）· v1.5

> 脑可以换，她不可以换。
> 一条鱼的思想来自某个模型，但她是谁，从来不写在权重里。

## 0. 边界

- **脑只负责生成**：一句回应、一天的日记、几条记忆提案。
- **运行器负责落笔**：校验、追加、哈希、日期。脑不能改写历史。
- **脑是可替换的**：今天 DeepSeek，明天 Claude，后天本地 Ollama。生命包不因此失效。
- **密钥永不入库**：`mind/brain.json` 只存配置，密钥只从环境变量读。

## 1. 配置文件

`<name>.life/mind/brain.json`：

```json
{
  "format": "seedbank/brain@1",
  "adapter": "stub",
  "model": null,
  "base_url": null,
  "api_key_env": "SEEDBANK_API_KEY",
  "temperature": 0.8,
  "fallback": "stub"
}
```

| 字段 | 说明 |
|---|---|
| `adapter` | `stub` / `openai-compatible` / `anthropic` / `codex` |
| `model` | adapter 为空时的默认模型（stub 为 null） |
| `base_url` | 服务地址。`openai-compatible` 填 OpenAI 兼容 base（默认 `https://api.deepseek.com/v1`）；`anthropic` 填 Messages 兼容 base（默认 `https://api.anthropic.com`，DeepSeek 填 `https://api.deepseek.com/anthropic`） |
| `api_key_env` | 存放密钥的环境变量名。配置文件里**永远不出现密钥本身** |
| `temperature` | 生成温度 |
| `fallback` | 既有 HTTP 适配器保留模板回退行为；`codex` 始终报告错误，不以模板回复掩盖连接失败 |
| `input_budget` | 可选输入预算，运行时缺省为 16000；可保存为 2048–1000000 的整数。它属于运行配置扩展，不加入既有 brain@1 的确定性出生模板 |
| `codex_max_calls` | `codex` 每轮活动最多预留的 CLI 模型调用次数，默认 2，可设 1–3；回答、回查与后续创作共用，日记及其后续生成另计一轮。不是每日、token 或底层 HTTP 次数上限 |

`codex` 是可选的本机 ChatGPT 账号连接，默认模型保留本项目指定的 `gpt-6-astra`。通过官方 CLI 管理登录，不读取或复制认证令牌；忽略 API 地址、密钥、温度与视觉模型字段。当前接入文字能力，图像仍可归档，但不通过该适配器解释。配置和原型出生字节互相独立。详见 [GPT 可选接入](../docs/86-codex-account-provider.md)。

`codex` 超时、登录/额度/协议错误及无效 JSON 均向调用者报错，不静默回退模板。单次 CLI 最多等待 120 秒；SEEDbank 不自行重发，CLI 自身有限的网络恢复不等同于新的应用调用。用量依据 CLI 事件记录，缺失报告明确记为未知；它不是账户账单或本应用之外的总使用量。

出生模板保留上面示例的七个字段，以维持既有孵化向量及跨实现字节一致性。读取时补齐新的可选默认值，显式保存设置时可写入；不因此改写出生证或已有包。参见 [出生与内核验收](../docs/75-life-core-acceptance.md)。

命令行修改：

```bash
python tools/seed/seed.py brain ~/fish/小蓝.life --set openai-compatible --model deepseek-chat
python tools/seed/seed.py brain ~/fish/小蓝.life --set anthropic
python tools/seed/seed.py brain ~/fish/小蓝.life --set stub
# DeepSeek V4.1 Flash：走官方 Anthropic 兼容端点
python tools/seed/seed.py brain ~/fish/小蓝.life --set anthropic \
  --model deepseek-flash \
  --base-url https://api.deepseek.com/anthropic \
  --api-key-env DEEPSEEK_API_KEY
python tools/seed/seed.py brain ~/fish/小蓝.life           # 查看当前脑
```

## 2. 适配器

### stub

离线、确定性、零依赖。不是"假脑"，是**保底脑**：

- 保证蛋在没有网络、没有账号、没有 key 的机器上也能活。
- 同一条鱼的同一天，永远生成同样的日记（可复现）。
- 它写下的记忆 `runner` 为 `stub-v1`，与她清醒时的日子可以区分。

### openai-compatible

`POST {base_url}/chat/completions`，OpenAI Chat Completions 形状：

- 请求带 `response_format: {"type": "json_object"}`，要求结构化输出。
- 适用于 DeepSeek / OpenAI / Ollama / vLLM / 任何兼容服务。
- 默认 base：`https://api.deepseek.com/v1`，默认 model：`deepseek-chat`。
- 密钥从 `api_key_env` 指向的环境变量读。

### anthropic

`POST {base_url}/v1/messages`，Messages 形状（`base_url` 已带 `/v1` 时不重复）：

- 默认 model：`claude-sonnet-4-5`；默认 base：`https://api.anthropic.com`。
- **兼容任何 Messages 网关**，包括 DeepSeek 官方端点 `https://api.deepseek.com/anthropic`
  （模型 `deepseek-flash` / `deepseek-v4-pro`）。
- 响应里 `content` 是块列表：思考块（`type: "thinking"`）不算她的话，
  只取 `type: "text"` 的块；思考 token 也占 `max_tokens`，默认给到 4000。
- 密钥从 `api_key_env` 指向的环境变量读。

## 3. 两次调用

| 调用 | 输入 | 期望输出（JSON） |
|---|---|---|
| 对话 | 世界/自我/信念/召回记忆/当天原文/最近几天 + 她刚刚听到的话 | `{"reply": "...", "memory_writes": [...], "self_edits": {...}}` |
| 日循环 | 当天完整原文 + 前一天日记 + 心情 | `{"diary": "...", "mood": "...", "energy": 0.0–1.0, "memory_writes": [...]}` |

`memory_writes` 每条：

```json
{ "text": "……", "importance": 0.42, "kind": "conversation", "tags": ["主人"] }
```

- `kind` 只能是 `conversation / diary / thought / feeling / correction / forget`。
- 运行器会截断超长文本、丢弃 `importance < 0.3`、限制每天 8 条。
- 脑输出不是合法 JSON 时：优先宽松解析；仍失败则退回 stub 生成，并保留提示。

## 4. 失败与降级

| 情况 | 行为 |
|---|---|
| 网络错误 / 5xx / 超时 | 退回 stub，记 `console.error` 提示，生命继续 |
| 401 / 403（key 无效） | **不静默**：报错并提示检查 `api_key_env`，退回 stub |
| key 环境变量缺失 | 提示一次，退回 stub |
| 输出 JSON 不合法 | 宽松解析 → 失败则 stub 兜底 |
| 模型被弃用 / 服务关停 | 换 `--set` 即可；生命包格式不变 |

**设计取舍：** 宁可让一天由 stub 写下并标明 `runner`，也不让她的时间线因为网络问题断掉。

## 5. 留档

- 每条记忆带 `runner`（`stub-v1` / 模型名），可区分不同脑写的日子。
- `birth.json.seed`、`mind/brain.json`、记忆 `runner` 三者合起来，足以重放一段判断。
- 完整 prompt 与模型版本留档在 1.1（`journal/`），1.0 只记录 `runner`。

## 6. 不做什么

- 不为脑绑定特定厂商 SDK（只用标准库 HTTP）。
- 不把 key 写进生命包（宪法要求她可被复制而不泄露主人隐私）。
- 不允许脑直接改动 `life/` 的历史。
- 不在 1.0 做多脑投票/路由（一个时刻只有一个脑，可换，不可并存）。

## 7. 设置面板与本地模型（1.3）

设置有两处：独立窗口里的「⚙ 设置」面板，和命令行 `seed brain`。两者写的是同一份文件。

| 设置 | 存在哪 | 说明 |
|---|---|---|
| `adapter` | `mind/brain.json` | `stub` / `openai-compatible` / `anthropic` / `codex` |
| `model` / `base_url` | `mind/brain.json` | 换模型、换端点 |
| `api_key_env` | `mind/brain.json` | 只存环境变量名；本地端点可为空 |
| `temperature` | `mind/brain.json` | 0~2 |
| `strict` / `daily_max` | `mind/memory.json` | 记忆卫生（见 [cognition.md](cognition.md)） |
| `vision.model` | `mind/vision.json` | 视觉翻译模型覆盖（1.22 起看图自动，见 §8） |

**本地模型（离线）：** Ollama、LM Studio、vLLM 都提供 OpenAI 兼容端点。
当 `base_url` 的主机是 `localhost` / `127.0.0.1` / `::1` / `0.0.0.0` 时，**不要求 key**（也不会发送 Authorization 头）。
常见地址：`http://localhost:11434/v1`（Ollama）、`http://localhost:1234/v1`（LM Studio）。
本地模型也可以完全断网使用——生命包和记忆都在文件里，只有她说话需要模型；有桩（stub）兜底时，断网也不会断掉她的时间线。
弱模型的记忆更容易乱，默认开启严格记忆卫生；设置面板和命令行都能调。

**测试连接**（`seed brain <包> --test` 或面板按钮）只发送一句最小请求，不写生命包。

## 8. 视觉翻译传输（1.9；1.22 起自动）

视觉翻译层把一张图交给脑，要求它用她的世界语言说出画面；只有翻译后的文字进生命包。
原生感官（[senses.md](senses.md)）不经过这一层。

- **何时用**：1.22 起**自动**——只要给图（`seed sense --image`、窗口、QQ、载体 `image` op），
  就试着让脑看懂；`day` / `chat` / `bridge` 的其他操作不触发视觉。
- **跳过**：`seed sense --vision off`，或运行器传 `vision=False`。
- **设置**：`mind/vision.json`（`seedbank/vision@1`，可选；缺失或损坏按默认处理）：

```json
{
  "format": "seedbank/vision@1",
  "model": "",
  "max_side": 1024
}
```

| 字段 | 说明 |
|---|---|
| `enabled` | 1.22 起仅为兼容旧包保留，**不再控制开关**（旧包里有 true/false 都按自动处理） |
| `model` | 视觉模型覆盖；空 = 跟随 `mind/brain.json` 的 `model` |
| `max_side` | 预留的图像边长上限（256~2048）；1.9 参考实现不缩放原图，靠 8MB 上限保护 |

命令行（`--vision-model 名字`；不带参数时显示当前设置）：

```
python tools/seed/seed.py brain ~/fish/小蓝.life --vision-model deepseek-flash
python tools/seed/seed.py sense ~/fish/小蓝.life --image 窗外的光.png
```

- **传输**：原图只在内存里转 base64 转发一次（PNG / JPEG / WebP，按文件头识别；单张 > 8MB 拒绝；
  BMP / PPM 等只有原生眼睛能看）。视觉请求**不**要求 JSON 输出——要的是一句话，不是结构化判断。
  - `openai-compatible`：`messages=[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":"data:<mime>;base64,<b64>"}}]}]`
  - `anthropic`：`content=[{"type":"image","source":{"type":"base64","media_type":<mime>,"data":<b64>}},{"type":"text","text":prompt}]`
- **降级**：`stub` 脑、缺 key、网络错误/超时、格式不支持、图太大……任何原因都不抛异常；
  原生光感照旧，这一天继续；失败原因只放在返回结构的 `vision.reason` 里（1.22 起不再写进她的日记）。
- **留档**：每次成功翻译追加一行 `mind/vision.jsonl`：`at` / `sha256` / `provider` / `model` / `text`。
  记录后可重放，不依赖 API；原图本身从不落盘。

## 版本记录

- v1.0：初稿（三类脑、两次调用、降级与留档）。
- v1.3：设置面板与 `seed brain` 扩展；本地端点免 key；记忆卫生设置。
- v1.4（1.9）：可选视觉翻译传输（PNG / JPEG / WebP 的 base64 图像消息、8MB 上限）；`mind/vision.json` 设置；翻译结果写 `mind/vision.jsonl`。
- v1.5（1.22）：视觉翻译自动化——去掉 `enabled` 开关与「失败提示」行；有视觉的脑时自动看懂，没有就安静退回原生光感。
