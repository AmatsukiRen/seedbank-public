import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "reminderDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(620, parent ? parent.width - 32 : 620)
    height: Math.min(680, parent ? parent.height - 32 : 680)
    modal: true
    closePolicy: Popup.NoAutoClose
    property string editAction: "add"
    property string reminderId: ""
    property string expected: ""
    property var viewed: chooser.currentIndex >= 0 && chooser.currentIndex < bridge.reminderRows.length ? bridge.reminderRows[chooser.currentIndex] : ({})
    onOpened: { if (!dueOn.text) dueOn.text = bridge.nextDate; bridge.loadReminders() }
    function fresh() { editAction = "add"; reminderId = ""; expected = ""; reminderText.text = ""; dueOn.text = bridge.nextDate; reason.text = "" }
    function restore(data) { fresh(); reminderText.text = data.text; dueOn.text = data.due_on }
    function selectReminder(row, action) {
        editAction = action; reminderId = row.id; expected = row.expected
        reminderText.text = row.text; dueOn.text = row.due_on || ""; reason.text = ""
    }
    function restoreRequest(row) {
        if (row.payload.kind === "reminder_edit") { restore(row.payload.data); return }
        const data = row.payload.data
        editAction = row.payload.action; reminderId = data.reminder_id; expected = data.expected
        reminderText.text = data.text || ""; dueOn.text = data.due_on || ""; reason.text = data.reason
    }
    function save() {
        if (editAction === "add") { bridge.remindOn(reminderText.text, dueOn.text); return }
        let data = {reminder_id: reminderId, expected: expected, reason: reason.text}
        if (editAction === "revise") { data.text = reminderText.text; data.due_on = dueOn.text }
        bridge.changeReminder(editAction, data)
    }
    function deadline(row) { return row.due_on || Style.tr("旧日页第 {number} 页", {number: row.due_day}) }
    Connections { target: bridge; function onReminderSaved() { dialog.fresh(); dueOn.text = ""; dialog.close() } }
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("提醒与日期"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        LabelText { text: Style.tr("按日历日期提醒。程序运行时检查，离线到期后恢复时补充说明；写入本地对话不等于已送达其他设备。"); Layout.fillWidth: true; color: Style.muted }
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        ScrollView {
            id: scroll
            Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
            ColumnLayout {
                width: scroll.availableWidth; spacing: 16
                LabelText { text: Style.tr("已有提醒与历史"); Layout.fillWidth: true; font.weight: Font.DemiBold }
                Choice {
                    id: chooser; objectName: "existingReminderChoice"; Layout.fillWidth: true
                    model: bridge.reminderRows; textRole: "label"; currentIndex: -1; enabled: !bridge.busy
                    displayText: currentIndex < 0 ? Style.tr("选择一条提醒") : currentText
                    font.pixelSize: 14 * Style.scale
                }
                LabelText { visible: Boolean(dialog.viewed.id); text: dialog.viewed.id ? dialog.deadline(dialog.viewed) + " · " + Style.tr(dialog.viewed.status) : ""; Layout.fillWidth: true }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("修改内容或日期"); enabled: !bridge.busy && dialog.viewed.status === "pending"; onClicked: dialog.selectReminder(dialog.viewed, "revise") }
                    AppButton { text: Style.tr("取消这条提醒"); enabled: !bridge.busy && dialog.viewed.status === "pending"; onClicked: dialog.selectReminder(dialog.viewed, "cancel") }
                    AppButton { text: Style.tr("刷新提醒列表"); enabled: !bridge.busy; onClicked: bridge.loadReminders() }
                }
                LabelText { visible: Boolean(dialog.viewed.id); text: Style.tr("取消不删除历史；已经提醒的记录保留。旧日页提醒改期时，请明确填写日历日期。"); Layout.fillWidth: true; color: Style.muted }
                Repeater {
                    model: (dialog.viewed.history || []).slice(-10).reverse()
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: modelData.on + " · " + Style.tr(modelData.action === "cancel" ? "取消这条提醒" : "修改内容或日期") + " · " + modelData.reason; Layout.fillWidth: true }
                        LabelText { text: modelData.before.text + " · " + dialog.deadline(modelData.before) + " → " + modelData.after.text + " · " + dialog.deadline(modelData.after) + " · " + Style.tr(modelData.after.status); Layout.fillWidth: true; color: Style.muted }
                    }
                }
                LabelText { visible: (dialog.viewed.history || []).length > 10; text: Style.tr("这里显示最近 10 次修改；完整历史仍保存在生命包中。"); Layout.fillWidth: true; color: Style.muted }
                RowLayout {
                    Layout.fillWidth: true
                    LabelText { text: dialog.editAction === "add" ? Style.tr("新增提醒") : dialog.reminderId + " · " + Style.tr(dialog.editAction === "cancel" ? "取消这条提醒" : "修改内容或日期"); Layout.fillWidth: true; font.weight: Font.DemiBold }
                    AppButton { text: Style.tr("新增提醒"); enabled: !bridge.busy; visible: dialog.editAction !== "add"; onClicked: dialog.fresh() }
                }
                Field { id: reminderText; objectName: "calendarReminderText"; visible: dialog.editAction !== "cancel"; caption: Style.tr("希望她记住什么？"); Layout.fillWidth: true; input.maximumLength: 120; enabled: !bridge.busy }
                Field { id: dueOn; objectName: "calendarReminderDate"; visible: dialog.editAction !== "cancel"; caption: Style.tr("日历日期（YYYY-MM-DD）"); Layout.fillWidth: true; input.maximumLength: 10; enabled: !bridge.busy }
                Field { id: reason; objectName: "reminderChangeReason"; visible: dialog.editAction !== "add"; caption: Style.tr("修改或取消的原因"); Layout.fillWidth: true; input.maximumLength: 300; enabled: !bridge.busy }
                LabelText { visible: dialog.editAction === "cancel"; text: Style.tr("保存后停止这条提醒，原内容与取消原因会保留。"); Layout.fillWidth: true; color: Style.muted }
                LabelText { visible: bridge.pendingReminders.length > 0; text: Style.tr("尚未完成的提醒操作"); Layout.fillWidth: true; color: Style.muted }
                Repeater {
                    model: bridge.pendingReminders
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: (modelData.payload.data.reminder_id || "") + " · " + (modelData.payload.data.due_on || "") + " · " + (modelData.payload.data.text || modelData.payload.data.reason || ""); Layout.fillWidth: true }
                        Flow {
                            Layout.fillWidth: true; spacing: 8
                            AppButton { text: Style.tr("恢复到编辑框"); enabled: !bridge.busy; onClicked: dialog.restoreRequest(modelData) }
                            AppButton { text: Style.tr("停止这条未完成操作"); enabled: !bridge.busy; onClicked: bridge.cancelPendingReminder(modelData.id) }
                        }
                    }
                }
            }
        }
    }
    footer: Item {
        implicitHeight: 72 * Style.scale
        RowLayout {
            anchors.fill: parent; anchors.margins: 16
            AppButton { text: Style.tr("关闭"); enabled: !bridge.busy; onClicked: dialog.close() }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "saveCalendarReminder"; text: Style.tr("保存"); primary: true; enabled: !bridge.busy && (dialog.editAction === "cancel" || (reminderText.text.trim().length > 0 && dueOn.text.length > 0)) && (dialog.editAction === "add" || reason.text.trim().length > 0); onClicked: dialog.save() }
        }
    }
}
