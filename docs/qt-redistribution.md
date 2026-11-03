# Qt 发行材料与未完成项

2026-11-04 更新。用户已完成新候选的打包与隔离程序检查，但 **Qt 发行材料尚未全部完成**。本页不是商业许可证，也不改变应用自身 MIT 许可。

## 旧包问题与新候选处理

所读现有 Windows exe SHA256 为 `f709a04ab7feb9c2294905835927ade0474629fa28d23e5293a1929597bf02c6`，对应此前源码提交 `31dedd986cbadd89593ada23985c276195418974`。

归档及 DLL 导入记录表明：`PySide6/plugins/qmltooling/qmldbg_quick3dprofiler.dll` 引用 `Qt6Quick3DUtils.dll`。这是未使用的开发调试依赖，不是 Live2D 本身，也不是普通 Qt Quick 2D 控件。Qt 的 [Quick 3D 6.12 文档](https://doc.qt.io/qt-6.12/qtquick3d-index.html)说明其商业/GPLv3 许可；对应 [utils 源码](https://github.com/qt/qtquick3d/blob/v6.12.0/src/utils/qssgutils_p.h)同样标注 GPL-3.0-only 或商业许可，[构建文件](https://github.com/qt/qtquick3d/blob/v6.12.0/src/utils/CMakeLists.txt)将其编入 Quick3DUtils。

已在最终 PyInstaller 清单排除整组 QML 调试插件和 Quick 3D 组件，并保留 Qt Quick 2D、控件、OpenGL 与原生 Live2D 依赖。照片选择只接受 PNG/JPEG/WebP/BMP，因此也排除闲置 qpdf 与 Qt6Pdf；它们本身具有 LGPL 选项，不因本次删除而称其为 GPL-only。实际包检查器使用同一排除规则。之前的 Virtual Keyboard 排除保留。**2026-11-04 用户运行的新候选 `1da9030c…` 通过实际归档排除、ZIP 通知及隔离界面/原生 Live2D 检查，详见[验收记录](acceptance.md)。**

已安装的 PySide6/shiboken6 6.12.0 wheel 许可证目录只提供商业许可引用，元数据则列 LGPL/GPL 选项，不能靠复制该目录完成开源许可通知。现已从 Qt `v6.12.0` 原库补入 LGPLv3 及它引用的 GPLv3 全文，保留来源 Git blob 标识；候选通知收集器将两份正文及说明放入 `third-party/qt/`，并在相关依赖索引中列出。

## 源码取得与替换路径

Qt 官方列出了 [Qt 6.12.0 源码 ZIP](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/qt-everywhere-src-6.12.0.zip.mirrorlist)及 [PySide/shiboken 6.12.0 源码](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/pyside-setup-everywhere-src-6.12.0.tar.xz.mirrorlist)。上游公布的版本、大小和摘要记录于 [sources.json](../packaging/licenses/qt/sources.json)。本轮只核对下载元数据，没有下载并确认全部源码与 wheel 二进制逐项对应。

LGPL 库适用的修改及为调试这些修改而进行逆向工程的权利应保留。SeedBank 不要求维护者签名密钥才能运行重建程序。单文件 exe 不能用“把 DLL 放在旁边”作为已验证的替换说明；应从应用源码在独立构建环境中使用接口兼容的修改版 PySide/Qt 重建：

1. 按[开发说明](development.md)建立独立环境，安装锁定的构建依赖。
2. 从对应 Qt/PySide 源码构建修改库；以匹配 Python ABI、架构与 Qt 版本的自建 wheel 安装到该环境，记录修改和构建参数。不要覆盖系统或用户日常环境。
3. 将 `PYTHON` 指向该环境，用 `packaging/build_windows.ps1 -NoInstall -SkipSmoke` 重建，避免安装步骤把修改库换回发行 wheel。
4. 在人工数据中运行所得 exe，验证实际装载了修改库，而非原 wheel 或系统副本；保存版本、来源、修改说明和结果。

这是待执行的重建路线，**尚未通过修改库重建实验**。Qt 自身源码的编译参数、第三方依赖和所需安装信息仍需按实际发行 wheel 补齐；不能用应用自身源码包代替全部 LGPL 对应源码。

## 公开前剩余交付

| 项目 | 当前状态 |
| --- | --- |
| 未使用 GPLv3/commercial 调试依赖 | 用户的新包归档检查通过，隔离原生渲染两轮通过 |
| LGPL/GPL 正文与显著通知 | 原文已入源码及组包流程；用户 ZIP 通知检查通过 |
| Qt/PySide 对应源码、构建修改和安装信息 | 官方源包位置已记录；尚未整理完整对应源码附件和等同可取得方式 |
| Qt 内嵌第三方组件声明 | 尚未按 wheel 构建配置/SBOM 完整匹配，不能以 Python 包元数据代替 |
| PDF 插件 | 新候选实际归档排除检查通过；若未来重新加入，须补齐其 PDFium 等依赖材料 |
| 修改库重建后运行 | 步骤已准备，尚未执行 |

依据：[Qt LGPL 义务说明](https://www.qt.io/development/open-source-lgpl-obligations)、[Qt 组件许可与第三方清单说明](https://doc.qt.io/qt-6/licensing.html)。不需要仅因使用 Qt 就默认购买商业许可；应先完成所选开源许可路线的实际义务。

## 由用户执行的本轮检查

本入口已由用户于 2026-11-04 执行，原日志保留；代理仅读取结果。以下供用户后续需要时复跑，不表示本轮再执行；使用专门构建环境，不操作真实生命包，每次输出目录须新建：

```powershell
& packaging/run_candidate_checks.ps1 -Executable dist/candidate-preparation/seedbank.exe
# 原生渲染需追加 -Model "获准使用的完整模型路径.model3.json"
```

该入口不构建，须先按[开发说明](development.md)生产相邻的 exe 和 ZIP；执行时每步成功才继续，失败保留日志。新增五个离线方法针对误收调试/PDF 依赖、保留 2D/照片依赖、通知正文和版本升级保护；并非完整许可审计。实际归档与 ZIP 检查分别核对禁入组件及 `third-party/qt/`，随后才启动隔离程序。未传模型路径时不宣称原生 Live2D 已验收，不自动替换固定入口、上传或公开发行。
