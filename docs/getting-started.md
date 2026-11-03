# 开始使用 SeedBank

[首页](../README.md) · [模型接入](model-services.md) · [开发](development.md)

## Windows 程序包

当前版本为 **0.0.2 预览版**，从 [GitHub Releases](https://github.com/AmatsukiRen/seedbank-public/releases/tag/v0.0.2) 下载 Windows x64 程序包。
解压整个 `SeedBank-0.0.2-windows-x64.zip`，双击其中的 `seedbank.exe`。从 0.0.1 升级时先备份自己的生命包，正常退出旧程序，解压到新目录后打开原生命包即可；无需重建个体。
不要只复制旧研发交付中的固定启动器；本包的 exe 是完整运行程序。
当前包未代码签名。系统若提出安全提示，应先核对下载来源与随附 SHA256，不能据此宣称已通过安全认证。

1. 首次运行选择创建一个个体，指定自己的保存目录与名字；默认从开放种子出生。
2. 设置中先使用离线模板也可以体验页面；连接模型时选择服务，填入自己的模型名和 API Key。
3. 到“设置 → 外观 → 角色与舞台”选择自己有权使用的 `.model3.json`。模型需保留完整目录；程序包不附带第三方模型。
4. 陪伴、日记、记忆、生活分别呈现对话、日页、记忆来源和成长。放大角色后可以拖动位置，滚轮缩放。
5. 模型生成的回复可以携带表情与招手提示；现阶段没有语音合成和音频口型同步。

没有模型文件时显示选择提示，对话和记录仍可使用。用户的角色外观不修改出生身份或记忆。
演示中的 DeepSeek-chan 公皮只用于维护者演示，仓库和下载包都不附带该资源。需要该形象时请自行向作者获取：[发布视频](https://www.bilibili.com/video/BV1KmxY66EZ3/) · [模型获取页](https://gf.bilibili.com/item/detail/1109618072)，并遵守模型的使用说明与署名要求。
程序会读取当前 Windows 用户已有的 SeedBank 配置；维护者验收请使用独立 Windows 测试账号，避免自动打开既有个体。

## 选择哪一种模型

**对话模型**负责交流与生成内容，在创建个体时或“设置 → 对话”选择服务。入口可展开已有云端预设、本地服务与兼容协议说明；具体配置见[模型接入](model-services.md)。使用自己的 API Key 与账号可用的模型 ID。Ollama、LM Studio、vLLM 需要先启动本机服务，SeedBank 不直接导入 GGUF 或权重文件。

**角色模型**负责外观展示，在陪伴页或“设置 → 外观 → 角色与舞台”选择：

- 当前入口支持 Live2D Cubism 的 `.model3.json` 运行时模型配置。先完整解压模型包，再选择其中的该文件。
- 保留配置引用的 `.moc3`、纹理、动作、表情、物理等文件和原目录结构；只复制一个 JSON 文件不能加载完整模型。引用文件需位于模型目录内。
- 不直接加载 ZIP、PNG / PSD、Cubism 编辑工程 `.cmo3`、旧版 `.model.json`，也没有 VRM、FBX 或 Spine 渲染器。请向模型作者取得对应的 Live2D 运行时导出。
- `.model3.json` 后缀不保证所有导出版本都兼容当前运行库。自动表情、待机与招手依赖具体资源和名称映射；当前 DeepSeek-chan（大肥鱼）有专门适配，其他模型不会仅因成功显示就拥有全部联动动作。未逐一验收其他模型，不宣称通用动作适配已完成。
- 程序不附带第三方角色，请按作者许可取得并使用。更换展示角色不修改出生身份或记忆。

界面提供中文、English、日本語、한국어的格式及接入提示，详细说明可展开；文件选择器会标明 `.model3.json`。

## 从源码启动

在仓库根目录使用 Python **3.11 或更新版本**；当前 Windows 生产包使用 Python 3.13 x64。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./tools/seed[desktop,channels]"
.\.venv\Scripts\python.exe packaging/windows_entry.py
```

只有命令行核心可省略 extras：`pip install -e ./tools/seed`，然后使用 `python tools/seed/seed.py`。
种子目录必须保留；非可编辑安装时通过 `SEEDBANK_EGG` 指定 `eggs/open.egg`。
未承诺 macOS、Linux 原生 Live2D 画面已验收。

## 保存与连接

生命包在你选择的目录；本机偏好位于 `~/.seedbank`。备份生命包不等于备份机器凭据。
Windows API Key 使用当前用户的 DPAPI 加密，生命包只保存引用；换电脑后需要重新填写。
模型服务、聊天机器人账号均由用户配置，程序不附带维护者账号或公共密钥。
联网对话会把所选上下文发送到配置的服务；外部渠道默认需要用户明确配置并启动。

休眠需要明确操作，保留档案并停止自动活动，允许明确恢复；关闭窗口不等于告别。
遇到异常请附最小人工复现、程序版本和去除个人信息后的报错，不上传真实生命包或完整聊天日志。
