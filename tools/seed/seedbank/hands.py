"""Reminders preserve what was requested and when it was recorded locally.

New reminders use explicit calendar dates (hands@2). Legacy due_day values keep
their page-number meaning. An offline calendar deadline remains pending; it is
not evidence of fault, regret, external delivery, or the user's acknowledgement.

文件：`<pack>/mind/hands.json`

    {
      "format": "seedbank/hands@1",
      "reminders": [
        {"id": "r_0001", "text": "明天提醒他浇花", "due_day": 5,
         "created_day": 2, "status": "pending", "said_day": null,
         "created_at": "...", "updated_at": "..."}
      ],
      "updated_at": "..."
    }
"""

from __future__ import annotations

from .i18n import t
import re
from pathlib import Path
from .pack_lock import durable, serialized
from .durability import RecoveryRequired
from . import deadlines

from .util import SeedError, canonical_json, mulberry32, now_iso, read_json, sha256, write_json_atomic

HANDS_FORMAT = "seedbank/hands@1"
CALENDAR_FORMAT = "seedbank/hands@2"
REVISION_FORMAT = "seedbank/hands@3"
REMINDER_MAX = 64
TEXT_CHARS = 120
STATUSES = ("pending", "said", "missed", "cancelled")

_RID = re.compile(r"^r_(\d{4,})$")


def hands_path(pack_dir) -> Path:
    return Path(pack_dir) / "mind" / "hands.json"


def _default_hands() -> dict:
    return {"format": HANDS_FORMAT, "reminders": [], "updated_at": None}


def _clean_text(value, limit: int = TEXT_CHARS) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"\s{2,}", " ", text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def load_hands(pack_dir) -> dict:
    path = hands_path(pack_dir)
    if not path.is_file():
        return _default_hands()
    return _normalize(read_json(path))


def _normalize(data):
    if not isinstance(data, dict) or not isinstance(data.get("reminders"), list):
        raise SeedError(t("mind/hands.json 坏了：不是一个带 reminders 列表的对象"))
    data.setdefault("format", HANDS_FORMAT)
    if data["format"] not in (HANDS_FORMAT, CALENDAR_FORMAT, REVISION_FORMAT):
        raise SeedError("提醒文件版本不受支持；原文件已保留。")
    data.setdefault("updated_at", None)
    reminders = []
    identifiers = set()
    for raw in data["reminders"]:
        if not isinstance(raw, dict):
            if data["format"] == REVISION_FORMAT:
                raise SeedError("提醒记录不完整；原文件已保留。")
            continue
        if data["format"] == REVISION_FORMAT:
            if (not isinstance(raw.get("id"), str) or not _RID.fullmatch(raw["id"])
                    or raw["id"] in identifiers
                    or not isinstance(raw.get("text"), str) or not raw["text"].strip()
                    or len(raw["text"]) > TEXT_CHARS or raw.get("status") not in STATUSES
                    or type(raw.get("created_day")) is not int or raw["created_day"] < 1
                    or (not raw.get("due_on") and (type(raw.get("due_day")) is not int or raw["due_day"] < 1))):
                raise SeedError("提醒记录不完整；原文件已保留。")
        from .reminder_changes import validate
        validate(raw, data["format"])
        text = _clean_text(raw.get("text"))
        calendar = any(key in raw for key in ("due_on", "created_on", "said_on", "said_via"))
        if calendar:
            validate_calendar(raw, data["format"])
        try:
            due_day = None if calendar else int(raw.get("due_day"))
        except (TypeError, ValueError):
            continue
        if not text or (not calendar and due_day < 1):
            continue
        reminder = {**raw,
            "id": str(raw.get("id") or f"r_{len(reminders) + 1:04d}"),
            "text": text,
            "due_day": due_day,
            "created_day": int(raw.get("created_day") or 1),
            "status": str(raw.get("status") or "pending"),
            "said_day": raw.get("said_day"),
            "created_at": raw.get("created_at") or None,
            "updated_at": raw.get("updated_at") or None,
        }
        if reminder["status"] not in STATUSES:
            reminder["status"] = "pending"
        identifiers.add(reminder["id"])
        reminders.append(reminder)
    data["reminders"] = reminders
    return data


@durable
def save_hands(pack_dir, data: dict) -> dict:
    path = hands_path(pack_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["format"] = (REVISION_FORMAT if data.get("format") == REVISION_FORMAT else
                         CALENDAR_FORMAT if data.get("format") == CALENDAR_FORMAT or any(r.get("due_on") for r in data.get("reminders", [])) else HANDS_FORMAT)
    payload["updated_at"] = now_iso()
    payload["reminders"] = list(payload.get("reminders") or [])
    if payload["format"] == REVISION_FORMAT:
        payload = _normalize(payload)
    write_json_atomic(path, payload)
    return payload


def _next_id(reminders: list) -> str:
    biggest = 0
    for reminder in reminders:
        match = _RID.match(str(reminder.get("id") or ""))
        if match:
            biggest = max(biggest, int(match.group(1)))
    return f"r_{biggest + 1:04d}"


@durable
def add_reminder(pack_dir, text, due_day: int | None = None, *, due_on=None, created_day: int | None = None, at: str | None = None) -> dict:
    """让她记着：到 due_day 要提醒主人一件事。"""
    clean = _clean_text(text)
    if not clean:
        raise SeedError(t("要她记着的事不能为空"))
    calendar = due_on is not None
    if calendar:
        due_on = deadlines.calendar_date(due_on)
        if due_day is not None:
            raise SeedError("日历日期与旧日页期限不能同时填写。")
        due = None
    else:
        if isinstance(due_day, bool):
            raise SeedError(t("--due-day 要一个天数（今天 = 当前第几天）"))
        try:
            due = int(due_day)
        except (TypeError, ValueError):
            raise SeedError(t("--due-day 要一个天数（今天 = 当前第几天）")) from None
        if due < 1:
            raise SeedError(t("--due-day 必须是大于零的天数"))
    if created_day is None:
        from .cognition import open_day
        created_day = int(open_day(pack_dir)["dayNo"])
    if not calendar and due < int(created_day):
        raise SeedError(t("第 {due} 天已经过去了（她那里现在是第 {created_day} 天）", due=due, created_day=created_day))
    created_on = deadlines.page_date(pack_dir, int(created_day)) if calendar else None
    if calendar and (not created_on or due_on < created_on):
        raise SeedError("提醒日期不能早于当前记录日，且当前日页必须有明确日期。")
    data = load_hands(pack_dir)
    if sum(item["status"] == "pending" for item in data["reminders"]) >= REMINDER_MAX:
        raise SeedError(t("她手里最多记着 {REMINDER_MAX} 件事，先完成/错过一些吧", REMINDER_MAX=REMINDER_MAX))
    now = at or now_iso()
    reminder = {
        "id": _next_id(data["reminders"]),
        "text": clean,
        "due_day": due,
        "created_day": int(created_day),
        "status": "pending",
        "said_day": None,
        "created_at": now,
        "updated_at": now,
    }
    if calendar:
        reminder.update(due_on=due_on, created_on=created_on, said_on=None, said_via="")
    data["reminders"].append(reminder)
    save_hands(pack_dir, data)
    return reminder


def list_reminders(pack_dir) -> list:
    return list(load_hands(pack_dir)["reminders"])


def find_reminder(pack_dir, reminder_id: str) -> dict | None:
    for reminder in list_reminders(pack_dir):
        if reminder["id"] == reminder_id:
            return reminder
    return None


def due_reminders(pack_dir, day_no: int) -> list:
    """今天该提醒的（还没说出口的）。"""
    on = deadlines.page_date(pack_dir, int(day_no))
    return [r for r in list_reminders(pack_dir) if r["status"] == "pending"
            and deadlines.state(r, int(day_no), on)["state"] in (("today", "overdue") if r.get("due_on") else ("today",))]


def overdue_reminders(pack_dir, day_no: int) -> list:
    on = deadlines.page_date(pack_dir, int(day_no))
    return [r for r in list_reminders(pack_dir) if r["status"] == "pending" and deadlines.state(r, int(day_no), on)["state"] == "overdue"]


@durable
def mark_said(pack_dir, reminder_id: str, day_no: int, at: str | None = None, *, via="manual") -> dict:
    data = load_hands(pack_dir)
    now = at or now_iso()
    for reminder in data["reminders"]:
        if reminder["id"] == reminder_id:
            if reminder["status"] == "said":
                return reminder
            if reminder["status"] == "cancelled":
                raise SeedError("这条提醒已取消，不能再标记为已提醒。")
            if reminder.get("due_on"):
                if via not in ("manual", "local_transcript"):
                    raise SeedError("提醒记录方式无效。")
                said_on = deadlines.page_date(pack_dir, int(day_no))
                if not said_on or said_on < reminder["created_on"]:
                    raise SeedError("当前日页日期不足以记录提醒结果。")
                reminder.update(said_on=said_on, said_via=via)
            reminder["status"] = "said"
            reminder["said_day"] = int(day_no)
            reminder["updated_at"] = now
            save_hands(pack_dir, data)
            return reminder
    raise SeedError(t("没找到这条提醒：{reminder_id}", reminder_id=reminder_id))


@durable
def sweep_missed(pack_dir, day_no: int) -> list:
    """过期的提醒：她没说出来 → 标记 missed，并在遗憾清单里留一条「没做到」。"""
    data = load_hands(pack_dir)
    missed = []
    now = now_iso()
    changed = False
    for reminder in data["reminders"]:
        if reminder.get("due_on") or reminder["status"] != "pending" or reminder["due_day"] >= int(day_no):
            continue
        reminder["status"] = "missed"
        reminder["updated_at"] = now
        missed.append(reminder)
        changed = True
    if not changed:
        return []
    save_hands(pack_dir, data)
    try:
        from .memorial import add_regret
    except Exception:  # pragma: no cover
        add_regret = None
    if add_regret is not None:
        for reminder in missed:
            try:
                add_regret(pack_dir, f"没做到：{reminder['text']}", day=int(day_no))
            except SeedError:
                pass
    return missed


def hands_summary(pack_dir, day_no: int) -> dict:
    reminders = list_reminders(pack_dir)
    on = deadlines.page_date(pack_dir, int(day_no))
    pending = [{"id": r["id"], "text": r["text"], "due_day": r["due_day"], "due_on": r.get("due_on"),
                "deadline": deadlines.state(r, int(day_no), on)} for r in reminders if r["status"] == "pending"]
    due = [r for r in pending if r["deadline"]["state"] in (("today", "overdue") if r.get("due_on") else ("today",))]
    missed = [r for r in reminders if r["status"] == "missed"]
    return {
        "due_today": due,
        "pending": pending,
        "missed": len(missed),
        "cancelled": sum(r["status"] == "cancelled" for r in reminders),
        "total": len(reminders),
    }


def describe_hands(pack_dir, day_no: int | None = None) -> str:
    if day_no is None:
        from .cognition import open_day
        day_no = int(open_day(pack_dir)["dayNo"])
    data = load_hands(pack_dir)
    lines = [t("手里的事（第 {value} 天）：", value=int(day_no))]
    if not data["reminders"]:
        lines.append(t("  她手里没有记着的事。"))
        return "\n".join(lines)
    for reminder in data["reminders"]:
        if reminder.get("due_on"):
            lines.append(f"  {reminder['id']} · {reminder['text']} · {reminder['due_on']} · " + t("已取消" if reminder["status"] == "cancelled" else reminder["status"]))
            continue
        label = {
            "pending": t("还没到 · 第 {due_day} 天", due_day=reminder['due_day']),
            "said": t("说过了 · 第 {value} 天", value=reminder.get('said_day') or '?'),
            "missed": t("错过了"),
            "cancelled": t("已取消"),
        }.get(reminder["status"], reminder["status"])
        lines.append(f"  {reminder['id']} · {reminder['text']} · {label}")
    return "\n".join(lines)


@durable
def apply_actions(pack_dir, day_no: int, at: str, actions) -> list:
    """脑在对话里提出的动作（1.17）：只收「记着」这一种，其余忽略。"""
    applied = []
    if not isinstance(actions, list):
        return applied
    for item in actions[:3]:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "remind":
            continue
        text = _clean_text(item.get("text") or item.get("what"))
        calendar = item.get("due_on") is not None
        try:
            due = None if calendar else int(item.get("due_day") or item.get("day"))
        except (TypeError, ValueError):
            continue
        if not text:
            continue
        try:
            if calendar and (item.get("due_day") is not None or item.get("day") is not None):
                continue
            reminder = add_reminder(pack_dir, text, due, due_on=item.get("due_on"), created_day=day_no, at=at)
        except RecoveryRequired:
            raise
        except SeedError:
            continue
        applied.append({"type": "remind", "id": reminder["id"], "text": reminder["text"], "due_day": reminder["due_day"], "due_on": reminder.get("due_on")})
    return applied


def hands_fingerprint(pack_dir) -> str:
    return sha256(canonical_json(load_hands(pack_dir)))


def validate_calendar(row, version):
    if version not in (CALENDAR_FORMAT, REVISION_FORMAT) or row.get("due_day") is not None:
        raise SeedError("日历提醒的版本或期限格式不完整；原文件已保留。")
    if (not isinstance(row.get("id"), str) or not _RID.fullmatch(row["id"])
            or not isinstance(row.get("text"), str) or not row["text"].strip() or len(row["text"]) > TEXT_CHARS
            or type(row.get("created_day")) is not int or row["created_day"] < 1
            or (row.get("status") in ("pending", "cancelled") and row.get("said_day") is not None)
            or (row.get("status") == "said" and (type(row.get("said_day")) is not int
                                                 or row["said_day"] < row["created_day"]))):
        raise SeedError("日历提醒的记录格式不完整；原文件已保留。")
    deadlines.calendar_date(row.get("due_on"))
    created = deadlines.calendar_date(row.get("created_on"))
    said = deadlines.calendar_date(row.get("said_on"), optional=True)
    if (created > row["due_on"] or (said and said < created)
            or row.get("status") not in (("pending", "said", "cancelled") if version == REVISION_FORMAT else ("pending", "said"))
            or row.get("said_via", "") not in ("", "manual", "local_transcript")
            or (row.get("status") == "said" and (not said or not row.get("said_via")))
            or (row.get("status") in ("pending", "cancelled") and (said is not None or row.get("said_via")))):
        raise SeedError("日历提醒的日期或记录方式无效；原文件已保留。")


@serialized
def schedule(pack, payload, *, request_id=""):
    from . import requests
    from .util import list_days
    if not isinstance(payload, dict):
        raise SeedError("提醒操作需要 data 对象。")
    data = {"text": _clean_text(payload.get("text")), "due_on": deadlines.calendar_date(payload.get("due_on"))}

    def current():
        pages = list_days(pack)
        if not data["text"] or not pages or data["due_on"] < pages[-1]["date"]:
            raise SeedError("请填写提醒内容，日期不能早于当前记录日。")
        if sum(r["status"] == "pending" for r in list_reminders(pack)) >= REMINDER_MAX:
            raise SeedError(t("她手里最多记着 {REMINDER_MAX} 件事，先完成/错过一些吧", REMINDER_MAX=REMINDER_MAX))
        return pages[-1]

    return requests.run(pack, {"kind": "reminder_edit", "data": data},
                        lambda: {"reminder": add_reminder(pack, data["text"], due_on=data["due_on"], created_day=current()["day"])},
                        request_id=request_id, validate=current)


@serialized
def cancel_pending(pack, request_id):
    from . import requests
    item = requests.get(pack, request_id)
    if item["payload"].get("kind") not in ("reminder_edit", "reminder_change"):
        raise SeedError("这不是未完成的提醒操作。")
    if item["status"] != "pending":
        if item.get("result", {}).get("cancelled"):
            return item["result"]
        raise SeedError("提醒请求已完成，不能作为未完成输入取消。")
    return requests.run(pack, item["payload"], lambda: {"cancelled": True}, request_id=request_id)
