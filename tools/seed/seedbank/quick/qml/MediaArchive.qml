import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "mediaArchiveDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(840, parent ? parent.width - 32 : 840)
    height: Math.min(800, parent ? parent.height - 32 : 800)
    modal: true
    closePolicy: Popup.NoAutoClose
    title: Style.tr("原始图片与声音")
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("原始图片与声音"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    readonly property var recordsData: bridge.mediaArchive
    readonly property var selected: bridge.mediaDetail
    readonly property var processing: selected.processing || ({})
    readonly property var visionState: processing.vision || ({})
    property bool showingDetail: false
    function refresh(offset) { bridge.loadMedia(search.text.trim(), offset || 0) }
    function stateLabel(value) {
        return Style.tr(value === "available" ? "原件可用" : value === "forgotten" || value === "withheld" ? "已退出回忆" :
                        value === "missing" ? "原件缺失" : value === "changed" ? "原件内容已变" : "原件当前不可用")
    }
    function processingLabel(value) {
        return Style.tr(value === "pending" ? "已接收，尚未处理完成" : value === "complete" ? "处理已完成" :
                        value === "cancelled" ? "原件保留，处理已停止" : value === "unavailable" ? "处理记录不可用，原件仍可查看" : "历史接收记录")
    }
    onOpened: { showingDetail = false; refresh(0) }
    Connections { target: bridge; function onMediaSaved() { reason.text = ""; note.text = "" } }
    contentItem: ScrollPane {
        ColumnLayout {
            width: parent.width; spacing: 14
            LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
            LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); Layout.fillWidth: true }
            LabelText { text: Style.tr("从现在起保存收到的原件。过去未保存的文件无法恢复；接收时间不等于拍摄或录制时间。"); color: Style.muted; Layout.fillWidth: true }
            LabelText { text: Style.tr("接收成功后原件会先保留。继续处理可能调用视觉模型；只保留原件不会开始分析。"); color: Style.muted; Layout.fillWidth: true }
            ColumnLayout {
                visible: !dialog.showingDetail; Layout.fillWidth: true
                Field { id: search; objectName: "mediaSearch"; caption: Style.tr("搜索文件名或接收日期"); Layout.fillWidth: true; input.onAccepted: dialog.refresh(0) }
                AppButton { text: Style.tr("搜索"); enabled: !bridge.busy; onClicked: dialog.refresh(0) }
                Repeater {
                    model: dialog.recordsData.pending || []
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: modelData.payload.kind === "media_intake" ? modelData.id : modelData.payload.data.asset_id; color: Style.muted; Layout.fillWidth: true }
                        AppButton { text: Style.tr("继续未完成的材料操作"); enabled: !bridge.busy; onClicked: bridge.resumeMedia(modelData.id) }
                        AppButton { visible: modelData.payload.kind === "media_intake"; text: Style.tr("只保留原件，停止处理"); enabled: !bridge.busy; onClicked: bridge.processMediaInput(modelData.id, true) }
                    }
                }
                LabelText { visible: (dialog.recordsData.total || 0) === 0; text: Style.tr("还没有保存的原始材料。"); Layout.fillWidth: true }
                Repeater {
                    model: dialog.recordsData.records || []
                    Panel {
                        required property var modelData
                        Layout.fillWidth: true; caption: dialog.stateLabel(modelData.state)
                        LabelText { text: modelData.name; Layout.fillWidth: true }
                        LabelText { text: modelData.at + " · " + (modelData.bytes / 1048576).toFixed(2) + " MiB"; color: Style.muted; Layout.fillWidth: true }
                        LabelText { text: dialog.processingLabel((modelData.processing || {}).state); color: Style.muted; Layout.fillWidth: true }
                        AppButton { text: Style.tr("查看材料与解释"); enabled: !bridge.busy; onClicked: {
                            if (bridge.loadMediaDetail(modelData.id)) { dialog.showingDetail = true; reason.text = ""; note.text = "" }
                        } }
                    }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("上一页"); enabled: !bridge.busy && dialog.recordsData.offset > 0; onClicked: dialog.refresh(Math.max(0, dialog.recordsData.offset - 30)) }
                    AppButton { text: Style.tr("下一页"); enabled: !bridge.busy && dialog.recordsData.offset + 30 < dialog.recordsData.total; onClicked: dialog.refresh(dialog.recordsData.offset + 30) }
                }
            }
            ColumnLayout {
                visible: dialog.showingDetail; Layout.fillWidth: true
                AppButton { text: Style.tr("返回列表"); enabled: !bridge.busy; onClicked: { dialog.showingDetail = false; dialog.refresh(dialog.recordsData.offset) } }
                LabelText { text: dialog.selected.name || ""; font.weight: Font.DemiBold; Layout.fillWidth: true }
                LabelText { text: dialog.stateLabel(dialog.selected.state); Layout.fillWidth: true }
                LabelText { objectName: "mediaProcessingState"; text: dialog.processingLabel((dialog.selected.processing || {}).state); color: Style.muted; Layout.fillWidth: true }
                LabelText { visible: !!dialog.visionState.attempted && dialog.visionState.ok === false; text: Style.tr("原件和本地分析已保存，本次没有获得视觉解释。"); color: Style.muted; Layout.fillWidth: true }
                Flow {
                    visible: (dialog.selected.processing || {}).state === "pending"; Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("继续上次材料处理"); enabled: !bridge.busy; onClicked: bridge.processMediaInput(dialog.selected.processing.request_id, false) }
                    AppButton { text: Style.tr("只保留原件，停止处理"); enabled: !bridge.busy; onClicked: bridge.processMediaInput(dialog.selected.processing.request_id, true) }
                }
                LabelText { text: (dialog.selected.at || "") + "\n" + (dialog.selected.audience_id || ""); color: Style.muted; Layout.fillWidth: true }
                LabelText { text: Style.tr("打开的是新导出的副本，不修改生命包中的原件。副本包含原文件的信息，请自行决定是否分享。"); Layout.fillWidth: true; color: Style.muted }
                AppButton { objectName: "openMediaCopy"; text: Style.tr("打开原件副本"); enabled: !bridge.busy && ["available", "forgotten", "withheld"].indexOf(dialog.selected.state) >= 0; onClicked: bridge.openMediaCopy(dialog.selected.id) }
                Repeater {
                    model: dialog.selected.events || []
                    Panel {
                        required property var modelData
                        Layout.fillWidth: true; caption: modelData.at
                        LabelText { text: modelData.text; Layout.fillWidth: true }
                        LabelText { visible: !!modelData.metadata.reason; text: modelData.metadata.reason || ""; color: Style.muted; Layout.fillWidth: true }
                        LabelText { visible: !modelData.recallable; text: Style.tr("仅供查看，不进入当前回忆。"); color: Style.muted; Layout.fillWidth: true }
                    }
                }
                ColumnLayout {
                    visible: dialog.selected.state === "available" && dialog.selected.media_kind === "image" && (dialog.selected.processing || {}).state !== "pending"; Layout.fillWidth: true
                    LabelText { text: Style.tr("本机重新理解的说明与新解释保持私人，不自动提供给原来的群聊或交流对象。"); color: Style.muted; Layout.fillWidth: true }
                    LabelText { text: Style.tr("重新理解会把原图和本次说明发送给配置的视觉模型，可能产生费用。旧解释保留，不把旧图记成今天新发生的事。"); Layout.fillWidth: true }
                    LongField { id: note; objectName: "mediaReviewNote"; caption: Style.tr("本次想重新理解什么（可留空）"); Layout.fillWidth: true }
                    AppButton { objectName: "revisitMedia"; text: Style.tr("重新理解图片（调用模型）"); enabled: !bridge.busy && note.text.length <= 2000; onClicked: bridge.saveMedia("revisit", {asset_id: dialog.selected.id, note: note.text}) }
                }
                ColumnLayout {
                    visible: !!dialog.selected.id && !dialog.selected.forgotten; Layout.fillWidth: true
                    LabelText { text: Style.tr("放下会停止使用这次接收的材料及关联解释；原件仍保留，其他独立接收不受影响。"); Layout.fillWidth: true }
                    LongField { id: reason; objectName: "mediaForgetReason"; caption: Style.tr("放下的理由"); Layout.fillWidth: true }
                    AppButton { objectName: "forgetMedia"; text: Style.tr("放下这份材料"); danger: true; enabled: !bridge.busy && reason.text.trim().length > 0 && reason.text.length <= 1000; onClicked: bridge.saveMedia("forget", {asset_id: dialog.selected.id, reason: reason.text}) }
                }
            }
        }
    }
    footer: DialogButtonBox {
        background: Item {}
        AppButton { text: Style.tr("关闭"); enabled: !bridge.busy; onClicked: dialog.close() }
    }
}
