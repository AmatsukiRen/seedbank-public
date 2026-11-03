import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "factsDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(840, parent ? parent.width - 32 : 840)
    height: Math.min(780, parent ? parent.height - 32 : 780)
    modal: true
    closePolicy: Popup.NoAutoClose
    property string editing: ""
    property var target: ({})
    property string chosen: ""
    property string retractHash: ""
    property var retractPreview: ({})
    property string changeType: "correction"
    readonly property var recordsData: bridge.facts
    function refresh(offset) { bridge.loadFacts(search.text, history.checked, offset || 0) }
    function start(action, group, claim) {
        editing = action; target = group || ({}); chosen = action === "retract" ? claim.id : claim || ""
        retractHash = action === "retract" ? claim.target_hash : ""
        retractPreview = action === "retract" ? claim : ({})
        changeType = "correction"; reason.text = ""; effective.text = ""; startsOn.text = ""
        aspect.text = group ? group.aspect : ""; value.text = ""; entityName.text = ""
        if (group) subject.currentIndex = subject.indexOfValue(group.subject)
    }
    function restore(payload, preview) {
        var saved = payload.data
        start(payload.action, null, payload.action === "retract" ? { id: saved.target, target_hash: saved.target_hash } : saved.selected || "")
        if (payload.action === "retract") retractPreview = preview || ({})
        target = { id: saved.slot || "", expected: saved.expected || [] }
        subject.currentIndex = subject.indexOfValue(saved.subject || "owner")
        aspect.text = saved.aspect || ""; value.text = saved.value || ""; entityName.text = saved.label || ""
        reason.text = saved.reason || ""; effective.text = saved.effective_on || ""
        startsOn.text = saved.starts_on || ""
        changeType = saved.change_type || "correction"
    }
    function save() {
        var payload
        if (editing === "entity") payload = { label: entityName.text.trim() }
        else if (editing === "add") {
            payload = { subject: subject.currentValue, aspect: aspect.text.trim(), value: value.text.trim() }
            if (startsOn.text.trim()) payload.starts_on = startsOn.text.trim()
        }
        else {
            payload = { slot: target.id, expected: target.expected, reason: reason.text.trim() }
            if (editing === "resolve") {
                payload.selected = chosen; payload.change_type = changeType
                payload.effective_on = changeType === "change" ? effective.text.trim() : ""
            }
            if (editing === "retract") { payload.target = chosen; payload.target_hash = retractHash }
        }
        bridge.editFact(editing, payload)
    }
    onOpened: { editing = ""; refresh(0) }
    Connections { target: bridge; function onFactSaved() { dialog.editing = "" } }
    FactTime { id: timeView }
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("单项记录与分歧"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        spacing: 10
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); color: Style.muted; Layout.fillWidth: true }
        LabelText { text: Style.tr("这里保存有来源的说法，不代表已经客观核实。不同说法会等待你核对。"); color: Style.muted; Layout.fillWidth: true }
        ColumnLayout {
            visible: dialog.editing === ""; Layout.fillWidth: true
            RowLayout {
                Layout.fillWidth: true
                Field { id: search; objectName: "factsSearch"; Layout.fillWidth: true; caption: Style.tr("搜索人物、事项或说法"); input.onAccepted: dialog.refresh(0) }
                AppButton { text: Style.tr("搜索"); enabled: !bridge.busy; Layout.alignment: Qt.AlignBottom; onClicked: dialog.refresh(0) }
            }
            ToggleRow { id: history; text: Style.tr("查看全部历史与已放下的原文"); onToggled: dialog.refresh(0) }
            AppButton { objectName: "openFactTime"; text: Style.tr("按日期回查"); enabled: !bridge.busy; onClicked: timeView.open() }
            RowLayout {
                AppButton { objectName: "addFact"; text: Style.tr("补充一项说法"); enabled: !bridge.busy; onClicked: dialog.start("add", null, "") }
                AppButton { text: Style.tr("登记另一个人物"); enabled: !bridge.busy; onClicked: dialog.start("entity", null, "") }
            }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: dialog.editing === "" ? 0 : 1
            ScrollView {
                id: records; clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: records.availableWidth; spacing: 16
                    Repeater {
                        model: dialog.recordsData.pending || []
                        AppButton { required property var modelData; text: Style.tr("恢复未完成的单项操作"); enabled: !bridge.busy; onClicked: dialog.restore(modelData.payload, modelData.target_preview) }
                    }
                    LabelText { visible: (dialog.recordsData.groups || []).length === 0; text: Style.tr("还没有匹配的单项记录。原始对话与记忆仍保留。"); color: Style.muted; Layout.fillWidth: true }
                    Repeater {
                        model: dialog.recordsData.groups || []
                        ColumnLayout {
                            id: group
                            required property var modelData
                            Layout.fillWidth: true; spacing: 10
                            LabelText { text: (group.modelData.subject === "owner" ? Style.tr("用户") : group.modelData.label) + " · " + group.modelData.aspect; font.weight: Font.DemiBold; font.pixelSize: 18 * Style.scale; Layout.fillWidth: true }
                            LabelText { text: Style.tr(group.modelData.status === "conflict" ? "存在不同说法，尚未决定采用哪条" : group.modelData.status === "reported" ? "当前保留的说法，未独立核实" : "没有可用于当前回忆的说法"); color: group.modelData.status === "conflict" ? Style.danger : Style.muted; Layout.fillWidth: true }
                            Repeater {
                                model: history.checked ? group.modelData.history : group.modelData.claims
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 6
                                    LabelText { text: modelData.value; font.pixelSize: 17 * Style.scale; Layout.fillWidth: true }
                                    LabelText { text: Style.tr(modelData.origin === "user" ? "用户直接记录" : "模型从发言中提取，含义仍需核对") + " · " + modelData.at; color: Style.muted; Layout.fillWidth: true }
                                    LabelText { text: Style.tr("原文") + "：" + modelData.quote; Layout.fillWidth: true }
                                    LabelText { visible: !!modelData.starts_on; text: Style.tr("生效起日") + "：" + (modelData.starts_on || ""); color: Style.muted; Layout.fillWidth: true }
                                    LabelText { text: (modelData.evidence || []).map(function(r) { return r.source }).join("\n"); color: Style.muted; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true }
                                    LabelText { visible: !modelData.recallable; text: Style.tr(modelData.retracted ? "提取有误，已撤回" : modelData.unavailable ? "已放下或依据不可用" : modelData.change_type === "change" ? "后来改变" : "原来记错") + (modelData.effective_on ? " · " + modelData.effective_on : ""); color: Style.muted; Layout.fillWidth: true }
                                    AppButton { text: Style.tr("核对并采用这条"); visible: modelData.recallable && group.modelData.claims.length > 1; enabled: !bridge.busy; onClicked: dialog.start("resolve", group.modelData, modelData.id) }
                                    AppButton { text: Style.tr("这条提取有误"); visible: modelData.recallable && modelData.origin === "model"; enabled: !bridge.busy; onClicked: dialog.start("retract", group.modelData, modelData) }
                                    AppButton { text: Style.tr("日期说明与修订"); enabled: !bridge.busy; onClicked: timeView.openDate(modelData.id) }
                                }
                            }
                            Repeater {
                                model: history.checked ? group.modelData.decisions : []
                                LabelText { required property var modelData; text: Style.tr(modelData.change_type === "change" ? "后来改变" : "原来记错") + " · " + modelData.reason + (modelData.effective_on ? " · " + modelData.effective_on : ""); color: Style.muted; Layout.fillWidth: true }
                            }
                            Repeater {
                                model: history.checked ? group.modelData.retractions : []
                                LabelText { required property var modelData; text: Style.tr("提取撤回理由") + "：" + modelData.reason + " · " + modelData.at; color: Style.muted; Layout.fillWidth: true }
                            }
                            RowLayout {
                                AppButton { text: Style.tr("补充这项"); enabled: !bridge.busy; onClicked: dialog.start("add", group.modelData, "") }
                                AppButton { text: Style.tr("放下这项"); visible: group.modelData.claims.length > 0; danger: true; enabled: !bridge.busy; onClicked: dialog.start("forget", group.modelData, "") }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: Style.line }
                        }
                    }
                    RowLayout {
                        AppButton { text: Style.tr("上一页"); enabled: !bridge.busy && (dialog.recordsData.offset || 0) > 0; onClicked: dialog.refresh(Math.max(0, dialog.recordsData.offset - 30)) }
                        AppButton { text: Style.tr("下一页"); enabled: !bridge.busy && (dialog.recordsData.offset || 0) + 30 < (dialog.recordsData.total || 0); onClicked: dialog.refresh((dialog.recordsData.offset || 0) + 30) }
                    }
                }
            }
            ScrollView {
                id: editor; clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: editor.availableWidth; spacing: 12
                    Field { id: entityName; visible: dialog.editing === "entity"; caption: Style.tr("人物名称或身份说明（最多 80 字）"); Layout.fillWidth: true; enabled: !bridge.busy }
                    LabelText { visible: dialog.editing === "entity"; text: Style.tr("同名人物请补充不同的身份说明；不会合并为同一个人。"); color: Style.muted; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "add"; text: Style.tr("人物"); Layout.fillWidth: true }
                    Choice { id: subject; objectName: "factSubject"; visible: dialog.editing === "add"; model: (dialog.recordsData.entities || []).map(function(r) { return {id: r.id, label: r.id === "owner" ? Style.tr("用户") : r.label} }); textRole: "label"; valueRole: "id"; Layout.fillWidth: true; enabled: !bridge.busy }
                    Field { id: aspect; objectName: "factAspect"; visible: dialog.editing === "add"; caption: Style.tr("单一事项（例如居住地，最多 60 字）"); Layout.fillWidth: true; enabled: !bridge.busy }
                    Field { id: value; objectName: "factValue"; visible: dialog.editing === "add"; caption: Style.tr("具体说法（保留否定和数字，最多 240 字）"); Layout.fillWidth: true; enabled: !bridge.busy }
                    Field { id: startsOn; objectName: "factStartsOn"; visible: dialog.editing === "add"; caption: Style.tr("生效起日（YYYY-MM-DD，不知道请留空）"); Layout.fillWidth: true; enabled: !bridge.busy }
                    LabelText { visible: dialog.editing === "add"; text: Style.tr("同一人物的同一事项表示一个值。请沿用原事项名称；多个并存的爱好应分别记录。"); color: Style.muted; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "resolve"; text: Style.tr("采用这条后，其余当前说法进入历史。请选择原来记错，还是后来发生了变化。"); Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "resolve" && dialog.changeType === "correction"; text: Style.tr("原话和独立事项保留；此前依赖错误来源的模型回答与摘要会退出回忆，影响范围可能包含同段内容。"); Layout.fillWidth: true; color: Style.muted }
                    RowLayout {
                        visible: dialog.editing === "resolve"
                        AppButton { text: Style.tr("原来记错"); selected: dialog.changeType === "correction"; onClicked: dialog.changeType = "correction" }
                        AppButton { text: Style.tr("后来改变"); selected: dialog.changeType === "change"; onClicked: dialog.changeType = "change" }
                    }
                    LabelText { visible: dialog.editing === "forget"; text: Style.tr("放下这项的全部历史说法，并停止回忆相关来源。若原文包含其他内容，也可能一起停止回忆；原文件保留。"); color: Style.danger; Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "retract"; text: Style.tr("只撤回这条模型提取，保留原话和其他事项。不会自动认定相反说法为真；引用旧理解的生成内容可能退出回忆。"); Layout.fillWidth: true }
                    LabelText { visible: dialog.editing === "retract" && !!dialog.retractPreview.value; text: (dialog.retractPreview.value || "") + "\n" + Style.tr("原文") + "：" + (dialog.retractPreview.quote || ""); Layout.fillWidth: true }
                    Field { id: reason; objectName: "factReason"; visible: dialog.editing === "resolve" || dialog.editing === "forget" || dialog.editing === "retract"; caption: Style.tr(dialog.editing === "retract" ? "哪里理解错了（最多 500 字）" : "核对或放下的理由（最多 500 字）"); Layout.fillWidth: true; enabled: !bridge.busy }
                    Field { id: effective; visible: dialog.editing === "resolve" && dialog.changeType === "change"; caption: Style.tr("变化日期（YYYY-MM-DD，可留空）"); Layout.fillWidth: true; enabled: !bridge.busy }
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
            AppButton {
                objectName: "saveFact"; visible: !!dialog.editing; text: Style.tr("保存"); primary: true
                enabled: !bridge.busy && (dialog.editing === "entity" ? entityName.text.trim().length > 0 && entityName.text.length <= 80
                         : dialog.editing === "add" ? subject.currentIndex >= 0 && aspect.text.trim().length > 0 && aspect.text.length <= 60 && value.text.trim().length > 0 && value.text.length <= 240
                         : reason.text.trim().length > 0 && reason.text.length <= 500)
                onClicked: dialog.save()
            }
        }
    }
}
