import QtQuick
import QtQuick.Controls.Basic

Switch {
    id: control
    implicitHeight: Math.max(48 * Style.scale, contentItem.implicitHeight + 16)
    leftPadding: 0
    rightPadding: 66
    Accessible.name: text
    contentItem: LabelText { text: control.text; verticalAlignment: Text.AlignVCenter }
    indicator: Rectangle {
        width: 48; height: 28; radius: 14
        x: control.width - width
        anchors.verticalCenter: parent.verticalCenter
        color: control.checked ? Style.accent : Style.muted
        border.width: control.visualFocus ? 2 : 0
        border.color: Style.ink
        Rectangle {
            width: 22; height: 22; radius: 11; y: 3
            x: control.checked ? 23 : 3
            color: Style.surface
            Behavior on x { NumberAnimation { duration: Style.duration; easing.type: Easing.OutCubic } }
        }
    }
}
