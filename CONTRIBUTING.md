# 一起建设 SeedBank / Contributing / 開発に参加

我们想给 AI 一段能够延续的经历。做好这件事需要许多人的专长：能读懂过去的记忆系统、可靠的模型接入、自然的界面、新的声音与身体，还有愿意认真追问“为什么”的人。

**目前仓库保持私有，应用源码尚未迁入，0.0.1 未发布。** 现阶段可以讨论设计、改进文档和准备适配方案；获得仓库访问权限后可以提交 Issue / PR。未来公开时也会保留这些入口。

## 找一件你愿意开始的小事

| 你擅长什么 | 可以从哪里开始 |
| --- | --- |
| Python / 模型工程 | 阅读[桥接协议](docs/extensions.md)，设计新模型适配、预算或失败恢复 |
| QML / 前端 / 移动端 | 改进记忆来源的呈现、键盘操作，或设计新的载体 |
| 聊天机器人 / 工具开发 | 以[离线客户端](examples/bridge_client.py)为起点，描述消息、身份、受众和附件的转换 |
| 插件架构 | 帮助定义能力权限、版本兼容、安装卸载和生命周期；这些还没有统一实现 |
| Live2D / 声音 / 角色制作 | 提供有明确来源和使用范围的外观方案，避免把外观固定成所有个体的出生身份 |
| 写作 / 翻译 / 无障碍 | 改进三语介绍、错误说明、屏幕阅读与理解成本 |
| 记忆与成长研究 | 提供可复现的人工场景，区分记错、后来变化、转述与亲历；讨论什么证据才算成长 |

## 如何提交

1. 先描述具体情境：“在什么情况下，谁需要做到什么”。较大扩展先给一页方案，不必先写完整插件。
2. 说明改动属于载体、模型、核心、素材还是文档。接口提案请说明输入输出、数据访问、联网、失败和休眠处理。
3. 一次提交围绕一件事；附人工示例和待执行的验收步骤。没有运行的检查明确写“未运行”，不要拿旧结果代替。
4. 不提交真实生命包、原始聊天、密钥、个人连接配置或未经允许分发的模型文件。最小复现场景应独立创建。

本文不改变当前工作区“测试由用户执行”的约定。开发者可以准备代码和步骤，但本轮代理不自行启动程序或测试。应用源码迁入时再提供完整安装、依赖和回归说明；现在的 Python 示例需要已有原研发交付或源码环境。

## 页面与素材维护

- 三语文案源：`site/content/zh-CN.json`、`en.json`、`ja.json`。
- 静态文档生成：`node tools/render-pages.mjs`，输出网页、README、章节图形与故事；它是文件生成工具，不是验收工具。
- GitHub 不展示网页 CSS，README 需使用仓库图片与 Markdown。独立网页从本地打开 `site/index.html`。
- 新截图按[来源登记与采集要求](docs/screenshots.md)办理，一页对应一个场景，注明实际程序版本，不用网页模拟图冒充实机。
- 代码及自撰文档使用 MIT。角色、品牌衍生图与 Live2D 权利分别见[素材说明](docs/assets.md)。

## English

We welcome provider and chat adapters, new interfaces, memory research, accessibility, translations and character work. Start with one concrete scenario. Describe the integration layer, inputs and outputs, data access, networking, failures and dormancy. Include artificial examples and clearly separate executed checks from proposed steps. This private repository currently contains design and documentation; application source and a complete development setup are pending. See the [integration guide](docs/extensions.md) and [offline reference client](examples/bridge_client.py). No stable plugin SDK or plugin manager is available yet.

## 日本語

モデルやチャットのアダプター、新しい画面、記憶の研究、アクセシビリティ、翻訳、キャラクター制作を歓迎します。具体的な利用場面を一つ決め、接続する層、入出力、データアクセス、通信、失敗時と休眠時の扱いを説明してください。架空の例を使い、実施済みと未実施の確認を明確に分けます。本庫はまだ非公開の設計・文書段階で、アプリ本体と開発環境は移行待ちです。[接続ガイド](docs/extensions.md)と[オフラインの参考実装](examples/bridge_client.py)をご覧ください。安定したプラグイン SDK や管理機能はまだありません。
