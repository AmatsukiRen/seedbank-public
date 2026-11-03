"""Explicit, reversible dormancy. Absence and model text never choose a state."""
import json
from pathlib import Path
import uuid

from .pack_lock import durable
from .util import SeedError, local_date, now_iso, parse_time, write_json_atomic

FORMAT = "seedbank/lifecycle@1"
PAUSED = "此个体已休眠；档案仍可查看，请明确恢复后再继续活动。"
UNAVAILABLE = "生命状态记录无法读取，自动活动已停止；原文件已保留。"


def status(pack):
    path = Path(pack) / "mind/lifecycle.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"format": FORMAT, "state": "active", "revision": 0, "history": []}
    except (OSError, ValueError):
        return {"state": "unavailable", "revision": -1, "history": [], "error": UNAVAILABLE}
    try:
        if (not isinstance(raw, dict) or raw.get("format") != FORMAT
                or raw.get("state") not in ("active", "dormant")
                or type(raw.get("revision")) is not int or not isinstance(raw.get("history"), list)
                or raw["revision"] != len(raw["history"]) or not raw["history"]):
            raise ValueError
        previous, identifiers = "active", set()
        for row in raw["history"]:
            if (not isinstance(row, dict) or row.get("from") != previous
                    or row.get("to") != ("dormant" if previous == "active" else "active")
                    or row.get("actor") != "user" or not isinstance(row.get("at"), str)
                    or not isinstance(row.get("note"), str)
                    or not row["note"].strip() or not isinstance(row.get("id"), str)
                    or not row["id"] or row["id"] in identifiers):
                raise ValueError
            parse_time(row["at"])
            previous = row["to"]
            identifiers.add(row["id"])
        if previous != raw["state"]:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"state": "unavailable", "revision": -1, "history": [], "error": UNAVAILABLE}
    return raw


def active(pack):
    return status(pack)["state"] == "active"


def require_active(pack):
    state = status(pack)
    if state["state"] != "active":
        raise SeedError(state.get("error") or PAUSED)


@durable
def transition(pack, action, *, note, expected, confirmed=False, now=None):
    """User confirmation is recorded as such, never as an inferred AI decision."""
    state = status(pack)
    if state["state"] == "unavailable":
        raise SeedError(UNAVAILABLE)
    if action not in ("pause", "resume") or confirmed is not True:
        raise SeedError("请明确确认休眠或恢复。")
    if type(expected) is not int or expected != state["revision"]:
        raise SeedError("生命状态已改变，请刷新后重新确认。")
    if not isinstance(note, str) or not note.strip() or len(note) > 2000:
        raise SeedError("请填写不超过 2000 字的选择说明。")
    target = "dormant" if action == "pause" else "active"
    if target == state["state"]:
        raise SeedError("已经处于这个状态，没有重复变更。")
    at = now or now_iso()
    parse_time(at)
    if state["history"] and parse_time(at) < parse_time(state["history"][-1]["at"]):
        raise SeedError("当前时间早于上次状态变更，请核对时钟。")
    if action == "resume":
        # Advance directly to the actual date without generating the missing
        # diaries or altering previous day pages. No pending input is replayed here.
        from .clock import _resume_page, save_clock
        _resume_page(pack, local_date(at), at, None, explicit_pause=True)
        save_clock(pack, {"last_seen_date": local_date(at)})
    entry = {"id": "lc_" + uuid.uuid4().hex, "from": state["state"], "to": target,
             "at": at, "note": note.strip(), "actor": "user"}
    result = {"format": FORMAT, "state": target, "revision": state["revision"] + 1,
              "history": [*state["history"], entry]}
    write_json_atomic(Path(pack) / "mind/lifecycle.json", result)
    return result
