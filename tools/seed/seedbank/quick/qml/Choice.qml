import QtQuick
import QtQuick.Controls.Basic

ComboBox {
    id: control
    implicitHeight: 46 * Style.scale
    wheelEnabled: false
    font.pixelSize: 15 * Style.scale
    leftPadding: 14
    rightPadding: 38
    contentItem: LabelText {
        text: control.displayText
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        wrapMode: Text.NoWrap
    }
    background: Rectangle {
        color: Style.field
        radius: 12
        border.color: Style.accent
        border.width: control.visualFocus ? 2 : 0
    }
    indicator: Icon { symbol: "chevron"; x: control.width - width - 12; anchors.verticalCenter: parent.verticalCenter }
    delegate: ItemDelegate {
        required property int index
        width: control.width
        height: 46 * Style.scale
        text: control.textAt(index)
        highlighted: control.highlightedIndex === index
        contentItem: LabelText { text: parent.text; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: parent.highlighted ? Style.soft : Style.surface; radius: 8 }
    }
    popup: Popup {
        y: control.height + 6
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 300)
        padding: 6
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
        background: Rectangle { color: Style.surface; radius: 14; border.color: Style.line }
    }
}
