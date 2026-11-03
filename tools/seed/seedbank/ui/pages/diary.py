"""日记页：按天倒序的日记卡。"""
import tkinter as tk

from .. import tokens as T  # noqa: F401


class DiaryPageMixin:

    def _build_diary_page(self) -> None:
        page = tk.Frame(self.page_host, bg=PANEL)
        self.pages["diary"] = page
        self.diary_scroll = _ScrollFrame(page, bg=PANEL, backdrop=True)
        self.diary_scroll.pack(fill="both", expand=True)
    def _refresh_diary(self) -> None:
        """按时间倒序重画日记页：每天一条分隔、一张卡片、一个记忆数。"""
        self._snapshot()
        self._refresh_meta()
        frame = self.diary_scroll.frame
        for child in frame.winfo_children():
            child.destroy()
        days = list_days(str(self.pack_dir))
        if not days:
            self._add_diary_empty(frame)
            return
        memories = self._memories_by_day()
        for day in reversed(days):
            try:
                number = int(day.get("day") or 0)
            except (TypeError, ValueError):
                number = 0
            self._add_diary_day(frame, day, memories.get(number, 0))
    def _memories_by_day(self) -> dict:
        """memories.jsonl 里每条记忆都带 day，按天加起来。"""
        counts: dict = {}
        try:
            entries = read_memories(str(self.pack_dir))
        except (OSError, ValueError):
            return counts
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                day = int(entry.get("day"))
            except (TypeError, ValueError):
                continue
            counts[day] = counts.get(day, 0) + 1
        return counts
    def _read_diary_text(self, day: dict) -> str:
        """取日文件里 `## 今天` 之后、下一个 `## ` 或 `---` 之前的正文。"""
        try:
            path = self.pack_dir / "life" / str(day.get("file") or "")
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""
        inside = False
        body = []
        for line in raw.splitlines():
            line = line.rstrip()
            stripped = line.strip()
            if not inside:
                if stripped == "## 今天":
                    inside = True
                continue
            if stripped.startswith("## ") or stripped == "---":
                break
            body.append(line)
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        # 卡片里只留字：把 markdown 的小记号拿掉。
        cleaned = []
        for line in body:
            if line.startswith("# "):
                cleaned.append(line[2:])
            elif line.startswith("> "):
                cleaned.append(line[2:])
            else:
                cleaned.append(line)
        return "\n".join(cleaned).strip()
    def _add_diary_day(self, parent, day: dict, memories: int) -> None:
        head = tk.Frame(parent, bg=PANEL)
        head.pack(fill="x", padx=24, pady=(22, 10))
        tk.Label(head, text=day_caption(day.get("day"), day.get("date")), bg=PANEL,
                 fg=TEXT, font=_font(12, "bold"), anchor="w").pack(side="left")
        count_text = t("{count} 条记忆", count=memories) if memories else t("没有记忆")
        tk.Label(head, text=count_text, bg=PANEL, fg=FAINT, font=_font(10),
                 anchor="e").pack(side="right")

        card = _Card(parent, bg=PANEL, fill=DIARY_BG, outline=DIARY_LINE, accent=ACCENT,
                     radius=18, inset=18)
        card.pack(fill="x", padx=22, pady=(0, 16))
        text = self._read_diary_text(day)
        if text:
            body = tk.Label(card.inner, text=text, bg=DIARY_BG, fg=TEXT_SOFT,
                            font=_font(12), justify="left", anchor="w")
        else:
            body = tk.Label(card.inner, text=t("这一天没有留下字。"), bg=DIARY_BG,
                            fg=FAINT, font=_font(10, slant="italic"), justify="left",
                            anchor="w")
        body.pack(fill="x")
        _bind_wrap(body, 12)
    def _add_diary_empty(self, parent) -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.pack(fill="x", padx=30, pady=(72, 0))
        tk.Label(box, text="🐋", bg=PANEL, fg=ACCENT_SOFT,
                 font=(_FONT_STATE["emoji"], 22)).pack()
        note = tk.Label(box, text=t("她还没有写下什么。\n等一天过去，这里就会出现她的一天。"),
                        bg=PANEL, fg=FAINT, font=_font(10), justify="center", anchor="center")
        note.pack(fill="x", pady=(12, 0))
