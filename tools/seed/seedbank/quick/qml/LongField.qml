import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string caption: ""
    property alias text: input.text
    property alias input: input
    spacing: 8
    LabelText { text: root.caption; Layout.fillWidth: true; font.weight: Font.Medium }
    TextArea {
        id: input
        Layout.fillWidth: true
        implicitHeight: Math.max(100 * Style.scale, contentHeight + topPadding + bottomPadding)
        wrapMode: TextEdit.Wrap
        textFormat: TextEdit.PlainText
        selectByMouse: true
        font.pixelSize: 15 * Style.scale
        color: Style.ink
        selectionColor: Style.soft
        selectedTextColor: Style.ink
        padding: 14
        Accessible.name: root.caption
        background: Rectangle { color: Style.field; radius: 12; border.width: input.activeFocus ? 2 : 0; border.color: Style.accent }
    }
}
