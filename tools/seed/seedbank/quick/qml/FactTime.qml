import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "factTimeDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(840, parent ? parent.width - 32 : 840)
    height: Math.min(780, parent ? parent.height - 32 : 780)
    modal: true
    closePolicy: Popup.NoAutoClose
    readonly property var recordsData: bridge.factTime
    function openDate(identifier) { dateEditor.openFor(identifier) }
    FactDate { id: dateEditor }
    function refresh(offset, slot, recordOffset) {
        bridge.loadFactTime(search.text, date.text.trim(), offset || 0, slot || "", recordOffset || 0)
    }
    function page(offset, slot, recordOffset) {
        bridge.loadFactTime(recordsData.query || "", recordsData.on || "", offset, slot || "", recordOffset || 0)
    }
    function stateText(state) {
        if (state === "reported") return Style.tr("登记时间线支持的说法，未独立核实")
        if (state === "conflict") return Style.tr("该日期存在互相冲突的说法")
        if (state === "uncertain") return Style.tr("该日期的情况仍不确定")
        if (state === "unknown") return Style.tr("没有足够日期依据，不能确定当时情况")
        return Style.tr("时间线：尚未指定回查日期")
    }
    function reasonText(reason) {
        var labels = { unknown_start: "起日未记录", unknown_end: "结束日期未记录",
                       conflicting_start_dates: "起日存在不同记录", reversed_dates: "起止日期顺序矛盾",
                       same_day_changes: "同一天有多次变化，无法确定整天的情况", date_revision_unavailable: "最新日期依据不可用，未恢复旧日期。" }
        return Style.tr(labels[reason] || reason)
    }
    onOpened: refresh(0, "", 0)
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("按日期回查"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        spacing: 10
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        LabelText { text: Style.tr("按现在可用的来源回看过去。保存时间不等于生效时间；缺少日期就保留未知。未记录后续变化不证明现实没有变化。"); color: Style.muted; Layout.fillWidth: true }
        Field { id: search; objectName: "factTimeSearch"; caption: Style.tr("搜索人物、事项或说法"); Layout.fillWidth: true; enabled: !bridge.busy }
        RowLayout {
            Layout.fillWidth: true
            Field { id: date; objectName: "factTimeDate"; caption: Style.tr("回查日期（YYYY-MM-DD，留空查看时间线）"); Layout.fillWidth: true; enabled: !bridge.busy; input.onAccepted: dialog.refresh(0, "", 0) }
            AppButton { objectName: "queryFactTime"; text: Style.tr("回查"); enabled: !bridge.busy; Layout.alignment: Qt.AlignBottom; onClicked: dialog.refresh(0, "", 0) }
        }
        LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); color: Style.muted; Layout.fillWidth: true }
        LabelText { visible: !!dialog.recordsData.on; text: Style.tr("本次结果对应日期") + "：" + (dialog.recordsData.on || ""); Layout.fillWidth: true }
        ScrollView {
            id: records; clip: true; contentWidth: availableWidth; Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                width: records.availableWidth; spacing: 14
                LabelText { visible: !bridge.busy && (dialog.recordsData.groups || []).length === 0; text: Style.tr("没有匹配的可用时间记录；这不代表事情从未发生。"); color: Style.muted; Layout.fillWidth: true }
                Repeater {
                    model: dialog.recordsData.pending || []
                    AppButton { required property var modelData; text: Style.tr("恢复未完成的日期修订"); enabled: !bridge.busy; onClicked: dateEditor.resume(modelData.payload.data) }
                }
                Repeater {
                    model: dialog.recordsData.groups || []
                    ColumnLayout {
                        id: group
                        required property var modelData
                        Layout.fillWidth: true; spacing: 8
                        LabelText { text: (group.modelData.subject === "owner" ? Style.tr("用户") : group.modelData.label) + " · " + group.modelData.aspect; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        LabelText { text: dialog.stateText(group.modelData.temporal.status); color: group.modelData.temporal.status === "reported" ? Style.ink : Style.muted; Layout.fillWidth: true }
                        LabelText { visible: group.modelData.temporal.values.length > 0; text: group.modelData.temporal.values.join(" / "); Layout.fillWidth: true }
                        LabelText { visible: group.modelData.temporal.omitted; text: Style.tr("这里只显示部分来源，结论已考虑全部可用候选。"); color: Style.muted; Layout.fillWidth: true }
                        Repeater {
                            model: group.modelData.temporal.records
                            ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true; spacing: 4
                                LabelText { text: modelData.value; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                LabelText { visible: modelData.match !== "not_queried"; text: Style.tr(modelData.match === "covered" ? "登记范围覆盖所问日期" : modelData.match === "outside" ? "不覆盖所问日期" : "日期依据不足，不能确定是否覆盖"); color: Style.muted; Layout.fillWidth: true }
                                LabelText { text: (modelData.starts_on || Style.tr("起日未记录")) + " → " + (modelData.until_on ? modelData.until_on + " · " + Style.tr("结束当日不包含在内") : Style.tr(modelData.open_end ? "未记录后续变化" : "结束日期未记录")); color: Style.muted; Layout.fillWidth: true }
                                LabelText { text: Style.tr("保存时间") + "：" + modelData.recorded_at; color: Style.muted; Layout.fillWidth: true }
                                LabelText { text: Style.tr(modelData.origin === "user" ? "用户直接记录" : "模型从发言中提取，含义仍需核对"); color: Style.muted; Layout.fillWidth: true }
                                LabelText { visible: modelData.date_state === "revised"; text: Style.tr("日期已有用户修订，原文仍保留。"); color: Style.muted; Layout.fillWidth: true }
                                AppButton { text: Style.tr("日期说明与修订"); enabled: !bridge.busy; onClicked: dialog.openDate(modelData.id) }
                                LabelText { visible: modelData.reasons.length > 0; text: modelData.reasons.map(dialog.reasonText).join(" · "); color: Style.muted; Layout.fillWidth: true }
                                LabelText { text: Style.tr("原文") + "：" + modelData.quote; Layout.fillWidth: true }
                                LabelText { text: modelData.evidence.map(function(r) { return r.source }).join("\n"); color: Style.muted; font.pixelSize: 12 * Style.scale; Layout.fillWidth: true }
                            }
                        }
                        RowLayout {
                            AppButton { text: Style.tr("上一页来源"); visible: group.modelData.temporal.offset > 0; enabled: !bridge.busy; onClicked: dialog.page(0, group.modelData.id, Math.max(0, group.modelData.temporal.offset - 30)) }
                            AppButton { text: Style.tr("下一页来源"); visible: group.modelData.temporal.offset + 30 < group.modelData.temporal.total; enabled: !bridge.busy; onClicked: dialog.page(0, group.modelData.id, group.modelData.temporal.offset + 30) }
                        }
                        Rectangle { height: 1; color: Style.line; Layout.fillWidth: true }
                    }
                }
                RowLayout {
                    AppButton { text: Style.tr("上一页"); enabled: !bridge.busy && (dialog.recordsData.offset || 0) > 0; onClicked: dialog.page(Math.max(0, dialog.recordsData.offset - 30), "", 0) }
                    AppButton { text: Style.tr("下一页"); enabled: !bridge.busy && (dialog.recordsData.offset || 0) + 30 < (dialog.recordsData.total || 0); onClicked: dialog.page((dialog.recordsData.offset || 0) + 30, "", 0) }
                    AppButton { text: Style.tr("返回全部事项"); visible: !!dialog.recordsData.slot; enabled: !bridge.busy; onClicked: dialog.refresh(0, "", 0) }
                }
            }
        }
    }
    footer: AppButton { text: Style.tr("关闭"); enabled: !bridge.busy; onClicked: dialog.close() }
}
