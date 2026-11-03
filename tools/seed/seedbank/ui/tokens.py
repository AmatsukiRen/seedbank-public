"""UI 设计令牌：配色、字体、间距、皮肤规格。

1.23 起界面重写为「皮肤素材 + 组件系统 + 页面层」。这个模块只放数据与
纯函数，不碰 tkinter 控件；window.py 和 ui.widgets 都从这里取颜色。
"""

from __future__ import annotations

DEFAULT_THEME = "deep"

THEME_ROLES = [
    "BG",
    "PANEL",
    "SURFACE",
    "SURFACE_HI",
    "CARD",
    "CARD_HI",
    "INPUT_BG",
    "BORDER",
    "BORDER_HI",
    "TEXT",
    "TEXT_SOFT",
    "MUTED",
    "FAINT",
    "ACCENT",
    "ACCENT_HI",
    "ACCENT_DEEP",
    "ACCENT_SOFT",
    "ACCENT_LINE",
    "ACCENT_TXT",
    "SENSE",
    "GOLD",
    "SENSE_SOFT",
    "SENSE_LINE",
    "ERROR",
    "OK",
    "HER_BUBBLE",
    "HER_BUBBLE_LINE",
    "DANGER_SOFT",
    "DANGER_LINE",
    "DANGER_HOVER",
    "DIARY_BG",
    "DIARY_LINE",
    "GUEST_BG",
    "GUEST_LINE",
    "GUEST_FG",
    "ENERGY_TRACK",
    "SCROLL",
    "SCROLL_HI",
    "SIDEBAR_BG",
    "SIDEBAR_LINE",
    "NAV_SELECTED",
    "NAV_HOVER",
    "TITLEBAR_BG",
    "TITLEBAR_LINE",
    "TITLEBAR_HOVER",
    "TITLEBAR_CLOSE",
    "DISABLED_FILL",
    "TRACK_OFF",
    "KNOB",
    "WINDOW_ICON_HOVER",
    "PET_SHADOW",
    "ON_ACCENT",
    "BG_TOP",
    "BG_BOTTOM",
    "GLOW_A",
    "GLOW_B",
    "GLASS",
    "GLASS_HI",
    "GLASS_LINE",
]

THEME_ORDER = [
    "deep",
    "violet",
    "amber",
    "forest",
    "dawn",
]

THEME_LABELS = {
    "deep": "深海蓝",
    "violet": "夜紫",
    "amber": "琥珀暖",
    "forest": "森林绿",
    "dawn": "晨光",
}

# 五套完整调色板：每套都要包含 THEME_ROLES 里的全部角色。
THEMES = {
    "deep": {
        "BG": "#0b1220",
        "PANEL": "#0f172a",
        "SURFACE": "#16233a",
        "SURFACE_HI": "#1d2c46",
        "CARD": "#142033",
        "CARD_HI": "#1b2a42",
        "INPUT_BG": "#0d1626",
        "BORDER": "#243449",
        "BORDER_HI": "#33506f",
        "TEXT": "#ebf1fb",
        "TEXT_SOFT": "#c6d3e6",
        "MUTED": "#8fa1b8",
        "FAINT": "#6b7f99",
        "ACCENT": "#6fb7ff",
        "ACCENT_HI": "#9ccfff",
        "ACCENT_DEEP": "#2f5d9e",
        "ACCENT_SOFT": "#132b44",
        "ACCENT_LINE": "#2f5a80",
        "ACCENT_TXT": "#f2faff",
        "SENSE": "#E3B341",
        "GOLD": "#D29922",
        "SENSE_SOFT": "#332B14",
        "SENSE_LINE": "#5C4A1E",
        "ERROR": "#F85149",
        "OK": "#3FB950",
        "HER_BUBBLE": "#15243a",
        "HER_BUBBLE_LINE": "#243a55",
        "DANGER_SOFT": "#33201F",
        "DANGER_LINE": "#5A3330",
        "DANGER_HOVER": "#422523",
        "DIARY_BG": "#122032",
        "DIARY_LINE": "#243a55",
        "GUEST_BG": "#2B2D32",
        "GUEST_LINE": "#3A3C42",
        "GUEST_FG": "#E8E8EA",
        "ENERGY_TRACK": "#1c2c42",
        "SCROLL": "#22364f",
        "SCROLL_HI": "#35506f",
        "SIDEBAR_BG": "#081020",
        "SIDEBAR_LINE": "#303237",
        "NAV_SELECTED": "#16283f",
        "NAV_HOVER": "#101c30",
        "TITLEBAR_BG": "#080e1a",
        "TITLEBAR_LINE": "#303237",
        "TITLEBAR_HOVER": "#35383E",
        "TITLEBAR_CLOSE": "#F85149",
        "DISABLED_FILL": "#33363B",
        "TRACK_OFF": "#2a3d5a",
        "KNOB": "#f4f7ff",
        "WINDOW_ICON_HOVER": "#ffffff",
        "PET_SHADOW": "#16171A",
        "ON_ACCENT": "#08131f",
    },
    "violet": {
        "BG": "#151226",
        "PANEL": "#0e0b18",
        "SURFACE": "#0e0b18",
        "SURFACE_HI": "#151024",
        "CARD": "#171224",
        "CARD_HI": "#211a33",
        "INPUT_BG": "#0c0917",
        "BORDER": "#2a2140",
        "BORDER_HI": "#3d3059",
        "TEXT": "#efe9fb",
        "TEXT_SOFT": "#cfc4e6",
        "MUTED": "#988cbb",
        "FAINT": "#766a9a",
        "ACCENT": "#b79cff",
        "ACCENT_HI": "#c3b2f0",
        "ACCENT_DEEP": "#3a2b63",
        "ACCENT_SOFT": "#241b3d",
        "ACCENT_LINE": "#463668",
        "ACCENT_TXT": "#f3edff",
        "SENSE": "#f0c98a",
        "GOLD": "#e8c37a",
        "SENSE_SOFT": "#251d12",
        "SENSE_LINE": "#44351f",
        "ERROR": "#f08a9a",
        "OK": "#7fd8a8",
        "HER_BUBBLE": "#1b1529",
        "HER_BUBBLE_LINE": "#34284d",
        "DANGER_SOFT": "#2a1826",
        "DANGER_LINE": "#472a3f",
        "DANGER_HOVER": "#3a2333",
        "DIARY_BG": "#151022",
        "DIARY_LINE": "#2e2547",
        "GUEST_BG": "#221838",
        "GUEST_LINE": "#382a56",
        "GUEST_FG": "#e7e0f8",
        "ENERGY_TRACK": "#241d38",
        "SCROLL": "#2a2140",
        "SCROLL_HI": "#463668",
        "SIDEBAR_BG": "#08060e",
        "SIDEBAR_LINE": "#171126",
        "NAV_SELECTED": "#221a38",
        "NAV_HOVER": "#120e1d",
        "TITLEBAR_BG": "#0c0915",
        "TITLEBAR_LINE": "#1a1330",
        "TITLEBAR_HOVER": "#1e1733",
        "TITLEBAR_CLOSE": "#c42b1c",
        "DISABLED_FILL": "#221b33",
        "TRACK_OFF": "#3a3050",
        "KNOB": "#f4f1ff",
        "WINDOW_ICON_HOVER": "#ffffff",
        "PET_SHADOW": "#030208",
        "ON_ACCENT": "#0b0714",
    },
    "amber": {
        "BG": "#100c08",
        "PANEL": "#16110b",
        "SURFACE": "#16110b",
        "SURFACE_HI": "#1d1610",
        "CARD": "#1f1810",
        "CARD_HI": "#2a2115",
        "INPUT_BG": "#120d08",
        "BORDER": "#332818",
        "BORDER_HI": "#4a3925",
        "TEXT": "#f5ecdd",
        "TEXT_SOFT": "#ddceb4",
        "MUTED": "#a89676",
        "FAINT": "#87775c",
        "ACCENT": "#d8ab68",
        "ACCENT_HI": "#ecc48f",
        "ACCENT_DEEP": "#5a3f1d",
        "ACCENT_SOFT": "#33240f",
        "ACCENT_LINE": "#5a4426",
        "ACCENT_TXT": "#fff4e2",
        "SENSE": "#f2c98a",
        "GOLD": "#e8c37a",
        "SENSE_SOFT": "#2a1f10",
        "SENSE_LINE": "#4d3a1e",
        "ERROR": "#ec8b8b",
        "OK": "#a8cf94",
        "HER_BUBBLE": "#241a10",
        "HER_BUBBLE_LINE": "#3d2c1a",
        "DANGER_SOFT": "#2c1913",
        "DANGER_LINE": "#4a2b22",
        "DANGER_HOVER": "#3a241c",
        "DIARY_BG": "#1b140c",
        "DIARY_LINE": "#3a2c1a",
        "GUEST_BG": "#241d2c",
        "GUEST_LINE": "#392e45",
        "GUEST_FG": "#e8def2",
        "ENERGY_TRACK": "#332716",
        "SCROLL": "#332818",
        "SCROLL_HI": "#54402a",
        "SIDEBAR_BG": "#0b0805",
        "SIDEBAR_LINE": "#1c150e",
        "NAV_SELECTED": "#2a2113",
        "NAV_HOVER": "#15100a",
        "TITLEBAR_BG": "#0d0a06",
        "TITLEBAR_LINE": "#221a10",
        "TITLEBAR_HOVER": "#2a2014",
        "TITLEBAR_CLOSE": "#c42b1c",
        "DISABLED_FILL": "#2a2114",
        "TRACK_OFF": "#4a3a22",
        "KNOB": "#fff6e8",
        "WINDOW_ICON_HOVER": "#ffffff",
        "PET_SHADOW": "#050302",
        "ON_ACCENT": "#1a1208",
    },
    "forest": {
        "BG": "#070f0b",
        "PANEL": "#0a140e",
        "SURFACE": "#0a140e",
        "SURFACE_HI": "#0e1a12",
        "CARD": "#0f1d15",
        "CARD_HI": "#15271c",
        "INPUT_BG": "#08110b",
        "BORDER": "#1d3226",
        "BORDER_HI": "#2c4a37",
        "TEXT": "#e9f4ec",
        "TEXT_SOFT": "#c3d8c9",
        "MUTED": "#8aa896",
        "FAINT": "#69856f",
        "ACCENT": "#78c79a",
        "ACCENT_HI": "#94dab4",
        "ACCENT_DEEP": "#1f4a32",
        "ACCENT_SOFT": "#12301f",
        "ACCENT_LINE": "#2b5b41",
        "ACCENT_TXT": "#eafff2",
        "SENSE": "#e8c980",
        "GOLD": "#e8c980",
        "SENSE_SOFT": "#241f10",
        "SENSE_LINE": "#42371c",
        "ERROR": "#e08593",
        "OK": "#7fd8a8",
        "HER_BUBBLE": "#0f2419",
        "HER_BUBBLE_LINE": "#1e3a2a",
        "DANGER_SOFT": "#241820",
        "DANGER_LINE": "#3f2a32",
        "DANGER_HOVER": "#33202d",
        "DIARY_BG": "#0d1f16",
        "DIARY_LINE": "#21412f",
        "GUEST_BG": "#141a28",
        "GUEST_LINE": "#25304a",
        "GUEST_FG": "#e2e8f7",
        "ENERGY_TRACK": "#1a2e22",
        "SCROLL": "#1d3226",
        "SCROLL_HI": "#2f4f3c",
        "SIDEBAR_BG": "#050b07",
        "SIDEBAR_LINE": "#101c14",
        "NAV_SELECTED": "#13261b",
        "NAV_HOVER": "#0b1510",
        "TITLEBAR_BG": "#08100b",
        "TITLEBAR_LINE": "#18271c",
        "TITLEBAR_HOVER": "#12251a",
        "TITLEBAR_CLOSE": "#c42b1c",
        "DISABLED_FILL": "#1a2b20",
        "TRACK_OFF": "#2a4433",
        "KNOB": "#f2fff6",
        "WINDOW_ICON_HOVER": "#ffffff",
        "PET_SHADOW": "#020604",
        "ON_ACCENT": "#08150f",
    },
    "dawn": {
        "BG": "#f3efe7",
        "PANEL": "#faf7f1",
        "SURFACE": "#faf7f1",
        "SURFACE_HI": "#efe9dd",
        "CARD": "#ffffff",
        "CARD_HI": "#f4efe5",
        "INPUT_BG": "#fffdf9",
        "BORDER": "#ded6c8",
        "BORDER_HI": "#c4b8a4",
        "TEXT": "#2b2a26",
        "TEXT_SOFT": "#4a4740",
        "MUTED": "#5f5a50",
        "FAINT": "#7a7468",
        "ACCENT": "#2f7d6d",
        "ACCENT_HI": "#3d9b87",
        "ACCENT_DEEP": "#cfe9e2",
        "ACCENT_SOFT": "#e4f2ee",
        "ACCENT_LINE": "#9cc9bf",
        "ACCENT_TXT": "#123f37",
        "SENSE": "#a8712c",
        "GOLD": "#a8712c",
        "SENSE_SOFT": "#f7ecd9",
        "SENSE_LINE": "#e2c79b",
        "ERROR": "#a94052",
        "OK": "#2e7d5b",
        "HER_BUBBLE": "#f2efe7",
        "HER_BUBBLE_LINE": "#ddd5c6",
        "DANGER_SOFT": "#f7e4e6",
        "DANGER_LINE": "#e6c2c7",
        "DANGER_HOVER": "#f0d6d9",
        "DIARY_BG": "#f6f2e9",
        "DIARY_LINE": "#e0d6c4",
        "GUEST_BG": "#efe9f5",
        "GUEST_LINE": "#d8cde8",
        "GUEST_FG": "#4b3f63",
        "ENERGY_TRACK": "#e6e0d4",
        "SCROLL": "#d8d1c4",
        "SCROLL_HI": "#bdb4a4",
        "SIDEBAR_BG": "#efeae0",
        "SIDEBAR_LINE": "#dfd8ca",
        "NAV_SELECTED": "#e2f0eb",
        "NAV_HOVER": "#f4efe6",
        "TITLEBAR_BG": "#efeae0",
        "TITLEBAR_LINE": "#ddd6c8",
        "TITLEBAR_HOVER": "#e6dfd2",
        "TITLEBAR_CLOSE": "#c42b1c",
        "DISABLED_FILL": "#e8e3d9",
        "TRACK_OFF": "#cfc7b8",
        "KNOB": "#ffffff",
        "WINDOW_ICON_HOVER": "#ffffff",
        "PET_SHADOW": "#d9d2c6",
        "ON_ACCENT": "#ffffff",
    },
}
# —— 当前主题与订阅 ——

_current = DEFAULT_THEME
_listeners = []


def current() -> str:
    """现在用的是哪套配色。"""
    return _current


def palette() -> dict:
    """当前主题的完整角色表。"""
    return THEMES[_current]


def theme(key: str) -> str:
    """切到某套配色；不认识的 key 回默认。只改颜色，不碰控件。"""
    global _current
    key = str(key or "")
    if key not in THEMES:
        key = DEFAULT_THEME
    changed = key != _current
    _current = key
    if changed:
        for listener in list(_listeners):
            try:
                listener(key)
            except Exception:  # pragma: no cover - 订阅者自己收拾
                pass
    return _current


def on_apply(callback) -> None:
    """主题换了以后通知谁：window.py 用它把全局调色板常量重绑一遍。"""
    _listeners.append(callback)


def set_theme(key: str) -> str:
    """兼容入口：旧代码习惯叫 set_theme，和 theme() 是同一件事。"""
    return theme(key)


def get(role: str, fallback: str = "#ff00ff") -> str:
    return THEMES[_current].get(role, fallback)


def blend(color_a: str, color_b: str, ratio: float) -> str:
    """两种颜色混一混，给渐变和悬停态用。"""
    try:
        ratio = max(0.0, min(1.0, float(ratio)))
        first = [int(str(color_a)[i:i + 2], 16) for i in (1, 3, 5)]
        second = [int(str(color_b)[i:i + 2], 16) for i in (1, 3, 5)]
        mixed = [int(round(lo + (hi - lo) * ratio)) for lo, hi in zip(first, second)]
        return "#" + "".join(f"{v:02x}" for v in mixed)
    except (ValueError, IndexError):
        return color_a


def rgba(color: str, alpha: float) -> tuple:
    """#rrggbb -> (r, g, b, a)，给皮肤合成用。"""
    try:
        r = int(str(color)[1:3], 16)
        g = int(str(color)[3:5], 16)
        b = int(str(color)[5:7], 16)
    except (ValueError, IndexError):
        r = g = b = 255
    a = int(round(max(0.0, min(1.0, float(alpha))) * 255))
    return (r, g, b, a)


def role_of(color: str):
    """反查一个颜色属于哪个角色；老代码里到处传颜色值，靠它猜皮肤变体。"""
    if not color:
        return None
    target = str(color).lower()
    for role, value in THEMES[_current].items():
        if str(value).lower() == target:
            return role
    return None


# —— 字体 ——

try:  # 没有 Tk 的环境（纯后端测试）也能 import
    import tkinter.font as tkfont
except Exception:  # pragma: no cover
    tkfont = None

_FONT_STATE = {
    "ready": False,
    "families": set(),
    "ui": "Microsoft YaHei UI",
    "display": "Microsoft YaHei UI",
    "latin": "Segoe UI",
    "emoji": "Segoe UI Emoji",
    "mono": "Cascadia Mono",
}

# 每种语言一套字体：不混搭字族，按 token 角色取家族与字重。
# 家族链里取第一个系统里装了的；都没有就走回退链（不崩）。
_FONT_STACKS = {
    "zh_CN": {
        "title": (("Noto Sans SC Light", "Noto Sans SC", "Microsoft YaHei UI"), ""),
        "section": (("Noto Sans SC Medium", "Noto Sans SC", "Microsoft YaHei UI"), ""),
        "body": (("Noto Sans SC", "Microsoft YaHei UI"), ""),
        "caption": (("Noto Sans SC", "Microsoft YaHei UI"), ""),
        "hint": (("Noto Sans SC Light", "Noto Sans SC", "Microsoft YaHei UI"), ""),
        "button": (("Noto Sans SC Medium", "Noto Sans SC", "Microsoft YaHei UI"), ""),
        "nav": (("Noto Sans SC", "Microsoft YaHei UI"), ""),
        "badge": (("Noto Sans SC", "Microsoft YaHei UI"), ""),
        "brand": (("Noto Sans SC Medium", "Noto Sans SC", "Microsoft YaHei UI"), ""),
        "display": (("Noto Sans SC Light", "Noto Sans SC", "Microsoft YaHei UI"), ""),
    },
    "en_US": {
        "title": (("Segoe UI Variable Display Light", "Segoe UI Variable Display",
                   "Segoe UI Variable Text", "Segoe UI"), ""),
        "section": (("Segoe UI Variable Text Semibold", "Segoe UI Variable Text Semibold",
                     "Segoe UI Semibold", "Segoe UI"), ""),
        "body": (("Segoe UI Variable Text", "Segoe UI"), ""),
        "caption": (("Segoe UI Variable Text", "Segoe UI"), ""),
        "hint": (("Segoe UI Variable Text Semilight", "Segoe UI Variable Text", "Segoe UI"), ""),
        "button": (("Segoe UI Variable Text Semibold", "Segoe UI Semibold", "Segoe UI"), ""),
        "nav": (("Segoe UI Variable Text", "Segoe UI"), ""),
        "badge": (("Segoe UI Variable Text", "Segoe UI"), ""),
        "brand": (("Segoe UI Variable Text Semibold", "Segoe UI Semibold", "Segoe UI"), ""),
        "display": (("Segoe UI Variable Display Light", "Segoe UI Variable Display",
                     "Segoe UI Variable Text", "Segoe UI"), ""),
    },
    "ja_JP": {
        "title": (("Noto Sans JP Light", "Noto Sans JP", "Yu Gothic UI"), ""),
        "section": (("Noto Sans JP Medium", "Noto Sans JP", "Yu Gothic UI"), ""),
        "body": (("Noto Sans JP", "Yu Gothic UI"), ""),
        "caption": (("Noto Sans JP", "Yu Gothic UI"), ""),
        "hint": (("Noto Sans JP Light", "Noto Sans JP", "Yu Gothic UI"), ""),
        "button": (("Noto Sans JP Medium", "Noto Sans JP", "Yu Gothic UI"), ""),
        "nav": (("Noto Sans JP", "Yu Gothic UI"), ""),
        "badge": (("Noto Sans JP", "Yu Gothic UI"), ""),
        "brand": (("Noto Sans JP Medium", "Noto Sans JP", "Yu Gothic UI"), ""),
        "display": (("Noto Sans JP Light", "Noto Sans JP", "Yu Gothic UI"), ""),
    },
    "ko_KR": {
        "title": (("Malgun Gothic Semilight", "Malgun Gothic", "Microsoft YaHei UI"), ""),
        "section": (("Malgun Gothic", "Microsoft YaHei UI"), "bold"),
        "body": (("Malgun Gothic", "Microsoft YaHei UI"), ""),
        "caption": (("Malgun Gothic", "Microsoft YaHei UI"), ""),
        "hint": (("Malgun Gothic Semilight", "Malgun Gothic", "Microsoft YaHei UI"), ""),
        "button": (("Malgun Gothic", "Microsoft YaHei UI"), "bold"),
        "nav": (("Malgun Gothic", "Microsoft YaHei UI"), ""),
        "badge": (("Malgun Gothic", "Microsoft YaHei UI"), ""),
        "brand": (("Malgun Gothic", "Microsoft YaHei UI"), "bold"),
        "display": (("Malgun Gothic Semilight", "Malgun Gothic", "Microsoft YaHei UI"), ""),
    },
}
_FONT_FALLBACK = ("Segoe UI", "Microsoft YaHei UI", "TkDefaultFont")

# 苹果式阶梯：大标题轻、正文中，靠字号+字重+留白做层级。
_FONT_SIZES = {
    "title": 22, "display": 22, "section": 15, "body": 13, "caption": 12,
    "hint": 11, "button": 13, "nav": 13, "badge": 11, "brand": 15,
}

_FONT_OBJECTS = {}
_FONT_OBJECTS_LOCALE = ""


def resolve_fonts() -> None:
    """问一次系统有哪些字体，之后不再问。"""
    if _FONT_STATE["ready"]:
        return
    available = set()
    try:
        if tkfont is not None:
            available = {str(name) for name in tkfont.families()}
    except Exception:  # pragma: no cover - 没有 root 也没有字体表
        available = set()
    _FONT_STATE["families"] = available
    _FONT_STATE.update({
        "ui": _pick_family(("Microsoft YaHei UI", "Noto Sans SC", "Segoe UI", "TkDefaultFont")),
        "display": _pick_family(("Segoe UI Variable Display", "Noto Sans SC Light", "Segoe UI",
                                 "Microsoft YaHei UI")),
        "latin": _pick_family(("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI")),
        "emoji": _pick_family(("Segoe UI Emoji", "Segoe UI Symbol", "Segoe UI")),
        "mono": _pick_family(("Cascadia Mono", "Consolas", "Courier New")),
        "ready": True,
    })


def _pick_family(choices) -> str:
    available = _FONT_STATE.get("families") or set()
    for name in choices:
        if name in available:
            return name
    return ""


def _font_locale() -> str:
    try:
        from ..i18n import get_locale
        code = str(get_locale())
    except Exception:
        code = "zh_CN"
    return code if code in _FONT_STACKS else "zh_CN"


def _role_for(size, weight: str = "") -> str:
    try:
        value = float(size)
    except Exception:
        value = 13.0
    if value >= 19:
        return "title"
    if value >= 14:
        return "section"
    if weight == "bold" and value >= 13:
        return "section"
    if value >= 13:
        return "body"
    if value >= 12:
        return "caption"
    if value >= 10:
        return "hint"
    return "badge"


def _named_font(role: str, slant: str = ""):
    """按当前语言取命名 Font（缓存，不每次 new）。"""
    global _FONT_OBJECTS_LOCALE
    locale = _font_locale()
    if locale != _FONT_OBJECTS_LOCALE:
        _FONT_OBJECTS.clear()
        _FONT_OBJECTS_LOCALE = locale
    key = (role, slant or "")
    cached = _FONT_OBJECTS.get(key)
    if cached is not None:
        return cached
    stacks = _FONT_STACKS.get(locale, _FONT_STACKS["zh_CN"])
    choices, weight = stacks.get(role, stacks["body"])
    family = _pick_family(choices) or _pick_family(_FONT_FALLBACK) or "TkDefaultFont"
    size = int(_FONT_SIZES.get(role, 13))
    # 设计规范里的字号是像素：tkfont 用负数表示像素，避免 125% DPI 下被放大 1.5 倍
    pixel_size = -max(6, size)
    spec = (family, pixel_size)
    try:
        if tkfont is not None:
            spec = tkfont.Font(family=family, size=pixel_size,
                               weight=weight or "normal", slant=slant or "roman")
    except Exception:  # pragma: no cover - 极端环境下退回元组
        spec = (family, pixel_size)
    _FONT_OBJECTS[key] = spec
    return spec


def font(size=13, weight: str = "", family: str = "ui", slant: str = ""):
    """按语言/角色返回字体（Font 命名对象；emoji/mono 仍是元组）。"""
    if family == "emoji":
        return (_FONT_STATE.get("emoji") or "Segoe UI Emoji", size)
    if family == "mono":
        return (_FONT_STATE.get("mono") or "Consolas", size)
    if not _FONT_STATE["ready"]:
        resolve_fonts()
    return _named_font(_role_for(size, weight), slant)


def font_role(role: str):
    """直接按 token 名取字体（title/section/body/caption/hint/button/nav/badge/brand/display）。"""
    if not _FONT_STATE["ready"]:
        resolve_fonts()
    return _named_font(role)


def linespace(font_spec=None) -> int:
    """字体的行高（像素）：所有控件高度都从这里长，不在页面里写死。"""
    spec = font_spec or font(FONT_BODY)
    try:
        if tkfont is not None:
            if isinstance(spec, tkfont.Font):
                return int(spec.metrics("linespace"))
            return int(tkfont.Font(font=spec).metrics("linespace"))
    except Exception:
        pass
    return 18


def row_height(font_spec=None, *, minimum: int = 38, pad: int = 14) -> int:
    """列表/导航一行的推荐高度。"""
    return max(int(minimum), linespace(font_spec) + int(pad))


def button_height(font_spec=None, *, minimum: int = 40, pad: int = 16) -> int:
    """按钮的推荐高度（含上下留白）。"""
    return max(int(minimum), linespace(font_spec) + int(pad))


def footer_height(font_spec=None) -> int:
    """底栏高度：按钮行 + 上下留白。"""
    return linespace(font_spec) + 48


def text_width(text, font_spec) -> float:
    """量一段字有多宽。Font 对象直接 measure，元组先转 Font。"""
    try:
        if tkfont is not None and isinstance(font_spec, tkfont.Font):
            return float(font_spec.measure(str(text)))
        if tkfont is not None:
            return float(tkfont.Font(font=font_spec).measure(str(text)))
    except Exception:
        pass
    return max(12, len(str(text)) * 10)


# —— 字号 / 间距 / 圆角：所有页面都用同一套 ——

FONT_DISPLAY = 22      # 页标题（title 角色：21 Light）
FONT_TITLE = 15        # 卡片标题（section 角色：14 Medium）
FONT_BRAND = 15        # 标题栏品牌（brand 角色：13 Medium）
FONT_BODY = 13         # 正文 / 气泡（body 角色：13）
FONT_SECTION = 15      # 区块标题（section 角色：14 Medium）
FONT_SMALL = 12        # 说明文字（hint 角色：11）
FONT_TINY = 11         # 角标
FONT_MICRO = 11        # 极小的状态行
FONT_NAV = 13          # 导航/标签（body 角色）

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 32

RADIUS_CARD = 18
RADIUS_BUTTON = 12
RADIUS_BUBBLE = 18
RADIUS_INPUT = 12
RADIUS_CHIP = 15
RADIUS_SWATCH = 12

# —— 控件比例（1.23 设计语言：现代桌面应用，8 的网格）——
BTN_PRIMARY_H = 44     # 主按钮
BTN_SECONDARY_H = 36   # 次按钮 / 工具按钮
CHIP_H = 30            # 药丸 / chip
INPUT_H = 44           # 输入框
TOGGLE_W = 42          # 开关
TOGGLE_H = 22
KNOB_SIZE = 18
NAV_H = 40             # 侧栏导航行
WIN_BTN_W = 32         # 标题栏窗口按钮
WIN_BTN_H = 24
SEND_BTN = 46
CONTENT_MAX = 920
COMPOSER_H = 96
ACTION_H = 44          # 发送键（圆形）
CARD_INSET = 20        # 卡片内边距


# —— 皮肤规格：build_skins.py 与运行时共用 ——
#
# 每项：
#   size     生成素材的逻辑尺寸（运行时按 9-slice 拉伸）
#   radius   圆角
#   fill     主色角色；fill2 顶部渐变色角色
#   border   描边角色；border_w 描边像素
#   shadow   外阴影像素（0 = 没有）
#   states   状态名 -> 覆盖项
#   left_bar 左侧强调条颜色角色（导航选中用）
#   glyph    烘进图片的字形名（发送按钮用）
#   glyph_color 字形颜色角色

# —— 玻璃拟态：背景渐变/柔光斑 + 半透明层用色（预渲染，运行时只画缓存）——
GLASS_EXTRA = {
    "deep": dict(BG_TOP="#12233c", BG_BOTTOM="#070c16", GLOW_A="#1d5c94", GLOW_B="#123a66",
                 GLASS="#ffffff", GLASS_HI="#ffffff", GLASS_LINE="#ffffff"),
    "violet": dict(BG_TOP="#241d40", BG_BOTTOM="#0d0a18", GLOW_A="#5b3fa0", GLOW_B="#39285f",
                   GLASS="#ffffff", GLASS_HI="#ffffff", GLASS_LINE="#ffffff"),
    "amber": dict(BG_TOP="#2c1f14", BG_BOTTOM="#120c08", GLOW_A="#8a5420", GLOW_B="#573414",
                  GLASS="#ffffff", GLASS_HI="#ffffff", GLASS_LINE="#ffffff"),
    "forest": dict(BG_TOP="#142a1f", BG_BOTTOM="#07110c", GLOW_A="#237a4f", GLOW_B="#175237",
                   GLASS="#ffffff", GLASS_HI="#ffffff", GLASS_LINE="#ffffff"),
    "dawn": dict(BG_TOP="#fbf7ef", BG_BOTTOM="#e8e0d0", GLOW_A="#dfe9ff", GLOW_B="#ffe9c4",
                 GLASS="#ffffff", GLASS_HI="#ffffff", GLASS_LINE="#000000"),
}
FLAT_BACKDROP = False
for _theme_key, _extra in GLASS_EXTRA.items():
    THEMES[_theme_key].update(_extra)

SKIN_SPECS = {
    # 玻璃面板：半透明层（浅色主题由 build_skins 自动提高到 55%），1px 描边 + 顶部光
    "card": dict(size=(200, 150), radius=RADIUS_CARD, fill="GLASS", fill_alpha=0.18,
                 border="GLASS_LINE", border_alpha=0.24, border_w=1, shadow=8,
                 shadow_alpha=0.22, highlight_alpha=0.16),
    "panel": dict(size=(200, 150), radius=RADIUS_CARD, fill="GLASS", fill_alpha=0.12,
                  border="GLASS_LINE", border_alpha=0.20, border_w=1, shadow=0,
                  highlight_alpha=0.18),
    "diary": dict(size=(200, 150), radius=RADIUS_CARD, fill="GLASS", fill_alpha=0.12,
                  border="GLASS_LINE", border_alpha=0.12, border_w=1, shadow=4,
                  shadow_alpha=0.12, highlight_alpha=0.12),
    "button": dict(size=(96, BTN_SECONDARY_H), radius=RADIUS_BUTTON, fill="GLASS",
                   fill_alpha=0.10, border="GLASS_LINE", border_alpha=0.22, border_w=1,
                   shadow=0, highlight_alpha=0.14,
                   states={"hover": dict(fill="ACCENT", fill_alpha=0.10),
                           "pressed": dict(fill="ACCENT", fill_alpha=0.18)}),
    "primary": dict(size=(96, BTN_PRIMARY_H), radius=RADIUS_BUTTON, fill="ACCENT",
                    fill2="ACCENT_HI", border=None, border_w=0, shadow=4,
                    shadow_alpha=0.28, highlight_alpha=0.22,
                    states={"hover": dict(fill="ACCENT_HI", fill2="ACCENT_HI", shadow=6),
                            "pressed": dict(fill="ACCENT_DEEP", fill2="ACCENT"),
                            "disabled": dict(fill="ACCENT", fill2="ACCENT", fill_alpha=0.4)}),
    "ghost": dict(size=(96, BTN_SECONDARY_H), radius=RADIUS_BUTTON, fill=None, fill2=None,
                  border=None, border_w=0, shadow=0,
                  states={"hover": dict(fill="ACCENT", fill_alpha=0.08)}),
    "danger": dict(size=(96, BTN_SECONDARY_H), radius=RADIUS_BUTTON, fill="ERROR",
                   fill_alpha=0.14, border="ERROR", border_alpha=0.35, border_w=1,
                   shadow=0, highlight_alpha=0.12),
    "input": dict(size=(160, INPUT_H), radius=RADIUS_INPUT, fill="GLASS", fill_alpha=0.11,
                  border="GLASS_LINE", border_alpha=0.22, border_w=1, shadow=0,
                  highlight_alpha=0.10,
                  states={"focus": dict(border="ACCENT", border_alpha=0.9, glow="ACCENT",
                                        fill_alpha=0.10)}),
    "toggle_on": dict(size=(TOGGLE_W, TOGGLE_H), radius=TOGGLE_H // 2, fill="ACCENT",
                      fill2="ACCENT_HI", border=None, border_w=0, shadow=2,
                      shadow_alpha=0.30, highlight_alpha=0.20),
    "toggle_off": dict(size=(TOGGLE_W, TOGGLE_H), radius=TOGGLE_H // 2, fill="GLASS",
                       fill_alpha=0.08, border="GLASS_LINE", border_alpha=0.14, border_w=1,
                       shadow=1),
    "knob": dict(size=(KNOB_SIZE, KNOB_SIZE), radius=KNOB_SIZE // 2, fill="KNOB", fill2=None,
                 border=None, border_w=0, shadow=2, shadow_alpha=0.35, highlight_alpha=0.30),
    "pill": dict(size=(84, CHIP_H), radius=RADIUS_CHIP, fill="GLASS", fill_alpha=0.08,
                 border="GLASS_LINE", border_alpha=0.14, border_w=1, shadow=0,
                 highlight_alpha=0.18),
    "pill_primary": dict(size=(84, CHIP_H), radius=RADIUS_CHIP, fill="ACCENT",
                         fill2="ACCENT_HI", border=None, border_w=0, shadow=0,
                         highlight_alpha=0.20,
                         states={"hover": dict(fill="ACCENT_HI", fill2="ACCENT_HI"),
                                 "pressed": dict(fill="ACCENT_DEEP", fill2="ACCENT")}),
    "pill_accent": dict(size=(84, CHIP_H), radius=RADIUS_CHIP, fill="ACCENT", fill_alpha=0.16,
                        border="ACCENT", border_alpha=0.40, border_w=1, shadow=0),
    "pill_sense": dict(size=(84, CHIP_H), radius=RADIUS_CHIP, fill="SENSE", fill_alpha=0.16,
                       border="SENSE", border_alpha=0.38, border_w=1, shadow=0),
    "pill_danger": dict(size=(84, CHIP_H), radius=RADIUS_CHIP, fill="ERROR", fill_alpha=0.14,
                        border="ERROR", border_alpha=0.38, border_w=1, shadow=0),
    "pill_soft": dict(size=(84, CHIP_H), radius=RADIUS_CHIP, fill="GLASS", fill_alpha=0.05,
                      border="GLASS_LINE", border_alpha=0.10, border_w=1, shadow=0),
    "bubble_me": dict(size=(160, 96), radius=RADIUS_BUBBLE, fill="HER_BUBBLE", fill2=None,
                      border="HER_BUBBLE_LINE", border_w=1, shadow=2, shadow_alpha=0.18,
                      highlight_alpha=0.16),
    "bubble_her": dict(size=(160, 96), radius=RADIUS_BUBBLE, fill="GLASS", fill_alpha=0.10,
                       border="GLASS_LINE", border_alpha=0.12, border_w=1, shadow=3,
                       shadow_alpha=0.16, highlight_alpha=0.12),
    "bubble_guest": dict(size=(160, 96), radius=RADIUS_BUBBLE, fill="GUEST_BG", fill2=None,
                         border="GUEST_LINE", border_w=1, shadow=2, shadow_alpha=0.16,
                         highlight_alpha=0.14),
    "scroll_track": dict(size=(8, 40), radius=4, fill="GLASS", fill_alpha=0.04,
                         border=None, border_w=0, shadow=0),
    "scroll_thumb": dict(size=(8, 40), radius=4, fill="GLASS", fill_alpha=0.18,
                         border=None, border_w=0, shadow=0,
                         states={"hover": dict(fill="GLASS", fill_alpha=0.30)}),
    "nav_selected": dict(size=(200, NAV_H), radius=10, fill="ACCENT", fill_alpha=0.12,
                         border="GLASS_LINE", border_alpha=0.10, border_w=1, shadow=0,
                         left_bar="GOLD", highlight_alpha=0.10),
    "nav_hover": dict(size=(200, NAV_H), radius=10, fill="ACCENT", fill_alpha=0.06,
                      border=None, border_w=0, shadow=0),
    "title_btn": dict(size=(WIN_BTN_W, WIN_BTN_H), radius=6, fill=None, border=None,
                      border_w=0, shadow=0,
                      states={"hover": dict(fill="GLASS", fill_alpha=0.10)}),
    "title_close": dict(size=(WIN_BTN_W, WIN_BTN_H), radius=6, fill=None, border=None,
                        border_w=0, shadow=0,
                        states={"hover": dict(fill="ERROR", fill_alpha=0.85)}),
    "send": dict(size=(SEND_BTN, SEND_BTN), radius=SEND_BTN // 2, fill="ACCENT",
                 fill2="ACCENT_HI", border=None, border_w=0, shadow=5,
                 shadow_alpha=0.30, highlight_alpha=0.25,
                 glyph="arrow_up", glyph_color="ON_ACCENT", glyph_size=18,
                 states={"hover": dict(fill="ACCENT_HI", fill2="ACCENT_HI", shadow=6),
                         "pressed": dict(fill="ACCENT_DEEP", fill2="ACCENT")}),
    "meter_track": dict(size=(40, 6), radius=3, fill="GLASS", fill_alpha=0.06,
                        border=None, border_w=0, shadow=0),
    "meter_fill": dict(size=(40, 6), radius=3, fill="ACCENT", fill2="ACCENT_HI",
                       border=None, border_w=0, shadow=0),
}

GLYPH_SPECS = {
    "min": dict(size=(11, 11), color="TEXT"),
    "max": dict(size=(11, 11), color="TEXT"),
    "restore": dict(size=(11, 11), color="TEXT"),
    "close": dict(size=(11, 11), color="TEXT"),
    "arrow_up": dict(size=(18, 18), color="ACCENT_TXT"),
    "check": dict(size=(12, 12), color="ACCENT_TXT"),
    "chevron_down": dict(size=(12, 12), color="MUTED"),
}


def skin_inset(spec_name: str) -> int:
    """9-slice 的边距：圆角 + 阴影 + 描边。"""
    spec = SKIN_SPECS.get(spec_name) or {}
    return int(spec.get("radius", 0)) + int(spec.get("shadow", 0)) + 1


def skin_content_inset(spec_name: str) -> int:
    """内容离图片边缘的安全距离（圆角以内）。"""
    spec = SKIN_SPECS.get(spec_name) or {}
    return int(spec.get("radius", 0)) + int(spec.get("shadow", 0)) // 2 + 2


# 玻璃皮肤：按文档 8–14% 白、18% 描边、28% 顶部高光、柔和阴影
for _name, _spec in SKIN_SPECS.items():
    _spec.setdefault("fill_alpha", 0.10)
    _spec["border_alpha"] = 0.18 if _spec.get("border") else 0.0
    if _spec.get("shadow"):
        _spec["shadow"] = max(_spec["shadow"], 6)
        _spec["shadow_alpha"] = 0.18
    _spec["highlight_alpha"] = 0.28
for _name in ("pill", "pill_soft", "pill_accent", "pill_sense", "pill_danger"):
    if _name in SKIN_SPECS:
        _spec = SKIN_SPECS[_name]
        _spec["fill_alpha"] = 0.12
        _spec["border_alpha"] = 0.18
        _spec["highlight_alpha"] = 0.22
if "nav_selected" in SKIN_SPECS:
    SKIN_SPECS["nav_selected"].update(fill="NAV_SELECTED", fill_alpha=0.10,
                                      border=None, border_w=0, left_bar="ACCENT")
if "nav_hover" in SKIN_SPECS:
    SKIN_SPECS["nav_hover"].update(fill="ACCENT", fill_alpha=0.06, border=None, border_w=0)
if "primary" in SKIN_SPECS:
    SKIN_SPECS["primary"].update(fill="ACCENT", fill2="ACCENT_HI", highlight_alpha=0.22)
if "pill_primary" in SKIN_SPECS:
    SKIN_SPECS["pill_primary"].update(fill="ACCENT", fill2="ACCENT_HI", highlight_alpha=0.22)
