"""聊天页：气泡、日记卡、输入区、对话与一天的动作。"""
import tkinter as tk

from .. import tokens as T  # noqa: F401  (运行期命名空间会由 window 绑定)


class ChatPageMixin:

    def _build_chat_page(self) -> None:
        page = tk.Frame(self.page_host, bg=PANEL)
        self.pages["chat"] = page
        self._build_composer(page)
        self._build_status(page)
        self.body = _ScrollFrame(page, bg=PANEL, max_content_width=T.CONTENT_MAX, backdrop=True)
        self.body.pack(fill="both", expand=True)
        self.body.frame.bind("<Configure>", self._on_body_resize, add="+")
    def _build_composer(self, parent) -> None:
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x", side="bottom")
        inner = tk.Frame(wrap, bg=PANEL)
        self._composer_inner = inner
        inner.pack(fill="x", padx=28, pady=(12, 18))
        try:
            parent.bind("<Configure>", self._on_composer_resize, add="+")
        except Exception:
            pass

        self.input = _InputBox(inner, bg=PANEL, font=_font(13))
        self.input.pack(fill="x")
        self.input.set_placeholder(t("对她说什么…"))
        self.input.text.bind("<Return>", self._on_return)
        self.input.text.bind("<Shift-Return>", self._on_shift_return)
        self.input.text.bind("<KeyRelease>", self._on_key_release)

        row = tk.Frame(inner, bg=PANEL)
        row.pack(fill="x", pady=(10, 0))
        action_h = T.ACTION_H
        self.day_btn = _Pill(row, t("🌙  陪她过一天"), self._advance_day, bg=PANEL, fill=CARD,
                             hover=CARD_HI, fg=TEXT_SOFT, font=_font(11), pad_x=18,
                             height=action_h, radius=action_h // 2)
        self.day_btn.pack(side="left")
        self.photo_btn = _Pill(row, t("📷  给她看照片"), self._send_photo, bg=PANEL, fill=CARD,
                               hover=CARD_HI, fg=TEXT_SOFT, font=_font(11), pad_x=18,
                               height=action_h, radius=action_h // 2)
        self.photo_btn.pack(side="left", padx=(10, 0))
        self.send_btn = _RoundButton(row, self._send, bg=PANEL, size=T.SEND_BTN)
        self.send_btn.pack(side="right")
    def _on_composer_resize(self, event=None) -> None:
        """输入区和动作栏跟聊天正文同宽（880），大窗口里居中。"""
        try:
            width = int(getattr(event, "width", 0) or self.page_host.winfo_width())
            inner = getattr(self, "_composer_inner", None)
            if width <= 1 or inner is None:
                return
            pad = max(28, (width - T.CONTENT_MAX) // 2)
            inner.pack_configure(padx=pad)
        except Exception:
            pass

    def _build_status(self, parent) -> None:
        self.status = tk.Label(parent, text="", bg=PANEL, fg=MUTED, font=_font(10), anchor="w")
        self.status.pack(fill="x", side="bottom", padx=26, pady=(0, 6))
        self._set_status(t("关掉这扇窗，她就停下 · 记忆在她的文件夹里"))
        try:
            parent.bind("<Configure>", self._on_chat_page_resize, add="+")
        except Exception:
            pass

    def _on_chat_page_resize(self, event=None) -> None:
        """窗口矮的时候把底部那行提示收起来，输入区和按钮永远完整。"""
        try:
            height = int(getattr(event, "height", 0) or self.status.master.winfo_height())
        except Exception:
            return
        if height <= 1:
            return
        try:
            if height < 560:
                self.status.pack_forget()
            elif not self.status.winfo_manager():
                self.status.pack(fill="x", side="bottom", padx=26, pady=(0, 6))
        except Exception:
            pass
    def _on_body_resize(self, event) -> None:
        width = int(getattr(event, "width", 0) or 0)
        if width < 140 or abs(width - self._body_width) < 10:
            return
        self._body_width = width
        max_width = self._bubble_max_width()
        for bubble in list(self._bubbles):
            try:
                bubble.set_max_width(max_width)
            except Exception:
                pass
        # 窗口变窄后气泡会换行、内容变高；聊天页本来就该停在最新一句上。
        if self._page_name == "chat":
            try:
                self.root.after_idle(self.body.scroll_to_end)
            except Exception:
                pass
    def _bubble_max_width(self) -> int:
        width = self._body_width
        if width < 140:
            try:
                width = int(self.body.frame.winfo_width())
            except Exception:
                width = 0
        if width < 140:
            width = 600
        return max(200, min(620, int(width * 0.78)))
    def _load_history(self) -> None:
        self._snapshot()
        self._refresh_meta()
        days = list_days(str(self.pack_dir))
        recent = days[-7:]
        if not recent:
            self._add_note(t("她的文件夹里还没有任何一天。"))
            return
        placeholder = False
        for index, day in enumerate(recent):
            parsed = _parse_day(str(self.pack_dir), day)
            news = _parse_news(self.pack_dir, day)
            self._add_day_divider(day["day"], day["date"])
            for turn in parsed["convo"]:
                self._add_turn(turn["who"], turn["text"])
            for line in parsed["senses"]:
                self._add_sense(line)
            for line in news:
                self._add_news(line)
            if parsed["diary"] and (index == len(recent) - 1 or not parsed["convo"]):
                self._add_diary(day["day"], parsed["diary"])
            if not (parsed["convo"] or parsed["senses"] or news or parsed["diary"]):
                placeholder = True
        if placeholder:
            self._add_note(t("今天还没有人跟她说话。"))
        try:
            self.root.after_idle(self._scroll_to_latest_day)
        except Exception:
            pass
    def _reload_chat(self) -> None:
        """按磁盘上的历史重画聊天页；只有外面写入了新对话、见闻或感知时才用。"""

        frame = getattr(self, "body", None)
        if frame is None or not hasattr(frame, "frame"):
            return
        try:
            for child in frame.frame.winfo_children():
                child.destroy()
        except Exception:
            pass
        self._bubbles = []
        try:
            self._load_history()
        except Exception:
            pass
        try:
            self.body.scroll_to_end()
        except Exception:
            pass
    def _add_day_divider(self, day_no, date) -> None:
        """一天的开头：两条细线把一枚日期胶囊夹在中间，安静地翻页。"""
        row = tk.Frame(self.body.frame, bg=self.body.frame.cget("bg"))
        row.pack(fill="x", padx=44, pady=(22, 12))
        tk.Frame(row, bg=SIDEBAR_LINE, height=1).pack(side="left", fill="x", expand=True)
        chip = _Pill(row, day_caption(day_no, date), None, bg=row.cget("bg"), fill=PANEL,
                     outline=BORDER, fg=MUTED, font=_font(10), pad_x=14, height=30,
                     radius=12, anchor="center")
        chip.pack(side="left", padx=12)
        tk.Frame(row, bg=SIDEBAR_LINE, height=1).pack(side="left", fill="x", expand=True)
        self._last_day_row = row
        self.body.scroll_to_end()

    def _scroll_to_latest_day(self) -> None:
        """打开聊天页时停在最新一天的日分隔上，别让顶部露出半条旧气泡。"""
        row = getattr(self, "_last_day_row", None)
        frame = getattr(getattr(self, "body", None), "frame", None)
        canvas = getattr(getattr(self, "body", None), "canvas", None)
        if row is None or frame is None or canvas is None:
            try:
                self.body.scroll_to_end()
            except Exception:
                pass
            return
        try:
            canvas.update_idletasks()
            total = max(1, frame.winfo_height())
            view = max(1, canvas.winfo_height())
            offset = row.winfo_y() - 8
            if offset <= 0:
                self.body.scroll_to_end()
                return
            # 最新一天如果太短，滚动到底也顶不到视口顶部；
            # 在列表尾部垫一段空白，让“最新一天的分隔”能停在顶部。
            needed = max(0, offset + view - total)
            pad = getattr(self, "_chat_bottom_pad", None)
            if needed > 0 or pad is not None:
                if pad is None or not pad.winfo_exists():
                    pad = tk.Frame(frame, bg=frame.cget("bg"))
                    pad.pack(fill="x")
                    self._chat_bottom_pad = pad
                pad.configure(height=needed)
                canvas.update_idletasks()
                total = max(1, frame.winfo_height())
            canvas.yview_moveto(min(1.0, offset / total))
        except Exception:
            try:
                self.body.scroll_to_end()
            except Exception:
                pass

    def _add_turn(self, who, text) -> None:
        speaker = str(who or "").strip()
        # 落款是「名字（主动）」时，把这份主动记在气泡上，名字本身照旧。
        initiated = False
        # 这个后缀是写进她日记里的数据，不翻译；只在渲染时剥掉。
        for marker in ("（主动）", "(主动)"):
            if speaker.endswith(marker):
                speaker = speaker[: -len(marker)].strip()
                initiated = True
                break
        if speaker in ("主人", "owner", "me", "我"):
            self._add_bubble("me", text)
        elif speaker in ("fish", self.name):
            self._add_bubble("her", text, initiated=initiated)
        else:
            self._add_bubble("guest", text, caption=t("访客 {speaker}", speaker=speaker))
    def _add_bubble(self, kind: str, text, caption: str = "", initiated: bool = False) -> None:
        if caption:
            cap = tk.Label(self.body.frame, text=caption, bg=PANEL, fg=FAINT,
                           font=_font(10), anchor="w")
            cap.pack(fill="x", padx=30, pady=(8, 0))
        row = tk.Frame(self.body.frame, bg=PANEL)
        if kind == "me":
            row.pack(fill="x", padx=(100, 48), pady=7)
        else:
            row.pack(fill="x", padx=(48, 116), pady=7)
        styles = {
            "her": dict(fill=HER_BUBBLE, outline=HER_BUBBLE_LINE, fg=TEXT),
            "me": dict(fill=ACCENT_DEEP, outline=ACCENT_LINE, fg=ACCENT_TXT),
            "guest": dict(fill=GUEST_BG, outline=GUEST_LINE, fg=GUEST_FG),
        }
        style = styles.get(kind, styles["her"])
        if kind == "her" and initiated:
            # 她自己先开口的那几句：气泡右上角挑一枚小小的夜光标签，
            # 不改变气泡本身的形状，免得看起来像另一种人说的话。
            holder = tk.Frame(row, bg=PANEL)
            holder.pack(side="left")
            chip = tk.Label(holder, text=t("主动开口"), bg=ACCENT_SOFT, fg=ACCENT,
                            font=_font(10), padx=9, pady=1)
            chip.pack(anchor="e", pady=(0, 3))
            bubble = _Bubble(holder, text, font=_font(13), max_width=self._bubble_max_width(),
                             **style)
            bubble.pack(anchor="w")
        else:
            bubble = _Bubble(row, text, font=_font(12), max_width=self._bubble_max_width(),
                             **style)
            bubble.pack(side="right" if kind == "me" else "left")
        self._bubbles.append(bubble)
        self.body.scroll_to_end()
    def _add_sense(self, line) -> None:
        """感官行：前面的 ✦ 和字之间留一点呼吸，整行往她的气泡那边缩进。"""
        row = tk.Frame(self.body.frame, bg=PANEL)
        row.pack(fill="x", padx=(52, 46), pady=4)
        tk.Label(row, text="✦", bg=PANEL, fg=SENSE,
                 font=_font(10)).pack(side="left", pady=(1, 0))
        label = tk.Label(row, text=str(line), bg=PANEL, fg=SENSE,
                         font=_font(10, slant="italic"), justify="left", anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(7, 0))
        _bind_wrap(label, 0)
        self.body.scroll_to_end()
    def _add_news(self, line) -> None:
        """见闻行：她「读到」的摘要，比感官更安静——小一号、灰蓝、前缀「读 ·」。"""
        row = tk.Frame(self.body.frame, bg=PANEL)
        row.pack(fill="x", padx=(52, 46), pady=3)
        tk.Label(row, text=t("读 ·"), bg=PANEL, fg=ACCENT,
                 font=_font(10)).pack(side="left", pady=(1, 0))
        label = tk.Label(row, text=str(line), bg=PANEL, fg=MUTED,
                         font=_font(10), justify="left", anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(5, 0))
        _bind_wrap(label, 0)
        self.body.scroll_to_end()
    def _add_diary(self, day_no, paragraphs) -> None:
        text = "\n\n".join(str(paragraph) for paragraph in paragraphs).strip()
        if not text:
            return
        try:
            number = int(day_no)
        except (TypeError, ValueError):
            number = 0
        card = _Card(self.body.frame, bg=PANEL, fill=DIARY_BG, outline=DIARY_LINE,
                     accent=ACCENT, radius=18, inset=18)
        card.pack(fill="x", padx=(22, 24), pady=(10, 14))
        head = tk.Frame(card.inner, bg=DIARY_BG)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="📖", bg=DIARY_BG, fg=ACCENT,
                 font=(_FONT_STATE["emoji"], 10)).pack(side="left")
        tk.Label(head, text=t("第 {number} 天 · 她写下", number=number), bg=DIARY_BG, fg=ACCENT,
                 font=_font(10, "bold")).pack(side="left", padx=(7, 0))
        body = tk.Label(card.inner, text=text, bg=DIARY_BG, fg=TEXT_SOFT, font=_font(12),
                        justify="left", anchor="w")
        body.pack(fill="x")
        _bind_wrap(body, 12)
        self.body.scroll_to_end()
    def _add_note(self, text: str) -> None:
        label = tk.Label(self.body.frame, text=str(text), bg=PANEL, fg=FAINT,
                         font=_font(10), justify="center", anchor="center")
        label.pack(fill="x", padx=(44, 44), pady=10)
        _bind_wrap(label, 40)
        self.body.scroll_to_end()
    def _set_status(self, text: str, tone: str = "normal") -> None:
        color = {"error": ERROR, "ok": OK, "accent": ACCENT, "warning": SENSE}.get(tone, MUTED)
        try:
            self.status.configure(text=str(text), fg=color)
        except Exception:
            pass
    def _busy_writing(self) -> bool:
        """有没有一件事正占着生命包的写权限（同一个包同一时间只该有一个写者）。"""
        return bool(
            self._busy
            or getattr(self, "_initiating", False)
            or getattr(self, "_processing_events", False)
        )
    def _set_busy(self, busy: bool, hint: str = "") -> None:
        self._busy = bool(busy)
        for widget in (self.send_btn, self.day_btn, self.photo_btn):
            try:
                widget.set_enabled(not busy)
            except Exception:
                pass
        if hint:
            self._set_status(hint)
    def _on_return(self, _event=None):
        self._send()
        return "break"
    def _on_shift_return(self, _event=None):
        # 让 Text 的默认行为换行，不要拦
        return None
    def _on_key_release(self, _event=None) -> None:
        self._resize_input()
        self.input.sync_placeholder()
        try:
            self.pet.wake()
        except Exception:
            pass
    def _resize_input(self) -> None:
        try:
            counted = self.input.text.count("1.0", "end-1c", "displaylines")
            lines = int(counted[0] or 0) if counted else 0
        except Exception:
            lines = 0
        lines = max(2, min(6, lines or 1))
        if lines == self._input_lines:
            return
        self._input_lines = lines
        try:
            self.input.text.configure(height=lines)
        except Exception:
            return
        self.input.fit()
    def _reset_input(self) -> None:
        self._input_lines = 2
        try:
            self.input.text.configure(height=2)
        except Exception:
            pass
        self.input.fit()
        self.input.sync_placeholder()
    def _send(self) -> None:
        text = self.input.get_text().strip()
        if not text:
            return
        if self._busy_writing():
            self._set_status(t("她还在忙上一件事，等一下她。"))
            return
        self.input.clear()
        self._reset_input()
        self._add_bubble("me", text)
        self._set_busy(True, t("她正在想…"))
        try:
            self.pet.happy()
        except Exception:
            pass
        pack = str(self.pack_dir)
        # speaker 会写进她的日记，是数据不是界面文案，保持中文原样。
        self._run(lambda: chat_turn(pack, text, self.brain, speaker="主人"), self._on_chat)
    def _on_chat(self, result) -> None:
        self._set_busy(False)
        self._add_bubble("her", result.get("reply") or t("（她沉默了一会儿。）"))
        added = int(result.get("memoriesAdded") or 0)
        self._set_status(t("她记下了 {added} 条记忆。", added=added) if added else t("她回了一句。"), "ok" if added else "normal")
        self._refresh()
        # 回上话了，开心一小会儿。
        try:
            self.pet.happy()
        except Exception:
            pass
    def _advance_day(self) -> None:
        if self._busy_writing():
            return
        self._set_busy(True, t("她在过这一天…"))
        pack = str(self.pack_dir)
        self._run(lambda: run_days(pack, days=1, brain=self.brain), self._on_day)
    def _on_day(self, result) -> None:
        self._set_busy(False)
        self._refresh()
        for info in result.get("days") or []:
            try:
                parsed = _parse_day(str(self.pack_dir), {
                    "day": info["day"], "date": info["date"], "file": info["file"],
                })
            except (OSError, KeyError, TypeError):
                continue
            self._add_day_divider(info["day"], info["date"])
            if parsed["diary"]:
                self._add_diary(info["day"], parsed["diary"])
        self._set_status(t("她又过了一天，现在是第 {day} 天。", day=self._day_no), "ok")
        # 过完一整天，值得跳一小段。
        try:
            self.pet.celebrate()
        except Exception:
            pass
    def _send_photo(self) -> None:
        if self._busy_writing() or filedialog is None:
            return
        path = filedialog.askopenfilename(
            title=t("给{name}看一张照片", name=self.name),
            filetypes=[(t("图片"), "*.png *.jpg *.jpeg *.bmp *.ppm *.pgm"), (t("所有文件"), "*.*")],
        )
        if not path:
            return
        self._set_busy(True, t("她正在看着这张照片…"))
        pack = str(self.pack_dir)
        self._run(lambda: sense_media(pack, image=path, note="主人给你看样东西"), self._on_photo)
    def _on_photo(self, result) -> None:
        self._set_busy(False)
        for line in result.get("lines") or []:
            self._add_sense(line)
        self._set_status(t("她看到了光，记在了今天里。"), "ok")
        self._refresh()
        try:
            self.pet.happy()
        except Exception:
            pass


