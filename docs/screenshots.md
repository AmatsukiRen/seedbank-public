# 画面状态与采集约定

**当前首页不展示实机截图。** 原来的三张图片都是同一旧版陪伴页的不同状态，不能介绍整个应用；透明背景还会让 GitHub 深色主题改变视觉效果。已从三语 README 和介绍页撤下，不将它们标为最新画面。

## 下一组画面

| 页面 | 应展示的内容 | 当前状态 |
| --- | --- | --- |
| 陪伴 | 当前品牌、角色区域、人工示例对话 | 待用户采集与查看 |
| 日记 | 选中日期后实际出现的正文 | 待用户采集与查看 |
| 记忆 | 实际记忆条目及清晰可辨的操作按钮 | 待用户采集与查看 |
| 生活 | 成长内容及心事、作品、休眠入口 | 待用户采集与查看 |
| 设置 | 当前配置界面；独立配置，不含个人凭据 | 待用户采集与查看 |

原研发交付已准备 `Capture-SeedBank-Pages.cmd` 用户入口。它选择交付清单中的当前程序，创建一次性人工生命包，以离线 stub 形成示例对话并明确推进一天，逐页保存程序自身渲染的画面。它不操作桌面输入，不读取真实个体或模型连接配置，不连接模型服务。可只读加载明确选定的本地 Live2D 文件；不随截图分发模型。

输出为独立 `seedbank-showcase-<日期时间>-<进程号>` 目录，包含 `companion.png`、`diary.png`、`memories.png`、`life.png`、`settings.png` 和 `capture.json`。元数据记录实际运行文件名、SHA256、采集时间、场景、尺寸与图片摘要。内部场景抓取不含窗口底色，因此输出时使用该窗口当时的真实清屏颜色填充为不透明 PNG，不对人物、文字或界面布局做后期重绘。

**本轮没有运行采集程序、应用测试或浏览器验收。** 入口完成不等于图片已经生成；退出码和捕获结果需由用户实际运行后查看。只在确认页面对应、正文可读、模型正常及版本一致后，将五张图片和精简后的来源记录纳入仓库。原始日志可能含本机路径，不能直接公开。

## 历史图片登记

保留文件以便追溯，但不用于当前介绍页。全部来自 **2026-11-03 01:50 研发版** 的原生 Live2D 人工隔离场景：

| 历史文件 | 拍摄时间（Asia/Shanghai） | 实际内容 |
| --- | --- | --- |
| `assets/screenshots/idle.png` | 2026-11-03 02:28:31 | 陪伴页静止，1280×840 |
| `assets/screenshots/wave.png` | 2026-11-03 02:28:33 | 同页抬手，1280×840 |
| `assets/screenshots/small.png` | 2026-11-03 02:28:51 | 同页缩小窗口，860×640 |

原研发记录为 `docs/80-all-acceptance.md`。图片含 Alpha，早于当前品牌调整；它们不能代表当前 UI、五个不同页面、0.0.1 验收、帧率或长期稳定性。

## 素材署名

DeepSeek-chan（大肥鱼），神宫凉子免费配布模型。**人设：ZipZipPipe、上善无形；原画及拆分：神宫凉子；Live2D 建模：霓虹猫_NeonNeko。**

[完整出处](assets.md) · [作者原始预告](https://www.bilibili.com/video/BV1ALnw6YEGK)

**English:** The three old companion-page captures have been withdrawn from all front pages. New captures of five distinct pages are pending user execution and review. The prepared entry captures the current packaged UI with an artificial offline life, records build metadata and preserves the actual window background in opaque PNGs. No capture or application test was run for this update.

**日本語:** 旧版の同じ陪伴画面を使った三枚をトップページから取り下げました。五画面の撮影はユーザーによる実行・確認待ちです。用意した入口は現在の実行ファイルと架空のオフライン個体を使い、実際の背景色とビルド情報を保存します。本更新で撮影やアプリのテストは実行していません。
