# 当前五页画面与采集记录

三语 README 展示 **0.0.1 当前 Windows 候选**的陪伴、日记、记忆、生活和设置五个不同页面。采集于 2026-11-03，1280 × 840；均来自同一个实际 exe，不是设计图或旧版本拼接。

- 程序 SHA256：`f709a04ab7feb9c2294905835927ade0474629fa28d23e5293a1929597bf02c6`。
- 场景：独立人工生命包，离线 stub 回复，明确推进一天以展示已完成日记；没有真实模型调用或真实用户内容。
- 日记选中了有正文的日期；记忆页展示实际保存的人工记录及操作按钮；生活页保留这个新示例尚无目标的真实状态。
- 设置页使用人工连接信息，不显示本机角色路径或凭据。角色从指定本地文件只读加载，不随截图分发模型本体。
- 程序自身逐页渲染并采集，不操作桌面鼠标键盘。采集时在内容树底部绘制与窗口一致的背景色，避免透明图层导致文字彩边；输出为不透明 PNG，未重绘人物、文字或布局。

[精简元数据与图片摘要](../assets/screenshots/current-capture.json) · [本轮验收](acceptance.md)

| 页面 | 文件 |
| --- | --- |
| 陪伴 | [companion.png](../assets/screenshots/companion.png) |
| 日记 | [diary.png](../assets/screenshots/diary.png) |
| 记忆 | [memories.png](../assets/screenshots/memories.png) |
| 生活 | [life.png](../assets/screenshots/life.png) |
| 设置 | [settings.png](../assets/screenshots/settings.png) |

## 再次采集

在 Windows 构建后运行 `packaging/capture_pages.ps1 -Executable <程序路径> -Model <完整的本地.model3.json路径>`。`-Output` 可指定一个尚不存在的输出目录；省略模型参数则展示无模型状态。入口使用一次性人工档案，不读取现有个体或模型服务配置，不请求网络。

采集记录并不证明长期成长、真实模型的表达质量或所有显卡上的表现。原始 capture.json 与日志可能带本机路径，不直接加入仓库。

## 历史图片

`idle.png`、`wave.png`、`small.png` 保留作历史资料，来自 2026-11-03 01:50 研发版，内容均为陪伴页；它们不再用于当前首页。

## 素材署名

DeepSeek-chan（大肥鱼），神宫凉子免费配布模型。**人设：ZipZipPipe、上善无形；原画及拆分：神宫凉子；Live2D 建模：霓虹猫_NeonNeko。**

[完整出处与使用边界](assets.md) · [作者发布视频](https://www.bilibili.com/video/BV1KmxY66EZ3/) · [模型获取页](https://gf.bilibili.com/item/detail/1109618072)

**English:** These are five actual pages from one checked 0.0.1 executable, captured with an artificial offline life. The diary date was explicitly advanced. They are not real conversations or evidence of autonomous growth. The local model is not bundled; credits and usage conditions remain applicable.

**日本語:** 同じ検査済み 0.0.1 実行ファイルの五画面を、架空のオフライン個体で撮影しました。日記用に日付を明示的に進めています。実際の会話や自律的成長の証拠ではありません。モデル本体は同梱せず、作者表記と利用条件を維持します。
