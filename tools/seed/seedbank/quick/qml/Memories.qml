import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    readonly property bool condensed: height < 460 * Style.scale
    property bool showTools: false
    function focusSearch() { search.input.forceActiveFocus(Qt.ShortcutFocusReason) }
    function filter() { bridge.filterMemories(search.text, forgotten.checked, history.checked); memories.positionViewAtBeginning() }
    spacing: page.condensed ? 8 : 16
    LabelText { visible: !page.condensed; text: Style.tr("她记得的小事"); font.pixelSize: 30 * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
    LabelText { visible: !page.condensed; text: Style.tr("放下记忆，不等于抹去她的过去。"); color: Style.muted; Layout.fillWidth: true }
    Disclosure { id: disclosureDialog }
    MediaArchive { id: mediaDialog }
    RowLayout {
        Layout.fillWidth: true
        Field {
            id: search
            objectName: "memorySearch"
            caption: Style.tr("搜索记忆")
            compact: page.condensed
            Layout.fillWidth: true
            onEdited: filterTimer.restart()
            input.onAccepted: page.filter()
        }
        AppButton { compact: page.condensed; text: Style.tr("搜索"); symbol: "search"; Layout.alignment: Qt.AlignBottom; onClicked: page.filter() }
        AppButton {
            objectName: "memoryToolsToggle"
            visible: page.condensed; compact: true; Layout.alignment: Qt.AlignBottom
            text: Style.tr("筛选与工具") + (history.checked || forgotten.checked ? " · " + (Number(history.checked) + Number(forgotten.checked)) : "")
            selected: page.showTools
            ToolTip.visible: hovered || visualFocus
            ToolTip.text: Style.tr(page.showTools ? "收起筛选与工具" : "筛选与工具")
            onClicked: page.showTools = !page.showTools
        }
    }
    ScrollPane {
        id: toolsScroll
        objectName: "memoryToolsScroll"
        visible: !page.condensed || page.showTools
        Layout.fillWidth: true
        Layout.minimumHeight: 0
        Layout.preferredHeight: Math.min(filterOptions.implicitHeight, Math.max(60, page.height * 0.45))
        contentHeight: filterOptions.implicitHeight
        ColumnLayout {
            id: filterOptions
            width: Math.max(0, toolsScroll.availableWidth - 14)
            spacing: page.condensed ? 8 : 16
            Flow {
                Layout.fillWidth: true; spacing: 8
                AppButton { objectName: "openFacts"; compact: page.condensed; symbol: "book"; text: Style.tr("单项记录与分歧"); enabled: !bridge.busy; onClicked: facts.open() }
                AppButton { objectName: "openDisclosure"; compact: page.condensed; symbol: "heart"; text: Style.tr("分享与私人记忆"); enabled: !bridge.busy; onClicked: disclosureDialog.open() }
                AppButton { objectName: "openMediaArchive"; compact: page.condensed; symbol: "photo"; text: Style.tr("原始图片与声音"); enabled: !bridge.busy; onClicked: mediaDialog.open() }
            }
            ToggleRow {
                id: history
                objectName: "includeMemoryHistory"
                text: Style.tr("包含修改前的版本")
                Layout.preferredWidth: Math.min(filterOptions.width, Math.max(330, implicitWidth))
                onToggled: page.filter()
            }
            ToggleRow {
                id: forgotten
                text: Style.tr("包含已放下的记忆")
                Layout.preferredWidth: Math.min(filterOptions.width, Math.max(330, implicitWidth))
                onToggled: page.filter()
            }
        }
    }
    ListView {
        id: memories
        objectName: "memoryList"
        Layout.fillWidth: true; Layout.fillHeight: true
        model: memoryModel
        clip: true; reuseItems: true; spacing: 10; cacheBuffer: 150
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: SlimBar {}
        delegate: Rectangle {
            required property var entry
            width: memories.width - 14
            height: memoryBody.implicitHeight + 40
            radius: 16; color: Style.surface
            RowLayout {
                id: memoryBody
                x: 22; y: 20; width: parent.width - 44; spacing: 20
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 10
                    LabelText { text: entry.day + " · " + (entry.kind === "forget" ? Style.tr("放下记录") : entry.forgotten ? Style.tr("已放下") : entry.superseded ? Style.tr("已更正") : entry.recallable === false ? Style.tr("仅存档") : Style.tr("记忆")); color: Style.muted; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true }
                    LabelText { text: entry.text; font.pixelSize: 16 * Style.scale; Layout.fillWidth: true }
                }
                ColumnLayout {
                    spacing: 10
                    AppButton { text: Style.tr("详情与修订"); symbol: "edit"; Layout.fillWidth: true; enabled: !bridge.busy; onClicked: { if (bridge.loadMemory(entry.id)) details.open() } }
                    AppButton { visible: !entry.forgotten && entry.kind !== "forget"; text: Style.tr("放下这条"); symbol: "archive"; danger: true; Layout.fillWidth: true; enabled: !bridge.busy; onClicked: { confirm.identifier = entry.id; confirm.open() } }
                }
            }
        }
        LabelText { visible: memories.count === 0; anchors.centerIn: parent; width: parent.width * 0.8; horizontalAlignment: Text.AlignHCenter; text: Style.tr("没有找到这段记忆。换个词，或一起创造新的回忆吧。"); color: Style.muted }
    }
    Timer { id: filterTimer; interval: 160; onTriggered: page.filter() }
    MemoryDetails { id: details }
    Facts { id: facts }
    Dialog {
        id: confirm
        property string identifier: ""
        anchors.centerIn: Overlay.overlay
        width: 450
        modal: true
        title: Style.tr("放下一段记忆")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: LabelText { text: Style.tr("她将不再主动想起这一条；原始记录仍会保留。确定继续吗？") }
        onAccepted: bridge.forget(identifier)
    }
}
