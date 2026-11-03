from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from .. import localmodels
from ..onboarding import clean_name, create_fish, default_pack_parent, remember_pack
from ..settings import PRESETS
from ..util import SeedError, read_json
from .pet import PetStage
from .text import t
from .theme import Theme, initialize_locale, style_native_widgets
from .widgets import Button, Card, Scroll, Select, field, label, paragraph


class SetupWizard(tk.Toplevel):
    def __init__(self, master, on_done, on_cancel=None):
        super().__init__(master)
        initialize_locale()
        self.theme = Theme.load(self)
        style_native_widgets(self, self.theme)
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.step = 0
        self.busy = False
        self.closed = False
        self.events = queue.Queue()
        self.timer = None
        self.controls = []
        self.name = tk.StringVar(self, value="小蓝")
        self.parent_dir = tk.StringVar(self, value=str(default_pack_parent()))
        self.preset_index = 0
        self.brain_fields = {key: tk.StringVar(self, value=str(value or "")) for key, value in {
            "adapter": "stub", "model": "", "base_url": "", "api_key_env": "SEEDBANK_API_KEY",
        }.items()}
        self.notice = tk.StringVar(self)
        self.title("Seedbank · " + t("初次见面"))
        self.configure(bg=self.theme.color("background"))
        self.geometry("820x720")
        self.minsize(760, 640)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda event: self.cancel())
        self.bind("<MouseWheel>", self.wheel)
        self.build()
        self.timer = self.after(80, self.poll)

    def button(self, parent, text, callback, **kwargs):
        widget = Button(parent, self.theme, text, callback, **kwargs)
        self.controls.append(widget)
        return widget

    def build(self):
        for child in self.winfo_children():
            child.destroy()
        self.controls = []
        shell = tk.Frame(self, bg=self.cget("bg"))
        shell.pack(fill="both", expand=True, padx=24, pady=24)
        label(shell, self.theme, "Seedbank", size=24, weight="bold").pack(anchor="w")
        label(shell, self.theme, t("一个小小的家，一段属于你们的故事。"), size=15, role="muted").pack(anchor="w", pady=(8, 20))
        steps = tk.Frame(shell, bg=shell.cget("bg"))
        steps.pack(fill="x", pady=(0, 20))
        steps.columnconfigure(tuple(range(3)), weight=1, uniform="steps")
        for index, caption in enumerate(("名字与住处", "对话方式", "准备见面")):
            label(steps, self.theme, f"0{index + 1}  {t(caption)}", size=14, weight="bold",
                  role="primary" if index == self.step else "muted").grid(row=0, column=index, sticky="w")
        footer = tk.Frame(shell, bg=shell.cget("bg"))
        footer.pack(side="bottom", fill="x", pady=(16, 0))
        self.button(footer, t("取消"), self.cancel, variant="ghost").pack(side="left")
        if self.step > 0:
            self.button(footer, t("上一步"), self.back).pack(side="left", padx=8)
        self.button(footer, t("开始孵化") if self.step == 2 else t("下一步"), self.next, primary=True).pack(side="right")
        self.notice_label = label(shell, self.theme, textvariable=self.notice, role="danger", size=13, wraplength=710)
        self.notice_label.pack(side="bottom", fill="x", pady=(12, 0))
        self.body = Scroll(shell, self.theme)
        self.body.pack(fill="both", expand=True)
        card = Card(self.body.frame, self.theme)
        card.pack(fill="x")
        body = card.body
        if self.step == 0:
            label(body, self.theme, t("先认识一下吧"), size=24, weight="bold").pack(fill="x", pady=(0, 16))
            field(body, self.theme, t("她的名字"), self.name, hint=t("最多 24 个字，你可以给她一个独一无二的名字。"))
            field(body, self.theme, t("她住在哪里"), self.parent_dir, hint=t("她的一生保存在这个文件夹里。"))
            self.button(body, t("选择文件夹"), self.choose_parent).pack(anchor="w", pady=8)
            paragraph(body, self.theme, t("已经有自己的那一条了？"))
            self.button(body, t("打开现有生命包"), self.open_existing).pack(anchor="w")
        elif self.step == 1:
            label(body, self.theme, t("让她怎么和你说话"), size=24, weight="bold").pack(fill="x", pady=(0, 16))
            paragraph(body, self.theme, t("可以先离线认识她，之后再到设置里换模型。"))
            selector = Select(body, self.theme, state="readonly", values=[t(row["label"]) for row in PRESETS], font=self.theme.font(14))
            selector.current(self.preset_index)
            selector.pack(fill="x", pady=(8, 16))

            def change(event):
                self.preset_index = selector.current()
                self.apply_preset(PRESETS[self.preset_index])

            selector.bind("<<ComboboxSelected>>", change)
            for key, caption in (("model", "模型名称"), ("base_url", "接口地址"), ("api_key_env", "密钥环境变量名")):
                field(body, self.theme, t(caption), self.brain_fields[key])
            paragraph(body, self.theme, t("这里填写变量名，不填写密钥。例如 SEEDBANK_API_KEY。"))
            self.button(body, t("发现本地模型"), self.discover).pack(anchor="w", pady=8)
        else:
            label(body, self.theme, t("她的小房间准备好了"), size=24, weight="bold").pack(fill="x")
            stage = PetStage(body, self.theme)
            stage.configure(height=200)
            stage.pack(fill="x", pady=12)
            paragraph(body, self.theme, t("名字：{name}", name=clean_name(self.name.get())), role="text", size=16)
            paragraph(body, self.theme, str(self.target()), size=13)
            paragraph(body, self.theme, t("点击开始孵化后，才会创建她的生命包。"))
        for button in self.controls:
            button.set_enabled(not self.busy)

    def target(self):
        return Path(self.parent_dir.get()).expanduser() / f"{clean_name(self.name.get())}.life"

    def choose_parent(self):
        path = filedialog.askdirectory(parent=self, title=t("选择文件夹"))
        if path:
            self.parent_dir.set(path)

    def open_existing(self):
        path = filedialog.askdirectory(parent=self, title=t("打开现有生命包"))
        if not path:
            return
        birth = read_json(Path(path) / "birth.json", {})
        if not isinstance(birth, dict) or not birth.get("name"):
            self.notice.set(t("这个文件夹里没有可读取的出生记录。"))
            return
        try:
            remember_pack(path)
            self.done(path)
        except OSError as error:
            self.notice.set(str(error))

    def back(self):
        if not self.busy:
            self.step = max(0, self.step - 1)
            self.notice.set("")
            self.build()

    def next(self):
        if self.busy:
            return
        try:
            name = clean_name(self.name.get())
            if not self.parent_dir.get().strip():
                raise ValueError(t("请选择她的住处。"))
            target = self.target()
            if target.exists():
                raise ValueError(t("这里已有同名生命包，请换个名字或打开现有生命包。"))
            if self.step == 1:
                address = self.brain_fields["base_url"].get().strip()
                if address and not address.startswith(("http://", "https://")):
                    raise ValueError(t("接口地址需要以 http:// 或 https:// 开头。"))
        except (ValueError, OSError, RuntimeError, SeedError) as error:
            self.notice.set(str(error))
            return
        self.notice.set("")
        if self.step < 2:
            self.step += 1
            self.build()
        else:
            parent = self.parent_dir.get()
            brain = {key: variable.get().strip() for key, variable in self.brain_fields.items()}
            self.background(lambda: create_fish(name, parent, brain), self.done, t("正在准备她的第一天…"))

    def apply_preset(self, preset):
        for key, variable in self.brain_fields.items():
            variable.set(preset.get(key) or "")

    def discover(self):
        def found(results):
            choice = localmodels.first_choice(results)
            if choice:
                self.apply_preset(choice)
                self.notice.set(t("已填入本机模型：{model}", model=choice["model"]))
            else:
                self.notice.set(t("没有发现本地模型，请先启动本地模型服务。"))

        self.background(localmodels.discover, found, t("正在寻找本机模型…"))

    def background(self, work, callback, notice):
        self.busy = True
        self.notice.set(notice)
        for button in self.controls:
            button.set_enabled(False)

        def run():
            try:
                self.events.put((True, work(), callback))
            except Exception as error:
                self.events.put((False, error, None))

        threading.Thread(target=run, name="seedbank-onboarding", daemon=True).start()

    def poll(self):
        self.timer = None
        if self.closed:
            return
        try:
            success, result, callback = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for button in self.controls:
                button.set_enabled(True)
            if success:
                callback(result)
            else:
                self.notice.set(str(result))
        if not self.closed:
            self.timer = self.after(80, self.poll)

    def done(self, path):
        self.on_done(Path(path))
        self.closed = True
        if self.timer:
            self.after_cancel(self.timer)
        self.destroy()

    def cancel(self):
        if self.busy:
            self.notice.set(t("正在完成当前步骤，请稍候。"))
            return
        if self.on_cancel:
            self.on_cancel()
        self.closed = True
        if self.timer:
            self.after_cancel(self.timer)
        self.destroy()

    def wheel(self, event):
        self.body.scroll(-3 if event.delta > 0 else 3)
