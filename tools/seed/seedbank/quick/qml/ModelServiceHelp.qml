import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: help
    property bool expanded: false
    spacing: 8
    LabelText {
        Layout.fillWidth: true
        text: Style.tr("支持 OpenAI、DeepSeek、Claude、Gemini 等云端 API，以及本地模型服务。")
        color: Style.muted; font.pixelSize: 13 * Style.scale
    }
    AppButton {
        objectName: "modelServiceHelpToggle"
        Layout.fillWidth: true; implicitWidth: 0
        implicitHeight: Math.max(36 * Style.scale, contentItem.implicitHeight + 12)
        compact: true; selected: help.expanded
        text: Style.tr(help.expanded ? "收起接入说明" : "查看支持的服务与接入方式")
        onClicked: help.expanded = !help.expanded
        contentItem: LabelText { text: parent.text; font.pixelSize: 13 * Style.scale; horizontalAlignment: Text.AlignHCenter }
    }
    ColumnLayout {
        visible: help.expanded
        Layout.fillWidth: true; spacing: 8
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("云端预设：OpenAI、DeepSeek、Claude / Anthropic、Google Gemini、通义千问、豆包、Kimi、智谱 GLM、MiniMax、硅基流动、OpenRouter、百度千帆、腾讯混元。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("本地服务：Ollama、LM Studio、vLLM。先在本机加载模型并启动兼容接口，再填写对应的模型 ID。这里不直接导入 GGUF 或模型权重文件。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("其他服务可按 OpenAI Chat Completions 或 Anthropic Messages 兼容协议填写。Codex 登录是独立的文字入口；不联网模式只提供固定模板。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("WorkBuddy 账号可通过同账号登录的 CodeBuddy CLI 接入；需单独安装、登录并填写模型 ID，不会自动同步桌面选择。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("使用自己的 API Key 和账号可用的模型 ID。预设不代表每个模型均已实测；图片、结构化回答等能力取决于所选模型与接口。角色外观请在“设置 → 外观”中选择。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
    }
}
