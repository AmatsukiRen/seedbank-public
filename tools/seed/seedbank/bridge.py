"""载体桥 —— 任何语言、任何聊天工具都能通过它和她说话。

一行 JSON 进，一行 JSON 出；没有人说话时，它安静地等。
载体不是她的一部分，只是一个窗口。协议见 spec/channel.md。
"""

from __future__ import annotations

from .i18n import t
import json
import sys
from pathlib import Path

from . import __version__
from .brain import create_brain, describe_brain, load_brain_config
from .clock import tick as clock_tick
from .cognition import chat_turn, feed_news, open_day, recall, run_days, sense_media
from .pack import check
from .util import SeedError, expand_home, list_days, read_json, read_memories
from .pack_lock import writer

PROTOCOL = "seedbank/bridge@1"

MAX_LINE = 1024 * 1024  # 单行最多 1MB，防止坏载体把内存撑爆

OPS = (
    "hello", "status", "lifecycle", "message", "image", "sound", "feed",
    "day", "tick", "recall", "check", "stop",
    # 1.21：后加的能力也放进协议，别让载体扩展只能用老功能
    "event", "reminder", "promise", "memorial", "inner",
    "work", "friend", "persona", "semantic", "facts", "learning", "relationships", "disclosure", "life_story", "media", "memories", "agency", "development", "requests", "resume",
)


def _mood(pack: Path) -> dict:
    from .body import state as body_state
    try:
        data = read_json(pack / "mind" / "mood.json", {}) or {}
    except (SeedError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    # Match snapshots and cognition: elapsed recovery is read-time state,
    # not a reason to rewrite the saved mood or resource history.
    energy = body_state(pack)["energy"]
    return {"mood": str(data.get("mood") or t("安静")), "energy": energy}


def _status(pack: Path) -> dict:
    from .lifecycle import status
    day = open_day(pack)
    return {
        "day": day["dayNo"],
        "date": day["date"],
        "days": len(list_days(pack)),
        "memories": len(read_memories(pack)),
        "lifecycle": status(pack),
        **_mood(pack),
    }


class Bridge:
    """把生命包变成一个「一问一答」的载体。一个 Bridge 只给一个线程用。"""

    def __init__(self, pack_dir, brain_override: str = ""):
        self.pack = Path(expand_home(str(pack_dir)))
        with writer(self.pack) as recovered:
            self.recovered_operations = recovered or []
        self.birth = read_json(self.pack / "birth.json", {}) or {}
        if not self.birth:
            raise SeedError(t("不是一个生命包（缺 birth.json）：{pack}", pack=self.pack))
        self.brain_override = str(brain_override or "")
        self._brain = None

    @property
    def name(self) -> str:
        return str(self.birth.get("name") or "她")

    @property
    def brain(self):
        if self._brain is None:
            self._brain = create_brain(self.pack, self.brain_override)
        return self._brain

    # —— 每个 op 一个方法，返回可以直接 JSON 化的 dict ——

    def hello(self) -> dict:
        return {
            "ok": True,
            "protocol": PROTOCOL,
            "name": self.name,
            "version": __version__,
            "born_at": self.birth.get("born_at"),
            "status": _status(self.pack),
        }

    def status(self) -> dict:
        return {
            "ok": True,
            "name": self.name,
            "version": __version__,
            "brain": describe_brain(load_brain_config(self.pack)),
            "egg": self.birth.get("egg", {}).get("id") or "",
            "runtime": (self.birth.get("requires") or {}),
            **_status(self.pack),
        }

    def development(self) -> dict:
        from .development import summary
        return {"ok": True, **summary(self.pack)}

    def message(self, text: str, speaker: str = "主人", *, request_id="", person_id=None, interaction_kind="direct", audience_id=None) -> dict:
        from .lifecycle import require_active
        from .presentation import normalize as normalize_presentation
        require_active(self.pack)
        self._tick()
        result = chat_turn(self.pack, text, self.brain, speaker=speaker or "主人", request_id=request_id,
                           person_id=person_id, interaction_kind=interaction_kind, audience_id=audience_id)
        return {
            "ok": True,
            "reply": result["reply"],
            "presentation": normalize_presentation(result.get("presentation")),
            "day": result["dayNo"],
            "date": result["date"],
            "memories_added": result["memoriesAdded"],
            "corrections": result.get("corrections", 0),
            "development_changes": result.get("developmentChanges", 0),
            "facts_added": result.get("factsAdded", 0),
            "fact_proposals_rejected": result.get("factProposalsRejected", 0),
            "action_results": result.get("actionResults", []),
            "model_budget": result.get("modelBudget", {}),
            "request_id": result.get("requestId"), "replayed": result.get("replayed", False),
            "status": _status(self.pack),
        }

    def _tick(self) -> None:
        """她的时间按真实的一天走：每次互动前先看钟。"""
        try:
            clock_tick(self.pack, self.brain)
        except Exception:  # noqa: BLE001 - 时钟不该挡住说话
            pass

    def _sense(self, **kwargs) -> dict:
        # Calendar bookkeeping may itself invoke a model. Capture the incoming
        # material first so that an interruption there cannot erase delivery.
        result = sense_media(self.pack, before_process=self._tick, **kwargs)
        return {
            "ok": True,
            "lines": result["lines"],
            "day": result["dayNo"],
            "date": result["date"],
            "memories_added": result["memoriesAdded"],
            "assets": result.get("assets", []),
            "vision": result.get("vision", {}),
            "request_id": result.get("requestId", ""), "replayed": result.get("replayed", False),
            "pending": result.get("pending", False), "cancelled": result.get("cancelled", False),
            "status": _status(self.pack),
        }

    def image(self, path: str, note: str = "", vision=None, *, person_id="owner", audience_id=None, request_id="") -> dict:
        # 1.22：vision=None 表示自动（有视觉的脑就看懂）；显式 False 才跳过。
        return self._sense(image=path, note=note or None, vision=vision, person_id=person_id, audience_id=audience_id, request_id=request_id)

    def sound(self, path: str, note: str = "", *, person_id="owner", audience_id=None, request_id="") -> dict:
        return self._sense(sound=path, note=note or None, person_id=person_id, audience_id=audience_id, request_id=request_id)

    def feed(self, items, source: str = "") -> dict:
        """让她读一段公开摘要（新闻、群聊公共内容）：写 `## 见闻` + hearsay 记忆。"""
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list) or not items:
            raise SeedError(t("feed 需要 items：一行行摘要的列表"))
        result = feed_news(self.pack, items, source=source or "载体")
        return {
            "ok": True,
            "lines": result["lines"],
            "day": result["dayNo"],
            "date": result["date"],
            "memories_added": result["memoriesAdded"],
            "status": _status(self.pack),
        }

    def day(self, days: int = 1) -> dict:
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise SeedError(t("days 必须是整数")) from None
        if days < 1 or days > 3650:
            raise SeedError(t("days 要在 1..3650 之间"))
        result = run_days(self.pack, days=days, brain=self.brain)
        return {
            "ok": True,
            "days": [
                {
                    "day": item["day"],
                    "date": item["date"],
                    "memories": item["memoriesAdded"],
                    "innerResult": item.get("innerResult"),
                    "mood": item["mood"],
                    "energy": item["energy"],
                }
                for item in result["days"]
            ],
            "status": _status(self.pack),
        }

    def recall(self, query: str = "", k: int = 5) -> dict:
        from .memory_state import provenance
        rows = recall(self.pack, query, k=int(k or 5), use_semantic=self.brain_override != "stub")
        memories = []
        for row in rows:
            memory = row.get("memory") if isinstance(row, dict) else None
            if memory is None:
                memory = row or {}
            memories.append({
                **memory,
                "text": str(memory.get("text") or ""),
                "day": memory.get("day"),
                "importance": memory.get("importance"),
                "tags": memory.get("tags") or [],
                "provenance": provenance(memory),
                "score": row.get("score") if isinstance(row, dict) else None,
                "retrieval": row.get("parts", {}) if isinstance(row, dict) else {},
            })
        from .semantic import last_status
        return {"ok": True, "memories": memories, "retrieval_status": last_status(self.pack)}

    def check(self) -> dict:
        result = check(self.pack)
        return {
            "ok": bool(result.get("ok")),
            "days": result.get("days"),
            "memories": result.get("memories"),
            "birth_at": result.get("birth_at"),
        }

    # —— 1.21：扩展接口（后加的意志/手/关系/有限性/内在/作品/他者/人格/记忆） ——

    def tick(self, now=None) -> dict:
        """手动让她看一次钟（幂等）：载体想主动推进时间时用。"""
        from .lifecycle import active
        result = clock_tick(self.pack, self.brain if active(self.pack) else None, now=str(now) if now else None)
        return {
            "ok": True,
            "today": result.get("today"),
            "advanced": result.get("advanced"),
            "reason": result.get("reason"),
            "day": result.get("day"),
            "date": result.get("date"),
            "sleptDays": result.get("sleptDays"),
            "status": _status(self.pack),
        }

    def event(self, kind: str, text: str, source: str = "", process: bool = True) -> dict:
        """生活流：把一条外部事件放进她的 inbox（news / sense / note）。"""
        from .live import enqueue_event, process_inbox

        kind = str(kind or "").strip().lower()
        if kind not in ("news", "sense", "note"):
            raise SeedError(t("事件 kind 只能是 news / sense / note"))
        if not str(text or "").strip():
            raise SeedError(t("事件要有 text"))
        enqueue_event(self.pack, {"kind": kind, "text": str(text), "source": source})
        result = process_inbox(self.pack, brain=self.brain) if process else {
            "processed": [], "failed": []
        }
        return {
            "ok": True,
            "processed": result.get("processed", []),
            "failed": result.get("failed", []),
            "status": _status(self.pack),
        }

    def reminder(self, action: str, text: str = "", due_day=None, reminder_id: str = "", *, due_on=None, request_id="", expected="", reason="") -> dict:
        """1.17 手：替主人记一件事；到期她会说出口。"""
        from .hands import add_reminder, list_reminders, mark_said

        action = str(action or "list").strip().lower()
        if action in ("revise", "cancel"):
            from .reminder_changes import perform
            return {"ok": True, **perform(self.pack, action, {"reminder_id": reminder_id, "expected": expected,
                        "reason": reason, "text": text, "due_on": due_on}, request_id=request_id)}
        if action == "history":
            from .reminder_changes import listing
            with writer(self.pack):
                return {"ok": True, "reminders": listing(self.pack)}
        if action == "cancel_pending":
            from .hands import cancel_pending
            return {"ok": True, **cancel_pending(self.pack, request_id)}
        day = open_day(self.pack)
        if action in ("add", "new"):
            if due_on is not None:
                from .hands import schedule
                if due_day is not None:
                    raise SeedError("日历日期与旧日页期限不能同时填写。")
                return {"ok": True, **schedule(self.pack, {"text": text, "due_on": due_on}, request_id=request_id), "status": _status(self.pack)}
            due = int(due_day or day["dayNo"])
            row = add_reminder(self.pack, text, due, created_day=day["dayNo"])
            return {"ok": True, "reminder": row, "status": _status(self.pack)}
        if action in ("done", "said"):
            row = mark_said(self.pack, str(reminder_id), day["dayNo"])
            return {"ok": True, "reminder": row, "status": _status(self.pack)}
        rows = list_reminders(self.pack)
        return {"ok": True, "reminders": rows, "status": _status(self.pack)}

    def promise(self, action: str, text: str = "", due_day=None,
                promise_id: str = "", note: str = "") -> dict:
        """1.12 关系：她答应过的事。"""
        from .bonds import (
            add_promise, break_promise, keep_promise, list_promises, pending_promises,
        )

        action = str(action or "list").strip().lower()
        if action in ("make", "add", "new"):
            row = add_promise(self.pack, text, due_day=int(due_day) if due_day else None)
            return {"ok": True, "promise": row, "status": _status(self.pack)}
        if action in ("keep", "kept"):
            row = keep_promise(self.pack, str(promise_id), note=note)
            return {"ok": True, "promise": row, "status": _status(self.pack)}
        if action in ("break", "broken"):
            row = break_promise(self.pack, str(promise_id), note=note)
            return {"ok": True, "promise": row, "status": _status(self.pack)}
        if action == "pending":
            return {"ok": True, "promises": pending_promises(self.pack)}
        return {"ok": True, "promises": list_promises(self.pack)}

    def memorial(self, action: str, name: str = "", text: str = "",
                 day=None, kind: str = "", note: str = "", index=None) -> dict:
        """1.13 有限性：纪念日 / 遗憾 / 告别。"""
        from .memorial import (
            add_anniversary, add_farewell, add_regret, memorial_summary,
            resolve_regret, total_missing_days,
        )

        day_no = int(day or open_day(self.pack)["dayNo"])
        action = str(action or "list").strip().lower()
        if action in ("anniversary", "day"):
            row = add_anniversary(self.pack, name, day=day_no, kind=kind or "custom", note=note)
        elif action == "regret":
            row = add_regret(self.pack, text, day=day_no)
        elif action in ("resolve", "resolved"):
            row = resolve_regret(self.pack, index, day=day_no)
        elif action == "farewell":
            row = add_farewell(self.pack, name, kind=kind or "goodbye", note=note, day=day_no)
        elif action == "list":
            row = memorial_summary(self.pack, day_no)
        else:
            raise SeedError(t("memorial 的 action 不认识：{action}", action=action))
        summary = memorial_summary(self.pack, day_no)
        summary["missing_days"] = total_missing_days(self.pack)
        return {"ok": True, "result": row, "memorial": summary, "status": _status(self.pack)}

    def inner(self, action: str, note: str = "", text: str = "",
              old: str = "", new: str = "") -> dict:
        """1.14 内在：沉默权 / 做梦 / 自我叙事 / 自我更正。"""
        from .inner import (
            add_dream, correct_belief, inner_summary, set_narrative, set_silence,
        )

        day = open_day(self.pack)
        action = str(action or "status").strip().lower()
        if action in ("silence_on", "silence"):
            set_silence(self.pack, True, note=note, day=day["dayNo"])
        elif action == "silence_off":
            set_silence(self.pack, False, day=day["dayNo"])
        elif action == "dream":
            add_dream(self.pack, day["dayNo"], text)
        elif action in ("narrate", "narrative"):
            set_narrative(self.pack, text, day=day["dayNo"])
        elif action == "correct":
            correct_belief(self.pack, old, new, day=day["dayNo"])
        elif action != "status":
            raise SeedError(t("inner 的 action 不认识：{action}", action=action))
        return {"ok": True, "inner": inner_summary(self.pack), "status": _status(self.pack)}

    def work(self, action: str = "list", kind: str = "", title: str = "",
             work_id: str = "", limit=None) -> dict:
        """1.15 作品：让她写诗 / 写信 / 画字符画，或者翻出来看。"""
        from . import works as works_module
        from .cognition import compose_work

        action = str(action or "list").strip().lower()
        if action in ("compose", "make", "write"):
            made = compose_work(self.pack, kind or "poem", self.brain, title=title)
            return {"ok": True, "work": made, "status": _status(self.pack)}
        if action in ("read", "get"):
            row = works_module.read_work(self.pack, str(work_id))
            if not row:
                raise SeedError(t("没有这篇作品：{id}", id=work_id))
            return {"ok": True, "work": row}
        rows = works_module.list_works(self.pack, kind or None, int(limit) if limit else None)
        return {"ok": True, "works": rows, "summary": works_module.works_summary(self.pack)}

    def friend(self, action: str, other: str = "", friend: str = "",
               note: str = "", letter: str = "") -> dict:
        """1.18 他者：别的鱼来串门 / 告别 / 给后来的人留一封信。"""
        from .cognition import legacy_letter, mourn, visit
        from .friends import describe_friends

        action = str(action or "list").strip().lower()
        if action == "visit":
            if not other:
                raise SeedError(t("visit 需要 other：另一个生命包的路径"))
            result = visit(self.pack, other, brain=self.brain, note=note)
            return {"ok": True, "visit": result, "friends": describe_friends(self.pack)}
        if action in ("mourn", "lost"):
            result = mourn(self.pack, friend, brain=self.brain, letter=letter)
            return {"ok": True, "mourn": result, "friends": describe_friends(self.pack)}
        if action in ("legacy", "letter"):
            result = legacy_letter(self.pack)
            return {"ok": True, "legacy": result}
        return {"ok": True, "friends": describe_friends(self.pack)}

    def persona(self, action: str = "check") -> dict:
        """Fixed archive-sample assessment; status never calls a model."""
        from . import persona as persona_module

        action = str(action or "check").strip().lower()
        if action == "capture":
            data = persona_module.capture(self.pack, self.brain_override)
        elif action == "check":
            data = persona_module.check(self.pack, self.brain_override)
        elif action == "status":
            data = persona_module.status(self.pack)
        else:
            raise SeedError("persona 的 action 只能是 capture / check / status")
        return {"ok": True, "persona": data}

    def memories(self, action: str = "list", query: str = "",
                 limit=20, memory_id: str = "", reason: str = "", *, text="",
                 change_type="correction", effective_on="", request_id="") -> dict:
        """记忆列表、显式修订、版本审计与放下；保留原始历史。"""
        from .cognition import forget_memory, list_memories
        from .memory_editor import history, revise

        action = str(action or "list").strip().lower()
        if action in ("forget", "forgot"):
            result = forget_memory(self.pack, str(memory_id), reason=reason)
            return {"ok": True, "forgotten": result}
        if action == "history":
            return {"ok": True, "history": history(self.pack, memory_id)}
        if action == "revise":
            return {"ok": True, **revise(self.pack, memory_id, text, reason=reason,
                                       change_type=change_type, effective_on=effective_on, request_id=request_id)}
        if action != "list":
            raise SeedError("记忆操作只能是 list / history / revise / forget。")
        rows = list_memories(self.pack)
        needle = str(query or "").strip()
        if needle:
            rows = [row for row in rows if needle in str(row.get("text") or "")]
        rows = rows[-int(limit or 20):]
        return {
            "ok": True,
            "memories": [
                {
                    **row,
                    "id": row.get("id"),
                    "day": row.get("day"),
                    "kind": row.get("kind"),
                    "text": row.get("text"),
                    "importance": row.get("importance"),
                    "tags": row.get("tags") or [],
                    "forgotten": bool(row.get("forgotten")),
                }
                for row in rows
            ],
        }

    def agency(self, action: str = "list", text: str = "", force: bool = False, *, day=None, before="", limit=20) -> dict:
        """1.11 意志：她的兴趣、边界、今天的计划；也能问她要不要先开口。"""
        from .agency import add_boundary, add_interest, clear_boundaries, load_agency
        from .cognition import maybe_initiate

        action = str(action or "list").strip().lower()
        if action == "history":
            from .agency import plan_history
            return {"ok": True, **plan_history(self.pack, day=day, before=before, limit=limit)}
        if action == "interest":
            add_interest(self.pack, text)
        elif action == "boundary":
            add_boundary(self.pack, text)
        elif action == "clear_boundaries":
            clear_boundaries(self.pack)
        elif action in ("initiate", "speak"):
            spoken = maybe_initiate(self.pack, self.brain, force=bool(force))
            return {
                "ok": True,
                "initiated": bool(spoken),
                "message": (spoken or {}).get("reply"),
                "status": _status(self.pack),
            }
        elif action != "list":
            raise SeedError(t("agency 的 action 不认识：{action}", action=action))
        data = load_agency(self.pack)
        return {"ok": True, "agency": data, "status": _status(self.pack)}

    # —— 一条请求 ——

    def handle(self, request: dict) -> dict:
        if not isinstance(request, dict):
            return {"ok": False, "error": t("请求必须是一个 JSON 对象")}
        rid = request.get("id")
        op = str(request.get("op") or "hello").strip().lower()
        try:
            if op in ("hello", "hi"):
                response = self.hello()
            elif op == "status":
                response = self.status()
            elif op == "lifecycle":
                from .lifecycle import status, transition
                action = request.get("action", "status")
                with writer(self.pack):
                    value = status(self.pack) if action == "status" else transition(
                        self.pack, action, note=request.get("note"), expected=request.get("expected"),
                        confirmed=request.get("confirmed") is True)
                response = {"ok": True, "lifecycle": value}
            elif op == "message":
                response = self.message(str(request.get("text") or ""), str(request.get("speaker") or "主人"),
                                        request_id=str(request.get("request_id") or ""), person_id=request.get("person_id"),
                                        audience_id=request.get("audience_id"))
            elif op == "requests":
                from .requests import pending
                with writer(self.pack):
                    response = {"ok": True, "pending": pending(self.pack)}
            elif op == "resume":
                from .requests import get
                identifier = str(request.get("request_id") or "")
                with writer(self.pack):
                    payload = get(self.pack, identifier)["payload"]
                if payload.get("kind") == "chat":
                    response = self.message(payload["text"], payload["speaker"], request_id=identifier,
                                            person_id=payload.get("person_id"), interaction_kind=payload.get("interaction_kind", "direct"),
                                            audience_id=payload.get("audience_id"))
                elif payload.get("kind") == "event":
                    from .live import process_event
                    response = {"ok": True, **process_event(self.pack, payload["event"], brain=self.brain, request_id=identifier)}
                elif payload.get("kind") == "memory_revision":
                    response = self.memories("revise", memory_id=payload["memory_id"], text=payload["text"],
                                             reason=payload["reason"], change_type=payload["change_type"],
                                             effective_on=payload.get("effective_on", ""), request_id=identifier)
                elif payload.get("kind") == "fact_edit":
                    from .facts import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "fact_time_edit":
                    from .fact_dates import perform
                    response = {"ok": True, **perform(self.pack, payload["data"], request_id=identifier)}
                elif payload.get("kind") == "learning_edit":
                    from .learning import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "reminder_edit":
                    from .hands import schedule
                    response = {"ok": True, **schedule(self.pack, payload["data"], request_id=identifier)}
                elif payload.get("kind") == "reminder_change":
                    from .reminder_changes import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "relationship_edit":
                    from .relationships import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "disclosure_edit":
                    from .disclosure import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "life_story_edit":
                    from .life_story import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "media_edit":
                    from .media_archive import perform
                    response = {"ok": True, **perform(self.pack, payload["action"], payload["data"], request_id=identifier)}
                elif payload.get("kind") == "media_intake":
                    from .media_intake import resume
                    response = {"ok": True, **resume(self.pack, identifier)}
                elif payload.get("kind") == "practice":
                    from .learning import practice
                    response = {"ok": True, **practice(self.pack, payload["goal_id"], payload["work_kind"],
                                                       payload["topic"], self.brain, request_id=identifier,
                                                       criteria_id=payload.get("criteria_id", ""))}
                else:
                    raise SeedError("这个请求的恢复方式尚不支持。")
            elif op == "image":
                response = self.image(
                    str(request.get("path") or ""),
                    str(request.get("note") or ""),
                    None if "vision" not in request else bool(request.get("vision")),
                    person_id=request.get("person_id", "owner"), audience_id=request.get("audience_id"),
                    request_id=str(request.get("request_id") or ""),
                )
            elif op == "sound":
                response = self.sound(str(request.get("path") or ""), str(request.get("note") or ""),
                                      person_id=request.get("person_id", "owner"), audience_id=request.get("audience_id"),
                                      request_id=str(request.get("request_id") or ""))
            elif op == "feed":
                response = self.feed(request.get("items"), str(request.get("source") or ""))
            elif op == "day":
                response = self.day(request.get("days", 1))
            elif op == "tick":
                response = self.tick(request.get("now"))
            elif op == "event":
                response = self.event(
                    str(request.get("kind") or ""),
                    str(request.get("text") or ""),
                    str(request.get("source") or ""),
                    bool(request.get("process", True)),
                )
            elif op == "reminder":
                response = self.reminder(
                    str(request.get("action") or "list"),
                    str(request.get("text") or ""),
                    request.get("due_day"),
                    str(request.get("reminder_id") or request.get("id") or ""),
                    due_on=request.get("due_on"), request_id=str(request.get("request_id") or ""),
                    expected=request.get("expected", ""), reason=request.get("reason", ""),
                )
            elif op == "promise":
                response = self.promise(
                    str(request.get("action") or "list"),
                    str(request.get("text") or ""),
                    request.get("due_day"),
                    str(request.get("id") or request.get("promise_id") or ""),
                    str(request.get("note") or ""),
                )
            elif op == "memorial":
                response = self.memorial(
                    str(request.get("action") or "list"),
                    str(request.get("name") or ""),
                    str(request.get("text") or ""),
                    request.get("day"),
                    str(request.get("kind") or ""),
                    str(request.get("note") or ""),
                    request.get("index"),
                )
            elif op == "inner":
                response = self.inner(
                    str(request.get("action") or "status"),
                    str(request.get("note") or ""),
                    str(request.get("text") or ""),
                    str(request.get("old") or ""),
                    str(request.get("new") or ""),
                )
            elif op == "work":
                response = self.work(
                    str(request.get("action") or "list"),
                    str(request.get("kind") or ""),
                    str(request.get("title") or ""),
                    str(request.get("id") or request.get("work_id") or ""),
                    request.get("limit"),
                )
            elif op == "friend":
                response = self.friend(
                    str(request.get("action") or "list"),
                    str(request.get("other") or ""),
                    str(request.get("friend") or ""),
                    str(request.get("note") or ""),
                    str(request.get("letter") or ""),
                )
            elif op == "persona":
                response = self.persona(str(request.get("action") or "check"))
            elif op == "semantic":
                from .semantic import manage
                response = {"ok": True, "semantic": manage(self.pack, str(request.get("action") or "status"))}
            elif op == "facts":
                from .facts import listing, perform
                action = str(request.get("action") or "list")
                if action == "date_detail":
                    from .fact_dates import detail
                    response = {"ok": True, "fact_date": detail(self.pack, str(request.get("target") or ""))}
                elif action == "date":
                    from .fact_dates import perform as amend
                    response = {"ok": True, **amend(self.pack, request.get("data"), request_id=str(request.get("request_id") or ""))}
                elif action == "timeline":
                    from .fact_time import listing as time_listing
                    response = {"ok": True, "fact_time": time_listing(self.pack, str(request.get("query") or ""),
                                on=request.get("on", ""), slot=str(request.get("slot") or ""),
                                limit=request.get("limit", 30), offset=request.get("offset", 0),
                                record_offset=request.get("record_offset", 0))}
                elif action == "list":
                    response = {"ok": True, "facts": listing(self.pack, str(request.get("query") or ""),
                                audit=request.get("audit") is True, limit=request.get("limit", 100),
                                offset=request.get("offset", 0))}
                else:
                    data = request.get("data")
                    if not isinstance(data, dict):
                        raise SeedError("事实修改需要 data 对象。")
                    response = {"ok": True, **perform(self.pack, action, data, request_id=str(request.get("request_id") or ""))}
            elif op == "media":
                from .media_archive import listing, detail, perform, export
                action = str(request.get("action") or "list")
                if action in ("probe_intake", "resume_intake", "cancel_intake"):
                    from . import media_intake
                    identifier = str(request.get("request_id") or "")
                    if action == "probe_intake":
                        expected = request.get("expected")
                        if not isinstance(expected, dict):
                            raise SeedError("材料投递查询需要 expected 对象。")
                        response = {"ok": True, **media_intake.probe(self.pack, identifier, expected=expected)}
                    elif action == "resume_intake":
                        response = {"ok": True, **media_intake.resume(self.pack, identifier)}
                    else:
                        response = {"ok": True, **media_intake.cancel(self.pack, identifier)}
                elif action == "list":
                    response = {"ok": True, "media": listing(self.pack, query=request.get("query", ""),
                                offset=request.get("offset", 0), limit=request.get("limit", 30))}
                elif action == "detail":
                    response = {"ok": True, "media_detail": detail(self.pack, str(request.get("asset_id") or ""))}
                elif action == "export":
                    response = {"ok": True, **export(self.pack, str(request.get("asset_id") or ""))}
                else:
                    response = {"ok": True, **perform(self.pack, action, request.get("data"), request_id=str(request.get("request_id") or ""))}
            elif op == "life_story":
                from .life_story import listing, perform, export
                action = str(request.get("action") or "list")
                if action == "list":
                    response = {"ok": True, "life_story": listing(self.pack, query=request.get("query", ""),
                                offset=request.get("offset", 0), limit=request.get("limit", 30),
                                source_offset=request.get("source_offset", 0), history=request.get("history") is True)}
                elif action == "export":
                    response = {"ok": True, **export(self.pack, request.get("destination") or None)}
                else:
                    response = {"ok": True, **perform(self.pack, action, request.get("data"), request_id=str(request.get("request_id") or ""))}
            elif op == "disclosure":
                from .disclosure import listing, perform
                action = str(request.get("action") or "list")
                if action == "list":
                    response = {"ok": True, "disclosure": listing(self.pack, query=request.get("query", ""),
                                offset=request.get("offset", 0), limit=request.get("limit", 30),
                                record_offset=request.get("record_offset", 0), history=request.get("history") is True)}
                else:
                    response = {"ok": True, **perform(self.pack, action, request.get("data"), request_id=str(request.get("request_id") or ""))}
            elif op == "relationships":
                from .relationships import listing, perform
                action = str(request.get("action") or "list")
                if action == "list":
                    response = {"ok": True, "relationships": listing(self.pack, str(request.get("person_id") or "owner"),
                                offset=request.get("offset", 0), limit=request.get("limit", 30), history=request.get("history") is True)}
                else:
                    response = {"ok": True, **perform(self.pack, action, request.get("data"), request_id=str(request.get("request_id") or ""))}
            elif op == "learning":
                from .learning import listing, perform, practice
                action = str(request.get("action") or "list")
                if action == "list":
                    response = {"ok": True, "learning": listing(self.pack, str(request.get("goal_id") or ""),
                                offset=request.get("offset", 0), limit=request.get("limit", 30))}
                else:
                    data = request.get("data")
                    if not isinstance(data, dict):
                        raise SeedError("练习操作需要 data 对象。")
                    identifier = str(request.get("request_id") or "")
                    result = (practice(self.pack, data.get("goal_id"), data.get("work_kind"), data.get("topic"),
                                       self.brain, request_id=identifier, criteria_id=data.get("criteria_id", "")) if action == "practice" else
                              perform(self.pack, action, data, request_id=identifier))
                    response = {"ok": True, **result}
            elif op == "memories":
                response = self.memories(
                    str(request.get("action") or "list"),
                    str(request.get("query") or ""),
                    request.get("limit", 20),
                    str(request.get("memory_id") or request.get("id") or ""),
                    str(request.get("reason") or ""),
                    text=str(request.get("text") or ""),
                    change_type=str(request.get("change_type") or "correction"),
                    effective_on=str(request.get("effective_on") or ""),
                    request_id=str(request.get("request_id") or ""),
                )
            elif op == "agency":
                response = self.agency(
                    str(request.get("action") or "list"),
                    str(request.get("text") or ""),
                    bool(request.get("force")),
                    day=request.get("day"), before=request.get("before", ""), limit=request.get("limit", 20),
                )
            elif op == "development":
                response = self.development()
            elif op == "recall":
                response = self.recall(str(request.get("query") or ""), request.get("k", 5))
            elif op == "check":
                response = self.check()
            elif op in ("stop", "bye"):
                response = {"ok": True, "bye": True}
            else:
                response = {"ok": False, "error": t("不认识的 op：{op}（可用：{join}）", op=op, join='/'.join(OPS))}
        except (SeedError, ValueError, OSError) as exc:
            response = {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - 一条请求出错，别让载体桥死掉
            response = {"ok": False, "error": t("这条请求没处理成：{exc}", exc=exc)}
        if rid is not None:
            response["id"] = rid
        return response


def _write_line(stream, payload: dict) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stream.flush()


def serve(pack_dir, brain_override: str = "") -> int:
    """stdin/stdout 上的 JSONL 循环。退出码 0；坏行不退出，只报错。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    bridge = Bridge(pack_dir, brain_override)
    while True:
        line = sys.stdin.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE and not line.endswith("\n"):
            while True:
                tail = sys.stdin.readline(MAX_LINE)
                if not tail or tail.endswith("\n"):
                    break
            _write_line(sys.stdout, {"ok": False, "id": None, "error": t("这一行太长了（最多 1MB）")})
            continue
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write_line(sys.stdout, {"ok": False, "id": None, "error": t("不是合法的 JSON")})
            continue
        response = bridge.handle(request)
        _write_line(sys.stdout, response)
        if response.get("bye"):
            return 0
