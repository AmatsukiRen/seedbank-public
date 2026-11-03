"""1.23 的新组件系统：所有控件都从「皮肤素材 + 设计令牌」长出来。

window.py 里的旧自绘控件（Pill / Card / Bubble / InputBox / Toggle …
的 canvas 版）由这里的同名类替代，构造函数保持兼容，内部改成：

    九宫格 PNG 皮肤（ui.skin）  +  统一的字号/间距（ui.tokens）

这样 5 套主题、4 种语言、4 个窗口尺寸下，圆角、描边、悬停态都一致，
也不用再靠「算坐标硬贴」去拼界面。
"""

from __future__ import annotations

import tkinter as tk

from . import backdrop as _backdrop
from . import tokens as T
from . import backdrop as ui_backdrop
from .skin import SKINS


def _bg_of(widget, fallback_role: str = "BG") -> str:
    """拿到父控件的底色，用于把半透明皮肤压上去。"""
    try:
        value = str(widget.cget("bg"))
        if value:
            return value
    except Exception:
        pass
    return T.get(fallback_role)


def _local_bg(widget) -> str:
    """控件背后真正会露出来的底色。

    优先用它自己的 bg（调用方通常把它设成父容器的真实底色：
    页面是 PANEL、卡片是 CARD、侧栏是被采样过的局部色），
    只有在 bg 缺失/是系统默认色时才回退到按窗口坐标采样背景。
    这样九宫格边缘的透明角就永远和父容器同色，不会出现方块底。
    """
    try:
        own = str(widget.cget("bg") or "")
        if own and own.lower() not in ("systembuttonface", "systemwindow"):
            return own
    except Exception:
        pass
    try:
        top = widget.winfo_toplevel()
        x = widget.winfo_rootx() - top.winfo_rootx()
        y = widget.winfo_rooty() - top.winfo_rooty()
        w = max(1, widget.winfo_width())
        h = max(1, widget.winfo_height())
        return ui_backdrop.color_at(x, y, w, h)
    except Exception:
        return T.get("BG")


def surface_color(widget, tint: float = 0.10) -> str:
    try:
        return T.blend(T.blend(_local_bg(widget), "#ffffff", tint), T.get("BG"), 0.0)
    except Exception:
        return _local_bg(widget)


def _photo(spec: str, size, bg: str, state: str = "normal"):
    return SKINS.photo(spec, size[0], size[1], bg, state=state)


# —— 卡片 ——

class _Card(tk.Frame):
    """圆角卡片：一张皮肤垫底，`.inner` 里放内容。"""

    def __init__(self, master, *, bg=None, fill=None, outline=None, accent="",
                 radius: int = 18, inset: int = 18):
        bg = bg or T.get("BG")
        fill = fill or T.get("CARD")
        self._bg = bg
        self._fill = fill
        self._accent = accent
        self._radius = radius
        self._inset = inset
        super().__init__(master, bg=bg)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        # Canvas.lower 是画布元素命令，把「窗口」压到底层要走 Tk 原生命令。
        self._canvas.tk.call("lower", self._canvas._w)
        self.inner = tk.Frame(self, bg=fill)
        self.inner.pack(fill="both", expand=True, padx=inset, pady=inset)
        self._photo_image = None
        self._spec_name = self._pick_spec(fill)
        self._canvas.bind("<Configure>", self._redraw)
        self.bind("<Destroy>", lambda _e: None)

    @staticmethod
    def _pick_spec(fill: str) -> str:
        role = T.role_of(fill)
        if role == "PANEL":
            return "panel"
        if role == "DIARY_BG":
            return "diary"
        return "card"

    def _redraw(self, _event=None) -> None:
        width = max(4, self._canvas.winfo_width())
        height = max(4, self._canvas.winfo_height())
        photo = _photo(self._spec_name, (width, height), _local_bg(self))
        self._canvas.delete("skin")
        if photo is not None:
            self._photo_image = photo
            self._canvas.create_image(0, 0, anchor="nw", image=photo, tags="skin")
        else:
            self._canvas.configure(bg=self._fill)
        # 皮肤缺失/被压扁时也保证有一圈看得见的描边。
        try:
            self._canvas.create_rectangle(0, 0, width - 1, height - 1,
                                          outline=T.get("BORDER_HI"), width=1,
                                          tags="skin")
        except Exception:
            pass
        if self._accent:
            self._canvas.delete("accent")
            inset = int(self._radius)
            band = max(6, height - inset * 2)
            self._canvas.create_rectangle(3, inset, 6, inset + band,
                                          fill=self._accent, outline="",
                                          tags="accent")


# —— 药丸按钮 ——

class _Pill(tk.Canvas):
    """圆角小按钮 / 标签：只有一张皮肤和一个居中的字。"""

    def __init__(self, master, text, command=None, *, bg=None, fill=None,
                 hover=None, fg=None, outline=None, font=None, pad_x: int = 14,
                 height: int = 30, radius=None, anchor: str = "w", min_width: int = 0):
        bg = bg or T.get("BG")
        fill = fill or T.get("CARD")
        fg = fg or T.get("TEXT_SOFT")
        self._bg = bg
        self._fill = fill
        self._hover_color = hover
        self._fg = fg
        self._outline = outline or T.get("BORDER")
        self._radius = radius
        self._pad_x = int(pad_x)
        self._height = int(height)
        self._anchor = anchor
        self._min_width = int(min_width)
        self._command = command
        self._text = str(text)
        self._enabled = True
        self._hovered = False
        self._pressed = False
        self._font = font or T.font(T.FONT_SMALL)
        self._spec = self._pick_spec(fill)
        self._photo_image = None
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, takefocus=0,
                         height=self._height)
        self._configure_width()
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _pick_spec(self, fill: str) -> str:
        try:
            normalized = str(fill).lower()
        except Exception:
            normalized = ""
        if normalized and normalized == str(T.get("ACCENT")).lower():
            return "primary"
        if normalized == str(T.get("DANGER_SOFT")).lower():
            return "pill_danger"
        if normalized == str(T.get("SENSE_SOFT")).lower():
            return "pill_sense"
        if normalized == str(T.get("ACCENT_SOFT")).lower():
            return "pill_accent"
        if normalized == str(T.get("SURFACE")).lower():
            return "pill_soft"
        if normalized == str(T.get("PANEL")).lower():
            return "pill_soft"
        return "pill"

    def _text_length(self) -> int:
        return int(T.text_width(self._text, self._font))

    def _configure_width(self) -> None:
        self.configure(width=max(self._min_width, self._text_length() + self._pad_x * 2),
                       height=self._height)

    def _redraw(self, _event=None) -> None:
        width = max(4, self.winfo_width())
        height = max(4, self.winfo_height())
        self.delete("all")
        state = "disabled" if not self._enabled else (
            "pressed" if self._pressed else ("hover" if self._hovered else "normal"))
        photo = _photo(self._spec, (width, height), _local_bg(self), state)
        if photo is not None:
            self._photo_image = photo
            self.create_image(0, 0, anchor="nw", image=photo)
        else:
            self.configure(bg=self._fill)
        color = self._fg if self._enabled else T.get("FAINT")
        if self._anchor == "center":
            x, anchor = width // 2, "center"
        else:
            x, anchor = self._pad_x, "w"
        self.create_text(x, height // 2, text=self._text, fill=color,
                         font=self._font, anchor=anchor)

    def _on_enter(self, _event=None):
        self._hovered = True
        self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event=None):
        if not self._enabled:
            return
        self._pressed = True
        self._redraw()

    def _on_release(self, _event=None):
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and self._enabled and callable(self._command):
            self._command()

    # —— 兼容旧接口 ——

    def set_text(self, text) -> None:
        self._text = str(text)
        self._configure_width()
        self._redraw()

    def set_colors(self, *, fill=None, outline=None, fg=None, hover=None) -> None:
        if fill is not None:
            self._fill = fill
            self._spec = self._pick_spec(fill)
        if outline is not None:
            self._outline = outline
        if fg is not None:
            self._fg = fg
        if hover is not None:
            self._hover_color = hover
        self._redraw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled and callable(self._command) else "")
        self._redraw()

    def get_width(self) -> int:
        return max(self._min_width, self._text_length() + self._pad_x * 2)


# —— 开关 ——

class _Toggle(tk.Canvas):
    """圆角开关：两条轨道皮肤 + 一枚圆形把手。"""

    def __init__(self, master, value: bool = False, command=None, *,
                 bg=None, width: int = T.TOGGLE_W, height: int = T.TOGGLE_H):
        bg = bg or T.get("BG")
        self._bg = bg
        self._value = bool(value)
        self._command = command
        self._w = int(width)
        self._h = int(height)
        self._hovered = False
        self._photo_image = None
        super().__init__(master, width=self._w, height=self._h, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", lambda _e: self.configure(cursor="hand2"))
        self.bind("<Leave>", lambda _e: self.configure(cursor=""))

    def _redraw(self, _event=None) -> None:
        width = max(8, self.winfo_width())
        height = max(8, self.winfo_height())
        self.delete("all")
        track = "toggle_on" if self._value else "toggle_off"
        photo = _photo(track, (width, height), _local_bg(self))
        if photo is not None:
            self._photo_image = photo
            self.create_image(0, 0, anchor="nw", image=photo)
        else:
            self.create_rectangle(0, 0, width, height, fill=T.get("ACCENT"), outline="")
        knob_size = max(10, height - 4)
        knob_bg = T.get("ACCENT_HI") if self._value else T.get("TRACK_OFF")
        knob = SKINS.photo("knob", knob_size, knob_size, knob_bg)
        x = width - knob_size - 2 if self._value else 2
        if knob is not None:
            self.create_image(x, 2, anchor="nw", image=knob)
        else:
            self.create_oval(x, 2, x + knob_size, height - 2, fill=T.get("KNOB"), outline="")

    def _toggle(self, _event=None) -> None:
        self._value = not self._value
        self._redraw()
        if callable(self._command):
            self._command(self._value)

    def get(self) -> bool:
        return self._value

    def set(self, value) -> None:
        self._value = bool(value)
        self._redraw()


# —— 气泡 ——

class _Bubble(tk.Canvas):
    """聊天气泡：按文字量自动换行，用气泡皮肤铺底。"""

    def __init__(self, master, text, *, bg=None, fill=None, outline=None, fg=None,
                 font=None, max_width: int = 300, radius: int = 16,
                 pad_x: int = 16, pad_y: int = 11):
        bg = bg or T.get("BG")
        self._bg = bg
        self._fill = fill or T.get("CARD")
        self._fg = fg or T.get("TEXT")
        self._font = font or T.font(T.FONT_BODY)
        self._text = str(text)
        self._max_width = int(max_width)
        self._pad_x = int(pad_x)
        self._pad_y = int(pad_y)
        self._spec = self._pick_spec(fill)
        self._photo_image = None
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self._text_id = self.create_text(0, 0, text=self._text, fill=self._fg,
                                         font=self._font, anchor="nw",
                                         width=max(60, self._max_width))
        self.bind("<Configure>", self._redraw)
        self._layout()

    def _pick_spec(self, fill) -> str:
        normalized = str(fill or "").lower()
        if normalized == str(T.get("HER_BUBBLE")).lower():
            return "bubble_me"
        if normalized == str(T.get("GUEST_BG")).lower():
            return "bubble_guest"
        if normalized == str(T.get("CARD")).lower():
            return "bubble_her"
        return "bubble_her"

    def _layout(self) -> None:
        try:
            bbox = self.bbox(self._text_id)
        except Exception:
            bbox = None
        text_w = (bbox[2] - bbox[0]) if bbox else self._max_width
        text_h = (bbox[3] - bbox[1]) if bbox else 24
        margin = 6
        width = min(self._max_width + self._pad_x * 2, text_w + self._pad_x * 2) + margin * 2
        height = text_h + self._pad_y * 2 + margin * 2
        self.configure(width=max(80, width), height=max(40, height))
        self.coords(self._text_id, margin + self._pad_x, margin + self._pad_y)
        self._redraw()

    def _redraw(self, _event=None) -> None:
        width = max(8, self.winfo_width())
        height = max(8, self.winfo_height())
        if self._photo_image is not None:
            # 尺寸变了才重画底图
            if (self._photo_image.width(), self._photo_image.height()) == (width, height):
                return
        photo = _photo(self._spec, (width, height), _local_bg(self))
        self.delete("skin")
        if photo is not None:
            self._photo_image = photo
            self.create_image(0, 0, anchor="nw", image=photo, tags="skin")
            self.tag_lower("skin")
        self.tag_raise(self._text_id)

    def set_max_width(self, max_width: int) -> None:
        self._max_width = int(max_width)
        self.itemconfigure(self._text_id, width=max(60, self._max_width))
        self._layout()


# —— 滚动区 ——

class _ThinBar(tk.Canvas):
    """细滚动条：轨道 + 滑块都用皮肤，内容装得下时自己藏起来。"""

    def __init__(self, master, canvas, *, bg=None, width: int = 6):
        bg = bg or T.get("BG")
        self._bg = bg
        self._canvas = canvas
        self._bar_width = int(width)
        self._first = 0.0
        self._last = 1.0
        self._hovered = False
        self._photo_image = None
        super().__init__(master, width=self._bar_width, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set(self, first, last) -> None:
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(self._first, min(1.0, float(last)))
        except (TypeError, ValueError):
            return
        self._redraw()

    def _redraw(self, _event=None) -> None:
        width = max(2, self.winfo_width() or self._bar_width)
        height = max(4, self.winfo_height())
        self.delete("all")
        if self._last - self._first <= 0.001:
            return
        self._photo_image = None
        photo = _photo("scroll_track", (width, height), _local_bg(self))
        if photo is not None:
            self.create_image(0, 0, anchor="nw", image=photo)
        else:
            self.create_rectangle(0, 0, width, height, fill=T.get("SCROLL"), outline="")
        span = max(0.08, self._last - self._first)
        top = int(self._first * height)
        bottom = max(top + 18, int((self._first + span) * height))
        bottom = min(height, bottom)
        state = "hover" if self._hovered else "normal"
        thumb = _photo("scroll_thumb", (width, bottom - top), _local_bg(self), state)
        if thumb is not None:
            self.create_image(0, top, anchor="nw", image=thumb)
        else:
            self.create_rectangle(0, top, width, bottom, fill=T.get("SCROLL_HI"), outline="")

    def _on_click(self, event):
        height = max(1, self.winfo_height())
        self._canvas.yview_moveto(max(0.0, min(1.0, event.y / height)))
        self._canvas.event_generate("<Motion>")

    def _on_drag(self, event):
        height = max(1, self.winfo_height())
        self._canvas.yview_moveto(max(0.0, min(1.0, event.y / height)))

    def _on_enter(self, _event=None):
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._redraw()


class _ScrollFrame(tk.Frame):
    """可滚动的容器：`.frame` 里放内容，超出时右侧出现细滚动条。"""

    def __init__(self, master, bg=None, bar_width: int = 6,
                 max_content_width: int = 0, backdrop: bool = False):
        bg = bg or T.get("BG")
        self._bg = bg
        self._backdrop = bool(backdrop)
        self._bar_width = int(bar_width)
        self._max_content_width = int(max_content_width or 0)
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, takefocus=1)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.frame = tk.Frame(self.canvas, bg=bg)
        self._window_id = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.bar = _ThinBar(self, self.canvas, bg=bg, width=self._bar_width)
        self._bar_visible = False
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.frame.bind("<Configure>", self._on_content)
        self.canvas.bind("<Configure>", self._on_view)
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.frame)

    # —— 尺寸与滚动 ——

    def _on_content(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._refresh_bar()
        self._bind_wheel_tree(self.frame)

    def _on_view(self, _event=None) -> None:
        canvas_w = max(1, self.canvas.winfo_width())
        width = max(80, canvas_w - self._bar_width - 6)
        if self._max_content_width:
            width = min(width, self._max_content_width)
        x = max(0, (canvas_w - width) // 2)
        self.canvas.itemconfigure(self._window_id, width=width)
        try:
            self.canvas.coords(self._window_id, x, 0)
        except Exception:
            pass
        if self._backdrop:
            try:
                _backdrop.paint(self.canvas, canvas_w,
                                max(1, self.canvas.winfo_height()))
            except Exception:
                pass
        self._refresh_bar()

    def _on_scroll(self, first, last) -> None:
        try:
            self.bar.set(first, last)
        except Exception:
            pass
        self._refresh_bar()

    def _refresh_bar(self) -> None:
        try:
            region = self.canvas.bbox("all")
            content_h = (region[3] - region[1]) if region else 0
            view_h = self.canvas.winfo_height()
            first, last = self.canvas.yview()
        except Exception:
            return
        scrollable = content_h > view_h + 4 and (last - first) < 0.999
        if scrollable and not self._bar_visible:
            self.bar.place(relx=1.0, x=-(self._bar_width + 4), y=4,
                           relheight=1.0, height=-8, width=self._bar_width)
            self._bar_visible = True
        elif not scrollable and self._bar_visible:
            self.bar.place_forget()
            self._bar_visible = False

    def scroll_to_end(self) -> None:
        self.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def yview_moveto(self, fraction: float) -> None:
        self.canvas.yview_moveto(fraction)

    def yview(self):
        return self.canvas.yview()

    # —— 滚轮 ——

    def _bind_wheel(self, widget) -> None:
        try:
            widget.bind("<MouseWheel>", self._on_wheel, add="+")
        except Exception:
            pass

    def _on_wheel(self, event):
        try:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            self.canvas.yview_scroll(delta * 2, "units")
            return "break"
        except Exception:
            return None

    def _bind_wheel_tree(self, widget) -> None:
        try:
            for child in widget.winfo_children():
                self._bind_wheel_tree(child)
        except Exception:
            return
        self._bind_wheel(widget)


# —— 输入框 ——

_PLACEHOLDER_SAFE_KEYS = frozenset({
    "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Caps_Lock", "Escape", "Tab", "Return", "KP_Enter", "Super_L", "Super_R", "ISO_Left_Tab",
})


class _InputBox(tk.Frame):
    """圆角输入框：皮肤铺底，里面是真的 Text。"""

    def __init__(self, master, *, bg=None, fill=None, outline=None, radius: int = T.RADIUS_INPUT,
                 pad: int = 16, font=None, lines: int = 2):
        bg = bg or T.get("SURFACE")
        self._bg = bg
        self._fill = fill or T.get("INPUT_BG")
        self._pad = int(pad)
        self._font = font or T.font(T.FONT_BODY)
        self._lines = int(lines)
        self._photo_image = None
        self._placeholder_text = ""
        self._placeholder_active = False
        super().__init__(master, bg=bg)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.text = tk.Text(self, bg=self._fill, fg=T.get("TEXT"), bd=0,
                            highlightthickness=0, insertbackground=T.get("TEXT"),
                            selectbackground=T.get("ACCENT_SOFT"),
                            selectforeground=T.get("TEXT"),
                            font=self._font, wrap="word", undo=True,
                            padx=2, pady=2, height=self._lines)
        self.text.pack(fill="both", expand=True,
                       padx=self._pad + 4, pady=self._pad)
        self._canvas.bind("<Configure>", self._redraw)
        self.text.bind("<FocusIn>", self._on_focus, add="+")
        self.text.bind("<FocusOut>", self._on_blur, add="+")
        self.text.bind("<KeyPress>", self._on_key_press, add="+")
        self.text.bind("<KeyRelease>", self._sync_after_key, add="+")
        self.text.bind("<<Paste>>", self._on_clipboard, add="+")
        self.text.bind("<<Cut>>", self._on_clipboard, add="+")
        self._min_height = T.INPUT_H
        self.configure(height=self._wanted_height())
        self.after(0, self._redraw)

    # —— 外观 ——

    def _wanted_height(self) -> int:
        try:
            line_height = int(self.text.tk.call("font", "metrics", self._font, "-linespace"))
        except Exception:
            line_height = 18
        lines = max(self._lines, 1)
        return max(self._min_height, line_height * lines + self._pad * 2)
    def _redraw(self, _event=None) -> None:
        width = max(4, self._canvas.winfo_width() or self.winfo_width())
        height = max(4, self._canvas.winfo_height() or self.winfo_height())
        state = "focus" if self.text.focus_get() is self.text else "normal"
        photo = _photo("input", (width, height), _local_bg(self), state)
        self._canvas.delete("skin")
        if photo is not None:
            self._photo_image = photo
            self._canvas.create_image(0, 0, anchor="nw", image=photo, tags="skin")
        else:
            self._canvas.configure(bg=self._fill)

    def _on_focus(self, _event=None) -> None:
        # 聚焦不清占位符：旧版就是聚焦也留着提示，真正按键时才让开。
        self._redraw()

    def _on_blur(self, _event=None) -> None:
        self._redraw()
        if not self.text.get("1.0", "end").strip():
            self._show_placeholder()

    def _on_key_press(self, event) -> None:
        if not self._placeholder_active:
            return
        keysym = str(getattr(event, "keysym", ""))
        if keysym in _PLACEHOLDER_SAFE_KEYS:
            return
        if int(getattr(event, "state", 0) or 0) & 0x4:  # Ctrl 快捷键
            return
        self._hide_placeholder()

    def _on_clipboard(self, _event=None) -> None:
        self._hide_placeholder()

    def _sync_after_key(self, _event=None) -> None:
        if self._placeholder_active and self.text.get("1.0", "end").strip():
            self._hide_placeholder()

    # —— 占位符 ——

    def set_placeholder(self, text: str) -> None:
        self._placeholder_text = str(text or "")
        self.refresh_placeholder()

    def refresh_placeholder(self) -> None:
        if not self._placeholder_text:
            return
        if not self.text.get("1.0", "end").strip():
            self._placeholder_active = False
            self._show_placeholder()
        else:
            self._hide_placeholder()

    def sync_placeholder(self) -> None:
        self.refresh_placeholder()

    def _show_placeholder(self) -> None:
        if self._placeholder_active or not self._placeholder_text:
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self._placeholder_text)
        self.text.mark_set("insert", "1.0")
        self.text.tag_add("placeholder", "1.0", "end-1c")
        self.text.tag_configure("placeholder", foreground=T.get("FAINT"))
        self._placeholder_active = True

    def _hide_placeholder(self) -> None:
        if not self._placeholder_active:
            return
        self.text.delete("1.0", "end")
        self.text.tag_delete("placeholder")
        self._placeholder_active = False

    # —— 尺寸与文本 ——

    def fit(self) -> None:
        text = self.text.get("1.0", "end-1c")
        lines = max(self._lines, text.count("\n") + 1)
        try:
            line_height = int(self.text.tk.call("font", "metrics", self._font, "-linespace"))
        except Exception:
            line_height = 18
        height = max(self._min_height, line_height * lines + self._pad * 2)
        self.configure(height=height)

    def get_text(self) -> str:
        if self._placeholder_active:
            return ""
        return self.text.get("1.0", "end-1c")

    def clear(self) -> None:
        self._placeholder_active = False
        self.text.delete("1.0", "end")
        self.text.tag_delete("placeholder")
        if self._placeholder_text:
            self._show_placeholder()

    def focus_input(self) -> None:
        try:
            self.text.focus_set()
        except Exception:
            pass


# —— 导航项 ——

class _NavItem(tk.Canvas):
    """侧栏的一项：图标 + 文字 + 选中/悬停皮肤。"""

    HEIGHT = 38

    def __init__(self, master, icon, label, command, *, bg=None):
        bg = bg or T.get("SIDEBAR_BG")
        self._bg = bg
        self._icon = str(icon)
        self._label = str(label)
        self._command = command
        self._selected = False
        self._hovered = False
        self._photo_image = None
        self._icons = {
            "chat": "💬", "diary": "📖", "memory": "🧠", "settings": "⚙",
        }
        # 行高跟着字体度量走：DPI/字号一变，行高自动跟上，不会互相压住。
        try:
            self.HEIGHT = int(T.row_height(T.font(T.FONT_NAV), minimum=44))
        except Exception:
            self.HEIGHT = 38
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         height=self.HEIGHT, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", lambda _e: self._command() if callable(self._command) else None)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", lambda _e: self._on_click())

    def _on_enter(self, _event=None):
        self._hovered = True
        self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def _on_click(self):
        if callable(self._command):
            self._command()

    def _redraw(self, _event=None) -> None:
        width = max(4, self.winfo_width())
        height = max(4, self.winfo_height())
        self.delete("all")
        local = _local_bg(self)
        if self._selected:
            # 1.24：不再用带描边的 pill 皮肤，改为「accent 14% 平填 + 3px 左侧指示条」。
            fill = T.blend(local, T.get("ACCENT"), 0.14)
            self.create_rectangle(0, 1, width, height - 1, fill=fill, outline="")
            self.create_rectangle(0, 3, 3, height - 3, fill=T.get("ACCENT"), outline="")
        elif self._hovered:
            fill = T.blend(local, T.get("TEXT"), 0.05)
            self.create_rectangle(0, 1, width, height - 1, fill=fill, outline="")
        color = T.get("TEXT") if self._selected else (
            T.get("TEXT_SOFT") if self._hovered else T.get("MUTED"))
        self.create_text(18, height // 2, text=self._icon, anchor="w",
                         font=T.font(13, family="emoji"), fill=color)
        self.create_text(40, height // 2, text=self._label, anchor="w",
                         fill=color, font=T.font(T.FONT_NAV, "bold" if self._selected else ""))

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._redraw()

    def set_label(self, label: str) -> None:
        self._label = str(label)
        self._redraw()


# —— 表单小件 ——

def _section(parent, title: str, subtitle: str = "", *, bg=None):
    """设置卡片的标题块：一条短强调线 + 标题 + 说明。返回标题 Frame。"""
    bg = bg or T.get("CARD")
    holder = tk.Frame(parent, bg=bg)
    head = tk.Frame(holder, bg=bg)
    head.pack(fill="x", pady=(0, 3))
    tk.Frame(head, bg=T.get("ACCENT"), width=3, height=14).pack(
        side="left", padx=(0, 8), pady=(4 if subtitle else 2, 0))
    tk.Label(head, text=title, bg=bg, fg=T.get("TEXT"),
             font=T.font(T.FONT_SECTION, "bold"), anchor="w").pack(side="left")
    if subtitle:
        tk.Label(holder, text=subtitle, bg=bg, fg=T.get("MUTED"),
                 font=T.font(T.FONT_SMALL), anchor="w", justify="left",
                 wraplength=620).pack(fill="x", pady=(3, 0))
    # 旧调用面是 `_section(box, ...)` 直接丢弃返回值；新 helper 自己 pack 好，
    # 同时返回 holder 供需要再装饰的调用方使用。
    holder.pack(fill="x", pady=(0, 12))
    return holder


def _field(parent, label: str, bg=None, value="", *, hint=""):
    """一行表单：小标题 + 输入框；返回里面的 tk.Entry。"""
    bg = bg or T.get("CARD")
    wrapper = tk.Frame(parent, bg=bg)
    wrapper.pack(fill="x", pady=(0, 16))
    if label:
        tk.Label(wrapper, text=label, bg=bg, fg=T.get("MUTED"),
                 font=T.font(T.FONT_TINY), anchor="w").pack(fill="x", pady=(0, 4))
    box = tk.Frame(wrapper, bg=bg)
    box.pack(fill="x")
    canvas = tk.Canvas(box, height=T.INPUT_H, bg=bg, highlightthickness=0, bd=0)
    canvas.place(x=0, y=0, relwidth=1, relheight=1)
    entry = tk.Entry(box, bd=0, highlightthickness=0, bg=T.get("INPUT_BG"),
                     fg=T.get("TEXT"), insertbackground=T.get("TEXT"),
                     font=T.font(T.FONT_BODY), relief="flat")
    entry.pack(fill="x", padx=16, pady=12)
    photo_holder = {"photo": None}

    def redraw(_event=None):
        width = max(4, canvas.winfo_width())
        height = max(4, canvas.winfo_height())
        photo = SKINS.photo("input", width, height, bg)
        canvas.delete("skin")
        if photo is not None:
            photo_holder["photo"] = photo
            canvas.create_image(0, 0, anchor="nw", image=photo, tags="skin")

    canvas.bind("<Configure>", redraw)
    box.configure(height=T.INPUT_H)
    if value:
        entry.insert(0, str(value))
    if hint:
        tk.Label(wrapper, text=hint, bg=bg, fg=T.get("FAINT"),
                 font=T.font(T.FONT_MICRO), anchor="w").pack(fill="x", pady=(3, 0))
    entry._skin_holder = wrapper
    return entry


def _flow_chips(parent, bg=None, specs=(), *, limit: int = 430, font=None,
                pad_x: int = 14, height: int = 30, gap: int = 8, on_layout=None):
    """把一排按钮（Pill）按宽度自动折行；返回 pill 列表（旧调用面可迭代）。

    换行布局不再一次算死：父容器变宽变窄时重排，旧设置页的预设 chips 靠这个
    才不会被窗口挤出边界。`on_layout` 在每次重排后回调，供调用方重新贴选中态。
    """
    bg = bg or T.get("CARD")
    normalized = []
    for item in specs:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("label") or item.get("value") or "")
            callback = item.get("command")
            colors = item
        else:
            text = str(item[0]) if item else ""
            callback = item[1] if len(item) > 1 else None
            colors = {}
        normalized.append((text, callback, colors))
    wrapper = tk.Frame(parent, bg=bg)
    wrapper.pack(fill="x")
    made: list = []
    state = {"width": int(limit), "after": None}

    def relayout(avail: int) -> None:
        for child in list(wrapper.winfo_children()):
            child.destroy()
        made[:] = []
        line = None
        used = 0
        for text, callback, colors in normalized:
            pill = _Pill(wrapper, text, callback, bg=bg,
                         fill=colors.get("fill", T.get("CARD")),
                         hover=colors.get("hover", T.get("CARD_HI")),
                         fg=colors.get("fg", T.get("TEXT_SOFT")),
                         outline=colors.get("outline", T.get("BORDER")),
                         font=font or T.font(T.FONT_TINY), pad_x=pad_x,
                         height=height)
            chip_width = pill.get_width() + gap
            if line is None or (used + chip_width > avail and used > 0):
                line = tk.Frame(wrapper, bg=bg)
                line.pack(fill="x", pady=(0, gap))
                used = 0
            pill.pack(in_=line, side="left", padx=(0, gap))
            made.append(pill)
            used += chip_width
        if callable(on_layout):
            try:
                on_layout()
            except Exception:
                pass

    def apply_width(width: int) -> None:
        try:
            if not parent.winfo_exists():
                return
        except Exception:
            return
        width = max(160, int(width) - 4)
        if abs(width - state["width"]) < 8:
            return
        state["width"] = width
        relayout(width)

    def on_configure(event) -> None:
        width = int(getattr(event, "width", 0) or 0)
        if width < 80:
            return
        try:
            if state["after"] is not None:
                parent.after_cancel(state["after"])
        except Exception:
            pass
        try:
            state["after"] = parent.after(60, lambda: apply_width(width))
        except Exception:
            apply_width(width)

    parent.bind("<Configure>", on_configure, add="+")
    relayout(state["width"])
    return made



# —— 圆形按钮（发送 / 窗口按钮） ——

class _RoundButton(tk.Canvas):
    """圆形按钮：发送键用超采样圆皮肤，不再是像素圆。"""

    def __init__(self, master, command=None, *, bg=None, size: int = T.SEND_BTN,
                 spec: str = "send"):
        bg = bg or T.get("PANEL")
        self._bg = bg
        self._size = int(size)
        self._spec = spec
        self._command = command
        self._hovered = False
        self._pressed = False
        self._photo_image = None
        super().__init__(master, width=self._size, height=self._size, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _redraw(self, _event=None) -> None:
        size = min(max(20, self.winfo_width() or self._size), self._size)
        self.delete("all")
        state = "pressed" if self._pressed else ("hover" if self._hovered else "normal")
        photo = _photo(self._spec, (size, size), _local_bg(self), state)
        if photo is not None:
            self._photo_image = photo
            self.create_image(0, 0, anchor="nw", image=photo)

    def _on_enter(self, _event=None):
        self._hovered = True
        self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event=None):
        self._pressed = True
        self._redraw()

    def _on_release(self, _event=None):
        was = self._pressed
        self._pressed = False
        self._redraw()
        if was and callable(self._command):
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self.configure(state="normal" if enabled else "disabled",
                       cursor="hand2" if enabled else "")
        if not enabled:
            self._hovered = False
            self._pressed = False

    def set_text(self, _text) -> None:
        """兼容旧 _Pill 接口：圆按钮不吃文字，忽略。"""


# —— 标题栏窗口按钮 ——

class _WinButton(tk.Canvas):
    """标题栏右上角的最小化/最大化/关闭按钮。"""

    WIDTH = T.WIN_BTN_W
    HEIGHT = T.WIN_BTN_H
    HIT_W = 46
    HIT_H = 32

    def __init__(self, master, kind: str, command=None, *, bg=None):
        bg = bg or T.get("TITLEBAR_BG")
        self._bg = bg
        self._kind = str(kind)
        self._command = command
        self._hovered = False
        self._maximized = False
        self._photo_image = None
        super().__init__(master, width=self.HIT_W, height=self.HIT_H, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", lambda _e: self._command() if callable(self._command) else None)

    def _glyph_name(self) -> str:
        if self._kind == "max":  # noqa: SIM116
            return "restore" if self._maximized else "max"
        if self._kind == "min" or self._kind == "close":
            return self._kind
        if self._kind == "restore":
            return "restore"
        return "max"

    def _redraw(self, _event=None) -> None:
        self.delete("all")
        width, height = self.HIT_W, self.HIT_H
        # 命中区 46x32：悬停先铺一层圆角底，再叠 32x24 的窗钮皮肤，图标居中。
        if self._hovered:
            hover_fill = T.get("ERROR") if self._kind == "close" else T.get("TITLEBAR_HOVER")
            self.create_rectangle(0, 0, width, height, fill=hover_fill, outline="")
        spec = "title_close" if self._kind == "close" else "title_btn"
        state = "hover" if self._hovered else "normal"
        photo = _photo(spec, (self.WIDTH, self.HEIGHT), _local_bg(self), state)
        if photo is not None:
            self._photo_image = photo
            self.create_image(width // 2, height // 2, anchor="center", image=photo)
        glyph_bg = T.get("ERROR") if (self._kind == "close" and self._hovered) else self._bg
        glyph = SKINS.glyph(self._glyph_name(), glyph_bg)
        if glyph is not None:
            self._glyph_image = glyph
            self.create_image(width // 2, height // 2, anchor="center", image=glyph)

    def _on_enter(self, _event=None):
        self._hovered = True
        self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = bool(maximized)
        self._redraw()


class _TitleBar(tk.Frame):
    """无边框窗口的标题栏：品牌 + 一句副标题 + 右侧窗口按钮。"""

    HEIGHT = 32

    def __init__(self, master, subtitle: str = "", *, brand: str = "Seedbank",
                 on_close=None, controls: bool = True):
        self._bg = T.get("TITLEBAR_BG")
        super().__init__(master, bg=self._bg, height=self.HEIGHT)
        self.pack_propagate(False)
        self._subtitle = str(subtitle or "")
        left = tk.Frame(self, bg=self._bg)
        left.pack(side="left", fill="y", padx=(16, 0))
        self._mark = tk.Label(left, text="🐋", bg=self._bg, fg=T.get("ACCENT"),
                              font=T.font(13, family="emoji"))
        self._mark.pack(side="left", pady=(7, 0))
        tk.Label(left, text=brand, bg=self._bg, fg=T.get("TEXT"),
                 font=T.font(T.FONT_BRAND, "bold")).pack(side="left", padx=(8, 0), pady=(7, 0))
        tk.Label(left, text="·", bg=self._bg, fg=T.get("FAINT"),
                 font=T.font(T.FONT_SMALL)).pack(side="left", padx=(8, 6), pady=(7, 0))
        self.subtitle_label = tk.Label(left, text=self._subtitle, bg=self._bg,
                                       fg=T.get("MUTED"), font=T.font(T.FONT_SMALL))
        self.subtitle_label.pack(side="left", pady=(7, 0))
        self._drag_bindings(left)
        if controls:
            right = tk.Frame(self, bg=self._bg)
            right.pack(side="right", fill="y", padx=(0, 6))
            self._close_btn = _WinButton(right, "close", on_close, bg=self._bg)
            self._close_btn.pack(side="right")
            self._max_btn = _WinButton(right, "max", self._toggle_max, bg=self._bg)
            self._max_btn.pack(side="right", padx=(4, 0))
            self._min_btn = _WinButton(right, "min", self._minimize, bg=self._bg)
            self._min_btn.pack(side="right", padx=(4, 0))
        self.bind("<Configure>", self._redraw)
        self._photo_image = None
        self._drag_bindings(self)
        for widget in (self, left):
            widget.bind("<Double-Button-1>", lambda _e: self._toggle_max(), add="+")

    def _redraw(self, _event=None) -> None:
        width = max(4, self.winfo_width())
        height = max(4, self.winfo_height())
        photo = _photo("panel", (width, height), _local_bg(self))
        self.delete("skin") if hasattr(self, "delete") else None

    def _drag_bindings(self, widget) -> None:
        try:
            widget.bind("<Button-1>", self._start_drag, add="+")
        except Exception:
            pass

    def _window_module(self):
        import sys
        return sys.modules.get("seedbank.window")

    def _start_drag(self, _event=None):
        """交给 win32 的「按住标题栏拖窗口」，比手算坐标稳。"""
        module = self._window_module()
        if module is not None and hasattr(module, "_begin_window_drag"):
            try:
                module._begin_window_drag(self.winfo_toplevel())
            except Exception:
                pass
        return None

    def _minimize(self):
        module = self._window_module()
        try:
            toplevel = self.winfo_toplevel()
            if module is not None and hasattr(module, "_minimize_window"):
                module._minimize_window(toplevel)
            else:
                toplevel.iconify()
        except Exception:
            pass

    def _toggle_max(self):
        module = self._window_module()
        try:
            if module is not None and hasattr(module, "_toggle_maximize"):
                module._toggle_maximize(self.winfo_toplevel())
            self.sync()
        except Exception:
            pass

    def sync(self) -> None:
        module = self._window_module()
        try:
            zoomed = bool(module._is_zoomed(self.winfo_toplevel())) if module else False
            if hasattr(self, "_max_btn"):
                self._max_btn.set_maximized(zoomed)
        except Exception:
            pass

    def set_subtitle(self, text: str) -> None:
        self._subtitle = str(text or "")
        try:
            self.subtitle_label.configure(text=self._subtitle)
        except Exception:
            pass


# —— 滑块 ——

class _Slider(tk.Canvas):
    """细轨 + 圆把手；拖哪滚哪，值 0~1 或自定义范围。"""

    def __init__(self, master, value: float = 0.8, *, minimum: float = 0.0,
                 maximum: float = 1.5, step: float = 0.05, command=None,
                 bg=None, width: int = 300, height: int = 30):
        bg = bg or T.get("CARD")
        self._bg = bg
        self._min = float(minimum)
        self._max = float(maximum) if float(maximum) > float(minimum) else float(minimum) + 1.0
        self._step = max(0.0001, float(step))
        self._value = self._clamp(value)
        self._command = command
        self._width = int(width)
        self._height = int(height)
        self._photo_image = None
        self._knob_photo = None
        super().__init__(master, width=self._width, height=self._height,
                         bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_drag)
        self.bind("<B1-Motion>", self._on_drag)

    def _clamp(self, value) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = self._min
        value = max(self._min, min(self._max, value))
        steps = round((value - self._min) / self._step)
        return max(self._min, min(self._max, self._min + steps * self._step))

    def _ratio(self) -> float:
        return (self._value - self._min) / max(1e-9, self._max - self._min)

    def _redraw(self, _event=None) -> None:
        width = max(40, self.winfo_width() or self._width)
        height = max(12, self.winfo_height() or self._height)
        self.delete("all")
        track_h = 6
        y = height // 2 - track_h // 2
        track = _photo("meter_track", (width, track_h), _local_bg(self))
        if track is not None:
            self._photo_image = track
            self.create_image(0, y, anchor="nw", image=track)
        else:
            self.create_rectangle(0, y, width, y + track_h, fill=T.get("ENERGY_TRACK"), outline="")
        filled = max(4, int(width * self._ratio()))
        fill = _photo("meter_fill", (filled, track_h), _local_bg(self))
        if fill is not None:
            self._fill_photo = fill
            self.create_image(0, y, anchor="nw", image=fill)
        knob_size = 18
        knob_bg = T.get("CARD")
        knob = SKINS.photo("knob", knob_size, knob_size, knob_bg)
        x = max(0, min(width - knob_size, int(width * self._ratio()) - knob_size // 2))
        if knob is not None:
            self._knob_photo = knob
            self.create_image(x, height // 2 - knob_size // 2, anchor="nw", image=knob)
        else:
            self.create_oval(x, height // 2 - knob_size // 2,
                             x + knob_size, height // 2 + knob_size // 2,
                             fill=T.get("KNOB"), outline="")

    def _on_drag(self, event):
        width = max(1, self.winfo_width())
        ratio = max(0.0, min(1.0, event.x / width))
        value = self._clamp(self._min + ratio * (self._max - self._min))
        if abs(value - self._value) < 1e-9:
            return
        self._value = value
        self._redraw()
        if callable(self._command):
            self._command(self._value)

    def get(self) -> float:
        return self._value

    def set(self, value) -> None:
        self._value = self._clamp(value)
        self._redraw()


# —— 主题色块预览 ——

class _ThemeSwatch(tk.Canvas):
    """配色预览：用那套配色的 BG/CARD/ACCENT/TEXT 画一张小样，点了就换。"""

    WIDTH = 96
    HEIGHT = 60

    def __init__(self, master, key: str, command, *, bg=None):
        bg = bg or T.get("CARD")
        self._bg = bg
        self._key = str(key)
        self._command = command
        self._selected = False
        self._hovered = False
        self._photo_image = None
        super().__init__(master, width=self.WIDTH, height=self.HEIGHT,
                         bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _palette(self) -> dict:
        return T.THEMES.get(self._key, T.THEMES[T.DEFAULT_THEME])

    def _redraw(self, _event=None) -> None:
        width = max(40, self.winfo_width() or self.WIDTH)
        height = max(30, self.winfo_height() or self.HEIGHT)
        palette = self._palette()
        self.delete("all")
        border = palette.get("ACCENT") if self._selected else (
            palette.get("GOLD") if self._hovered else palette.get("BORDER_HI"))
        width_px = 2 if self._selected else 1
        # 一张 mini 窗口：顶栏 + 侧栏 + 主卡 + 两行字 + 一个按钮 + 一枚气泡
        self._round_rect(2, 2, width - 2, height - 2, 12,
                         fill=palette.get("BG", "#101010"), outline="")
        self.create_rectangle(5, 5, width - 5, 19,
                              fill=palette.get("PANEL", "#101010"), outline="")
        for index in range(3):
            cx = width - 12 - index * 8
            self.create_oval(cx - 2, 9, cx + 2, 13,
                             fill=palette.get("MUTED", "#999999"), outline="")
        self.create_rectangle(5, 20, 30, height - 6,
                              fill=palette.get("PANEL", "#101010"), outline="")
        for index in range(3):
            color = palette.get("ACCENT" if index == 0 else "TEXT_SOFT", "#cccccc")
            self.create_line(10, 28 + index * 9, 25, 28 + index * 9,
                             fill=color, width=2)
        self._round_rect(34, 24, width - 7, height - 8, 9,
                         fill=palette.get("CARD", "#202020"),
                         outline=palette.get("BORDER", "#333333"))
        self.create_line(41, 34, width - 18, 34,
                         fill=palette.get("TEXT_SOFT", "#cccccc"), width=3)
        self.create_line(41, 42, width - 34, 42,
                         fill=palette.get("MUTED", "#999999"), width=2)
        self._round_rect(41, 50, 66, 61, 6,
                         fill=palette.get("ACCENT", "#22aa99"), outline="")
        self._round_rect(72, 50, width - 14, 61, 6,
                         fill=palette.get("CARD_HI", "#333333"), outline="")
        self._round_rect(2, 2, width - 3, height - 3, 13,
                         fill="", outline=border, width=width_px)

    def _round_rect(self, x1, y1, x2, y2, radius, *, fill, outline="", width=1) -> None:
        import math

        radius = max(1, min(int(radius), int((x2 - x1) / 2), int((y2 - y1) / 2)))
        points = []
        # 顺时针：左上(180..270) → 右上(270..360) → 右下(0..90) → 左下(90..180)
        arcs = (
            (x1 + radius, y1 + radius, 180.0, 270.0),
            (x2 - radius, y1 + radius, 270.0, 360.0),
            (x2 - radius, y2 - radius, 0.0, 90.0),
            (x1 + radius, y2 - radius, 90.0, 180.0),
        )
        step = 6.0
        for cx, cy, start, end in arcs:
            angle = start
            while angle <= end + 0.01:
                radians = angle * math.pi / 180.0
                points.extend((cx + radius * math.cos(radians),
                               cy + radius * math.sin(radians)))
                angle += step
        if fill:
            self.create_polygon(points, fill=fill, outline="", smooth=False)
        if outline and width:
            self.create_polygon(points, fill="", outline=outline, width=width, smooth=False)

    def _on_enter(self, _event=None):
        self._hovered = True
        self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def _on_click(self, _event=None):
        if callable(self._command):
            self._command(self._key)

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._redraw()
