import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "lifeStoryDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(860, parent ? parent.width - 32 : 860)
    height: Math.min(840, parent ? parent.height - 32 : 840)
    modal: true
    closePolicy: Popup.NoAutoClose
    title: Style.tr("人生回顾")
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("人生回顾"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    readonly property var recordsData: bridge.lifeStory
    readonly property var timeData: recordsData.time || ({})
    property string editing: ""
    property var target: ({})
    property var selectedAnchors: []
    function refresh(offset, sourceOffset) { bridge.loadLifeStory(search.text.trim(), offset || 0, sourceOffset || 0, history.checked) }
    function start(action, record) {
        target = record || ({}); editing = action
        var data = target.data || ({})
        kindChoice.currentIndex = target.kind === "turning_point" ? 1 : 0
        statusChoice.currentIndex = data.status === "closed" ? 1 : 0
        titleField.text = data.title || ""; interpretation.text = data.interpretation || ""
        change.text = data.change || ""; question.text = data.question || ""; reason.text = ""
        selectedAnchors = JSON.parse(JSON.stringify(target.anchors || []))
    }
    function containsSource(identifier) { return selectedAnchors.some(function(a) { return a.id === identifier }) }
    function addSource(source) { selectedAnchors = selectedAnchors.concat([JSON.parse(JSON.stringify(source))]) }
    function removeSource(index) { var next = selectedAnchors.slice(); next.splice(index, 1); selectedAnchors = next }
    function save() {
        var data = {target: target.key || "", expected: target.id || "", reason: reason.text.trim()}
        if (editing === "save") {
            data.kind = kindChoice.currentIndex === 1 ? "turning_point" : "chapter"
            data.status = statusChoice.currentIndex === 1 ? "closed" : "open"
            data.title = titleField.text.trim(); data.interpretation = interpretation.text.trim()
            data.change = change.text.trim(); data.question = question.text.trim()
            data.anchors = selectedAnchors.map(function(a) { return {id: a.id, hash: a.hash, quote: a.quote.trim()} })
        }
        bridge.saveLifeStory(editing, data)
    }
    onOpened: { editing = ""; refresh(0, 0) }
    Connections { target: bridge; function onLifeStorySaved() { dialog.editing = ""; dialog.selectedAnchors = [] } }
    contentItem: ScrollPane {
        id: scroll
        ColumnLayout {
            width: scroll.availableWidth; spacing: 14
            LabelText { text: bridge.notice; color: bridge.error ? Style.danger : Style.muted; Layout.fillWidth: true }
            LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); Layout.fillWidth: true }
            LabelText { text: Style.tr("从原文理解人生阶段与转折，保留尚未解开的问题。用户整理与模型解释分别标明，理解可以随着新经历改变。"); Layout.fillWidth: true; color: Style.muted }
            Panel {
                Layout.fillWidth: true; caption: Style.tr("时间与记录")
                LabelText { objectName: "storyPageCount"; text: Style.tr("已有日页：{count}", {count: dialog.timeData.recorded_pages || 0}); Layout.fillWidth: true }
                LabelText { objectName: "storyCalendarDays"; text: Style.tr("距出生日期的日历天数：{count}", {count: dialog.timeData.calendar_days_since_birth === null || dialog.timeData.calendar_days_since_birth === undefined ? Style.tr("未知") : dialog.timeData.calendar_days_since_birth}); Layout.fillWidth: true }
                LabelText { text: Style.tr("日页数不代表年龄或成熟度。没有日页的空档，期间经历未知。"); Layout.fillWidth: true; color: Style.muted }
                LabelText { text: Style.tr("日页日期之间未记录：{count} 天", {count: dialog.timeData.unrecorded_calendar_days_between_pages || 0}); Layout.fillWidth: true }
                Repeater {
                    model: dialog.timeData.unrecorded_intervals || []
                    LabelText { required property var modelData; text: modelData.from + " — " + modelData.through; Layout.fillWidth: true; color: Style.muted }
                }
                LabelText { visible: (dialog.timeData.future_dated_pages || 0) > 0; text: Style.tr("档案中有晚于当前日期的日页；保留原记录，暂不据此计算人生阶段。"); Layout.fillWidth: true; color: Style.muted }
            }
            ColumnLayout {
                visible: dialog.editing === ""; Layout.fillWidth: true; spacing: 12
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { objectName: "newLifeStory"; text: Style.tr("整理一段经历"); enabled: !bridge.busy; onClicked: dialog.start("save", null) }
                    AppButton { text: Style.tr("导出私人回顾"); enabled: !bridge.busy; onClicked: bridge.exportLifeStory() }
                }
                ToggleRow { id: history; text: Style.tr("包含回顾的旧版本"); enabled: !bridge.busy; onToggled: dialog.refresh(0, 0) }
                Repeater {
                    model: dialog.recordsData.pending || []
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        LabelText { text: modelData.payload.data.title || modelData.payload.data.reason; Layout.fillWidth: true }
                        AppButton { text: Style.tr("继续保存未完成的回顾"); enabled: !bridge.busy; onClicked: bridge.resumeLifeStory(modelData.id) }
                    }
                }
                LabelText { visible: (dialog.recordsData.total || 0) === 0; text: Style.tr("还没有符合条件的人生回顾。可以选择真实记录开始整理。"); Layout.fillWidth: true; color: Style.muted }
                Repeater {
                    model: dialog.recordsData.records || []
                    Panel {
                        id: recordPanel
                        required property var modelData
                        Layout.fillWidth: true
                        caption: modelData.data.title || Style.tr("已放下的解释")
                        detail: Style.tr(modelData.origin === "user" ? "用户整理" : "模型解释") + " · " + Style.tr(modelData.current ? "最新版本" : "历史解释") + " · " + Style.tr(modelData.availability === "available" ? "依据可用" : modelData.availability === "set_aside" ? "已放下的解释" : "依据需要重新核对")
                        LabelText { visible: !!modelData.data.status; text: Style.tr(modelData.data.status === "closed" ? "已告一段落" : "仍在经历"); Layout.fillWidth: true }
                        LabelText { visible: !!modelData.data.from_day; text: Style.tr("依据跨度：第 {first} 至 {last} 页", {first: modelData.data.from_day || 0, last: modelData.data.through_day || 0}); Layout.fillWidth: true; color: Style.muted }
                        LabelText { text: modelData.data.interpretation || ""; Layout.fillWidth: true }
                        LabelText { visible: !!modelData.data.change; text: Style.tr("理解的变化") + "\n" + (modelData.data.change || ""); Layout.fillWidth: true }
                        LabelText { visible: !!modelData.data.question; text: Style.tr("仍未解开的问题") + "\n" + (modelData.data.question || ""); Layout.fillWidth: true }
                        LabelText { text: modelData.at + "\n" + modelData.reason; Layout.fillWidth: true; color: Style.muted }
                        Repeater {
                            model: recordPanel.modelData.anchors || []
                            LabelText { required property var modelData; text: modelData.basis + "\n“" + modelData.quote + "”\n" + modelData.source; Layout.fillWidth: true; color: Style.muted }
                        }
                        Flow {
                            visible: recordPanel.modelData.current && recordPanel.modelData.kind !== "forget"
                            Layout.fillWidth: true; spacing: 8
                            AppButton { text: Style.tr("重新理解这段经历"); enabled: !bridge.busy; onClicked: dialog.start("save", recordPanel.modelData) }
                            AppButton { text: Style.tr("放下这条解释"); enabled: !bridge.busy; onClicked: dialog.start("forget", recordPanel.modelData) }
                        }
                    }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("上一页回顾"); enabled: !bridge.busy && dialog.recordsData.offset > 0; onClicked: dialog.refresh(Math.max(0, dialog.recordsData.offset - 30), dialog.recordsData.source_offset) }
                    AppButton { text: Style.tr("下一页回顾"); enabled: !bridge.busy && dialog.recordsData.offset + 30 < dialog.recordsData.total; onClicked: dialog.refresh(dialog.recordsData.offset + 30, dialog.recordsData.source_offset) }
                }
            }
            ColumnLayout {
                visible: dialog.editing !== ""; Layout.fillWidth: true; spacing: 12
                ColumnLayout {
                    visible: dialog.editing === "save"; enabled: !bridge.busy; Layout.fillWidth: true; spacing: 12
                    LabelText { text: Style.tr("回顾种类"); Layout.fillWidth: true }
                    Choice { id: kindChoice; Accessible.name: Style.tr("回顾种类"); model: [Style.tr("人生章节"), Style.tr("转折点")]; enabled: !dialog.target.key; Layout.fillWidth: true }
                    LabelText { text: Style.tr("当前状态"); Layout.fillWidth: true }
                    Choice { id: statusChoice; Accessible.name: Style.tr("当前状态"); model: [Style.tr("仍在经历"), Style.tr("已告一段落")]; Layout.fillWidth: true }
                    Field { id: titleField; objectName: "storyTitle"; caption: Style.tr("标题"); Layout.fillWidth: true }
                    LongField { id: interpretation; objectName: "storyInterpretation"; caption: Style.tr("我对这段经历的理解"); Layout.fillWidth: true }
                    LongField { id: change; caption: Style.tr("理解的变化"); Layout.fillWidth: true }
                    LongField { id: question; caption: Style.tr("仍未解开的问题"); Layout.fillWidth: true }
                    LabelText { text: Style.tr("选择 1 至 8 段原文。引文须逐字对应；依据变化后，请移除旧依据并重新选择。"); Layout.fillWidth: true; color: Style.muted }
                    Repeater {
                        model: dialog.selectedAnchors
                        ColumnLayout {
                            id: selected
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            LabelText { text: modelData.basis + "\n" + modelData.source; Layout.fillWidth: true; color: Style.muted }
                            LongField {
                                caption: Style.tr("逐字引文"); text: selected.modelData.quote; Layout.fillWidth: true
                                input.onTextChanged: { if (dialog.selectedAnchors[selected.index]) dialog.selectedAnchors[selected.index].quote = text }
                            }
                            AppButton { text: Style.tr("移除这段依据"); onClicked: dialog.removeSource(selected.index) }
                        }
                    }
                }
                LabelText { visible: dialog.editing === "forget"; text: Style.tr("放下这条解释及其旧版本，原始经历仍然保留。"); Layout.fillWidth: true }
                LongField { id: reason; objectName: "storyReason"; caption: Style.tr("整理或修订说明"); enabled: !bridge.busy; Layout.fillWidth: true }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { objectName: "saveLifeStory"; text: Style.tr("保存"); enabled: !bridge.busy && reason.text.trim() !== "" && (dialog.editing === "forget" || (titleField.text.trim() !== "" && interpretation.text.trim() !== "" && dialog.selectedAnchors.length > 0)); onClicked: dialog.save() }
                    AppButton { text: Style.tr("取消"); enabled: !bridge.busy; onClicked: dialog.editing = "" }
                }
            }
            Field { id: search; caption: Style.tr("搜索回顾与原文"); enabled: !bridge.busy; Layout.fillWidth: true; input.onAccepted: dialog.refresh(0, 0) }
            AppButton { text: Style.tr("搜索"); enabled: !bridge.busy; onClicked: dialog.refresh(0, 0) }
            ColumnLayout {
                visible: dialog.editing === "save"; Layout.fillWidth: true; spacing: 12
                Repeater {
                    model: dialog.recordsData.sources || []
                    Panel {
                        required property var modelData
                        Layout.fillWidth: true; caption: modelData.basis
                        LabelText { text: modelData.text; Layout.fillWidth: true }
                        LabelText { text: modelData.source; Layout.fillWidth: true; color: Style.muted }
                        AppButton { text: Style.tr("选择这段依据"); enabled: !bridge.busy && dialog.selectedAnchors.length < 8 && !dialog.containsSource(modelData.id); onClicked: dialog.addSource(modelData) }
                    }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { text: Style.tr("上一页原文"); enabled: !bridge.busy && dialog.recordsData.source_offset > 0; onClicked: dialog.refresh(dialog.recordsData.offset, Math.max(0, dialog.recordsData.source_offset - 30)) }
                    AppButton { text: Style.tr("下一页原文"); enabled: !bridge.busy && dialog.recordsData.source_offset + 30 < dialog.recordsData.source_total; onClicked: dialog.refresh(dialog.recordsData.offset, dialog.recordsData.source_offset + 30) }
                }
            }
            AppButton { text: Style.tr("关闭"); enabled: !bridge.busy; onClicked: dialog.close() }
        }
    }
}
