# 休眠与恢复弹窗的关闭入口修复

2026-11-04 用户报告：打开「生活 → 休眠与恢复」后没有可用关闭入口。截图中弹窗已显示，底部没有关闭按钮。

## 原因

原实现将 `Close` 只写在自定义 `DialogButtonBox.standardButtons` 上，父 `Dialog.standardButtons` 仍是 `NoButton`。Qt 6.12 的 `QQuickDialog::setFooter` 会把父弹窗的值传给底部按钮栏，清掉这个标准按钮。同时 `Popup.NoAutoClose` 禁用了 Esc 和外部点击，页头又没有关闭按钮，因此无法退出弹窗。

依据为当前 Qt 6.12 完整源码中的 `qtdeclarative/src/quicktemplates/qquickdialog.cpp`，以及 [Dialog 标准按钮说明](https://doc.qt.io/qt-6/qml-qtquick-controls-dialog.html)、[Popup Esc 与焦点说明](https://doc.qt.io/qt-6/qml-qtquick-controls-popup.html)。这次只读取实现和用户截图，没有运行应用复现。

## 修改

- 页头右侧与底部改为显式「关闭」按钮，放在内容滚动区之外。
- 弹窗取得焦点并允许 Esc 关闭；点击外部仍不关闭，避免误触。
- 关闭入口不依赖加载状态、说明文字或确认开关，不调用休眠/恢复操作。
- 不修改生命周期数据格式、休眠与恢复的确认条件或历史记录。

原有用例只通过 QML `close()` 结束弹窗，没有实际点击关闭按钮，因此不能证明用户能退出。新增三项用例覆盖鼠标关闭、Esc（包括编辑框焦点）及状态读取中关闭；窗口尺寸包含 1280×840、860×640、640×420，以及三主题、四语和大字模式。另保留原有明确休眠/恢复用例。

## 待用户执行

本修复尚未测试。按当前约定，代理不运行回归、应用自检或构建检查；生产打包不是测试通过的证据。

离线专项入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/run_dialog_close_checks.ps1
```

该入口只使用临时人工档案、离线模板与离屏 Qt，并阻断网络。输出 `artifacts/dialog-close-*.log`。由用户运行后再读取实际结果，不沿用 0.0.1 旧版验收结论。

手动验收修正版程序：

1. 正常关闭旧程序，打开独立修正版，使用人工测试个体。
2. 进入「生活 → 休眠与恢复」，分别尝试右上角关闭、底部关闭和 Esc。
3. 缩小窗口、切换大字模式后重复；不用滚动到底就应能关闭。
4. 填写说明并勾选确认，但不点休眠/恢复，只关闭弹窗；再次进入时状态和选择历史应保持原样。

本轮修正版独立交付，不覆盖已发布的 v0.0.1 附件或移动标签。应用版本号保持 0.0.1，具体修复候选以相邻 `runtime-build.json` 的源码提交与摘要区分。
