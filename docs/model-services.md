# 模型服务：使用自己的 Key

[SeedBank](../README.md) · [聊天平台与机器人框架](channels.md) · [开发与扩展](extensions.md)

模型服务决定个体用哪一个模型理解和表达；聊天渠道决定你从哪里与它相见。两者分别配置，切换模型不会新建另一份出生记录。

已有 13 家云服务的配置预设，以及自定义兼容地址、本地模型和独立 Codex 登录入口。2026-11-04 修订加入 [WorkBuddy 同账号 CodeBuddy CLI 实验入口](workbuddy.md)，离线检查已通过，真实账号调用未验收。**预设与协议适配不代表每个服务、每个模型均已通过真实调用验收。** 0.0.2 预览版下载包的具体范围见发行说明。

## 云服务预设

下列变量名是示例，可以自行改名；实际 API Key 属于你自己的服务账号。表内链接指向服务商文档。接口地址填写根地址，不要再拼上 `chat/completions` 或 `messages`。

| 服务 | 接口根地址 | 密钥环境变量示例 |
| --- | --- | --- |
| [OpenAI](https://developers.openai.com/api/reference/overview) | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| [DeepSeek](https://api-docs.deepseek.com/) | `https://api.deepseek.com/anthropic`（已有预设）；自定义 OpenAI 兼容方式可用 `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| [Claude / Anthropic](https://platform.claude.com/docs/en/api/overview) | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` |
| [Google Gemini / AI Studio](https://ai.google.dev/gemini-api/docs/openai) | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` |
| [通义千问 / 阿里云百炼](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope) | `https://dashscope.aliyuncs.com/compatible-mode/v1`（北京；工作空间地址见下文） | `DASHSCOPE_API_KEY` |
| [豆包 / 火山方舟](https://docs.volcengine.com/docs/ark/text-generation?lang=en) | `https://ark.cn-beijing.volces.com/api/v3` | `ARK_API_KEY` |
| [Kimi / Moonshot](https://platform.kimi.com/docs/get-api-key) | `https://api.moonshot.cn/v1` | `MOONSHOT_API_KEY` |
| [智谱 GLM / BigModel](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction) | `https://open.bigmodel.cn/api/paas/v4` | `ZHIPU_API_KEY` |
| [MiniMax 国内 API](https://platform.minimax.cn/docs/api-reference/text-openai-api) | `https://api.minimax.cn/v1` | `MINIMAX_API_KEY` |
| [硅基流动 / SiliconFlow](https://docs.siliconflow.cn/docs/api/chat-completions-post) | `https://api.siliconflow.cn/v1` | `SILICONFLOW_API_KEY` |
| [OpenRouter](https://openrouter.ai/docs/api/reference/overview) | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| [百度千帆通用 API](https://cloud.baidu.com/doc/qianfan/s/rmh4stn9m) | `https://qianfan.baidubce.com/v2` | `QIANFAN_API_KEY` |
| [腾讯混元 API Key](https://cloud.tencent.com/document/product/1729/111007) | `https://api.hunyuan.cloud.tencent.com/v1` | `HUNYUAN_API_KEY` |

新增十家预设都走 Chat Completions 兼容协议，模型 ID 留空，由使用者填写账号实际可用的 ID。豆包可以使用 Model ID 或 `ep-` 推理接入点 ID；聚合服务往往需要完整的 `提供方/模型名`。已有预设里的模型名称也可以修改，不应据此认定账号已开通模型。

百炼的 Key、地域、模型和工作空间需要对应。若控制台给出 `<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` 等工作空间地址，直接替换预设地址；新加坡、香港、美国等地域不能只换 Key 而沿用北京地址。不要把带尖括号的占位地址直接保存。参考[官方兼容说明](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)。

国内站、国际站、网页会员、Coding Plan 和通用 API 可能有不同的 Key、权限与地址，按相应服务控制台配置。千帆这里采用通用 API Key；混元这里采用 API Key，不接旧 AK/SK 或腾讯云 SecretId/SecretKey 签名流程。

## 在应用里配置

1. 打开 **设置 → 对话**，选择预设。
2. 填写模型 ID，并按地域或工作空间调整根地址。
3. Windows 可直接填写 API Key，由当前系统用户加密保存。生命包只保存引用，换电脑后重新填写。也可选择环境变量，只在界面填写变量名，实际值放到本机环境变量中。
4. 保存。使用环境变量时，修改变量后需要重新打开应用。
5. 由你点击“测试连接”。这会发出模型请求，可能计费；随后再用独立人工生命包确认普通对话、日记及结构化返回是否符合需要。文字连通不代表所有能力都可用。

新增预设默认使用模型自己的温度，并通过提示请求结构化回答，应用仍按原协议解析和校验。确认所选模型支持后，可以打开“服务端 JSON 模式”；需要自定义温度时关闭“使用模型默认温度”。参数不兼容不会触发自动更换参数的第二次传输请求。正常的记忆回查或后续创作仍可能属于另一项模型活动，不等于取消了原有调用流程。

MiniMax 返回中的推理内容与回答正文分开处理；空回答、仅有推理或因长度/过滤中断的回答不会被当作完整成功结果。其余服务也可能有思考预算和输出限制，具体取决于模型。

## 本地与其他入口

| 入口 | 配置 |
| --- | --- |
| Ollama | 默认 `http://localhost:11434/v1`，填写已安装模型 ID |
| LM Studio | 默认 `http://localhost:1234/v1`，先启动本地服务器 |
| vLLM / 本地兼容服务 | 默认 `http://127.0.0.1:8000/v1`，模型 ID 按本机服务填写 |
| 自定义云服务 | 选择 OpenAI-compatible 或 Anthropic，填写服务商根地址、模型和自己的 Key |
| Codex 登录 | 单独选择本机 Codex 登录入口，使用该客户端账号额度；与 API Key 无关，当前仅文字 |
| WorkBuddy 同账号（实验） | 先在官方 CodeBuddy CLI 登录同一账号，再填写模型 ID；不同步桌面登录或模型选择。见[接入与用户验收](workbuddy.md) |

当前“发现本地模型”面向本机服务，没有实现各云平台的模型目录同步。Vertex AI IAM、Azure 专用鉴权、AWS Bedrock、厂商原生工具/联网搜索、语音实时会话、视频和生图接口没有因为新增预设而自动接入。图片仍需所选模型和兼容接口实际支持，不能只按平台名称判断。

**English:** Bring your own API key and the model ID available to your account. Presets are configuration and protocol support, not a claim of live verification. Chat channels are configured separately. Native cloud IAM, realtime voice and provider tools are outside this integration.

**日本語:** 自分の API Key と利用可能なモデル ID を設定してください。プリセットは接続設定であり、全サービスの実機検証済みを意味しません。チャット連携は別設定です。クラウド固有の IAM、リアルタイム音声、提供元固有のツールは今回の対象外です。
