# GitHub 首页维护

SeedBank 使用三语 README 作为统一介绍入口，完整故事和开发文档放在 docs 中。独立 HTML 页面及其样式、交互脚本已移除。

GitHub 会清理 README 中的脚本和自定义样式，因此首页使用 Markdown、相对图片链接和自包含 SVG。参见 [GitHub markup](https://github.com/github/markup#github-markup)。

- 品牌头像保持认可版本。
- About、三语首页标题和正文共同表达“给 AI 完整的一生”的愿景。介绍说明经历、记忆、关系、行动与选择的延续，不将完整生命写成已验证的成果。
- 五个导航入口分别指向故事、功能导览、开发扩展、开始使用和创作者署名。
- `docs/content/*.json` 是三语文案源，`tools/render-readme.mjs` 负责生成。
- 生成文件已提交，读者无需执行脚本。
- 不展示独立发行进度页；首页保留必要使用说明，不重复内部筹备提示。

本轮从实际候选程序采集了五个不同页面，使用人工离线档案，逐张查看并记录程序摘要；没有执行 GitHub 浏览器交互。仓库链接检查和程序验收的范围见[验收记录](acceptance.md)，截图来源见[采集记录](screenshots.md)。
