"""设置页：语言、外观、模型、连接、记忆、感官、关系……所有卡片。"""
import tkinter as tk
from pathlib import Path

from .. import tokens as T


class _SettingsPage(tk.Frame):
    """设置页：以前那个独立小窗的内容，现在安静地待在主区里。

    控件全部沿用窗口里的自绘零件；只有「测试连接」会联网，而且要点它才发请求。
    """

    def __init__(self, master, pack_dir, on_saved=None, on_theme=None):
        super().__init__(master, bg=PANEL)
        _resolve_fonts()
        self.pack_dir = Path(expand_home(str(pack_dir)))
        self.on_saved = on_saved
        self.on_theme = on_theme
        self._entries: dict = {}
        self._adapter = "stub"
        self._adapter_pills: dict = {}
        self._preset_pills: list = []
        self._preset_index = None
        self._presets = _presets()
        self._testing = False
        self._queue: queue.Queue = queue.Queue()
        self._after_id = None
        # QQ 卡的后台测试状态：卡可能因为后端缺失而没建，先给安全的默认值。
        self._qq_testing = False
        self._qq_queue: queue.Queue = queue.Queue()
        self._qq_after_id = None
        self._qq_proc = None
        self._qq_port = QQ_DEFAULT_PORT
        self._settings = self._read_settings()
        self._build()
        self.refresh()

    # —— 读设置 ——

    def _read_settings(self) -> dict:
        data = dict(_FALLBACK_SETTINGS)
        loader = _settings_loader()
        if loader is not None:
            try:
                loaded = loader(self.pack_dir)
                if isinstance(loaded, dict):
                    for key in data:
                        if key in loaded:
                            data[key] = loaded[key]
                    for key in ("model", "base_url"):
                        if key in loaded:
                            data[key] = loaded[key]
            except Exception:  # noqa: BLE001 - 读不出来就用默认值，别让设置页打不开
                pass
        return data

    def _read_ui_settings(self) -> dict:
        """桌面偏好（置顶、自启、配色）；ui.json 坏了也各用各的默认值。"""
        data = {"always_on_top": False, "autostart": False, "theme": CURRENT_THEME}
        loader = _ui_loader()
        if loader is not None:
            try:
                loaded = loader()
            except Exception:  # noqa: BLE001 - 偏好坏了不该拦着设置页
                loaded = None
            if isinstance(loaded, dict):
                for key in ("always_on_top", "autostart"):
                    if key in loaded:
                        data[key] = bool(loaded[key])
        theme = str(_ui_file_data().get("theme") or "")
        if theme in THEMES:
            data["theme"] = theme
        return data

    # —— 搭界面 ——

    def _build(self) -> None:
        self._build_footer()
        self.body = _ScrollFrame(self, bg=PANEL, max_content_width=T.CONTENT_MAX, backdrop=True)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        content = self.body.frame
        self._build_language_card(content)
        self._build_theme_card(content)
        self._build_model_card(content)
        self._build_connection_card(content)
        self._build_memory_card(content)
        self._build_senses_card(content)
        self._build_clock_card(content)
        self._build_bond_card(content)
        self._build_memorial_card(content)
        self._build_inner_card(content)
        self._build_hands_card(content)
        self._build_friends_card(content)
        self._build_works_card(content)
        self._build_qq_card(content)
        self._build_window_card(content)
        tk.Frame(content, bg=PANEL, height=16).pack(fill="x")

    def _build_footer(self) -> None:
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill="x", side="bottom")
        self._foot = foot
        tk.Frame(foot, bg=SIDEBAR_LINE, height=1).pack(fill="x")
        inner = tk.Frame(foot, bg=PANEL)
        inner.pack(fill="x", padx=22, pady=(8, 16))
        self._foot_inner = inner
        self.note = tk.Label(inner, text="", bg=SURFACE, fg=MUTED, font=_font(10),
                             anchor="w", justify="left")
        self.note.pack(fill="x", pady=(0, 6))
        _bind_wrap(self.note, 40)
        row = tk.Frame(inner, bg=SURFACE)
        row.pack(fill="x")
        self._foot_row = row
        # 按钮高度从字体度量来：DPI/字号变了也不会压扁。
        btn_h = int(T.button_height(T.font(T.FONT_BODY), minimum=40, pad=16))
        small_h = int(T.button_height(T.font(T.FONT_SMALL), minimum=36, pad=14))
        self.save_btn = _Pill(row, t("保存"), self._save, bg=SURFACE, fill=ACCENT, hover=ACCENT_HI,
                              fg=ON_ACCENT, outline="", font=_font(10, "bold"), pad_x=20, height=btn_h)
        self.save_btn.pack(side="right")
        self.test_btn = _Pill(row, t("测试连接"), self._test, bg=SURFACE, fill=CARD, hover=CARD_HI,
                              fg=TEXT_SOFT, font=_font(10), pad_x=16, height=small_h)
        self.test_btn.pack(side="right", padx=(0, 8))
        self.folder_btn = _Pill(row, t("📁  她的文件夹"), self._open_folder, bg=SURFACE, fill=SURFACE,
                                hover=CARD, fg=MUTED, outline="", font=_font(10), pad_x=10,
                                height=small_h)
        self.folder_btn.pack(side="left")
        try:
            self.bind("<Configure>", self._on_settings_resize, add="+")
        except Exception:
            pass

    def _on_settings_resize(self, _event=None) -> None:
        """矮页先把提示行收起来，底部按钮行必须完整留在窗口里。"""
        try:
            height = int(self.winfo_height())
        except Exception:
            return
        if height <= 1:
            return
        try:
            if height < 600:
                self.note.pack_forget()
            elif not self.note.winfo_manager():
                self.note.pack(fill="x", pady=(0, 6), before=self._foot_row)
        except Exception:
            pass
        try:
            self._layout_theme_swatches()
        except Exception:
            pass

    # —— 语言卡片：只改界面，不动她的手账 ——

    def _language_code(self) -> str:
        try:
            return normalize_locale(get_locale())
        except Exception:  # pragma: no cover - i18n 异常时按中文算
            return "zh_CN"

    def _build_language_card(self, parent) -> None:
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(6, 14))
        box = card.inner
        _section(box, t("语言 / Language"), t("只改界面文案；她的日记和记忆不会翻译。"), bg=CARD)
        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(2, 10))
        self._lang_pills: dict = {}
        for code in available_locales():
            label = LOCALE_LABELS.get(code, code)
            pill = _Pill(row, label, lambda code=code: self._on_language(code), bg=CARD,
                         fill=CARD, hover=CARD_HI, fg=TEXT_SOFT, outline=BORDER,
                         font=_font(10), pad_x=14, height=30, radius=15, anchor="center")
            pill.pack(side="left", padx=(0, 8))
            self._lang_pills[code] = pill
        self._language_note = tk.Label(box, text="", bg=CARD, fg=FAINT, font=_font(10),
                                       anchor="w", justify="left")
        self._language_note.pack(fill="x")
        _bind_wrap(self._language_note, 26)
        self._sync_language_pills()
        if self._language_code() == "zh_CN":
            self._language_note.configure(text=t("切换后重启窗口，所有页面都会用新语言。"))
        else:
            self._language_note.configure(
                text=t("界面语言是「{lang}」；切换后重启窗口，所有页面都会用新语言。",
                       lang=LOCALE_LABELS.get(self._language_code(), self._language_code())))

    def _sync_language_pills(self) -> None:
        current = self._language_code()
        for code, pill in getattr(self, "_lang_pills", {}).items():
            try:
                if code == current:
                    pill.set_colors(fill=ACCENT_SOFT, hover=ACCENT_SOFT,
                                    fg=ACCENT_TXT, outline=ACCENT_LINE)
                else:
                    pill.set_colors(fill=CARD, hover=CARD_HI,
                                    fg=TEXT_SOFT, outline=BORDER)
            except Exception:  # pragma: no cover - 样式失败不影响切换
                pass

    def _on_language(self, code) -> None:
        try:
            code = normalize_locale(code)
        except Exception:  # pragma: no cover - 陌生语言码按中文
            code = "zh_CN"
        try:
            set_locale(code)
        except Exception:  # pragma: no cover - i18n 坏了也不该拦着
            pass
        saved = False
        error_text = ""
        saver = setup_save_config
        if saver is not None:
            try:
                saver({"language": code})
                saved = True
            except Exception as error:  # noqa: BLE001 - 存不下来也要先把界面切过去
                error_text = str(error)
        self._sync_language_pills()
        label = LOCALE_LABELS.get(code, code)
        if saved:
            self._language_note.configure(
                text=t("界面语言已切到「{lang}」，已保存；重启窗口后所有页面都会用新语言。",
                       lang=label),
                fg=OK)
        else:
            self._language_note.configure(
                text=t("界面语言已切到「{lang}」，但没存下来：{error}",
                       lang=label, error=error_text),
                fg=ERROR)

    def _build_theme_card(self, parent) -> None:
        """外观：五套配色，点一下就换；只改这台电脑的壳，不碰她的记忆。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(6, 16))
        box = card.inner
        _section(box, t("外观"), t("只改这台电脑的外观，不改她的记忆。"), bg=CARD)
        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(2, 8))
        self._theme_row = row
        self._theme_swatches: dict = {}
        self._theme_cols: list = []
        self._theme_grid_cols = 0
        for key in THEME_ORDER:
            col = tk.Frame(row, bg=CARD)
            swatch = _ThemeSwatch(col, key, self._on_theme, bg=CARD)
            swatch.pack()
            tk.Label(col, text=t(str(T.THEME_LABELS.get(key, key))), bg=CARD,
                     fg=TEXT_SOFT, font=_font(10), anchor="center").pack(fill="x", pady=(4, 0))
            self._theme_swatches[key] = swatch
            self._theme_cols.append(col)
        row.bind("<Configure>", self._on_theme_row_configure, add="+")
        self.after(60, lambda: self._layout_theme_swatches())
        self.after(220, lambda: self._layout_theme_swatches())
        self._theme_note = tk.Label(
            box, text=t("选一个配色：整扇窗会立刻按它重新铺一遍。"), bg=CARD,
            fg=FAINT, font=_font(10), anchor="w", justify="left")
        self._theme_note.pack(fill="x")
        _bind_wrap(self._theme_note, 26)
        self._sync_theme_pills()

    def _on_theme_row_configure(self, _event=None) -> None:
        """色块行按可用宽度换行：最小窗 3+2 两行，宽窗一行五个。"""
        try:
            self._layout_theme_swatches()
        except Exception:
            pass

    def _layout_theme_swatches(self) -> None:
        row = getattr(self, "_theme_row", None)
        cols = getattr(self, "_theme_cols", None)
        if row is None or not cols:
            return
        try:
            width = int(self.winfo_width()) - 80
        except Exception:
            width = 0
        if width <= 1:
            try:
                width = int(row.winfo_width())
            except Exception:
                width = 0
        need_one_row = 5 * (96 + 8)
        target = 5 if width >= need_one_row else 3
        last_width = getattr(self, "_theme_last_width", -1)
        if target == getattr(self, "_theme_grid_cols", 0) and abs(width - last_width) < 8:
            return
        self._theme_last_width = width
        self._theme_grid_cols = target
        for index, col in enumerate(cols):
            col.grid_forget()
            col.grid(row=index // target, column=index % target,
                     padx=(0, 8), pady=(0, 8), sticky="nw")

    def _sync_theme_pills(self) -> None:
        current = str(self._read_ui_settings().get("theme") or CURRENT_THEME)
        for key, swatch in getattr(self, "_theme_swatches", {}).items():
            try:
                swatch.set_selected(key == current)
            except Exception:  # pragma: no cover - 样式失败不影响切主题
                pass

    def _on_theme(self, key) -> None:
        """换配色：交给窗口重搭（立刻生效）；没有回调时只改内存并提示重启。"""
        callback = self.on_theme
        if callable(callback):
            callback(str(key))
            return
        try:
            _apply_theme(str(key))
        except Exception:
            pass
        self._sync_theme_pills()
        try:
            self._theme_note.configure(text=t("配色已切换；重启窗口后其它页面也会用上。"))
        except Exception:
            pass

    def _build_model_card(self, parent) -> None:
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(6, 14))
        box = card.inner
        _section(box, t("选一个脑"), t("点一个预设，地址和模型会自动填好；也可以自己改。"), bg=CARD)

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(2, 8))
        for label, value in ((t("离线 stub"), "stub"), (t("OpenAI 兼容"), "openai-compatible"),
                             ("Anthropic", "anthropic"), ("Codex", "codex")):
            pill = _Pill(row, label, lambda chosen=value: self._choose_adapter(chosen), bg=CARD,
                         fill=SURFACE, outline=BORDER, hover=CARD_HI, fg=TEXT_SOFT,
                         font=_font(10), pad_x=14, height=30)
            pill.pack(side="left", padx=(0, 6))
            self._adapter_pills[value] = pill

        preset_row = tk.Frame(box, bg=CARD)
        preset_row.pack(fill="x")
        specs = []
        for index, preset in enumerate(self._presets):
            label = t(str(preset.get("label") or preset.get("model") or "预设"))
            specs.append((label, lambda chosen=preset, position=index: self._apply_preset(chosen, position)))
        self._preset_pills = _flow_chips(preset_row, CARD, specs, limit=380,
                                         on_layout=self._on_preset_layout)

        self._preset_hint = tk.Label(box, text="", bg=CARD, fg=FAINT, font=_font(10),
                                     anchor="w", justify="left")
        self._preset_hint.pack(fill="x", pady=(2, 0))
        _bind_wrap(self._preset_hint, 26)

    def _build_connection_card(self, parent) -> None:
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("连接"), t("key 只存环境变量名，不存 key 本身。"), bg=CARD)

        self._entries["model"] = _field(box, t("模型"), CARD, self._settings.get("model") or "",
                                        hint=t("例如 deepseek-chat · qwen2.5:7b · gpt-4o-mini"))
        self._entries["base_url"] = _field(box, t("地址 base_url"), CARD,
                                           self._settings.get("base_url") or "",
                                           hint=t("OpenAI 兼容端点一般以 /v1 结尾；Anthropic 留空用官方地址"))
        self._entries["api_key_env"] = _field(box, t("API key 的环境变量名"), CARD,
                                              self._settings.get("api_key_env") or "",
                                              hint=t("只写变量名，例如 DEEPSEEK_API_KEY；本地端点可以留空"))
        self._entries["api_key_env"].bind("<KeyRelease>", lambda _event: self._refresh_env())
        self._env_label = tk.Label(box, text="", bg=CARD, fg=FAINT, font=_font(10), anchor="w")
        self._env_label.pack(fill="x", pady=(0, 10))
        _bind_wrap(self._env_label, 26)

        head = tk.Frame(box, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text=t("温度"), bg=CARD, fg=MUTED, font=_font(10), anchor="w").pack(side="left")
        self._temp_value = tk.Label(head, text="", bg=CARD, fg=ACCENT, font=_font(10, "bold"))
        self._temp_value.pack(side="right")
        temperature = self._settings.get("temperature")
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = 0.8
        self._slider = _Slider(box, temperature, minimum=0.0, maximum=1.5, step=0.05,
                               bg=CARD, command=self._on_temperature)
        self._slider.pack(fill="x", pady=(6, 12))
        self._on_temperature(self._slider.get())

        local = tk.Label(box, text=t(LOCAL_HINT), bg=CARD, fg=FAINT, font=_font(10),
                         justify="left", anchor="w")
        local.pack(fill="x")
        _bind_wrap(local, 26)
        self._refresh_env()

    def _build_memory_card(self, parent) -> None:
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("记忆"), t("她的一生是记忆堆起来的；宁可少记，不要记乱。"), bg=CARD)

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(0, 16))
        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=t("严格记忆"), bg=CARD, fg=TEXT_SOFT, font=_font(10), anchor="w").pack(fill="x")
        sub = tk.Label(info, text=t("只写她确定记得的事；没把握的不写进记忆。"), bg=CARD, fg=FAINT,
                       font=_font(10), anchor="w", justify="left")
        sub.pack(fill="x", pady=(2, 0))
        _bind_wrap(sub, 150)
        self._strict = _Toggle(row, bool(self._settings.get("strict")), bg=CARD)
        self._strict.pack(side="right", padx=(12, 0))

        row2 = tk.Frame(box, bg=CARD)
        row2.pack(fill="x")
        info2 = tk.Frame(row2, bg=CARD)
        info2.pack(side="left", fill="x", expand=True)
        tk.Label(info2, text=t("每轮最多提炼几条（1–50）"), bg=CARD, fg=TEXT_SOFT, font=_font(10),
                 anchor="w").pack(fill="x")
        sub2 = tk.Label(info2, text=t("原始对话保留，下一轮仍可提炼新的记忆。"), bg=CARD, fg=FAINT,
                        font=_font(10), anchor="w")
        sub2.pack(fill="x", pady=(2, 0))
        _bind_wrap(sub2, 150)
        daily_max = self._settings.get("daily_max")
        try:
            daily_max = int(daily_max)
        except (TypeError, ValueError):
            daily_max = 8
        self._spin = tk.Spinbox(row2, from_=1, to=50, width=3, bg=INPUT_BG, fg=TEXT,
                                buttonbackground=SURFACE_HI, relief="flat", bd=0, font=_font(10),
                                highlightthickness=1, highlightbackground=BORDER,
                                highlightcolor=ACCENT, insertbackground=TEXT, justify="center")
        self._spin.delete(0, "end")
        self._spin.insert(0, str(max(1, min(50, daily_max))))
        self._spin.pack(side="right", padx=(12, 0), ipady=3)

    def _build_senses_card(self, parent) -> None:
        """感官：她一直看得见光、听得见声音；有视觉的脑时她自己看懂。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(6, 16))
        box = card.inner
        _section(
            box,
            t("感官"),
            t("她看得见光，也听得见声音；你的脑能看图时，她会自己看懂。"),
            bg=CARD,
        )

    def _build_clock_card(self, parent) -> None:
        """她的时间：只有一种走法——真实的一天。这里只说明，不做选择。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("时间"), t("她的时间不需要设置：一天就是真实的一天。"), bg=CARD)
        hint = tk.Label(
            box,
            text=t("每过一个凌晨，她过完一天、写一篇日记；窗口关着的时间不补写，她只记得自己睡了一阵。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        hint.pack(fill="x", pady=(2, 0))
        _bind_wrap(hint, 30)

    def _build_bond_card(self, parent) -> None:
        """关系：只读。熟悉度、没做到的承诺，全从 mind/bonds.json 读出来。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("关系"), t("她记得你们之间发生过什么；这里只是读给你看。"), bg=CARD)

        self._bond_days_label = tk.Label(box, text=t("还不认识很久"), bg=CARD, fg=MUTED,
                                         font=_font(10), anchor="w", justify="left")
        self._bond_days_label.pack(fill="x")
        _bind_wrap(self._bond_days_label, 26)

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(5, 0))
        self._bond_familiar_label = tk.Label(row, text=t("熟悉度 0%（说过 0 次话）"), bg=CARD,
                                             fg=MUTED, font=_font(10), anchor="w")
        self._bond_familiar_label.pack(side="left")
        self._bond_meter = tk.Canvas(row, height=4, bg=CARD, highlightthickness=0, bd=0)
        self._bond_meter.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
        self._bond_meter.bind("<Configure>", lambda _event: self._draw_bond_meter())

        tk.Label(box, text=t("还没做到的承诺"), bg=CARD, fg=FAINT, font=_font(10),
                 anchor="w").pack(fill="x", pady=(14, 5))
        self._bond_list = tk.Frame(box, bg=CARD)
        self._bond_list.pack(fill="x")
        self._bond_hint = tk.Label(box, text="", bg=CARD, fg=FAINT, font=_font(10),
                                   anchor="w", justify="left")
        self._bond_hint.pack(fill="x", pady=(6, 0))
        _bind_wrap(self._bond_hint, 26)
        self._bond_data: dict = {}
        self._refresh_bond_card()

    def _draw_bond_meter(self) -> None:
        data = getattr(self, "_bond_data", {}) or {}
        try:
            ratio = float(data.get("familiarity") or 0.0)
        except (TypeError, ValueError):
            ratio = 0.0
        _paint_meter(self._bond_meter, ratio)

    def refresh_bonds(self) -> None:
        """只刷新关系卡：给窗口的 _refresh() 用，不动其它还没保存的字段。"""
        self._refresh_bond_card()

    def _refresh_bond_card(self) -> None:
        """从磁盘重读关系，再填这张只读卡片；失败时安静地显示空档。"""
        data = _bond_snapshot(self.pack_dir)
        self._bond_data = data
        available = bool(data.get("available"))
        pending = data.get("pending") or []
        try:
            pending_count = int(data.get("pending_count") or 0)
        except (TypeError, ValueError):
            pending_count = len(pending)
        due_ids = {str((item or {}).get("id") or "") for item in (data.get("due_today") or [])}
        try:
            if available:
                self._bond_days_label.configure(
                    text=t("认识的第 {0} 天（从第 {1} 天开始）").format(
                        int(data.get("days") or 0), int(data.get("since_day") or 1)),
                    fg=TEXT_SOFT)
            else:
                self._bond_days_label.configure(text=t("还不认识很久"), fg=MUTED)
        except Exception:
            pass
        try:
            percent = int(round(float(data.get("familiarity") or 0.0) * 100))
            self._bond_familiar_label.configure(
                text=t("熟悉度 {0}%（说过 {1} 次话）").format(
                    percent, int(data.get("talks") or 0)),
                fg=MUTED)
        except Exception:
            pass
        box = self._bond_list
        try:
            for child in box.winfo_children():
                child.destroy()
            if not pending and pending_count <= 0:
                empty = t("她还没有答应过你什么。") if available else t("还没有承诺。")
                tk.Label(box, text=empty, bg=CARD, fg=FAINT, font=_font(10),
                         anchor="w", justify="left").pack(fill="x")
            else:
                for item in pending[:3]:
                    item = item if isinstance(item, dict) else {}
                    due_day = item.get("due_day")
                    if str(item.get("id") or "") in due_ids:
                        due_text = t("今天到期")
                    elif due_day:
                        due_text = t("第 {0} 天到期").format(due_day)
                    else:
                        due_text = t("没有定期限")
                    line = "{0} · {1} · {2}".format(
                        str(item.get("id") or ""), str(item.get("text") or ""), due_text)
                    label = tk.Label(box, text=line, bg=CARD,
                                     fg=SENSE if due_text == t("今天到期") else TEXT_SOFT,
                                     font=_font(10), anchor="w", justify="left")
                    label.pack(fill="x", pady=(0, 4))
                    _bind_wrap(label, 10)
                remaining = max(0, pending_count - len(pending[:3]))
                if remaining > 0:
                    tk.Label(box, text=t("……还有 {0} 条没列出来。").format(remaining), bg=CARD,
                             fg=FAINT, font=_font(10), anchor="w").pack(fill="x")
        except Exception:
            pass
        hint = "" if available else t("还没有关系记录；等她和你说过话、答应过你事情，这里会慢慢长出来。")
        try:
            self._bond_hint.configure(text=hint)
        except Exception:
            pass
        self._draw_bond_meter()

    def _build_memorial_card(self, parent) -> None:
        """有限性：只读。记着的日子、没放下的遗憾、告别过的人、缺席的日子。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("有限性"), t("她记得日子，也记得没做到的事。"), bg=CARD)

        self._memorial_days_label = tk.Label(box, text="", bg=CARD, fg=TEXT_SOFT,
                                             font=_font(10), anchor="w", justify="left")
        self._memorial_days_label.pack(fill="x")
        _bind_wrap(self._memorial_days_label, 26)
        self._memorial_day_list = tk.Frame(box, bg=CARD)
        self._memorial_day_list.pack(fill="x", pady=(3, 0))

        self._memorial_regret_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                               font=_font(10), anchor="w", justify="left")
        self._memorial_regret_label.pack(fill="x", pady=(14, 0))
        self._memorial_regret_list = tk.Frame(box, bg=CARD)
        self._memorial_regret_list.pack(fill="x", pady=(3, 0))

        self._memorial_farewell_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                                 font=_font(10), anchor="w", justify="left")
        self._memorial_farewell_label.pack(fill="x", pady=(14, 0))
        self._memorial_farewell_list = tk.Frame(box, bg=CARD)
        self._memorial_farewell_list.pack(fill="x", pady=(3, 0))

        self._memorial_missing_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                                font=_font(10), anchor="w", justify="left")
        self._memorial_hint = tk.Label(box, text="", bg=CARD, fg=FAINT,
                                       font=_font(10), anchor="w", justify="left")
        self._memorial_hint.pack(fill="x", pady=(10, 0))
        _bind_wrap(self._memorial_hint, 26)
        self._memorial_data: dict = {}
        self._refresh_memorial_card()

    def refresh_memorial(self) -> None:
        """只刷新有限性卡：给窗口的 _refresh() 用，不动别的字段。"""
        self._refresh_memorial_card()

    @staticmethod
    def _clear_children(box) -> None:
        try:
            for child in box.winfo_children():
                child.destroy()
        except Exception:
            pass

    @staticmethod
    def _memorial_row(box, text: str, *, fg=None) -> None:
        if fg is None:
            fg = T.get("TEXT_SOFT")
        label = tk.Label(box, text=str(text), bg=CARD, fg=fg, font=_font(10),
                         anchor="w", justify="left")
        label.pack(fill="x", pady=(0, 4))
        _bind_wrap(label, 10)

    def _refresh_memorial_card(self) -> None:
        """从磁盘重读有限性，再填这张只读卡片；失败时安静地显示空档。"""
        data = _memorial_snapshot(self.pack_dir)
        self._memorial_data = data
        available = bool(data.get("available"))
        anniversaries = [item for item in (data.get("anniversaries") or [])
                         if isinstance(item, dict)]
        regrets = [item for item in (data.get("regrets") or []) if isinstance(item, dict)]
        farewells = [item for item in (data.get("farewells") or []) if isinstance(item, dict)]
        try:
            regret_count = max(int(data.get("regret_count") or 0), len(regrets))
        except (TypeError, ValueError):
            regret_count = len(regrets)
        try:
            farewell_count = max(int(data.get("farewell_count") or 0), len(farewells))
        except (TypeError, ValueError):
            farewell_count = len(farewells)
        try:
            missing_days = int(data.get("missing_days") or 0)
        except (TypeError, ValueError):
            missing_days = 0

        # 记着的日子
        try:
            if anniversaries:
                self._memorial_days_label.configure(
                    text=t("记着的日子 {0} 个").format(len(anniversaries)), fg=TEXT_SOFT)
            else:
                self._memorial_days_label.configure(text=t("她还没有记下特别的日子。"), fg=MUTED)
        except Exception:
            pass
        self._clear_children(self._memorial_day_list)
        try:
            for item in anniversaries[:3]:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                try:
                    day_no = int(item.get("day") or 0)
                except (TypeError, ValueError):
                    day_no = 0
                tail = str(item.get("note") or "").strip() or str(item.get("kind") or "custom")
                self._memorial_row(self._memorial_day_list,
                                   t("{0} · 第 {1} 天 · {2}").format(name, day_no, tail))
            if len(anniversaries) > 3:
                self._memorial_row(self._memorial_day_list,
                                   t("……还有 {0} 个没列出来。").format(len(anniversaries) - 3),
                                   fg=FAINT)
        except Exception:
            pass

        # 遗憾
        try:
            if regret_count > 0:
                self._memorial_regret_label.configure(
                    text=t("遗憾 {0} 件").format(regret_count), fg=MUTED)
            else:
                self._memorial_regret_label.configure(text=t("没有还没放下的遗憾。"), fg=FAINT)
        except Exception:
            pass
        self._clear_children(self._memorial_regret_list)
        try:
            for item in regrets[:3]:
                text_value = str(item.get("text") or "").strip()
                if not text_value:
                    continue
                try:
                    day_no = int(item.get("day") or 0)
                except (TypeError, ValueError):
                    day_no = 0
                line = (t("第 {0} 天 · {1}").format(day_no, text_value)
                        if day_no else text_value)
                self._memorial_row(self._memorial_regret_list, line)
            leftover = max(0, regret_count - len(regrets[:3]))
            if leftover > 0:
                self._memorial_row(self._memorial_regret_list,
                                   t("……还有 {0} 件没列出来。").format(leftover), fg=FAINT)
        except Exception:
            pass

        # 告别
        try:
            if farewell_count > 0:
                self._memorial_farewell_label.configure(
                    text=t("告别 {0} 次").format(farewell_count), fg=MUTED)
            else:
                self._memorial_farewell_label.configure(text=t("还没有告别过。"), fg=FAINT)
        except Exception:
            pass
        self._clear_children(self._memorial_farewell_list)
        try:
            for item in farewells[:3]:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                try:
                    day_no = int(item.get("day") or 0)
                except (TypeError, ValueError):
                    day_no = 0
                line = t("{0} · 第 {1} 天 · {2}").format(
                    name, day_no, str(item.get("kind") or "goodbye"))
                note = str(item.get("note") or "").strip()
                if note:
                    line += " · " + note
                self._memorial_row(self._memorial_farewell_list, line)
            leftover = max(0, farewell_count - len(farewells[:3]))
            if leftover > 0:
                self._memorial_row(self._memorial_farewell_list,
                                   t("……还有 {0} 次没列出来。").format(leftover), fg=FAINT)
        except Exception:
            pass

        # 她不在的日子：0 不显示
        try:
            if missing_days > 0:
                self._memorial_missing_label.configure(
                    text=t("她不在的日子：{0} 天").format(missing_days), fg=MUTED)
                if self._memorial_missing_label.winfo_manager() != "pack":
                    self._memorial_missing_label.pack(fill="x", pady=(12, 0))
            else:
                self._memorial_missing_label.pack_forget()
        except Exception:
            pass

        # 空态提示：没有记录时自然一点
        hint = ""
        if not available:
            hint = t("还没有她记着的日子；等日子慢慢过去，这里会自己长出来。")
        elif not (anniversaries or regrets or farewells or missing_days):
            hint = t("她还没有记下特别的日子；日子还长，慢慢来。")
        try:
            self._memorial_hint.configure(text=hint)
        except Exception:
            pass

    def _build_inner_card(self, parent) -> None:
        """内在：只读。沉默权、自我叙事、最近做过的梦、最近的自我更正。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("内在"), t("她有自己的沉默、梦，和关于自己的说法。"), bg=CARD)

        # 沉默权
        tk.Label(box, text=t("沉默权"), bg=CARD, fg=TEXT_SOFT, font=_font(10),
                 anchor="w").pack(fill="x")
        self._inner_silence_value = tk.Label(box, text=t("关着 · 她愿意说话"), bg=CARD,
                                             fg=MUTED, font=_font(10), anchor="w",
                                             justify="left")
        self._inner_silence_value.pack(fill="x", pady=(2, 0))
        _bind_wrap(self._inner_silence_value, 26)
        self._inner_silence_note = tk.Label(box, text="", bg=CARD, fg=FAINT,
                                            font=_font(10), anchor="w", justify="left")
        _bind_wrap(self._inner_silence_note, 26)

        # 自我叙事
        self._inner_narrative_title = tk.Label(box, text=t("自我叙事"), bg=CARD, fg=TEXT_SOFT,
                                               font=_font(10), anchor="w")
        self._inner_narrative_title.pack(fill="x", pady=(14, 0))
        self._inner_narrative_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                               font=_font(10), anchor="w", justify="left")
        self._inner_narrative_label.pack(fill="x", pady=(2, 0))
        _bind_wrap(self._inner_narrative_label, 26)
        self._inner_narrative_day = tk.Label(box, text="", bg=CARD, fg=FAINT,
                                             font=_font(10), anchor="w", justify="left")

        # 最近做过的梦
        self._inner_dream_title = tk.Label(box, text=t("最近做过的梦"), bg=CARD, fg=TEXT_SOFT,
                                           font=_font(10), anchor="w", justify="left")
        self._inner_dream_title.pack(fill="x", pady=(14, 0))
        self._inner_dream_list = tk.Frame(box, bg=CARD)
        self._inner_dream_list.pack(fill="x", pady=(3, 0))

        # 最近的自我更正
        self._inner_correction_title = tk.Label(box, text=t("最近的自我更正"), bg=CARD,
                                                fg=TEXT_SOFT, font=_font(10), anchor="w",
                                                justify="left")
        self._inner_correction_title.pack(fill="x", pady=(14, 0))
        self._inner_correction_list = tk.Frame(box, bg=CARD)
        self._inner_correction_list.pack(fill="x", pady=(3, 0))

        self._inner_hint = tk.Label(
            box, text=t("这些都是她自己留下来的，不会因为换窗口而消失。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        self._inner_hint.pack(fill="x", pady=(10, 0))
        _bind_wrap(self._inner_hint, 26)
        self._inner_data: dict = {}
        self._refresh_inner_card()

    def refresh_inner(self) -> None:
        """只刷新内在卡：给窗口的 _refresh() 用，不动别的字段。"""
        self._refresh_inner_card()

    def _refresh_inner_card(self) -> None:
        """从磁盘重读内在，再填这张只读卡片；失败时安静显示空档。"""

        data = _inner_snapshot(self.pack_dir)
        self._inner_data = data

        def clip(value, limit=28) -> str:
            text = str(value or "").strip()
            return text if len(text) <= limit else text[:limit - 1] + "…"

        def day_of(item) -> int:
            try:
                return int((item or {}).get("day") or 0)
            except (TypeError, ValueError):
                return 0

        # 沉默权：开/关 + note + 从第 N 天起；关着就写她愿意说话。
        silence = data.get("silence") if isinstance(data.get("silence"), dict) else {}
        on = bool(silence.get("on"))
        note = str(silence.get("note") or "").strip()
        try:
            since = int(silence.get("since_day") or 0)
        except (TypeError, ValueError):
            since = 0
        try:
            if on:
                text = t("开着 · 从第 {0} 天起").format(since) if since else t("开着")
                self._inner_silence_value.configure(text=text, fg=SENSE)
            else:
                self._inner_silence_value.configure(text=t("关着 · 她愿意说话"), fg=MUTED)
            if note:
                self._inner_silence_note.configure(text=t("「{0}」").format(clip(note, 40)))
                if self._inner_silence_note.winfo_manager() != "pack":
                    # 放在「自我叙事」标题前面：note 跟着沉默权走，不能落到卡片底部
                    self._inner_silence_note.pack(fill="x", pady=(3, 0),
                                                  before=self._inner_narrative_title)
            else:
                self._inner_silence_note.pack_forget()
        except Exception:
            pass

        # 自我叙事
        from ...inner_sources import display_lines as inner_lines
        narrative = data.get("narrative") if isinstance(data.get("narrative"), dict) else {}
        narrative_text = "\n".join(inner_lines(narrative))
        try:
            updated_day = int(narrative.get("updated_day") or 0)
        except (TypeError, ValueError):
            updated_day = 0
        try:
            if narrative_text:
                self._inner_narrative_label.configure(text=narrative_text, fg=TEXT_SOFT)
            else:
                self._inner_narrative_label.configure(
                    text=t("她还没有给自己写过叙事。"), fg=MUTED)
            if updated_day:
                self._inner_narrative_day.configure(
                    text=t("第 {0} 天写的").format(updated_day))
                if self._inner_narrative_day.winfo_manager() != "pack":
                    # 紧跟叙事正文，不落到列表/提示后面
                    self._inner_narrative_day.pack(fill="x", pady=(2, 0),
                                                   after=self._inner_narrative_label)
            else:
                self._inner_narrative_day.pack_forget()
        except Exception:
            pass

        # 最近的梦：最多 2 条，每条「第 N 天 · 文本」。
        dreams = [item for item in (data.get("last_dreams") or [])
                  if isinstance(item, dict)]
        dream_count = data.get("dreams") or 0
        try:
            dream_title = t("最近做过的梦（共 {0} 个）").format(int(dream_count)) \
                if dream_count else t("最近做过的梦")
            self._inner_dream_title.configure(text=dream_title)
        except Exception:
            pass
        self._clear_children(self._inner_dream_list)
        try:
            if dreams:
                for item in dreams[:2]:
                    text_value = "\n".join(inner_lines(item))
                    if not text_value:
                        continue
                    day_no = day_of(item)
                    line = (t("第 {0} 天 · {1}").format(day_no, text_value)
                            if day_no else text_value)
                    self._memorial_row(self._inner_dream_list, line)
            else:
                self._memorial_row(self._inner_dream_list, t("她还没有做过梦。"), fg=MUTED)
        except Exception:
            pass

        # 最近的自我更正：最多 2 条，「第 N 天 · 以前以为 X，现在知道 Y」。
        corrections = [item for item in (data.get("recent_corrections") or [])
                       if isinstance(item, dict)]
        correction_count = data.get("corrections") or 0
        try:
            correction_title = t("最近的自我更正（共 {0} 次）").format(int(correction_count)) \
                if correction_count else t("最近的自我更正")
            self._inner_correction_title.configure(text=correction_title)
        except Exception:
            pass
        self._clear_children(self._inner_correction_list)
        try:
            if corrections:
                for item in corrections[:2]:
                    line = "\n".join(inner_lines(item))
                    if not line:
                        continue
                    day_no = day_of(item)
                    if day_no:
                        line = t("第 {0} 天 · {1}").format(day_no, line)
                    self._memorial_row(self._inner_correction_list, line)
            else:
                self._memorial_row(self._inner_correction_list, t("她还没有更正过自己。"),
                                   fg=MUTED)
        except Exception:
            pass

    def _build_works_card(self, parent) -> None:
        """作品：只读。她写下的诗、信，和一点字符画。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("作品"), t("她会写诗、写信，也会画点东西。这些是她自己留下的。"), bg=CARD)

        self._works_stats_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                           font=_font(10), anchor="w", justify="left")
        self._works_stats_label.pack(fill="x")
        _bind_wrap(self._works_stats_label, 26)
        self._works_list = tk.Frame(box, bg=CARD)
        self._works_list.pack(fill="x", pady=(4, 0))
        self._works_hint = tk.Label(
            box, text=t("只有文字：画也是字符画，谁都能读、能带走。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        self._works_hint.pack(fill="x", pady=(8, 0))
        _bind_wrap(self._works_hint, 26)
        self._works_data: dict = {}
        self._refresh_works_card()

    def refresh_works(self) -> None:
        """只刷新作品卡：给窗口的 _refresh() 用，不动别的字段。"""
        self._refresh_works_card()

    def _refresh_works_card(self) -> None:
        """从磁盘重读作品，再填这张只读卡片；失败时安静显示空档。"""

        data = _works_snapshot(self.pack_dir)
        self._works_data = data
        try:
            total = max(0, int(data.get("total") or 0))
        except (TypeError, ValueError):
            total = 0
        try:
            poems = max(0, int(data.get("poems") or 0))
            letters = max(0, int(data.get("letters") or 0))
            drawings = max(0, int(data.get("drawings") or 0))
        except (TypeError, ValueError):
            poems = letters = drawings = 0
        recent = [item for item in (data.get("recent") or []) if isinstance(item, dict)]
        # 统计行；一件都没有时直接换成空态文案。
        try:
            if total > 0:
                self._works_stats_label.configure(
                    text=t("诗 {0} 首 / 信 {1} 封 / 画 {2} 张（共 {3} 件）").format(
                        poems, letters, drawings, total),
                    fg=TEXT_SOFT)
            else:
                self._works_stats_label.configure(
                    text=t("她还没有留下作品。（等她想写的时候，或者用 `seed make` 让她写一样东西。）"),
                    fg=MUTED)
        except Exception:
            pass
        self._clear_children(self._works_list)
        try:
            for item in recent[:3]:
                self._add_works_row(self._works_list, item)
        except Exception:
            pass

    @staticmethod
    def _add_works_row(parent, item) -> None:
        """一条作品：标题行「[诗] 标题 · 第 N 天」+ 正文预览（画最多 2 行）。"""

        def clip(value, limit: int) -> str:
            text = str(value or "").strip()
            return text if len(text) <= limit else text[:limit - 1] + "…"

        kind = str(item.get("kind") or "")
        label = str(item.get("label") or "").strip() or t("作品")
        title = clip(item.get("title"), 30) or t("没有标题")
        try:
            day_no = int(item.get("day") or 0)
        except (TypeError, ValueError):
            day_no = 0
        head = "[{0}] {1}".format(label, title)
        if day_no:
            head += t(" · 第 {0} 天").format(day_no)
        head_label = tk.Label(parent, text=head, bg=CARD, fg=TEXT_SOFT, font=_font(10),
                              anchor="w", justify="left")
        head_label.pack(fill="x", pady=(4, 0))
        _bind_wrap(head_label, 26)
        # 正文预览：诗/信各一行；画是字符画，给两行。
        body_text = str(item.get("text") or "").strip()
        lines = body_text.splitlines() if body_text else []
        if not lines:
            lines = [t("（没有正文）")]
        if kind == "drawing":
            body = "\n".join(clip(line, 48) for line in lines[:2])
            font = _font(10, family="latin")
        else:
            body = clip(lines[0], 30)
            font = _font(10)
        body_label = tk.Label(parent, text=body, bg=CARD, fg=FAINT, font=font,
                              anchor="w", justify="left")
        body_label.pack(fill="x", pady=(1, 0))
        _bind_wrap(body_label, 26)

    def _current_day(self) -> int:
        """她那边现在是第几天：跟主窗 _snapshot 一样取 life/ 里最后一天。"""

        try:
            days = list_days(str(self.pack_dir))
        except Exception:
            return 0
        if not days:
            return 0
        try:
            return int(days[-1].get("day") or 0)
        except (TypeError, ValueError):
            return 0

    def _build_hands_card(self, parent) -> None:
        """手：只读。她替你记着的事，到期她会自己说出口。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("手"), t("她能替你做的不多：记着，然后提醒。"), bg=CARD)

        self._hands_stats_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                           font=_font(10), anchor="w", justify="left")
        self._hands_stats_label.pack(fill="x")
        _bind_wrap(self._hands_stats_label, 26)
        self._hands_list = tk.Frame(box, bg=CARD)
        self._hands_list.pack(fill="x", pady=(4, 0))
        self._hands_hint = tk.Label(
            box, text=t("到期那天她会自己说出口；说过了就不再重复。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        self._hands_hint.pack(fill="x", pady=(8, 0))
        _bind_wrap(self._hands_hint, 26)
        self._hands_data: dict = {}
        self._refresh_hands_card()

    def refresh_hands(self) -> None:
        """只刷新手卡：给窗口的 _refresh() 用，不动别的字段。"""
        self._refresh_hands_card()

    def _refresh_hands_card(self) -> None:
        """从磁盘重读她手里的事，再填这张只读卡片；失败时安静显示空档。"""

        data = _hands_snapshot(self.pack_dir, self._current_day())
        self._hands_data = data
        pending = [item for item in (data.get("pending") or []) if isinstance(item, dict)]
        due = [item for item in (data.get("due_today") or []) if isinstance(item, dict)]
        due_ids = {str((item or {}).get("id") or "") for item in due}
        try:
            missed = int(data.get("missed") or 0)
        except (TypeError, ValueError):
            missed = 0
        try:
            total = int(data.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        said = max(0, total - len(pending) - missed)

        def clip(value, limit=40) -> str:
            text = str(value or "").strip()
            return text if len(text) <= limit else text[:limit - 1] + "…"

        if total > 0:
            stats = t("记着 {0} 条 · 说过了 {1} 条 · 错过 {2} 条").format(
                len(pending), said, missed)
        else:
            stats = t("她手里还没有替你记着的事。")
        try:
            self._hands_stats_label.configure(text=stats, fg=MUTED)
        except Exception:
            pass
        self._clear_children(self._hands_list)
        try:
            if pending:
                for item in pending[:3]:
                    text = clip(item.get("text"), 40)
                    if not text:
                        continue
                    try:
                        due_day = int(item.get("due_day") or 0)
                    except (TypeError, ValueError):
                        due_day = 0
                    line = t("第 {0} 天 · {1}").format(due_day, text) if due_day else text
                    self._hands_row(self._hands_list, line,
                                    today=str(item.get("id") or "") in due_ids)
            else:
                self._memorial_row(self._hands_list, t("她手里还没有替你记着的事。"),
                                   fg=MUTED)
        except Exception:
            pass

    @staticmethod
    def _hands_row(box, text: str, *, today: bool = False) -> None:
        """一条她记着的事；到期当天的行用 SENSE 色，并在右边标「今天」。"""

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(0, 4))
        label = tk.Label(row, text=str(text), bg=CARD,
                         fg=SENSE if today else TEXT_SOFT, font=_font(10),
                         anchor="w", justify="left")
        label.pack(side="left", fill="x", expand=True)
        _bind_wrap(label, 60)
        if today:
            tag = tk.Label(row, text=t("今天"), bg=CARD, fg=SENSE, font=_font(10, "bold"),
                           anchor="e")
            tag.pack(side="right", padx=(8, 0))

    def _build_friends_card(self, parent) -> None:
        """他者：只读。她记得来过的别人，也记得谁不在了。"""

        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("他者"), t("她记得来过的别人，也记得谁不在了。"), bg=CARD)

        self._friends_stats_label = tk.Label(box, text="", bg=CARD, fg=MUTED,
                                             font=_font(10), anchor="w", justify="left")
        self._friends_stats_label.pack(fill="x")
        _bind_wrap(self._friends_stats_label, 26)
        self._friends_list = tk.Frame(box, bg=CARD)
        self._friends_list.pack(fill="x", pady=(4, 0))
        self._friends_hint = tk.Label(
            box, text=t("她记得的是关系，不是别人的记忆。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        self._friends_hint.pack(fill="x", pady=(8, 0))
        _bind_wrap(self._friends_hint, 26)
        self._friends_data: dict = {}
        self._refresh_friends_card()

    def refresh_friends(self) -> None:
        """只刷新他者卡：给窗口的 _refresh() 用，不动别的字段。"""
        self._refresh_friends_card()

    def _refresh_friends_card(self) -> None:
        """从磁盘重读她记得的别人，再填这张只读卡片；失败时安静显示空档。"""

        data = _friends_snapshot(self.pack_dir)
        self._friends_data = data
        recent = [item for item in (data.get("recent") or []) if isinstance(item, dict)]
        try:
            total = max(0, int(data.get("total") or 0))
            alive = max(0, int(data.get("alive") or 0))
            lost = max(0, int(data.get("lost") or 0))
        except (TypeError, ValueError):
            total = alive = lost = 0

        def clip(value, limit=20) -> str:
            text = str(value or "").strip()
            return text if len(text) <= limit else text[:limit - 1] + "…"

        if total > 0:
            stats = t("来过 {0} 位 · 还在 {1} · 失联 {2}").format(total, alive, lost)
        else:
            stats = t("还没有别人来过。")
        try:
            self._friends_stats_label.configure(text=stats, fg=MUTED)
        except Exception:
            pass
        self._clear_children(self._friends_list)
        try:
            if recent:
                for item in recent[:3]:
                    name = clip(item.get("name"), 20)
                    if not name:
                        continue
                    try:
                        visits = max(0, int(item.get("visits") or 0))
                    except (TypeError, ValueError):
                        visits = 0
                    try:
                        day = int(item.get("last_visit_day") or 0)
                    except (TypeError, ValueError):
                        day = 0
                    try:
                        lost_day = int(item.get("lost_day") or 0)
                    except (TypeError, ValueError):
                        lost_day = 0
                    if str(item.get("status") or "alive") == "lost":
                        text = t("{0} · 第 {1} 天走了").format(name, lost_day or day) \
                            if (lost_day or day) else t("{0} · 走了").format(name)
                        self._memorial_row(self._friends_list, text, fg=FAINT)
                    else:
                        text = t("{0} · 来过 {1} 次 · 第 {2} 天").format(name, visits, day) if day \
                            else t("{0} · 来过 {1} 次").format(name, visits)
                        self._memorial_row(self._friends_list, text, fg=TEXT_SOFT)
            else:
                self._memorial_row(self._friends_list, t("用 seed visit 让别的鱼来串门。"),
                                   fg=FAINT)
        except Exception:
            pass

    # —— QQ 载体（1.20）：把 QQ 接进来，成为她的又一扇窗 ——

    def _qq_available(self) -> bool:
        """后端 qq 模块缺失时整张卡都不出现：旧包照常能开设置页。"""

        return qq_save_config is not None and qq_test_connection is not None

    def _qq_defaults(self) -> dict:
        """从 ~/.seedbank/config.json 的 qq 段读默认值；读不到就全用默认。"""

        data: dict = {}
        if qq_config_defaults is not None:
            try:
                loaded = qq_config_defaults()
                if isinstance(loaded, dict):
                    data = dict(loaded)
            except Exception:  # noqa: BLE001 - 配置坏了不该拦着设置页
                data = {}
        return data

    def _qq_groups_text(self, value) -> str:
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "")

    def _qq_groups(self) -> list:
        raw = self._read_entry("qq_groups")
        if qq_parse_groups is not None:
            try:
                return list(qq_parse_groups(raw))
            except Exception:  # noqa: BLE001 - 解析失败就退回手动切
                pass
        return [item.strip() for item in str(raw or "").replace("，", ",").split(",")
                if item.strip()]

    def _build_qq_card(self, parent) -> None:
        """QQ：一个 OneBot v11 桥，就是她说话的另一扇窗。"""
        if not self._qq_available():
            return
        defaults = self._qq_defaults()
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("QQ"),
                 t("把 QQ 接进来：需要 SnowLuma / NapCat / LLOneBot 之一（OneBot v11）。"),
                 bg=CARD)

        self._entries["qq_onebot_http"] = _field(
            box, t("OneBot 地址"), CARD,
            str(defaults.get("onebot_http") or QQ_DEFAULT_ONEBOT_HTTP),
            hint=t("默认 http://127.0.0.1:3001；填那个桥的 HTTP 端口。"))
        self._entries["qq_token"] = _field(
            box, t("Token"), CARD, "",
            hint=t("可空；不存明文，仅本次运行使用。"))
        self._entries["qq_owner"] = _field(
            box, t("主人 QQ"), CARD, str(defaults.get("owner") or ""),
            hint=t("必填；私聊只回主人。"))
        self._entries["qq_groups"] = _field(
            box, t("群号白名单"), CARD, self._qq_groups_text(defaults.get("groups")),
            hint=t("可空，逗号分隔；不填 = 不回应群聊。"))

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(2, 0))
        self.qq_test_btn = _Pill(row, t("测试连接"), self._qq_test, bg=CARD,
                                 fill=SURFACE, outline=BORDER, hover=CARD_HI,
                                 fg=TEXT_SOFT, font=_font(10), pad_x=12, height=30)
        self.qq_test_btn.pack(side="left", padx=(0, 8))
        self.qq_launch_btn = _Pill(row, t("启动 QQ 载体"), self._qq_launch, bg=CARD,
                                   fill=ACCENT_SOFT, hover=ACCENT_SOFT, fg=ACCENT_TXT,
                                   outline=ACCENT_LINE, font=_font(10), pad_x=12, height=30)
        self.qq_launch_btn.pack(side="left")

        self._qq_note = tk.Label(box, text="", bg=CARD, fg=FAINT, font=_font(10),
                                 anchor="w", justify="left")
        self._qq_note.pack(fill="x", pady=(8, 0))
        _bind_wrap(self._qq_note, 26)

        self._build_qq_bridges(box)

        hint = tk.Label(
            box, text=t("她的记忆始终在生命包里；QQ 只是又一个窗口。第三方桥有账号风控风险，建议小号。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        hint.pack(fill="x", pady=(6, 0))
        _bind_wrap(hint, 26)

        try:
            self._qq_port = int(defaults.get("port") or QQ_DEFAULT_PORT)
        except (TypeError, ValueError):
            self._qq_port = QQ_DEFAULT_PORT
        self._qq_testing = False
        self._qq_queue: queue.Queue = queue.Queue()
        self._qq_after_id = None
        self._qq_proc = None

    def _build_qq_bridges(self, box) -> None:
        """QQ 卡里的第三方桥子块：下载页 + 配置步骤 + 一键填本机地址。"""

        tk.Frame(box, bg=BORDER, height=1).pack(fill="x", pady=(14, 10))
        title = tk.Label(box, text=t("第三方 OneBot 桥 / 一键配置"), bg=CARD,
                         fg=TEXT_SOFT, font=_font(12, "bold"), anchor="w")
        title.pack(fill="x")
        self._qq_bridges_title = title

        descriptions = {
            "SnowLuma": t("挂在官方 QQ 客户端上的 OneBot 实现（需先装 QQ）"),
            "NapCat": t("QQNT 插件式 OneBot，生态最全"),
            "LLOneBot": t("LiteLoaderQQNT 插件式 OneBot"),
        }
        self.qq_bridge_download_btns = {}
        self.qq_bridge_steps_btns = {}
        for name in ("SnowLuma", "NapCat", "LLOneBot"):
            row = tk.Frame(box, bg=CARD)
            row.pack(fill="x", pady=(8, 0))
            info = tk.Frame(row, bg=CARD)
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=name, bg=CARD, fg=TEXT_SOFT,
                     font=_font(10, "bold"), anchor="w").pack(fill="x")
            desc = tk.Label(info, text=descriptions.get(name, name), bg=CARD,
                            fg=MUTED, font=_font(10), anchor="w", justify="left")
            desc.pack(fill="x")
            _bind_wrap(desc, 150)
            steps_btn = _Pill(
                row, t("配置步骤"),
                lambda bridge=name: self._qq_show_bridge_steps(bridge),
                bg=CARD, fill=SURFACE, outline=BORDER, hover=CARD_HI,
                fg=TEXT_SOFT, font=_font(10), pad_x=10, height=24, radius=12)
            steps_btn.pack(side="right", padx=(6, 0))
            download_btn = _Pill(
                row, t("下载"),
                lambda bridge=name: self._qq_bridge_download(bridge),
                bg=CARD, fill=SURFACE, outline=BORDER, hover=CARD_HI,
                fg=TEXT_SOFT, font=_font(10), pad_x=10, height=24, radius=12)
            download_btn.pack(side="right")
            self.qq_bridge_download_btns[name] = download_btn
            self.qq_bridge_steps_btns[name] = steps_btn

        helper = tk.Frame(box, bg=CARD)
        helper.pack(fill="x", pady=(12, 0))
        self.qq_use_local_btn = _Pill(
            helper, t("用本机默认地址"), self._qq_use_default_address, bg=CARD,
            fill=ACCENT_SOFT, hover=ACCENT_SOFT, fg=ACCENT_TXT,
            outline=ACCENT_LINE, font=_font(10), pad_x=10, height=24, radius=12)
        self.qq_use_local_btn.pack(side="left")
        server_note = tk.Label(
            helper,
            text=t("桥在服务器上？把地址改成 http://服务器IP:3001 即可，输入框一直可编辑。"),
            bg=CARD, fg=MUTED, font=_font(10), anchor="w", justify="left")
        server_note.pack(side="left", fill="x", expand=True, padx=(8, 0))
        _bind_wrap(server_note, 240)

        tail = tk.Label(
            box,
            text=t("桥运行在服务器时：地址填 http://服务器IP:3001，在桥的配置里开启 HTTP 服务（监听 0.0.0.0）并设置 token；本工具不需要公网入口，只有出站连接。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        tail.pack(fill="x", pady=(6, 0))
        _bind_wrap(tail, 26)

    def _qq_bridge_download(self, name: str) -> None:
        """打开某个桥的下载页；URL 固定成常量，方便离线核对。"""

        url = QQ_BRIDGE_DOWNLOADS.get(name)
        if not url:
            return
        try:
            webbrowser.open(url)
        except Exception as error:  # noqa: BLE001 - 打不开浏览器要说人话
            self._qq_say(t("没能打开浏览器：{error}", error=error), "error")
            return
        self._qq_say(t("已打开 {name} 的下载页。", name=name), "ok")

    def _qq_show_bridge_steps(self, name: str) -> None:
        """只读的配置步骤小窗；同一时间只开一个，重复点会抬起来。"""

        existing = getattr(self, "_qq_bridge_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    return
            except Exception:
                pass
        window = tk.Toplevel(self)
        self._qq_bridge_window = window
        window.title(t("{name} · 配置步骤", name=name))
        window.configure(bg=BG)
        window.resizable(False, False)
        try:
            window.transient(self.winfo_toplevel())
        except Exception:
            pass
        width, height = 540, 430
        try:
            screen_w = window.winfo_screenwidth()
            screen_h = window.winfo_screenheight()
            x = max(40, (screen_w - width) // 2)
            y = max(40, (screen_h - height) // 3)
            window.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass
        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(body, text=t("{name} · 配置步骤", name=name), bg=BG, fg=TEXT,
                 font=_font(14, "bold"), anchor="w").pack(fill="x")
        intro = tk.Label(
            body, text=t("四步就好。桥只是把 QQ 的消息转成 OneBot v11 的 HTTP 接口。"),
            bg=BG, fg=MUTED, font=_font(10), anchor="w", justify="left")
        intro.pack(fill="x", pady=(4, 10))
        _bind_wrap(intro, 30)
        steps = (
            t("① 安装并登录 QQ；"),
            t("② 安装 {name} 并启用 HTTP API 服务（默认端口 3001）；", name=name),
            t("③ 在本卡「OneBot 地址」填 http://127.0.0.1:3001（桥在本机）或 http://<服务器IP>:3001（桥在服务器），并在桥上允许外部访问 / 配置 token；"),
            t("④ 点「测试连接」，成功后点「启动 QQ 载体」。"),
        )
        for line in steps:
            label = tk.Label(body, text=line, bg=BG, fg=TEXT_SOFT, font=_font(10),
                             anchor="w", justify="left")
            label.pack(fill="x", pady=(0, 8))
            _bind_wrap(label, 34)
        close_btn = _Pill(body, t("知道了"), window.destroy, bg=BG,
                          fill=SURFACE, outline=BORDER, hover=CARD_HI,
                          fg=TEXT_SOFT, font=_font(10), pad_x=16, height=28)
        close_btn.pack(anchor="e", pady=(6, 0))
        window.bind("<Escape>", lambda _event: window.destroy())
        try:
            window.protocol("WM_DELETE_WINDOW", window.destroy)
            window.focus_force()
        except Exception:
            pass

    def _qq_use_default_address(self) -> None:
        """一键把地址填回本机默认，再异步测一次连接（不卡界面）。"""

        self._write_entry("qq_onebot_http", QQ_DEFAULT_ONEBOT_HTTP)
        self._qq_say(t("地址已填成本机默认：{url}", url=QQ_DEFAULT_ONEBOT_HTTP), "accent")
        self._qq_test()

    def _refresh_qq_card(self) -> None:
        """打开设置页时重读 QQ 配置；token 永远不回显。"""

        if not self._qq_available() or "qq_owner" not in self._entries:
            return
        defaults = self._qq_defaults()
        for name, value in (
            ("qq_onebot_http", defaults.get("onebot_http") or QQ_DEFAULT_ONEBOT_HTTP),
            ("qq_owner", defaults.get("owner") or ""),
            ("qq_groups", self._qq_groups_text(defaults.get("groups"))),
        ):
            self._write_entry(name, value)
        try:
            self._qq_port = int(defaults.get("port") or QQ_DEFAULT_PORT)
        except (TypeError, ValueError):
            self._qq_port = QQ_DEFAULT_PORT
        self._write_entry("qq_token", "")

    def _qq_collect(self) -> dict:
        """把表单收成 qq.save_config 的 patch；token 只在新填时带上。"""

        patch = {
            "pack": str(self.pack_dir),
            "owner": self._read_entry("qq_owner"),
            "groups": self._qq_groups(),
            "onebot_http": self._read_entry("qq_onebot_http") or QQ_DEFAULT_ONEBOT_HTTP,
            "port": int(self._qq_port or QQ_DEFAULT_PORT),
        }
        token = self._read_entry("qq_token")
        if token:
            patch["token"] = token
        return patch

    def _qq_save(self, announce: bool = False) -> bool:
        """保存 QQ 配置；token 只在表单里新填时交给后端。"""

        if qq_save_config is None:
            return False
        try:
            saved = qq_save_config(self._qq_collect())
        except Exception as error:  # noqa: BLE001 - 存不下来要说人话
            self._qq_say(t("QQ 配置没存成：{error}", error=error), "error")
            return False
        if isinstance(saved, dict):
            try:
                self._qq_port = int(saved.get("port") or self._qq_port)
            except (TypeError, ValueError):
                pass
        self._write_entry("qq_token", "")
        if announce:
            self._qq_say(t("QQ 配置已保存。"), "ok")
        return True

    def _qq_say(self, text: str, tone: str = "normal") -> None:
        """QQ 卡片自己的状态行：绿/红/青，别抢底栏。"""

        color = {"error": ERROR, "ok": OK, "accent": ACCENT}.get(tone, FAINT)
        try:
            self._qq_note.configure(text=str(text), fg=color)
        except Exception:
            pass

    def _qq_test(self) -> None:
        """后台问一次 OneBot「你是谁」，结果写回卡片状态行。"""

        if qq_test_connection is None or getattr(self, "_qq_testing", False):
            return
        base = self._read_entry("qq_onebot_http") or QQ_DEFAULT_ONEBOT_HTTP
        token = self._read_entry("qq_token")
        self._qq_testing = True
        try:
            self.qq_test_btn.set_enabled(False)
        except Exception:
            pass
        self._qq_say(t("正在问桥「你是谁」…"), "accent")

        def work():
            try:
                result = qq_test_connection(base, token)
            except Exception as error:  # noqa: BLE001 - 网络问题也要说人话
                result = {"ok": False, "error": str(error)}
            if not isinstance(result, dict):
                result = {"ok": False, "error": t("桥没有回应")}
            self._qq_queue.put(result)

        threading.Thread(target=work, daemon=True).start()
        self._poll_qq_test()

    def _poll_qq_test(self) -> None:
        try:
            result = self._qq_queue.get_nowait()
        except queue.Empty:
            try:
                if not self.winfo_exists():
                    return
                self._qq_after_id = self.after(120, self._poll_qq_test)
            except Exception:
                pass
            return
        self._qq_after_id = None
        self._qq_testing = False
        try:
            self.qq_test_btn.set_enabled(True)
        except Exception:
            pass
        if result.get("ok"):
            who = str(result.get("nickname") or result.get("user_id") or "").strip()
            self._qq_say(t("连上了：{who}", who=who) if who else t("连上了：桥在回应。"), "ok")
        else:
            self._qq_say(t("连不上：{error}",
                           error=result.get("error") or result.get("message") or t("没有回应")),
                         "error")

    def _qq_launch_command(self) -> list:
        """按安装形态拼出 `seed qq` 的启动命令（只拼不启动）。"""

        if getattr(sys, "frozen", False):
            command = [sys.executable, "qq"]
        else:
            # window.py 在 tools/seed/seedbank/ 下：parents[1] 就是 tools/seed。
            seed_py = Path(__file__).resolve().parents[1] / "seed.py"
            command = [sys.executable, str(seed_py), "qq"]
        command += ["--pack", str(self.pack_dir)]
        owner = self._read_entry("qq_owner")
        if owner:
            command += ["--owner", owner]
        groups = self._qq_groups()
        if groups:
            command += ["--groups", ",".join(groups)]
        base = self._read_entry("qq_onebot_http") or QQ_DEFAULT_ONEBOT_HTTP
        command += ["--onebot-http", base,
                    "--port", str(int(self._qq_port or QQ_DEFAULT_PORT))]
        # token 不放进 argv（进程列表可见）；由 _qq_launch 通过环境变量传给孩子。
        return command

    def _qq_stop(self) -> None:
        """关窗时把 QQ 载体一起收走，别留一个孤儿写者。"""
        proc = getattr(self, "_qq_proc", None)
        self._qq_proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:  # noqa: BLE001 - 不听话就强杀
                    proc.kill()
        except Exception:
            pass

    def _qq_launch(self) -> None:
        """把 `seed qq` 作为后台进程拉起来；不阻塞窗口。"""

        existing = getattr(self, "_qq_proc", None)
        if existing is not None and existing.poll() is None:
            self._qq_say(t("QQ 载体已经在跑了（端口 {port}）。",
                           port=int(self._qq_port or QQ_DEFAULT_PORT)), "normal")
            return
        if not self._read_entry("qq_owner"):
            self._qq_say(t("先填主人 QQ 号：私聊只回主人。"), "error")
            return
        try:
            command = self._qq_launch_command()
        except Exception as error:  # noqa: BLE001 - 拼命令失败要说人话
            self._qq_say(t("拼不出启动命令：{error}", error=error), "error")
            return
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        token = self._read_entry("qq_token")
        if token:
            # 只从环境变量传，别出现在进程列表里。
            extra["env"] = {**os.environ, "SEEDBANK_ONEBOT_TOKEN": token}
        try:
            self._qq_proc = subprocess.Popen(command, **extra)  # noqa: S603 - 本机 CLI
        except Exception as error:  # noqa: BLE001 - 拉不起来也要说人话
            self._qq_say(t("载体没启动：{error}", error=error), "error")
            return
        self._qq_save()
        self._qq_say(t("载体已启动（端口 {port}），在 QQ 里给主人发消息试试。",
                       port=int(self._qq_port or QQ_DEFAULT_PORT)), "ok")

    def _build_window_card(self, parent) -> None:
        """桌面开关：总在最前、开机自启；改了立刻生效，不用点保存。"""
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, radius=18, inset=20)
        card.pack(fill="x", padx=22, pady=(0, 24))
        box = card.inner
        _section(box, t("窗口"), t("这两个开关立刻生效，只影响这台电脑。"), bg=CARD)

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(0, 16))
        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=t("总在最前"), bg=CARD, fg=TEXT_SOFT, font=_font(10),
                 anchor="w").pack(fill="x")
        sub = tk.Label(info, text=t("这扇窗始终浮在其它窗口上面，方便一直看到她。"),
                       bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        sub.pack(fill="x", pady=(2, 0))
        _bind_wrap(sub, 150)
        self._always = _Toggle(row, False, command=self._on_topmost, bg=CARD)
        self._always.pack(side="right", padx=(12, 0))

        row2 = tk.Frame(box, bg=CARD)
        row2.pack(fill="x")
        info2 = tk.Frame(row2, bg=CARD)
        info2.pack(side="left", fill="x", expand=True)
        tk.Label(info2, text=t("开机自启"), bg=CARD, fg=TEXT_SOFT, font=_font(10),
                 anchor="w").pack(fill="x")
        sub2 = tk.Label(info2, text=t("登录 Windows 后自动打开这扇窗；不支持的系统会把开关弹回去。"),
                        bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        sub2.pack(fill="x", pady=(2, 0))
        _bind_wrap(sub2, 150)
        self._autostart = _Toggle(row2, False, command=self._on_autostart, bg=CARD)
        self._autostart.pack(side="right", padx=(12, 0))

        self._window_hint = tk.Label(
            box, text=t("置顶和自启都只跟窗口有关，不碰她的记忆。"),
            bg=CARD, fg=FAINT, font=_font(10), anchor="w", justify="left")
        self._window_hint.pack(fill="x", pady=(12, 0))
        _bind_wrap(self._window_hint, 26)
        ui = self._read_ui_settings()
        try:
            self._always.set(bool(ui.get("always_on_top")))
            self._autostart.set(bool(ui.get("autostart")))
        except Exception:
            pass

    # —— 字段读写 ——

    def _entry(self, name):
        return self._entries.get(name)

    def _read_entry(self, name: str) -> str:
        entry = self._entries.get(name)
        if entry is None:
            return ""
        try:
            return entry.get().strip()
        except Exception:
            return ""

    def _write_entry(self, name: str, value) -> None:
        entry = self._entries.get(name)
        if entry is None:
            return
        try:
            entry.delete(0, "end")
            entry.insert(0, str(value or ""))
        except Exception:
            pass

    def _refresh_env(self) -> None:
        name = self._read_entry("api_key_env")
        try:
            if not name:
                self._env_label.configure(text=t("留空：本地端点通常不需要 key；云端请填环境变量名。"),
                                          fg=FAINT)
                return
            has_key = bool(os.environ.get(name))
            self._env_label.configure(text=t("{name}：{status}", name=name,
                                        status=t("已设置") if has_key else t("未设置")),
                                      fg=OK if has_key else FAINT)
        except Exception:
            pass

    def _on_temperature(self, value) -> None:
        try:
            self._temp_value.configure(text=f"{float(value):.2f}")
        except Exception:
            pass

    # —— 预设与适配器 ——

    def _choose_adapter(self, adapter: str) -> None:
        self._adapter = str(adapter or "stub")
        for key, pill in self._adapter_pills.items():
            if key == self._adapter:
                pill.set_colors(fill=ACCENT_SOFT, outline=ACCENT_LINE, fg=ACCENT_TXT, hover=ACCENT_SOFT)
            else:
                pill.set_colors(fill=SURFACE, outline=BORDER, fg=TEXT_SOFT, hover=CARD_HI)
        self._mark_preset(None)

    def _mark_preset(self, index) -> None:
        self._preset_index = index
        for position, pill in enumerate(self._preset_pills):
            if index is not None and position == index:
                pill.set_colors(fill=ACCENT_SOFT, outline=ACCENT_LINE, fg=ACCENT_TXT, hover=ACCENT_SOFT)
            else:
                pill.set_colors(fill=SURFACE, outline=BORDER, fg=TEXT_SOFT, hover=CARD_HI)

    def _on_preset_layout(self) -> None:
        # 宽度变了，芯片会重建；把当前选中的那颗重新点亮。
        self._mark_preset(self._preset_index)

    def _apply_preset(self, preset, index) -> None:
        self._choose_adapter(str(preset.get("adapter") or "stub"))
        self._write_entry("model", preset.get("model") or "")
        self._write_entry("base_url", preset.get("base_url") or "")
        self._write_entry("api_key_env", preset.get("api_key_env") or "")
        self._mark_preset(index)
        try:
            self._preset_hint.configure(text=t(str(preset.get("hint") or " ")))
        except Exception:
            pass
        self._refresh_env()

    def refresh(self) -> None:
        """打开设置页时，从磁盘重新读一遍；没保存的改动会被丢掉。"""
        self._settings = self._read_settings()
        adapter = str(self._settings.get("adapter") or "stub")
        self._write_entry("model", self._settings.get("model") or "")
        self._write_entry("base_url", self._settings.get("base_url") or "")
        self._write_entry("api_key_env", self._settings.get("api_key_env") or "")
        try:
            temperature = float(self._settings.get("temperature"))
        except (TypeError, ValueError):
            temperature = 0.8
        self._slider.set(temperature)
        self._on_temperature(temperature)
        self._strict.set(bool(self._settings.get("strict")))
        try:
            daily_max = int(self._settings.get("daily_max"))
        except (TypeError, ValueError):
            daily_max = 8
        try:
            self._spin.delete(0, "end")
            self._spin.insert(0, str(max(1, min(50, daily_max))))
        except Exception:
            pass
        self._choose_adapter(adapter)
        index = None
        hint = t("预设只是把下面几个字段填好；真正生效要点「保存」。")
        model = str(self._settings.get("model") or "")
        for position, preset in enumerate(self._presets):
            if str(preset.get("adapter") or "") != adapter:
                continue
            if str(preset.get("model") or "") == model:
                index = position
                hint = t(str(preset.get("hint") or hint))
                break
        self._mark_preset(index)
        try:
            self._preset_hint.configure(text=hint)
        except Exception:
            pass
        self._refresh_env()
        try:
            self._sync_language_pills()
        except Exception:
            pass
        ui = self._read_ui_settings()
        try:
            self._always.set(bool(ui.get("always_on_top")))
        except Exception:
            pass
        try:
            self._autostart.set(bool(ui.get("autostart")))
        except Exception:
            pass
        try:
            self._refresh_bond_card()
        except Exception:
            pass
        try:
            self._refresh_memorial_card()
        except Exception:
            pass
        try:
            self._refresh_inner_card()
        except Exception:
            pass
        try:
            self._refresh_works_card()
        except Exception:
            pass
        try:
            self._refresh_hands_card()
        except Exception:
            pass
        try:
            self._refresh_friends_card()
        except Exception:
            pass
        try:
            self._refresh_qq_card()
        except Exception:
            pass
        self._say(t("改完点保存；下一句话就用新的脑。"))

    # —— 动作 ——

    def _collect(self) -> dict:
        try:
            temperature = round(float(self._slider.get()), 2)
        except Exception:
            temperature = 0.8
        try:
            daily_max = int(float(self._spin.get() or 8))
        except (TypeError, ValueError):
            daily_max = 8
        return {
            "adapter": self._adapter,
            "model": self._read_entry("model") or None,
            "base_url": self._read_entry("base_url") or None,
            "api_key_env": self._read_entry("api_key_env"),
            "temperature": temperature,
            "strict": bool(self._strict.get()),
            "daily_max": max(1, min(50, daily_max)),
        }

    def _say(self, text: str, tone: str = "normal") -> None:
        color = {"error": ERROR, "ok": OK, "accent": ACCENT}.get(tone, MUTED)
        try:
            self.note.configure(text=str(text), fg=color)
        except Exception:
            pass

    def _window_say(self, text: str, tone: str = "normal") -> None:
        """窗口卡片自己的提示行，别把远处底栏的字抢过来。"""
        color = {"error": ERROR, "ok": OK, "accent": ACCENT}.get(tone, FAINT)
        try:
            self._window_hint.configure(text=str(text), fg=color)
        except Exception:
            pass

    def _on_topmost(self, value) -> None:
        """总在最前：立刻改窗口属性，再存进桌面偏好。"""
        try:
            self.winfo_toplevel().attributes("-topmost", bool(value))
        except Exception as error:  # noqa: BLE001 - 个别窗口管理器不认这个属性
            self._always.set(not bool(value))
            self._window_say(t("置顶没成功：{error}", error=error), "error")
            return
        saver = _ui_saver()
        if saver is None:
            self._window_say(t("置顶生效了，但设置模块还没就绪，存不下来。"), "error")
            return
        try:
            saver({"always_on_top": bool(value)})
        except Exception as error:  # noqa: BLE001 - 存不下来也要说一声
            self._window_say(t("置顶生效了，但没存下来：{error}", error=error), "error")
            return
        self._window_say(t("置顶开着：她会一直浮在最上面。") if value
                         else t("不再置顶，她回到普通窗口。"), "ok")

    def _on_autostart(self, value) -> None:
        """开机自启：交给 settings.set_autostart；不行就回弹并说明原因。"""
        setter = getattr(seed_settings, "set_autostart", None) if seed_settings is not None else None
        if setter is None:
            self._autostart.set(not bool(value))
            self._window_say(t("设置模块还没就绪，开机自启暂时改不了。"), "error")
            return
        try:
            result = setter(bool(value))
        except Exception as error:  # noqa: BLE001 - 写注册表失败也要说人话
            self._autostart.set(not bool(value))
            self._window_say(t("开机自启没设成：{error}", error=error), "error")
            return
        result = result if isinstance(result, dict) else {"ok": True, "message": ""}
        if not result.get("ok"):
            self._autostart.set(not bool(value))
            self._window_say(str(result.get("message") or t("这台机器不支持开机自启。")),
                             "error")
            return
        self._autostart.set(bool(value))
        fallback = t("已经设好：登录后自动打开。") if value else t("不再开机自启。")
        self._window_say(str(result.get("message") or fallback), "ok")

    def _open_folder(self) -> None:
        opener = getattr(seed_settings, "open_pack_folder", None) if seed_settings is not None else None
        if opener is not None:
            try:
                opener(self.pack_dir)
                return
            except Exception as error:  # noqa: BLE001
                self._say(t("打不开文件夹：{error}", error=error), "error")
                return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(self.pack_dir))  # noqa: S606 - Windows 上打开资源管理器
                return
        except Exception:
            pass
        self._say(t("她的文件夹在：{pack_dir}", pack_dir=self.pack_dir), "normal")

    def _save(self) -> None:
        saver = _settings_saver()
        if saver is None:
            self._say(t("设置模块还没就绪，保存不了。"), "error")
            return
        patch = self._collect()
        try:
            saved = saver(self.pack_dir, patch)
        except Exception as error:  # noqa: BLE001 - 写不进去要说人话
            self._say(t("保存失败：{error}", error=error), "error")
            return
        if isinstance(saved, dict):
            self._settings.update(saved)
        else:
            self._settings.update(patch)
        # QQ 配置跟「保存」一起落盘；卡没建（旧后端）就安静跳过。
        try:
            if self._qq_available():
                self._qq_save(announce=bool(self._read_entry("qq_owner")))
        except Exception:
            pass
        self._say(t("已保存。下一句话就用新的设置。"), "ok")
        if self.on_saved is not None:
            try:
                self.on_saved(saved if isinstance(saved, dict) else patch)
            except Exception:
                pass

    def _test(self) -> None:
        if self._testing:
            return
        tester = getattr(seed_settings, "test_brain", None) if seed_settings is not None else None
        if tester is None:
            self._say(t("设置模块还没就绪，测试不了。"), "error")
            return
        self._testing = True
        try:
            self.test_btn.set_enabled(False)
        except Exception:
            pass
        self._say(t("正在测（真的发一次很小的请求，可能要几秒…）"), "accent")
        patch = self._collect()

        def work():
            try:
                ok, message = tester(self.pack_dir, patch)
            except Exception as error:  # noqa: BLE001 - 网络问题也要说人话
                ok, message = False, t("测试出错：{error}", error=error)
            self._queue.put((bool(ok), str(message or "")))

        threading.Thread(target=work, daemon=True).start()
        self._poll_test()

    def _poll_test(self) -> None:
        try:
            ok, message = self._queue.get_nowait()
        except queue.Empty:
            try:
                if not self.winfo_exists():
                    return
                self._after_id = self.after(100, self._poll_test)
            except Exception:
                pass
            return
        self._testing = False
        try:
            self.test_btn.set_enabled(True)
        except Exception:
            pass
        self._say(message or (t("连接正常。") if ok else t("连接失败。")), "ok" if ok else "error")

    def close(self) -> None:
        """窗口关掉时收掉还在排队的测试轮询。"""
        self._testing = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        # QQ 卡的探测轮询也要一起收掉，别留下悬空的 after。
        self._qq_testing = False
        if getattr(self, "_qq_after_id", None) is not None:
            try:
                self.after_cancel(self._qq_after_id)
            except Exception:
                pass
            self._qq_after_id = None
