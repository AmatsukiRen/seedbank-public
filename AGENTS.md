# SeedBank 工作约定

## 仓库与发行

- 本库是产品开发与发行准备仓库，当前保持 PRIVATE。用户于 2026-11-03 要求再次检查并将主程序等上传 Git，准备公开库；已按清单迁入源码、适配器和构建材料，允许本轮生产与上传私有候选附件。
- 首个版本为 0.0.1；允许准备 GitHub draft release，不能擅自改 PUBLIC、发布 Release、部署 Pages 或发布正式标签。公开需用户后续明确指令。
- 迁移清单见 docs/source-files.txt，范围与历史结果见 docs/repository-plan.md、docs/acceptance.md。本库继续维护产品源码；原研发目录保留历史，不做双向同步。
- 程序包放在私有发行草稿附件中，不把 exe、zip、构建目录或本地绝对路径加入 Git 源码。

## 测试

- 用户执行测试、验证例程、构建检查和应用自检。代理可静态阅读代码、编辑、生产打包、读取已有结果；不运行测试，不将成功打包当作通过证据。
- 生产命令 packaging/build_windows.ps1 -NoInstall -SkipSmoke 不启动程序。测试入口 packaging/run_offline.ps1 只交用户执行。
- 不用 computer-use，不读写真实生命包，不调用模型或 QQ/其他聊天平台，不沿用或重置历史预算，不改变系统自启。
- 历史测试明确日期、源码版本与范围；新候选未测试。

## 产品与素材

- 品牌 SeedBank；愿景“给 AI 完整的一生。”，不声称完整人格或意识已实现。
- 默认开放出生，外观不预设物种、性别、童年；不设固定寿命。明确休眠后保留档案并停止活动，允许明确恢复。
- 保留认可的白底蓝色女仆头像；不重新生图。人设 ZipZipPipe、上善无形；参考 Live2D 原画拆分神宫凉子，建模霓虹猫_NeonNeko。详情 docs/assets.md。
- 公开品牌授权及 Live2D SDK 发行类别尚待确认；按 THIRD_PARTY_NOTICES.md 处理，不把署名当作许可。
- 不能提交真实生命包、个人连接配置、密钥、原始日志或第三方模型本体。迁移必须使用明确文件清单，不能复制原工作区或其 .git。
- 三语 README 与 docs 为介绍入口，不维护 HTML 站点，不重新引入 docs/release-plan.md。文案源 docs/content/*.json，生成工具 tools/render-readme.mjs。
- 历史三张同页截图已从首页撤下；新截图待用户提供真实新候选画面，不假造截图或运行结果。
- 本地 JSON Lines、模型和渠道适配已经有实现；没有稳定插件 SDK、插件商店、热加载或权限沙箱，不混写为已完成。

## 版本

应用唯一版本来源 tools/seed/seedbank/__init__.py，CLI、Python 元信息、Qt 和 Windows 文件版本沿用；生命周期与协议格式编号保持原值。release-plan.json 是发行状态，不代表已发布。
