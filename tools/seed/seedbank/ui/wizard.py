"""首次启动向导：欢迎、起名字、住哪、选脑、孵化。"""
import tkinter as tk
from pathlib import Path

from . import tokens as T
from ..i18n import t  # noqa: F401


def _wizard_center(window, width: int, height: int) -> None:
    """把向导摆到屏幕中间偏上一点，别顶着任务栏。"""
    try:
        window.update_idletasks()
        screen_w = int(window.winfo_screenwidth())
        screen_h = int(window.winfo_screenheight())
        x = max(0, (screen_w - int(width)) // 2)
        y = max(0, (screen_h - int(height)) // 2 - 30)
        window.geometry(f"{int(width)}x{int(height)}+{x}+{y}")
    except Exception:
        try:
            window.geometry(f"{int(width)}x{int(height)}")
        except Exception:
            pass


class SetupWizard(tk.Toplevel):
    """第一次打开 Seedbank 时的向导：起名字、选住处、选脑，然后孵出来。

    一扇 780x660 的小窗，四步都在同一扇窗里切页；孵化与本地模型探测都在
    后台线程里做，界面不会卡住。孵化成功后先把目录交给 on_done，再由
    调用方打开她的房间（这样向导关闭时窗口已经在路上了）。
    """

    WIDTH = 780
    HEIGHT = 720

    def __init__(self, master, on_done, on_cancel=None):
        super().__init__(master)
        self._on_done = on_done
        self._on_cancel = on_cancel
        self._closed = False
        self._step = 0
        self._busy = False
        self._shell_tries = 0
        self._probe_after = None
        self._hatch_after = None
        self._path_after = None
        self._shell_after = None
        self._probing = False
        self._probe_queue = queue.Queue()
        self._hatch_queue = queue.Queue()
        self._probe_results: list = []
        self._brain_mode = "stub"
        self._local_choice = None
        self._cloud_choice = None
        self._pages: list = []
        self._brain_marks: dict = {}
        self._brain_panels: dict = {}
        self._steps = (t("欢迎"), t("起名字"), t("她住在哪"), t("选一个脑"))

        # 名字与住处：名字跟着 Entry 走，住处可以换。
        self._name_var = tk.StringVar(self, value="小蓝")
        self._parent_dir = Path.home() / "fish"
        if callable(setup_default_parent):
            try:
                self._parent_dir = setup_default_parent()
            except Exception:
                pass

        self.withdraw()
        try:
            self.configure(bg=BG)
            self.title(t("Seedbank · 初次见面"))
            self.protocol("WM_DELETE_WINDOW", self._cancel)
            self.minsize(self.WIDTH, self.HEIGHT)
        except Exception:
            pass

        # 自绘标题栏（和主窗口一套）；系统标题栏随后拿掉，拿不掉就留着。
        self._titlebar = _TitleBar(self, t("初次见面"), brand="Seedbank",
                                   on_close=self._cancel, controls=False)
        self._titlebar.pack(fill="x", side="top")
        tk.Frame(self, bg=TITLEBAR_LINE, height=1).pack(fill="x", side="top")

        self._build_header()
        self._build_footer()
        self._build_pages()
        self._goto_step(0)

        self.bind("<Escape>", self._on_escape)
        self.bind("<Return>", self._on_return)
        _wizard_center(self, self.WIDTH, self.HEIGHT)
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass
        try:
            self._shell_after = self.after(60, self._install_shell)
            self._name_var.trace_add("write", self._on_name_changed)
        except Exception:
            pass
        try:
            self._path_after = self.after(120, self._update_path_label)
        except Exception:
            pass

    # —— 外壳 ——

    def _install_shell(self) -> None:
        """拿掉系统标题栏；Tk 的窗口句柄要等窗口真正露脸才有。"""
        if self._closed:
            return
        try:
            if _apply_frameless(self):
                return
        except Exception:
            return
        self._shell_tries += 1
        if self._shell_tries <= 4:
            try:
                self._shell_after = self.after(50, self._install_shell)
            except Exception:
                pass

    # —— 页头 / 页脚 ——

    def _build_header(self) -> None:
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=32, pady=(24, 0))
        left = tk.Frame(head, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        self._step_title = tk.Label(left, text="", bg=BG, fg=TEXT,
                                    font=_font(20, "bold"), anchor="w")
        self._step_title.pack(fill="x")
        self._step_sub = tk.Label(left, text="", bg=BG, fg=MUTED,
                                  font=_font(10), anchor="w", justify="left")
        self._step_sub.pack(fill="x", pady=(5, 0))
        _bind_wrap(self._step_sub, 40)
        self._step_count = tk.Label(head, text="", bg=BG, fg=FAINT,
                                    font=_font(10, family="latin"), anchor="e")
        self._step_count.pack(side="right", padx=(16, 0), pady=(4, 0))

    def _build_footer(self) -> None:
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill="x", side="bottom")
        tk.Frame(foot, bg=BORDER, height=1).pack(fill="x", side="top")
        inner = tk.Frame(foot, bg=PANEL)
        inner.pack(fill="x", padx=32, pady=(12, 14))
        self._foot_note = tk.Label(inner, text="", bg=PANEL, fg=MUTED,
                                   font=_font(10), anchor="w", justify="left")
        self._foot_note.pack(side="left", fill="x", expand=True, padx=(0, 16))
        _bind_wrap(self._foot_note, 60)
        self._next_btn = _Pill(inner, t("下一步"), self._next, bg=PANEL,
                               fill=ACCENT_SOFT, outline=ACCENT_LINE, fg=ACCENT_TXT,
                               font=_font(10, "bold"), height=34, pad_x=24)
        self._next_btn.pack(side="right")
        self._back_btn = _Pill(inner, t("上一步"), self._back, bg=PANEL,
                               fill=CARD, outline=BORDER, fg=TEXT_SOFT,
                               height=34, pad_x=18)
        self._back_btn.pack(side="right", padx=(0, 8))

    # —— 步骤容器 ——

    def _build_pages(self) -> None:
        host = tk.Frame(self, bg=BG)
        host.pack(fill="both", expand=True, padx=32, pady=(20, 12))
        for index in range(4):
            page = tk.Frame(host, bg=BG)
            self._pages.append(page)
        self._build_welcome(self._pages[0])
        self._build_name(self._pages[1])
        self._build_place(self._pages[2])
        self._build_brain(self._pages[3])

    # —— 第 1 步：欢迎 ——

    def _build_welcome(self, page) -> None:
        # 页头已经写着「欢迎来到 Seedbank」，这里只留一个安静的引子。
        hero = tk.Frame(page, bg=BG)
        hero.pack(fill="x", pady=(2, 18))
        tk.Label(hero, text="🥚", bg=BG, fg=ACCENT,
                 font=(_FONT_STATE["emoji"], 26)).pack(side="left", padx=(0, 16))
        col = tk.Frame(hero, bg=BG)
        col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text=t("她还在蛋里。"), bg=BG, fg=TEXT,
                 font=_font(13, "bold"), anchor="w").pack(fill="x")
        tk.Label(col, text=t("再过两分钟，你就能叫出她的名字。"),
                 bg=BG, fg=TEXT_SOFT, font=_font(10), anchor="w").pack(fill="x", pady=(3, 0))
        rows = (
            ("🧺", t("她的身体是一个文件夹"),
             t("孵出来以后，她的房间、照片和日记都在那一个文件夹里。")),
            ("📖", t("她的记忆是一串纯文本文件"),
             t("每说一句话、每过一天，都会写进她能读懂的文件；你也能直接看。")),
            ("🧠", t("她需要一个脑来思考"),
             t("可以先用离线模板脑，也可以接本地模型或云端 API；以后随时能改。")),
        )
        for emoji, title, desc in rows:
            row = tk.Frame(page, bg=BG)
            row.pack(fill="x", pady=(0, 16))
            tk.Label(row, text=emoji, bg=BG, fg=ACCENT,
                     font=(_FONT_STATE["emoji"], 15)).pack(side="left", padx=(0, 12))
            col = tk.Frame(row, bg=BG)
            col.pack(side="left", fill="x", expand=True)
            tk.Label(col, text=title, bg=BG, fg=TEXT, font=_font(12, "bold"),
                     anchor="w").pack(fill="x")
            tip = tk.Label(col, text=desc, bg=BG, fg=MUTED, font=_font(10),
                           anchor="w", justify="left")
            tip.pack(fill="x", pady=(3, 0))
            _bind_wrap(tip, 120)
        tk.Label(page, text=t("这些说明以后在设置页也能找到。"), bg=BG, fg=FAINT,
                 font=_font(10), anchor="w").pack(fill="x", pady=(10, 0))

    # —— 第 2 步：起名字 ——

    def _build_name(self, page) -> None:
        tk.Label(page, text=t("她的名字"), bg=BG, fg=MUTED,
                 font=_font(10), anchor="w").pack(fill="x", pady=(6, 0))
        entry = tk.Entry(
            page, textvariable=self._name_var, bg=INPUT_BG, fg=TEXT,
            insertbackground=ACCENT, relief="flat", bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT, font=_font(14),
            selectbackground=ACCENT_DEEP, selectforeground=TEXT,
        )
        entry.pack(fill="x", pady=(6, 0), ipady=10)
        self._name_entry = entry
        hint = tk.Label(page, text=t("她的名字，最多 24 个字；只影响称呼，不影响文件。"),
                        bg=BG, fg=FAINT, font=_font(10), anchor="w", justify="left")
        hint.pack(fill="x", pady=(6, 0))
        _bind_wrap(hint, 40)
        tk.Label(page, text=t("名字之后可以在文件夹里改；改了她也认得自己。"),
                 bg=BG, fg=MUTED, font=_font(10), anchor="w").pack(fill="x", pady=(26, 0))

    # —— 第 3 步：她住在哪 ——

    def _build_place(self, page) -> None:
        tk.Label(page, text=t("她的家"), bg=BG, fg=MUTED,
                 font=_font(10), anchor="w").pack(fill="x", pady=(6, 0))
        box = tk.Frame(page, bg=CARD, highlightthickness=1,
                       highlightbackground=BORDER)
        box.pack(fill="x", pady=(6, 0))
        self._path_label = tk.Label(box, text="", bg=CARD, fg=TEXT_SOFT,
                                    font=_font(12, family="latin"), anchor="w",
                                    justify="left")
        self._path_label.pack(fill="x", padx=16, pady=(14, 4))
        _bind_wrap(self._path_label, 20)
        self._place_note = tk.Label(box, text="", bg=CARD, fg=FAINT,
                                    font=_font(10), anchor="w", justify="left")
        self._place_note.pack(fill="x", padx=16, pady=(0, 16))
        _bind_wrap(self._place_note, 20)
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        _Pill(row, t("换个地方…"), self._pick_folder, bg=BG, fill=CARD,
              outline=BORDER, fg=TEXT_SOFT, height=30, pad_x=14).pack(side="left")
        tk.Label(page, text=t("以后日记、记忆、承诺都在这一个文件夹里，搬走=搬家。"),
                 bg=BG, fg=MUTED, font=_font(10), anchor="w", justify="left").pack(
            fill="x", pady=(14, 0))
        tk.Label(page, text=t("她会占几十 MB：主要是页面素材和日记。"),
                 bg=BG, fg=FAINT, font=_font(10), anchor="w").pack(fill="x", pady=(6, 0))

    # —— 第 4 步：选一个脑 ——

    def _build_brain(self, page) -> None:
        self._brain_rows = {}
        specs = (
            ("stub", t("先不接（离线 · 模板脑）"),
             t("现在就能用，说话简单一些，以后随时能改。")),
            ("local", t("本地模型（这台电脑上）"),
             t("Ollama / LM Studio / vLLM；不联网、不用 key。")),
            ("cloud", t("云端（DeepSeek / Claude / OpenAI 兼容）"),
             t("需要 API key；具体放在环境变量里。")),
        )
        for mode, title, subtitle in specs:
            row = tk.Frame(page, bg=CARD, highlightthickness=1,
                           highlightbackground=BORDER)
            row.pack(fill="x", pady=(0, 8))
            mark = tk.Label(row, text="○", bg=CARD, fg=FAINT,
                            font=_font(14, "bold", family="latin"))
            mark.pack(side="left", padx=(14, 10), pady=10)
            col = tk.Frame(row, bg=CARD)
            col.pack(side="left", fill="x", expand=True, pady=8)
            tk.Label(col, text=title, bg=CARD, fg=TEXT, font=_font(12, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(col, text=subtitle, bg=CARD, fg=MUTED, font=_font(10),
                     anchor="w", justify="left").pack(fill="x", pady=(2, 0))
            self._brain_marks[mode] = mark
            for widget in (row, mark, col) + tuple(col.winfo_children()):
                widget.bind("<Button-1>", lambda _event, m=mode: self._choose_brain(m))

        # 探测结果可能一屏放不下：详情区自己带一个滚动条。
        detail_host = _ScrollFrame(page, bg=BG, bar_width=5)
        detail_host.pack(fill="both", expand=True, pady=(4, 0))
        self._brain_detail = detail_host
        parent = detail_host.frame
        self._brain_panels["stub"] = self._build_stub_panel(parent)
        self._brain_panels["local"] = self._build_local_panel(parent)
        self._brain_panels["cloud"] = self._build_cloud_panel(parent)

    def _build_stub_panel(self, host):
        panel = tk.Frame(host, bg=BG)
        tk.Label(panel, text=t("离线模板脑：不联网、不花钱，她的回答是规则算出来的。"),
                 bg=BG, fg=MUTED, font=_font(10), anchor="w", justify="left").pack(
            fill="x", pady=(8, 0))
        tk.Label(panel, text=t("以后想接真模型，在设置页「脑」那一栏随时能换。"),
                 bg=BG, fg=FAINT, font=_font(10), anchor="w").pack(fill="x", pady=(6, 0))
        return panel

    def _build_local_panel(self, host):
        panel = tk.Frame(host, bg=BG)
        self._local_status = tk.Label(panel, text=t("正在找本机上的模型…"),
                                      bg=BG, fg=MUTED, font=_font(10), anchor="w",
                                      justify="left")
        self._local_status.pack(fill="x", pady=(6, 2))
        _bind_wrap(self._local_status, 40)
        self._local_list = tk.Frame(panel, bg=BG)
        self._local_list.pack(fill="x")
        fields = tk.Frame(panel, bg=BG)
        fields.pack(fill="x", pady=(6, 0))
        self._local_url = _field(fields, t("服务地址 base_url"), bg=BG,
                                 value="http://127.0.0.1:11434/v1",
                                 hint=t("OpenAI 兼容端点，一般以 /v1 结尾。"))
        self._local_model = _field(fields, t("模型名 model"), bg=BG, value="",
                                   hint=t("点上面的模型会自动填进来；本地不用 key。"))
        return panel

    def _build_cloud_panel(self, host):
        panel = tk.Frame(host, bg=BG)
        tk.Label(panel, text=t("选一个预设，或者填一个 OpenAI 兼容端点："),
                 bg=BG, fg=MUTED, font=_font(10), anchor="w").pack(fill="x", pady=(6, 2))
        presets = []
        for preset in _presets():
            label = t(str(preset.get("label") or ""))
            adapter = str(preset.get("adapter") or "")
            if adapter == "stub" or "本地" in label or "离线" in label:
                continue
            presets.append(dict(preset))
        self._cloud_chips = tk.Frame(panel, bg=BG)
        self._cloud_chips.pack(fill="x", pady=(2, 4))
        self._cloud_presets = presets
        self._render_cloud_presets()
        tk.Label(panel, text=t("key 只存环境变量名，不存 key 本身。"),
                 bg=BG, fg=FAINT, font=_font(10), anchor="w").pack(fill="x", pady=(2, 0))
        fields = tk.Frame(panel, bg=BG)
        fields.pack(fill="x", pady=(6, 0))
        self._cloud_base = _field(fields, t("地址 base_url"), bg=BG, value="",
                                  hint=t("Claude 官方可以留空；其它填 https://…/v1。"))
        self._cloud_model = _field(fields, t("模型 model"), bg=BG, value="")
        self._cloud_key = _field(fields, t("环境变量名 api_key_env"), bg=BG,
                                 value="DEEPSEEK_API_KEY",
                                 hint=t("把 key 放在这个环境变量里；这里只写名字。"))
        self._cloud_adapter_label = tk.Label(panel, text=t("适配器：openai-compatible"),
                                             bg=BG, fg=FAINT, font=_font(10),
                                             anchor="w")
        self._cloud_adapter_label.pack(fill="x", pady=(2, 0))
        return panel

    def _render_cloud_presets(self) -> None:
        for child in list(self._cloud_chips.winfo_children()):
            child.destroy()
        specs = []
        for preset in self._cloud_presets:
            label = t(str(preset.get("label") or ""))
            specs.append((label, lambda p=dict(preset): self._choose_preset(p)))
        specs.append((t("自定义…"), lambda: self._choose_preset(None)))
        _flow_chips(self._cloud_chips, BG, specs, font=_font(10), pad_x=11, height=26)

    # —— 步骤切换 ——

    def _goto_step(self, index: int) -> None:
        index = max(0, min(len(self._pages) - 1, int(index)))
        self._step = index
        for page in self._pages:
            page.pack_forget()
        self._pages[index].pack(fill="both", expand=True)
        titles = (
            (t("欢迎来到 Seedbank"), t("三件小事，两分钟。")),
            (t("给她起个名字"), t("名字会跟着她一辈子。")),
            (t("她住在哪"), t("一个文件夹就是她的身体。")),
            (t("给她选一个脑"), t("不接模型也能说话；以后随时能改。")),
        )
        try:
            self._step_title.configure(text=titles[index][0])
            self._step_sub.configure(text=titles[index][1])
            self._step_count.configure(text=t("第 {step} 步 / 共 4 步", step=index + 1))
        except Exception:
            pass
        self._clear_note()
        self._update_buttons()
        if index == 2:
            self._update_path_label()
        if index == 1:
            try:
                self._name_entry.focus_set()
                self._name_entry.icursor("end")
            except Exception:
                pass
        elif index == 3:
            self._choose_brain(self._brain_mode)

    def _update_buttons(self) -> None:
        last = self._step >= len(self._pages) - 1
        try:
            self._next_btn.set_text(t("正在孵…") if self._busy else (t("开始孵化") if last else t("下一步")))
            self._next_btn.set_enabled(not self._busy)
            self._back_btn.set_enabled(not self._busy)
            if self._step <= 0:
                self._back_btn.pack_forget()
            else:
                if not self._back_btn.winfo_manager():
                    self._back_btn.pack(side="right", padx=(0, 8))
        except Exception:
            pass

    # —— 页脚提示 ——

    def _set_note(self, text: str, tone: str = "muted") -> None:
        colors = {"muted": MUTED, "error": ERROR, "ok": OK, "accent": ACCENT}
        try:
            self._foot_note.configure(text=str(text or ""), fg=colors.get(tone, MUTED))
        except Exception:
            pass

    def _clear_note(self) -> None:
        self._set_note("", "muted")

    def _show_error(self, text: str) -> None:
        self._set_note(text, "error")

    # —— 交互 ——

    def _on_escape(self, _event=None):
        self._cancel()
        return "break"

    def _on_return(self, _event=None):
        if not self._busy:
            self._next()
        return "break"

    def _on_name_changed(self, *_args) -> None:
        if self._step == 2:
            self._update_path_label()

    def _name_value(self) -> str:
        try:
            return str(self._name_var.get() or "").strip()
        except Exception:
            return ""

    def _target_path(self):
        name = self._name_value()
        if not name:
            return None
        if callable(setup_clean_name):
            try:
                name = setup_clean_name(name)
            except SeedError:
                return None
            except Exception:
                pass
        return Path(self._parent_dir) / f"{name}.life"

    def _update_path_label(self) -> None:
        if self._closed:
            return
        target = self._target_path()
        name = self._name_value()
        if target is None:
            try:
                self._path_label.configure(text=t("{name}.life（名字还没定）", name=name or t("她")),
                                           fg=FAINT)
                self._place_note.configure(text=t("想好名字，这里就会变成她的文件夹。"))
            except Exception:
                pass
            return
        try:
            self._path_label.configure(text=str(target), fg=TEXT_SOFT)
            self._place_note.configure(text=t("会在 {parent} 里孵出一颗蛋。", parent=Path(target).parent))
        except Exception:
            pass

    def _pick_folder(self) -> None:
        if filedialog is None:
            self._show_error(t("这台电脑上的文件选择器不可用，可以直接用默认位置。"))
            return
        try:
            chosen = filedialog.askdirectory(
                parent=self, title=t("她住在哪（选一个文件夹）"),
                initialdir=str(self._parent_dir), mustexist=False,
            )
        except Exception as error:
            self._show_error(t("没能打开文件夹选择器：{error}", error=error))
            return
        if not chosen:
            return
        try:
            self._parent_dir = Path(chosen)
        except Exception:
            return
        self._update_path_label()

    def _next(self) -> None:
        if self._busy or self._closed:
            return
        step = self._step
        if step == 1:
            if callable(setup_clean_name):
                try:
                    setup_clean_name(self._name_value())
                except SeedError as error:
                    self._show_error(str(error))
                    return
                except Exception:
                    pass
            elif not self._name_value():
                self._show_error(t("她的名字不能是空的。"))
                return
            self._goto_step(2)
            return
        if step == 2:
            target = self._target_path()
            if target is None:
                self._show_error(t("先给她起一个能用的名字。"))
                self._goto_step(1)
                return
            if target.exists():
                self._show_error(t("这里已经有一条叫「{replace}」的鱼了：{target}", replace=target.stem.replace('.life', ''), target=target))
                return
            self._goto_step(3)
            return
        if step >= 3:
            self._hatch()
            return
        self._goto_step(step + 1)

    def _back(self) -> None:
        if self._busy or self._closed:
            return
        self._goto_step(self._step - 1)

    # —— 选脑 ——

    def _choose_brain(self, mode: str) -> None:
        if mode not in ("stub", "local", "cloud"):
            mode = "stub"
        self._brain_mode = mode
        for key, mark in self._brain_marks.items():
            try:
                mark.configure(text="◉" if key == mode else "○",
                               fg=ACCENT if key == mode else FAINT)
            except Exception:
                pass
        for key, panel in self._brain_panels.items():
            panel.pack_forget()
        try:
            self._brain_panels[mode].pack(fill="both", expand=True)
        except Exception:
            pass
        if mode == "local":
            if not self._probe_results and not self._probing:
                self._start_probe()
        if mode == "cloud" and not self._cloud_choice:
            presets = getattr(self, "_cloud_presets", [])
            if presets:
                self._choose_preset(presets[0])

    def _choose_preset(self, preset) -> None:
        if preset:
            self._cloud_choice = dict(preset)
            adapter = str(preset.get("adapter") or "openai-compatible")
            try:
                self._cloud_adapter_label.configure(text=t("适配器：{adapter}", adapter=adapter))
            except Exception:
                pass
            values = {
                "base": preset.get("base_url") or "",
                "model": preset.get("model") or "",
                "key": preset.get("api_key_env") or "",
            }
        else:
            self._cloud_choice = {"adapter": "openai-compatible", "custom": True}
            try:
                self._cloud_adapter_label.configure(text=t("适配器：openai-compatible"))
            except Exception:
                pass
            values = {"base": "", "model": "", "key": "DEEPSEEK_API_KEY"}
        for entry, key in ((self._cloud_base, "base"), (self._cloud_model, "model"),
                           (self._cloud_key, "key")):
            try:
                entry.delete(0, "end")
                entry.insert(0, str(values[key]))
            except Exception:
                pass

    def _choose_local(self, result: dict, model: str) -> None:
        self._local_choice = {"result": dict(result or {}), "model": str(model)}
        base = str((result or {}).get("base_url") or "")
        try:
            self._local_url.delete(0, "end")
            self._local_url.insert(0, base)
            self._local_model.delete(0, "end")
            self._local_model.insert(0, str(model))
        except Exception:
            pass
        label = str((result or {}).get("label") or t("本地模型"))
        self._set_note(t("选好了：{label} 的 {model}", label=label, model=model), "ok")

    # —— 本地模型探测 ——

    def _start_probe(self) -> None:
        if self._probing or self._closed:
            return
        if seed_localmodels is None:
            try:
                self._local_status.configure(text=t("本机模型探测还没就绪，可以直接手填地址和模型名。"))
            except Exception:
                pass
            return
        self._probing = True
        try:
            self._local_status.configure(text=t("正在找本机上的模型…"))
        except Exception:
            pass

        def work():
            try:
                results = seed_localmodels.discover(timeout=1.2)
            except Exception:
                results = []
            try:
                self._probe_queue.put(results if isinstance(results, list) else [])
            except Exception:
                pass

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            self._probing = False
            return
        self._poll_probe()

    def _poll_probe(self) -> None:
        self._probe_after = None
        if self._closed:
            return
        try:
            results = self._probe_queue.get_nowait()
        except queue.Empty:
            try:
                self._probe_after = self.after(120, self._poll_probe)
            except Exception:
                pass
            return
        self._probing = False
        self._probe_results = list(results or [])
        self._render_local_results()

    def _render_local_results(self) -> None:
        try:
            for child in list(self._local_list.winfo_children()):
                child.destroy()
        except Exception:
            return
        results = self._probe_results
        if not results:
            try:
                self._local_status.configure(
                    text=t("这台电脑上还没发现本地模型（试过 Ollama / LM Studio / vLLM / llama.cpp）。也可以直接手填地址和模型名。"))
            except Exception:
                pass
            return
        total = sum(len(row.get("models") or []) for row in results)
        try:
            self._local_status.configure(text=t("发现了 {total} 个本地模型，点一个试试：", total=total))
        except Exception:
            pass
        for result in results:
            label = str(result.get("label") or t("本地服务"))
            head = tk.Label(self._local_list, text=f"{label} · {result.get('base_url') or ''}",
                            bg=BG, fg=FAINT, font=_font(10, family="latin"), anchor="w")
            head.pack(fill="x", pady=(4, 2))
            chips = tk.Frame(self._local_list, bg=BG)
            chips.pack(fill="x")
            for model in list(result.get("models") or [])[:8]:
                text = str(model)
                _Pill(chips, text, lambda r=dict(result), m=text: self._choose_local(r, m),
                      bg=BG, fill=ACCENT_SOFT, outline=ACCENT_LINE, fg=ACCENT_TXT,
                      font=_font(10, family="latin"), pad_x=10, height=24).pack(
                    side="left", padx=(0, 6), pady=(0, 4))

    # —— 孵化 ——

    def _collect_brain(self) -> dict:
        mode = self._brain_mode
        if mode == "local":
            base = ""
            model = ""
            try:
                base = str(self._local_url.get() or "").strip()
                model = str(self._local_model.get() or "").strip()
            except Exception:
                pass
            if not base or not model:
                raise SeedError(t("本地模型要填服务地址和模型名。"))
            if seed_localmodels is not None:
                try:
                    base = seed_localmodels.normalize_base_url(base)
                except SeedError:
                    raise
                except Exception:
                    pass
            return {"adapter": "openai-compatible", "base_url": base,
                    "model": model, "api_key_env": ""}
        if mode == "cloud":
            preset = dict(self._cloud_choice or {"adapter": "openai-compatible", "custom": True})
            adapter = str(preset.get("adapter") or "openai-compatible")
            if preset.get("custom"):
                try:
                    base = str(self._cloud_base.get() or "").strip()
                    model = str(self._cloud_model.get() or "").strip()
                    key = str(self._cloud_key.get() or "").strip()
                except Exception:
                    base = model = key = ""
                if not model:
                    raise SeedError(t("云端模型至少要有模型名。"))
                if not base and adapter != "anthropic":
                    raise SeedError(t("云端模型要有地址 base_url。"))
                return {"adapter": "openai-compatible", "base_url": base or None,
                        "model": model, "api_key_env": key or "SEEDBANK_API_KEY"}
            return {"adapter": adapter, "base_url": preset.get("base_url"),
                    "model": preset.get("model"), "api_key_env": preset.get("api_key_env")}
        return {"adapter": "stub", "model": None, "base_url": None,
                "api_key_env": "SEEDBANK_API_KEY"}

    def _hatch(self) -> None:
        if self._busy or self._closed:
            return
        if not callable(setup_create_fish):
            self._show_error(t("孵化模块还没就绪：请检查安装是否完整。"))
            return
        name = self._name_value()
        try:
            if callable(setup_clean_name):
                name = setup_clean_name(name)
        except SeedError as error:
            self._show_error(str(error))
            return
        except Exception:
            pass
        try:
            brain = self._collect_brain()
        except SeedError as error:
            self._show_error(str(error))
            return
        target = self._target_path()
        if target is not None and target.exists():
            self._show_error(t("这里已经有一条叫「{replace}」的鱼了：{target}", replace=target.stem.replace('.life', ''), target=target))
            return
        parent = str(self._parent_dir)
        self._busy = True
        self._update_buttons()
        self._set_note(t("正在孵一颗蛋…这一步要几秒。"), "accent")

        def work():
            try:
                pack = setup_create_fish(name, parent, brain=brain)
                self._hatch_queue.put(("ok", pack))
            except SeedError as error:
                self._hatch_queue.put(("error", str(error)))
            except Exception as error:  # noqa: BLE001 - 失败也要说人话
                self._hatch_queue.put(("error", t("孵化失败：{error}", error=error)))

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as error:
            self._busy = False
            self._update_buttons()
            self._show_error(t("起不了孵化线程：{error}", error=error))
            return
        self._poll_hatch()

    def _poll_hatch(self) -> None:
        self._hatch_after = None
        if self._closed:
            return
        try:
            status, payload = self._hatch_queue.get_nowait()
        except queue.Empty:
            try:
                self._hatch_after = self.after(120, self._poll_hatch)
            except Exception:
                pass
            return
        self._busy = False
        if status == "ok":
            self._finish(payload)
            return
        self._update_buttons()
        self._show_error(str(payload or t("孵化失败。")))

    def _finish(self, pack) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_after()
        try:
            self.destroy()
        except Exception:
            pass
        if callable(self._on_done):
            try:
                self._on_done(Path(pack))
            except Exception:
                pass

    # —— 关闭 ——

    def _cancel_after(self) -> None:
        for name in ("_probe_after", "_hatch_after", "_path_after", "_shell_after"):
            handle = getattr(self, name, None)
            if handle:
                try:
                    self.after_cancel(handle)
                except Exception:
                    pass
                setattr(self, name, None)
    def _cancel(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_after()
        callback = self._on_cancel
        try:
            self.destroy()
        except Exception:
            pass
        if callable(callback):
            try:
                callback()
            except Exception:
                pass

    def close(self) -> None:
        self._cancel()

    def destroy(self) -> None:
        self._closed = True
        self._cancel_after()
        try:
            super().destroy()
        except Exception:
            pass
