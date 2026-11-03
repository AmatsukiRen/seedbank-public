import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: panel
    property var choices: bridge.channelPresets()
    property var selected: choices.find(function(row) { return row.id === bridge.channelForm.id }) || choices[0]
    property var connectionState: bridge.channelStatus.find(function(row) { return row.id === bridge.channelForm.id }) || ({running: false, state: Style.tr("尚未启动"), received: 0, sent: 0, failed: 0})
    spacing: 16
    Component.onCompleted: bridge.selectChannel(bridge.channelForm.id)
    Connections { target: bridge; function onLocaleChanged() { panel.choices = bridge.channelPresets() } }
    Panel {
        caption: Style.tr("从更多地方来见她")
        detail: Style.tr("桌面与聊天平台共用同一个体；每个渠道需要你自己的机器人凭据。")
        Layout.fillWidth: true
        Choice {
            objectName: "channelChoice"
            Layout.fillWidth: true; model: panel.choices; textRole: "label"
            currentIndex: panel.choices.findIndex(function(row) { return row.id === bridge.channelForm.id })
            onActivated: bridge.selectChannel(panel.choices[currentIndex].id)
        }
        LabelText { text: panel.selected.hint; Layout.fillWidth: true; color: Style.muted }
        Field { caption: Style.tr("主人账号 ID"); Layout.fillWidth: true; text: bridge.channelForm.owner; onEdited: function(value) { bridge.editChannel("owner", value) } }
        Field { caption: Style.tr("群或频道白名单（逗号分隔）"); Layout.fillWidth: true; text: bridge.channelForm.groups; onEdited: function(value) { bridge.editChannel("groups", value) } }
        Field { caption: Style.tr("令牌环境变量名"); Layout.fillWidth: true; text: bridge.channelForm.token_env; onEdited: function(value) { bridge.editChannel("token_env", value) } }
        Field { visible: ["feishu", "dingtalk"].indexOf(bridge.channelForm.id) >= 0; caption: "App ID / Client ID"; Layout.fillWidth: true; text: bridge.channelForm.app_id; onEdited: function(value) { bridge.editChannel("app_id", value) } }
        Field { visible: bridge.channelForm.id === "feishu"; caption: Style.tr("机器人 open_id"); Layout.fillWidth: true; text: bridge.channelForm.self_id; onEdited: function(value) { bridge.editChannel("self_id", value) } }
        Field { visible: bridge.channelForm.id === "astrbot"; caption: Style.tr("本机上报端口"); Layout.fillWidth: true; text: String(bridge.channelForm.port); onEdited: function(value) { bridge.editChannel("port", value) } }
        LabelText { text: Style.tr("这里只填变量名；实际 Token 或 App Secret 放入电脑的环境变量，再重新打开 SeedBank。模型 API Key 在“对话”页单独设置。"); color: Style.muted; Layout.fillWidth: true }
        RowLayout {
            AppButton { text: Style.tr("保存设置"); enabled: !bridge.busy; onClicked: bridge.saveChannel() }
            AppButton { objectName: "startChannelButton"; text: panel.connectionState.running ? Style.tr("停止连接") : Style.tr("启动连接"); primary: true; enabled: !bridge.busy; onClicked: bridge.toggleChannel(!panel.connectionState.running) }
        }
        LabelText { objectName: "channelDeliveryStatus"; text: panel.connectionState.state; Layout.fillWidth: true; color: Style.accent }
        LabelText {
            objectName: "channelDeliveryCounts"
            text: (bridge.channelForm.id === "astrbot" ? Style.tr("已接收 / 已转交插件 / 失败") : Style.tr("已接收 / 已交付 / 失败"))
                  + ": " + panel.connectionState.received + " / "
                  + (bridge.channelForm.id === "astrbot" ? (panel.connectionState.relayed || 0) : panel.connectionState.sent)
                  + " / " + panel.connectionState.failed
            Layout.fillWidth: true; color: Style.muted
        }
    }
    ObservationPanel { visible: bridge.channelForm.id !== "astrbot"; Layout.fillWidth: true }
    Panel {
        caption: Style.tr("连接与可见范围")
        Layout.fillWidth: true
        LabelText { text: Style.tr("文字回复仅限主人私聊、白名单群内明确提及；可另外指定旁听群。群聊不使用私人上下文，附件、语音和主动推送暂未接入。"); Layout.fillWidth: true; color: Style.muted }
        LabelText { text: Style.tr("关窗后停止连接，下次打开需手动启动。休眠期间不处理消息；重复事件和失败回复不会自动重试。平台连接与模型请求可能使用你的服务额度。"); Layout.fillWidth: true; color: Style.muted }
        LabelText { text: Style.tr("QQ 与 SnowLuma 请使用 QQ 页的 OneBot v11。AstrBot 需要安装随包插件；同一账号、同一会话只选择一条接入路径，避免重复回复。"); Layout.fillWidth: true; color: Style.muted }
    }
}
