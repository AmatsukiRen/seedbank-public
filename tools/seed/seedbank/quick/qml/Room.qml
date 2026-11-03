import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

Item {
    id: room
    property bool active: false
    readonly property bool condensed: height < 360 * Style.scale
    RowLayout {
        anchors.fill: parent
        spacing: width < 1000 ? 22 : 40
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: room.condensed ? 8 : 16
            LabelText { visible: !bridge.lifeActive; text: Style.tr(bridge.lifecycle.state === "unavailable" ? "生命状态记录无法读取，自动活动已停止；原文件已保留。" : "此个体已休眠；档案仍可查看，请明确恢复后再继续活动。"); color: Style.accent; Layout.fillWidth: true }
            LabelText { visible: !room.condensed; text: Style.tr("今天，想聊些什么？"); font.pixelSize: (room.width < 500 ? 23 : 28) * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
            ListView {
                id: messages
                objectName: "chatList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 14
                model: chatModel
                reuseItems: true
                cacheBuffer: 150
                boundsBehavior: Flickable.StopAtBounds
                property bool followTail: true
                onMovementEnded: followTail = atYEnd
                onContentHeightChanged: if (followTail) positionViewAtEnd()
                ScrollBar.vertical: SlimBar {}
                delegate: Item {
                    required property var entry
                    width: messages.width - 16
                    height: bubble.height
                    Rectangle {
                        id: bubble
                        width: parent.width * 0.94
                        anchors.right: entry.incoming ? undefined : parent.right
                        radius: 19
                        color: entry.incoming ? Style.surface : Style.soft
                        height: bubbleBody.implicitHeight + 32
                        Column {
                            id: bubbleBody
                            x: 18; y: 16; width: parent.width - 36; spacing: 8
                            LabelText { text: entry.observation ? Style.tr("她的小房间") : entry.who; color: Style.accent; font.pixelSize: 12 * Style.scale; width: parent.width }
                            TextEdit {
                                text: entry.text; width: parent.width
                                font.pixelSize: 16 * Style.scale; color: Style.ink
                                wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                                readOnly: true; selectByMouse: true; activeFocusOnTab: false
                            }
                        }
                    }
                }
                LabelText {
                    visible: messages.count === 0
                    width: parent.width - 40
                    anchors.centerIn: parent
                    horizontalAlignment: Text.AlignHCenter
                    text: Style.tr("从一句问候开始，把今天的一点小事告诉她。")
                    color: Style.muted
                }
                Connections {
                    target: bridge
                    function onChatUpdated(newDay) { if (newDay) messages.followTail = true; if (messages.followTail) Qt.callLater(messages.positionViewAtEnd) }
                }
            }
            LabelText { objectName: "replyThinking"; text: Style.tr("她正在想怎么回答你…"); visible: bridge.avatarThinking && !room.condensed; color: Style.accent; font.pixelSize: 13 * Style.scale; Layout.fillWidth: true }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: composerLayout.implicitHeight + (room.condensed ? 20 : 28)
                radius: 22
                color: Style.surface
                border.color: Style.accent
                border.width: composer.activeFocus ? 2 : 0
                ColumnLayout {
                    id: composerLayout
                    enabled: bridge.lifeActive
                    x: 16; y: room.condensed ? 10 : 14; width: parent.width - 32; spacing: room.condensed ? 6 : 10
                    ScrollPane {
                        objectName: "composerScroll"
                        Layout.fillWidth: true
                        Layout.preferredHeight: (room.condensed ? 48 : room.height < 520 ? 72 : 104) * Style.scale
                        Layout.minimumHeight: (room.condensed ? 48 : 72) * Style.scale
                        Layout.maximumHeight: 104 * Style.scale
                        TextArea {
                        id: composer
                        objectName: "composer"
                        font.pixelSize: 16 * Style.scale
                        color: Style.ink
                        placeholderText: Style.tr("对她说的话")
                        placeholderTextColor: Style.muted
                        Accessible.name: placeholderText
                        wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.PlainText
                        selectByMouse: true
                        Keys.onTabPressed: nextItemInFocusChain(true).forceActiveFocus(Qt.TabFocusReason)
                        Keys.onBacktabPressed: nextItemInFocusChain(false).forceActiveFocus(Qt.BacktabFocusReason)
                        text: bridge.draft
                        onTextChanged: bridge.setDraft(text)
                        background: Item {}
                        Keys.onPressed: function(event) {
                            if (!inputMethodComposing && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                                bridge.send(); event.accepted = true
                            }
                        }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        LabelText { text: "Ctrl + Enter"; color: Style.muted; font.pixelSize: 11 * Style.scale; Layout.fillWidth: true }
                        LabelText {
                            readonly property int count: bridge.textLength(composer.text.trim())
                            text: count + " / 2000"
                            color: count > 2000 ? Style.danger : Style.muted
                            font.pixelSize: 11 * Style.scale
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        AppButton { compact: room.condensed; text: Style.tr("照片"); symbol: "photo"; quiet: true; enabled: !bridge.busy; onClicked: photo.open() }
                        AppButton { compact: room.condensed; text: Style.tr("声音"); quiet: true; enabled: !bridge.busy; onClicked: soundFile.open() }
                        AppButton { objectName: "sendMessage"; compact: room.condensed; text: Style.tr("发送"); symbol: "send"; primary: true; enabled: !bridge.busy && composer.text.trim() !== "" && bridge.textLength(composer.text.trim()) <= 2000; onClicked: bridge.send() }
                    }
                    AppButton { objectName: "retryMediaInput"; visible: bridge.mediaInputPending && !bridge.busy; text: Style.tr("继续上次材料处理"); enabled: !bridge.busy; onClicked: bridge.retryMediaInput() }
                }
            }
        }
    }
    FileDialog { id: photo; title: Style.tr("选择照片，原件将保存在生命包"); nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp)"]; onAccepted: bridge.sendPhoto(selectedFile.toString()) }
    FileDialog { id: soundFile; title: Style.tr("选择 WAV 声音，原件将保存在生命包"); nameFilters: ["WAV (*.wav)"]; onAccepted: bridge.sendSound(selectedFile.toString()) }
}
