import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

ColumnLayout {
    id: page
    property int section: 0
    readonly property bool condensed: height < 360 * Style.scale
    onSectionChanged: if (scroll.contentItem) scroll.contentItem.contentY = 0
    spacing: page.condensed ? 8 : 16
    LabelText { visible: !page.condensed; text: Style.tr("布置她的家"); font.pixelSize: 30 * Style.scale; font.weight: Font.DemiBold; Layout.fillWidth: true }
    Flow {
        Layout.fillWidth: true; spacing: 8
        Repeater {
            model: ["外观", "对话", "记忆", "QQ", "聊天渠道", "插件与扩展"]
            AppButton { required property string modelData; required property int index; compact: page.condensed; text: Style.tr(modelData); quiet: true; selected: page.section === index; onClicked: page.section = index }
        }
        AppButton { compact: page.condensed; text: Style.tr("保存设置"); visible: page.section > 0 && page.section < 5; primary: true; enabled: !bridge.busy; onClicked: page.section === 4 ? bridge.saveChannel() : (page.section === 3 ? bridge.saveQQ() : bridge.saveSettings()) }
    }
    ScrollPane {
        id: scroll
        objectName: "settingsScroll"
        Layout.fillWidth: true; Layout.fillHeight: true
        contentWidth: availableWidth
        contentHeight: contentLoader.item ? contentLoader.item.implicitHeight : 0
        Loader {
            id: contentLoader
            width: scroll.availableWidth - 14
            sourceComponent: [appearance, conversation, memory, connection, channels, plugins][page.section]
        }
    }
    FileDialog {
        id: avatarFile
        title: Style.tr("选择 Live2D 模型（.model3.json）")
        nameFilters: ["Live2D Cubism (*.model3.json)"]
        onAccepted: bridge.selectAvatarModel(selectedFile.toString())
    }
    Component {
        id: appearance
        ColumnLayout {
            spacing: 16
            Panel {
                caption: Style.tr("角色与舞台")
                detail: Style.tr("形象是相遇的载体，经历从出生开始。")
                Layout.fillWidth: true
                AvatarModelHelp { Layout.fillWidth: true }
                LabelText { text: bridge.avatarModel || Style.tr("尚未选择角色模型"); Layout.fillWidth: true; color: Style.muted; font.pixelSize: 12 * Style.scale; wrapMode: Text.WrapAnywhere }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    AppButton { objectName: "selectLive2DModel"; text: Style.tr("选择角色模型"); onClicked: avatarFile.open() }
                    AppButton { text: Style.tr("清除模型选择"); quiet: true; onClicked: { bridge.preference("live2d_model", ""); bridge.reloadAvatar() } }
                    AppButton { text: Style.tr("重新加载"); quiet: true; onClicked: bridge.reloadAvatar() }
                }
                LabelText { text: Style.tr("角色大小"); Layout.fillWidth: true }
                RowLayout {
                    Layout.fillWidth: true
                    Slider {
                        Layout.fillWidth: true
                        from: 0.65; to: 1.6; stepSize: 0.05
                        value: bridge.preferences.live2d_zoom || 1.0
                        Accessible.name: Style.tr("角色大小")
                        onPressedChanged: if (!pressed) bridge.preference("live2d_zoom", value)
                        Keys.onReleased: bridge.preference("live2d_zoom", value)
                    }
                    AppButton { text: Style.tr("还原视图"); onClicked: bridge.setAvatarView(1.0, 0.0, 0.0) }
                }
                LabelText { text: Style.tr("在陪伴页拖动角色调整位置，滚轮缩放；还原视图可恢复默认大小与位置。"); Layout.fillWidth: true; color: Style.muted; font.pixelSize: 12 * Style.scale }
                LabelText { text: Style.tr("模型由本机目录读取，移动文件后请重新选择。外观设置不改变出生身份或记忆。"); Layout.fillWidth: true; color: Style.muted; font.pixelSize: 12 * Style.scale }
                LabelText { text: Style.tr("初始模型署名") + "\n" + bridge.avatarCredit; Layout.fillWidth: true; color: Style.muted; font.pixelSize: 12 * Style.scale }
            }
            Panel {
                caption: Style.tr("选一种家的颜色")
                detail: Style.tr("换一种心情，故事仍然接着写。")
                Layout.fillWidth: true
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Repeater {
                        model: [{key: "sky", title: "月白蓝", color: "#E7EFF8", ink: "#3567A1"}, {key: "mint", title: "薄荷海", color: "#DDEEE8", ink: "#286F68"}, {key: "night", title: "晚安蓝", color: "#222D3D", ink: "#96BCEA"}]
                        AppButton {
                            required property var modelData
                            Layout.fillWidth: true; implicitHeight: 92
                            text: Style.tr(modelData.title)
                            selected: Style.theme === modelData.key
                            onClicked: bridge.preference("desktop_theme", modelData.key)
                            background: Rectangle { color: modelData.color; radius: 18; border.width: parent.selected || parent.visualFocus ? 2 : 0; border.color: modelData.ink }
                            contentItem: LabelText { text: parent.text; color: modelData.ink; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        }
                    }
                }
            }
            Panel {
                caption: Style.tr("阅读与动作")
                Layout.fillWidth: true
                ToggleRow { text: Style.tr("使用更大的文字"); checked: !!bridge.preferences.desktop_large_text; Layout.fillWidth: true; onToggled: bridge.preference("desktop_large_text", checked) }
                ToggleRow { text: Style.tr("减少动态效果"); checked: !!bridge.preferences.desktop_reduced_motion; Layout.fillWidth: true; onToggled: bridge.preference("desktop_reduced_motion", checked) }
                LabelText { text: Style.tr("减少动态时，角色保持静态，所有功能照常使用。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
            }
            Panel {
                caption: Style.tr("界面语言")
                detail: Style.tr("只翻译窗口，不翻译她自己的话。")
                Layout.fillWidth: true
                Choice {
                    objectName: "languageChoice"
                    Layout.fillWidth: true
                    model: bridge.languages
                    textRole: "label"; valueRole: "code"
                    currentIndex: bridge.languages.findIndex(function(row) { return row.code === bridge.preferences.language })
                    onActivated: bridge.preference("language", currentValue)
                    Accessible.name: Style.tr("界面语言")
                }
            }
            Panel {
                caption: Style.tr("桌面陪伴")
                Layout.fillWidth: true
                ToggleRow { text: Style.tr("窗口总在最前"); checked: !!bridge.preferences.always_on_top; Layout.fillWidth: true; onToggled: bridge.preference("always_on_top", checked) }
                ToggleRow { text: Style.tr("登录电脑后打开她的房间"); checked: !!bridge.preferences.autostart; Layout.fillWidth: true; onToggled: bridge.preference("autostart", checked) }
                AppButton { text: Style.tr("打开她的文件夹"); onClicked: bridge.openFolder() }
            }
            Panel {
                caption: Style.tr("保存一份备份")
                detail: Style.tr("备份保存在生命包同级的 SEEDbank-backups 文件夹，可复制到另一块硬盘。")
                Layout.fillWidth: true
                AppButton { text: Style.tr("创建备份"); enabled: !bridge.busy; onClicked: bridge.backupNow() }
                AppButton { objectName: "openArchiveRestore"; text: Style.tr("从备份恢复"); enabled: !bridge.busy; onClicked: bridge.showArchiveManager() }
                AppButton { text: Style.tr("打开备份文件夹"); onClicked: bridge.openBackups() }
            }
        }
    }
    Component {
        id: conversation
        ColumnLayout {
            spacing: 16
            Panel {
                caption: Style.tr("选择对话方式")
                detail: Style.tr("选择服务，填写模型与自己的 API Key。使用哪个账号，由 Key 决定。")
                Layout.fillWidth: true
                ModelServiceHelp { Layout.fillWidth: true }
                Choice {
                    Layout.fillWidth: true; model: { bridge.localeRevision; return bridge.presets() }
                    textRole: "label"; currentIndex: -1; displayText: currentIndex < 0 ? Style.tr("选择对话方式") : currentText
                    onActivated: bridge.applyPreset(currentIndex)
                    Accessible.name: Style.tr("选择对话方式")
                }
                LabelText {
                    text: { bridge.localeRevision; return bridge.providerHint }
                    Layout.fillWidth: true
                    color: Style.muted
                    font.pixelSize: 13 * Style.scale
                }
                LabelText { text: Style.tr("接口类型") }
                Choice {
                    Layout.fillWidth: true; model: ["stub", "openai-compatible", "anthropic", "codex", "workbuddy"]
                    currentIndex: model.indexOf(bridge.form.adapter || "stub")
                    onActivated: bridge.editSetting("adapter", currentText)
                    Accessible.name: Style.tr("接口类型")
                }
                Repeater {
                    model: ["codex", "workbuddy"].indexOf(bridge.form.adapter) >= 0
                        ? [{key: "model", label: "模型名称"}, {key: bridge.form.adapter + "_max_calls", label: "每轮活动最多调用（1–3）"}]
                        : [{key: "model", label: "模型名称"}, {key: "base_url", label: "接口地址"}, {key: "temperature", label: "温度（0–2）"}, {key: "vision_model", label: "视觉模型（可留空）"}]
                    Field {
                        required property var modelData
                        caption: Style.tr(modelData.label); Layout.fillWidth: true
                        visible: modelData.key !== "temperature" || bridge.form.temperature_mode !== "default"
                        hint: modelData.key === "model" && bridge.remoteApi ? Style.tr("填写服务商控制台中的模型 ID；预设不代表账号已开通该模型。") : ""
                        text: String(bridge.form[modelData.key] ?? "")
                        onEdited: function(value) { bridge.editSetting(modelData.key, value) }
                    }
                }
                ColumnLayout {
                    visible: bridge.form.adapter === "openai-compatible" || bridge.form.adapter === "anthropic"
                    Layout.fillWidth: true
                    spacing: 10
                    ToggleRow {
                        Layout.fillWidth: true
                        text: Style.tr("使用模型默认温度")
                        checked: bridge.form.temperature_mode === "default"
                        onToggled: bridge.editSetting("temperature_mode", checked ? "default" : "custom")
                    }
                    ToggleRow {
                        visible: bridge.form.adapter === "openai-compatible"
                        Layout.fillWidth: true
                        text: Style.tr("启用服务端 JSON 模式")
                        checked: bridge.form.response_format_mode === "json_object"
                        onToggled: bridge.editSetting("response_format_mode", checked ? "json_object" : "prompt")
                    }
                    LabelText {
                        Layout.fillWidth: true; color: Style.muted; font.pixelSize: 13 * Style.scale
                        text: Style.tr("默认按提示生成结构化回答，应用仍会校验。确认模型支持后可开启 JSON 模式；参数不兼容时不会自动换参数重试。")
                    }
                }
                ColumnLayout {
                    visible: bridge.remoteApi
                    Layout.fillWidth: true
                    spacing: 10
                    LabelText { text: Style.tr("密钥方式") }
                    Choice {
                        Layout.fillWidth: true
                        model: [Style.tr("填写 API Key（本机加密保存）"), Style.tr("环境变量（高级）")]
                        currentIndex: bridge.form.api_key_source === "local" ? 0 : 1
                        onActivated: bridge.editSetting("api_key_source", currentIndex === 0 ? "local" : "env")
                        Accessible.name: Style.tr("密钥方式")
                        enabled: !bridge.busy
                    }
                    Field {
                        visible: bridge.form.api_key_source === "local"
                        Layout.fillWidth: true
                        enabled: !bridge.busy
                        caption: "API Key"
                        secret: true
                        text: bridge.apiKeyDraft
                        hint: bridge.apiKeyStatus
                        onEdited: function(value) { bridge.editApiKey(value) }
                    }
                    LabelText {
                        visible: bridge.form.api_key_source === "local"
                        text: Style.tr("Key 由 Windows 当前用户加密保存，不写入生命包或备份。换电脑后需重新填写。")
                        color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale
                    }
                    Field {
                        visible: bridge.form.api_key_source !== "local"
                        caption: Style.tr("密钥环境变量名")
                        Layout.fillWidth: true
                        text: String(bridge.form.api_key_env ?? "")
                        hint: Style.tr("这里填写变量名，例如 OPENAI_API_KEY；实际 Key 放在该环境变量中。")
                        onEdited: function(value) { bridge.editSetting("api_key_env", value) }
                    }
                    LabelText {
                        text: Style.tr("API Key 属于你选择的模型服务账号，与浏览器或 ChatGPT 当前登录账号无关。测试连接会发出请求，并可能产生费用。")
                        color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale
                    }
                }
                LabelText { visible: bridge.form.adapter === "codex"; text: Style.tr("使用本机 Codex 的 ChatGPT 登录与账号额度；无需填写密钥。当前支持文字，图片仅归档。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                LabelText { visible: bridge.form.adapter === "codex"; text: Style.tr("每轮默认最多调用两次，共用于回答、回查和随后创作。主动活动、每篇日记分别计一轮；使用低推理量。这不是 token 硬上限，测试连接也会使用账号额度。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                LabelText { visible: bridge.form.adapter === "workbuddy"; text: Style.tr("先在 CodeBuddy CLI 登录与 WorkBuddy 相同的账号，再填写该账号可用的模型 ID。不会自动同步桌面模型；仅文字，测试连接会使用账号额度。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                LabelText { visible: bridge.form.adapter === "workbuddy"; text: Style.tr("每轮默认最多调用两次，共用于回答、回查和随后创作；这不是 token 或积分硬上限。连接失败后暂停自动请求，成功发送消息或重新保存设置后再继续。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                AppButton { visible: bridge.form.adapter === "workbuddy"; text: Style.tr("打开 CodeBuddy 官方安装与登录指南"); onClicked: Qt.openUrlExternally("https://www.codebuddy.cn/docs/cli/quickstart") }
                LabelText { text: Style.tr("照片和 WAV 原件会保存在生命包，并随完整备份保留。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                LabelText { visible: ["codex", "workbuddy"].indexOf(bridge.form.adapter) < 0; text: Style.tr("递交照片时可能向已配置的视觉模型发送图片并产生费用；日常文字聊天不会自动重发原图。"); color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                RowLayout {
                    AppButton { text: Style.tr("测试连接"); enabled: !bridge.busy; onClicked: bridge.testConnection() }
                    AppButton { text: Style.tr("发现本地模型"); enabled: !bridge.busy; onClicked: bridge.discover() }
                }
                LabelText { visible: bridge.form.adapter === "codex"; text: bridge.codexUsage; color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                AppButton { visible: bridge.form.adapter === "codex"; text: Style.tr("刷新本机 GPT 用量"); onClicked: bridge.refreshCodexUsage() }
                LabelText { visible: bridge.form.adapter === "workbuddy"; text: bridge.workbuddyUsage; color: Style.muted; Layout.fillWidth: true; font.pixelSize: 13 * Style.scale }
                AppButton { visible: bridge.form.adapter === "workbuddy"; text: Style.tr("刷新本机 WorkBuddy 用量"); onClicked: bridge.refreshWorkBuddyUsage() }
            }
            Panel {
                caption: Style.tr("本机可用的模型")
                detail: Style.tr("选择后先填入草稿，保存后生效。")
                visible: bridge.localModels.length > 0
                Layout.fillWidth: true
                Repeater {
                    model: bridge.localModels
                    AppButton { required property var modelData; required property int index; Layout.fillWidth: true; text: modelData.label + " · " + modelData.model; onClicked: bridge.chooseModel(index) }
                }
            }
            ContinuityPanel { Layout.fillWidth: true }
        }
    }
    Component {
        id: memory
        ColumnLayout {
            spacing: 16
            Panel {
                Layout.fillWidth: true
                caption: Style.tr("记忆的节奏")
                detail: Style.tr("她会从经历中挑选值得留下的片段。")
                ToggleRow { text: Style.tr("过滤重复与空泛的记忆"); checked: !!bridge.form.strict; Layout.fillWidth: true; onToggled: bridge.editSetting("strict", checked) }
                Field { caption: Style.tr("每轮最多提炼几条（1–50）"); text: String(bridge.form.daily_max ?? 8); Layout.fillWidth: true; onEdited: function(value) { bridge.editSetting("daily_max", value) } }
            }
            Panel { caption: Style.tr("时间慢慢往前走"); detail: Style.tr("每过一个凌晨就进入新的一天；没有运行的日子不会伪造经历。"); Layout.fillWidth: true }
            Panel { caption: Style.tr("放下，不抹去"); detail: Style.tr("在记忆页可以让她停止主动回忆某一条，原始历史仍保留。"); Layout.fillWidth: true }
            SemanticPanel { Layout.fillWidth: true }
        }
    }
    Component {
        id: channels
        ChannelPanel { }
    }
    Component {
        id: plugins
        PluginPanel { onSectionRequested: function(section) { page.section = section } }
    }
    Component {
        id: connection
        ColumnLayout {
            spacing: 16
            Panel {
                caption: Style.tr("从 QQ 来看她")
                detail: Style.tr("连接你已有的第三方 OneBot 桥；这里只负责接收和回复消息。")
                Layout.fillWidth: true
                Repeater {
                    model: [{key: "owner", label: "主人 QQ 号", fallback: ""}, {key: "groups", label: "群白名单（逗号分隔）", fallback: ""}, {key: "self_id", label: "她使用的 QQ 号", fallback: ""}, {key: "onebot_http", label: "OneBot HTTP 地址", fallback: "http://127.0.0.1:3001"}, {key: "port", label: "本机上报端口", fallback: "8790"}, {key: "secret_env", label: "上报签名密钥环境变量", fallback: "SEEDBANK_ONEBOT_SECRET"}]
                    Field { required property var modelData; caption: Style.tr(modelData.label); text: String(bridge.qqForm[modelData.key] ?? modelData.fallback); Layout.fillWidth: true; onEdited: function(value) { bridge.editQQ(modelData.key, value) } }
                }
                LabelText { text: Style.tr("访问令牌使用环境变量 SEEDBANK_ONEBOT_TOKEN，不写进配置。"); Layout.fillWidth: true; font.pixelSize: 13 * Style.scale; color: Style.muted }
                LabelText { text: Style.tr("上报密钥默认使用 SEEDBANK_ONEBOT_SECRET；请在 OneBot HTTP 上报的 secret 中填写相同密钥。此处只填写变量名，未配置密钥不能启动连接。"); Layout.fillWidth: true; font.pixelSize: 13 * Style.scale; color: Style.muted }
                RowLayout {
                    AppButton { text: bridge.qqRunning ? Style.tr("停止连接") : Style.tr("启动连接"); enabled: !bridge.busy; onClicked: bridge.toggleQQ() }
                    AppButton { text: Style.tr("测试连接"); enabled: !bridge.busy; onClicked: bridge.testQQ() }
                }
                LabelText { objectName: "qqDeliveryStatus"; text: bridge.qqStatusText; color: Style.accent; Layout.fillWidth: true }
            }
            ObservationPanel { qqMode: true; Layout.fillWidth: true }
            Panel { caption: Style.tr("连接方法"); detail: Style.tr("先在 SnowLuma、NapCat 或 LLOneBot 中开启 HTTP 服务，将消息上报地址设为 http://127.0.0.1:上报端口/。保存后点击启动连接。"); Layout.fillWidth: true }
        }
    }
}
