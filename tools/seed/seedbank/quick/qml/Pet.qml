import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Seedbank.Avatar 1.0

Item {
    id: pet
    objectName: "live2dStage"
    property bool running: true
    property string stateName: "idle"
    property string expressionName: "idle"
    property string previousExpression: ""
    property bool expressionReady: false
    readonly property string moodStyle: bridge.avatarMood
    readonly property bool thinking: bridge.avatarThinking
    readonly property bool utteranceActive: utteranceTimer.running
    readonly property bool expressionActive: expressionReady && running && visible && !Style.reduced && bridge.ready && bridge.lifeActive
    readonly property real viewZoom: bridge.preferences.live2d_zoom || 1.0
    readonly property real viewX: bridge.preferences.live2d_offset_x || 0.0
    readonly property real viewY: bridge.preferences.live2d_offset_y || 0.0
    readonly property string loadStatus: testMode ? "disabled" : !bridge.avatarModel ? "unconfigured" : !avatarGraphicsEnabled ? "error" : viewer.item ? viewer.item.status : "loading"
    onLoadStatusChanged: if (issueScroll && issueScroll.contentItem) issueScroll.contentItem.contentY = 0
    signal settingsRequested()
    Component.onCompleted: expressionReady = true

    function restInterval() { return 18000 + Math.floor(Math.random() * 17000) }
    function showMood() {
        if (!expressionActive || thinking || utteranceActive) return
        expressionName = bridge.avatarExpression(previousExpression)
        previousExpression = expressionName
        expressionReset.interval = 4000 + Math.floor(Math.random() * 3000)
        expressionReset.restart()
    }
    function refreshExpression() {
        if (!expressionReady) return
        if (expressionActive && !thinking && utteranceActive) return
        expressionReset.stop()
        expressionName = expressionActive && thinking ? "think" : "idle"
        if (expressionActive && !thinking) showMood()
    }
    onMoodStyleChanged: refreshExpression()
    onThinkingChanged: {
        if (!expressionReady) return
        if (thinking) {
            utteranceTimer.stop()
            reset.stop()
            stateName = "idle"
        }
        refreshExpression()
    }
    onExpressionActiveChanged: {
        if (!expressionReady) return
        utteranceTimer.stop()
        reset.stop()
        stateName = "idle"
        refreshExpression()
    }
    function play(action) {
        if (!running || !visible || Style.reduced) return
        if (utteranceActive && action !== "wave" && action !== "dance") return
        if (action === "wave" || action === "dance") {
            stateName = "wave"
            reset.restart()
        } else if (action === "think") {
            if (expressionActive && thinking) {
                expressionReset.stop()
                expressionName = "think"
            }
        } else if (action === "idle") {
            expressionReset.stop()
            expressionName = "idle"
        } else if (["happy", "warm", "sad", "nervous", "angry"].indexOf(action) >= 0) {
            expressionName = action
            expressionReset.interval = 5000
            expressionReset.restart()
        } else {
            showMood()
        }
    }
    function presentUtterance(cue) {
        if (!expressionActive || thinking) return
        expressionReset.stop()
        reset.stop()
        stateName = "idle"
        var expression = cue.expression
        expressionName = ["happy", "warm", "sad", "nervous", "angry"].indexOf(expression) >= 0 ? expression : "idle"
        if (cue.gesture === "wave") {
            stateName = "wave"
            reset.restart()
        }
        utteranceTimer.interval = Math.max(3000, Math.min(12000, Number(cue.duration_ms) || 3000))
        utteranceTimer.restart()
    }
    Timer {
        id: utteranceTimer
        objectName: "avatarUtteranceTimer"
        onTriggered: {
            stop()
            reset.stop()
            pet.stateName = "idle"
            pet.expressionName = "idle"
        }
    }
    Timer {
        id: reset
        interval: 3200
        onTriggered: pet.stateName = "idle"
    }
    Timer {
        id: expressionReset
        objectName: "avatarExpressionReset"
        onTriggered: pet.expressionName = pet.expressionActive && pet.thinking ? "think" : "idle"
    }
    Timer {
        id: ambientExpression
        objectName: "avatarExpressionTimer"
        interval: pet.restInterval()
        running: pet.expressionActive && !pet.thinking && !pet.utteranceActive
        repeat: true
        onTriggered: {
            pet.showMood()
            interval = pet.restInterval()
        }
    }
    Connections {
        target: bridge
        function onPetAction(action) { pet.play(action) }
        function onAvatarUtterance(cue) { pet.presentUtterance(cue) }
        function onAvatarReloadRequested() { if (viewer.item) viewer.item.reload() }
    }
    Loader {
        id: viewer
        anchors.fill: parent
        active: !testMode && avatarGraphicsEnabled && !!bridge.avatarModel
        sourceComponent: Live2DView {
            objectName: "live2dView"
            source: bridge.avatarModel
            animating: pet.running && pet.visible && !Style.reduced
            motion: pet.stateName
            expression: pet.expressionName
            zoom: pet.viewZoom
            offsetX: interaction.dragging ? interaction.previewX : pet.viewX
            offsetY: interaction.dragging ? interaction.previewY : pet.viewY
        }
    }
    MouseArea {
        id: interaction
        objectName: "avatarInteraction"
        anchors.fill: parent
        enabled: pet.loadStatus === "ready"
        hoverEnabled: true
        preventStealing: true
        activeFocusOnTab: true
        acceptedButtons: Qt.LeftButton
        cursorShape: dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        property bool dragging: false
        property bool moved: false
        property real startX: 0
        property real startY: 0
        property real originX: 0
        property real originY: 0
        property real previewX: 0
        property real previewY: 0
        Accessible.name: Style.tr("角色视图")
        Accessible.description: Style.tr("拖动调整位置，滚轮缩放。方向键微调，Home 复位。")
        onPressed: function(mouse) {
            forceActiveFocus()
            moved = false
            dragging = false
            startX = mouse.x; startY = mouse.y
            originX = pet.viewX; originY = pet.viewY
            previewX = originX; previewY = originY
            if (viewer.item) viewer.item.lookAt(0.5, 0.5)
        }
        onPositionChanged: function(mouse) {
            if (pressed) {
                var dx = mouse.x - startX, dy = mouse.y - startY
                if (moved || Math.sqrt(dx * dx + dy * dy) >= Qt.styleHints.startDragDistance) {
                    moved = true
                    previewX = Math.max(-0.45, Math.min(0.45, originX + dx / Math.max(1, width)))
                    previewY = Math.max(-0.45, Math.min(0.45, originY + dy / Math.max(1, height)))
                    dragging = true
                }
            } else if (viewer.item && pet.running && !Style.reduced) {
                viewer.item.lookAt(mouse.x / Math.max(1, width), mouse.y / Math.max(1, height))
            }
        }
        onReleased: {
            if (moved) bridge.setAvatarView(pet.viewZoom, previewX, previewY)
            dragging = false
        }
        onCanceled: { moved = true; dragging = false }
        onEnabledChanged: if (!enabled) { moved = true; dragging = false }
        onExited: if (viewer.item) viewer.item.lookAt(0.5, 0.5)
        onClicked: if (!moved) pet.play("wave")
        onWheel: function(wheel) {
            if (pressed) return
            var delta = wheel.angleDelta.y || wheel.pixelDelta.y
            if (delta) {
                bridge.setAvatarView(pet.viewZoom + (delta > 0 ? 0.05 : -0.05), pet.viewX, pet.viewY)
                wheel.accepted = true
            }
        }
        Keys.onPressed: function(event) {
            var step = event.modifiers & Qt.ShiftModifier ? 0.05 : 0.02
            var x = pet.viewX, y = pet.viewY, zoom = pet.viewZoom
            if (event.key === Qt.Key_Left) x -= step
            else if (event.key === Qt.Key_Right) x += step
            else if (event.key === Qt.Key_Up) y -= step
            else if (event.key === Qt.Key_Down) y += step
            else if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) zoom += 0.05
            else if (event.key === Qt.Key_Minus) zoom -= 0.05
            else if (event.key === Qt.Key_Home) { x = 0; y = 0; zoom = 1 }
            else return
            event.accepted = true
            bridge.setAvatarView(zoom, x, y)
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 2
            visible: interaction.activeFocus
            color: "transparent"; radius: 12
            border.color: Style.accent; border.width: 2
        }
    }
    ScrollPane {
        id: issueScroll
        objectName: "avatarIssueScroll"
        anchors.fill: parent
        visible: pet.loadStatus !== "ready"
        ColumnLayout {
        width: Math.max(0, issueScroll.availableWidth - 14)
        spacing: 14
        BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: pet.loadStatus === "loading"; visible: running }
        LabelText {
            objectName: "avatarStatus"
            Layout.fillWidth: true
            text: testMode ? Style.tr("角色渲染在隔离测试中关闭。") : pet.loadStatus === "unconfigured" ? Style.tr("选择一个本地角色，开始相见。") : pet.loadStatus === "error" ? Style.tr("角色暂时没有显示") : Style.tr("正在准备角色…")
            horizontalAlignment: Text.AlignHCenter
            color: Style.muted
        }
        LabelText {
            Layout.fillWidth: true
            visible: pet.loadStatus === "error" || pet.loadStatus === "unconfigured"
            text: pet.loadStatus === "unconfigured" ? Style.tr("未附带角色模型；对话和记录仍可使用。") : Style.tr("请检查模型位置；对话和记录仍可使用。")
            horizontalAlignment: Text.AlignHCenter
            color: Style.muted
            font.pixelSize: 12 * Style.scale
        }
        AvatarModelHelp {
            Layout.fillWidth: true
            visible: pet.loadStatus === "error" || pet.loadStatus === "unconfigured"
        }
        AppButton {
            Layout.fillWidth: true
            implicitWidth: 0
            implicitHeight: Math.max(44 * Style.scale, contentItem.implicitHeight + 20)
            visible: pet.loadStatus === "error"
            enabled: viewer.item !== null
            text: Style.tr("重新加载")
            onClicked: if (viewer.item) viewer.item.reload()
            contentItem: LabelText { text: parent.text; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 14 * Style.scale }
        }
        AppButton {
            Layout.fillWidth: true
            implicitWidth: 0
            implicitHeight: Math.max(44 * Style.scale, contentItem.implicitHeight + 20)
            visible: pet.loadStatus === "error" || pet.loadStatus === "unconfigured"
            text: Style.tr("选择角色模型")
            quiet: true
            onClicked: pet.settingsRequested()
            contentItem: LabelText { text: parent.text; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 14 * Style.scale }
        }
        LabelText {
            Layout.fillWidth: true
            visible: pet.loadStatus === "error"
            text: !avatarGraphicsEnabled ? Style.tr("当前图形模式不支持角色渲染。") : viewer.item ? viewer.item.detail : ""
            wrapMode: Text.WrapAnywhere
            color: Style.muted
            font.pixelSize: 11 * Style.scale
        }
        }
    }
}
