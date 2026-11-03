# SeedBank 的 README 设计

项目介绍集中在 GitHub README：品牌、故事、功能、使用方式、扩展接口与素材署名都能直接阅读。保留简体中文、英文、日文，不再维护独立 HTML 站点。

## 视觉与内容

白底、钴蓝标题和少量品红强调，沿用已认可的女仆头像。首页以“让相遇，有后来。”开始，用六章故事说明经历如何延续，再提供五个功能入口和具体开发方向。

正文保留可选择的文字；SVG 用于品牌标题、导航与章节横条，附替代文字。头像独立使用 PNG，不重新绘制。GitHub 的显示以 Markdown 与仓库内资源为准。

内部进度在原研发库记录，不另设对外进度页。不在每个章节重复“私有设计稿”等工作状态；已实现能力、规划与文学示例仍需区分。

## 维护文件

| 文件 | 用途 |
| --- | --- |
| `README.md`、`README.en.md`、`README.ja.md` | 三语首页 |
| `docs/content/*.json` | README 与完整故事的三语文案源 |
| `tools/render-readme.mjs` | 生成 Markdown 与标题图形，不生成 HTML |
| `tools/readme-design.mjs` | README 模板与 SVG 排版 |
| `assets/readme/*.svg` | 品牌标题、五个导航和五个章节横条 |
| `docs/story*.md` | 六章完整故事 |
| `docs/extensions.md`、`CONTRIBUTING.md` | 接口、扩展方向与参与方法 |

维护者修改文案后运行 `node tools/render-readme.mjs` 生成文件。普通读者直接阅读 README，无需安装依赖或生成网页。

新图应来自同一当前程序的五个不同页面，包含实际窗口底色及版本记录。旧三图已撤下，见[截图说明](screenshots.md)。素材署名见[assets.md](assets.md)。
