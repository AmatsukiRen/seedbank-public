import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

Item {
    id: welcome
    property int step: 0
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 4; spacing: 16
        LabelText { text: Style.tr("初次见面"); font.pixelSize: 34 * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
        LabelText { text: Style.tr("从一次初见开始，慢慢形成自己的一生。"); color: Style.muted; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; spacing: 24
            ScrollPane {
                id: scroll
                objectName: "welcomeScroll"
                Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth
                ColumnLayout {
                    width: scroll.availableWidth - 14; spacing: 18
                    Panel {
                        Layout.fillWidth: true
                        caption: Style.tr("名字与住处")
                        Field { id: fishName; caption: Style.tr("名字"); text: ""; Layout.fillWidth: true }
                        Field { id: folder; caption: Style.tr("她住在哪里"); text: bridge.defaultParent; Layout.fillWidth: true }
                        AppButton { text: Style.tr("选择文件夹"); enabled: !bridge.busy; onClicked: chooseParent.open() }
                    }
                    Panel {
                        Layout.fillWidth: true
                        caption: Style.tr("对话方式")
                        detail: Style.tr("可以先离线认识她，之后再到设置里换模型。")
                        ModelServiceHelp { Layout.fillWidth: true }
                        Choice { id: preset; Layout.fillWidth: true; model: bridge.presets(); textRole: "label"; Accessible.name: Style.tr("对话方式") }
                        LabelText { visible: preset.currentIndex >= 0 && preset.model[preset.currentIndex].adapter !== "codex"; text: preset.currentIndex >= 0 ? preset.model[preset.currentIndex].hint : ""; Layout.fillWidth: true; color: Style.muted }
                        LabelText { visible: preset.currentIndex >= 0 && !!preset.model[preset.currentIndex].api_key_env && ["openai-compatible", "anthropic"].indexOf(preset.model[preset.currentIndex].adapter) >= 0; text: Style.tr("创建后请到设置填写 Key 和模型 ID，再开始对话。"); Layout.fillWidth: true; color: Style.muted }
                        LabelText { visible: preset.currentIndex >= 0 && preset.model[preset.currentIndex].adapter === "codex"; text: Style.tr("使用本机 Codex 的 ChatGPT 登录与账号额度；无需填写密钥。当前支持文字，图片仅归档。"); Layout.fillWidth: true; color: Style.muted }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        AppButton { text: Style.tr("打开现有生命包"); enabled: !bridge.busy; onClicked: openExisting.open() }
                        AppButton { objectName: "createPackButton"; text: Style.tr("开始孵化"); primary: true; enabled: !bridge.busy; onClicked: bridge.createPack(fishName.text, folder.text, preset.currentIndex) }
                    }
                    LabelText { text: Style.tr("默认种子不预设形态或童年，经历从出生开始。点击开始孵化后才会创建生命包。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                    AppButton { text: Style.tr("从备份恢复"); enabled: !bridge.busy; onClicked: bridge.showArchiveManager() }
                }
            }
        }
    }
    FolderDialog { id: chooseParent; title: Style.tr("选择文件夹"); onAccepted: folder.text = selectedFolder.toString() }
    FolderDialog { id: openExisting; title: Style.tr("打开现有生命包"); onAccepted: bridge.openPack(selectedFolder.toString()) }
}
