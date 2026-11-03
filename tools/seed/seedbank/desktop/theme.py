from __future__ import annotations

import ctypes
import os
import sys
import tkinter.font as tkfont
from tkinter import ttk
from dataclasses import dataclass

from PIL import ImageTk

from .render import icon_image
from ..i18n import detect_locale, set_locale
from ..onboarding import load_config
from ..settings import ui_settings_path
from ..util import read_json, write_json_atomic


PALETTES = {
    "cream": {
        "background": "#F6F5F9", "surface": "#FFFFFF", "text": "#302B46",
        "muted": "#655E78", "primary": "#7150A5", "on_primary": "#FFFFFF",
        "hover": "#60418F", "soft": "#EEE6F8", "border": "#D9CEE8",
        "stage": "#EDE6FA", "stage_floor": "#DAD0EF", "mint": "#E1F2EA",
        "peach": "#FBE9E0", "danger": "#A1394B", "success": "#27674E",
        "shadow": "#E6DFEF", "disabled": "#E8E3ED", "disabled_text": "#716A7D",
        "scroll_thumb": "#9A86B6",
        "glass_edge": "#DDD4EC", "glass_glow": "#FFFFFF", "glass_refraction": "#C3B9E6",
        "field": "#EFEDF4", "separator": "#E8E5EF", "navigation": "#FCFBFF",
    },
    "mint": {
        "background": "#F3F7F5", "surface": "#FFFFFF", "text": "#243E3B",
        "muted": "#536D68", "primary": "#286F68", "on_primary": "#FFFFFF",
        "hover": "#205C56", "soft": "#DDEEE8", "border": "#C6DDD5",
        "stage": "#E0F0EA", "stage_floor": "#BDDCD0", "mint": "#E0EDF9",
        "peach": "#FBEBDA", "danger": "#A1394B", "success": "#27674E",
        "shadow": "#DDE9E4", "disabled": "#E0E9E5", "disabled_text": "#63766E",
        "scroll_thumb": "#6A9990",
        "glass_edge": "#CEDFD9", "glass_glow": "#FFFFFF", "glass_refraction": "#A9C9D6",
        "field": "#E8F0EC", "separator": "#DCE8E2", "navigation": "#FAFDFB",
    },
    "night": {
        "background": "#1D2335", "surface": "#293149", "text": "#F3EFFB",
        "muted": "#C2BCD5", "primary": "#C9B5F2", "on_primary": "#28203B",
        "hover": "#DBC9FA", "soft": "#3C3C5B", "border": "#565B78",
        "stage": "#353E5C", "stage_floor": "#485273", "mint": "#304C4B",
        "peach": "#51404D", "danger": "#FFB3BD", "success": "#A2E2C3",
        "shadow": "#161B2A", "disabled": "#363E54", "disabled_text": "#B2AFC2",
        "scroll_thumb": "#8686AA",
        "glass_edge": "#4B5574", "glass_glow": "#8696BE", "glass_refraction": "#7A6A9E",
        "field": "#323A51", "separator": "#3C455E", "navigation": "#2C344C",
    },
}


def preferences() -> dict:
    data = read_json(ui_settings_path(), {})
    return dict(data) if isinstance(data, dict) else {}


def save_preferences(patch: dict) -> dict:
    data = preferences()
    data.update(patch)
    write_json_atomic(ui_settings_path(), data)
    return data


def initialize_locale() -> None:
    set_locale(os.environ.get("SEEDBANK_LANG") or load_config().get("language") or detect_locale())


def system_reduced_motion() -> bool:
    if sys.platform != "win32":
        return False
    try:
        enabled = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not bool(enabled.value)
    except (AttributeError, OSError):
        pass
    return False


def style_native_widgets(root, theme):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground=theme.color("field"),
                    background=theme.color("soft"), foreground=theme.color("text"),
                    arrowcolor=theme.color("primary"), bordercolor=theme.color("border"),
                    lightcolor=theme.color("border"), darkcolor=theme.color("border"), padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", theme.color("field"))],
              foreground=[("readonly", theme.color("text"))],
              selectbackground=[("readonly", theme.color("soft"))],
              selectforeground=[("readonly", theme.color("text"))])
    owner = root._root()
    if not hasattr(owner, "_desktop_select_arrows"):
        owner._desktop_select_arrows = {}
    cache = owner._desktop_select_arrows
    key = theme.key, theme.scale
    if key not in cache:
        name = f"SeedbankSelect{len(cache)}.Combobox.downarrow"
        picture = ImageTk.PhotoImage(icon_image("chevron_down", round(20 * theme.scale), theme.color("primary")), master=owner)
        style.element_create(name, "image", picture, sticky="e")
        cache[key] = name, picture
    style.layout("Seedbank.TCombobox", [("Combobox.padding", {"sticky": "nswe", "children": [
        (cache[key][0], {"side": "right", "sticky": "ns"}),
        ("Combobox.textarea", {"sticky": "nswe"}),
    ]})])
    style.configure("Seedbank.TCombobox", padding=0, borderwidth=0, arrowsize=16,
                    background=theme.color("field"))
    root.option_add("*TCombobox*Listbox.font", theme.font(14))
    root.option_add("*TCombobox*Listbox.background", theme.color("surface"))
    root.option_add("*TCombobox*Listbox.foreground", theme.color("text"))
    root.option_add("*TCombobox*Listbox.selectBackground", theme.color("primary"))
    root.option_add("*TCombobox*Listbox.selectForeground", theme.color("on_primary"))
    root.option_add("*TCombobox*Listbox.borderWidth", 0)


@dataclass
class Theme:
    key: str = "cream"
    scale: float = 1.0
    reduced_motion: bool = False
    family: str = "Segoe UI"

    @classmethod
    def load(cls, root):
        saved = preferences()
        key = saved.get("desktop_theme", "cream")
        if key not in PALETTES:
            key = "cream"
        scale = 1.15 if saved.get("desktop_large_text") else 1.0
        available = set(tkfont.families(root))
        family = next((name for name in (
            "Microsoft YaHei UI", "MiSans", "Noto Sans CJK SC", "Yu Gothic UI",
            "Malgun Gothic", "Segoe UI", "DejaVu Sans",
        ) if name in available), "TkDefaultFont")
        return cls(key, scale, bool(saved.get("desktop_reduced_motion", system_reduced_motion())), family)

    def color(self, role: str) -> str:
        return PALETTES[self.key][role]

    def font(self, size: int = 16, weight: str = "normal") -> tuple:
        return self.family, -round(max(13, size) * self.scale), weight
