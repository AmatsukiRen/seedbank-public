import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "lifecycleDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(680, parent ? parent.width - 32 : 680)
    height: Math.min(700, parent ? parent.height - 32 : 700)
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    title: Style.tr("休眠与恢复")
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: Item {
        implicitHeight: headerRow.implicitHeight + 32
        RowLayout {
            id: headerRow
            anchors.fill: parent; anchors.margins: 16
            spacing: 12
            LabelText { text: dialog.title; font.pixelSize: 22 * Style.scale; Layout.fillWidth: true }
            AppButton {
                objectName: "closeLifecycleHeader"
                text: Style.tr("关闭")
                onClicked: dialog.reject()
            }
        }
    }
    property int expected: 0
    onOpened: { note.text = ""; confirmation.checked = false; bridge.loadLifecycle() }
    Connections {
        target: bridge
        function onStateChanged() {
            if (dialog.expected !== bridge.lifecycle.revision) {
                dialog.expected = bridge.lifecycle.revision
                confirmation.checked = false
                note.text = ""
            }
        }
    }
    contentItem: ScrollPane {
        id: scroll
        ColumnLayout {
            width: scroll.availableWidth; spacing: 14
            LabelText { text: bridge.notice; color: bridge.error ? Style.danger : Style.muted; Layout.fillWidth: true }
            LabelText { text: Style.tr(bridge.lifeActive ? "正在继续生活" : bridge.lifecycle.state === "dormant" ? "已休眠，档案完整保留。" : "生命状态记录无法读取，自动活动已停止；原文件已保留。"); Layout.fillWidth: true }
            LabelText { text: Style.tr("休眠保留人生档案，停止翻页、主动表达、收件箱处理和对话回复。重新打开程序不会恢复；恢复后从实际日期继续，不补写休眠期间的日记。"); Layout.fillWidth: true; color: Style.muted }
            LabelText { text: Style.tr("请记录个体明确选择告别或恢复的原话与背景。这条确认由用户保存，不会被当成模型自主作出的决定。"); Layout.fillWidth: true; color: Style.muted }
            LongField { id: note; objectName: "lifecycleNote"; Layout.fillWidth: true; caption: Style.tr("选择说明"); enabled: !bridge.busy && bridge.lifecycle.state !== "unavailable" }
            ToggleRow { id: confirmation; objectName: "lifecycleConfirmation"; text: Style.tr("我确认这是一次明确的选择"); enabled: !bridge.busy && bridge.lifecycle.state !== "unavailable" }
            AppButton {
                objectName: "changeLifecycle"
                text: Style.tr(bridge.lifeActive ? "保留档案并休眠" : "明确恢复")
                enabled: !bridge.busy && bridge.lifecycle.state !== "unavailable" && confirmation.checked && note.text.trim() !== "" && bridge.textLength(note.text) <= 2000
                onClicked: { bridge.changeLifecycle(bridge.lifeActive ? "pause" : "resume", note.text, dialog.expected); confirmation.checked = false }
            }
            LabelText { text: Style.tr("选择记录（由用户确认）"); Layout.fillWidth: true }
            Repeater {
                model: (bridge.lifecycle.history || []).slice().reverse()
                LabelText {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData.at + " · " + Style.tr(modelData.to === "dormant" ? "保留档案并休眠" : "明确恢复") + "\n" + modelData.note
                }
            }
        }
    }
    // Dialog forwards its own standardButtons to a DialogButtonBox footer.
    // A footer-only Close setting gets reset to NoButton. Use explicit controls,
    // outside the scroll area, and keep dismissal available during status reads.
    footer: Item {
        implicitHeight: footerRow.implicitHeight + 32
        RowLayout {
            id: footerRow
            anchors.fill: parent; anchors.margins: 16
            Item { Layout.fillWidth: true }
            AppButton {
                objectName: "closeLifecycleFooter"
                text: Style.tr("关闭")
                onClicked: dialog.reject()
            }
        }
    }
}
