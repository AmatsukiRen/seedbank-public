"""关系：她记得你们之间发生过什么。

1.12 起，`mind/bonds.json` 记三样东西：

- 熟悉度：认识了多少天、说过多少话、熟悉到几成；
- 承诺：谁答应了谁什么、到哪天为止、做到了没有；
- 事件：感谢、道歉、争执、和好——关系里发生过的事。

这个模块只负责**存取**。写记忆、进提示词、出现在窗口里，是上层（cognition / CLI / window）的事。
"""

from __future__ import annotations

from .i18n import t
from pathlib import Path
from .pack_lock import durable

from .util import (
    SeedError,
    expand_home,
    list_days,
    local_date,
    now_iso,
    parse_time,
    read_json,
    round2,
    write_json_atomic,
)

BONDS_FORMAT = "seedbank/bonds@1"

TEXT_CHARS = 120        # 一条承诺 / 一件事件的字数上限
MAX_PROMISES = 40       # Simultaneously pending promises; history is retained.
MAX_EVENTS = 200        # 最多记多少件关系事件

PROMISE_STATUSES = ("pending", "kept", "broken")

EVENT_KINDS = {
    "thank": "感谢",
    "apology": "道歉",
    "conflict": "争执",
    "repair": "和好",
}

DEFAULT_BONDS = {
    "format": BONDS_FORMAT,
    "owner": {
        "name": "主人",
        "since_day": 1,
        "talks": 0,
        "familiarity": 0.0,
        "last_talk_day": None,
    },
    "promises": [],
    "events": [],
}


# —— 存取 ——

def bonds_path(pack_dir) -> Path:
    return Path(expand_home(pack_dir)) / "mind" / "bonds.json"


def _clean_text(value, limit: int = TEXT_CHARS) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit].strip()


def _clean_owner(value) -> dict:
    owner = dict(DEFAULT_BONDS["owner"])
    if isinstance(value, dict):
        if value.get("name"):
            owner["name"] = _clean_text(value["name"], 24) or "主人"
        try:
            owner["since_day"] = max(1, int(value.get("since_day") or 1))
        except (TypeError, ValueError):
            pass
        try:
            owner["talks"] = max(0, int(value.get("talks") or 0))
        except (TypeError, ValueError):
            pass
        try:
            owner["familiarity"] = round2(min(1.0, max(0.0, float(value.get("familiarity") or 0.0))))
        except (TypeError, ValueError):
            pass
        owner["last_talk_day"] = value.get("last_talk_day") or None
    return owner


def _clean_promises(value) -> list[dict]:
    items: list[dict] = []
    if not isinstance(value, list):
        return items
    for item in value:
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text"))
        if not text:
            continue
        status = str(item.get("status") or "pending")
        if status not in PROMISE_STATUSES:
            status = "pending"
        record = {
            "id": str(item.get("id") or "") or f"p_{len(items) + 1:04d}",
            "text": text,
            "made_day": int(item.get("made_day") or 1),
            "due_day": int(item["due_day"]) if item.get("due_day") is not None else None,
            "status": status,
            "kept_day": int(item["kept_day"]) if item.get("kept_day") is not None else None,
            "note": _clean_text(item.get("note")),
            "created_at": str(item.get("created_at") or ""),
        }
        items.append(record)
    return items


def _clean_events(value) -> list[dict]:
    items: list[dict] = []
    if not isinstance(value, list):
        return items
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        text = _clean_text(item.get("text"))
        if kind not in EVENT_KINDS or not text:
            continue
        items.append(
            {
                "id": str(item.get("id") or "") or f"e_{len(items) + 1:04d}",
                "kind": kind,
                "text": text,
                "day": int(item.get("day") or 1),
                "at": str(item.get("at") or ""),
            }
        )
    return items


def load_bonds(pack_dir) -> dict:
    path = bonds_path(pack_dir)
    raw = read_json(path, None)
    if raw is None and not path.exists():
        raw = {}
    elif not isinstance(raw, dict) or raw.get("format") != BONDS_FORMAT:
        raise SeedError("旧关系文件格式不完整；原文件已保留。")
    if any(key in raw and not isinstance(raw[key], list) for key in ("promises", "events")):
        raise SeedError("旧关系文件格式不完整；原文件已保留。")
    return {
        "format": BONDS_FORMAT,
        "owner": _clean_owner(raw.get("owner")),
        "promises": _clean_promises(raw.get("promises")),
        "events": _clean_events(raw.get("events")),
    }


@durable
def save_bonds(pack_dir, patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise SeedError(t("关系数据必须是对象。"))
    data = load_bonds(pack_dir)
    if "owner" in patch:
        merged = dict(data["owner"])
        merged.update(patch["owner"] or {})
        data["owner"] = _clean_owner(merged)
    if "promises" in patch:
        data["promises"] = _clean_promises(patch["promises"])
    if "events" in patch:
        data["events"] = _clean_events(patch["events"])
    write_json_atomic(bonds_path(pack_dir), data)
    return data


# —— 认识与熟悉 ——

@durable
def register_talk(pack_dir, day_no: int, *, name: str = "主人") -> dict:
    """Legacy interaction count; elapsed days never certify trust or intimacy."""
    data = load_bonds(pack_dir)
    owner = dict(data["owner"])
    if name and not owner.get("name"):
        owner["name"] = _clean_text(name, 24) or "主人"
    owner["talks"] = int(owner.get("talks") or 0) + 1
    last = owner.get("last_talk_day")
    if last != int(day_no):
        owner["last_talk_day"] = int(day_no)
    data["owner"] = owner
    write_json_atomic(bonds_path(pack_dir), data)
    return data


def familiarity_percent(pack_dir) -> int:
    return int(round(float(load_bonds(pack_dir)["owner"].get("familiarity") or 0.0) * 100))


# —— 承诺 ——

@durable
def add_promise(
    pack_dir,
    text: str,
    *,
    due_day: int | None = None,
    made_day: int | None = None,
    at: str | None = None,
) -> dict:
    text = _clean_text(text)
    if not text:
        raise SeedError(t("承诺不能是空的。"))
    data = load_bonds(pack_dir)
    if sum(item["status"] == "pending" for item in data["promises"]) >= MAX_PROMISES:
        raise SeedError(t("她记的承诺太多了（上限 {MAX_PROMISES} 条）。", MAX_PROMISES=MAX_PROMISES))
    day = int(made_day or _today_day(pack_dir))
    due = int(due_day) if due_day is not None else None
    if due is not None and due < day:
        raise SeedError(t("承诺的期限不能早于今天。"))
    record = {
        "id": f"p_{len(data['promises']) + 1:04d}",
        "text": text,
        "made_day": day,
        "due_day": due,
        "status": "pending",
        "kept_day": None,
        "note": "",
        "created_at": at or now_iso(),
    }
    data["promises"].append(record)
    write_json_atomic(bonds_path(pack_dir), data)
    return record


def _find_promise(data: dict, promise_id: str) -> dict:
    for item in data["promises"]:
        if item["id"] == promise_id:
            return item
    raise SeedError(t("找不到这条承诺：{promise_id}", promise_id=promise_id))


@durable
def keep_promise(pack_dir, promise_id: str, *, day: int | None = None, note: str = "") -> dict:
    data = load_bonds(pack_dir)
    item = _find_promise(data, promise_id)
    if item["status"] != "pending":
        raise SeedError(t("这条承诺已经处理过了。"))
    item["status"] = "kept"
    item["kept_day"] = int(day or _today_day(pack_dir))
    item["note"] = _clean_text(note)
    write_json_atomic(bonds_path(pack_dir), data)
    return item


@durable
def break_promise(pack_dir, promise_id: str, *, day: int | None = None, note: str = "") -> dict:
    data = load_bonds(pack_dir)
    item = _find_promise(data, promise_id)
    if item["status"] != "pending":
        raise SeedError(t("这条承诺已经处理过了。"))
    item["status"] = "broken"
    item["kept_day"] = int(day or _today_day(pack_dir))
    item["note"] = _clean_text(note)
    write_json_atomic(bonds_path(pack_dir), data)
    # 没做到的承诺会进遗憾清单（1.13）：遗憾不是惩罚，是她记得这件事。
    try:
        from .memorial import add_regret  # 延迟导入：memorial 在顶层 import bonds? 不，它不 import；保险起见仍延迟

        add_regret(pack_dir, f"没有做到：{item['text']}", day=int(item["kept_day"] or 0))
    except SeedError:
        pass
    return item


def list_promises(pack_dir, *, status: str | None = None) -> list[dict]:
    data = load_bonds(pack_dir)
    if status is None:
        return data["promises"]
    return [item for item in data["promises"] if item["status"] == status]


def pending_promises(pack_dir) -> list[dict]:
    return list_promises(pack_dir, status="pending")


# —— 关系事件 ——

@durable
def add_event(
    pack_dir,
    kind: str,
    text: str,
    *,
    day: int | None = None,
    at: str | None = None,
) -> dict:
    kind = str(kind or "")
    if kind not in EVENT_KINDS:
        raise SeedError(t("不认识的关系事件：{kind}（可选：{join}）", kind=kind, join='/'.join(EVENT_KINDS)))
    text = _clean_text(text)
    if not text:
        raise SeedError(t("事件不能是空的。"))
    data = load_bonds(pack_dir)
    record = {
        "id": f"e_{len(data['events']) + 1:04d}",
        "kind": kind,
        "text": text,
        "day": int(day or _today_day(pack_dir)),
        "at": at or now_iso(),
    }
    data["events"].append(record)
    write_json_atomic(bonds_path(pack_dir), data)
    return record


def events_by_kind(pack_dir, kind: str) -> list[dict]:
    return [item for item in load_bonds(pack_dir)["events"] if item["kind"] == kind]


# —— 给上层的摘要 ——

def _current_day(pack_dir) -> int:
    """她现在处在第几天。

    不能只看 life/ 的最后一个文件：今天可能还没人跟她说话（还没落页），
    但「今天」已经开始了。所以以 open_day 为准（不创建文件，只算日子）。
    """
    from .cognition import open_day  # 延迟导入：cognition 在顶层 import bonds，避免循环

    return int(open_day(pack_dir)["dayNo"])


def _today_day(pack_dir) -> int:
    return _current_day(pack_dir)


def days_known(pack_dir) -> int:
    return _current_day(pack_dir)


def due_today(pack_dir) -> list[dict]:
    day = days_known(pack_dir)
    return [item for item in pending_promises(pack_dir) if item.get("due_day") == day]


def bond_summary(pack_dir) -> dict:
    data = load_bonds(pack_dir)
    owner = data["owner"]
    pending = [item for item in data["promises"] if item["status"] == "pending"]
    day = days_known(pack_dir)
    due = [item for item in pending if item.get("due_day") == day]
    return {
        "owner": owner.get("name") or "主人",
        "days": day,
        "since_day": owner.get("since_day") or 1,
        "talks": owner.get("talks") or 0,
        "familiarity": owner.get("familiarity") or 0.0,
        "pending": pending[-3:],
        "pending_count": len(pending),
        "kept_count": sum(p["status"] == "kept" for p in data["promises"]),
        "broken_count": sum(p["status"] == "broken" for p in data["promises"]),
        "recent_broken": [p for p in data["promises"] if p["status"] == "broken"][-3:],
        "due_today": due,
        "events": len(data["events"]),
    }


def describe_bonds(pack_dir) -> list[str]:
    data = load_bonds(pack_dir)
    owner = data["owner"]
    day = days_known(pack_dir)
    since = int(owner.get("since_day") or 1)
    percent = int(round(float(owner.get("familiarity") or 0.0) * 100))
    lines = [
        t("认识：从第 {since} 天到现在（第 {day} 天）", since=since, day=day),
        t("聊过 {count} 次天", count=int(owner.get('talks') or 0)),
    ]
    pending = [item for item in data["promises"] if item["status"] == "pending"]
    if pending:
        lines.append(t("还没做到的承诺：{value} 条", value=len(pending)))
        for item in pending[-3:]:
            due = f"，第 {item['due_day']} 天到期" if item.get("due_day") else ""
            lines.append(t("  · {id} {value}（第 {made_day} 天答应{due}）", id=item['id'], value=item['text'], made_day=item['made_day'], due=due))
    else:
        lines.append(t("承诺：没有还没做到的。"))
    counts = {kind: 0 for kind in EVENT_KINDS}
    for item in data["events"]:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    if data["events"]:
        parts = [f"{EVENT_KINDS[k]} {counts[k]}" for k in EVENT_KINDS if counts.get(k)]
        lines.append(t("关系里发生过：") + "、".join(parts))
    return lines
