import QtQuick

Item {
    id: root
    property string symbol: "home"
    property color tint: Style.ink
    implicitWidth: 22
    implicitHeight: 22
    readonly property var paths: ({
        home: "M3 11 L12 3 L21 11 M6 10 L6 21 L18 21 L18 10 M10 21 L10 15 L14 15 L14 21",
        book: "M12 5 L7 3 L3 4 L3 20 L7 19 L12 21 L17 19 L21 20 L21 4 L17 3 L12 5 L12 21",
        heart: "M12 21 C8 17 2 13 3 8 C4 2 9 2 12 7 C15 2 20 2 21 8 C22 13 16 17 12 21 Z",
        leaf: "M5 20 C2 8 12 3 21 3 C21 15 17 23 5 20 Z M4 22 L15 10",
        settings: "M3 5 L21 5 M3 12 L21 12 M3 19 L21 19 M8 3 L8 7 M16 10 L16 14 M10 17 L10 21",
        send: "M3 3 L22 12 L3 21 L6 12 Z M6 12 L22 12",
        photo: "M3 5 L21 5 L21 20 L3 20 Z M3 18 L8 12 L13 17 L17 13 L21 17 M15 9 L16 9",
        search: "M17 10 A7 7 0 1 1 3 10 A7 7 0 1 1 17 10 M15 15 L22 22",
        chevron: "M6 9 L12 15 L18 9",
        plus: "M4 12 L20 12 M12 4 L12 20",
        edit: "M13 5 L19 11 M4 20 L5 14 L16 3 L22 9 L11 20 Z M4 20 L11 20",
        archive: "M3 4 L21 4 L21 9 L3 9 Z M5 9 L5 21 L19 21 L19 9 M10 13 L14 13",
        refresh: "M20 10 A8 8 0 1 0 19 17 M20 4 L20 10 L14 10"
    })
    Image {
        anchors.fill: parent
        sourceSize: Qt.size(Math.ceil(root.width * Screen.devicePixelRatio), Math.ceil(root.height * Screen.devicePixelRatio))
        source: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="' + (root.paths[root.symbol] || root.paths.plus) + '" fill="none" stroke="' + root.tint + '" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        smooth: true
        cache: true
    }
}
