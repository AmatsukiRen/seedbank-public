import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    default property alias contents: body.data
    property int inset: 24
    property string caption: ""
    property string detail: ""
    implicitHeight: body.implicitHeight + inset * 2
    radius: 22
    color: Style.surface
    ColumnLayout {
        id: body
        x: root.inset; y: root.inset
        width: root.width - root.inset * 2
        spacing: 14
        LabelText { visible: root.caption !== ""; text: root.caption; font.pixelSize: 18 * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
        LabelText { visible: root.detail !== ""; text: root.detail; color: Style.muted; font.pixelSize: 13 * Style.scale; Layout.fillWidth: true }
    }
}
