import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: help
    property bool expanded: false
    spacing: 8
    LabelText {
        Layout.fillWidth: true
        text: Style.tr("角色模型：Live2D（.model3.json）")
        color: Style.accent; font.pixelSize: 13 * Style.scale; font.weight: Font.Medium
    }
    LabelText {
        Layout.fillWidth: true
        text: Style.tr("先解压完整模型文件夹，再选择其中的 .model3.json。")
        color: Style.muted; font.pixelSize: 13 * Style.scale
    }
    AppButton {
        objectName: "avatarModelHelpToggle"
        Layout.fillWidth: true; implicitWidth: 0
        implicitHeight: Math.max(36 * Style.scale, contentItem.implicitHeight + 12)
        compact: true; selected: help.expanded
        text: Style.tr(help.expanded ? "收起格式说明" : "支持格式与准备方式")
        onClicked: help.expanded = !help.expanded
        contentItem: LabelText { text: parent.text; font.pixelSize: 13 * Style.scale; horizontalAlignment: Text.AlignHCenter }
    }
    ColumnLayout {
        visible: help.expanded
        Layout.fillWidth: true; spacing: 8
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("需要 .moc3、纹理，以及配置引用的动作、表情等文件；请保留原有目录结构。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("不能直接加载压缩包、PNG / PSD 图片、.cmo3 工程、旧版 .model.json 或 VRM / FBX 模型。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("显示兼容性取决于模型导出版本。自动表情与招手需要适配；其他模型不一定具有相同表现。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
        LabelText {
            Layout.fillWidth: true
            text: Style.tr("请使用获授权的模型。对话 AI 在“设置 → 对话”中配置，与角色外观分开。")
            color: Style.muted; font.pixelSize: 13 * Style.scale
        }
    }
}
