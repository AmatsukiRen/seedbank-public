import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

Rectangle {
    id: stage
    property bool active: true
    readonly property bool condensed: height < 420 * Style.scale
    radius: 26
    color: Style.stage
    clip: true
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: stage.condensed ? 10 : stage.width < 300 ? 16 : 24
        spacing: stage.condensed ? 6 : 12
        LabelText { visible: !stage.condensed; text: bridge.ready ? Style.tr("此刻，一起") : Style.tr("等待一次初见"); color: Style.accent; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true }
        LabelText {
            text: bridge.ready ? bridge.name : "SEEDbank"
            font.pixelSize: (stage.condensed ? 20 : stage.width < 300 ? 23 : 30) * Style.scale
            font.weight: Font.DemiBold
            Layout.fillWidth: true
            maximumLineCount: stage.condensed ? 1 : 2; elide: Text.ElideRight
        }
        Pet {
            id: pet
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: stage.condensed ? 64 : 160
            running: stage.active && (!bridge.ready || bridge.lifeActive)
            onSettingsRequested: modelFile.open()
        }
        RowLayout {
            Layout.fillWidth: true
            LabelText {
                text: Style.tr("拖动移位 · 滚轮缩放")
                Layout.fillWidth: true
                color: Style.muted; font.pixelSize: 11 * Style.scale
                visible: pet.loadStatus === "ready"
            }
            AppButton {
                objectName: "resetAvatarView"
                text: Style.tr("复位"); compact: true
                Accessible.name: Style.tr("还原角色视图")
                enabled: pet.loadStatus === "ready"
                onClicked: bridge.setAvatarView(1.0, 0.0, 0.0)
            }
        }
        LabelText {
            text: bridge.ready ? (bridge.lifeActive ? bridge.mood : Style.tr(bridge.lifecycle.state === "unavailable" ? "生命状态记录无法读取，自动活动已停止；原文件已保留。" : "已休眠，档案完整保留。")) : Style.tr("形象是相遇的载体，经历从出生开始。")
            color: Style.muted
            font.pixelSize: 13 * Style.scale
            Layout.fillWidth: true
            maximumLineCount: stage.condensed ? 2 : 3; elide: Text.ElideRight
        }
        RowLayout {
            visible: bridge.ready && !stage.condensed
            Layout.fillWidth: true
            spacing: 10
            LabelText { text: Style.tr("精力"); color: Style.muted; font.pixelSize: 12 * Style.scale }
            Rectangle {
                Layout.fillWidth: true; height: 4; radius: 2; color: Style.line
                Rectangle { width: parent.width * Math.max(0, Math.min(1, bridge.energy)); height: 4; radius: 2; color: Style.accent }
            }
            LabelText { text: Math.round(bridge.energy * 100) + "%"; color: Style.muted; font.pixelSize: 12 * Style.scale }
        }
        AppButton {
            objectName: "avatarWave"
            Layout.fillWidth: true
            implicitWidth: 0
            compact: stage.condensed
            text: Style.tr("打个招呼")
            symbol: "heart"; quiet: true
            enabled: pet.loadStatus === "ready" && !Style.reduced && (!bridge.ready || bridge.lifeActive)
            onClicked: pet.play("wave")
        }
    }
    FileDialog {
        id: modelFile
        title: Style.tr("选择角色模型")
        nameFilters: ["Live2D (*.model3.json)"]
        onAccepted: bridge.selectAvatarModel(selectedFile.toString())
    }
}
