import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs as Native

ColumnLayout {
    id: page
    objectName: "pluginPanel"
    spacing: 16
    signal sectionRequested(int section)
    property string selectedId: ""
    readonly property var selected: bridge.plugins.find(function(row) { return row.id === page.selectedId }) || bridge.plugins[0] || ({})
    readonly property var result: bridge.pluginOutput.id === selected.id ? bridge.pluginOutput : ({})
    property string confirmId: ""
    property string confirmName: ""
    function settingsValues() {
        let values = {}
        for (let i = 0; i < fields.count; i++) {
            const field = fields.itemAt(i)
            if (field) values[field.fieldKey] = field.draft
        }
        return values
    }
    Component.onCompleted: bridge.refreshPlugins()

    Panel {
        Layout.fillWidth: true
        caption: Style.tr("给生活添一种工具")
        detail: Style.tr("添加可信来源的本地插件，按需运行。结果由你查看，不会自动写成她的记忆。")
        Flow {
            Layout.fillWidth: true; spacing: 8
            AppButton { objectName: "addLocalPlugin"; text: Style.tr("添加本地插件"); primary: true; enabled: !bridge.busy; onClicked: picker.open() }
            AppButton { objectName: "addExamplePlugin"; text: Style.tr("添加便签示例"); enabled: !bridge.busy; onClicked: bridge.addExamplePlugin() }
            AppButton { text: Style.tr("刷新列表"); quiet: true; enabled: !bridge.busy; onClicked: bridge.refreshPlugins() }
            AppButton { text: Style.tr("插件开发文档"); quiet: true; onClicked: bridge.pluginDeveloperGuide() }
        }
        LabelText {
            Layout.fillWidth: true; color: Style.muted; font.pixelSize: 13 * Style.scale
            text: Style.tr("当前提供手动文本插件；没有插件商店、自动更新或权限沙箱。只安装你信任的代码。")
        }
    }
    Panel {
        Layout.fillWidth: true
        caption: Style.tr("我的插件")
        LabelText { Layout.fillWidth: true; visible: bridge.plugins.length === 0; color: Style.muted; text: Style.tr("还没有插件。可先添加便签示例，了解安装、配置和运行流程。") }
        Choice {
            objectName: "pluginChoice"
            visible: bridge.plugins.length > 0; Layout.fillWidth: true
            model: bridge.plugins; textRole: "name"; valueRole: "id"
            currentIndex: Math.max(0, bridge.plugins.findIndex(function(row) { return row.id === page.selected.id }))
            onActivated: page.selectedId = currentValue
            Accessible.name: Style.tr("我的插件")
        }
        ColumnLayout {
            visible: !!page.selected.id; Layout.fillWidth: true; spacing: 12
            LabelText {
                Layout.fillWidth: true; textFormat: Text.PlainText; font.weight: Font.DemiBold
                text: (page.selected.name || "") + " · " + (page.selected.version || "") + " · " + (page.selected.author || "")
            }
            LabelText { Layout.fillWidth: true; textFormat: Text.PlainText; text: page.selected.description || ""; visible: text.length > 0 }
            LabelText {
                Layout.fillWidth: true; color: page.selected.error ? Style.danger : Style.muted; textFormat: Text.PlainText
                text: page.selected.error ? Style.tr(page.selected.error) : (page.selected.enabled ? Style.tr("已启用 · 仅在点击运行后执行") : Style.tr("已停用 · 不会执行"))
            }
            LabelText {
                Layout.fillWidth: true; color: Style.muted
                text: Style.tr("作者声明的访问：") + ((page.selected.access || []).map(function(item) { return Style.tr(item === "network" ? "网络" : "本地文件") }).join("、") || Style.tr("无额外访问"))
            }
            Flow {
                Layout.fillWidth: true; spacing: 8
                AppButton {
                    objectName: "enablePlugin"
                    text: page.selected.enabled ? Style.tr("停用插件") : Style.tr("启用插件")
                    primary: !page.selected.enabled
                    enabled: !bridge.busy && !page.selected.error
                    onClicked: {
                        if (page.selected.enabled) bridge.enablePlugin(page.selected.id, false)
                        else {
                            page.confirmId = page.selected.id
                            page.confirmName = page.selected.name + " · " + page.selected.author + " · " + page.selected.version
                            trust.open()
                        }
                    }
                }
                AppButton { text: Style.tr("打开插件文件夹"); enabled: !page.selected.error; onClicked: bridge.openPluginFolder(page.selected.id) }
                AppButton { text: Style.tr("从列表移除"); danger: true; enabled: !bridge.busy; onClicked: { page.confirmId = page.selected.id; page.confirmName = page.selected.name; remove.open() } }
            }
            LabelText { Layout.fillWidth: true; visible: (page.selected.settings || []).length > 0; color: Style.muted; font.pixelSize: 13 * Style.scale; text: Style.tr("配置以明文保存在本机插件目录，请勿填写 API Key、密码或其他秘密。") }
            Repeater {
                id: fields
                model: page.selected.settings || []
                ColumnLayout {
                    required property var modelData
                    property string fieldKey: modelData.key
                    property string draft: String((page.selected.config || {})[fieldKey] ?? modelData.default)
                    Layout.fillWidth: true
                    LabelText { Layout.fillWidth: true; textFormat: Text.PlainText; text: modelData.label }
                    Field {
                        Layout.fillWidth: true; compact: true; caption: modelData.label; text: parent.draft
                        input.maximumLength: 1000
                        onEdited: function(value) { parent.draft = value }
                    }
                }
            }
            AppButton {
                visible: fields.count > 0; text: Style.tr("保存插件配置"); enabled: !bridge.busy && !page.selected.error
                onClicked: bridge.configurePlugin(page.selected.id, page.settingsValues())
            }
        }
    }
    Panel {
        Layout.fillWidth: true; visible: !!page.selected.id && !page.selected.error
        caption: Style.tr("手动运行")
        detail: Style.tr("只传入下方文字和插件配置；不会由宿主自动附带生命包、聊天记录或模型密钥。单次最多 30 秒。")
        LongField { id: input; objectName: "pluginInput"; Layout.fillWidth: true; caption: Style.tr("交给插件的文字"); enabled: !bridge.busy }
        LabelText { Layout.fillWidth: true; text: input.text.length + " / 4000"; color: input.text.length > 4000 ? Style.danger : Style.muted; horizontalAlignment: Text.AlignRight }
        Flow {
            Layout.fillWidth: true; spacing: 8
            AppButton {
                objectName: "runPlugin"; text: Style.tr("运行插件"); primary: true
                enabled: !bridge.busy && bridge.lifeActive && page.selected.enabled === true && input.text.length <= 4000
                onClicked: bridge.runPlugin(page.selected.id, input.text, page.settingsValues())
            }
            AppButton { objectName: "stopPlugin"; visible: bridge.runningPlugin !== ""; text: Style.tr("停止运行"); danger: true; onClicked: bridge.stopPlugin() }
        }
        LabelText { Layout.fillWidth: true; visible: !bridge.lifeActive; color: Style.muted; text: Style.tr("休眠期间不运行插件。") }
        LabelText { Layout.fillWidth: true; visible: bridge.runningPlugin === page.selected.id; color: Style.muted; text: Style.tr("插件正在运行…") }
        TextArea {
            objectName: "pluginResult"
            visible: !!page.result.id; Layout.fillWidth: true
            readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.WrapAnywhere
            text: page.result.text || (page.result.id ? Style.tr("插件已完成，没有返回文字。") : "")
            color: page.result.error ? Style.danger : Style.ink; font.pixelSize: 14 * Style.scale; padding: 14
            implicitHeight: Math.max(100, contentHeight + 28)
            background: Rectangle { color: Style.field; radius: 12; border.color: Style.line }
            Accessible.name: Style.tr("插件结果")
        }
    }
    Panel {
        Layout.fillWidth: true; caption: Style.tr("已有的连接能力")
        detail: Style.tr("模型服务和聊天渠道已有独立设置，也欢迎开发新的适配器。")
        Flow {
            Layout.fillWidth: true; spacing: 8
            AppButton { text: Style.tr("模型服务"); onClicked: page.sectionRequested(1) }
            AppButton { text: "QQ / OneBot"; onClicked: page.sectionRequested(3) }
            AppButton { text: Style.tr("聊天渠道"); onClicked: page.sectionRequested(4) }
        }
    }
    Native.FileDialog {
        id: picker; title: Style.tr("添加本地插件"); nameFilters: ["SeedBank plugin (plugin.json)"]
        onAccepted: bridge.addPlugin(selectedFile.toString())
    }
    Dialog {
        id: trust; objectName: "pluginTrustDialog"
        parent: Overlay.overlay; anchors.centerIn: parent; width: Math.min(560, parent ? parent.width - 32 : 560)
        modal: true; title: Style.tr("确认插件来源")
        header: LabelText { text: trust.title; padding: 20; font.weight: Font.DemiBold }
        background: Rectangle { color: Style.surface; radius: 18; border.color: Style.line }
        contentItem: ColumnLayout {
            spacing: 16
            LabelText { Layout.fillWidth: true; textFormat: Text.PlainText; text: page.confirmName; font.weight: Font.DemiBold }
            LabelText { Layout.fillWidth: true; text: Style.tr("插件会以当前系统用户的权限执行代码，可以自行访问文件和网络。独立进程不是权限沙箱，访问声明也不是强制限制。") }
            LabelText { Layout.fillWidth: true; color: Style.muted; text: Style.tr("启用不会自动运行。请先查看代码与来源；确认信任后再启用。") }
            Flow {
                Layout.fillWidth: true; spacing: 8
                AppButton { text: Style.tr("取消"); onClicked: trust.close() }
                AppButton { objectName: "confirmEnablePlugin"; text: Style.tr("信任并启用"); primary: true; enabled: !bridge.busy; onClicked: { bridge.enablePlugin(page.confirmId, true); trust.close() } }
            }
        }
    }
    Dialog {
        id: remove
        parent: Overlay.overlay; anchors.centerIn: parent; width: Math.min(520, parent ? parent.width - 32 : 520)
        modal: true; title: Style.tr("从列表移除")
        header: LabelText { text: remove.title; padding: 20; font.weight: Font.DemiBold }
        background: Rectangle { color: Style.surface; radius: 18; border.color: Style.line }
        contentItem: ColumnLayout {
            spacing: 16
            LabelText { Layout.fillWidth: true; textFormat: Text.PlainText; text: page.confirmName }
            LabelText { Layout.fillWidth: true; text: Style.tr("移除登记并停用插件，保留本机插件文件。再次添加后需要重新确认启用。") }
            Flow {
                Layout.fillWidth: true; spacing: 8
                AppButton { text: Style.tr("取消"); onClicked: remove.close() }
                AppButton { text: Style.tr("从列表移除"); danger: true; enabled: !bridge.busy; onClicked: { bridge.removePlugin(page.confirmId); remove.close() } }
            }
        }
    }
}
