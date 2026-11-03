# 实机画面的来源

本次只整理既有文件，**没有重新运行程序、图形自检或截图测试**。

## 画面登记

三张 PNG 来自 2026-11-03 的研发验收中，第二轮原生 Live2D 隔离场景。使用当天 **01:50 研发版**，对应窗口中仍可见旧版品牌写法。

| 仓库文件 | 原截图文件名 | 采集时间（Asia/Shanghai） | 内容 |
| --- | --- | --- | --- |
| `assets/screenshots/idle.png` | `report-1-idle.png` | 2026-11-03 02:28:31 | 陪伴页静止画面，1280×840 |
| `assets/screenshots/wave.png` | `report-1-wave.png` | 2026-11-03 02:28:33 | Live2D 动作画面，1280×840 |
| `assets/screenshots/small.png` | `report-1-small.png` | 2026-11-03 02:28:51 | 缩小窗口，860×640 |

原研发库的记录为 `docs/80-all-acceptance.md`，原图位于该库 `build/all-acceptance-20261103/native-avatar/`。不把原始运行日志、本机绝对路径和生命包复制到对外仓库。

## 范围与呈现

- 场景名称为“原生渲染隔离测试”，人工数据、空白聊天，不是私人个体的日记或对话。
- 这三张截图确实来自程序运行，页面没有制作假软件界面。
- 不包含当前品牌版的日记、记忆修订画面；相应首发截图仍待在候选版上由用户采集。
- 图片按原文件复制，含 Alpha 透明度。网页以 `#f4f8fc` 背景承接透明部分，不将浅色背景写入 PNG。
- 单独打开 PNG 或在 GitHub 深色主题中查看，透明区域可能采用查看器背景。这不是程序截图中新增的黑色矩形；本地介绍页提供一致的浅色呈现。
- 静态动作帧不证明帧率、持续稳定性或所有模型兼容性。
- 这些画面早于目前品牌更新，不作 0.0.1 候选的界面或验收承诺。

## 模型署名

DeepSeek-chan（大肥鱼），神宫凉子免费配布模型。**原画及拆分：神宫凉子；Live2D 建模：霓虹猫_NeonNeko；人设：ZipZipPipe、上善无形。**

[完整出处与使用说明](assets.md) · [作者原始预告](https://www.bilibili.com/video/BV1ALnw6YEGK)

## 首发前替换计划

由用户在 0.0.1 候选与独立人工包中采集陪伴、日记正文、记忆来源及修订画面，登记准确提交、程序标识、日期与场景，再更新页面和本记录。保留当前研发图片的历史身份，不更改旧截图日期或把它们重新标为候选实测。

---

**English:** Real captures from the 01:50 development build, taken on 3 November 2026 using an isolated artificial scenario. They predate current branding, contain alpha transparency, and are not 0.0.1 acceptance evidence. No capture or application test was rerun for this page update.

**日本語:** 2026年11月3日01:50開発版を用い、同日撮影した独立した架空のシナリオです。現在のブランド変更前の画面で、透明部分があります。0.0.1の検証完了を示すものではなく、本更新でアプリや撮影テストは再実行していません。

