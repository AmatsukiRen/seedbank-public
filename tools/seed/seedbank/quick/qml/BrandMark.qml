import QtQuick

// Image exposes a natural (read-only) implicit size. Keep the layout hint on
// a plain Item so the brand asset cannot make Main.qml fail to instantiate.
Item {
    id: root
    implicitWidth: 48 * Style.scale
    implicitHeight: 48 * Style.scale
    Accessible.ignored: true

    Image {
        anchors.fill: parent
        source: "brand/seedbank-logo.png"
        sourceSize: Qt.size(Math.ceil(root.width * Screen.devicePixelRatio), Math.ceil(root.height * Screen.devicePixelRatio))
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        Accessible.ignored: true
    }
}
