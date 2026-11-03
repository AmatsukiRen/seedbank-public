# 开发与扩展：给同一个体更多入口

[SeedBank](../README.md) · [参与开发](../CONTRIBUTING.md) · [最小 Python 客户端](../examples/bridge_client.py)

桌面窗口只是一个入口。我们希望一个个体可以换用不同的模型、声音和身体，也可以来到新的平台；经历、记忆的来源和明确作出的选择继续留在生命包里。欢迎把自己擅长的部分接进来。

**当前状态：** 以下接口来自原研发实现，按 2026-11-03 源码整理，应用核心尚未迁入本库。这些接口尚未作为稳定插件 SDK 发布。现在没有插件商店、统一安装器、热加载、权限沙箱或公开 HTTP 服务。新增 AstrBot 转接只监听本机、使用独立令牌、只接收消息，不是通用核心 HTTP API。

## 1. 选择一条接入路线

| 想做什么 | 已有机制 | 贡献的切入点 |
| --- | --- | --- |
| 让个体来到聊天平台 | Python JSON Lines 载体桥；QQ / OneBot；新增 Discord、Telegram、飞书、钉钉及 AstrBot 转接 | [渠道配置与范围](channels.md)；继续完善附件、身份映射及投递恢复，新增项待验收 |
| 使用新的模型服务 | `stub`、`openai-compatible`、`anthropic`、`codex` 适配器；13 家云服务预设 | [模型服务接入](model-services.md)；服务适配、结构化输出、请求预算、超时和取消 |
| 做另一种界面或身体 | Qt Quick / QML 桌面界面、Live2D 本地模型、独立载体桥 | 手机端、桌宠、无障碍界面或 VR 载体；这些新载体是贡献方向，并非已有成品 |
| 加入新的工具能力 | 桥接操作、事件输入、目标与行动记录 | 在核心中明确能力边界，记录来源、尝试和结果；当前不能把任意脚本扔进 plugins 文件夹运行 |
| 改进记忆和成长 | 来源、修订、放下、目标、作品与反馈的已有机制 | 更好的查看和解释、更可靠的检索、失败反馈及人工回归场景 |
| 建设插件生态 | 尚无统一插件运行时 | 一起设计 manifest、能力声明、授权界面、兼容版本、安装卸载和隔离机制 |

模型适配器只负责与模型交互；载体负责平台、输入输出和呈现；生命包保存个体的经历。不要让每个新平台再维护一份互相失联的“人格”。新增内置渠道经桌面的同一个 Session 顺序处理，其网络子进程不打开生命包。开发自定义 JSON Lines 客户端时，仍不要另开独立写会话同时使用一个包：初次接入请让一个桥接进程持有一个独立人工包，并先关闭使用这个包的 GUI。

## 2. 已有协议：本地进程 + 逐行 JSON

启动方式，二选一；路径由开发者指定：

```powershell
# 原研发源码环境；本库尚无 tools/seed/seed.py
python <原研发目录>/tools/seed/seed.py bridge <独立人工包.life> --brain stub

# 含命令行入口的 Windows 研发交付
seedbank.exe bridge <独立人工包.life> --brain stub
```

`stub` 是离线模板。启动桥接会进行恢复工作，部分查询会打开当天记录，因此“只发 hello”也不能承诺磁盘完全不变。请不要拿真实个体练手。

- UTF-8，stdin 每行一个 JSON 对象，stdout 每行一个 JSON 响应；不是 HTTP、WebSocket 或 SSE。
- 子进程不会主动吐出握手，客户端先发 `hello`。成功握手的 `protocol` 为 `seedbank/bridge@1`。
- 请求中有 `id` 时响应原样带回，用它关联这一轮。当前串行处理；初版客户端一次只保留一个未完成请求。
- `ok: false` 时读取 `error`，不能把错误当作角色回答。stderr 作为诊断通道处理，不混进 JSON 流。
- `stop` 或关闭 stdin 结束桥接进程；这**不是**个体休眠，也不会替你结束日记中的一天。
- `hello` 返回名称、版本、出生与状态信息，当前不提供完整能力清单。适配器应明确支持的协议和操作。

发送：

```json
{"id":"hello-1","op":"hello"}
{"id":"message-1","op":"message","request_id":"demo-message-001","text":"这是人工接入样例。今天一起讨论了一张雨天便签。","speaker":"样例使用者","person_id":"owner"}
{"id":"recall-1","op":"recall","query":"雨天便签","k":3}
{"id":"stop-1","op":"stop"}
```

这些是协议示例，不是实测输出。下面的客户端默认只握手、读取生命周期状态并退出；传入 `--message` 才会把明确给定的人工内容写入指定包。它强制使用 `stub`，不读取密钥，也不自动创建或查找生命包。

```powershell
python examples/bridge_client.py --pack <独立人工包.life> --exe <seedbank.exe路径>
# 或：--seed-script <原研发目录>/tools/seed/seed.py
```

## 3. 第一批值得理解的操作

| 操作 | 用途与关键字段 | 注意事项 |
| --- | --- | --- |
| `hello` / `status` | 协议、个体与运行状态 | 打开/恢复可能写入生命包，不作为无副作用探测 |
| `message` | `text`、`speaker`、`person_id`、`audience_id`、`request_id` | 可能推进当天活动和请求模型；模板模式的行为不证明真实模型效果 |
| `recall` | `query`、`k`；返回带来源的 `memories` | 语义检索是否联网取决于配置；示例强制 stub |
| `memories` | `action: list/history/revise/forget`；详情用 `memory_id` | 修订需理由，`change_type` 区分纠错与后来改变；保留历史 |
| `image` / `sound` | `path`、`note`、身份与 `request_id` | path 是运行桥接的机器可访问的本地文件；媒体可能归档，图片理解可能外发；不要直接接受群友指定任意本地路径 |
| `event` | `kind`、`text`、`source`、`process` | 标明谁提供、从哪里来；处理可能触发模型，不等于任意函数调用接口 |
| `work` / `learning` | 作品、练习与反馈 | 具体 action 各有字段；不能把“提出想法”写成已执行成功 |
| `relationships` / `disclosure` | 身份、相处边界、披露约定 | 平台适配器仍需自行认证用户；传入 person_id 不是身份验证 |
| `life_story` / `agency` / `development` | 回顾、目标与成长记录 | 记录来源及修订，避免给推断冒充个人选择 |
| `lifecycle` | `action: status/pause/resume` | 状态变更需明确选择、`confirmed: true` 和当前 `expected` 修订号 |
| `requests` / `resume` | 查未完成请求；按 `request_id` 恢复 | 顶层 resume 是恢复请求，**不是**生命周期恢复；不自动无限重试 |
| `day` / `tick` | 人工推进或按时间处理 | 会改变档案、可能调用模型；不要把 UI 刷新循环接到 day |

细节目前以原研发源码的 `seedbank/bridge.py` 为准，以上不是完整的稳定 API schema。应用迁入后应补齐字段约束、响应示例和兼容性用例。源代码位置：`tools/seed/seedbank/bridge.py`、`brain.py`、`quick/` 和 `adapters/qq-onebot/`；这些路径当前属于原研发库，不能在本库直接运行。

## 4. 请求重试、休眠和记忆的约定

**关联编号与写入编号分开。** `id` 用于这一轮响应；支持持久化请求的写操作使用 `request_id` 识别同一次尝试。断线不代表未执行。先查看未完成请求，再按同一内容、同一 `request_id` 恢复，不要换个新编号盲目重发。不是每个操作都支持同样的幂等保证。

**休眠是个体状态。** 外部载体应反映生命周期状态，暂停主动调度，不因为重新连接就自动恢复。恢复必须来自明确选择；读取当前 revision 再提交 `lifecycle` 的 resume。外部工具的长任务也需由适配器自行停止或取消，核心无法替你管理任意外部进程。

**来源随记忆一起走。** 展示召回结果时保留来源、修订链及是否放下。不要只复制一句“事实”到插件私有库，然后永远忽略它的更正。私人会话与公开频道的受众不同；不要把 owner 身份用于所有群成员。模型、附件和日志的实际外发范围应让使用者看得见。

## 5. 一起定义插件规范

下一步值得共同设计的是：插件 ID 和版本、核心协议兼容范围、入口命令、请求能力、允许访问的数据、离线/联网声明、停止与卸载行为，以及可撤回的用户授权。

这些仍是设计任务，暂不提供看似能用的 `manifest.json` 或安装命令。可先提交小型提案，说明：谁使用、输入与输出、接入哪一层、是否写生命包或联网、失败如何恢复，以及人工验收方法。等协议和核心迁入后，再把提案变成可运行的示例插件。

**English:** Existing R&D integrations use a local JSON Lines bridge (`seedbank/bridge@1`), provider adapters and Qt Quick/Live2D presentation. App source has not migrated to this repository. A plugin manager, permission manifest, hot reload and a stable SDK are future work. The offline Python example below is a reference client, not a tested release.

**日本語:** 元の開発版には JSON Lines ブリッジ、モデルアダプター、Qt Quick / Live2D の仕組みがあります。本庫へのアプリ移行は未完了です。統一プラグイン管理、権限宣言、ホットリロード、安定 SDK は今後の設計課題です。Python のオフライン例は参考実装で、検証済みリリースではありません。
