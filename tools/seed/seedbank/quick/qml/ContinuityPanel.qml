import QtQuick
import QtQuick.Layouts

Panel {
    id: panel
    objectName: "continuityPanel"
    caption: Style.tr("换模型前后的档案理解")
    detail: Style.tr("先创建样本，再保存新模型，最后检查同一份样本。两个操作都会将样本发送给已配置的模型服务，可能产生费用。")
    Component.onCompleted: bridge.assessContinuity("status")
    LabelText {
        Layout.fillWidth: true
        text: Style.tr("结果只反映有限样本的读取、引用和状态区分；未覆盖项不算通过，也不能证明人格同一性。")
        color: Style.muted; font.pixelSize: 13 * Style.scale
    }
    AppButton {
        objectName: "continuityCapture"
        Layout.fillWidth: true
        text: Style.tr("创建对照样本（调用模型）")
        enabled: !bridge.busy && !bridge.conversationDirty
        onClicked: bridge.assessContinuity("capture")
    }
    AppButton {
        objectName: "continuityCheck"
        Layout.fillWidth: true
        text: Style.tr("用已保存模型检查")
        enabled: !bridge.busy && !bridge.conversationDirty && !!bridge.continuity.has_baseline
        onClicked: bridge.assessContinuity("check")
    }
    LabelText {
        Layout.fillWidth: true; visible: bridge.conversationDirty
        text: Style.tr("请先保存对话设置，评估使用已保存的模型。")
        color: Style.muted
    }
    LabelText {
        objectName: "continuityResult"
        Layout.fillWidth: true
        text: { bridge.localeRevision; return bridge.continuityText }
    }
    AppButton { text: Style.tr("刷新评估记录"); enabled: !bridge.busy; onClicked: bridge.assessContinuity("status") }
    AppButton { text: Style.tr("打开评估文件夹"); enabled: !!bridge.continuity.has_baseline; onClicked: bridge.openContinuityFolder() }
}
