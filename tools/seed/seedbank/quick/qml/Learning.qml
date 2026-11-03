import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "learningDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(860, parent ? parent.width - 32 : 860)
    height: Math.min(820, parent ? parent.height - 32 : 820)
    modal: true
    closePolicy: Popup.NoAutoClose
    readonly property var recordsData: bridge.learning
    readonly property var goal: recordsData.goal || ({})
    readonly property var criteria: recordsData.criteria || ({})
    readonly property var items: criteria.data ? criteria.data.items : []
    property string editing: ""
    property var target: ({})
    property var attempt: ({})
    property var ratings: ({})
    property var chosen: ({})
    property var draftItems: []
    property var groupNames: []
    property int prerequisiteCount: 0
    readonly property var verdictOptions: [{id: "unclear", label: Style.tr("暂时不确定")}, {id: "met", label: Style.tr("符合")}, {id: "not_met", label: Style.tr("不符合")}]
    readonly property var kindOptions: [{id: "letter", label: Style.tr("信")}, {id: "poem", label: Style.tr("诗")}, {id: "drawing", label: Style.tr("字符画")}, {id: "reflection", label: Style.tr("反思")}]
    readonly property var fitOptions: [{id: "uncertain", label: Style.tr("暂时不确定")}, {id: "applicable", label: Style.tr("适合这次任务")}, {id: "not_applicable", label: Style.tr("不适合这次任务")}]
    readonly property var useOptions: [{id: "uncertain", label: Style.tr("暂时不确定")}, {id: "observed", label: Style.tr("作品中能看到体现")}, {id: "not_observed", label: Style.tr("作品中未观察到体现")}]
    readonly property var effectOptions: [{id: "uncertain", label: Style.tr("暂时不确定")}, {id: "helpful", label: Style.tr("对这次成果有帮助")}, {id: "harmful", label: Style.tr("对这次成果有妨碍")}, {id: "no_clear_effect", label: Style.tr("未见明确效果")}]
    ListModel { id: criteriaDraft; objectName: "learningCriteriaDraft" }
    ListModel { id: prerequisiteDraft; objectName: "learningPrerequisiteDraft" }
    ListModel { id: observationDraft; objectName: "learningObservationDraft" }
    function choiceLabel(choice) {
        var labels = {adopt: "模型自述：参考", adapt: "模型自述：调整后参考", skip: "模型自述：不采用", uncertain: "模型自述：暂不确定"}
        return Style.tr(labels[choice] || "本次未留下经验取舍说明。")
    }
    function choiceState(state) {
        if (state === "no_model_report") return Style.tr("离线或回退结果未记录模型取舍。")
        if (state === "invalid_source") return Style.tr("取舍说明的来源当前无法核对。")
        if (state === "artifact_unavailable") return Style.tr("作品已变化或不可用，暂不展示取舍说明。")
        if (state === "invalid_report") return Style.tr("返回的取舍说明未能对应本次提供的经验。")
        return Style.tr("本次未留下经验取舍说明。")
    }
    function observationLabel(row) {
        function label(options, value) { return options.filter(function(r) { return r.id === value }).map(function(r) { return r.label }).join("") }
        return label(fitOptions, row.fit) + " · " + label(useOptions, row.use) + " · " + label(effectOptions, row.effect)
    }
    function prepareObservations() {
        observationDraft.clear()
        if ((attempt.practice || {}).scope !== "provided_to_creator") return
        var saved = ((attempt.feedback || {}).data || {}).lesson_observations || []
        ;(attempt.offered_lessons || []).forEach(function(lesson) {
            if (!lesson.currently_available) return
            var matches = saved.filter(function(r) { return r.lesson_id === lesson.id })
            var row = matches.length ? matches[0] : ({})
            observationDraft.append({lesson_id: lesson.id, strategy: lesson.data.text, selected: matches.length > 0,
                fit: row.fit || "uncertain", use: row.use || "uncertain", effect: row.effect || "uncertain", reason: row.reason || "", quote: row.quote || ""})
        })
    }
    function refresh(offset) { attempt = ({}); bridge.loadLearning(goal.id || "", offset || 0) }
    function startPlan(fresh) {
        target = fresh ? ({}) : goal; editing = "plan"
        goalTitle.text = target.title || ""; skill.text = !fresh && criteria.data ? criteria.data.skill : ""
        nextStep.text = target.next_step || ""; reason.text = ""
        criteriaDraft.clear()
        var rows = fresh ? [] : items
        for (var i = 0; i < rows.length; i++) criteriaDraft.append({text: rows[i].text, group: rows[i].group, check: rows[i].check, artifact_kind: rows[i].artifact_kind || "letter"})
        if (!criteriaDraft.count) addCriterion()
        prerequisiteDraft.clear(); prerequisiteCount = 0
        var saved = !fresh && criteria.data ? (criteria.data.prerequisites || []) : []
        var available = (recordsData.prerequisite_options || []).filter(function(r) { return r.goal_id !== target.id })
        available.forEach(function(option) {
            var previous = saved.filter(function(r) { return r.goal_id === option.goal_id })[0]
            prerequisiteDraft.append({goal_id: option.goal_id, title: option.title, current_criteria: option.criteria_id,
                criteria_id: previous ? previous.criteria_id : option.criteria_id, selected: !!previous, available: true})
            if (previous) prerequisiteCount++
        })
        saved.forEach(function(previous) {
            if (!available.some(function(r) { return r.goal_id === previous.goal_id })) {
                prerequisiteDraft.append({goal_id: previous.goal_id, title: Style.tr("前置目标依据不可用"), current_criteria: "",
                    criteria_id: previous.criteria_id, selected: true, available: false})
                prerequisiteCount++
            }
        })
    }
    function selectPrerequisite(index, checked) {
        var row = prerequisiteDraft.get(index)
        if (row.selected === checked) return
        prerequisiteCount += checked ? 1 : -1
        prerequisiteDraft.setProperty(index, "selected", checked)
        if (checked) prerequisiteDraft.setProperty(index, "criteria_id", row.current_criteria)
    }
    function addCriterion() { criteriaDraft.append({text: "", group: Style.tr("成果"), check: "feedback", artifact_kind: "letter"}) }
    function start(action) {
        editing = action; reason.text = ""; nextStep.text = ""; task.text = ""
        target = {goal_id: goal.id, expected: goal.event_id, criteria_id: criteria.id, outcome_id: attempt.id || ""}
        draftItems = items; chosen = ({}); groupNames = items.map(function(r) { return r.group }).filter(function(v, i, all) { return all.indexOf(v) === i })
        ratings = attempt.feedback && attempt.feedback.data ? Object.assign({}, attempt.feedback.data.ratings) : ({})
        if (action === "feedback") {
            target.expected = attempt.feedback ? (attempt.feedback.id || "") : ""
            reason.text = attempt.feedback && attempt.feedback.data ? attempt.feedback.data.reason : ""
            nextStep.text = attempt.feedback && attempt.feedback.data ? attempt.feedback.data.next_step : ""
            prepareObservations()
        }
        if (action === "strategy") {
            var previous = (attempt.adjustment || {}).data || ({})
            target = {goal_id: goal.id, feedback_id: attempt.feedback.id, expected: attempt.strategy_expected || ""}
            strategyText.text = previous.text || ""; expectedResult.text = previous.expected_result || ""
            appliesWhen.text = (previous.transfer || {}).applies_when || ""
            avoidWhen.text = (previous.transfer || {}).avoid_when || ""
            allowReuse.checked = !!appliesWhen.text && !!avoidWhen.text
        }
    }
    function restoreStrategy(data) {
        editing = "strategy"; target = {goal_id: data.goal_id, feedback_id: data.feedback_id, expected: data.expected}
        strategyText.text = data.text; expectedResult.text = data.expected_result
        appliesWhen.text = (data.transfer || {}).applies_when || ""; avoidWhen.text = (data.transfer || {}).avoid_when || ""
        allowReuse.checked = !!appliesWhen.text && !!avoidWhen.text
    }
    function save() {
        var data
        if (editing === "plan") {
            var rows = []
            for (var i = 0; i < criteriaDraft.count; i++) { var r = criteriaDraft.get(i); rows.push({text: r.text, group: r.group, check: r.check, artifact_kind: r.artifact_kind}) }
            data = {goal_id: target.id || "", expected: target.event_id || "", title: goalTitle.text.trim(), skill: skill.text.trim(), reason: reason.text.trim(), next_step: nextStep.text.trim(), criteria: rows}
            data.prerequisites = []
            for (var p = 0; p < prerequisiteDraft.count; p++) {
                var prerequisite = prerequisiteDraft.get(p)
                if (prerequisite.selected) data.prerequisites.push({goal_id: prerequisite.goal_id, criteria_id: prerequisite.criteria_id})
            }
        } else if (editing === "practice") {
            data = {goal_id: target.goal_id, criteria_id: target.criteria_id, work_kind: workKind.currentValue, topic: task.text.trim()}
        } else if (editing === "feedback") {
            var values = ({})
            draftItems.forEach(function(r) { values[r.id] = ratings[r.id] || "unclear" })
            data = Object.assign({}, target, {ratings: values, reason: reason.text.trim(), next_step: nextStep.text.trim()})
            if (observationDraft.count || ((attempt.feedback || {}).data || {}).lesson_observations !== undefined) {
                var observations = []
                for (var j = 0; j < observationDraft.count; j++) {
                    var observation = observationDraft.get(j)
                    if (observation.selected) observations.push({lesson_id: observation.lesson_id, fit: observation.fit,
                        use: observation.use, effect: observation.effect, reason: observation.reason.trim(), quote: observation.quote.trim()})
                }
                data.lesson_observations = observations
            }
        } else if (editing === "strategy") {
            data = Object.assign({}, target, {text: strategyText.text.trim(), expected_result: expectedResult.text.trim(),
                transfer: allowReuse.checked ? {applies_when: appliesWhen.text.trim(), avoid_when: avoidWhen.text.trim()} : ({})})
        } else {
            var evidence = ({})
            draftItems.forEach(function(r) { evidence[r.id] = chosen[r.group] || "" })
            data = Object.assign({}, target, {evidence: evidence, reason: reason.text.trim()})
        }
        bridge.saveLearning(editing, data)
    }
    function verdict(value) { return Style.tr(value === "met" ? "符合" : value === "not_met" ? "不符合" : "暂时不确定") }
    function assetLabel(value) { return Style.tr(value === "unchanged" ? "成果内容与保存时一致" : value === "changed" ? "成果已改变，请重新尝试" : value === "unavailable" ? "成果文件不可用" : "旧回执没有内容指纹，请重新尝试") }
    onOpened: { editing = ""; attempt = ({}); bridge.loadLearning("", 0) }
    Connections { target: bridge; function onLearningSaved() { dialog.editing = ""; dialog.attempt = ({}) } }
    background: Rectangle { color: Style.surface; radius: 20; border.color: Style.line }
    header: LabelText { text: Style.tr("练习与反馈"); padding: 22; font.pixelSize: 22 * Style.scale; font.weight: Font.DemiBold }
    contentItem: ColumnLayout {
        spacing: 10
        LabelText { text: Style.tr("保存成功只说明做过。具体反馈用于下次尝试，不代表已经掌握一种能力。"); color: Style.muted; Layout.fillWidth: true }
        LabelText { visible: bridge.error; text: bridge.notice; color: Style.danger; Layout.fillWidth: true }
        LabelText { visible: bridge.busy; text: Style.tr("正在整理，请稍候…"); Layout.fillWidth: true }
        ScrollView {
            id: scroll; clip: true; contentWidth: availableWidth; Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                width: scroll.availableWidth; spacing: 14
                ColumnLayout {
                    visible: dialog.editing === ""; Layout.fillWidth: true
                    Repeater {
                        model: dialog.recordsData.pending || []
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            LabelText { text: (modelData.payload.topic || (modelData.payload.data || {}).title || (modelData.payload.data || {}).reason || ""); Layout.fillWidth: true }
                            AppButton { text: Style.tr(modelData.payload.action === "strategy" ? "恢复未完成的经验编辑" : modelData.payload.kind === "practice" ? "继续未完成的创作（会调用模型）" : "恢复未完成的练习操作"); enabled: !bridge.busy; onClicked: { if (modelData.payload.action === "strategy") dialog.restoreStrategy(modelData.payload.data); else bridge.resumeLearning(modelData.id) } }
                        }
                    }
                    Choice {
                        objectName: "learningGoal"; Layout.fillWidth: true; enabled: !bridge.busy
                        model: dialog.recordsData.goals || []; textRole: "title"; valueRole: "id"
                        currentIndex: (dialog.recordsData.goals || []).map(function(r) { return r.id }).indexOf(dialog.goal.id)
                        onActivated: { dialog.attempt = ({}); bridge.loadLearning(currentValue, 0) }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 8
                        AppButton { objectName: "newLearningGoal"; text: Style.tr("新建练习目标"); enabled: !bridge.busy; onClicked: dialog.startPlan(true) }
                        AppButton { text: Style.tr("修订目标与条件"); enabled: !bridge.busy && (dialog.goal.status === "active" || dialog.goal.status === "paused"); onClicked: dialog.startPlan(false) }
                        AppButton { text: Style.tr("刷新"); enabled: !bridge.busy; onClicked: dialog.refresh(dialog.recordsData.offset) }
                    }
                    LabelText { visible: !!dialog.goal.id; text: Style.tr(dialog.goal.status || "") + " · " + (dialog.goal.reason || ""); Layout.fillWidth: true }
                    Repeater {
                        model: dialog.recordsData.interpretation_lines || []
                        LabelText { required property string modelData; text: modelData; Layout.fillWidth: true; color: Style.muted }
                    }
                    Panel {
                        visible: !!(dialog.recordsData.project || {}).title
                        Layout.fillWidth: true; caption: Style.tr("分阶段安排")
                        LabelText { text: (dialog.recordsData.project || {}).title || ""; Layout.fillWidth: true; font.weight: Font.DemiBold }
                        LabelText { text: (dialog.recordsData.project || {}).reason || ""; Layout.fillWidth: true; color: Style.muted }
                        LabelText { text: Style.tr("由个体提出；阶段状态分别记录，安排本身不代表完成。"); Layout.fillWidth: true; color: Style.muted }
                        Repeater {
                            model: (dialog.recordsData.project || {}).stages || []
                            RowLayout {
                                id: projectStage
                                required property var modelData
                                Layout.fillWidth: true
                                LabelText { text: projectStage.modelData.title ? projectStage.modelData.title + " · " + Style.tr(projectStage.modelData.status) : Style.tr("当前依据已不可用"); Layout.fillWidth: true; font.weight: projectStage.modelData.selected ? Font.DemiBold : Font.Normal }
                                AppButton { text: Style.tr("查看此阶段"); enabled: !bridge.busy && !!projectStage.modelData.title && !projectStage.modelData.selected; onClicked: { dialog.attempt = ({}); bridge.loadLearning(projectStage.modelData.goal_id, 0) } }
                            }
                        }
                    }
                    LabelText {
                        visible: dialog.goal.status === "completed"; Layout.fillWidth: true; color: Style.muted
                        text: Style.tr(dialog.recordsData.completion_current && dialog.recordsData.completion_current.passed ? "当前依据仍符合这次目标的完成条件。" : "历史上标记过完成，当前依据不足以确认；历史记录保留。")
                    }
                    LabelText { visible: !dialog.criteria.id; text: Style.tr("先写下明确条件，再开始练习。"); Layout.fillWidth: true }
                    LabelText { visible: (dialog.recordsData.readiness_lines || []).length > 0; text: Style.tr("先完成这些目标"); Layout.fillWidth: true; font.weight: Font.DemiBold }
                    Repeater {
                        model: dialog.recordsData.readiness_lines || []
                        LabelText { required property string modelData; text: modelData; Layout.fillWidth: true }
                    }
                    LabelText { visible: !!dialog.criteria.id && !(dialog.recordsData.readiness || {}).ready; text: Style.tr("前置目标尚未按当前依据完成，请先完成或明确修订前置安排。"); Layout.fillWidth: true; color: Style.muted }
                    Repeater {
                        model: dialog.items
                        LabelText { required property var modelData; text: modelData.group + " · " + modelData.text + (modelData.check === "artifact" ? " · " + Style.tr("自动核对保存") : ""); Layout.fillWidth: true }
                    }
                    LabelText { visible: (dialog.recordsData.lessons || []).length > 0; text: Style.tr("按当前目标查找参考经验；开始创作时，会结合这次任务重新选择。请先判断是否适用。"); Layout.fillWidth: true; color: Style.muted }
                    Repeater {
                        model: dialog.recordsData.lessons || []
                        Panel {
                            id: lessonCard
                            required property var modelData
                            Layout.fillWidth: true; caption: modelData.source_goal_title
                            LabelText { text: modelData.data.text; Layout.fillWidth: true }
                            LabelText { visible: !!lessonCard.modelData.retrieval; text: Style.tr((lessonCard.modelData.retrieval || {}).basis === "recent_fallback" ? "没有找到直接的文字关联，暂列为近期参考。" : "与当前目标或任务有文字关联，不代表适用性已经确认。"); Layout.fillWidth: true; color: Style.muted }
                            LabelText { visible: ((lessonCard.modelData.retrieval || {}).matched_fields || []).indexOf("avoid_when") >= 0; text: Style.tr("当前内容也与不宜照搬的情形有关，请核对适用边界。"); Layout.fillWidth: true; color: Style.muted }
                            LabelText { text: Style.tr("适用情形") + "：" + modelData.data.transfer.applies_when + "\n" + Style.tr("不宜照搬的情形") + "：" + modelData.data.transfer.avoid_when; Layout.fillWidth: true; color: Style.muted }
                            LabelText { text: Style.tr("原任务反馈") + "：" + modelData.source_feedback.reason; Layout.fillWidth: true; color: Style.muted }
                            LabelText { visible: (lessonCard.modelData.observation_count || 0) > 0; text: Style.tr("后续尝试中的用户观察（选取最多三条，保留相关反例）") + " · " + lessonCard.modelData.observation_count; Layout.fillWidth: true; color: Style.muted }
                            Repeater {
                                model: lessonCard.modelData.observations || []
                                LabelText { required property var modelData; text: modelData.goal_title + " · " + dialog.observationLabel(modelData) + "\n" + modelData.reason + (modelData.quote ? "\n“" + modelData.quote + "”" : ""); Layout.fillWidth: true }
                            }
                        }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 8
                        AppButton { objectName: "startPractice"; text: Style.tr("开始一次创作"); enabled: !bridge.busy && !!dialog.criteria.id && dialog.goal.status === "active" && (dialog.recordsData.readiness || {}).ready === true; onClicked: dialog.start("practice") }
                        AppButton { text: Style.tr("核对目标完成"); enabled: !bridge.busy && !!dialog.criteria.id && (dialog.goal.status === "active" || dialog.goal.status === "paused") && (dialog.recordsData.readiness || {}).ready === true; onClicked: dialog.start("complete") }
                    }
                    Choice {
                        objectName: "learningAttempt"; Layout.fillWidth: true; enabled: !bridge.busy
                        model: (dialog.recordsData.attempts || []).map(function(r, i) { return {id: r.id, label: String(dialog.recordsData.total - dialog.recordsData.offset - i) + " · " + (r.artifact_view.title || r.detail || r.action) + " · " + Style.tr(r.status)} })
                        textRole: "label"; valueRole: "id"; currentIndex: (dialog.recordsData.attempts || []).map(function(r) { return r.id }).indexOf(dialog.attempt.id)
                        onActivated: dialog.attempt = dialog.recordsData.attempts[currentIndex]
                    }
                    RowLayout {
                        AppButton { text: Style.tr("上一页"); enabled: !bridge.busy && dialog.recordsData.offset > 0; onClicked: dialog.refresh(Math.max(0, dialog.recordsData.offset - 30)) }
                        AppButton { text: Style.tr("下一页"); enabled: !bridge.busy && dialog.recordsData.offset + 30 < dialog.recordsData.total; onClicked: dialog.refresh(dialog.recordsData.offset + 30) }
                    }
                    Panel {
                        visible: !!dialog.attempt.id; Layout.fillWidth: true; caption: dialog.attempt.artifact_view ? (dialog.attempt.artifact_view.title || dialog.attempt.action || "") : ""
                        LabelText { text: dialog.attempt.status !== "succeeded" && !dialog.attempt.artifact ? Style.tr("本次没有可评价的成果") : dialog.assetLabel((dialog.attempt.artifact_view || {}).state); Layout.fillWidth: true }
                        LabelText { text: Style.tr(dialog.attempt.attempt_state === "started" ? "已进入执行流程" : dialog.attempt.attempt_state === "not_started" ? "未进入执行流程" : "未记录是否开始执行"); Layout.fillWidth: true; color: Style.muted }
                        LabelText { text: (dialog.attempt.artifact_view || {}).text || dialog.attempt.detail || ""; Layout.fillWidth: true }
                        LabelText { text: Style.tr("来源") + " · " + (dialog.attempt.source || "") + "\n" + ((dialog.attempt.generation || {}).runner || "") + " · " + ((dialog.attempt.generation || {}).model || ""); color: Style.muted; Layout.fillWidth: true }
                        ColumnLayout {
                            objectName: "strategyChoicesPanel"; Layout.fillWidth: true
                            LabelText { text: Style.tr("这次怎样参考经验"); font.weight: Font.DemiBold; Layout.fillWidth: true }
                            LabelText { text: Style.tr("这是随作品返回的模型自述，请结合实际作品和反馈判断。"); color: Style.muted; Layout.fillWidth: true }
                            LabelText { visible: !((dialog.attempt.strategy_choices || {}).items || []).length; text: dialog.choiceState((dialog.attempt.strategy_choices || {}).state); Layout.fillWidth: true; color: Style.muted }
                            Repeater {
                                model: (dialog.attempt.strategy_choices || {}).items || []
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    LabelText { text: dialog.choiceLabel(modelData.choice) + " · " + modelData.strategy; Layout.fillWidth: true }
                                    LabelText { text: modelData.reason + (modelData.application ? "\n" + modelData.application : "") + (modelData.currently_available ? "" : "\n" + Style.tr("当前依据已不可用")); Layout.fillWidth: true; color: Style.muted }
                                }
                            }
                            LabelText { visible: ((dialog.attempt.strategy_choices || {}).unreported_ids || []).length > 0; text: Style.tr("另有 {count} 条已提供经验未说明取舍。", {count: ((dialog.attempt.strategy_choices || {}).unreported_ids || []).length}); Layout.fillWidth: true; color: Style.muted }
                            LabelText { visible: (dialog.attempt.strategy_choices || {}).rejected_count > 0; text: Style.tr("有 {count} 项说明未能与本次提供的经验核对。", {count: (dialog.attempt.strategy_choices || {}).rejected_count || 0}); Layout.fillWidth: true; color: Style.muted }
                        }
                        LabelText { text: dialog.attempt.feedback && dialog.attempt.feedback.data ? dialog.attempt.feedback.data.reason + "\n" + dialog.attempt.feedback.data.next_step : Style.tr("还没有针对这份成果的反馈。"); Layout.fillWidth: true }
                        Repeater {
                            model: ((dialog.attempt.feedback || {}).data || {}).lesson_observations || []
                            LabelText { required property var modelData; text: dialog.observationLabel(modelData) + "\n" + modelData.reason + (modelData.quote ? "\n“" + modelData.quote + "”" : ""); Layout.fillWidth: true }
                        }
                        AppButton { objectName: "reviewPractice"; text: Style.tr("填写或修正反馈"); enabled: !bridge.busy && !!dialog.criteria.id && dialog.attempt.status === "succeeded" && (dialog.attempt.artifact_view || {}).state === "unchanged"; onClicked: dialog.start("feedback") }
                        LabelText { visible: !!(dialog.attempt.adjustment || {}).id; text: dialog.attempt.adjustment && dialog.attempt.adjustment.data ? Style.tr("下次尝试的策略") + "\n" + dialog.attempt.adjustment.data.text : ""; Layout.fillWidth: true }
                        AppButton { objectName: "editLearningStrategy"; text: Style.tr("整理或修订这次经验"); enabled: !bridge.busy && !!(dialog.attempt.feedback || {}).id && (dialog.attempt.artifact_view || {}).state === "unchanged"; onClicked: dialog.start("strategy") }
                        ToggleRow { id: strategyHistory; visible: (dialog.attempt.strategy_history_total || 0) > 0; text: Style.tr("查看这条经验的最近版本（最多五条）") }
                        Repeater {
                            model: strategyHistory.checked ? dialog.attempt.strategy_history || [] : []
                            LabelText { required property var modelData; text: modelData.at + " · " + Style.tr(modelData.origin === "user" ? "用户整理" : "模型提出") + "\n" + modelData.data.text + "\n" + modelData.data.expected_result; Layout.fillWidth: true; color: Style.muted }
                        }
                        LabelText { visible: (dialog.attempt.offered_lessons || []).length > 0; text: Style.tr((dialog.attempt.practice || {}).scope === "provided_to_creator" ? "本次提供给创作模型的经验，不证明已经采用。" : "执行时可用的经验，不证明已经读取。"); Layout.fillWidth: true; color: Style.muted }
                        Repeater {
                            model: dialog.attempt.offered_lessons || []
                            LabelText { required property var modelData; text: modelData.data.text + (modelData.currently_available ? "" : " · " + Style.tr("当前依据已不可用")); Layout.fillWidth: true }
                        }
                        LabelText { visible: (dialog.attempt.offered_observations || []).length > 0; text: Style.tr((dialog.attempt.practice || {}).scope === "provided_to_creator" ? "本次提供过的经验观察，不证明模型已经采用。" : "执行时可用的经验观察，不证明已经读取。"); Layout.fillWidth: true; color: Style.muted }
                        Repeater {
                            model: dialog.attempt.offered_observations || []
                            ColumnLayout {
                                id: providedObservation
                                required property var modelData
                                Layout.fillWidth: true
                                LabelText { visible: !providedObservation.modelData.currently_available; text: Style.tr("当前依据已不可用"); Layout.fillWidth: true; color: Style.muted }
                                Repeater {
                                    model: providedObservation.modelData.observations || []
                                    LabelText { required property var modelData; text: dialog.observationLabel(modelData) + "\n" + modelData.reason; Layout.fillWidth: true }
                                }
                            }
                        }
                        LabelText { visible: !!((dialog.attempt.practice || {}).task || {}).topic; text: Style.tr("这次具体任务") + "：" + (((dialog.attempt.practice || {}).task || {}).topic || ""); Layout.fillWidth: true }
                        LabelText { visible: !!(dialog.attempt.comparison || {}).comparable; text: Style.tr("以下仅比较相同条件与模型标签下的用户评价，任务可能不同，不是能力认证。"); color: Style.muted; Layout.fillWidth: true }
                        Repeater {
                            model: (dialog.attempt.comparison || {}).changes || []
                            LabelText { required property var modelData; text: modelData.text + " · " + dialog.verdict(modelData.before) + " → " + dialog.verdict(modelData.after); Layout.fillWidth: true }
                        }
                    }
                }
                ColumnLayout {
                    visible: dialog.editing !== ""; Layout.fillWidth: true; enabled: !bridge.busy
                    Field { id: goalTitle; objectName: "learningTitle"; visible: dialog.editing === "plan"; caption: Style.tr("练习目标"); Layout.fillWidth: true; input.maximumLength: 120 }
                    Field { id: skill; objectName: "learningSkill"; visible: dialog.editing === "plan"; caption: Style.tr("练习方向"); Layout.fillWidth: true; input.maximumLength: 80 }
                    LabelText { visible: dialog.editing === "plan"; text: Style.tr("可选：先完成哪些目标？最多选择六项。前置成果与反馈变化后，会重新核对。"); Layout.fillWidth: true; color: Style.muted }
                    LabelText { visible: dialog.editing === "plan" && !prerequisiteDraft.count; text: Style.tr("还没有其他带完成条件的目标。"); Layout.fillWidth: true; color: Style.muted }
                    Repeater {
                        model: dialog.editing === "plan" ? prerequisiteDraft : null
                        ColumnLayout {
                            id: prerequisiteRow
                            required property int index
                            required property var model
                            Layout.fillWidth: true
                            ToggleRow {
                                objectName: "learningPrerequisiteToggle_" + prerequisiteRow.index
                                Layout.fillWidth: true; text: prerequisiteRow.model.title; checked: prerequisiteRow.model.selected
                                enabled: prerequisiteRow.model.selected || (prerequisiteRow.model.available && dialog.prerequisiteCount < 6)
                                onToggled: dialog.selectPrerequisite(prerequisiteRow.index, checked)
                            }
                            LabelText {
                                visible: prerequisiteRow.model.selected && prerequisiteRow.model.criteria_id !== prerequisiteRow.model.current_criteria
                                text: Style.tr("前置版本已变化，请取消后重新选择；不可用的目标可以移除。"); color: Style.danger; Layout.fillWidth: true
                            }
                        }
                    }
                    LabelText { visible: dialog.editing === "plan"; text: Style.tr("同一份成果的条件使用同一名称；需要多份成果时分别命名。修订条件后需要重新反馈。"); Layout.fillWidth: true; color: Style.muted }
                    Repeater {
                        model: dialog.editing === "plan" ? criteriaDraft : null
                        Panel {
                            id: criterionCard
                            required property int index
                            required property var model
                            Layout.fillWidth: true; caption: String(index + 1)
                            Field { caption: Style.tr("成果名称"); text: criterionCard.model.group; Layout.fillWidth: true; input.maximumLength: 40; onEdited: function(value) { criteriaDraft.setProperty(criterionCard.index, "group", value) } }
                            Choice { Layout.fillWidth: true; model: [Style.tr("由用户反馈核对"), Style.tr("自动核对保存")]; currentIndex: criterionCard.model.check === "artifact" ? 1 : 0; onActivated: criteriaDraft.setProperty(criterionCard.index, "check", currentIndex ? "artifact" : "feedback") }
                            Field { visible: criterionCard.model.check === "feedback"; caption: Style.tr("明确的完成条件"); text: criterionCard.model.text; Layout.fillWidth: true; input.maximumLength: 160; onEdited: function(value) { criteriaDraft.setProperty(criterionCard.index, "text", value) } }
                            Choice { visible: criterionCard.model.check === "artifact"; Layout.fillWidth: true; model: dialog.kindOptions; textRole: "label"; valueRole: "id"; currentIndex: dialog.kindOptions.map(function(r) { return r.id }).indexOf(criterionCard.model.artifact_kind); onActivated: criteriaDraft.setProperty(criterionCard.index, "artifact_kind", currentValue) }
                            AppButton { text: Style.tr("删除这条条件"); enabled: criteriaDraft.count > 1; onClicked: criteriaDraft.remove(criterionCard.index) }
                        }
                    }
                    AppButton { visible: dialog.editing === "plan"; text: Style.tr("添加完成条件"); enabled: criteriaDraft.count < 6; onClicked: dialog.addCriterion() }
                    LabelText { visible: dialog.editing === "practice"; text: Style.tr("开始后会调用当前创作模型，可能产生费用；这次任务将带上条件和可用反馈。"); Layout.fillWidth: true; color: Style.muted }
                    Choice { id: workKind; visible: dialog.editing === "practice"; Layout.fillWidth: true; model: dialog.kindOptions.slice(0, 3); textRole: "label"; valueRole: "id" }
                    Field { id: task; objectName: "learningTask"; visible: dialog.editing === "practice"; caption: Style.tr("这次具体尝试什么？"); Layout.fillWidth: true; input.maximumLength: 200 }
                    LabelText { visible: dialog.editing === "strategy"; text: Style.tr("从这份成果和反馈中整理具体做法。经验是待尝试的理解，不是已经掌握的能力。"); Layout.fillWidth: true; color: Style.muted }
                    Field { id: strategyText; objectName: "learningStrategyText"; visible: dialog.editing === "strategy"; caption: Style.tr("下一次的具体做法（最多 500 字）"); Layout.fillWidth: true; input.maximumLength: 500 }
                    Field { id: expectedResult; objectName: "learningExpectedResult"; visible: dialog.editing === "strategy"; caption: Style.tr("怎样观察是否有帮助（最多 500 字）"); Layout.fillWidth: true; input.maximumLength: 500 }
                    ToggleRow { id: allowReuse; objectName: "learningAllowReuse"; visible: dialog.editing === "strategy"; text: Style.tr("允许同方向、不同任务参考这条经验") }
                    Field { id: appliesWhen; objectName: "learningAppliesWhen"; visible: dialog.editing === "strategy" && allowReuse.checked; caption: Style.tr("适用情形"); Layout.fillWidth: true; input.maximumLength: 500 }
                    Field { id: avoidWhen; objectName: "learningAvoidWhen"; visible: dialog.editing === "strategy" && allowReuse.checked; caption: Style.tr("不宜照搬的情形"); Layout.fillWidth: true; input.maximumLength: 500 }
                    LabelText { visible: dialog.editing === "feedback" && observationDraft.count > 0; text: Style.tr("可选：观察经验在这份作品中的表现。用户判断不是模型采用或因果关系的证明。"); Layout.fillWidth: true; color: Style.muted }
                    TextArea {
                        visible: dialog.editing === "feedback" && observationDraft.count > 0
                        objectName: "learningObservationArtifact"; Layout.fillWidth: true
                        readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                        text: (dialog.attempt.artifact_view || {}).text || ""
                        font.pixelSize: 15 * Style.scale; color: Style.ink; selectionColor: Style.soft; background: null
                    }
                    Repeater {
                        model: dialog.editing === "feedback" ? observationDraft : null
                        Panel {
                            id: observationCard
                            required property int index
                            required property var model
                            Layout.fillWidth: true; caption: model.strategy
                            ToggleRow { Layout.fillWidth: true; text: Style.tr("记录我对这条经验的观察"); checked: observationCard.model.selected; onToggled: observationDraft.setProperty(observationCard.index, "selected", checked) }
                            ColumnLayout {
                                visible: observationCard.model.selected; Layout.fillWidth: true
                                LabelText { text: Style.tr("适用性"); Layout.fillWidth: true }
                                Choice { Layout.fillWidth: true; model: dialog.fitOptions; textRole: "label"; valueRole: "id"; currentIndex: dialog.fitOptions.map(function(r) { return r.id }).indexOf(observationCard.model.fit); onActivated: observationDraft.setProperty(observationCard.index, "fit", currentValue) }
                                LabelText { text: Style.tr("作品中的体现"); Layout.fillWidth: true }
                                Choice { Layout.fillWidth: true; model: dialog.useOptions; textRole: "label"; valueRole: "id"; currentIndex: dialog.useOptions.map(function(r) { return r.id }).indexOf(observationCard.model.use); onActivated: { observationDraft.setProperty(observationCard.index, "use", currentValue); if (currentValue !== "observed") observationDraft.setProperty(observationCard.index, "effect", "uncertain") } }
                                LabelText { text: Style.tr("对这次成果的效果"); Layout.fillWidth: true }
                                Choice { Layout.fillWidth: true; enabled: observationCard.model.use === "observed"; model: dialog.effectOptions; textRole: "label"; valueRole: "id"; currentIndex: dialog.effectOptions.map(function(r) { return r.id }).indexOf(observationCard.model.effect); onActivated: observationDraft.setProperty(observationCard.index, "effect", currentValue) }
                                Field { caption: Style.tr("观察理由（最多 500 字）"); text: observationCard.model.reason; Layout.fillWidth: true; input.maximumLength: 500; onEdited: function(value) { observationDraft.setProperty(observationCard.index, "reason", value) } }
                                Field { caption: Style.tr("作品原文片段（最多 300 字）"); hint: Style.tr("认为作品体现了经验时必填；可从上方作品复制。"); text: observationCard.model.quote; Layout.fillWidth: true; input.maximumLength: 300; onEdited: function(value) { observationDraft.setProperty(observationCard.index, "quote", value) } }
                            }
                        }
                    }
                    Repeater {
                        model: dialog.editing === "feedback" ? dialog.draftItems : []
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            LabelText { text: modelData.group + " · " + modelData.text; Layout.fillWidth: true }
                            Choice { Layout.fillWidth: true; model: dialog.verdictOptions; textRole: "label"; valueRole: "id"; currentIndex: dialog.verdictOptions.map(function(r) { return r.id }).indexOf(dialog.ratings[modelData.id] || "unclear"); onActivated: { var values = Object.assign({}, dialog.ratings); values[modelData.id] = currentValue; dialog.ratings = values } }
                        }
                    }
                    LabelText { visible: dialog.editing === "complete"; text: Style.tr("为每份成果选择一次尝试。每项条件都要符合，不能拼用不同尝试的部分结果。"); Layout.fillWidth: true }
                    Repeater {
                        model: dialog.editing === "complete" ? dialog.groupNames : []
                        ColumnLayout {
                            required property string modelData
                            Layout.fillWidth: true
                            LabelText { text: modelData; Layout.fillWidth: true }
                            Choice { Layout.fillWidth: true; model: (dialog.recordsData.attempts || []).map(function(r, i) { return {id: r.id, label: String(dialog.recordsData.total - dialog.recordsData.offset - i) + " · " + (r.artifact_view.title || r.detail || r.action) + " · " + Style.tr(r.status)} }); textRole: "label"; valueRole: "id"; currentIndex: -1; onActivated: { var values = Object.assign({}, dialog.chosen); values[modelData] = currentValue; dialog.chosen = values } }
                        }
                    }
                    Field { id: reason; objectName: "learningReason"; visible: dialog.editing !== "practice" && dialog.editing !== "strategy"; caption: Style.tr(dialog.editing === "feedback" ? "具体反馈" : "理由"); Layout.fillWidth: true; input.maximumLength: dialog.editing === "feedback" ? 600 : 500 }
                    Field { id: nextStep; objectName: "learningNextStep"; visible: dialog.editing === "plan" || dialog.editing === "feedback"; caption: Style.tr("下一次怎样尝试？"); Layout.fillWidth: true; input.maximumLength: dialog.editing === "plan" ? 200 : 600 }
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
            AppButton { objectName: "saveLearning"; visible: !!dialog.editing; text: Style.tr(dialog.editing === "practice" ? "开始创作" : "保存"); primary: true; enabled: !bridge.busy && (dialog.editing !== "strategy" || (strategyText.text.trim().length > 0 && expectedResult.text.trim().length > 0 && (!allowReuse.checked || (appliesWhen.text.trim().length > 0 && avoidWhen.text.trim().length > 0)))); onClicked: dialog.save() }
        }
    }
}
