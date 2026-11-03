import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    property int selectedDay: 0
    Component.onCompleted: selectedDay = bridge.diaryDay
    Connections {
        target: bridge
        function onDiaryChanged() {
            if (page.selectedDay !== bridge.diaryDay) {
                page.selectedDay = bridge.diaryDay
                reader.cursorPosition = 0
                Qt.callLater(function() { if (diaryScroll.contentItem) diaryScroll.contentItem.contentY = 0 })
            }
        }
    }
    spacing: 22
    LabelText { text: Style.tr("一起走过的日子"); font.pixelSize: 30 * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
    RowLayout {
        Layout.fillHeight: true; Layout.fillWidth: true; spacing: 24
        ColumnLayout {
            Layout.preferredWidth: 180 * Style.scale
            Layout.maximumWidth: 180 * Style.scale
            Layout.fillWidth: false
            Layout.fillHeight: true
            LabelText { text: Style.tr("选择一天"); color: Style.muted; font.pixelSize: 13 * Style.scale }
            ListView {
                id: dates
                objectName: "dateList"
                Layout.fillWidth: true; Layout.fillHeight: true
                model: daysModel; clip: true; reuseItems: true; spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: SlimBar {}
                delegate: AppButton {
                    required property var entry
                    width: dates.width - 12
                    height: 66 * Style.scale
                    text: entry.date + "\n" + Style.tr("第 {day} 天", {day: entry.day})
                    selected: entry.day === bridge.diaryDay
                    quiet: true
                    onClicked: bridge.selectDay(entry.day)
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.minimumWidth: 300 * Style.scale
            Layout.preferredWidth: 640 * Style.scale
            radius: 24; color: Style.surface
            ColumnLayout {
                anchors.fill: parent; anchors.margins: page.width < 760 ? 18 : 24
                spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    LabelText {
                        objectName: "diaryDateHeading"
                        Layout.fillWidth: true
                        text: bridge.diaryDate
                        font.pixelSize: 14 * Style.scale
                        color: Style.accent
                    }
                    BusyIndicator { visible: bridge.diaryStatus === "loading"; running: visible; Layout.preferredWidth: 22; Layout.preferredHeight: 22 }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Style.line }
                ScrollPane {
                    id: diaryScroll
                    objectName: "diaryScroll"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    visible: bridge.diaryText !== ""
                    contentWidth: availableWidth
                    TextArea {
                        id: reader
                        objectName: "diaryReader"
                        text: bridge.diaryText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.MarkdownText
                        font.pixelSize: 16 * Style.scale
                        color: Style.ink
                        background: Item {}
                        Accessible.name: Style.tr("日记")
                    }
                }
                ScrollPane {
                    id: diaryStatusScroll
                    Layout.fillWidth: true; Layout.fillHeight: true
                    visible: bridge.diaryText === ""
                    ColumnLayout {
                        width: Math.max(0, diaryStatusScroll.availableWidth - 14)
                        spacing: 16
                        LabelText {
                            objectName: "diaryStatus"
                            Layout.fillWidth: true
                            text: bridge.diaryStatus === "error" ? Style.tr("这一天的日记暂时无法读取。") : bridge.diaryStatus === "loading" ? Style.tr("正在打开这一天的日记…") : Style.tr("这一天还没有写下日记。")
                            color: bridge.diaryStatus === "error" ? Style.danger : Style.muted
                        }
                        LabelText { text: bridge.diaryError; visible: bridge.diaryStatus === "error"; Layout.fillWidth: true; color: Style.muted; font.pixelSize: 12 * Style.scale; wrapMode: Text.WrapAnywhere }
                        AppButton { objectName: "retryDiary"; visible: bridge.diaryStatus === "error"; text: Style.tr("重新读取日记"); onClicked: bridge.selectDay(bridge.diaryDay) }
                    }
                }
            }
        }
    }
}
