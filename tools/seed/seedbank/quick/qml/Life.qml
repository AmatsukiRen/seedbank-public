import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    property string section: "growth"
    readonly property bool condensed: height < 360 * Style.scale
    spacing: page.condensed ? 8 : 18
    LabelText { visible: !page.condensed; text: Style.tr("她的小小生活"); font.pixelSize: 30 * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
    RowLayout {
        spacing: 8
        Repeater {
            model: [{key: "growth", label: "成长"}, {key: "heart", label: "心事"}, {key: "works", label: "作品"}]
            AppButton { required property var modelData; compact: page.condensed; text: Style.tr(modelData.label); selected: page.section === modelData.key; quiet: true; onClicked: { page.section = modelData.key; bridge.lifeSection(page.section); list.positionViewAtBeginning() } }
        }
    }
    Flow {
        Layout.fillWidth: true; spacing: 8
        AppButton { objectName: "openLearning"; compact: page.condensed; text: Style.tr("练习与反馈"); enabled: !bridge.busy; onClicked: learningDialog.open() }
        AppButton { objectName: "openRelationships"; compact: page.condensed; text: Style.tr("相处与约定"); enabled: !bridge.busy; onClicked: relationshipsDialog.open() }
        AppButton { objectName: "openLifeStory"; compact: page.condensed; text: Style.tr("人生回顾"); enabled: !bridge.busy; onClicked: lifeStoryDialog.open() }
        AppButton { objectName: "openReminders"; compact: page.condensed; text: Style.tr("提醒与日期"); enabled: !bridge.busy; onClicked: reminder.open() }
        AppButton { objectName: "openLifecycle"; compact: page.condensed; text: Style.tr("休眠与恢复"); enabled: !bridge.busy; onClicked: lifecycleDialog.open() }
    }
    Learning { id: learningDialog }
    Relationships { id: relationshipsDialog }
    LifeStory { id: lifeStoryDialog }
    Lifecycle { id: lifecycleDialog }
    ListView {
        id: list
        objectName: "lifeList"
        Layout.fillWidth: true; Layout.fillHeight: true
        model: lifeModel; clip: true; reuseItems: true; spacing: 16; cacheBuffer: 150
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: SlimBar {}
        delegate: Panel {
            required property var entry
            width: list.width - 14
            caption: entry.title
            LabelText { text: entry.text; Layout.fillWidth: true; visible: text !== "" }
            RowLayout {
                visible: entry.action !== ""
                AppButton { visible: entry.action === "day"; text: Style.tr("陪她过一天"); enabled: !bridge.busy; onClicked: dayConfirm.open() }
                AppButton { visible: entry.action === "remind"; text: Style.tr("记一件事"); symbol: "plus"; enabled: !bridge.busy; onClicked: reminder.open() }
                Repeater {
                    model: entry.action === "work" ? [{key: "poem", label: "写首诗"}, {key: "letter", label: "写封信"}, {key: "drawing", label: "画点什么"}] : []
                    AppButton { required property var modelData; text: Style.tr(modelData.label); enabled: !bridge.busy; onClicked: bridge.compose(modelData.key) }
                }
            }
        }
    }
    Dialog {
        id: dayConfirm
        anchors.centerIn: Overlay.overlay; width: 440; modal: true
        title: Style.tr("陪她过一天")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: LabelText { text: Style.tr("这会结束当前一天、写下日记并推进生命天数。平时也会随真实日期自然推进。继续吗？") }
        onAccepted: bridge.advanceDay()
    }
    Reminder { id: reminder }
}
