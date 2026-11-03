# 聊天平台与机器人框架

[SeedBank](../README.md) · [模型服务](model-services.md) · [开发与扩展](extensions.md)

你可以从桌面、私聊或群聊来见同一个体。平台负责收发消息；经历、记忆、选择与模型配置继续由 SeedBank 的同一个会话处理。聊天平台的机器人 Token 与模型 API Key 是两种凭据，请分别设置。

本地另有尚未发布的[指定群旁听候选](group-observation.md)：旁听名单与回复白名单独立，只处理平台实际推送的新文字，默认关闭。当前完整修订等待用户测试，不包含在下方已发布的 0.0.2 结果中。

以下描述当前源码实现。2026-11-04 的其他渠道修订已通过隔离离线集成及打包程序检查；真实平台连接尚未验收。版本与实际范围见[验收记录](acceptance.md)，不以模拟结果保证每个平台线上兼容。

## QQ 以外的同类问题

2026-11-04 代码审查确认：四个直连平台会先去除对机器人的提及，再交给共享路由；旧路由拒绝空正文，因此只 @ 不附文字时也会丢弃。已修改共享入口，仅在白名单群内有明确提及时传入“对方 @ 了你，没有附带文字”的事件说明，不伪造发言。空白私聊、未允许的群及没有实际提及的群消息仍被拒绝。

| 范围 | 代码发现与修订 |
| --- | --- |
| Telegram | 修复纯 @；只移除平台实体指明的提及，保留普通文字中的用户名，并支持有显示名字的提及。发送成功还需有消息编号回执。 |
| Discord | 修复纯 @；从平台 mentions 列表确认提及，保留群私信不能使用主人上下文的限制。 |
| 飞书 | 修复纯 @；无效 content JSON、非文字内容或异常 mentions 不再直接中断解析。 |
| 钉钉 | 修复平台确认已 @ 但 text.content 为空时的丢弃；不再将对象或数组强制转换成发言。 |
| AstrBot | 仍通过 `/seed 文字` 显式转交。新增独立 relayed 计数和提示，不能把本机 HTTP 返回成功当作最终平台送达。 |
| SnowLuma / NapCat / LLOneBot | 继续走 QQ OneBot 同一实现，沿用 [QQ 修订](qq-group-replies.md)，没有第二套独立记忆。 |

这些渠道共用 `Connection.exchange → Session.call → Bridge.message`，当前输入渠道进入模型上下文，档案、日记和记忆仍属于同一个体；群的可见范围相互隔离。摘要卡片与原始对话是两层记录，不能仅凭“记忆页没有新卡片”判断消息完全未保存。路由拒绝、生成未完成和发送结果未知也不是同一种状态。

设置 → 聊天渠道现在分别显示白名单／主人限制、正在生成、正在提交、发送成功、未生成文字、失败或结果未知。发送不明确时仍不重试，避免重复消息；AstrBot 显示“已转交插件”。这些信息也保留到连接断开时，不用一个笼统断开状态掩盖刚才的发送异常。

新增 14 项逻辑用例及 1 项四语界面用例已随本轮集成回归通过。逻辑用例包括五渠道消息保存、重开桌面回忆、无摘要时的原始记录检索及群间隔离，使用假模型和假发送器。复跑入口为 `packaging/run_offline.ps1 -Suite integrations`；核心与预算为 `-Suite core`，打包程序为 `packaging/run_candidate_checks.ps1`。这些脚本不会验证真实账号收发。

提及解析依据：[Telegram MessageEntity](https://core.telegram.org/bots/api#messageentity)、[Discord Message.mentions](https://discordpy.readthedocs.io/en/stable/api.html#discord.Message.mentions)。Telegram 的发送回执依据：[sendMessage](https://core.telegram.org/bots/api#sendmessage)。其余平台仍沿用已有 SDK 接口，本轮不声称完成线上兼容性验收。

## 接入范围

| 渠道或框架 | 接入方式 | 当前范围 |
| --- | --- | --- |
| QQ | 已有 OneBot v11 HTTP API + 本机 HTTP 上报 | 主人私聊、白名单群 @、原有文字及图片路径 |
| SnowLuma / NapCat / LLOneBot 等 | 使用它们提供的 OneBot v11 能力 | 属于上面同一条 QQ 接入路径；不是再登录一个 QQ 账号 |
| Telegram | Bot API 长轮询 | 新增文字私聊、白名单群 @ |
| Discord | Bot Gateway，discord.py | 新增文字私聊、白名单频道 @ |
| 飞书 | 企业自建机器人，官方 SDK 长连接 | 新增文字私聊、白名单群 @ |
| 钉钉 | 企业机器人，官方 Stream SDK | 新增文字私聊、白名单群 @ |
| AstrBot | 本机认证转接 + 随包插件 | `/seed` 文字指令，平台身份与会话白名单由 SeedBank 再次检查 |

“QQ 已有”表示已有适配器与配置入口，不表示代替第三方客户端登录或保证所有实现版本兼容。这里的 Snow 指 SnowLuma；其他名为 Snow 的项目需按实际协议确认。AstrBot 是机器人框架，其已有平台可以通过插件尝试转接；不能把整个 AstrBot 平台清单写成 SeedBank 均已独立适配和验收。

## 共用设置

### QQ HTTP 上报认证与去重

QQ 设置页新增“上报签名密钥环境变量”，默认 `SEEDBANK_ONEBOT_SECRET`。将随机密钥放在这个环境变量中，并在 OneBot 的 HTTP 上报配置 `secret` 填入相同值；重新启动 SeedBank 后生效。界面和普通配置只记录变量名。调用 OneBot API 的 `SEEDBANK_ONEBOT_TOKEN` 是另一项发送凭据，不能替代上报签名。

Windows 可搜索“编辑账户的环境变量”，在当前用户变量中新增 `SEEDBANK_ONEBOT_SECRET`，值填写自行生成的随机密钥；把同一值填入 OneBot 的 HTTP 上报 `secret`。保存后关闭并重新打开 SeedBank。不要把密钥值发到 Issue 或填进“环境变量名”一栏。

接收器按 [OneBot v11 HTTP POST 规范](https://github.com/botuniverse/onebot-11/blob/master/communication/http-post.md)校验原始正文的 `X-Signature: sha1=...`。未设置密钥时拒绝启动；缺少签名返回 401，无效签名返回 403。第三方实现必须支持该签名配置，不提供关闭认证的开关。命令行可用 `--secret-env VARIABLE_NAME` 指定变量名，不要在命令行粘贴实际密钥。

同一账号、会话、消息编号只领取一次，领取和投递状态保存在本机 `.seedbank/channels/` 的投递账本，不存正文或密钥。重开适配器仍去重。必须携带 `self_id` 与 `message_id`；缺失编号的消息不进入生成流程。明确失败、处理中断或投递结果未知的事件不自动重新生成/发送；可在桌面查看未完成请求。人工处理后应发送一条新消息，不能依靠重报旧事件补发。

HTTP 接收最多同时处理 8 个请求，待处理事件最多排队 32 条、按顺序处理；满载返回 503，拒绝的事件尚未领取，可由桥接端稍后重报。停止连接后丢弃待处理事件；已经交给平台的消息无法撤回。仅本机监听，不建议将接收端口映射到公网。

新增渠道位于 **设置 → 聊天渠道**；QQ / SnowLuma 使用原 **QQ** 页。

1. 在对应平台创建自己的机器人，取得下表所需凭据。
2. 将实际 Token / App Secret 写入电脑环境变量，重新打开 SeedBank。界面只填写变量名，不把密钥粘贴进账号 ID、应用 ID 或环境变量名框。
3. 填写主人账号 ID。昵称不能代替稳定 ID；空白名单不响应任何群。
4. 填写允许的群或频道 ID，保存，再手动“启动连接”。启动进程并不等于平台鉴权或消息投递已经成功。
5. 先用独立人工包，确认指定主人私聊、陌生人拒绝、白名单群 @、非白名单拒绝，再使用日常个体。

| 渠道 | 凭据变量默认名 | 应用字段 | 主人 ID | 群白名单 |
| --- | --- | --- | --- | --- |
| Telegram | `SEEDBANK_TELEGRAM_TOKEN` | 无 | 数字 user ID | 数字 chat ID（群通常为负数） |
| Discord | `SEEDBANK_DISCORD_TOKEN` | 无 | 数字用户 ID | 频道 ID，不是服务器 ID |
| 飞书 | `SEEDBANK_FEISHU_SECRET` | App ID + 机器人 open_id | 用户 open_id | chat_id |
| 钉钉 | `SEEDBANK_DINGTALK_SECRET` | Client ID / AppKey | senderStaffId | conversationId |
| AstrBot | `SEEDBANK_ASTRBOT_TOKEN` | 本机端口，默认 8791 | `/seedid` 返回的完整主人 ID | `/seedid` 返回的完整会话 ID |

默认只接受文字，单条最多 2000 字。新渠道尚未接附件、语音、主动推送或任意远程管理命令。休眠时不处理新消息，不会因聊天内容或重连自动恢复。主人在群里说话也使用群的可见范围；未绑定的群成员不会被冒认为主人。群只接触允许分享的上下文。

## 各平台准备

### Telegram

通过 BotFather 建 Bot，将 Token 放入对应环境变量。用户需先打开 Bot 私聊，群内使用 `@机器人用户名` 明确提及。保留平台隐私设置，并按官方说明配置机器人可收到的消息。使用 [Bot API 的 getUpdates / sendMessage](https://core.telegram.org/bots/api)。

一个 Bot 只能选择一种接收路径；如果已经配置 Webhook，本实现会拒绝启动，不会替你删除。每次手动启动会跳过已有待处理更新，避免突然回答一批离线积压消息。不要与其他轮询器同时使用同一 Token。程序关闭时不接收消息，也不会伪造这段时间的经历。

### Discord

创建 Bot 应用，使用 **Bot Token**，不要使用普通用户 Token。启用 **Message Content Intent**，邀请到目标服务器并允许查看频道、发送消息。白名单填具体频道或线程 ID；普通群私信不会按主人私聊处理。接入参考 [Discord Gateway](https://github.com/discord/discord-api-docs/blob/main/developers/events/gateway.mdx) 与 [discord.py](https://discordpy.readthedocs.io/en/stable/quickstart.html)。

回复禁用自动提及，避免模型输出触发 `@everyone` 等通知。启动 SeedBank 后再发送一条新消息；没有导入历史频道内容。

### 飞书

使用企业自建应用，启用机器人能力与**长连接接收事件**，订阅 `im.message.receive_v1`，按控制台为私聊接收、群内 @ 接收及机器人发送消息授予权限，并发布到需要使用的企业范围。填写 App ID，环境变量保存 App Secret。群内 @ 根据机器人自己的 open_id 判断，不能填昵称或 App ID 代替它。

读取用户 open_id、机器人 open_id、群 chat_id 时应使用同一应用的身份范围。当前端点是飞书国内站，没有将 Lark 国际站自动切换纳入此版。参考[官方长连接说明](https://open.feishu.cn/document/ukTMukTMukTM/uYDNxYjL2QTM24iN0EjN/event-subscription-configure-)及[回复消息 API](https://open.feishu.cn/document/server-docs/im-v1/message/reply)。

### 钉钉

在开放平台创建企业机器人并启用 **Stream** 接收模式，填写 Client ID / AppKey，环境变量保存 Client Secret / AppSecret。配置机器人可见范围并发布。主人绑定 `senderStaffId`，群绑定 `conversationId`；外部联系人缺少 staff ID 的事件暂不处理。

这不是只能发送通知的群自定义 Webhook 机器人。回复使用本次事件的短期 sessionWebhook；过期或投递失败不自动重发。参考[钉钉官方 Stream Python SDK](https://github.com/open-dingtalk/dingtalk-stream-sdk-python)。

### QQ / SnowLuma

在已有 OneBot 实现里启用 HTTP API，将消息上报到 QQ 页填写的本机端口，例如 `http://127.0.0.1:8790/`。SeedBank 的 OneBot HTTP 地址应填写桥端实际 API 地址；常见端口并不统一，不必照抄示例。主人 QQ 号、群白名单、机器人 QQ 号分别填写。

设置 `SEEDBANK_ONEBOT_TOKEN` 与桥端 HTTP API 的访问令牌匹配；另外设置 `SEEDBANK_ONEBOT_SECRET` 与 HTTP 上报的签名密钥匹配。两者用途不同。OneBot 的登录、平台权限及协议兼容仍由所选实现负责。不要同时把相同 QQ 事件经 OneBot 和 AstrBot 两条路径交给同一个体。

### AstrBot

本机研发交付随附 `seedbank-astrbot-plugin.zip`。解压到 AstrBot 的插件目录，例如 `data/plugins/seedbank_bridge/`，确认该目录下直接是 `main.py`、`metadata.yaml`、`_conf_schema.json`，然后按 AstrBot 的[插件安装方法](https://docs.astrbot.app/use/plugin.html)重载。此次未向插件市场发布。

AstrBot 和 SeedBank 必须运行在**同一台机器、同一网络命名空间**；当前只监听 `127.0.0.1`，不能直接从远端主机或默认 Docker 网络访问。两边设置同一个足够长的随机 `SEEDBANK_ASTRBOT_TOKEN`，插件与应用端口一致。它是本机桥接令牌，不是模型 Key 或 AstrBot 管理员密码。

先发送 `/seedid`，把返回的主人 ID 与需要的会话 ID 复制到 SeedBank；主人 ID 带平台实例前缀，以免不同平台上碰巧相同的用户 ID 被混认。之后用 `/seed 今天想说的话`；群内该指令即明确调用，但仍须在白名单中。修改了 AstrBot 的命令前缀时使用对应前缀。

插件停止该事件继续触发 AstrBot 的默认模型流程，由 SeedBank 生成并保存经历；没有复制 AstrBot 的人设、历史会话或工具权限。插件只调用固定的 `POST /v1/message`，不开放生命包读写、休眠恢复或任意桥接命令。接口返回表示内容已交给插件，**不是平台最终送达回执**。参考 [AstrBot 消息事件开发说明](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)。

## 运行与恢复

每种新渠道最多启动一个连接，多个渠道与桌面共享同一个 Session 顺序处理。平台网络 SDK 在单独的受管子进程内运行；停止连接或关闭窗口会结束相应子进程，不关闭其他应用。关窗后不会作为后台机器人继续运行，重开不会自动连接。

新渠道的配置与投递编号保存在本机用户目录 `.seedbank/channels/`，按生命包路径分隔。里面不保存令牌、输入正文或回答正文。聊天记录仍写入生命包。搬迁生命包后需要重新配置渠道，不能期待旧的去重记录跨机器自动恢复。

平台重投的同一消息会去重；已经尝试过的失败消息也不自动再次请求模型或发送。失败计数需要结合桌面的未完成请求查看。断线、超时或分段回复时，远端可能已经收到部分内容，不能保证恰好一次送达。SDK 可重连网络连接，这不等于自动重试失败的模型活动。

休眠确认与直接渠道的当前消息处理、回复提交顺序执行，可能需等待当前模型请求或发送完成；已经提交到平台的消息不能撤回。AstrBot 的最终发信由框架完成，停止转接不能撤回已交给插件的回复。

**English:** QQ uses OneBot. Telegram, Discord, Feishu and DingTalk use direct text adapters; AstrBot uses an explicit `/seed` local bridge. The 2026-11-04 revisions address bare mentions, preserve literal message text and distinguish bridge handoff from platform delivery. Current isolated integration and packaged UI checks passed; live platform connections remain unverified.

**日本語:** QQ は OneBot、Telegram・Discord・Feishu・DingTalk は文字アダプター、AstrBot は `/seed` ローカルブリッジを使用します。2026-11-04 の修訂は、本文のないメンション、文字の保持、プラグインへの引き渡しと配信確認の区別を対象としています。隔離した統合テストと配布プログラムの UI 検査は成功しましたが、実際のプラットフォーム接続は未検証です。
