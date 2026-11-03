# GitHub 首页维护

SeedBank 使用三语 README 作为统一介绍入口，完整故事和开发文档放在 docs 中。独立 HTML 页面及其样式、交互脚本已移除。

GitHub 会清理 README 中的脚本和自定义样式，因此首页使用 Markdown、相对图片链接和自包含 SVG。参见 [GitHub markup](https://github.com/github/markup#github-markup)。

- 品牌头像保持认可版本。
- 五个导航入口分别指向故事、功能导览、开发扩展、开始使用和创作者署名。
- `docs/content/*.json` 是三语文案源，`tools/render-readme.mjs` 负责生成。
- 生成文件已提交，读者无需执行脚本。
- 仓库可见性与发行状态集中在[发行计划](release-plan.md)，首页不重复内部筹备提示。

本轮没有运行浏览器、图形渲染或测试。阅读与交互检查由用户按[验收步骤](acceptance.md)执行。
