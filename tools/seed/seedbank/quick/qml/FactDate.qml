import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "factDateDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(800, parent ? parent.width - 32 : 800)
    height: Math.min(780, parent ? parent.height - 32 : 780)
    modal: true
    closePolicy: Popup.NoAutoClose
    readonly property var details: bridge.factDate
    property var restored: ({})
    property string expected: ""
    property string targetHash: ""
    function openFor(identifier) {
        restored = ({}); date.text = ""; reason.text = ""; expected = ""; targetHash = ""
        if (bridge.loadFactDate(identifier)) open()
    }
    function restore(data) {
        restored = data; expected = data.expected; targetHash = data.target_hash
        date.text = data.date || ""; reason.text = data.reason || ""
    }
    function resume(data) {
        openFor(data.target)
        restored = data
    }
    function loaded() {
        if (restored.target === details.target) restore(restored)
        else {
            expected = details.expected || ""; targetHash = details.target_hash || ""
            date.text = details.date || ""; reason.text = ""
        }
    }
    Connections {
        target: bridge
        function onFactDateLoaded() { dialog.loaded() }
        function onFactDateSaved() { dialog.restored = ({}); dialog.loaded() }
    }
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("日期说明与修订"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        spacing: 10
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); color: Style.muted; Layout.fillWidth: true }
        LabelText { text: (dialog.details.label || "") + " · " + (dialog.details.aspect || ""); font.weight: Font.DemiBold; Layout.fillWidth: true }
        LabelText { text: Style.tr("只补充或修正这条记录的日期，不改变说法内容或已采用的选择。原文保留；引用旧日期的生成内容可能退出普通回忆。"); color: Style.muted; Layout.fillWidth: true }
        ScrollView {
            id: scroll; clip: true; contentWidth: availableWidth; Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                width: scroll.availableWidth; spacing: 12
                LabelText { text: (dialog.details.original || {}).quote || (dialog.details.original || {}).reason || ""; Layout.fillWidth: true }
                LabelText { text: Style.tr("最初记录的日期") + "：" + (dialog.details.original_date || Style.tr("未知")); color: Style.muted; Layout.fillWidth: true }
                LabelText { visible: dialog.details.date_state === "unavailable"; text: Style.tr("最新日期依据不可用，未恢复旧日期。"); color: Style.muted; Layout.fillWidth: true }
                LabelText { visible: !!dialog.details.target && !dialog.details.editable; text: Style.tr("这条说法或变化已记错、放下或失去依据，只能查看历史。"); color: Style.muted; Layout.fillWidth: true }
                Repeater {
                    model: dialog.details.pending || []
                    AppButton { required property var modelData; text: Style.tr("恢复未完成的日期修订"); enabled: !bridge.busy; onClicked: dialog.restore(modelData.payload.data) }
                }
                Field { id: date; objectName: "amendFactDate"; caption: Style.tr(dialog.details.kind === "resolve" ? "变化日期（YYYY-MM-DD，留空表示未知）" : "生效起日（YYYY-MM-DD，留空表示未知）"); Layout.fillWidth: true; enabled: !bridge.busy && !!dialog.details.editable }
                Field { id: reason; objectName: "amendFactDateReason"; caption: Style.tr("日期修订理由（最多 500 字）"); Layout.fillWidth: true; enabled: !bridge.busy && !!dialog.details.editable }
                AppButton { text: Style.tr("重新读取当前日期版本"); enabled: !bridge.busy && !!dialog.details.target; onClicked: dialog.openFor(dialog.details.target) }
                LabelText { text: Style.tr("相关起日与变化记录"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                Repeater {
                    model: dialog.details.related || []
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: modelData.text; Layout.fillWidth: true }
                        AppButton { text: Style.tr(modelData.kind === "claim" ? "查看生效起日" : "查看变化日期"); enabled: !bridge.busy && modelData.id !== dialog.details.target; onClicked: dialog.openFor(modelData.id) }
                    }
                }
                LabelText { text: Style.tr("日期修改历史"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                Repeater {
                    model: (dialog.details.versions || []).slice().reverse()
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: (modelData.date || Style.tr("未知")) + " · " + modelData.at; Layout.fillWidth: true }
                        LabelText { text: modelData.reason; Layout.fillWidth: true }
                        LabelText { text: modelData.evidence.map(function(r) { return r.source }).join("\n"); color: Style.muted; Layout.fillWidth: true }
                    }
                }
            }
        }
    }
    footer: Item {
        implicitHeight: 68 * Style.scale
        RowLayout {
            anchors.fill: parent; anchors.margins: 12
            AppButton { text: Style.tr("关闭"); enabled: !bridge.busy; onClicked: dialog.close() }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "saveFactDate"; text: Style.tr("保存日期修订"); primary: true; enabled: !bridge.busy && !!dialog.details.editable && reason.text.trim().length > 0 && reason.text.length <= 500
                onClicked: bridge.saveFactDate({target: dialog.details.target, target_hash: dialog.targetHash, expected: dialog.expected, date: date.text.trim(), reason: reason.text.trim()}) }
        }
    }
}
