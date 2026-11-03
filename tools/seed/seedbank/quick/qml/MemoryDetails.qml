import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "memoryDetails"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(760, parent ? parent.width - 40 : 760)
    height: Math.min(740, parent ? parent.height - 40 : 740)
    modal: true
    closePolicy: Popup.NoAutoClose
    title: Style.tr("记忆的来处与变化")
    property int section: 0
    property bool editing: false
    property string changeType: "correction"
    readonly property var detail: bridge.memoryDetail
    readonly property var selected: detail.selected || ({})
    readonly property var current: detail.current || ({})
    readonly property var pending: detail.pending || []
    function startEdit(saved) {
        changeType = saved ? saved.change_type : "correction"
        content.text = saved ? saved.text : (selected.text || "")
        reason.text = saved ? saved.reason : ""
        effective.text = saved ? saved.effective_on : ""
        editing = true
        content.forceActiveFocus()
    }
    onOpened: { section = 0; editing = false }
    Connections {
        target: bridge
        function onMemorySaved(identifier) { dialog.editing = false; dialog.section = 0 }
    }
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: dialog.title; padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        spacing: 12
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); color: Style.muted; Layout.fillWidth: true }
        RowLayout {
            visible: !dialog.editing
            AppButton { text: Style.tr("内容与来源"); selected: dialog.section === 0; onClicked: dialog.section = 0 }
            AppButton { text: Style.tr("修改历史"); selected: dialog.section === 1; onClicked: dialog.section = 1 }
            AppButton { text: Style.tr("刷新版本"); symbol: "refresh"; enabled: !bridge.busy && !!dialog.selected.id; onClicked: bridge.loadMemory(dialog.selected.id) }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: dialog.editing ? 2 : dialog.section
            ScrollView {
                id: information
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: information.availableWidth
                    spacing: 14
                    LabelText { text: dialog.selected.text || ""; font.pixelSize: 18 * Style.scale; Layout.fillWidth: true }
                    LabelText { text: Style.tr(dialog.selected.provenance || "历史记录，来源待确认"); color: Style.accent; Layout.fillWidth: true }
                    LabelText { text: Style.tr("记录时间") + "：" + (dialog.selected.at || Style.tr("未记录")); color: Style.muted; Layout.fillWidth: true }
                    LabelText { text: Style.tr("来源") + "：" + (dialog.selected.source || Style.tr("未记录")); color: Style.muted; Layout.fillWidth: true }
                    LabelText {
                        visible: !!dialog.selected.change_type
                        text: Style.tr(dialog.selected.change_type === "change" ? "后来改变" : "原来记错")
                              + (dialog.selected.change_type === "change" ? " · " + (dialog.selected.effective_on || Style.tr("变化日期未注明")) : "")
                        color: Style.accent; Layout.fillWidth: true
                    }
                    LabelText { visible: !!dialog.selected.reason; text: Style.tr("修订理由") + "：" + (dialog.selected.reason || ""); Layout.fillWidth: true }
                    LabelText { visible: dialog.selected.recallable === false; text: Style.tr("此版本仅供查看，不进入当前回忆。"); color: Style.muted; Layout.fillWidth: true }
                    LabelText { visible: !!dialog.detail.conflict; text: Style.tr("这条记忆存在多个当前版本，需要核对来源。"); color: Style.danger; Layout.fillWidth: true }
                    AppButton {
                        visible: !!dialog.current.id && dialog.current.id !== dialog.selected.id
                        text: Style.tr("查看当前版本"); enabled: !bridge.busy
                        onClicked: bridge.loadMemory(dialog.current.id)
                    }
                    AppButton {
                        visible: dialog.pending.length > 0 && !!dialog.selected.can_revise
                        text: Style.tr("恢复未完成的修订"); enabled: !bridge.busy
                        onClicked: dialog.startEdit(dialog.pending[dialog.pending.length - 1].payload)
                    }
                    LabelText { text: Style.tr("引用的记录"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                    LabelText { visible: (dialog.detail.evidence || []).length === 0; text: Style.tr("这条旧记忆没有逐条引用，来源路径仍保留。"); color: Style.muted; Layout.fillWidth: true }
                    Repeater {
                        model: dialog.detail.evidence || []
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true; spacing: 6
                            LabelText { text: Style.tr(modelData.provenance) + " · " + (modelData.at || Style.tr("未记录")); color: Style.muted; Layout.fillWidth: true }
                            LabelText { text: modelData.missing ? Style.tr("引用的原始记录暂不可用。") : modelData.text; Layout.fillWidth: true }
                            LabelText { text: modelData.source || modelData.id; color: Style.muted; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true }
                            Rectangle { Layout.fillWidth: true; height: 1; color: Style.line }
                        }
                    }
                }
            }
            ListView {
                id: versions
                objectName: "memoryVersions"
                clip: true; reuseItems: true; spacing: 12
                model: dialog.detail.versions || []
                ScrollBar.vertical: SlimBar {}
                delegate: Rectangle {
                    required property var modelData
                    width: versions.width - 14
                    height: versionBody.implicitHeight + 28
                    color: Style.field; radius: 12
                    ColumnLayout {
                        id: versionBody
                        x: 14; y: 14; width: parent.width - 28; spacing: 8
                        LabelText {
                            text: (modelData.at || Style.tr("未记录")) + " · "
                                  + Style.tr(modelData.forgotten ? "已放下" : modelData.recallable ? "当前版本" : "仅存档")
                            color: Style.accent; Layout.fillWidth: true
                        }
                        LabelText { text: modelData.text; Layout.fillWidth: true }
                        LabelText { visible: !!modelData.reason; text: Style.tr("修订理由") + "：" + (modelData.reason || ""); Layout.fillWidth: true }
                        LabelText { text: Style.tr(modelData.provenance); color: Style.muted; Layout.fillWidth: true }
                        LabelText {
                            visible: !!modelData.change_type
                            text: Style.tr(modelData.change_type === "change" ? "后来改变" : "原来记错")
                                  + (modelData.change_type === "change" ? " · " + (modelData.effective_on || Style.tr("变化日期未注明")) : "")
                            color: Style.muted; Layout.fillWidth: true
                        }
                        AppButton { text: Style.tr("查看来源"); symbol: "book"; enabled: !bridge.busy; onClicked: { dialog.section = 0; bridge.loadMemory(modelData.id) } }
                    }
                }
            }
            ScrollView {
                id: editor
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: editor.availableWidth
                    spacing: 12
                    LabelText { text: Style.tr("这次修改会标为用户提供，保留原版本和理由。"); color: Style.muted; Layout.fillWidth: true }
                    RowLayout {
                        AppButton { objectName: "revisionCorrection"; text: Style.tr("原来记错"); selected: dialog.changeType === "correction"; enabled: !bridge.busy; onClicked: dialog.changeType = "correction" }
                        AppButton { objectName: "revisionChange"; text: Style.tr("后来改变"); selected: dialog.changeType === "change"; enabled: !bridge.busy; onClicked: dialog.changeType = "change" }
                    }
                    LabelText { text: Style.tr(dialog.changeType === "change" ? "过去的说法当时成立，后来发生了变化。" : "原先的说法有误，需要纠正。"); color: Style.muted; Layout.fillWidth: true }
                    LabelText { text: Style.tr("修订内容（最多 1000 字）"); Layout.fillWidth: true }
                    TextArea {
                        id: content
                        objectName: "revisionContent"
                        Layout.fillWidth: true; Layout.preferredHeight: Math.max(100, implicitHeight)
                        enabled: !bridge.busy; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                        font.pixelSize: 15 * Style.scale; color: Style.ink
                        selectByMouse: true; padding: 12
                        Accessible.name: Style.tr("修订内容（最多 1000 字）")
                        background: Rectangle { radius: 12; color: Style.field; border.width: content.activeFocus ? 2 : 0; border.color: Style.accent }
                    }
                    LabelText { text: Style.tr("修订理由（最多 500 字）"); Layout.fillWidth: true }
                    TextArea {
                        id: reason
                        objectName: "revisionReason"
                        Layout.fillWidth: true; Layout.preferredHeight: Math.max(80, implicitHeight)
                        enabled: !bridge.busy; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                        font.pixelSize: 15 * Style.scale; color: Style.ink
                        selectByMouse: true; padding: 12
                        Accessible.name: Style.tr("修订理由（最多 500 字）")
                        background: Rectangle { radius: 12; color: Style.field; border.width: reason.activeFocus ? 2 : 0; border.color: Style.accent }
                    }
                    Field {
                        id: effective
                        objectName: "revisionEffectiveDate"
                        visible: dialog.changeType === "change"
                        enabled: !bridge.busy; Layout.fillWidth: true
                        caption: Style.tr("变化日期（YYYY-MM-DD，可留空）")
                        hint: Style.tr("不知道日期可以留空，不会把保存时间当作变化发生时间。")
                    }
                    LabelText { visible: content.text.length > 1000 || reason.text.length > 500; text: Style.tr("修订内容最多 1000 字，理由最多 500 字。"); color: Style.danger; Layout.fillWidth: true }
                }
            }
        }
    }
    footer: Item {
        implicitHeight: 72 * Style.scale
        RowLayout {
            anchors.fill: parent; anchors.margins: 16
            AppButton {
                text: Style.tr(dialog.editing ? "取消编辑" : "关闭"); enabled: !bridge.busy
                onClicked: { if (dialog.editing) dialog.editing = false; else dialog.close() }
            }
            Item { Layout.fillWidth: true }
            AppButton {
                objectName: "editMemory"
                visible: !dialog.editing && !!dialog.selected.can_revise && !dialog.detail.conflict
                text: Style.tr("修改这条记忆"); primary: true; enabled: !bridge.busy
                onClicked: dialog.startEdit(null)
            }
            AppButton {
                objectName: "saveMemoryRevision"
                visible: dialog.editing
                text: Style.tr("保存修订"); primary: true
                enabled: !bridge.busy && content.text.trim().length > 0 && reason.text.trim().length > 0
                         && content.text.length <= 1000 && reason.text.length <= 500
                onClicked: bridge.saveMemoryRevision(dialog.selected.id, content.text, reason.text, dialog.changeType,
                                                      dialog.changeType === "change" ? effective.text : "")
            }
        }
    }
}
