from __future__ import annotations

import tkinter as tk

from .widgets import Button, PillScrollbar, wheel_direction


class DateList(tk.Frame):
    def __init__(self, parent, theme, rows):
        super().__init__(parent, bg=parent.cget("bg"), bd=0)
        self.theme = theme
        self.rows = tuple(rows)
        self.selected = None
        self.row_height = round(76 * theme.scale)
        self.scroll_unit = max(1, self.row_height // 3)
        self.pool = []
        self.canvas = tk.Canvas(self, bg=self.cget("bg"), bd=0, highlightthickness=0,
                                width=1, takefocus=True, yscrollincrement=self.scroll_unit)
        self.bar = PillScrollbar(self, theme, command=self.yview)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self._scrolled)
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<FocusIn>", self._focus)
        self.canvas.bind("<FocusOut>", lambda event: self._render_rows())
        self._bind_navigation(self.canvas)

    def _bind_navigation(self, widget):
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self._wheel)
        for key in ("Up", "Down", "Home", "End", "Prior", "Next"):
            widget.bind(f"<{key}>", self._key)

    def _resize(self, event):
        self.canvas.configure(scrollregion=(0, 0, event.width, max(1, len(self.rows) * self.row_height)))
        self._render_rows()

    def _scrolled(self, first, last):
        self.bar.set(first, last)
        self._render_rows()

    def _focus(self, event):
        if self.selected is not None:
            self.see(self.selected)
        self._render_rows()

    def _render_rows(self):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 16 or height < 16:
            return
        first = max(0, int(self.canvas.canvasy(0)) // self.row_height)
        visible = max(0, min(len(self.rows) - first, height // self.row_height + 2))
        while len(self.pool) < visible:
            button = Button(self.canvas, self.theme, "", None, detail="", variant="list", width=1)
            button.native.configure(takefocus=False)
            for child in (button, button.art, button.native, button.detail):
                self._bind_navigation(child)
            item = self.canvas.create_window(0, 0, window=button, anchor="nw")
            self.pool.append((item, button))
        for offset, (item, button) in enumerate(self.pool):
            if offset >= visible:
                self.canvas.itemconfigure(item, state="hidden")
                continue
            index = first + offset
            date, caption = self.rows[index]
            if getattr(button, "date_index", None) != index:
                button.date_index = index
                button.hovered = button.pressed = False
                button.set_text(date)
                button.detail.configure(text=caption)
                button.command = lambda destination=index: self.select(destination, focus=True)
            self.canvas.coords(item, 0, index * self.row_height)
            self.canvas.itemconfigure(item, width=width, height=self.row_height - 6, state="normal")
            button.selected = index == self.selected
            button.focused = button.selected and self.focus_get() is self.canvas
            button._paint()

    def select(self, index, *, notify=True, focus=False):
        if not self.rows:
            return
        index = max(0, min(len(self.rows) - 1, index))
        changed = self.selected != index
        self.selected = index
        if focus:
            self.canvas.focus_set()
        self.see(index)
        self._render_rows()
        if changed and notify:
            self.event_generate("<<DateSelected>>")

    def see(self, index):
        top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        start = index * self.row_height
        total = max(1, len(self.rows) * self.row_height)
        if start < top:
            self.canvas.yview_moveto((start // self.scroll_unit * self.scroll_unit) / total)
        elif start + self.row_height > top + height:
            target = start + self.row_height - height
            self.canvas.yview_moveto(((target + self.scroll_unit - 1) // self.scroll_unit * self.scroll_unit) / total)

    def yview(self, *args):
        return self.canvas.yview(*args)

    def _wheel(self, event):
        direction = wheel_direction(event)
        if direction and len(self.rows) * self.row_height > self.canvas.winfo_height():
            self.canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _key(self, event):
        current = self.selected if self.selected is not None else 0
        page = max(1, self.canvas.winfo_height() // self.row_height - 1)
        destination = {
            "Up": current - 1, "Down": current + 1,
            "Home": 0, "End": len(self.rows) - 1,
            "Prior": current - page, "Next": current + page,
        }.get(event.keysym, current)
        self.select(destination, focus=True)
        return "break"
