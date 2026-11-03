import QtQuick
import QtQuick.Layouts

Panel {
    id: panel
    objectName: "semanticPanel"
    property bool advanced: false
    caption: Style.tr("换一种说法，也能回想")
    detail: Style.tr("可选的语义检索需要嵌入模型，与聊天模型分开配置。默认关闭。")
    Component.onCompleted: bridge.semanticIndex("status")
    ToggleRow {
        objectName: "semanticEnabled"
        Layout.fillWidth: true
        text: Style.tr("启用语义回忆")
        checked: !!bridge.form.semantic_enabled
        onToggled: bridge.editSetting("semantic_enabled", checked)
    }
    LabelText {
        Layout.fillWidth: true
        text: Style.tr("开启并保存后，查询和允许回查的记忆片段会发送给所填服务，可能产生费用。本机服务可让内容留在本机。")
        color: Style.muted; font.pixelSize: 13 * Style.scale
    }
    Repeater {
        model: [{key: "semantic_model", label: "嵌入模型名称"}, {key: "semantic_base_url", label: "嵌入接口根地址"}, {key: "semantic_api_key_env", label: "嵌入服务密钥环境变量名"}]
        Field {
            required property var modelData
            Layout.fillWidth: true; caption: Style.tr(modelData.label)
            text: String(bridge.form[modelData.key] ?? "")
            onEdited: function(value) { bridge.editSetting(modelData.key, value) }
        }
    }
    LabelText { Layout.fillWidth: true; color: Style.muted; font.pixelSize: 13 * Style.scale; text: Style.tr("接口需兼容 /embeddings。填写模型服务的根地址，例如 http://localhost:11434/v1；密钥只填写环境变量名。") }
    LabelText { Layout.fillWidth: true; color: Style.muted; font.pixelSize: 13 * Style.scale; text: Style.tr("索引包括允许回查的经历和日记，以及未放下的旧版本；相似不等于事实相同。") }
    AppButton { text: Style.tr("更多模型选项"); selected: panel.advanced; onClicked: panel.advanced = !panel.advanced }
    ColumnLayout {
        Layout.fillWidth: true; visible: panel.advanced
        Repeater {
            model: [{key: "semantic_min_similarity", label: "相似度下限（0–1）"}, {key: "semantic_revision", label: "模型版本标记"}, {key: "semantic_query_prefix", label: "查询前缀（按模型要求）"}, {key: "semantic_document_prefix", label: "片段前缀（按模型要求）"}]
            Field {
                required property var modelData
                Layout.fillWidth: true; caption: Style.tr(modelData.label)
                text: String(bridge.form[modelData.key] ?? "")
                onEdited: function(value) { bridge.editSetting(modelData.key, value) }
            }
        }
        LabelText { Layout.fillWidth: true; color: Style.muted; text: Style.tr("同名模型更新后请更改版本标记，或清空该模型缓存。相似度下限需用你的记录调整，不代表事实可信度。") }
    }
    LabelText {
        objectName: "semanticProgress"
        Layout.fillWidth: true
        text: Style.tr("当前索引模型") + ": " + (bridge.semantic.model || "—")
              + "\n" + Style.tr("已索引片段") + ": " + (bridge.semantic.indexed_chunks ?? "—") + " / " + (bridge.semantic.total_chunks ?? "—")
              + "\n" + Style.tr("待补充片段") + ": " + (bridge.semantic.pending_chunks ?? "—")
    }
    LabelText {
        Layout.fillWidth: true; color: Style.muted
        visible: !!bridge.semantic.last_query && bridge.semantic.last_query.state === "lexical_fallback"
        text: Style.tr("最近一次语义检索不可用，已继续使用文字检索。")
    }
    AppButton {
        objectName: "semanticIndex"
        Layout.fillWidth: true
        text: Style.tr("补充下一批索引（调用服务）")
        enabled: !bridge.busy && !bridge.conversationDirty && !!bridge.form.semantic_enabled
        onClicked: bridge.semanticIndex("index")
    }
    LabelText { Layout.fillWidth: true; color: Style.muted; font.pixelSize: 13 * Style.scale; text: Style.tr("每批最多 64 个片段；启用后，每次回忆也会补充最多 8 个。未索引内容仍可按文字回查。") }
    AppButton { text: Style.tr("刷新索引状态（不调用服务）"); enabled: !bridge.busy; onClicked: bridge.semanticIndex("status") }
    AppButton { text: Style.tr("清空此模型的语义缓存"); enabled: !bridge.busy && !bridge.conversationDirty; onClicked: bridge.semanticIndex("clear") }
    LabelText { Layout.fillWidth: true; visible: bridge.conversationDirty; text: Style.tr("请先保存语义检索设置。"); color: Style.muted }
}
