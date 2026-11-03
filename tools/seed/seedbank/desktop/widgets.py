from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from PIL import Image, ImageTk

from .render import icon_image, mix_color, panel_image, panel_strips, scrollbar_thumb_image, switch_image, theme_preview_image
from .theme import Theme


def label(parent, theme: Theme, text="", *, size=15, weight="normal", role="text", **kwargs):
    return tk.Label(parent, text=text, font=theme.font(size, weight), fg=theme.color(role),
                    bg=parent.cget("bg"), anchor="w", justify="left", **kwargs)


def paragraph(parent, theme, text, *, role="muted", size=13):
    widget = label(parent, theme, text, size=size, role=role, wraplength=440)
    widget.pack(fill="x", pady=(4, 8))
    widget.bind("<Configure>", lambda event: widget.configure(wraplength=max(80, event.width)), add="+")
    return widget


def wheel_direction(event):
    number = getattr(event, "num", None)
    delta = getattr(event, "delta", 0)
    if number == 4 or delta > 0:
        return -1
    if number == 5 or delta < 0:
        return 1
    return 0


class Card(tk.Frame):
    def __init__(self, parent, theme, *, tone="surface", padding=20, outlined=False, radius=22,
                 material="flat", **kwargs):
        super().__init__(parent, bg=parent.cget("bg"), bd=0, **kwargs)
        self.theme = theme
        self.tone = tone
        self.outlined = outlined
        self.radius = radius
        self.material = material
        self.fill = theme.color(tone) if tone else self.cget("bg")
        if not self.fill.startswith("#"):
            self.fill = "#" + "".join(f"{channel // 257:02x}" for channel in self.winfo_rgb(self.fill))
        self.focused = False
        self._paint_state = None
        self.art = tk.Canvas(self, highlightthickness=0, bd=0, bg=self.cget("bg"))
        self.art.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=self.fill, bd=0)
        padding = max(padding, round(radius * .3) + 4)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)
        self.bind("<Configure>", self._paint, add="+")

    def _paint(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 8 or height < 8:
            return
        state = width, height, self.focused
        if state == self._paint_state:
            return
        self._paint_state = state
        background = tuple(channel // 257 for channel in self.winfo_rgb(self.cget("bg")))
        floating = self.material == "navigation"
        border = self.theme.color("primary") if self.focused else self.theme.color("separator") if self.outlined or floating else self.fill
        options = dict(background=background, fill=self.fill, border=border,
                       shadow=mix_color(background, self.theme.color("shadow"), .25) if floating else background,
                       radius=self.radius, border_width=2 if self.focused else 1, soft_shadow=floating)
        self.art.delete("all")
        self._border_images = []
        if width * height > 150000 and not floating:
            self._image = None
            self.art.configure(bg=self.fill)
            for horizontal, vertical, strip in panel_strips((width, height), **options):
                picture = ImageTk.PhotoImage(strip, master=self.art)
                self._border_images.append(picture)
                self.art.create_image(horizontal, vertical, image=picture, anchor="nw")
        else:
            self.art.configure(bg=self.cget("bg"))
            self._image = ImageTk.PhotoImage(panel_image((width, height), **options), master=self.art)
            self.art.create_image(0, 0, image=self._image, anchor="nw")

    def set_focus(self, active):
        self.focused = active
        self._paint()


class Button(tk.Frame):
    def __init__(self, parent, theme, text, command, *, primary=False, danger=False,
                 icon_name="", width=None, selected=False, variant="secondary", preview=None, detail=None):
        self.theme = theme
        self.primary = primary
        self.danger = danger
        self.selected = selected
        self.enabled = True
        self.hovered = False
        self.focused = False
        self.pressed = False
        self.variant = variant
        self.preview = preview
        self.icon_name = icon_name
        self.command = command
        self.caption = text
        self.detail = None
        self.anim_id = None
        self._colors = None
        self._paint_state = None
        self._symbol_key = None
        measured = tkfont.Font(font=theme.font(14, "bold")).measure(text)
        super().__init__(parent, bg=parent.cget("bg"), width=width or measured + (78 if icon_name else 50),
                         height=round((120 if preview else 68 if detail is not None else 64 if variant == "navigation" else 46) * theme.scale), bd=0)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.art = tk.Canvas(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        self.art.place(x=0, y=0, relwidth=1, relheight=1)
        self.native = ttk.Button(self, text=text, command=self.invoke, cursor="hand2", takefocus=True, width=0)
        inset = 18
        self.native.place(x=inset, y=9, relwidth=1, width=-inset - 18, relheight=1, height=-20)
        if variant == "navigation":
            self.native.place(y=7)
        if preview:
            self.native.place(y=round(78 * theme.scale), relheight=0, height=round(26 * theme.scale))
        if detail is not None:
            self.native.place(y=round(8 * theme.scale), relheight=0, height=round(28 * theme.scale))
            self.detail = label(self, theme, detail, size=13, role="muted")
            self.detail.place(x=inset, y=round(36 * theme.scale), relwidth=1, width=-inset - 18,
                              height=max(round(20 * theme.scale), self.detail.winfo_reqheight()))
            self.detail.bind("<ButtonPress-1>", lambda event: self._press(True))
            self.detail.bind("<ButtonRelease-1>", self._release_detail)
        self.art.bind("<ButtonPress-1>", lambda event: self._press(True))
        self.art.bind("<ButtonRelease-1>", self._release_art)
        self.native.bind("<ButtonPress-1>", lambda event: self._press(True), add="+")
        self.native.bind("<ButtonRelease-1>", lambda event: self._press(False), add="+")
        self.native.bind("<KeyPress-space>", lambda event: self._press(True), add="+")
        self.native.bind("<KeyRelease-space>", lambda event: self._press(False), add="+")
        for child in (self, self.art, self.native, *([self.detail] if self.detail is not None else [])):
            child.bind("<Enter>", lambda event: self._hover(True), add="+")
            child.bind("<Leave>", lambda event: self._hover(False), add="+")
        self.native.bind("<FocusIn>", lambda event: self._focus(True))
        self.native.bind("<FocusOut>", lambda event: self._focus(False))
        self.native.bind("<Return>", self._activate_key)
        self.bind("<Configure>", self._paint, add="+")
        self.bind("<Destroy>", self._destroy, add="+")
        self._paint()

    def _hover(self, active):
        if self.hovered == active:
            return
        self.hovered = active
        self._paint(animate=not self.theme.reduced_motion)

    def _focus(self, active):
        self.focused = active
        if not active:
            self.pressed = False
        self._paint()

    def _press(self, active):
        self.pressed = active and self.enabled
        self._paint()

    def _release_art(self, event):
        was_pressed = self.pressed
        self._press(False)
        if was_pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def _release_detail(self, event):
        event.x += self.detail.winfo_x()
        event.y += self.detail.winfo_y()
        self._release_art(event)

    def _paint(self, event=None, *, animate=False):
        if self.anim_id:
            self.after_cancel(self.anim_id)
            self.anim_id = None
        fill_role = "primary" if self.primary else "soft" if self.selected or self.hovered else "field"
        if self.variant in ("ghost", "tab", "navigation", "list") and not (self.selected or self.hovered or self.primary):
            fill_role = None
        if self.primary and (self.hovered or self.pressed):
            fill_role = "hover"
        elif self.pressed:
            fill_role = "border"
        foreground = "on_primary" if self.primary else "danger" if self.danger else "primary" if self.selected or self.variant == "ghost" else "muted" if self.variant in ("tab", "navigation") else "text"
        if not self.enabled:
            fill_role, foreground = "disabled", "disabled_text"
        fill = self.theme.color(fill_role) if fill_role else self.cget("bg")
        if not fill.startswith("#"):
            fill = "#" + "".join(f"{channel // 257:02x}" for channel in self.winfo_rgb(fill))
        color = self.theme.color(foreground)
        if not animate or self._colors is None or not self.enabled:
            self._draw(fill, color)
            return
        initial = self._colors

        def blend(start, end, ratio):
            channels = [round(int(start[offset:offset + 2], 16) * (1 - ratio) + int(end[offset:offset + 2], 16) * ratio)
                        for offset in (1, 3, 5)]
            return "#" + "".join(f"{channel:02x}" for channel in channels)

        def advance(step=1):
            self.anim_id = None
            ratio = 1 - (1 - step / 9) ** 2
            self._draw(blend(initial[0], fill, ratio), blend(initial[1], color, ratio))
            if step < 9:
                self.anim_id = self.after(18, lambda: advance(step + 1))

        advance()

    def _draw(self, fill, color):
        self._colors = fill, color
        width, height = max(8, self.winfo_width()), max(8, self.winfo_height())
        background = self.cget("bg")
        state = (width, height, fill, color, background, self.focused, self.enabled,
                 self.selected, self.icon_name, self.preview, self.variant)
        if state == self._paint_state:
            return
        self._paint_state = state
        self.native.configure(style=self._text_style(fill, color), state="normal" if self.enabled else "disabled")
        if self.detail is not None:
            self.detail.configure(bg=fill, fg=self.theme.color("muted" if self.enabled else "disabled_text"))
        background = tuple(channel // 257 for channel in self.winfo_rgb(background))
        border = self.theme.color("primary") if self.focused else fill
        artwork = panel_image((width, height), background=background, fill=fill, border=border,
                              shadow=background, radius=16, border_width=2 if self.focused else 1)
        if self.icon_name:
            size = round(20 * self.theme.scale)
            symbol_key = self.icon_name, size, color, self.variant
            if symbol_key != self._symbol_key:
                self._symbol_key = symbol_key
                symbol = Image.new("RGBA", (size if self.variant == "navigation" else size + 8, size))
                symbol.alpha_composite(icon_image(self.icon_name, size, color))
                self._symbol = ImageTk.PhotoImage(symbol, master=self.native)
                self.native.configure(image=self._symbol, compound="top" if self.variant == "navigation" else "left")
        if self.selected and not self.preview:
            indicator = scrollbar_thumb_image((8, 18), self.theme.color("primary"), active=True)
            if self.variant in ("tab", "navigation"):
                indicator = indicator.transpose(Image.Transpose.ROTATE_90)
                artwork.alpha_composite(indicator, (max(0, (width - 18) // 2), max(0, height - 10)))
            else:
                artwork.alpha_composite(indicator, (6, max(0, (height - 18) // 2)))
        if self.preview and width > 40:
            preview_height = round(54 * self.theme.scale)
            artwork.alpha_composite(theme_preview_image((width - 32, preview_height), Theme(self.preview)), (16, 14))
            if self.selected:
                artwork.alpha_composite(icon_image("check", 20, color), (width - 37, 17))
        self._image = ImageTk.PhotoImage(artwork, master=self.art)
        self.art.delete("all")
        self.art.create_image(0, 0, image=self._image, anchor="nw")

    def _text_style(self, fill, color):
        root = self._root()
        style = ttk.Style(root)
        if not hasattr(root, "_desktop_button_styles"):
            root._desktop_button_styles = {}
        cache = root._desktop_button_styles
        font = self.theme.font(13 if self.variant == "navigation" else 14, "bold" if self.primary or self.selected else "normal")
        key = style.theme_use(), font, fill, color, self.detail is not None
        if key not in cache:
            name = f"SeedbankText{len(cache)}.TButton"
            style.layout(name, [("Button.label", {"sticky": "nswe"})])
            style.configure(name, font=font, background=fill, foreground=color,
                            padding=0, borderwidth=0, relief="flat", anchor="w" if self.detail is not None else "center")
            style.map(name, background=[("disabled", fill), ("!disabled", fill)],
                      foreground=[("disabled", color), ("!disabled", color)])
            cache[key] = name
        return cache[key]

    def _activate_key(self, event=None):
        self.invoke()
        return "break"

    def _destroy(self, event):
        if event.widget is self and self.anim_id:
            self.after_cancel(self.anim_id)
            self.anim_id = None

    def invoke(self):
        if self.enabled and self.command:
            self.native.focus_set()
            return self.command()

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        if self.enabled == enabled and not self.pressed:
            return
        self.enabled = enabled
        self.pressed = False
        self._paint()

    def set_selected(self, selected):
        selected = bool(selected)
        if self.selected == selected:
            return
        self.selected = selected
        self._paint()

    def set_text(self, text):
        self.caption = text
        self.native.configure(text=text)


class PillScrollbar(ttk.Scrollbar):
    def __init__(self, parent, theme, *, command):
        self.command = command
        root = parent._root()
        style = ttk.Style(root)
        if not hasattr(root, "_desktop_scrollbar_styles"):
            root._desktop_scrollbar_styles = {}
        cache = root._desktop_scrollbar_styles
        background = tuple(channel // 257 for channel in parent.winfo_rgb(parent.cget("bg")))
        key = style.theme_use(), theme.key, theme.scale, background
        if key not in cache:
            prefix = f"SeedbankScroll{len(cache)}"
            name = prefix + ".Vertical.TScrollbar"
            trough = prefix + ".Vertical.Scrollbar.trough"
            thumb = prefix + ".Vertical.Scrollbar.thumb"
            size = round(18 * theme.scale), round(36 * theme.scale)
            track = ImageTk.PhotoImage(Image.new("RGB", (size[0], 1), background), master=root)
            normal = ImageTk.PhotoImage(scrollbar_thumb_image(size, theme.color("scroll_thumb")), master=root)
            active = ImageTk.PhotoImage(scrollbar_thumb_image(size, theme.color("primary"), active=True), master=root)
            empty = ImageTk.PhotoImage(scrollbar_thumb_image(size, None), master=root)
            style.element_create(trough, "image", track, sticky="nswe")
            style.element_create(thumb, "image", normal, ("disabled", empty), ("pressed", active),
                                 ("active", active), border=(0, 6, 0, 6), padding=0, sticky="nswe")
            style.layout(name, [(trough, {"sticky": "nswe", "children": [
                (thumb, {"sticky": "nswe", "expand": True}),
            ]})])
            style.configure(name, borderwidth=0, relief="flat")
            cache[key] = name, (track, normal, active, empty)
        super().__init__(parent, orient="vertical", command=command, style=cache[key][0], takefocus=False)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", self._wheel)
        self.bind("<Button-5>", self._wheel)

    def set(self, first, last):
        super().set(first, last)
        full = float(first) <= 0 and float(last) >= 1
        self.state(["disabled"] if full else ["!disabled"])

    def _wheel(self, event):
        direction = wheel_direction(event)
        if direction and not self.instate(["disabled"]):
            self.command("scroll", direction * 3, "units")
        return "break"


class Scroll(tk.Frame):
    def __init__(self, parent, theme, *, max_width=None):
        super().__init__(parent, bg=parent.cget("bg"), bd=0)
        self.max_width = max_width
        self.canvas = tk.Canvas(self, bg=self.cget("bg"), highlightthickness=0, bd=0, yscrollincrement=24, width=1)
        self.bar = PillScrollbar(self, theme, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.frame = tk.Frame(self.canvas, bg=self.cget("bg"))
        self.item = self.canvas.create_window(0, 0, window=self.frame, anchor="nw", width=1)
        self.canvas.bind("<Configure>", self._resize)
        self.frame.bind("<Configure>", self._extent)

    def _resize(self, event):
        width = max(1, min(event.width - 2, self.max_width or event.width))
        self.canvas.itemconfigure(self.item, width=width)
        self.canvas.coords(self.item, max(0, (event.width - width) // 2), 0)

    def _extent(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scroll(self, units):
        if self.frame.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")

    def bottom(self):
        self.canvas.yview_moveto(1)


class Input(Card):
    def __init__(self, parent, theme, variable, *, secret=False, icon_name=""):
        super().__init__(parent, theme, tone="field", padding=12, radius=14)
        if icon_name:
            self._symbol = ImageTk.PhotoImage(icon_image(icon_name, round(20 * theme.scale), theme.color("muted")), master=self)
            symbol = label(self.body, theme, image=self._symbol)
            symbol.pack(side="left", padx=(0, 10))
            symbol.bind("<Button-1>", lambda event: self.control.focus_set())
        self.control = tk.Entry(self.body, textvariable=variable, font=theme.font(), width=1,
                                bd=0, relief="flat", highlightthickness=0,
                                bg=theme.color("field"), fg=theme.color("text"),
                                insertbackground=theme.color("primary"),
                                selectbackground=theme.color("primary"), selectforeground=theme.color("on_primary"),
                                show="•" if secret else "")
        self.control.pack(fill="both", expand=True)
        self.control.bind("<FocusIn>", lambda event: self.set_focus(True))
        self.control.bind("<FocusOut>", lambda event: self.set_focus(False))

    def focus_set(self):
        self.control.focus_set()

    def bind(self, sequence=None, func=None, add=None):
        target = self.control if hasattr(self, "control") and sequence != "<Configure>" else self
        return tk.Misc.bind(target, sequence, func, add)


def entry(parent, theme, variable, *, secret=False, icon_name=""):
    return Input(parent, theme, variable, secret=secret, icon_name=icon_name)


class Toggle(Card):
    def __init__(self, parent, theme, caption, variable, command=None):
        super().__init__(parent, theme, tone=None, padding=9, radius=12)
        self.control = ttk.Checkbutton(self.body, text=caption, variable=variable, command=command,
                                       style=self._style(380), cursor="hand2")
        self.control.pack(fill="x")
        self.control.bind("<FocusIn>", lambda event: self.set_focus(True))
        self.control.bind("<FocusOut>", lambda event: self.set_focus(False))
        self.control.bind("<Return>", lambda event: (self.control.invoke(), "break")[-1])
        self.control.bind("<Configure>", lambda event: self.control.configure(style=self._style(max(80, self.master.winfo_width() - round(90 * theme.scale)))))

    def _style(self, wraplength):
        root = self._root()
        if not hasattr(root, "_desktop_toggle_styles"):
            root._desktop_toggle_styles = {}
            root._desktop_switch_images = {}
        cache = root._desktop_toggle_styles
        style = ttk.Style(self)
        image_key = style.theme_use(), self.theme.key, self.theme.scale
        if image_key not in root._desktop_switch_images:
            element = f"SeedbankSwitchGlyph{len(root._desktop_switch_images)}.indicator"
            scale = self.theme.scale
            images = []
            for selected in (False, True):
                picture = Image.new("RGBA", (round(58 * scale), round(26 * scale)))
                picture.alpha_composite(switch_image((round(44 * scale), round(26 * scale)), self.theme, selected),
                                        (round(14 * scale), 0))
                images.append(ImageTk.PhotoImage(picture, master=root))
            style.element_create(element, "image", images[0], ("selected", images[1]), sticky="e")
            root._desktop_switch_images[image_key] = element, images
        element = root._desktop_switch_images[image_key][0]
        wraplength = max(80, wraplength // 16 * 16)
        background = self.body.cget("bg")
        key = image_key, self.theme.font(14), wraplength, background
        if key not in cache:
            name = f"SeedbankSwitch{len(cache)}.TCheckbutton"
            style.layout(name, [("Checkbutton.padding", {"sticky": "nswe", "children": [
                (element, {"side": "right", "sticky": "e"}),
                ("Checkbutton.label", {"sticky": "we"}),
            ]})])
            style.configure(name, background=background, foreground=self.theme.color("text"),
                            font=self.theme.font(14), padding=0, wraplength=wraplength, anchor="w")
            style.map(name, foreground=[("disabled", self.theme.color("disabled_text"))],
                      background=[("active", background)])
            cache[key] = name
        return cache[key]

    def configure(self, cnf=None, **kwargs):
        if "state" in kwargs:
            self.control.configure(state=kwargs.pop("state"))
        return super().configure(cnf, **kwargs)


class Select(Card):
    def __init__(self, parent, theme, **kwargs):
        super().__init__(parent, theme, tone="field", padding=12, radius=14)
        kwargs.setdefault("font", theme.font())
        self.control = ttk.Combobox(self.body, style="Seedbank.TCombobox", width=1, **kwargs)
        self.control.pack(fill="both", expand=True)
        self.control.bind("<FocusIn>", lambda event: self.set_focus(True))
        self.control.bind("<FocusOut>", lambda event: self.set_focus(False))
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.control.bind(sequence, self._wheel)

    def _wheel(self, event):
        parent = self.master
        direction = wheel_direction(event)
        while parent is not None:
            if isinstance(parent, Scroll):
                if direction:
                    parent.scroll(direction * 3)
                break
            parent = parent.master
        return "break"

    def bind(self, sequence=None, func=None, add=None):
        target = self.control if hasattr(self, "control") and sequence != "<Configure>" else self
        return tk.Misc.bind(target, sequence, func, add)

    def current(self, index=None):
        return self.control.current(index)

    def get(self):
        return self.control.get()

    def focus_set(self):
        self.control.focus_set()


class MessageBubble(tk.Frame):
    def __init__(self, parent, theme, who, text, *, incoming=True):
        super().__init__(parent, bg=parent.cget("bg"))
        self.bubble = Card(self, theme, tone="surface" if incoming else "soft", padding=14, radius=18)
        self.bubble.pack(anchor="w" if incoming else "e")
        self.sender = label(self.bubble.body, theme, who, size=13, role="primary", weight="bold", wraplength=300)
        self.sender.pack(anchor="w", pady=(0, 6))
        self.message = label(self.bubble.body, theme, text, size=15, wraplength=300)
        self.message.pack(anchor="w")
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        width = max(60, min(560, round(event.width * .84) - 32))
        self.message.configure(wraplength=width)
        self.sender.configure(wraplength=width)


def field(parent, theme, caption, variable, *, hint="", secret=False):
    frame = tk.Frame(parent, bg=parent.cget("bg"))
    frame.pack(fill="x", pady=(0, 16))
    label(frame, theme, caption, size=14, weight="bold").pack(fill="x", pady=(0, 6))
    control = entry(frame, theme, variable, secret=secret)
    control.pack(fill="x")
    if hint:
        paragraph(frame, theme, hint, size=12)
    return control


def reader(parent, theme, *, height=8):
    frame = Card(parent, theme, padding=10, radius=18)
    text = tk.Text(frame.body, font=theme.font(), wrap="word", bd=0, highlightthickness=0,
                   bg=theme.color("surface"), fg=theme.color("text"), padx=8, pady=6,
                   spacing1=4, spacing3=8, height=height, width=1, cursor="arrow", takefocus=True,
                   selectbackground=theme.color("soft"), selectforeground=theme.color("text"))
    text.bind("<FocusIn>", lambda event: frame.set_focus(True))
    text.bind("<FocusOut>", lambda event: frame.set_focus(False))
    bar = PillScrollbar(frame.body, theme, command=text.yview)
    text.configure(yscrollcommand=bar.set, state="disabled")
    text.tag_configure("heading1", font=theme.font(21, "bold"), spacing1=12, spacing3=10)
    text.tag_configure("heading2", font=theme.font(18, "bold"), spacing1=10, spacing3=8)
    text.tag_configure("heading3", font=theme.font(16, "bold"), spacing1=8, spacing3=6)
    bar.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    frame.pack(fill="both", expand=True)
    return text


def set_reader(widget, content, *, markdown=False):
    position = widget.yview()[0]
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    if markdown:
        fenced = False
        for line in content.splitlines(keepends=True):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                widget.insert("end", line)
                continue
            heading = re.match(r"^(#{1,3})\s+(.+?)(\n?)$", line) if not fenced else None
            if heading:
                widget.insert("end", heading.group(2) + heading.group(3), f"heading{len(heading.group(1))}")
            else:
                widget.insert("end", "• " + line[2:] if not fenced and line.startswith("- ") else line)
    else:
        widget.insert("1.0", content)
    widget.configure(state="disabled")
    widget.yview_moveto(position)
