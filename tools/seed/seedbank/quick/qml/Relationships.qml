import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "relationshipsDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(860, parent ? parent.width - 32 : 860)
    height: Math.min(820, parent ? parent.height - 32 : 820)
    modal: true
    closePolicy: Popup.NoAutoClose
    readonly property var recordsData: bridge.relationships
    readonly property var relation: recordsData.context || ({})
    property string editing: ""
    property var target: ({})
    property string editPerson: "owner"
    property string expected: ""
    property var chosen: ({})
    property var chosenLabels: ({})
    readonly property var completionItems: bridge.learning.criteria && bridge.learning.criteria.id && bridge.learning.criteria.id === (target.data || {}).criteria_id ? ((bridge.learning.criteria.data || {}).items || []) : []
    readonly property var groupNames: completionItems.map(function(r) { return r.group }).filter(function(v, i, all) { return all.indexOf(v) === i })
    readonly property var noteKinds: [{id: "reflection", label: Style.tr("相处理解")}, {id: "appreciation", label: Style.tr("感谢与欣赏")}, {id: "tension", label: Style.tr("感到有分歧")}]
    readonly property var issueStates: [{id: "open", label: Style.tr("尚待处理")}, {id: "trying", label: Style.tr("正在尝试修复")}, {id: "resolved", label: Style.tr("用户记录已缓和")}, {id: "set_aside", label: Style.tr("暂时搁置这件事")}]
    readonly property var reviewStates: [{id: "fulfilled", label: Style.tr("核对约定条件")}, {id: "unfulfilled", label: Style.tr("记录未履行")}, {id: "withdrawn", label: Style.tr("撤回并说明理由")}]
    function refresh(offset) { bridge.loadRelationships(recordsData.person_id || "owner", offset || 0, history.checked) }
    function start(action, record) {
        editing = action; target = record || ({}); editPerson = recordsData.person_id || "owner"
        expected = record ? record.id : action === "boundary" ? (recordsData.boundary_expected || "") : ""
        reason.text = ""; content.text = record ? (record.data.text || record.data.title || "") : ""
        personName.text = ""; dueDay.text = ""; chosen = ({}); chosenLabels = ({})
        noteKind.currentIndex = record && record.kind === "note" ? noteKind.indexOfValue(record.data.type) : 0
        issueState.currentIndex = record && record.kind === "issue" ? issueState.indexOfValue(record.data.status) : 0
        proactive.currentIndex = relation.proactive === "paused" ? 1 : 0
        reviewState.currentIndex = 0
        goal.currentIndex = -1
        if (action === "review") bridge.loadLearning(record.data.goal_id, 0)
    }
    function save() {
        var data = {person_id: editPerson, target: target.key || "", expected: expected, reason: reason.text.trim()}
        if (editing === "person") data = {label: personName.text.trim()}
        else if (editing === "note") { data.type = noteKind.currentValue; data.text = content.text.trim() }
        else if (editing === "issue") { data.title = content.text.trim(); data.status = issueState.currentValue }
        else if (editing === "boundary") data.proactive = proactive.currentIndex ? "paused" : "allowed"
        else if (editing === "agreement") {
            var selected = (recordsData.goals || [])[goal.currentIndex] || ({})
            data.goal_id = selected.id || ""; data.criteria_id = selected.criteria_id || ""
            data.due_on = dueDay.text.trim() || null
        } else if (editing === "review") {
            data.status = reviewState.currentValue; data.completion_evidence = ({})
            completionItems.forEach(function(r) { data.completion_evidence[r.id] = chosen[r.group] || "" })
        }
        bridge.saveRelationship(editing, data)
    }
    function label(row) {
        if (row.kind === "note") return Style.tr("相处理解")
        if (row.kind === "issue") return issueStates.filter(function(r) { return r.id === row.data.status })[0].label
        if (row.kind === "boundary") return Style.tr(row.data.proactive === "paused" ? "暂停自主开口" : "允许自主开口")
        if (row.kind === "forget") return Style.tr("已放下的记录")
        var state = (row.assessment || {}).state
        return Style.tr(state === "criteria_met" ? "约定条件已核对" : state === "due_for_review" ? "已过期限，等待核对" : state === "conditions_changed" ? "约定条件已变化，需重新协商" : state === "needs_review" ? "当前依据不足，需重新核对" : row.data.status === "unfulfilled" ? "用户记录未履行" : row.data.status === "withdrawn" ? "已记录撤回" : row.data.status === "fulfilled" ? "历史记录曾核对履行" : "约定仍待履行")
    }
    onOpened: { editing = ""; bridge.loadRelationships("owner", 0, history.checked) }
    Connections { target: bridge; function onRelationshipSaved() { dialog.editing = "" } }
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("相处与约定"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        spacing: 10
        LabelText { text: Style.tr("这里记录相处的依据和后续。用户的记录与模型的理解，都不代表第三方已经确认或原谅。"); color: Style.muted; Layout.fillWidth: true }
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); Layout.fillWidth: true }
        ScrollView {
            id: scroll; clip: true; contentWidth: availableWidth; Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                width: scroll.availableWidth; spacing: 14
                ColumnLayout {
                    visible: dialog.editing === ""; Layout.fillWidth: true
                    Choice {
                        objectName: "relationshipPerson"; Layout.fillWidth: true; enabled: !bridge.busy
                        model: (dialog.recordsData.people || []).map(function(r, i, all) { return {id: r.id, label: r.label + (all.filter(function(p) { return p.label === r.label }).length > 1 ? " · " + r.id.slice(-6) : "")} })
                        textRole: "label"; valueRole: "id"
                        currentIndex: (dialog.recordsData.people || []).map(function(r) { return r.id }).indexOf(dialog.recordsData.person_id)
                        onActivated: bridge.loadRelationships(currentValue, 0, history.checked)
                    }
                    LabelText { text: Style.tr("有身份关联的交流：{count} 次；次数不代表信任或亲密。").replace("{count}", String(dialog.relation.interaction_count || 0)); Layout.fillWidth: true }
                    LabelText { text: Style.tr(dialog.relation.proactive === "paused" ? "暂停自主开口" : "允许自主开口"); Layout.fillWidth: true }
                    Flow {
                        Layout.fillWidth: true; spacing: 8
                        AppButton { text: Style.tr("登记人物"); enabled: !bridge.busy; onClicked: dialog.start("person", null) }
                        AppButton { objectName: "addRelationshipNote"; text: Style.tr("记一次相处"); enabled: !bridge.busy; onClicked: dialog.start("note", null) }
                        AppButton { text: Style.tr("记录待处理的事情"); enabled: !bridge.busy; onClicked: dialog.start("issue", null) }
                        AppButton { text: Style.tr("记录一项约定"); enabled: !bridge.busy; onClicked: dialog.start("agreement", null) }
                        AppButton { objectName: "editContactBoundary"; text: Style.tr("自主开口设置"); enabled: !bridge.busy; onClicked: dialog.start("boundary", null) }
                    }
                    ToggleRow { id: history; text: Style.tr("查看原始历史（含已放下）"); enabled: !bridge.busy; onToggled: dialog.refresh(0) }
                    Repeater {
                        model: dialog.recordsData.pending || []
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            LabelText { text: modelData.payload.data.reason || modelData.payload.data.label || ""; Layout.fillWidth: true }
                            AppButton { text: Style.tr("恢复未完成的关系记录"); enabled: !bridge.busy; onClicked: bridge.resumeRelationship(modelData.id) }
                        }
                    }
                    Repeater {
                        model: dialog.recordsData.records || []
                        Panel {
                            required property var modelData
                            Layout.fillWidth: true; caption: dialog.label(modelData)
                            LabelText { text: modelData.data.title || modelData.data.text || ""; Layout.fillWidth: true }
                            LabelText { text: modelData.data.reason; Layout.fillWidth: true }
                            LabelText { visible: !!modelData.data.due_on; text: Style.tr("约定日期") + " · " + (modelData.data.due_on || ""); Layout.fillWidth: true }
                            LabelText { visible: modelData.data.due_day !== undefined && modelData.data.due_day !== null; text: Style.tr("旧日页第 {number} 页").replace("{number}", String(modelData.data.due_day)); Layout.fillWidth: true }
                            LabelText { visible: (modelData.assessment || {}).state === "deadline_unknown"; text: Style.tr("当前日页日期不足以判断期限。"); Layout.fillWidth: true; color: Style.muted }
                            LabelText { text: Style.tr(modelData.origin === "model" ? "模型的理解，尚未核实" : "用户记录的情况") + "\n" + modelData.at + "\n" + modelData.source; color: Style.muted; Layout.fillWidth: true }
                            LabelText { visible: !modelData.current; text: Style.tr("历史版本或依据已退出当前回忆"); color: Style.muted; Layout.fillWidth: true }
                            Flow {
                                visible: modelData.current; Layout.fillWidth: true; spacing: 8
                                AppButton { visible: modelData.kind === "note" || modelData.kind === "issue"; text: Style.tr("补充或修正后续"); enabled: !bridge.busy; onClicked: dialog.start(modelData.kind, modelData) }
                                AppButton { visible: modelData.kind === "agreement"; text: Style.tr("核对或修正约定结果"); enabled: !bridge.busy; onClicked: dialog.start("review", modelData) }
                                AppButton { visible: modelData.kind !== "boundary"; text: Style.tr("放下这条记录"); enabled: !bridge.busy; onClicked: dialog.start("forget", modelData) }
                            }
                        }
                    }
                    RowLayout {
                        AppButton { text: Style.tr("上一页"); enabled: !bridge.busy && dialog.recordsData.offset > 0; onClicked: dialog.refresh(Math.max(0, dialog.recordsData.offset - 30)) }
                        AppButton { text: Style.tr("下一页"); enabled: !bridge.busy && dialog.recordsData.offset + 30 < dialog.recordsData.total; onClicked: dialog.refresh(dialog.recordsData.offset + 30) }
                        AppButton { text: Style.tr("刷新"); enabled: !bridge.busy; onClicked: dialog.refresh(dialog.recordsData.offset) }
                    }
                }
                ColumnLayout {
                    visible: dialog.editing !== ""; Layout.fillWidth: true; enabled: !bridge.busy
                    Field { id: personName; objectName: "relationshipPersonName"; visible: dialog.editing === "person"; caption: Style.tr("人物名称或身份说明（最多 80 字）"); Layout.fillWidth: true; input.maximumLength: 80 }
                    Choice { id: noteKind; visible: dialog.editing === "note"; model: dialog.noteKinds; textRole: "label"; valueRole: "id"; Layout.fillWidth: true }
                    Field { id: content; objectName: "relationshipContent"; visible: dialog.editing === "note" || dialog.editing === "issue"; caption: Style.tr("具体发生了什么？"); Layout.fillWidth: true; input.maximumLength: dialog.editing === "issue" ? 160 : 500 }
                    Choice { id: issueState; visible: dialog.editing === "issue" && !!dialog.target.id; model: dialog.issueStates; textRole: "label"; valueRole: "id"; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "issue"; text: Style.tr("说明尝试了什么，以及收到什么反馈。一次道歉不会自动代表关系已修复。"); color: Style.muted; Layout.fillWidth: true }
                    Choice { id: proactive; objectName: "relationshipProactive"; visible: dialog.editing === "boundary"; model: [Style.tr("允许自主开口"), Style.tr("暂停自主开口")]; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "boundary"; text: Style.tr("暂停自主开口仍允许你直接对话。已经设置的提醒另行管理；目前自动开口仅面向用户渠道。"); color: Style.muted; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "agreement"; text: Style.tr("选择已有完成条件的目标作为约定。你记录的是本地约定，并不验证另一方的同意。"); Layout.fillWidth: true }
                    Choice { id: goal; objectName: "relationshipGoal"; visible: dialog.editing === "agreement"; model: dialog.recordsData.goals || []; textRole: "title"; valueRole: "id"; currentIndex: -1; Layout.fillWidth: true }
                    Field { id: dueDay; objectName: "agreementDate"; visible: dialog.editing === "agreement"; caption: Style.tr("约定日期（YYYY-MM-DD，可留空）"); Layout.fillWidth: true; input.maximumLength: 10 }
                    Choice { id: reviewState; visible: dialog.editing === "review"; model: dialog.reviewStates; textRole: "label"; valueRole: "id"; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "review"; text: Style.tr("成果与逐项反馈在“练习与反馈”中记录。条件变化后应重新协商，不能沿用旧约定宣布履行。"); Layout.fillWidth: true }
                    Repeater {
                        model: dialog.editing === "review" && reviewState.currentValue === "fulfilled" ? dialog.groupNames : []
                        ColumnLayout {
                            required property string modelData
                            Layout.fillWidth: true
                            LabelText { text: modelData; Layout.fillWidth: true }
                            Choice {
                                Layout.fillWidth: true; textRole: "label"; valueRole: "id"; currentIndex: -1
                                model: (bridge.learning.attempts || []).map(function(r, i) { return {id: r.id, label: String(bridge.learning.total - bridge.learning.offset - i) + " · " + (r.artifact_view.title || r.detail || r.action)} })
                                onActivated: { var values = Object.assign({}, dialog.chosen); values[modelData] = currentValue; dialog.chosen = values; var labels = Object.assign({}, dialog.chosenLabels); labels[modelData] = currentText; dialog.chosenLabels = labels }
                            }
                            LabelText { text: dialog.chosenLabels[modelData] || ""; color: Style.muted; Layout.fillWidth: true }
                        }
                    }
                    RowLayout {
                        visible: dialog.editing === "review" && reviewState.currentValue === "fulfilled"
                        AppButton { text: Style.tr("上一页成果"); enabled: bridge.learning.offset > 0; onClicked: bridge.loadLearning(dialog.target.data.goal_id, Math.max(0, bridge.learning.offset - 30)) }
                        AppButton { text: Style.tr("下一页成果"); enabled: bridge.learning.offset + 30 < bridge.learning.total; onClicked: bridge.loadLearning(dialog.target.data.goal_id, bridge.learning.offset + 30) }
                    }
                    LabelText { visible: dialog.editing === "forget"; text: Style.tr("停止回忆这条记录及依赖它的理解；原文与历史保留。自主开口设置不会因此改变。"); color: Style.muted; Layout.fillWidth: true }
                    Field { id: reason; objectName: "relationshipReason"; visible: dialog.editing !== "person"; caption: Style.tr("依据或说明"); Layout.fillWidth: true; input.maximumLength: 600 }
                }
            }
        }
    }
    footer: Item {
        implicitHeight: 72 * Style.scale
        RowLayout {
            anchors.fill: parent; anchors.margins: 16
            AppButton { text: Style.tr(dialog.editing ? "取消编辑" : "关闭"); enabled: !bridge.busy; onClicked: { if (dialog.editing) dialog.editing = ""; else dialog.close() } }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "saveRelationship"; visible: !!dialog.editing; text: Style.tr("保存"); primary: true; enabled: !bridge.busy; onClicked: dialog.save() }
        }
    }
}
