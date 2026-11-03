import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: window
    objectName: "seedbankWindow"
    width: 1280; height: 840
    minimumWidth: 640; minimumHeight: 420
    visible: false
    color: Style.background
    title: "SeedBank " + Qt.application.version
    flags: Qt.Window | (bridge.preferences.always_on_top ? Qt.WindowStaysOnTopHint : 0)
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 15 * Style.scale
    palette.window: Style.surface
    palette.windowText: Style.ink
    palette.base: Style.field
    palette.text: Style.ink
    palette.button: Style.button
    palette.buttonText: Style.ink
    palette.highlight: Style.accent
    palette.highlightedText: Style.accentText
    property int page: 0
    property bool mayClose: false
    readonly property bool compact: width < 1120 * Style.scale
    readonly property bool bottomNavigation: width < 760 * Style.scale || height < 580 * Style.scale
    readonly property bool shortWindow: height < 640 * Style.scale
    readonly property real pageMargin: bottomNavigation ? 10 : compact ? 16 : 24
    readonly property real pageGap: compact ? 16 : 26
    readonly property real navigationWidth: compact ? 76 * Style.scale : 158
    // Derive the avatar's preferred width from the window, not its own layout's
    // assigned width (which feeds back into that layout's implicit size).
    readonly property real contentWidth: Math.max(0, width - 2 * pageMargin
        - (bridge.ready && !bottomNavigation ? navigationWidth + pageGap : 0))
    ArchiveDialog { id: archiveDialog }
    function navigate(destination) {
        if (destination >= 0 && destination < 5) { page = destination; navigation.forceActiveFocus() }
    }
    onClosing: function(event) {
        if (!mayClose) {
            event.accepted = false
            if (bridge.dirty && !bridge.closing) discard.open()
            else bridge.requestClose()
        }
    }
    Connections {
        target: bridge
        function onArchiveRequested() { archiveDialog.open() }
        function onCloseReady() { bridge.saveGeometry(window.width, window.height, window.x, window.y); window.mayClose = true; window.close() }
    }
    GridLayout {
        anchors.fill: parent
        anchors.margins: window.pageMargin
        columns: window.bottomNavigation || !bridge.ready ? 1 : 2
        rowSpacing: 8
        columnSpacing: window.pageGap
        Rectangle {
            id: navigation
            objectName: "navigation"
            visible: bridge.ready
            Layout.row: window.bottomNavigation ? 1 : 0
            Layout.column: 0
            Layout.preferredWidth: window.bottomNavigation ? -1 : window.navigationWidth
            Layout.preferredHeight: window.bottomNavigation ? 62 * Style.scale : -1
            Layout.minimumWidth: 0
            Layout.fillWidth: window.bottomNavigation
            Layout.fillHeight: !window.bottomNavigation
            radius: 22
            color: Style.surface
            GridLayout {
                anchors.fill: parent
                anchors.margins: window.bottomNavigation ? 5 : 10
                columns: window.bottomNavigation ? 5 : 1
                rowSpacing: 8; columnSpacing: 4
                ColumnLayout {
                    visible: !window.bottomNavigation
                    Layout.fillWidth: true; Layout.topMargin: 8; Layout.bottomMargin: 16
                    spacing: 8
                    BrandMark { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 46 * Style.scale; Layout.preferredHeight: 46 * Style.scale }
                    LabelText {
                        visible: !window.compact
                        Layout.fillWidth: true
                        text: "SeedBank"; font.pixelSize: 20; font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter; color: Style.ink
                    }
                }
                Repeater {
                    model: [{label: "陪伴", symbol: "home"}, {label: "日记", symbol: "book"}, {label: "记忆", symbol: "heart"}, {label: "生活", symbol: "leaf"}, {label: "设置", symbol: "settings"}]
                    AppButton {
                        id: navButton
                        required property var modelData
                        required property int index
                        objectName: "nav-" + index
                        Layout.fillWidth: true
                        Layout.preferredWidth: window.bottomNavigation ? 1 : -1
                        Layout.minimumWidth: 0
                        Layout.preferredHeight: (window.bottomNavigation ? 52 : window.compact ? 70 : 54) * Style.scale
                        // The rail has a deliberate narrow mode; long translated
                        // names get an accessible tooltip instead of widening it.
                        implicitWidth: 0
                        leftPadding: 6; rightPadding: 6
                        topPadding: window.bottomNavigation ? 4 : 10
                        bottomPadding: window.bottomNavigation ? 4 : 10
                        text: Style.tr(modelData.label)
                        selected: window.page === index
                        quiet: true
                        onClicked: window.navigate(index)
                        ToolTip.visible: hovered || visualFocus
                        ToolTip.text: text
                        contentItem: GridLayout {
                            columns: window.compact || window.bottomNavigation ? 1 : 2
                            columnSpacing: 12; rowSpacing: 4
                            Icon {
                                symbol: navButton.modelData.symbol
                                tint: navButton.selected ? Style.accent : Style.muted
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 21; Layout.preferredHeight: 21
                            }
                            LabelText {
                                text: navButton.text
                                color: navButton.selected ? Style.accent : Style.muted
                                font.pixelSize: (window.compact || window.bottomNavigation ? 11 : 14) * Style.scale
                                Layout.fillWidth: true
                                horizontalAlignment: window.compact || window.bottomNavigation ? Text.AlignHCenter : Text.AlignLeft
                                maximumLineCount: 1; elide: Text.ElideRight
                            }
                        }
                    }
                }
                Item { visible: !window.bottomNavigation; Layout.fillHeight: true }
                LabelText {
                    Layout.fillWidth: true; Layout.bottomMargin: 16
                    visible: !window.compact && !window.bottomNavigation
                    text: Style.tr("每一天，慢慢成为自己。")
                    color: Style.muted
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
        ColumnLayout {
            Layout.row: 0
            Layout.column: window.bottomNavigation || !bridge.ready ? 0 : 1
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.minimumWidth: 0; Layout.minimumHeight: 0
            spacing: window.shortWindow ? 8 : 18
            RowLayout {
                Layout.fillWidth: true
                BrandMark { visible: !bridge.ready || window.bottomNavigation; Layout.preferredWidth: 32 * Style.scale; Layout.preferredHeight: 32 * Style.scale }
                LabelText { text: "SeedBank"; visible: !bridge.ready || window.compact || window.bottomNavigation; font.pixelSize: 20; font.weight: Font.DemiBold }
                LabelText { text: Style.tr("小小栖息地"); color: Style.muted; font.pixelSize: 12 * Style.scale }
                Item { Layout.fillWidth: true }
                LabelText { text: Style.tr("相伴第 {day} 天", {day: bridge.day}); color: Style.accent; font.pixelSize: 12 * Style.scale; visible: bridge.ready }
            }
            RowLayout {
                id: body
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.minimumWidth: 0; Layout.minimumHeight: 0
                spacing: window.bottomNavigation ? 12 : window.compact ? 18 : 28
                AvatarStage {
                    objectName: "companionStage"
                    visible: !bridge.ready || window.page === 0
                    Layout.preferredWidth: Math.min(470, window.contentWidth * (window.bottomNavigation ? 0.28 : window.compact ? 0.33 : 0.40))
                    Layout.minimumWidth: 0; Layout.minimumHeight: 0
                    Layout.fillHeight: true
                    active: visible && window.visible && window.visibility !== Window.Minimized
                }
                StackLayout {
                    id: pages
                    objectName: "pages"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Layout.minimumWidth: 0; Layout.minimumHeight: 0
                    currentIndex: bridge.ready ? window.page : 5
                    Room { objectName: "roomPage"; active: bridge.ready && window.page === 0 }
                    Diary { objectName: "diaryPage" }
                    Memories { id: memoriesPage; objectName: "memoryPage" }
                    Life { objectName: "lifePage" }
                    Settings { objectName: "settingsPage" }
                    Welcome { objectName: "welcomePage" }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                LabelText { text: bridge.notice; color: bridge.error ? Style.danger : Style.muted; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                BusyIndicator { running: bridge.busy; visible: running; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
            }
        }
    }
    Shortcut { sequence: "Ctrl+1"; enabled: bridge.ready; onActivated: window.navigate(0) }
    Shortcut { sequence: "Ctrl+2"; enabled: bridge.ready; onActivated: window.navigate(1) }
    Shortcut { sequence: "Ctrl+3"; enabled: bridge.ready; onActivated: window.navigate(2) }
    Shortcut { sequence: "Ctrl+4"; enabled: bridge.ready; onActivated: window.navigate(3) }
    Shortcut { sequence: "Ctrl+5"; enabled: bridge.ready; onActivated: window.navigate(4) }
    Shortcut { sequence: "Ctrl+F"; enabled: bridge.ready; onActivated: { window.navigate(2); memoriesPage.focusSearch() } }
    Dialog {
        id: discard
        anchors.centerIn: Overlay.overlay; width: 440; modal: true
        title: Style.tr("尚未保存")
        standardButtons: Dialog.Discard | Dialog.Cancel
        contentItem: LabelText { text: Style.tr("设置尚未保存。放弃这些修改并关闭吗？") }
        onDiscarded: bridge.requestClose()
    }
}
