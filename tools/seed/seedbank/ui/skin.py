"""皮肤素材库：一个组件 = 一张小 PNG，运行时按九宫格拉到实际大小。

素材由 `tools/seed/assets/ui/build_skins.py` 生成，放在
`tools/seed/assets/ui/<theme>/` 下；这个模块只负责读、拉、合成、缓存。
找不到素材时安静地退回纯色方块，界面不会因为少一张图开不起来。
"""

from __future__ import annotations

from pathlib import Path

from . import raster, tokens

try:  # 图形环境以外 import 也不该炸
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None

_ROOT = Path(__file__).resolve().parents[2] / "assets" / "ui"


def _hex_to_rgb(color: str) -> tuple:
    return tokens.rgba(color, 1.0)[:3]


class SkinLibrary:
    """按主题缓存素材与 PhotoImage。"""

    def __init__(self) -> None:
        self._raw = {}
        self._photos = {}
        self._glyphs = {}
        self._missing = set()

    # —— 目录与加载 ——

    def root(self) -> Path:
        return _ROOT

    def theme_dir(self, theme: str) -> Path:
        return _ROOT / str(theme)

    def _read(self, theme: str, filename: str):
        key = (theme, filename)
        if key in self._raw:
            return self._raw[key]
        path = self.theme_dir(theme) / filename
        try:
            width, height, pixels = raster.decode_png(path.read_bytes())
        except (OSError, ValueError):
            self._raw[key] = None
            self._missing.add(str(path))
            return None
        self._raw[key] = (width, height, pixels)
        return self._raw[key]

    def has_theme(self, theme: str) -> bool:
        directory = self.theme_dir(theme)
        try:
            return directory.is_dir() and any(directory.glob("*.png"))
        except OSError:
            return False

    # —— 组件图片 ——

    def photo(self, spec_name: str, width: int, height: int, bg: str,
              state: str = "normal", theme: str = "") -> "object":
        """拿一张已经拉好的 PhotoImage；没有素材时返回 None。"""
        theme = theme or tokens.current()
        width = max(2, int(width))
        height = max(2, int(height))
        if tk is None:  # pragma: no cover - 纯无图形环境
            return None
        self._sync_root(tk)  # 换过根窗口就先丢旧缓存，再查缓存
        key = (theme, spec_name, state, width, height, str(bg))
        cached = self._photos.get(key)
        if cached is not None:
            return cached
        raw = self._read(theme, f"{spec_name}__{state}.png")
        if raw is None:
            return None
        src_w, src_h, pixels = raw
        inset = tokens.skin_inset(spec_name)
        stretched = raster.nine_slice(pixels, src_w, src_h, inset, width, height)
        flat = raster.flatten(width, height, stretched, _hex_to_rgb(bg))
        try:
            photo = tk.PhotoImage(data=raster.photo_data(width, height, flat))
        except Exception:  # pragma: no cover - 图片坏了
            return None
        self._photos[key] = photo
        return photo

    # —— 字形 ——

    def glyph(self, name: str, bg: str, theme: str = "") -> "object":
        """标题栏图标 / 发送箭头的纯色字形，已合成到背景。"""
        theme = theme or tokens.current()
        if tk is None:  # pragma: no cover
            return None
        self._sync_root(tk)
        key = (theme, name, str(bg))
        cached = self._glyphs.get(key)
        if cached is not None:
            return cached
        raw = self._read(theme, f"glyph_{name}.png")
        if raw is None:
            return None
        src_w, src_h, pixels = raw
        flat = raster.flatten(src_w, src_h, pixels, _hex_to_rgb(bg))
        try:
            photo = tk.PhotoImage(data=raster.photo_data(src_w, src_h, flat))
        except Exception:  # pragma: no cover
            return None
        self._glyphs[key] = photo
        return photo

    # —— 缓存维护 ——

    def _sync_root(self, tk_module) -> None:
        """Tk 根窗口换了（一个进程里开第二扇窗/跑测试）就丢掉旧 PhotoImage。

        PhotoImage 绑在创建它的解释器上：旧根销毁后缓存里只剩死名字，再用就会
        报 `image "pyimageN" doesn't exist`。
        """
        root = getattr(tk_module, "_default_root", None)
        if root is not getattr(self, "_root", None):
            self._root = root
            self._photos.clear()
            self._glyphs.clear()

    def clear(self) -> None:
        self._raw.clear()
        self._photos.clear()
        self._glyphs.clear()

    def missing(self) -> list:
        return sorted(self._missing)


SKINS = SkinLibrary()
