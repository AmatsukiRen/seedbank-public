import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Panel {
    id: panel
    property bool qqMode: false
    property var form: qqMode ? bridge.qqForm : bridge.channelForm
    caption: Style.tr("旁听与学习")
    detail: Style.tr("指定群的新文字消息会作为见闻保存，分批提炼笔记；旁听不会自动发言。")
    function edit(key, value) { if (qqMode) bridge.editQQ(key, value); else bridge.editChannel(key, value) }
    Field {
        objectName: "observationGroups"
        caption: Style.tr("旁听群或频道 ID（逗号分隔，留空关闭）")
        Layout.fillWidth: true; text: String(panel.form.observe_groups || "")
        onEdited: function(value) { panel.edit("observe_groups", value) }
    }
    Field {
        objectName: "observationDailyLimit"
        caption: Style.tr("每日整理调用上限（1–20）")
        Layout.fillWidth: true; text: String(panel.form.observe_daily_limit || 4)
        onEdited: function(value) { panel.edit("observe_daily_limit", value) }
    }
    LabelText {
        Layout.fillWidth: true; color: Style.muted
        text: Style.tr("保存后重新启动连接生效。回复仍由群白名单和 @ 控制；只旁听的群不会回复。每批最多 20 条、6000 字，每分钟检查，满批或等待 5 分钟后整理。多个渠道共享每日额度，使用其中较小上限。")
    }
    LabelText {
        Layout.fillWidth: true; color: Style.muted
        text: Style.tr("只接收平台实际推送的新文字，不抓取历史或附件。队列最多 80 条，每天最多接收 1000 条；超出不保存，待整理超过 24 小时不再自动提交。模型只读本批群聊，原文和笔记按群隔离。")
    }
    LabelText {
        Layout.fillWidth: true; color: Style.muted
        text: Style.tr("整理使用当前模型，可能计费；这是调用次数上限，不是 token 费用上限。平台权限决定能收到哪些消息，未推送的普通群聊无法旁听。")
    }
    AppButton { objectName: "openObservationHistory"; text: Style.tr("查看旁听记录"); enabled: !bridge.busy; onClicked: audit.open() }
    Dialog {
        id: audit
        objectName: "observationHistoryDialog"
        parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(760, parent ? parent.width - 32 : 760)
        height: Math.min(700, parent ? parent.height - 32 : 700)
        modal: true; focus: true; closePolicy: Popup.CloseOnEscape
        onOpened: bridge.observationPage(0)
        background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
        header: Item {
            implicitHeight: heading.implicitHeight + 32
            RowLayout {
                id: heading; anchors.fill: parent; anchors.margins: 16
                LabelText { text: Style.tr("旁听记录"); Layout.fillWidth: true; font.pixelSize: 22 * Style.scale }
                AppButton { objectName: "closeObservationHistory"; text: Style.tr("关闭"); onClicked: audit.reject() }
            }
        }
        contentItem: ScrollPane {
            id: scroll
            ColumnLayout {
                width: scroll.availableWidth; spacing: 14
                LabelText { text: bridge.notice; Layout.fillWidth: true; color: bridge.error ? Style.danger : Style.muted }
                LabelText { text: Style.tr("待整理 / 今日已尝试") + ": " + bridge.observationHistory.pending + " / " + bridge.observationHistory.attempts + " · " + bridge.observationHistory.date; Layout.fillWidth: true }
                LabelText { text: Style.tr("每页显示 10 批原文与笔记。放下后停止检索原文及派生笔记，历史审阅仍保留；关闭旁听只停止后续收集。失败和中断批次不会自动重试。"); Layout.fillWidth: true; color: Style.muted }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("刷新"); enabled: !bridge.busy; onClicked: bridge.loadObservations() }
                    AppButton { objectName: "processObservations"; text: Style.tr("现在整理一批（使用模型）"); enabled: !bridge.busy && bridge.observationHistory.pending > 0 && bridge.lifeActive; onClicked: bridge.processObservations() }
                    AppButton { objectName: "withdrawPendingObservations"; text: Style.tr("放下待整理内容"); enabled: !bridge.busy && bridge.observationHistory.pending > 0; onClicked: bridge.withdrawObservation("pending") }
                }
                AppButton { id: showPending; text: Style.tr("待整理原文"); property bool expanded: false; onClicked: expanded = !expanded }
                LabelText { visible: showPending.expanded; text: (bridge.observationHistory.pending_messages || []).join("\n\n") || Style.tr("暂无到期的旁听内容。"); Layout.fillWidth: true; color: Style.muted }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("上一页"); enabled: !bridge.busy && bridge.observationHistory.page > 0; onClicked: bridge.observationPage(bridge.observationHistory.page - 1) }
                    LabelText { text: (bridge.observationHistory.page + 1) + " / " + bridge.observationHistory.pages }
                    AppButton { text: Style.tr("下一页"); enabled: !bridge.busy && bridge.observationHistory.page + 1 < bridge.observationHistory.pages; onClicked: bridge.observationPage(bridge.observationHistory.page + 1) }
                }
                Repeater {
                    model: bridge.observationHistory.batches || []
                    Panel {
                        required property var modelData
                        Layout.fillWidth: true; inset: 16
                        caption: modelData.channel + " · " + modelData.group + " · " + modelData.at
                        detail: Style.tr(({completed: "已整理", failed: "失败（不重试）", attempting: "已尝试／结果未确认", withdrawn: "已放下", expired: "已过期（未提交模型）"})[modelData.state] || "等待整理")
                        LabelText { text: (modelData.messages || []).join("\n\n"); Layout.fillWidth: true; color: Style.muted }
                        Repeater {
                            model: modelData.notes || []
                            LabelText { required property var modelData; text: Style.tr("旁听笔记") + ": " + modelData.text; Layout.fillWidth: true }
                        }
                        LabelText { visible: modelData.state === "completed" && !(modelData.notes || []).length; text: Style.tr("本批未提炼出笔记，原文见上方。"); Layout.fillWidth: true; color: Style.muted }
                        AppButton { text: Style.tr("放下本批旁听"); enabled: !bridge.busy && modelData.state !== "withdrawn"; onClicked: bridge.withdrawObservation(modelData.id) }
                    }
                }
            }
        }
    }
}
