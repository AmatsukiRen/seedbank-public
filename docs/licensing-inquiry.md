# 许可询问材料（未发送）

2026-11-03 准备，11 月 4 日补充已确认的角色许可声明与模型发布来源。以下三份分别用于 SDK 分类、角色衍生头像及模型宣传画面；没有发送、提交表单、签约或收到新授权。仅公开声明不明确的具体用途需要询问，不要求作者重新授予已经清楚允许的非商业二创和个人使用。

## 一、Live2D：先咨询分类和免费开源安排

入口：[Live2D 联系表单](https://www.live2d.jp/eng/contact/)，选择 Cubism SDK → SDK Release License (Publication License)。**不直接提交[可扩展应用正式申请表](https://www.live2d.jp/eng/application-publication-license/form/)**：该表包含费用/报告、应用声明、标识和生成式 AI 权利保证等确认，不能当作无承诺咨询。

咨询需要维护者提供联系人姓名、回复邮箱及个人/企业身份；正式申请还涉及发行主体、业务规模、电话、发行地区等。本库不填写虚构身份，不读取账号信息代填，也不把这些个人信息提交 Git。当前免费首发安排不构成永久免费或接受付费条款的承诺。

**Subject: SeedBank 0.0.1 — publication classification and terms for a free open-source AI companion**

Hello Live2D licensing team,

I am preparing SeedBank 0.0.1, a Windows x64 desktop AI companion intended to maintain an individual's memories and life history. The application source and candidate binary are currently private. The proposed first release would offer our own source under MIT and the application free of charge, without bundling users' AI service accounts or third-party Live2D models.

The application uses Python 3.13, PySide6 6.12.0 and live2d-py 1.0.0. The wrapper includes native Cubism components; a previously captured runtime banner reports CsmSDK5-r.5. We have not independently established the embedded Core's exact patch/build identity and can supply binary/component details through an agreed private channel if needed.

Users can select and switch to arbitrary locally obtained .model3.json files. We use the model's existing expressions and motions alongside AI-generated conversation, with a desktop OpenGL display. Our integration does not generate, edit or export Live2D models or textures. A separate, explicitly enabled local text-plugin interface is included. This is not intended as a model-authoring tool or a replacement for illustrators and riggers.

The proposed icon is an AI-assisted derivative of a character reference, and the proposed screenshots show a separately obtained character model. The relevant artwork/brand-use permissions are still being clarified; we are not representing that this clearance is complete. No third-party model source or textures would be submitted with this initial inquiry.

Could you please clarify:

1. Does local loading of arbitrary models make this application an Expandable Application, and what approval route applies to an AI companion of this kind?
2. Are the proposed free, open-source first-release terms eligible for any free-of-charge arrangement? Please explain any fees, reporting, notices, logos or other conditions before we decide whether to apply.
3. How should we handle the Windows binary's embedded Cubism components, our MIT integration source, users' source builds and downstream forks? Does each downstream publisher need a separate approval?
4. What exact SDK/Core version details and distribution materials do you require? Can classification be discussed before we provide cleared showcase artwork?

This is an initial inquiry only, not an acceptance of publication conditions or a statement that SeedBank has been licensed. We have not set a public release date pending clarification.

Thank you.

## 二、角色设计作者：头像与项目标识

联系入口：维护者已提供的 [ZipZipPipe 主页](https://space.bilibili.com/4168597)及[上善无形本人声明](https://www.bilibili.com/opus/1253873972180680713)中的作者入口。分别发送，不假设其中一位可代另一位授权。当前三视图具体绘制者待核实，也请维护者补充其原始发布来源。

随询问审阅的具体成品：[认可头像 PNG](../assets/brand/seedbank-logo.png)、[陪伴页截图](../assets/screenshots/companion.png)。发送前由维护者确认这些附件，不附原始三视图、模型或私人记录；私有 GitHub 链接不能作为对方可访问的附件。

**主题：咨询女仆鲸鱼娘衍生头像在免费 SeedBank 项目中的使用范围**

您好，我在制作个人开源项目 SeedBank，愿景是“给 AI 完整的一生”，希望让 AI 在持续的记忆与经历中成长。计划首个版本 0.0.1 免费发布，目前仓库与安装包仍私有。

我想确认附件中蓝发女仆、闭眼合掌祈愿的半身头像，能否用于 SeedBank 的应用图标、GitHub 仓库头像/README、下载说明及项目介绍。该头像根据维护者提供的角色参考通过 AI 辅助生成，后续只做了圆角透明处理；它不是您绘制的原图，也不会声称由您绘制或获得您的合作背书。

我们会保留“原角色：上善无形；女仆二次设计：ZipZipPipe”的署名和来源，明确角色权利不属于应用代码的 MIT 许可。我们已读到 ZipZipPipe《有关大肥鱼玩偶的重要提醒》中明确的 CC BY-NC-SA 4.0 声明，自身头像改编贡献也按该许可标注；本次只确认尚不明确的参考图来源与具体品牌用途，不请求重新授予已有的非商业二创许可。

请问：

1. 上述具体用途是否在现有许可内？若有额外条件，请告知。
2. 是否允许将该衍生 PNG/转换的图标文件随源码和免费安装包分发？其他开发者非商业 fork 时能否依同一条件保留，还是应替换头像？
3. AI 辅助衍生图是否有特别要求；参考三视图如属另一位绘制者，还应向谁确认？
4. 您希望采用怎样的署名、原帖链接及许可说明？您能确认的是哪些权利范围，还需要联系哪些共同作者？

此次只询问上述免费首发用途，不请求角色独占权、商标注册权、收费产品或商品销售授权。若今后用途改变，会另行确认。感谢您。

## 三、模型发布者：软件截图与介绍

入口：[作者发布视频](https://www.bilibili.com/video/BV1KmxY66EZ3/)及[神宫凉子主页](https://space.bilibili.com/13737731)。UID 已由该视频公开元数据确认。维护者另提供[工房获取页](https://gf.bilibili.com/item/detail/1109618072)，正文未能读取。请发布者确认是否还需霓虹猫_NeonNeko 单独同意。

附件：[五页实机画面目录与来源](screenshots.md)，其中主要模型展示为 companion.png。只发送软件画面，不发送模型、纹理、PSD 或模型包。

**主题：咨询 DeepSeek-chan 免费 Live2D 模型在 SeedBank 项目截图中的展示**

您好，我是 SeedBank 的维护者。我们在本地研发中使用了您配布的 DeepSeek-chan（大肥鱼）模型，准备免费发布开源桌面 AI 陪伴程序 0.0.1，目前仓库和程序仍私有。

我们阅读了随包使用须知：个人直播、视频和作品展示有相应许可，而品牌广告及产品推广需事先确认。因此想请您确认，能否将本地加载模型的程序截图用于 GitHub README、使用教程、下载说明及免费项目介绍。具体截图见附件，均为人工离线示例，不是模型作者背书或合作宣传。

程序与源码不附带模型、纹理、动作或 PSD，用户需从作者发布渠道自行取得模型。我们仅驱动已有表情/动作，不制作或销售模型衍生包；截图中会保留“模型名称：DeepSeek-chan（大肥鱼）；原画及拆分：神宫凉子；Live2D 建模：霓虹猫_NeonNeko；模型来源：神宫凉子免费配布模型”，并注明人设 ZipZipPipe、上善无形。

请问上述免费软件展示用途是否允许？截图能否随项目文档和非商业 fork 保留，应适用什么转载条件？是否还需向建模作者或角色设计作者分别取得同意？我们拟链接上述发布视频及工房获取页；如有更合适的作者渠道，也请告知。

此询问只涉及画面展示与文档，不请求重新分发模型、收费使用或将模型素材转为 MIT。若有署名格式或其他条件，我们会按明确范围落实。谢谢。

## 回复如何记录

只有收到能对应上述用途、文件和回复者身份的明确答复，才更新[许可状态](licensing-review.md)。保存原回复日期和范围，公开仓库只收录经允许公开的摘要/条款，不上传私人邮箱、电话或完整私信。未回复、点赞、一般鼓励或其他项目的授权，都不记录成 SeedBank 获批。
