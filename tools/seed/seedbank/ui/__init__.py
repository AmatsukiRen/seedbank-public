"""1.23 的 UI 包：皮肤素材、设计令牌、组件系统。

页面层（chat / diary / memory / settings）在 window.py 的薄适配器里
逐页迁过来；这个包先提供所有页面共用的东西。
"""

from . import raster, skin, tokens
from .skin import SKINS
from .components import (
    _Bubble,
    _Card,
    _InputBox,
    _NavItem,
    _Pill,
    _RoundButton,
    _ScrollFrame,
    _Slider,
    _ThemeSwatch,
    _ThinBar,
    _TitleBar,
    _Toggle,
    _WinButton,
    _field,
    _flow_chips,
    _section,
)

__all__ = [
    "SKINS", "raster", "skin", "tokens",
    "_Bubble", "_Card", "_InputBox", "_NavItem", "_Pill", "_RoundButton",
    "_ScrollFrame", "_Slider", "_ThemeSwatch", "_ThinBar", "_TitleBar",
    "_Toggle", "_WinButton", "_field", "_flow_chips", "_section",
]
