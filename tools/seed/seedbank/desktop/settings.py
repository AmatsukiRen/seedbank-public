from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path

from .. import localmodels, qq
from ..i18n import LOCALE_LABELS, get_locale, set_locale
from ..onboarding import save_config
from ..settings import PRESETS, desktop_executable, load_ui_settings, save_ui_settings, set_autostart, test_brain
from .pages import Page
from .text import t
from .widgets import Button, Card, Scroll, Select, Toggle, field, label, paragraph


class SettingsPage(Page):
    key = "settings"
    snapshot_fields = ("brain",)

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.heading(t("布置她的家"), t("把窗口调成你喜欢的样子，让陪伴更自在。"))
        self.variables = {}
        self.fields = {}
        self.section_key = self.state.get("section", "appearance")
        tabs = tk.Frame(self, bg=self.cget("bg"))
        tabs.pack(anchor="w", pady=(0, 12))
        for key, title in (("appearance", "外观"), ("conversation", "对话"), ("memory", "记忆"), ("qq", "QQ")):
            Button(tabs, self.theme, t(title), lambda destination=key: self.switch(destination),
                   selected=key == self.section_key, variant="tab").pack(side="left", padx=(0, 8))
        if self.section_key in ("conversation", "memory", "qq"):
            footer = tk.Frame(self, bg=self.cget("bg"))
            footer.pack(side="bottom", fill="x", pady=(12, 0))
            app.action(footer, t("保存设置"), self.save, primary=True).pack(side="right")
            paragraph(footer, self.theme, t("修改后记得保存，切换页面不会丢失草稿。"), size=12)
        self.body = Scroll(self, self.theme, max_width=920)
        self.body.pack(fill="both", expand=True)
        getattr(self, self.section_key)()

    def switch(self, key):
        if key == self.section_key:
            return
        self.state["section"] = key
        self.app.show_page("settings")

    def card(self, title, description="", tone="surface"):
        card = Card(self.body.frame, self.theme, tone=tone)
        card.pack(fill="x", pady=(0, 16))
        label(card.body, self.theme, title, size=18, weight="bold").pack(fill="x", pady=(0, 8))
        if description:
            paragraph(card.body, self.theme, description)
        return card.body

    def variable(self, key, default="", boolean=False):
        if key not in self.variables:
            value = self.app.settings_draft.get(key, default)
            self.variables[key] = tk.BooleanVar(self, value=bool(value)) if boolean else tk.StringVar(self, value="" if value is None else str(value))
        return self.variables[key]

    def input(self, parent, caption, key, default="", hint=""):
        widget = field(parent, self.theme, caption, self.variable(key, default), hint=hint)
        self.fields[key] = widget
        return widget

    def check(self, parent, caption, variable, command=None):
        widget = Toggle(parent, self.theme, caption, variable, command)
        widget.pack(fill="x")
        return widget

    def appearance(self):
        body = self.card(t("选一种家的颜色"), t("换一种心情，故事仍然接着写。"))
        choices = tk.Frame(body, bg=body.cget("bg"))
        choices.pack(fill="x", pady=(12, 0))
        choices.columnconfigure((0, 1, 2), weight=1, uniform="themes")
        for column, (key, name, detail) in enumerate((
            ("cream", "奶油紫", "暖白与莓紫，像一本柔软的手帐。"),
            ("mint", "薄荷海", "清透的绿与蓝，像海边安静的午后。"),
            ("night", "晚安蓝", "柔和的深蓝，在夜里也舒服。"),
        )):
            row = tk.Frame(choices, bg=choices.cget("bg"))
            row.grid(row=0, column=column, sticky="nsew", padx=(0, 12 if column < 2 else 0))
            Button(row, self.theme, t(name), lambda choice=key: self.app.change_appearance(desktop_theme=choice),
                   width=130, selected=self.theme.key == key, preview=key).pack(fill="x")
            paragraph(row, self.theme, t(detail), size=13)
        body = self.card(t("阅读与动作"))
        self.large = tk.BooleanVar(self, value=self.theme.scale > 1)
        self.motion = tk.BooleanVar(self, value=self.theme.reduced_motion)
        self.check(body, t("使用更大的文字"), self.large,
                   lambda: self.app.change_appearance(desktop_large_text=self.large.get()))
        self.check(body, t("减少动态效果"), self.motion,
                   lambda: self.app.change_appearance(desktop_reduced_motion=self.motion.get()))
        paragraph(body, self.theme, t("减少动态时，角色保持静态，所有功能照常使用。"))
        body = self.card(t("界面语言"), t("只翻译窗口，不翻译她自己的话。"))
        self.language = tk.StringVar(self, value=LOCALE_LABELS.get(get_locale(), "简体中文"))
        selector = Select(body, self.theme, values=list(LOCALE_LABELS.values()), textvariable=self.language,
                                state="readonly", font=self.theme.font(), height=4)
        selector.pack(fill="x", pady=4)
        selector.bind("<<ComboboxSelected>>", self.language_changed)
        body = self.card(t("桌面陪伴"))
        saved = load_ui_settings()
        self.always = tk.BooleanVar(self, value=saved.get("always_on_top", False))
        self.autostart = tk.BooleanVar(self, value=saved.get("autostart", False))
        self.check(body, t("窗口总在最前"), self.always, self.topmost_changed)
        autostart = self.check(body, t("登录电脑后打开她的房间"), self.autostart, self.autostart_changed)
        if sys.platform != "win32":
            autostart.configure(state="disabled")
            paragraph(body, self.theme, t("开机自启仅适用于 Windows。"))
        Button(body, self.theme, t("打开她的文件夹"), self.app.open_folder).pack(anchor="w", pady=(8, 0))

    def conversation(self):
        body = self.card(t("选择对话方式"), t("先选一个预设，再按需要调整。密钥填在系统环境变量中。"))
        self.preset = Select(body, self.theme, state="readonly", values=[t(row["label"]) for row in PRESETS],
                                   font=self.theme.font(14))
        self.preset.pack(fill="x", pady=(0, 12))
        self.preset.bind("<<ComboboxSelected>>", self.apply_preset)
        self.preset_hint = paragraph(body, self.theme, t("离线也可以先认识她，之后随时连接模型。"))
        label(body, self.theme, t("接口类型"), size=14, weight="bold").pack(fill="x", pady=(8, 6))
        Select(body, self.theme, state="readonly", textvariable=self.variable("adapter", "stub"),
               values=("stub", "openai-compatible", "anthropic", "codex"), font=self.theme.font()).pack(fill="x", pady=(0, 16))
        self.input(body, t("模型名称"), "model")
        self.input(body, t("接口地址"), "base_url")
        self.input(body, t("密钥环境变量名"), "api_key_env", "SEEDBANK_API_KEY",
                   t("这里填写变量名，不填写密钥。例如 SEEDBANK_API_KEY。"))
        self.input(body, t("温度（0–2）"), "temperature", "0.8")
        self.input(body, t("视觉模型（可留空）"), "vision_model")
        self.input(body, t("每轮活动最多调用（1–3）"), "codex_max_calls", "2")
        paragraph(body, self.theme, "GPT / Codex: " + t("使用本机 Codex 的 ChatGPT 登录与账号额度；无需填写密钥。当前支持文字，图片仅归档。"))
        paragraph(body, self.theme, t("照片和 WAV 原件会保存在生命包，并随完整备份保留。"))
        paragraph(body, self.theme, t("递交照片时可能向已配置的视觉模型发送图片并产生费用；日常文字聊天不会自动重发原图。"))
        actions = tk.Frame(body, bg=body.cget("bg"))
        actions.pack(fill="x", pady=(8, 0))
        self.app.action(actions, t("测试连接"), self.test_connection).pack(side="left", padx=(0, 8))
        self.app.action(actions, t("发现本地模型"), self.discover).pack(side="left")
        self.error_label = paragraph(body, self.theme, "", role="danger")
        results = self.state.get("models", [])
        if results:
            body = self.card(t("本机可用的模型"), t("选择后先填入草稿，保存后生效。"), "mint")
            for result in results:
                for model in result.get("models", [])[:8]:
                    Button(body, self.theme, str(result.get("label", "")) + " · " + model,
                           lambda source=result, name=model: self.select_local(source, name)).pack(fill="x", pady=4)

    def memory(self):
        body = self.card(t("记忆的节奏"), t("她会从经历中挑选值得留下的片段。"), "mint")
        self.check(body, t("过滤重复与空泛的记忆"), self.variable("strict", True, boolean=True))
        self.input(body, t("每轮最多提炼几条（1–50）"), "daily_max", "8")
        self.error_label = paragraph(body, self.theme, "", role="danger")
        self.card(t("时间慢慢往前走"), t("每过一个凌晨就进入新的一天；没有运行的日子不会伪造经历。"))
        self.card(t("放下，不抹去"), t("在记忆页可以让她停止主动回忆某一条，原始历史仍保留。"))

    def qq(self):
        config = self.state.setdefault("qq_draft", dict(qq.config_defaults()))
        body = self.card(t("从 QQ 来看她"), t("连接你已有的第三方 OneBot 桥；这里只负责接收和回复消息。"))
        self.qq_variables = {}
        for key, caption, default in (
            ("owner", "主人 QQ 号", ""), ("groups", "群白名单（逗号分隔）", ""),
            ("self_id", "她使用的 QQ 号", ""), ("onebot_http", "OneBot HTTP 地址", qq.DEFAULT_ONEBOT_HTTP),
            ("port", "本机上报端口", str(qq.DEFAULT_QQ_PORT)),
        ):
            value = config.get(key, default)
            if isinstance(value, list):
                value = ",".join(str(item) for item in value)
            variable = tk.StringVar(self, value=str(value or ""))
            self.qq_variables[key] = variable
            self.fields[key] = field(body, self.theme, t(caption), variable)
        self.state.setdefault("qq_saved", {key: variable.get() for key, variable in self.qq_variables.items()})
        paragraph(body, self.theme, t("访问令牌使用环境变量 SEEDBANK_ONEBOT_TOKEN，不写进配置。"))
        self.error_label = paragraph(body, self.theme, "", role="danger")
        row = tk.Frame(body, bg=body.cget("bg"))
        row.pack(fill="x", pady=(8, 0))
        self.app.action(row, t("停止连接") if self.app.session.server else t("启动连接"), self.toggle_qq).pack(side="left", padx=(0, 8))
        self.app.action(row, t("测试连接"), self.test_qq).pack(side="left")
        self.connection_label = paragraph(body, self.theme, t("正在连接") if self.app.session.server else t("尚未启动"))
        self.card(t("连接方法"), t("先在 SnowLuma、NapCat 或 LLOneBot 中开启 HTTP 服务，将消息上报地址设为 http://127.0.0.1:上报端口/。保存后点击启动连接。"), "mint")

    def apply_preset(self, event=None):
        selected = self.preset.current()
        if selected < 0:
            return
        preset = PRESETS[selected]
        for key in ("adapter", "model", "base_url", "api_key_env"):
            self.variable(key).set(preset.get(key) or "")
        self.preset_hint.configure(text=t(preset.get("hint", "")))

    def select_local(self, source, model):
        for key, value in {"adapter": "openai-compatible", "model": model,
                           "base_url": source["base_url"], "api_key_env": ""}.items():
            self.variable(key).set(value)
        self.app.notify(t("已填入本地模型，保存后生效。"))

    def capture(self):
        super().capture()
        for key, variable in self.variables.items():
            self.app.settings_draft[key] = variable.get()
        if hasattr(self, "qq_variables"):
            self.state["qq_draft"] = {key: variable.get() for key, variable in self.qq_variables.items()}

    def collect(self):
        self.capture()
        patch = dict(self.app.settings_draft)
        for key, lower, upper, conversion in (("temperature", 0, 2, float), ("daily_max", 1, 50, int)):
            if key not in patch or patch[key] is None:
                continue
            try:
                value = conversion(patch[key])
                if not lower <= value <= upper:
                    raise ValueError()
            except (ValueError, TypeError):
                self.problem(key, t("请输入 {lower} 到 {upper} 之间的数值。", lower=lower, upper=upper))
                return None
            patch[key] = value
        for key in ("base_url",):
            value = str(patch.get(key) or "").strip()
            if value and not value.startswith(("http://", "https://")):
                self.problem(key, t("接口地址需要以 http:// 或 https:// 开头。"))
                return None
        return patch

    def problem(self, key, message):
        self.error_label.configure(text=message)
        if key in self.fields:
            self.fields[key].focus_set()
        self.app.notify(message, "error")

    def save(self):
        if self.section_key == "qq":
            config = self.collect_qq()
            if config is None:
                return
            app = self.app

            def saved(result):
                app.page_state["settings"]["qq_saved"] = dict(result)
                if isinstance(app.page, SettingsPage):
                    app.page.capture()
                current = dict(app.page_state["settings"].get("qq_draft", {}))
                for key, value in result.items():
                    sent = config.get(key)
                    current_value = current.get(key)
                    if key == "groups":
                        unchanged = qq.parse_groups(current_value) == qq.parse_groups(sent)
                    else:
                        unchanged = str(current_value if current_value is not None else "") == str(sent if sent is not None else "")
                    if unchanged:
                        current[key] = value
                app.page_state["settings"]["qq_draft"] = current
                if app.page_key != "settings":
                    app.invalidate_page("settings")
                app.notify(t("QQ 设置已保存；重新启动连接后生效。"), "ok")

            app.submit(lambda: qq.save_config(config), saved)
            return
        patch = self.collect()
        if patch is None:
            return
        app = self.app

        def saved(result):
            if isinstance(app.page, SettingsPage):
                app.page.capture()
            draft = dict(app.settings_draft)
            for key, value in result.items():
                current = draft.get(key)
                sent = patch.get(key)
                if str(current if current is not None else "") == str(sent if sent is not None else ""):
                    draft[key] = value
            app.settings_saved = dict(result)
            app.settings_draft = draft
            if isinstance(app.page, SettingsPage):
                for key, variable in app.page.variables.items():
                    if key in draft:
                        variable.set("" if draft[key] is None else draft[key])
            else:
                app.invalidate_page("settings")
            app.notify(t("设置已保存。"), "ok")

        app.submit(lambda: app.session.save_brain(patch), saved)

    def test_connection(self):
        patch = self.collect()
        if patch is not None:
            app = self.app
            app.submit(lambda: test_brain(app.pack_dir, patch),
                       lambda result: app.notify(result[1], "ok" if result[0] else "error"), t("正在连接…"))

    def discover(self):
        app = self.app

        def done(results):
            app.page_state["settings"]["models"] = results
            app.notify(t("选择一个本地模型，然后保存。") if results else t("没有发现本地模型，请先启动本地模型服务。"))
            app.invalidate_page("settings")

        app.submit(localmodels.discover, done, t("正在寻找本机模型…"))

    def collect_qq(self):
        self.capture()
        config = dict(self.state["qq_draft"])
        if not str(config.get("owner", "")).isdigit():
            self.problem("owner", t("请输入有效的主人 QQ 号。"))
            return None
        try:
            config["port"] = int(config["port"])
            if not 1024 <= config["port"] <= 65535:
                raise ValueError()
        except (ValueError, TypeError):
            self.problem("port", t("端口需要在 1024 到 65535 之间。"))
            return None
        config["groups"] = qq.parse_groups(config.get("groups"))
        config["pack"] = str(self.app.pack_dir)
        return config

    def toggle_qq(self):
        app = self.app
        if app.session.server:
            app.submit(app.session.stop_qq, self.qq_changed)
        else:
            config = self.collect_qq()
            if config is not None:
                app.submit(lambda: app.session.start_qq(config), self.qq_changed)

    def qq_changed(self, result):
        self.app.notify(t("QQ 连接已启动。") if result.get("running") else t("QQ 连接已停止。"), "ok")
        self.app.invalidate_page("settings")

    def test_qq(self):
        base = self.qq_variables["onebot_http"].get()
        app = self.app
        app.submit(lambda: qq.test_connection(base, os.environ.get("SEEDBANK_ONEBOT_TOKEN", "")),
                   lambda result: app.notify(t("已连接：{name}", name=result.get("nickname") or result.get("user_id") or "OneBot")
                                             if result.get("ok") else str(result.get("error") or t("连接失败，请检查地址。")),
                                             "ok" if result.get("ok") else "error"), t("正在连接…"))

    def language_changed(self, event=None):
        code = next(key for key, value in LOCALE_LABELS.items() if value == self.language.get())
        try:
            save_config({"language": code})
            set_locale(code)
            self.app._build_shell()
        except OSError as error:
            self.app.notify(str(error), "error")

    def topmost_changed(self):
        try:
            self.app.root.attributes("-topmost", self.always.get())
            save_ui_settings({"always_on_top": self.always.get()})
        except (OSError, tk.TclError) as error:
            self.always.set(not self.always.get())
            self.app.notify(str(error), "error")

    def autostart_changed(self):
        executable = Path(sys.executable)
        if getattr(sys, "frozen", False):
            command = [desktop_executable()]
        else:
            pythonw = executable.with_name("pythonw.exe")
            command = [str(pythonw if pythonw.exists() else executable),
                       str(Path(__file__).resolve().parents[2] / "seed.py"), "window", str(self.app.pack_dir)]
        result = set_autostart(self.autostart.get(), command=command)
        if not result.get("ok"):
            self.autostart.set(not self.autostart.get())
        self.app.notify(result.get("message", ""), "ok" if result.get("ok") else "error")
