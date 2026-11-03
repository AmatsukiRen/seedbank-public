import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "disclosureDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(860, parent ? parent.width - 32 : 860)
    height: Math.min(820, parent ? parent.height - 32 : 820)
    modal: true
    closePolicy: Popup.NoAutoClose
    title: Style.tr("分享与私人记忆")
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("分享与私人记忆"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    readonly property var recordsData: bridge.disclosure
    property string editing: ""
    property var selectedSource: ({})
    property var target: ({})
    function refresh(offset, recordOffset) { bridge.loadDisclosure(search.text.trim(), offset || 0, recordOffset || 0, history.checked) }
    function start(action, source, record) {
        editing = action; selectedSource = source || ({}); target = record || ({})
        content.text = source ? source.text : record ? record.text : ""
        reason.text = ""; scopeChoice.currentIndex = 0; groupId.text = ""; personChoice.currentIndex = -1
    }
    function save() {
        var data = {target: target.key || "", expected: target.id || "", reason: reason.text.trim()}
        if (editing !== "revoke") {
            data.scope = scopeChoice.currentIndex === 0 ? "public" : scopeChoice.currentIndex === 1 ? "person:" + (personChoice.currentValue || "") : "qq-group:" + groupId.text.trim()
            data.text = content.text.trim()
            data.source_id = editing === "excerpt" ? selectedSource.id : ""
            data.source_hash = editing === "excerpt" ? selectedSource.hash : ""
        }
        bridge.saveDisclosure(editing, data)
    }
    onOpened: { editing = ""; refresh(0, 0) }
    Connections { target: bridge; function onDisclosureSaved() { dialog.editing = "" } }
    contentItem: ScrollPane {
        id: scroll
        ColumnLayout {
            width: scroll.availableWidth; spacing: 14
            LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
            LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); Layout.fillWidth: true }
            LabelText { text: Style.tr("私人档案默认不进入访客或群聊。只分享你选定的正文；撤回会停止后续使用，无法收回已经发送的内容。"); Layout.fillWidth: true; color: Style.muted }
            ColumnLayout {
                visible: dialog.editing === ""; Layout.fillWidth: true
                AppButton { objectName: "newPublicProfile"; text: Style.tr("填写对外自我介绍"); enabled: !bridge.busy; onClicked: dialog.start("profile", null, null) }
                ToggleRow { id: history; text: Style.tr("包含分享的旧版本"); enabled: !bridge.busy; onToggled: dialog.refresh(0, 0) }
                Repeater {
                    model: dialog.recordsData.pending || []
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: modelData.payload.data.text || modelData.payload.data.reason; Layout.fillWidth: true }
                        AppButton { text: Style.tr("继续保存未完成的分享"); enabled: !bridge.busy; onClicked: bridge.resumeDisclosure(modelData.id) }
                    }
                }
                Repeater {
                    model: dialog.recordsData.records || []
                    Panel {
                        required property var modelData
                        Layout.fillWidth: true
                        caption: Style.tr(modelData.kind === "revoke" ? "已撤回分享" : modelData.available ? "当前可分享" : "当前不可分享")
                        LabelText { text: modelData.text; Layout.fillWidth: true }
                        LabelText { text: modelData.scope + "\n" + modelData.at + "\n" + modelData.reason + (modelData.source_id ? "\n" + modelData.source_id : ""); color: Style.muted; Layout.fillWidth: true }
                        AppButton { visible: modelData.current && modelData.kind !== "revoke"; text: Style.tr("撤回这条分享"); enabled: !bridge.busy; onClicked: dialog.start("revoke", null, modelData) }
                    }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("上一页分享"); enabled: !bridge.busy && dialog.recordsData.record_offset > 0; onClicked: dialog.refresh(dialog.recordsData.offset, Math.max(0, dialog.recordsData.record_offset - 30)) }
                    AppButton { text: Style.tr("下一页分享"); enabled: !bridge.busy && dialog.recordsData.record_offset + 30 < dialog.recordsData.record_total; onClicked: dialog.refresh(dialog.recordsData.offset, dialog.recordsData.record_offset + 30) }
                }
                Field { id: search; objectName: "disclosureSearch"; caption: Style.tr("寻找想分享的原文"); Layout.fillWidth: true; input.onAccepted: dialog.refresh(0, 0) }
                AppButton { text: Style.tr("搜索"); enabled: !bridge.busy; onClicked: dialog.refresh(0, 0) }
                Repeater {
                    model: dialog.recordsData.sources || []
                    Panel {
                        required property var modelData
                        Layout.fillWidth: true; caption: modelData.kind
                        LabelText { text: modelData.text; Layout.fillWidth: true }
                        LabelText { text: modelData.source + "\n" + modelData.id; color: Style.muted; Layout.fillWidth: true }
                        AppButton { text: Style.tr("从这条原文选择摘录"); enabled: !bridge.busy; onClicked: dialog.start("excerpt", modelData, null) }
                    }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("上一页原文"); enabled: !bridge.busy && dialog.recordsData.offset > 0; onClicked: dialog.refresh(Math.max(0, dialog.recordsData.offset - 30), dialog.recordsData.record_offset) }
                    AppButton { text: Style.tr("下一页原文"); enabled: !bridge.busy && dialog.recordsData.offset + 30 < dialog.recordsData.total; onClicked: dialog.refresh(dialog.recordsData.offset + 30, dialog.recordsData.record_offset) }
                }
            }
            ColumnLayout {
                visible: dialog.editing !== ""; enabled: !bridge.busy; Layout.fillWidth: true
                LabelText { visible: dialog.editing === "excerpt"; text: dialog.selectedSource.text || ""; Layout.fillWidth: true }
                LabelText { text: Style.tr(dialog.editing === "excerpt" ? "只保留原文中连续的一段，最多 2000 字。原文变化或退出回忆后，分享会停止生效。" : dialog.editing === "profile" ? "填写允许对外使用的自我介绍，最多 2000 字。它会标为用户提供，不会改写出生档案。" : "撤回只影响后续披露，私人档案和分享历史仍保留。"); Layout.fillWidth: true }
                LabelText { visible: dialog.editing !== "revoke"; text: Style.tr("实际分享的正文"); Layout.fillWidth: true }
                TextArea {
                    id: content; objectName: "disclosureContent"
                    visible: dialog.editing !== "revoke"; Layout.fillWidth: true; Layout.preferredHeight: 180 * Style.scale
                    wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; selectByMouse: true
                    color: Style.ink; font.pixelSize: 15 * Style.scale; padding: 12
                    background: Rectangle { color: Style.soft; radius: 12 }
                }
                Choice { id: scopeChoice; objectName: "disclosureScope"; visible: dialog.editing !== "revoke"; Layout.fillWidth: true; model: [Style.tr("所有外部交流"), Style.tr("指定人物的私人交流"), Style.tr("指定QQ群")] }
                Choice { id: personChoice; visible: dialog.editing !== "revoke" && scopeChoice.currentIndex === 1; Layout.fillWidth: true; model: dialog.recordsData.people || []; textRole: "label"; valueRole: "id" }
                Field { id: groupId; visible: dialog.editing !== "revoke" && scopeChoice.currentIndex === 2; caption: Style.tr("QQ群号"); Layout.fillWidth: true; input.maximumLength: 24 }
                Field { id: reason; objectName: "disclosureReason"; caption: Style.tr("分享或撤回说明"); Layout.fillWidth: true; input.maximumLength: 600 }
            }
        }
    }
    footer: Item {
        implicitHeight: 72 * Style.scale
        RowLayout {
            anchors.fill: parent; anchors.margins: 16
            AppButton { text: Style.tr(dialog.editing ? "取消编辑" : "关闭"); enabled: !bridge.busy; onClicked: { if (dialog.editing) dialog.editing = ""; else dialog.close() } }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "saveDisclosure"; visible: !!dialog.editing; text: Style.tr("保存范围，不发送消息"); primary: true; enabled: !bridge.busy; onClicked: dialog.save() }
        }
    }
}
