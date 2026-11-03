# GitHub 首页设计

2026-11-03。用户指出网页设计未体现在 GitHub 仓库首页，本轮补齐 README 专用的视觉层。

## 原因

此前设计集中在 `site/index.html` 及其 CSS。虽然 README 已经更新了文字和截图，仓库首页不会因此变成该 HTML 页。

GitHub 会将 README 渲染为 HTML，并清理脚本、自定义内联样式等内容，见 [GitHub 官方 markup 说明](https://github.com/github/markup#github-markup)。仓库首页支持[相对图片与文档链接](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes#relative-links-and-image-paths-in-readme-files)，因此本轮把首页需要的视觉排版做成仓库内的自包含 SVG。

## 本轮文件

- `README.md`、`README.en.md`、`README.ja.md`：独立的 GitHub 首页排版。
- `assets/readme/hero-*.svg`：三语品牌标题与主张，沿用白、蓝、品红。
- `assets/readme/nav-*.svg`：故事、实机画面、开始之前、创作者署名四个可点击入口。
- `assets/readme/section-*.svg`：四个主题章节横条。
- `tools/readme-design.mjs`：可维护的 Markdown 与 SVG 生成源，由现有 `render-pages.mjs` 引用。

共 27 个小型 SVG，只有字体排版和基本界面形状，没有外部资源、内嵌图片、脚本或 foreignObject。三语均保留可选择的真实正文和图片替代文字。现有 PNG 角色作为独立图片显示，未重新生成或修改。

本轮已直接写入产物，用户无需先运行生成工具才能在 GitHub 看到内容。后续维护者若修改文案，可按原流程重生成；这不授权自动运行测试。

## 两个入口

- [新私有仓库首页](https://github.com/AmatsukiRen/seedbank-public)：查看这版 README 设计。
- `site/index.html`：下载仓库后本地打开，查看完整独立网页。

README 已解释这一区别，并将底部 HTML 链接称为“网页源文件”。本轮没有部署 Pages、创建标签、发布 Release 或改变仓库私有状态。

## 验收

只做文件实施、提交与交付；未运行 SVG 渲染、网页或 GitHub 浏览器验收，也未执行测试、验证例程或构建检查。用户步骤见 [acceptance.md](acceptance.md)。

原研发截图的版本与透明度说明、角色与模型署名均保持原样。此改动不涉及应用 exe。

