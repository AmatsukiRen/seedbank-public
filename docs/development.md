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

安装[源码运行依赖](getting-started.md)，另外安装 PyInstaller：

```powershell
.\.venv\Scripts\python.exe -m pip install "PyInstaller==6.22.3"
$env:PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_windows.ps1 -NoInstall -SkipSmoke
```

输出 `dist/seedbank.exe`，从已认可 PNG 转换应用图标。此流程只生产打包，默认不启动产物、不运行测试。
依赖的原始许可证与版本清单由 `packaging/collect_notices.py` 整理；`packaging/package_candidate.py`
将程序、使用说明与许可证组装成 ZIP，并生成 SHA256。
生产包会包含 Python、Qt 和 Live2D 运行库，**不含第三方模型**；公开分发前按 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md) 确认许可。

当前未配置自动发布工作流，提交和打标签不会自动公开仓库或发布二进制。

## 用户执行的离线回归

当前工作约定由用户执行测试。代理未在迁入后运行以下命令：

```powershell
# 临时 HOME、离线保护；日志保留在本地 artifacts，不入 Git
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite core
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite integrations
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_offline.ps1 -Suite plugins
```

使用与运行源码相同的 Python；可通过 `PYTHON` 指定 venv 解释器。Qt 用例使用离屏软件模式，SDK 相关用例使用模拟对象；不代表原生画面实测。
新环境、空模型选择和 Windows 图标需另按 [验收步骤](acceptance.md) 人工确认。
历史真实模型观察脚本及其固定人工档案未迁入；没有继承任何维护者的测试调用额度。

不要直接对真实个体运行调试、测试、示例写入或并行写会话。分享问题时只提供人工复现。
