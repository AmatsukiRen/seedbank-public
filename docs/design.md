# SeedBank 对外页面设计

2026-11-03 第二稿。面向 AI 陪伴与数字生命的使用者，采用白底、钴蓝和少量品红的复古桌面出版风格，以品牌角色和六章叙事作为视觉中心。原生 HTML/CSS/JavaScript，无依赖、无服务端。

首屏：**让相遇，有后来。**

## 本轮设计

- 角色海报：保留认可的头像，用网格底、蓝色硬边框与轻微错位投影组成完整的视觉区域。
- 叙事书页：左侧章节目录，右侧白纸阅读区；品红用于引句和当前章的标记。
- 截图画廊：一张主图与两张次图，保留原始程序画面，点击打开原 PNG。
- 功能索引：五个日常入口以编号排版，不将每段文字都装进相同卡片。
- 可见署名：人物设计、Live2D 原画、拆分、建模与模型来源直接出现在页面及各语 README。
- 语言入口：简体中文、English、日本語的独立静态页面。关闭 JavaScript 仍可切换，全部章节顺序可读。
- 动态仅用于按钮和图片链接反馈，不自动播放、轮换故事或模拟聊天。

设计取值：DESIGN_VARIANCE 8、MOTION_INTENSITY 3、VISUAL_DENSITY 4。白底遵循用户偏好，品红作为少量强调，主操作统一钴蓝。

## 页面结构

首屏与角色 → 为什么想留住今天 → 开放出生 → 六章故事 → 研发实机截图 → 日常功能 → 初次见面准备与问答 → 素材创作者 → 页尾。

故事见[中文](story.md)、[English](story.en.md)、[日本語](story.ja.md)。它从命名、雨天与书店，写到修订、第一件作品、目标和恢复；明确为创作示例，不把文学叙事包装成模型能力验收。

## 文件结构

GitHub 仓库首页有单独的视觉实现：README 引用 assets/readme/ 中的三语 SVG 标题、导航与章节横条，保留原 PNG 头像及正文，不依赖 site/style.css。详见 [GitHub 首页设计](readme-design.md)。独立网页仍由 site/*.html 提供，未部署在线站点。

| 文件 | 作用 |
| --- | --- |
| `site/index.html`、`en.html`、`ja.html` | 可直接双击的三语页面 |
| `site/style.css` | 白底主题、版式、响应式与键盘焦点 |
| `site/story.js` | 章节切换、展开全文与章节定位 |
| `site/content/*.json` | 三语完整文案源 |
| `tools/render-pages.mjs` | 维护者重生成静态 HTML、README、故事文档的工具 |
| `tools/readme-design.mjs` | GitHub 首页专用模板与原生 SVG 排版 |
| `assets/readme/*.svg` | 三语品牌标题、五个导航入口与五个章节横条 |
| `README*.md` | 三语 GitHub 首页 |
| `docs/story*.md` | 六章连续阅读版 |
| `assets/brand/seedbank-logo.png` | 已认可的品牌头像 |
| `assets/screenshots/*.png` | 历史研发截图，已从首页撤下 |

修改文案时编辑对应 JSON，再由维护者运行 `node tools/render-pages.mjs` 生成静态内容。它是文件生成工具，不会启动浏览器或调用模型。静态页面与 Markdown 本次已写入，无需用户先生成才能预览。

## 可读性与交互设计

钴蓝 `#2450BD`、深蓝文字 `#182E55`、次级文字 `#50627C`、品红 `#B91D72`、浅底 `#EFF4FF`。主要按钮白字蓝底，次级入口带下划线，章节选中同时有背景、字重与左边线，焦点使用品红轮廓。

960px 以下导航换到第二行；680px 以下角色与文字顺排、故事目录两列、画廊单列。正文不限制固定高度，长译文可自然展开。为减少动态效果和打印提供 CSS 分支。

## 素材与真实状态

旧版实机画面按日期与程序版本标注，见[来源](screenshots.md)。不得把它们改标成 0.0.1 当前界面。首发还需要用户采集候选版的日记、记忆来源与修订截图。

[人设与 Live2D 出处](assets.md)分开署名。完整模型不迁入，不把图标衍生处理说成角色原创。

首发仍计划为 0.0.1 Alpha；本库保持 PRIVATE，没有 Pages、公开下载、标签或 Release。页面保留草稿说明和 noindex。

## 参考

[dsh-wallpaper-engine](https://github.com/elysia395/dsh-wallpaper-engine) 的统一品牌画面与导航，[dsh-pet](https://github.com/PC2005-cloud/dsh-pet) 的实机展示组织。只参考信息与版式方向，没有复制这些项目的素材或代码。

## 验收状态

本轮只实施与整理，未运行页面、浏览器自动化、脚本验证、构建检查或应用测试。没有宣称移动端、键盘或各浏览器已经验证通过。用户步骤见[acceptance.md](acceptance.md)。


## 开发者参与与当前画面

三语首页新增开发扩展区域：已有桥接、模型适配与载体接口分别列出，统一插件运行时明确列为待建设。CONTRIBUTING.md、docs/extensions.md 与离线 Python 示例提供进一步入口。旧版同页三图不再展示；五页实机图待用户运行当前交付采集后补入，状态见 screenshots.md。
