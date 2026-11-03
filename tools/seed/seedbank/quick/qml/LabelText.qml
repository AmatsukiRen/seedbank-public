import QtQuick

Text {
    readonly property bool eliding: elide !== Text.ElideNone
    color: Style.ink
    font.pixelSize: 15 * Style.scale
    wrapMode: Text.Wrap
    textFormat: Text.PlainText
    renderType: Text.QtRendering
    lineHeight: 1.25
}
