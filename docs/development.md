# 开发与构建

## 源码结构

| 路径 | 内容 |
| --- | --- |
| `tools/seed/seedbank` | 生命包、记忆、行动、模型与渠道逻辑 |
| `tools/seed/seedbank/quick` | Qt Quick 桥接、QML、原生 Live2D 渲染 |
| `tools/seed/test_*.py` | 人工数据离线用例 |
| `eggs/open.egg` | 默认开放出生种子 |
| `eggs/dafeiyu.egg` | 历史格式与回归用种子，不是默认出生，也不是角色模型 |
| `adapters` | AstrBot 插件与 OneBot 适配示例 |
| `examples/plugins/hello` | 本地文本插件示例，供设置中的插件管理页导入 |
| `spec` | 生命包及接口协议；历史格式版本独立于应用版本 |
| `packaging` | Windows 生产与用户验收入口 |

应用版本唯一来源为 `tools/seed/seedbank/__init__.py`；Python 元信息、CLI、Qt 窗口与 Windows 文件版本读取它。
`release-plan.json` 是发行状态记录；生命包、提示与协议格式编号不随 0.0.1 重置。

## Windows 生产打包

创建 Python 3.13 的独立虚拟环境，使用已登记的 Windows 依赖版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r packaging/requirements-windows.lock
$env:PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -NoInstall -SkipSmoke
```

输出 `dist/seedbank.exe`，从已认可 PNG 转换应用图标。此流程只生产打包，默认不启动产物、不运行测试。
依赖的原始许可证与版本清单由 `packaging/collect_notices.py` 整理；`packaging/package_candidate.py`
将程序、使用说明与许可证组装成 ZIP，另导出对应提交的 Source ZIP，并生成两者的 SHA256。先提交实际源码，再生产和组包：`runtime-build.json` 记录 exe 对应的干净源码提交，组包必须使用该提交，不能把旧 exe 与新 HEAD 混合交付。
生产包会包含 Python、Qt 和 Live2D 运行库，**不含第三方模型**；公开分发前按 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md) 确认许可。

当前未配置自动发布工作流，提交和打标签不会自动公开仓库或发布二进制。

`requirements-windows.lock` 固定本次构建的直接与传递依赖，不含本机路径或凭据。更新依赖时，在已安装目标版本的 Windows 环境运行 `python packaging/freeze_dependencies.py` 并复测；版本锁定不保证不同系统产生逐字节相同的 exe。构建明确排除未使用的 Qt Virtual Keyboard DLL 和输入插件，其许可与普通 Qt LGPL 模块不同。

2026-11-03 后续许可核对补充了 QML 调试插件及其 Qt Quick 3D 依赖的排除，保留 Qt Quick 2D；照片入口不接收 PDF，也排除闲置 qpdf/Qt6Pdf。通知收集器补入 LGPLv3/GPLv3 正文。新包的生产记录以相邻 `runtime-build.json` 为准，测试结果独立记录。Qt 源码来源、替换重建步骤及待办见 [Qt 发行材料](qt-redistribution.md)，不把普通界面测试视为许可认证。

单独准备候选而不覆盖当前 `dist/seedbank.exe`：

```powershell
& packaging/build_windows.ps1 -NoInstall -SkipSmoke -OutputDirectory dist/candidate-preparation
& $env:PYTHON packaging/package_candidate.py --executable dist/candidate-preparation/seedbank.exe --output-dir dist/candidate-preparation
```

以上是生产流程，不运行验收；没有验收报告的 ZIP 会明确标为未测试。源码、文档和程序从同一干净提交产生，`package_candidate.py` 不上传、发布或自动替换用户正在使用的程序。

## 隔离离线回归

以下命令均只使用临时人工数据。执行结果与范围见 [验收记录](acceptance.md)：

```powershell
# 临时 HOME、离线保护；日志保留在本地 artifacts，不入 Git
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite core
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite integrations
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite plugins
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite security
```

使用与运行源码相同的 Python；可通过 `PYTHON` 指定 venv 解释器。Qt 用例使用离屏软件模式，SDK 相关用例使用模拟对象；不代表原生画面实测。
新环境、空模型选择和 Windows 图标需另按 [验收步骤](acceptance.md) 人工确认。
历史真实模型观察脚本及其固定人工档案未迁入；没有继承任何维护者的测试调用额度。

GitHub 的 `Offline regressions (manual)` 工作流只有 `workflow_dispatch` 入口，由维护者明确启动；push、PR 和标签不自动触发，也不执行模型或聊天平台请求。

不要直接对真实个体运行调试、测试、示例写入或并行写会话。分享问题时只提供人工复现。

## 检查实际 Windows 包

用户执行的完整入口：

```powershell
& packaging/run_candidate_checks.ps1 -Executable dist/candidate-preparation/seedbank.exe
# 可追加 -Model "获准使用的完整路径.model3.json" 来覆盖原生 Live2D
```

它依次运行打包专项、实际归档/图标与 ZIP 通知检查、隔离应用检查；任何一步失败立即停止。控制台与结果位置保存到 `artifacts/candidate-check-*.log`，不会自动部署或联网。ZIP 必须已在同目录生产。以下是各独立入口：

```powershell
# 只读取 exe 的归档和图标资源，不启动应用
.\.venv\Scripts\python.exe packaging/verify_candidate.py dist/seedbank.exe
# 启动当前 exe 的隔离界面、插件子进程和五页采集；无桌面输入操作
.\.venv\Scripts\python.exe packaging/run_packaged_checks.py dist/seedbank.exe artifacts/package-check
# 若明确选定了获准使用的本地模型，可追加 --model "完整路径.model3.json"
# 这会增加两轮原生渲染、动作、重载与休眠恢复检查，不修改模型文件
```

每次使用新的输出目录。入口创建临时偏好和人工生命包，不读取个人连接设置；不调用真实模型或聊天平台。原生检查仍不等于各种显卡、所有 Live2D 模型、真实渠道或长期稳定性均已验收。

仓库内容检查：`python tools/repository_check.py --history` 检查本地文档链接、JSON、排除路径与历史对象中的常见凭据模式，输出仅含文件名，不显示匹配值；它不是覆盖所有密钥类型的安全认证。只采集文档画面可用 `packaging/capture_pages.ps1`，见[截图说明](screenshots.md)。
