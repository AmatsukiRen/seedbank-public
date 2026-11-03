# 使用 WorkBuddy 同一账号生成回复

[模型服务](model-services.md) · [用户验收](acceptance.md)

新增实验入口 **WorkBuddy（同账号 CodeBuddy CLI）**。SeedBank 负责提供当前对话、记忆和人生记录，官方 CodeBuddy CLI 负责账号认证及模型生成，回复再交回 SeedBank 保存。切换此入口不重新出生，也不改写已有经历。

**当前状态：实验入口已纳入本轮 0.0.2 预览修订，离线传输与设置检查通过；真实 CLI 账号调用尚未验收。** 具体发行范围以 [Release](https://github.com/AmatsukiRen/seedbank-public/releases/tag/v0.0.2) 的修订说明为准。

## 账号与模型的实际边界

官方明确说明，**国内版 CodeBuddy 和 WorkBuddy 同一账号共享积分**；请以自己的账号、地区和套餐权益为准。[官方账号说明](https://www.codebuddy.cn/docs/ide/Account/pricing)

这里使用的是同一账号的官方 CLI 通路，**不是直接控制 WorkBuddy 桌面，也不读取或解密桌面登录文件**。仅在 WorkBuddy 桌面登录过，不代表 CLI 已登录。WorkBuddy 桌面当前选中的模型不会自动同步，请在 SeedBank 填写同一账号可用的模型 ID；记录中的模型名称来自配置，不冒充服务端核验结果。

本实现不调用 WorkBuddy 本地助理消息 API，避免把个体上下文混入用户正在进行的办公任务。该 Open API 另需第三方应用及 OAuth 授权，并不是一个免配置的 Chat Completions 地址。[官方 Open API](https://open.workbuddy.cn/docs/openapi)

## 安装与配置

1. 按 [CodeBuddy 官方快速开始](https://www.codebuddy.cn/docs/cli/quickstart)安装较新版本。支持官方原生 CLI，或官方 npm 包 `@tencent-ai/codebuddy-code`；npm 方式需要 Node.js。
2. 在终端启动 `codebuddy`，选择对应站点，登录**与 WorkBuddy 相同的账号**。在 CLI 的 `/model` 中查看可用模型，并记下需要的模型 ID。不要向项目维护者发送密码、Cookie 或令牌。
3. 重开 SeedBank，在 **设置 → 对话** 选择 **WorkBuddy（同账号 CodeBuddy CLI）**，填写模型 ID。此处无需 API Key 或接口地址。
4. 保存后，由你点击“测试连接”。这会产生一次真实 CLI 调用并消耗账号额度。之后在独立人工生命包发送一条消息，确认返回内容、记忆保存和切回其他模型的行为。

SeedBank 从 PATH 查找 `codebuddy` 或 `cbc`。若安装在其他位置，可设置本机环境变量 `SEEDBANK_WORKBUDDY_CLI` 为官方 `codebuddy.exe` 的绝对路径，或 npm 安装产生的 `codebuddy.cmd` 路径。变量不写入生命包。Windows npm 入口通过该官方包的 Node 入口运行，不拼接 shell 命令；不支持任意自制批处理包装器。不要把 WorkBuddy.exe 桌面启动器填在这里。

只安装 WorkBuddy 桌面且无法从 PATH 找到独立 CLI 时，需要先完成第 1–2 步。本实现没有自动安装、自动登录或读取桌面内置私有凭据。

## 请求与用量

- 当前仅文字，包括普通回复、记忆回查、日记和创作。图片仍可归档，此入口不做图片理解。没有启用电脑操作、MCP、文件工具或后台任务。
- 每轮活动默认最多发起 **2 次 CLI 调用**，可设 1–3；回答、回查与随后创作共享同一轮预算。主动机会和日记各按自己的活动计数。
- 每次 CLI 设置单轮、低推理量、输出最多 2048 tokens，并使用独立临时目录、SeedBank 系统提示和不持久化会话参数。关闭用户配置加载、自动记忆、Hooks 与插件 MCP。不恢复旧 CodeBuddy 会话。
- SeedBank 不重发失败请求，并设置 CLI 的普通退避重试次数为 0。**CLI 或服务网关仍可能有内部传输重试/恢复策略；应用调用次数不是底层请求次数、token 或积分硬上限。** 上游行为与参数支持以实际版本为准。[官方 CLI 参数](https://www.codebuddy.cn/docs/cli/cli-reference)及[环境变量](https://www.codebuddy.cn/docs/cli/env-vars)
- 120 秒超时或输出超过 4 MiB 时停止本次子进程；不把不完整返回当作角色回答。检测到工具输出、额外轮次或非法事件时拒绝采用，不能据此声称所有第三方版本均已实测隔离。
- 用量回执独立存放于用户目录 `.seedbank/workbuddy-usage`。只保存状态、配置模型、调用编号、时间与已知 token 用量，不保存提示、正文或登录凭据；未知用量明确计为未知。关闭会话持久化不等于承诺上游服务或 CLI 的诊断系统完全不留记录。
- 自动活动遇到错误后暂停调用；成功发送手动消息或重新保存设置后再继续。连接测试本身不会恢复个体休眠。

## 验收

仓库根目录运行 `powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_workbuddy_checks.ps1`。此入口只运行假传输、临时人工包及软件界面用例，禁止网络，不启动真实 CodeBuddy，不消耗账号额度；日志为 `artifacts/workbuddy-*.log`。

2026-11-04 用户明确允许代理测试后，上述入口 **50/50 通过，1.842 秒**。覆盖独立工作目录和系统提示、模型 ID 必填、工具事件拒绝、错误/超时/缺失用量、环境变量隔离、调用预算共享、自动活动暂停、连接结果解析、四语设置保存及现有 Codex 回归。全部是假传输，没有启动真实 CodeBuddy 或消耗账号额度；真实 CLI 兼容性、账号授权与回答质量仍未验收。

**English:** Experimental WorkBuddy account support uses the official CodeBuddy CLI, signed into the same account. Desktop authentication and selected models are not imported. A model ID is required. Offline transport/settings checks passed and the feature is included in this 0.0.2 preview revision; live CLI compatibility remains unverified.

**日本語:** WorkBuddy と同じアカウントでログインした公式 CodeBuddy CLI 経由の実験的な接続です。デスクトップ認証・モデル選択は取り込まず、モデル ID の入力が必要です。オフライン検査は成功し、今回の 0.0.2 プレビュー修訂に含まれます。実際の CLI 接続は未検証です。
