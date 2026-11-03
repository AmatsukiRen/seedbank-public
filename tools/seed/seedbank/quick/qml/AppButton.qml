import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Button {
    id: control
    property bool primary: false
    property bool selected: false
    property bool danger: false
    property bool quiet: false
    property bool compact: false
    property string symbol: ""
    property real cornerRadius: 14
    implicitHeight: (compact ? 36 : 44) * Style.scale
    implicitWidth: Math.max(88, contentItem.implicitWidth + 28)
    leftPadding: 14
    rightPadding: 14
    topPadding: compact ? 6 : 10
    bottomPadding: compact ? 6 : 10
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: text
    opacity: enabled ? 1 : 0.55
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    contentItem: RowLayout {
        spacing: 8
        Icon {
            visible: control.symbol !== ""
            symbol: control.symbol
            tint: caption.color
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20
        }
        LabelText {
            id: caption
            text: control.text
            color: control.primary ? Style.accentText : control.danger ? Style.danger : control.selected ? Style.accent : Style.ink
            font.pixelSize: 14 * Style.scale
            font.weight: control.primary || control.selected ? Font.DemiBold : Font.Medium
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            Layout.fillWidth: true
        }
    }
    background: Rectangle {
        radius: control.cornerRadius
        color: control.primary ? (control.down ? Style.accentPressed : control.hovered ? Style.accentHover : Style.accent)
             : control.danger ? (control.down ? Style.dangerPressed : control.hovered ? Style.dangerHover : Style.dangerSurface)
             : control.down ? Style.buttonPressed
             : control.hovered ? Style.buttonHover
             : control.selected ? Style.buttonSelected
             : control.quiet ? "transparent" : Style.button
        border.width: control.visualFocus || control.selected ? 2 : control.quiet && !control.danger && !control.primary ? 0 : 1
        border.color: control.visualFocus ? Style.accent : control.danger ? Style.dangerBorder : control.primary || control.selected ? Style.accent : Style.buttonBorder
        Behavior on color { ColorAnimation { duration: Style.duration } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -3
            visible: control.visualFocus
            color: "transparent"; radius: control.cornerRadius + 3
            border.width: 2; border.color: Style.accent
        }
    }
}
