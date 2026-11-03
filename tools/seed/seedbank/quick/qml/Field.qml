import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string caption: ""
    property string hint: ""
    property bool compact: false
    property bool secret: false
    property alias text: input.text
    property alias input: input
    signal edited(string value)
    spacing: compact ? 4 : 8
    LabelText { visible: !root.compact; text: root.caption; font.weight: Font.Medium; Layout.fillWidth: true }
    TextField {
        id: input
        objectName: "field-" + root.caption
        Layout.fillWidth: true
        implicitHeight: (root.compact ? 38 : 46) * Style.scale
        placeholderText: root.compact ? root.caption : ""
        placeholderTextColor: Style.muted
        font.pixelSize: 15 * Style.scale
        color: Style.ink
        selectByMouse: true
        echoMode: root.secret ? TextInput.Password : TextInput.Normal
        inputMethodHints: root.secret ? Qt.ImhHiddenText | Qt.ImhSensitiveData | Qt.ImhNoPredictiveText : Qt.ImhNone
        selectionColor: Style.soft
        selectedTextColor: Style.ink
        leftPadding: 14
        rightPadding: 14
        Accessible.name: root.caption
        onTextEdited: root.edited(text)
        background: Rectangle {
            radius: 12
            color: Style.field
            border.width: input.activeFocus ? 2 : 0
            border.color: Style.accent
        }
    }
    LabelText { text: root.hint; visible: text !== ""; color: Style.muted; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true }
}
