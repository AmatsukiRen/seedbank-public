from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox

from .. import __version__
from ..qq import parse_groups
from ..settings import load_settings, load_ui_settings, open_pack_folder
from . import text as copy
from .dpi import enable_high_dpi
from .session import Session
from .theme import Theme, initialize_locale, preferences, save_preferences, style_native_widgets
from .widgets import Button, Card, Scroll, label


WINDOW_TITLE = "她住在这里"


class CompanionWindow:
    def __init__(self, root, pack_dir, brain_override=""):
        initialize_locale()
        self.root = root
        self.session = Session(pack_dir, brain_override)
        self.pack_dir = self.session.pack
        self.name = self.session.name
        self.theme = Theme.load(root)
        self.snapshot = self.session.snapshot()
        self.settings_draft = load_settings(self.pack_dir)
        self.settings_saved = dict(self.settings_draft)
        self.page_key = "room"
        self.page = None
        self.page_state = {}
        self._page_cache = {}
        self.controls = []
        self._queue = queue.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="seedbank-room")
        self._busy = False
        self._closed = False
        self._closing = False
        self._after_id = None
        self._clock_after_id = None
        self._refresh_after_id = None
        self._resize_after_id = None
        self._compact = True
        self._greeted = False
        self.status = tk.StringVar(root, value=copy.t("今天也一起慢慢来。"))
        self.root.title(f"Seedbank · {self.name} · {copy.t(WINDOW_TITLE)}")
        self.root.minsize(860, 640)
        saved = preferences()
        width = max(860, min(1180, self.root.winfo_screenwidth() - 80))
        height = max(640, min(820, self.root.winfo_screenheight() - 90))
        geometry = str(saved.get("desktop_geometry") or f"{width}x{height}")
        try:
            self.root.geometry(geometry)
        except tk.TclError:
            self.root.geometry("1120x800")
        self.root.attributes("-topmost", bool(load_ui_settings().get("always_on_top")))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._resize, add="+")
        self.root.bind("<MouseWheel>", self._wheel, add="+")
        self.root.bind("<Button-4>", self._wheel, add="+")
        self.root.bind("<Button-5>", self._wheel, add="+")
        self.root.bind("<Destroy>", self._destroyed, add="+")
        for number, key in enumerate(("room", "diary", "memory", "life", "settings"), 1):
            self.root.bind(f"<Control-Key-{number}>", lambda event, destination=key: self.navigate(destination))
        self.root.bind("<Control-f>", self._search)
        self._build_shell()
        self._after_id = self.root.after(80, self._poll)
        self._clock_after_id = self.root.after(1200, self._clock_loop)
        self._refresh_after_id = self.root.after(2000, self._watch_revision)

    def _build_shell(self):
        if self.page:
            self.page.suspend()
        self._page_cache.clear()
        for child in self.root.winfo_children():
            child.destroy()
        self.page = None
        theme = self.theme
        style_native_widgets(self.root, theme)
        self.root.title(f"Seedbank · {self.name} · {copy.t(WINDOW_TITLE)}")
        self.root.configure(bg=theme.color("background"))
        self.shell = tk.Frame(self.root, bg=theme.color("background"))
        self.shell.pack(fill="both", expand=True, padx=24, pady=(18, 12))
        masthead = tk.Frame(self.shell, bg=self.shell.cget("bg"))
        masthead.pack(fill="x", pady=(0, 12))
        brand = tk.Frame(masthead, bg=masthead.cget("bg"))
        brand.pack(side="left")
        label(brand, theme, "Seedbank", size=18, weight="bold").pack(side="left")
        label(brand, theme, copy.t("小小栖息地"), size=13, role="muted").pack(side="left", padx=12)
        self.meta_label = label(masthead, theme, copy.t("第 {number} 天", number=self.snapshot["day"]),
                                size=14, weight="bold", role="primary")
        self.meta_label.pack(side="right", padx=4)
        footer = tk.Frame(self.shell, bg=self.shell.cget("bg"))
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.status_label = label(footer, theme, size=12, role="muted", textvariable=self.status, wraplength=680)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.status_label.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(200, event.width)))
        label(footer, theme, f"v{__version__}", size=12, role="muted").pack(side="right", padx=(12, 0))
        self.host = tk.Frame(self.shell, bg=self.shell.cget("bg"))
        nav_panel = Card(self.shell, theme, padding=6, radius=28, tone="navigation", material="navigation")
        self.navigation = nav_panel
        nav_panel.pack(side="bottom", anchor="center", pady=(12, 0))
        nav = nav_panel.body
        nav.columnconfigure(tuple(range(5)), weight=1, uniform="navigation")
        self.nav_buttons = {}
        for column, (key, caption, symbol) in enumerate((
            ("room", "陪伴", "home"), ("diary", "日记", "book"), ("memory", "记忆", "heart"),
            ("life", "生活", "leaf"), ("settings", "设置", "settings"),
        )):
            button = Button(nav, theme, copy.t(caption), lambda destination=key: self.navigate(destination),
                            icon_name=symbol, selected=key == self.page_key, variant="navigation", width=round(120 * theme.scale))
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 4 if column < 4 else 0))
            self.nav_buttons[key] = button
        self.host.pack(fill="both", expand=True)
        self.show_page(self.page_key)

    def navigate(self, key):
        return self.show_page(key, refresh=False)

    def invalidate_page(self, key):
        if key == self.page_key:
            self.show_page(key)
        else:
            cached = self._page_cache.pop(key, None)
            if cached:
                cached[1].destroy()

    def show_page(self, key, *, refresh=True):
        from .pages import DiaryPage, LifePage, MemoryPage, RoomPage
        from .settings import SettingsPage

        if self._closed or self._closing:
            return
        signature = self._compact, self.page_state.get(key, {}).get("section")
        cached = self._page_cache.get(key)
        reusable = not refresh and cached is not None and cached[0] == signature and not cached[1].stale
        if reusable and cached[1] is self.page:
            return "break"
        if self.page:
            self.page.suspend()
            focused = self.root.focus_get()
            if focused is self.page or (focused is not None and str(focused).startswith(str(self.page) + ".")):
                self.nav_buttons[key].native.focus_set()
        self.page_key = key
        if reusable:
            _, self.page, self.controls = cached
        else:
            if cached:
                self._page_cache.pop(key)
                cached[1].destroy()
            self.controls = []
            classes = {"room": RoomPage, "diary": DiaryPage, "memory": MemoryPage,
                       "life": LifePage, "settings": SettingsPage}
            self.page = classes[key](self.host, self)
            self._page_cache[key] = signature, self.page, self.controls
        if not self.page.winfo_manager():
            self.page.place(x=0, y=0, relwidth=1, relheight=1)
        self.page.lift()
        self.page.resume()
        for destination, button in self.nav_buttons.items():
            button.set_selected(destination == key)
        self._set_busy(self._busy)
        return "break"

    def action(self, parent, caption, command, **kwargs):
        button = Button(parent, self.theme, caption, command, **kwargs)
        button.set_enabled(not self._busy and not self._closing)
        self.controls[:] = [control for control in self.controls if control.winfo_exists()]
        self.controls.append(button)
        return button

    def _set_busy(self, busy):
        self._busy = busy
        for control in self.controls:
            if control.winfo_exists():
                control.set_enabled(not busy and not self._closing)
        if hasattr(self.page, "reply_status"):
            self.page.reply_status.configure(text=copy.t("她正在想怎么回答你…") if busy else "")

    def notify(self, text, kind=""):
        self.status.set(str(text))
        role = "danger" if kind == "error" else "success" if kind == "ok" else "muted"
        self.status_label.configure(fg=self.theme.color(role))

    def _run(self, work, on_ok):
        if self._closed or self._closing:
            return False
        self._set_busy(True)

        def execute():
            try:
                self._queue.put(("ok", work(), on_ok))
            except Exception as error:
                self._queue.put(("error", error, None))

        self._executor.submit(execute)
        return True

    def submit(self, work, on_ok, note=None):
        if self._busy or self._closing:
            self.notify(copy.t("她正在忙，请稍等一会儿。"))
            return False
        self.notify(note or copy.t("正在整理，请稍候…"))
        return self._run(work, on_ok)

    def operate(self, operation, *, on_done=None, busy_text=None, **fields):
        def work():
            with self.session.lock:
                result = self.session.call(operation, **fields)
                return result, self.session.snapshot()

        def complete(payload):
            result, snapshot = payload
            if on_done:
                on_done(result)
            self.apply_snapshot(snapshot)
            if operation == "work" and result.get("work", {}).get("succeeded") is False:
                self.notify(copy.t("本次未生成作品，尝试已记录。再次发起会作为新的尝试。"))
                return
            if self.page_key == "room":
                self.pet.play({"message": "happy", "image": "curious", "day": "dance", "work": "happy"}.get(operation, "idle"))
            self.notify(copy.t("已经记下来了。"), "ok")

        return self.submit(work, complete, busy_text)

    def _poll(self):
        if self._closed:
            return
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        while True:
            try:
                kind, payload, callback = self._queue.get_nowait()
            except queue.Empty:
                break
            self._set_busy(False)
            try:
                if kind == "ok" and callback:
                    callback(payload)
                elif kind == "error":
                    self._closing = False
                    self._set_busy(False)
                    self.notify(copy.t("没有完成：{error}。可以调整后重试。", error=payload), "error")
                    if self.page_key == "room" and hasattr(self, "pet") and self.pet.winfo_exists():
                        self.pet.play("sad")
            except Exception as error:
                self.notify(copy.t("显示未完成：{error}，请重新打开这一页。", error=error), "error")
            if self._closed:
                return
        if self._closing and not self._busy:
            self._finish_close()
        self._after_id = self.root.after(80, self._poll)

    def apply_snapshot(self, snapshot):
        previous = self.snapshot
        self.snapshot = snapshot
        self.meta_label.configure(text=copy.t("第 {number} 天", number=snapshot["day"]))
        for signature, page, controls in self._page_cache.values():
            page.stale = page.stale or page.snapshot_changed(previous, snapshot)
        if self.page is not None and self.page.stale:
            self.show_page(self.page_key)

    def _clock_loop(self):
        if self._closed or self._closing:
            return
        if self._clock_after_id:
            self.root.after_cancel(self._clock_after_id)
        if not self._busy:
            self._set_busy(True)
            self._run(self.session.pulse, self._on_clock)
        self._clock_after_id = self.root.after(60000, self._clock_loop)

    def _on_clock(self, result):
        self._set_busy(False)
        if result.get("snapshot"):
            self.apply_snapshot(result["snapshot"])
        if (result.get("spoken") or {}).get("reply"):
            self.notify(copy.t("她有一句话想对你说。"))
        elif result.get("advanced"):
            self.notify(copy.t("新的一天开始了。"))

    def _watch_revision(self):
        if self._closed or self._closing:
            return
        if not self._busy and self.session.revision != self.snapshot.get("revision"):
            self._run(self.session.snapshot, self.apply_snapshot)
        self._refresh_after_id = self.root.after(2000, self._watch_revision)

    def _set_memory_note(self, text, kind=""):
        self.notify(text, kind)

    def _forget_memory(self, memory_id):
        if self._busy:
            self._set_memory_note(copy.t("她正在忙，请稍等一会儿。"))
            return
        if messagebox.askyesno(copy.t("放下一段记忆"), copy.t("她将不再主动想起这一条；原始记录仍会保留。确定继续吗？"), parent=self.root):
            self.operate("memories", action="forget", memory_id=memory_id)

    def send_photo(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title=copy.t("给她看一张照片"),
                                          filetypes=[(copy.t("图片"), "*.png *.jpg *.jpeg *.webp *.bmp"), (copy.t("所有文件"), "*.*")])
        if path:
            self.operate("image", path=path, note=copy.t("给你看样东西"), busy_text=copy.t("她正在看你分享的照片…"))

    def advance_day(self):
        if messagebox.askyesno(copy.t("陪她过一天"), copy.t("这会结束当前一天、写下日记并推进生命天数。平时也会随真实日期自然推进。继续吗？"), parent=self.root):
            self.operate("day", days=1)

    def change_appearance(self, **patch):
        try:
            save_preferences(patch)
        except OSError as error:
            self.notify(str(error), "error")
            return
        self.theme = Theme.load(self.root)
        self._build_shell()

    def open_folder(self):
        try:
            open_pack_folder(self.pack_dir)
        except OSError as error:
            self.notify(str(error), "error")

    def _search(self, event=None):
        self.navigate("memory")
        self.page.search_entry.focus_set()
        return "break"

    def _resize(self, event):
        if event.widget is not self.root or self._closed:
            return
        compact = event.width < 1060 or event.height < 730
        if compact != self._compact:
            self._compact = compact
            if self._resize_after_id:
                self.root.after_cancel(self._resize_after_id)
            self._resize_after_id = self.root.after(150, self._resize_page)

    def _resize_page(self):
        self._resize_after_id = None
        if not self._closed:
            self.navigate(self.page_key)

    def _wheel(self, event):
        widget = event.widget
        if isinstance(widget, (tk.Text, tk.Listbox)):
            return
        while widget is not None:
            if isinstance(widget, Scroll):
                delta = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
                widget.scroll(delta * 3)
                return "break"
            widget = getattr(widget, "master", None)

    def _on_close(self):
        if self._closed or self._closing:
            return
        if self.page:
            self.page.capture()
        changed = any(str(value if value is not None else "") != str(self.settings_saved.get(key) if self.settings_saved.get(key) is not None else "")
                      for key, value in self.settings_draft.items())
        settings_state = self.page_state.get("settings", {})
        qq_draft = settings_state.get("qq_draft", {})
        qq_saved = settings_state.get("qq_saved", {})
        for key in ("owner", "self_id", "onebot_http", "port", "groups"):
            current, saved = qq_draft.get(key, ""), qq_saved.get(key, "")
            changed = changed or (parse_groups(current) != parse_groups(saved) if key == "groups" else str(current) != str(saved))
        if changed:
            if not messagebox.askyesno(copy.t("尚未保存"), copy.t("设置尚未保存。放弃这些修改并关闭吗？"), parent=self.root):
                return
        self._closing = True
        self._set_busy(self._busy)
        self.notify(copy.t("正在保存窗口并等当前操作结束…"))
        if not self._busy:
            self._finish_close()

    def _finish_close(self):
        self._closing = False

        def closed(result):
            try:
                save_preferences({"desktop_geometry": self.root.geometry()})
            except OSError:
                pass
            self._closed = True
            self._cancel_timers()
            self._executor.shutdown(wait=False)
            self.root.destroy()

        self._run(self.session.close, closed)
        self._closing = True

    def _cancel_timers(self):
        for name in ("_after_id", "_clock_after_id", "_refresh_after_id", "_resize_after_id"):
            timer = getattr(self, name, None)
            if timer:
                try:
                    self.root.after_cancel(timer)
                except tk.TclError:
                    pass
                setattr(self, name, None)

    def _destroyed(self, event):
        if event.widget is self.root and not self._closed:
            self._closed = True
            self._cancel_timers()
            self._executor.submit(self.session.close)
            self._executor.shutdown(wait=False)


def window(pack_dir: str, brain_override: str = "") -> int:
    enable_high_dpi()
    root = tk.Tk()
    try:
        CompanionWindow(root, Path(pack_dir), brain_override)
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    return 0
