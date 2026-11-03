"""Compatibility stage. Character rendering belongs to the Live2D interface."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from .text import t
from .theme import Theme


PET_STATES = ("idle", "happy", "dance", "wave", "sleep", "think", "curious", "sad")


def asset_root(name="pet"):
    """Retain historical path helpers without probing or loading old artwork."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name


PET_ROOT = asset_root()
PET_SMALL_ROOT = asset_root("pet-small")


def _load_frames(root_path, state):
    """Retired compatibility API; existing asset directories cannot enable it."""
    return ()


class PetStage(tk.Canvas):
    def __init__(self, parent, theme=None, *, asset_path=None, bg=None):
        self.theme = theme or Theme()
        # Accept old callers' asset_path argument, but never read the directory.
        super().__init__(parent, bg=bg or self.theme.color("stage"),
                         highlightthickness=0, height=300, width=280, bd=0)
        self._available = False
        self._running = False
        self._after = None
        self._scene_size = None
        self.bind("<Configure>", self._draw)
        self.bind("<Destroy>", self._destroy, add="+")
        self.resume()

    def play(self, state="happy", seconds=3):
        self._draw()
        return False

    def set_mood(self, mood, energy=1.0):
        pass

    def _draw(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if not self._running or width < 20 or height < 20:
            return
        self._scene_size = width, height
        self.delete("all")
        self.create_text(
            width / 2, height / 2, width=max(1, width - 32), justify="center",
            text=t("角色展示已迁移，请使用当前 SEEDbank 入口。"),
            fill=self.theme.color("muted"), font=self.theme.font(),
            tags=("placeholder",),
        )

    def stop(self):
        self._running = False

    def resume(self):
        self._running = True
        self._draw()

    def _destroy(self, event):
        if event.widget is self:
            self.stop()
