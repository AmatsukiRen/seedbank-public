pragma Singleton
import QtQuick

QtObject {
    readonly property string theme: !bridge.preferences.desktop_theme || bridge.preferences.desktop_theme === "cream" ? "sky" : bridge.preferences.desktop_theme
    readonly property bool dark: theme === "night"
    readonly property bool mint: theme === "mint"
    readonly property real scale: bridge.preferences.desktop_large_text ? 1.15 : 1
    readonly property bool reduced: !!bridge.preferences.desktop_reduced_motion
    readonly property color background: dark ? "#161E2B" : mint ? "#F3F7F5" : "#F3F6FA"
    readonly property color surface: dark ? "#222D3D" : "#FFFFFF"
    readonly property color ink: dark ? "#E8EFF8" : mint ? "#243E3B" : "#243449"
    readonly property color muted: dark ? "#B0BED1" : mint ? "#536D68" : "#5C6E84"
    readonly property color accent: dark ? "#96BCEA" : mint ? "#286F68" : "#3567A1"
    readonly property color accentText: dark ? "#162637" : "#FFFFFF"
    readonly property color soft: dark ? "#2A3D55" : mint ? "#DDEEE8" : "#E3EDF9"
    readonly property color field: dark ? "#293647" : mint ? "#E8F0EC" : "#EAF0F6"
    readonly property color line: dark ? "#394A60" : mint ? "#DCE8E2" : "#DCE5EF"
    readonly property color stage: dark ? "#1C2B40" : mint ? "#E5F1ED" : "#E7EFF8"
    readonly property color danger: dark ? "#FFB3BD" : "#A1394B"
    // Action surfaces stay distinct from both cards and editable fields.
    readonly property color button: dark ? "#30435A" : mint ? "#E9F4EF" : "#EDF3FB"
    readonly property color buttonHover: dark ? "#3B526D" : mint ? "#D8EBE2" : "#DDE9F8"
    readonly property color buttonPressed: dark ? "#425E7D" : mint ? "#C7DFD4" : "#CBDDF2"
    readonly property color buttonBorder: dark ? "#8198B4" : mint ? "#678B7C" : "#6F89A8"
    readonly property color buttonSelected: dark ? "#324F70" : mint ? "#D2E9DE" : "#D7E6F8"
    readonly property color accentHover: dark ? "#B0CEF2" : mint ? "#21635D" : "#2C5B93"
    readonly property color accentPressed: dark ? "#82ACE1" : mint ? "#19534D" : "#234C7D"
    readonly property color dangerSurface: dark ? "#442F3B" : "#FFF0F3"
    readonly property color dangerHover: dark ? "#593B4A" : "#FBE0E7"
    readonly property color dangerPressed: dark ? "#6C4656" : "#F4CDD7"
    readonly property color dangerBorder: dark ? "#C5899C" : "#B86D81"
    readonly property color dock: dark ? "#ED2C344C" : "#EEFFFFFF"
    readonly property int duration: reduced ? 0 : 160
    function tr(text, values) {
        bridge.localeRevision
        var translated = bridge.translate(text)
        if (values) Object.keys(values).forEach(function(key) {
            translated = translated.split("{" + key + "}").join(String(values[key]))
        })
        return translated
    }
}
