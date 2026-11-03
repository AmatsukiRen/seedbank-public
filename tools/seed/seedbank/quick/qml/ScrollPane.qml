import QtQuick
import QtQuick.Controls.Basic

ScrollView {
    id: control
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: SlimBar {
        parent: control
        x: control.width - width
        y: control.topPadding
        height: control.availableHeight
    }
}
