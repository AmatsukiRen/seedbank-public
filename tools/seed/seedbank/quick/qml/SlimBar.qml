import QtQuick
import QtQuick.Controls.Basic

ScrollBar {
    id: control
    policy: ScrollBar.AsNeeded
    minimumSize: 0.07
    implicitWidth: 12
    padding: hovered || pressed ? 2.5 : 4
    contentItem: Rectangle {
        implicitWidth: control.hovered || control.pressed ? 7 : 4
        radius: width / 2
        color: Style.muted
        opacity: control.policy === ScrollBar.AlwaysOff || (control.policy === ScrollBar.AsNeeded && control.size >= 1)
                 ? 0 : control.active || control.hovered || control.pressed ? 0.75 : 0.25
        Behavior on opacity { NumberAnimation { duration: Style.duration } }
    }
    background: Item {}
}
