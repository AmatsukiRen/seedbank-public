"""记忆页：搜索、按天分组、忘记一条。"""
import tkinter as tk

from .. import tokens as T  # noqa: F401


class MemoryPageMixin:

    def _build_memory_page(self) -> None:
        """记忆页：一条搜索框 + 按天倒序的记忆卡片。"""
        page = tk.Frame(self.page_host, bg=PANEL)
        self.pages["memory"] = page
        self.memory_search = _InputBox(page, bg=PANEL, font=_font(12), lines=1)
        self.memory_search.pack(fill="x", padx=22, pady=(16, 0))
        self.memory_search.set_placeholder(t("搜一段记忆…"))
        try:
            self.memory_search.text.bind("<KeyRelease>", self._on_memory_search)
            self.memory_search.text.bind("<Return>", lambda _event: "break")
        except Exception:  # pragma: no cover - 输入框异常不该拦着建页
            pass
        bar = tk.Frame(page, bg=PANEL)
        bar.pack(fill="x", padx=24, pady=(8, 2))
        self.memory_hint = tk.Label(bar, text="", bg=PANEL, fg=FAINT, font=_font(10),
                                    anchor="w")
        self.memory_hint.pack(side="left")
        self.memory_note = tk.Label(bar, text="", bg=PANEL, fg=FAINT, font=_font(10),
                                    anchor="e", justify="right")
        self.memory_note.pack(side="right")
        _bind_wrap(self.memory_note, 220)
        self.memory_scroll = _ScrollFrame(page, bg=PANEL, backdrop=True)
        self.memory_scroll.pack(fill="both", expand=True)
    def _load_memories(self) -> list:
        """读记忆：优先后端 list_memories；后端没就绪就退回直接读文件。"""
        if list_memories is not None:
            try:
                entries = list_memories(str(self.pack_dir))
            except Exception:  # noqa: BLE001 - 后端出错不该让窗口打不开
                entries = None
            if isinstance(entries, list):
                return [dict(item) for item in entries if isinstance(item, dict)]
        try:
            raw = read_memories(str(self.pack_dir))
        except (OSError, ValueError):
            return []
        entries = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            memory = dict(item)
            memory.setdefault("forgotten", False)
            entries.append(memory)
        return entries
    def _memory_stats(self) -> tuple:
        """(记得的条数, 已忘记的条数)；墓碑本身不算「记得」。"""
        entries = [item for item in getattr(self, "_memory_entries", [])
                   if isinstance(item, dict)]
        forgotten = sum(1 for item in entries if item.get("forgotten"))
        kept = sum(1 for item in entries
                   if not item.get("forgotten")
                   and str(item.get("kind") or "") != "forget")
        return kept, forgotten
    def _memory_day_dates(self) -> dict:
        """day 号 → 那天的日期，给分隔行用。"""
        dates: dict = {}
        try:
            days = list_days(str(self.pack_dir))
        except Exception:  # noqa: BLE001 - 日期读不出来就只显示第几天
            return dates
        for day in days:
            try:
                dates[int(day.get("day"))] = str(day.get("date") or "")
            except (TypeError, ValueError):
                continue
        return dates
    def _memory_query(self) -> str:
        try:
            return str(self.memory_search.get_text() or "").strip().lower()
        except Exception:
            return ""
    def _filtered_memories(self) -> list:
        """没被忘记、且与搜索词相符的记忆（时间正序，交给渲染分天倒排）。"""
        query = self._memory_query()
        picked = []
        for memory in getattr(self, "_memory_entries", []):
            if not isinstance(memory, dict) or memory.get("forgotten"):
                continue
            if str(memory.get("kind") or "") == "forget":
                continue  # 墓碑是「忘记」这件事的凭证，不再当成可忘的记忆展示
            if not query:
                picked.append(memory)
                continue
            tags = " ".join(str(tag) for tag in (memory.get("tags") or []))
            hay = " ".join((str(memory.get("text") or ""), tags,
                            str(memory.get("kind") or ""))).lower()
            if query in hay:
                picked.append(memory)
        return picked
    def _refresh_memory(self) -> None:
        """重画记忆页：读一遍后端、刷页头、再画卡片。"""
        self._snapshot()
        self._refresh_meta()
        self._render_memory()
    def _render_memory(self, keep_scroll: bool = False) -> None:
        frame = self.memory_scroll.frame
        try:
            first = float(self.memory_scroll.canvas.yview()[0])
        except Exception:
            first = 0.0
        for child in frame.winfo_children():
            child.destroy()
        entries = self._filtered_memories()
        query = self._memory_query()
        self._set_memory_hint(t("搜到 {count} 条", count=len(entries)) if query
                              else t("按时间倒序 · 最新的在最上面"))
        if list_memories is None:
            self._set_memory_note(t("记忆后端还没接上：先按文件里的旧记录显示。"), "muted")
        else:
            self._set_memory_note("", "muted")
        if not entries:
            self._add_memory_empty(frame, query)
        else:
            dates = self._memory_day_dates()
            grouped: dict = {}
            for memory in entries:
                try:
                    day_no = int(memory.get("day") or 0)
                except (TypeError, ValueError):
                    day_no = 0
                grouped.setdefault(day_no, []).append(memory)
            for day_no in sorted(grouped, reverse=True):
                self._add_memory_day(frame, day_no, dates.get(day_no, ""))
                for memory in grouped[day_no]:
                    self._add_memory_card(frame, memory)
        try:
            self.memory_scroll.canvas.update_idletasks()
            self.memory_scroll.canvas.yview_moveto(first if keep_scroll else 0.0)
        except Exception:
            pass
    def _add_memory_day(self, parent, day_no: int, date: str) -> None:
        head = tk.Frame(parent, bg=PANEL)
        head.pack(fill="x", padx=24, pady=(20, 10))
        tk.Label(head, text=day_caption(day_no, date), bg=PANEL, fg=TEXT_SOFT,
                 font=_font(12, "bold"), anchor="w").pack(side="left")
    def _add_memory_card(self, parent, memory: dict) -> None:
        card = _Card(parent, bg=PANEL, fill=CARD, outline=BORDER, accent=ACCENT_SOFT,
                     radius=18, inset=18)
        card.pack(fill="x", padx=22, pady=(0, 10))
        box = card.inner
        text = str(memory.get("text") or "").strip() or t("（这条记忆没有留下字。）")
        body = tk.Label(box, text=text, bg=CARD, fg=TEXT_SOFT, font=_font(12),
                        justify="left", anchor="w")
        body.pack(fill="x")
        _bind_wrap(body, 16)

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(10, 0))
        meta = tk.Label(row, text=memory_meta_text(memory), bg=CARD, fg=FAINT,
                        font=_font(10), anchor="w", justify="left")
        meta.pack(side="left", fill="x", expand=True)
        _bind_wrap(meta, 150)
        memory_id = str(memory.get("id") or "")
        if forget_memory is None or not memory_id:
            pill = _Pill(row, t("忘记"), None, bg=CARD, fill=SURFACE, outline=BORDER,
                         fg=FAINT, font=_font(10), pad_x=11, height=24, radius=12)
            pill.set_enabled(False)
        else:
            pill = _Pill(row, t("忘记"), lambda mid=memory_id: self._forget_memory(mid),
                         bg=CARD, fill=DANGER_SOFT, outline=DANGER_LINE,
                         hover=DANGER_HOVER, fg=ERROR, font=_font(10), pad_x=11,
                         height=24, radius=12)
        pill.pack(side="right", padx=(10, 0))
    def _add_memory_empty(self, parent, query: str = "") -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.pack(fill="x", padx=30, pady=(64, 0))
        tk.Label(box, text="🧠", bg=PANEL, fg=ACCENT_SOFT,
                 font=(_FONT_STATE["emoji"], 22)).pack()
        if query:
            text = t("没有找到和「{query}」有关的记忆。", query=query)
        elif list_memories is None:
            text = t("记忆功能还在装。")
        else:
            text = t("她还没有记住什么。")
        note = tk.Label(box, text=text, bg=PANEL, fg=FAINT, font=_font(10),
                        justify="center", anchor="center")
        note.pack(fill="x", pady=(12, 0))
    def _set_memory_hint(self, text: str) -> None:
        try:
            self.memory_hint.configure(text=str(text))
        except Exception:
            pass
    def _set_memory_note(self, text: str, tone: str = "muted") -> None:
        colors = {"error": ERROR, "ok": OK, "accent": ACCENT, "muted": FAINT}
        try:
            self.memory_note.configure(text=str(text), fg=colors.get(tone, FAINT))
        except Exception:
            pass
    def _on_memory_search(self, _event=None) -> None:
        try:
            self.memory_search.sync_placeholder()
        except Exception:
            pass
        self._render_memory()
    def _forget_memory(self, memory_id: str) -> None:
        """忘记一条记忆：交给后端，等它回来再重画。"""
        memory_id = str(memory_id or "")
        if not memory_id:
            return
        if forget_memory is None:
            self._set_memory_note(t("记忆功能还在装，暂时忘不掉。"), "error")
            return
        if self._busy:
            self._set_memory_note(t("她正在忙这一件事，稍等一下。"), "error")
            return
        self._set_memory_note(t("她正在把这条放进遗忘…"), "accent")
        self._set_busy(True)
        pack = str(self.pack_dir)

        def work():
            try:
                return {"ok": True, "result": forget_memory(pack, memory_id)}
            except Exception as error:  # noqa: BLE001 - 失败要用人话告诉她
                return {"ok": False, "message": str(error)}

        self._run(work, self._on_forgotten)
    def _on_forgotten(self, payload) -> None:
        try:
            if not isinstance(payload, dict) or not payload.get("ok"):
                message = ""
                if isinstance(payload, dict):
                    message = str(payload.get("message") or "")
                message = message or t("后端没有回应")
                self._set_memory_note(t("没能忘掉：{message}", message=message), "error")
                try:
                    self._set_status(t("她没能忘掉这条记忆：{message}", message=message), "error")
                except Exception:
                    pass
                return
            self._snapshot()
            self._refresh_meta()
            self._render_memory(keep_scroll=True)
            self._set_memory_note(t("她忘掉了这条记忆。"), "ok")
            try:
                self._set_status(t("她忘掉了这条记忆。"), "ok")
            except Exception:
                pass
        finally:
            self._set_busy(False)
