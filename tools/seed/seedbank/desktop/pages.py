from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog

from PIL import ImageTk
from ..util import SeedError

from .dates import DateList
from .pet import PetStage
from .render import meter_image
from .text import t
from .widgets import Button, Card, MessageBubble, Scroll, Toggle, entry, label, paragraph, reader, set_reader


class Page(tk.Frame):
    key = ""
    snapshot_fields = ()

    def __init__(self, parent, app):
        super().__init__(parent, bg=app.theme.color("background"))
        self.app = app
        self.theme = app.theme
        self.state = app.page_state.setdefault(self.key, {})
        self.active = True
        self.stale = False
        self._focus_options = {}
        self._focus_command = self.register(self._take_focus)
        self.scroll_key = "scroll:" + self.state.get("section", "")
        self.restore_timer = self.after_idle(self.restore)
        self.bind("<Destroy>", self._destroy, add="+")

    def capture(self):
        if isinstance(getattr(self, "body", None), Scroll):
            self.state[self.scroll_key] = self.body.canvas.yview()[0]
        fields = getattr(self, "fields", {})
        focused = self.focus_get()
        self.state["focus_field"] = next((key for key, widget in fields.items() if getattr(widget, "control", widget) is focused), None)

    def restore(self):
        self.restore_timer = None
        if isinstance(getattr(self, "body", None), Scroll):
            self.body.canvas.yview_moveto(self.state.get(self.scroll_key, 0))
        focused = getattr(self, "fields", {}).get(self.state.get("focus_field"))
        if focused is not None:
            focused.focus_set()

    def _cancel_restore(self):
        for name in ("restore_timer", "restore_id"):
            timer = getattr(self, name, None)
            if timer:
                self.after_cancel(timer)
                setattr(self, name, None)

    def suspend(self):
        if not self.active:
            return
        self.capture()
        self._cancel_restore()
        self.active = False
        self._guard_focus()

    def _guard_focus(self):
        self._focus_options = {path: options for path, options in self._focus_options.items()
                               if options[0].winfo_exists()}
        pending = [self]
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            if str(widget) in self._focus_options:
                continue
            try:
                original = widget.cget("takefocus")
            except tk.TclError:
                continue
            if str(original) != "0":
                self._focus_options[str(widget)] = widget, original
                widget.configure(takefocus=self._focus_command)

    def _take_focus(self, path):
        if not self.active:
            return 0
        original = self._focus_options[path][1]
        if str(original) in ("", "0", "1"):
            return original
        return self.tk.call("eval", original, self.tk.call("list", path))

    def resume(self):
        self.active = True
        if self.restore_timer is None:
            self.restore_timer = self.after_idle(self.restore)

    def snapshot_changed(self, previous, current):
        return any(previous.get(field) != current.get(field) for field in self.snapshot_fields)

    def _destroy(self, event):
        if event.widget is self:
            self._cancel_restore()

    def heading(self, title, subtitle):
        label(self, self.theme, title, size=26, weight="bold").pack(fill="x", pady=(0, 4))
        paragraph(self, self.theme, subtitle, size=14)


class RoomPage(Page):
    key = "room"
    snapshot_fields = ("day", "transcript", "senses", "news")

    def snapshot_changed(self, previous, current):
        return (super().snapshot_changed(previous, current)
                or previous["states"].get("mood") != current["states"].get("mood"))

    def __init__(self, parent, app):
        super().__init__(parent, app)
        theme = self.theme
        snapshot = app.snapshot
        self.columnconfigure(0, weight=4, uniform="room")
        self.columnconfigure(1, weight=6, uniform="room")
        self.rowconfigure(0, weight=1)
        companion = Card(self, theme, tone=None, padding=16)
        self.companion = companion
        companion.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        companion.pack_propagate(False)
        label(companion.body, theme, t("她的小房间"), size=13, role="primary").pack(fill="x")
        self.name_label = label(companion.body, theme, app.name, size=26 if app._compact else 30, weight="bold", wraplength=240)
        self.name_label.pack(fill="x", pady=(4, 8))
        self.name_label.bind("<Configure>", lambda event: self.name_label.configure(wraplength=max(80, event.width)))
        base = tk.Frame(companion.body, bg=companion.body.cget("bg"))
        base.pack(side="bottom", fill="x")
        mood = snapshot["states"]["mood"]
        mood_text = str(mood.get("mood") or t("安静"))
        try:
            energy = max(0.0, min(1.0, float(mood.get("energy", 1))))
        except (TypeError, ValueError):
            energy = 1.0
        paragraph(base, theme, t("心情 · {mood}", mood=mood_text), role="text", size=14)
        meter = tk.Canvas(base, height=24, bg=base.cget("bg"), highlightthickness=0)
        meter.pack(fill="x", pady=(6, 0))

        def paint(event):
            if event.width < 12:
                return
            meter.artwork = ImageTk.PhotoImage(meter_image((event.width, 24), energy,
                                               base.cget("bg"), theme.color("stage_floor"),
                                               theme.color("primary")), master=meter)
            meter.delete("all")
            meter.create_image(0, 0, image=meter.artwork, anchor="nw")

        meter.bind("<Configure>", paint)
        status_row = tk.Frame(base, bg=base.cget("bg"))
        status_row.pack(fill="x", pady=(4, 0))
        label(status_row, theme, t("精力 {value}%", value=round(energy * 100)), size=12, role="muted").pack(side="left")
        self.pet = PetStage(companion.body, theme, bg=companion.body.cget("bg"))
        self.pet.pack(fill="both", expand=True, pady=8)
        self.pet.set_mood(mood_text, energy)
        if not app._greeted:
            self.pet.play("wave")
            app._greeted = True
        Button(status_row, theme, t("摸摸她"), lambda: self.pet.play("dance"), icon_name="heart", variant="ghost").pack(side="right")
        if not app._compact:
            paragraph(base, theme, t("不着急，陪伴有自己的节奏。"), size=12)
        app.pet = self.pet
        conversation = Card(self, theme, tone=None, padding=16)
        self.conversation = conversation
        conversation.grid(row=0, column=1, sticky="nsew")
        conversation.pack_propagate(False)
        top = tk.Frame(conversation.body, bg=conversation.body.cget("bg"))
        top.pack(fill="x", pady=(0, 12))
        heading = label(top, theme, t("今天，想聊些什么？"), size=21, weight="bold", wraplength=320)
        heading.pack(fill="x")
        heading.bind("<Configure>", lambda event: heading.configure(wraplength=max(80, event.width)))
        self.composer_panel = Card(conversation.body, theme, tone="surface", padding=14, radius=18)
        self.composer_panel.pack(side="bottom", fill="x", pady=(12, 0))
        self.composer = self.composer_panel.body
        label(self.composer, theme, t("对她说的话"), size=13, weight="bold").pack(fill="x", pady=(0, 6))
        self.input = tk.Text(self.composer, height=2 if app._compact else 3, wrap="word", width=1,
                            font=theme.font(), bg=theme.color("surface"), fg=theme.color("text"),
                            insertbackground=theme.color("primary"), bd=0, padx=0, pady=4,
                            highlightthickness=0, undo=True,
                            selectbackground=theme.color("soft"), selectforeground=theme.color("text"))
        self.input.pack(fill="x")
        self.input.insert("1.0", self.state.get("draft", ""))
        self.input.bind("<Control-Return>", self.send)
        self.input.bind("<Tab>", self._next_focus)
        self.input.bind("<FocusIn>", lambda event: self.composer_panel.set_focus(True))
        self.input.bind("<FocusOut>", lambda event: self.composer_panel.set_focus(False))
        actions = tk.Frame(self.composer, bg=self.composer.cget("bg"))
        actions.pack(fill="x", pady=(10, 0))
        app.action(actions, t("照片"), app.send_photo, icon_name="photo", variant="ghost").pack(side="left")
        app.action(actions, t("发送"), self.send, primary=True, icon_name="send").pack(side="right")
        if not app._compact:
            label(actions, theme, "Ctrl + Enter", size=12, role="muted").pack(side="right", padx=8)
        self.reply_status = label(conversation.body, theme, size=13, role="primary", wraplength=320)
        self.reply_status.pack(side="bottom", fill="x", pady=(4, 0))
        self.messages = Scroll(conversation.body, theme)
        self.messages.pack(fill="both", expand=True)
        app.body = self.messages
        transcript = snapshot["transcript"]
        self.limit = int(self.state.get("limit", 30))
        if len(transcript) > self.limit:
            Button(self.messages.frame, theme, t("更早的对话"), self.more, variant="ghost").pack(anchor="center", pady=8)
        if not transcript:
            empty = Card(self.messages.frame, theme, tone=None)
            empty.pack(fill="x", pady=12)
            label(empty.body, theme, t("你来了。"), size=22, weight="bold").pack(fill="x")
            paragraph(empty.body, theme, t("从一句问候开始，把今天的一点小事告诉她。"))
            Button(empty.body, theme, t("写一句问候"), self.greet).pack(anchor="w", pady=(8, 0))
        for row in transcript[-self.limit:]:
            is_fish = row["who"] == app.name or row["who"].startswith(app.name + "（") or row["who"] == "fish"
            bubble = MessageBubble(self.messages.frame, theme, row["who"], row["text"], incoming=is_fish)
            bubble.pack(fill="x", pady=(0, 16))
        for observation in (snapshot["senses"] + snapshot["news"])[-6:]:
            paragraph(self.messages.frame, theme, observation, size=13)
        self._scroll_initialized = False
        self.restore_id = self.after_idle(self._restore_scroll)

    def _restore_scroll(self):
        self.restore_id = None
        if not self._scroll_initialized:
            self.messages.update_idletasks()
            self._scroll_initialized = True
        follow_tail = self.state.pop("jump_bottom", False) or self.state.get("follow_tail", True)
        position = 1.0 if follow_tail else self.state.get("scroll", 1.0)
        self.messages.canvas.yview_moveto(position)
        if self.state.get("input_focus"):
            self.input.focus_set()
            self.input.mark_set("insert", self.state.get("cursor", "end-1c"))

    def _next_focus(self, event):
        target = self.input.tk_focusPrev() if event.state & 1 else self.input.tk_focusNext()
        target.focus_set()
        return "break"

    def greet(self):
        self.input.delete("1.0", "end")
        self.input.insert("1.0", t("我来陪你了，今天过得怎么样？"))
        self.input.focus_set()

    def send(self, event=None):
        message = self.input.get("1.0", "end-1c").strip()
        if not message:
            self.app.notify(t("先写一点想说的话吧。"))
            self.input.focus_set()
            return "break"
        if len(message) > 2000:
            self.app.notify(t("一条消息最多 2000 字"), "error")
            return "break"

        def complete(result):
            draft = self.app.page_state.setdefault("room", {})
            current = self.app.page
            if isinstance(current, RoomPage):
                current.capture()
            if draft.get("draft", "").strip() == message:
                draft["draft"] = ""
                if isinstance(current, RoomPage):
                    current.input.delete("1.0", "end")
            draft["jump_bottom"] = True

        if self.app.operate("message", text=message, on_done=complete, busy_text=t("她正在想怎么回答你…")):
            self.pet.play("think", seconds=120)
        return "break"

    def more(self):
        self.limit += 30
        self.app.show_page("room")

    def capture(self):
        if self.restore_id:
            self.after_cancel(self.restore_id)
            self.restore_id = None
        self.state.update(draft=self.input.get("1.0", "end-1c"), limit=self.limit,
                          scroll=self.messages.canvas.yview()[0], input_focus=self.focus_get() is self.input,
                          follow_tail=self.messages.canvas.yview()[1] >= .99, cursor=self.input.index("insert"))

    def suspend(self):
        super().suspend()
        self.pet.stop()

    def resume(self):
        super().resume()
        self.app.pet = self.pet
        self.app.body = self.messages
        self.pet.resume()
        if self.restore_id is None:
            self.restore_id = self.after_idle(self._restore_scroll)


class DiaryPage(Page):
    key = "diary"
    snapshot_fields = ("days", "transcript", "states")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.heading(t("一起走过的日子"), t("一天一页，都是她真实留下的生活。"))
        self.rows = list(reversed(app.snapshot["days"]))
        body = tk.Frame(self, bg=self.cget("bg"))
        body.pack(fill="both", expand=True)
        sidebar = Card(body, self.theme, width=round(224 * self.theme.scale), padding=12, tone=None)
        sidebar.pack(side="left", fill="y", padx=(0, 16))
        sidebar.pack_propagate(False)
        label(sidebar.body, self.theme, t("选择一天"), size=14, weight="bold").pack(fill="x", pady=(4, 12))
        self.dates = DateList(sidebar.body, self.theme,
                              [(row["date"], t("第 {number} 天", number=row["day"])) for row in self.rows])
        self.dates.pack(fill="both", expand=True)
        page = Card(body, self.theme)
        page.pack(side="left", fill="both", expand=True)
        self.title = label(page.body, self.theme, t("日记"), size=22, weight="bold")
        self.title.pack(fill="x", pady=(0, 12))
        self.document = reader(page.body, self.theme)
        self.dates.bind("<<DateSelected>>", self.select)
        selected = next((index for index, row in enumerate(self.rows) if row["day"] == self.state.get("day")), 0)
        if self.rows:
            self.dates.select(selected, notify=False)
            self.select()
            self.document.yview_moveto(self.state.get("scroll", 0))
        else:
            set_reader(self.document, t("还没有记录，新的故事会从这里开始。"))

    def select(self, event=None):
        selected = self.dates.selected
        if selected is None:
            return
        row = self.rows[selected]
        self.state["day"] = row["day"]
        self.title.configure(text=t("第 {number} 天", number=row["day"]) + " · " + row["date"])
        try:
            set_reader(self.document, self.app.session.diary(row["day"]), markdown=True)
        except (OSError, ValueError, SeedError) as error:
            set_reader(self.document, t("这一天的日记暂时无法读取。") + "\n\n" + t(str(error)))
        self.document.yview_moveto(0)

    def capture(self):
        self.state["scroll"] = self.document.yview()[0]


class MemoryPage(Page):
    key = "memory"
    snapshot_fields = ("memories",)

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.heading(t("她记得的小事"), t("记忆可以被放下，曾经发生的事仍然属于她。"))
        label(self, self.theme, t("搜索记忆"), size=13, role="muted").pack(anchor="w", pady=(8, 6))
        search = tk.Frame(self, bg=self.cget("bg"))
        search.pack(fill="x", pady=(0, 6))
        self.query = tk.StringVar(self, value=self.state.get("query", ""))
        self.search_entry = entry(search, self.theme, self.query, icon_name="search")
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda event: self.filter())
        Button(search, self.theme, t("搜索"), self.filter, variant="ghost").pack(side="left", padx=(8, 0))
        self.forgotten = tk.BooleanVar(self, value=self.state.get("forgotten", False))
        Toggle(self, self.theme, t("包含已放下的记忆"), self.forgotten, self.filter).pack(anchor="w", pady=(0, 12))
        pager = tk.Frame(self, bg=self.cget("bg"))
        pager.pack(side="bottom", fill="x", pady=(8, 0))
        self.previous = Button(pager, self.theme, t("上一页"), lambda: self.move(-1), variant="ghost")
        self.previous.pack(side="left")
        self.next = Button(pager, self.theme, t("下一页"), lambda: self.move(1), variant="ghost")
        self.next.pack(side="right")
        self.count = label(pager, self.theme, size=13, role="muted")
        self.count.pack(side="left", padx=16)
        self.body = Scroll(self, self.theme)
        self.body.pack(fill="both", expand=True)
        self.render()

    def filter(self):
        self.state["index"] = 0
        self.render()

    def move(self, delta):
        self.state["index"] = max(0, self.state.get("index", 0) + delta)
        self.render()

    def render(self):
        for child in self.body.frame.winfo_children():
            child.destroy()
        query = self.query.get().strip().casefold()
        rows = [row for row in reversed(self.app.snapshot["memories"])
                if (self.forgotten.get() or (not row.get("forgotten") and row.get("kind") != "forget"))
                and query in str(row.get("text", "")).casefold()]
        pages = max(1, (len(rows) + 19) // 20)
        index = min(self.state.get("index", 0), pages - 1)
        self.state["index"] = index
        self.previous.set_enabled(index > 0)
        self.next.set_enabled(index < pages - 1)
        self.count.configure(text=t("{count} 条 · {page}/{pages}", count=len(rows), page=index + 1, pages=pages))
        self.memory_rows = []
        self.memory_group = None
        if not rows:
            card = Card(self.body.frame, self.theme)
            card.pack(fill="x", pady=8)
            paragraph(card.body, self.theme, t("没有找到这段记忆。换个词，或一起创造新的回忆吧。"), role="text", size=15)
        else:
            self.memory_group = Card(self.body.frame, self.theme, padding=16, radius=18)
            self.memory_group.pack(fill="x")
        visible = rows[index * 20:(index + 1) * 20]
        for position, row in enumerate(visible):
            item = tk.Frame(self.memory_group.body, bg=self.memory_group.body.cget("bg"))
            item.pack(fill="x", pady=(8, 8))
            item.columnconfigure(0, weight=1)
            content = tk.Frame(item, bg=item.cget("bg"))
            content.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
            self.memory_rows.append(item)
            caption = t("第 {number} 天", number=row.get("day", "—"))
            if row.get("forgotten"):
                caption += " · " + t("已放下")
            elif row.get("superseded"):
                caption += " · " + t("已更正")
            label(content, self.theme, caption, size=13, role="muted").pack(fill="x")
            paragraph(content, self.theme, str(row.get("text", "")), role="text", size=15)
            if not row.get("forgotten") and row.get("kind") != "forget":
                self.app.action(item, t("放下这条"), lambda identifier=row["id"]: self.app._forget_memory(identifier),
                                danger=True, variant="ghost").grid(row=0, column=1, sticky="ne")
            if position < len(visible) - 1:
                tk.Frame(self.memory_group.body, height=1, bg=self.theme.color("separator")).pack(fill="x")
        self.body.canvas.yview_moveto(0)

    def capture(self):
        super().capture()
        self.state.update(query=self.query.get(), forgotten=self.forgotten.get())


class LifePage(Page):
    key = "life"
    snapshot_fields = ("day", "states")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.heading(t("她的小小生活"), t("在意的事、做过的梦，还有慢慢长出来的自己。"))
        tabs = tk.Frame(self, bg=self.cget("bg"))
        tabs.pack(anchor="w", pady=(0, 12))
        current = self.state.get("section", "growth")
        for key, caption in (("growth", "成长"), ("heart", "心事"), ("works", "作品")):
            Button(tabs, self.theme, t(caption), lambda destination=key: self.switch(destination),
                   selected=current == key, variant="tab").pack(side="left", padx=(0, 8))
        self.body = Scroll(self, self.theme, max_width=1100)
        self.body.pack(fill="both", expand=True)
        self.section_count = 0
        self.section_columns = 2 if not app._compact and current != "works" and self.theme.scale == 1 else 1
        self.body.frame.columnconfigure(tuple(range(self.section_columns)), weight=1, uniform="life")
        self.states = app.snapshot["states"]
        getattr(self, current)()

    def switch(self, section):
        if section == self.state.get("section", "growth"):
            return
        self.state["section"] = section
        self.app.show_page("life")

    def section(self, title, lines=(), tone="surface"):
        card = Card(self.body.frame, self.theme, tone=tone)
        row, column = divmod(self.section_count, self.section_columns)
        card.grid(row=row, column=column, sticky="nsew", padx=(0, 12 if column < self.section_columns - 1 else 0), pady=(0, 16))
        self.section_count += 1
        label(card.body, self.theme, title, size=18, weight="bold").pack(fill="x", pady=(0, 8))
        for text in lines:
            paragraph(card.body, self.theme, str(text), role="text", size=14)
        return card.body

    def growth(self):
        agency = self.states["agency"]
        plans = [row.get("plan", "") for row in agency.get("plans", []) if row.get("day") == self.app.snapshot["day"]]
        interests = [row.get("topic", "") for row in agency.get("interests", [])]
        body = self.section(t("今天的小计划"), plans or [t("今天还没有计划，先一起待一会儿。")], "mint")
        self.app.action(body, t("陪她过一天"), self.app.advance_day, icon_name="moon").pack(anchor="w", pady=(8, 0))
        from ..agency import history_line
        changes = self.states.get("plan_history", {})
        self.section(t("今天的计划变化"), [history_line(row) for row in changes.get("records", [])]
                     + ([t("较早的计划变化仍保留在档案中。")] if changes.get("has_more") else [])
                     or [t("今天还没有计划变化。")])
        from ..plan_links import display_lines as plan_review_lines
        self.section(t("计划与实际行动"), plan_review_lines(self.states.get("development", {}).get("plan_review", []))
                     or [t("尚无可回顾的计划与行动关联。")])
        from ..plan_continuity import display_lines as prior_choice_lines
        self.section(t("先前的打算"), prior_choice_lines(self.states.get("development", {}).get("prior_choices", []))
                     or [t("目前没有可供重新考虑的先前打算。")])
        self.section(t("她在意的事"), [" · ".join(interests)] if interests else [t("兴趣会从真实经历中慢慢长出来。")])
        bonds = self.states["bonds"]
        owner = bonds.get("owner") or {}
        body = self.section(t("你们之间"), [t("聊过 {count} 次天", count=owner.get("talks", 0))])
        for promise in bonds.get("promises", [])[-8:]:
            paragraph(body, self.theme, str(promise.get("text", "")) + " · " + t(str(promise.get("status", "pending"))))
        reminders = self.states["hands"].get("reminders", [])
        body = self.section(t("替你记着"), [
            t("第 {number} 天", number=row.get("due_day", "—")) + " · " + str(row.get("text", "")) + " · " + t(str(row.get("status", "pending")))
            for row in reminders[-12:]
        ] or [t("还没有需要提醒的事。")])
        self.app.action(body, t("记一件事"), self.remind).pack(anchor="w", pady=(8, 0))
        friends = self.states["friends"].get("friends", [])
        self.section(t("来过的朋友"), [str(row.get("name", "")) + " · " + t(str(row.get("status", "alive"))) for row in friends]
                     or [t("还没有朋友来访。")])

    def heart(self):
        inner = self.states["inner"]
        self.section(t("关于她自己"), [inner.get("narrative", {}).get("text") or t("她还在慢慢认识自己。")], "peach")
        silence = inner.get("silence", {})
        self.section(t("此刻的心意"), [t("今天想安静一会儿") if silence.get("on") else t("可以慢慢说话。"), silence.get("note", "")])
        dreams = inner.get("dreams", [])
        self.section(t("梦里的片段"), [row.get("text", "") for row in dreams[-5:]] or [t("还没有留下梦的片段。")])
        corrections = inner.get("corrections", [])
        if corrections:
            self.section(t("重新认识的事"), [str(row.get("old", "")) + " → " + str(row.get("new", "")) for row in corrections[-6:]])
        memorial = self.states["memorial"]
        self.section(t("值得记住的日子"), [t("第 {number} 天", number=row.get("day", "—")) + " · " + row.get("name", "")
                     for row in memorial.get("anniversaries", [])] or [t("重要的日子会慢慢积攒。")])
        self.section(t("还没放下的事"), [row.get("text", "") for row in memorial.get("regrets", [])[-8:]] or [t("此刻没有留下遗憾。")])
        farewells = memorial.get("farewells", [])
        if farewells:
            self.section(t("好好说过再见"), [row.get("name", "") + " · " + row.get("note", "") for row in farewells[-8:]])
        boundaries = self.states["agency"].get("boundaries", [])
        if boundaries:
            self.section(t("她不想聊的事"), [str(row.get("topic", row.get("text", ""))) if isinstance(row, dict) else str(row) for row in boundaries])

    def works(self):
        body = self.section(t("留下一点小作品"), [t("有时是一首诗，有时是一封信，也可能是一幅字符画。")], "peach")
        actions = tk.Frame(body, bg=body.cget("bg"))
        actions.pack(fill="x", pady=(8, 0))
        for kind, caption in (("poem", "写首诗"), ("letter", "写封信"), ("drawing", "画点什么")):
            self.app.action(actions, t(caption), lambda choice=kind: self.app.operate("work", action="compose", kind=choice)).pack(side="left", padx=(0, 8))
        works = self.states["works"].get("works", [])
        limit = self.state.get("limit", 10)
        if not works:
            self.section(t("作品收藏"), [t("她留下的作品，会好好收在这里。")])
        for work in reversed(works[-limit:]):
            self.section(work.get("title") or t("无题"), [t("第 {number} 天", number=work.get("day", "—")), work.get("text", "")])
        if len(works) > limit:
            Button(self.body.frame, self.theme, t("更早的作品"), self.more_works, variant="ghost").grid(row=self.section_count, column=0, pady=8)

    def more_works(self):
        self.state["limit"] = self.state.get("limit", 10) + 10
        self.app.show_page("life")

    def remind(self):
        text = simpledialog.askstring(t("记一件事"), t("希望她记住什么？"), parent=self.app.root)
        if not text:
            return
        due = simpledialog.askinteger(t("提醒日期"), t("在她的第几天提醒？"), parent=self.app.root,
                                      initialvalue=self.app.snapshot["day"] + 1, minvalue=self.app.snapshot["day"])
        if due is not None:
            self.app.operate("reminder", action="add", text=text, due_day=due)
