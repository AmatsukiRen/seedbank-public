import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs as Native

Dialog {
    id: dialog
    objectName: "archiveDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(780, parent ? parent.width - 32 : 780)
    height: Math.min(760, parent ? parent.height - 32 : 760)
    modal: true
    closePolicy: Popup.NoAutoClose
    title: Style.tr("备份与恢复")
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("备份与恢复"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    readonly property var stateData: bridge.archiveState
    readonly property var info: stateData.info || ({})
    readonly property var progressData: stateData.progress || ({})
    readonly property var resultData: stateData.result || ({})
    function stageLabel(stage) {
        return Style.tr(({planning: "正在整理备份清单", writing: "正在保存备份", reading: "正在读取备份清单", restoring: "正在恢复并核对文件", publishing: "正在完成保存"})[stage] || "正在整理，请稍候…")
    }
    contentItem: ScrollPane {
        id: scroll
        ColumnLayout {
            width: scroll.availableWidth; spacing: 14
            LabelText { text: bridge.notice; color: bridge.error ? Style.danger : Style.muted; Layout.fillWidth: true }
            LabelText { text: Style.tr("恢复到新的文件夹，保留原始身份、经历与未完成输入。恢复后不会自动切换当前生命包或重新发送消息。"); Layout.fillWidth: true; color: Style.muted }
            LabelText { text: Style.tr("恢复产生存档副本；两份档案分别继续使用后，新增经历不会自动合并。"); Layout.fillWidth: true; color: Style.muted }
            AppButton { visible: bridge.ready; text: Style.tr("创建当前生命包的备份"); enabled: !bridge.busy; onClicked: bridge.backupNow() }
            Field { id: archiveFile; objectName: "archiveFile"; caption: Style.tr("备份 ZIP 文件"); enabled: !bridge.busy; Layout.fillWidth: true; onEdited: bridge.clearBackupPreview() }
            Flow {
                Layout.fillWidth: true; spacing: 8
                AppButton { text: Style.tr("选择备份文件"); enabled: !bridge.busy; onClicked: chooseBackup.open() }
                AppButton { objectName: "inspectArchive"; text: Style.tr("读取备份信息"); enabled: !bridge.busy && archiveFile.text.trim() !== ""; onClicked: bridge.inspectBackup(archiveFile.text) }
            }
            Panel {
                visible: !!dialog.info.manifest_digest; Layout.fillWidth: true
                caption: dialog.info.pack_name || Style.tr("备份信息")
                LabelText { text: dialog.info.created_at || ""; Layout.fillWidth: true }
                LabelText { objectName: "archiveFileCount"; text: Style.tr("归档文件：{count}", {count: dialog.info.files || 0}); Layout.fillWidth: true }
                LabelText { text: Style.tr("恢复内容大小：{size} MiB", {size: ((dialog.info.source_bytes || 0) / 1048576).toFixed(2)}); Layout.fillWidth: true }
                LabelText { text: Style.tr("这是清单信息；文件内容将在恢复时逐一核对。"); Layout.fillWidth: true; color: Style.muted }
            }
            Field { id: destination; objectName: "archiveDestination"; caption: Style.tr("新的生命包文件夹"); text: bridge.defaultParent + "/恢复的生命包.life"; enabled: !bridge.busy; Layout.fillWidth: true }
            AppButton { text: Style.tr("选择恢复位置"); enabled: !bridge.busy; onClicked: chooseParent.open() }
            LabelText { text: Style.tr("填写尚不存在的新文件夹路径。已有文件夹不会被覆盖。"); Layout.fillWidth: true; color: Style.muted }
            AppButton { objectName: "restoreArchive"; text: Style.tr("恢复到新文件夹"); enabled: !bridge.busy && !!dialog.info.manifest_digest && destination.text.trim() !== ""; onClicked: bridge.restoreBackup(archiveFile.text, destination.text) }
            ColumnLayout {
                visible: !!dialog.stateData.running; Layout.fillWidth: true
                LabelText { text: dialog.stageLabel(dialog.progressData.stage); Layout.fillWidth: true }
                LabelText { text: Style.tr("已处理 {count} 个文件，{size} MiB", {count: dialog.progressData.files || 0, size: ((dialog.progressData.processed_bytes || 0) / 1048576).toFixed(2)}); Layout.fillWidth: true }
                ProgressBar {
                    Layout.fillWidth: true; from: 0; to: dialog.progressData.total_bytes || 1
                    value: dialog.progressData.processed_bytes || 0
                    indeterminate: dialog.progressData.total_bytes === null || dialog.progressData.total_bytes === undefined
                }
                AppButton { text: Style.tr(dialog.stateData.cancelling ? "正在取消…" : "取消本次操作"); enabled: !dialog.stateData.cancelling; onClicked: bridge.cancelArchive() }
            }
            LabelText { text: dialog.resultData.pack || dialog.resultData.file || ""; visible: text !== ""; Layout.fillWidth: true }
            AppButton { visible: !!dialog.resultData.pack && !bridge.ready; text: Style.tr("打开恢复的生命包"); enabled: !bridge.busy; onClicked: { bridge.openPack(dialog.resultData.pack); dialog.close() } }
            LabelText { visible: !!dialog.resultData.pack && bridge.ready; text: Style.tr("恢复已完成。关闭当前窗口后，可选择恢复出的生命包继续使用。"); Layout.fillWidth: true; color: Style.muted }
            AppButton { text: Style.tr("关闭"); enabled: !dialog.stateData.running; onClicked: dialog.close() }
        }
    }
    Native.FileDialog { id: chooseBackup; title: Style.tr("选择备份文件"); nameFilters: ["ZIP (*.zip)"]; onAccepted: { archiveFile.text = selectedFile.toString(); bridge.inspectBackup(archiveFile.text) } }
    Native.FolderDialog { id: chooseParent; title: Style.tr("选择恢复位置"); onAccepted: destination.text = selectedFolder.toString() + "/恢复的生命包.life" }
}
