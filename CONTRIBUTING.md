# 一起建设 SeedBank / Contributing / 開発に参加

我们想给 AI 一段能够延续的经历。做好这件事需要许多人的专长：能读懂过去的记忆系统、可靠的模型接入、自然的界面、新的声音与身体，还有愿意认真追问“为什么”的人。

欢迎通过 Issue 讨论具体问题，用 PR 提交独立改进。应用核心、Qt Quick 界面及渠道适配器已在本库；从[开发说明](docs/development.md)和接入指南开始。

## 找一件你愿意开始的小事

| 你擅长什么 | 可以从哪里开始 |
| --- | --- |
| Python / 模型工程 | 阅读[桥接协议](docs/extensions.md)，设计新模型适配、预算或失败恢复 |
| QML / 前端 / 移动端 | 改进记忆来源的呈现、键盘操作，或设计新的载体 |
| 聊天机器人 / 工具开发 | 以[离线客户端](examples/bridge_client.py)为起点，描述消息、身份、受众和附件的转换 |
| 插件架构 | 从[本地文本插件](docs/plugins.md)与便签示例开始；继续完善能力权限、版本兼容和生命周期 |
| Live2D / 声音 / 角色制作 | 提供有明确来源和使用范围的外观方案，避免把外观固定成所有个体的出生身份 |
| 写作 / 翻译 / 无障碍 | 改进三语介绍、错误说明、屏幕阅读与理解成本 |
| 记忆与成长研究 | 提供可复现的人工场景，区分记错、后来变化、转述与亲历；讨论什么证据才算成长 |

## 如何提交

1. 先描述具体情境：“在什么情况下，谁需要做到什么”。较大扩展先给一页方案，不必先写完整插件。
2. 说明改动属于载体、模型、核心、素材还是文档。接口提案请说明输入输出、数据访问、联网、失败和休眠处理。
3. 一次提交围绕一件事；附人工示例和待执行的验收步骤。没有运行的检查明确写“未运行”，不要拿旧结果代替。
4. 不提交真实生命包、原始聊天、密钥、个人连接配置或未经允许分发的模型文件。最小复现场景应独立创建。

安装、构建与隔离离线回归入口见 [开发说明](docs/development.md)。贡献者应运行与修改相关的检查，附实际结果和未覆盖范围；所有示例使用人工数据，不连接维护者账号。安全漏洞请按 [SECURITY.md](SECURITY.md) 私下报告。

## 页面与素材维护

- 三语文案源：`docs/content/zh-CN.json`、`en.json`、`ja.json`。
- 静态文档生成：`node tools/render-readme.mjs`，输出 README、章节图形与故事；它是文件生成工具，不是验收工具。
- 介绍集中在三语 README 与 docs；不维护独立 HTML 网站。
- 新截图按[来源登记与采集要求](docs/screenshots.md)办理，一页对应一个场景，注明实际程序版本，不用网页模拟图冒充实机。
- 代码及自撰文档使用 MIT。角色、品牌衍生图与 Live2D 权利分别见[素材说明](docs/assets.md)。

## English

We welcome provider and chat adapters, new interfaces, memory research, accessibility, translations and character work. Start with one concrete scenario. Describe the integration layer, inputs and outputs, data access, networking, failures and dormancy. Include artificial examples and clearly separate executed checks from proposed steps. The application core and desktop UI are included in this repository; setup and offline regression commands are in docs/development.md. See the [integration guide](docs/extensions.md) and [offline reference client](examples/bridge_client.py). A local manual text-plugin manager and example are now included; see docs/plugins.md. There is no stable SDK or permission sandbox, and the new implementation awaits user testing.

## 日本語

モデルやチャットのアダプター、新しい画面、記憶の研究、アクセシビリティ、翻訳、キャラクター制作を歓迎します。具体的な利用場面を一つ決め、接続する層、入出力、データアクセス、通信、失敗時と休眠時の扱いを説明してください。架空の例を使い、実施済みと未実施の確認を明確に分けます。アプリのコアとデスクトップ画面は本リポジトリに収録しています。導入と回帰テストの手順は docs/development.md を参照してください。[接続ガイド](docs/extensions.md)と[オフラインの参考実装](examples/bridge_client.py)をご覧ください。ローカルの手動テキストプラグイン管理とサンプルを追加しました。docs/plugins.md を参照してください。安定 SDK や権限サンドボックスは未提供で、新実装はユーザーによる検証待ちです。
