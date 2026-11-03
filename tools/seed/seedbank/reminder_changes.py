"""Explicit user revisions of existing reminders; original requests stay in history."""
from copy import deepcopy
import re

from . import deadlines, hands, requests
from .pack_lock import serialized
from .util import SeedError, canonical_json, list_days, now_iso, read_json, sha256


def fingerprint(row):
    return sha256(canonical_json(row))


def snapshot(row):
    return {key: row.get(key) for key in ("text", "due_day", "due_on", "status")}


def _snapshot_valid(value):
    if (not isinstance(value, dict) or set(value) != {"text", "due_day", "due_on", "status"}
            or not isinstance(value["text"], str) or not value["text"].strip()
            or len(value["text"]) > hands.TEXT_CHARS or value["status"] not in ("pending", "cancelled")):
        raise SeedError("提醒修改历史不完整；原文件已保留。")
    if value["due_on"] is not None:
        deadlines.calendar_date(value["due_on"])
        if value["due_day"] is not None:
            raise SeedError("提醒修改历史的期限格式冲突；原文件已保留。")
    elif type(value["due_day"]) is not int or value["due_day"] < 1:
        raise SeedError("提醒修改历史缺少期限；原文件已保留。")


def validate(row, version):
    history = row.get("history", [])
    if ("history" in row or row.get("status") == "cancelled") and version != hands.REVISION_FORMAT:
        raise SeedError("提醒修改历史需要新版格式；原文件已保留。")
    if not isinstance(history, list) or ("history" in row and not history):
        raise SeedError("提醒修改历史不完整；原文件已保留。")
    previous = None
    for index, change in enumerate(history, 1):
        if (not isinstance(change, dict) or type(change.get("revision")) is not int
                or change["revision"] != index or change.get("action") not in ("revise", "cancel")
                or not isinstance(change.get("reason"), str) or not change["reason"].strip()
                or len(change["reason"]) > 300 or not isinstance(change.get("at"), str) or not change["at"]
                or not isinstance(change.get("request_id"), str) or not change["request_id"]
                or type(change.get("day")) is not int or change["day"] < row["created_day"]):
            raise SeedError("提醒修改历史不完整；原文件已保留。")
        on = deadlines.calendar_date(change.get("on"))
        before, after = change.get("before"), change.get("after")
        _snapshot_valid(before)
        _snapshot_valid(after)
        if before["status"] != "pending" or (previous is not None and before != previous):
            raise SeedError("提醒修改历史衔接不一致；原文件已保留。")
        if change["action"] == "cancel":
            if after != {**before, "status": "cancelled"}:
                raise SeedError("取消提醒的历史不一致；原文件已保留。")
        elif (after["status"] != "pending" or after["due_on"] is None
              or after["due_on"] < on or before == after):
            raise SeedError("提醒改期的历史不一致；原文件已保留。")
        previous = after
    if previous is not None:
        current = snapshot(row)
        # A later delivery/missed transition is allowed, never a further text/date edit.
        if previous["status"] == "pending" and row["status"] in ("said", "missed"):
            current["status"] = "pending"
            if row["status"] == "said" and (type(row.get("said_day")) is not int
                    or row["said_day"] < history[-1]["day"]
                    or (row.get("due_on") and (not isinstance(row.get("said_on"), str) or row["said_on"] < history[-1]["on"]))):
                raise SeedError("提醒当前内容与修改历史不一致；原文件已保留。")
        if current != previous:
            raise SeedError("提醒当前内容与修改历史不一致；原文件已保留。")
    elif row.get("status") == "cancelled":
        raise SeedError("已取消的提醒缺少取消记录；原文件已保留。")


def listing(pack):
    return [{**row, "expected": fingerprint(row)} for row in hands.list_reminders(pack)]


@serialized
def perform(pack, action, payload, *, request_id=""):
    if action not in ("revise", "cancel") or not isinstance(payload, dict):
        raise SeedError("提醒修改操作无效。")
    identifier, expected, reason = (payload.get(key) for key in ("reminder_id", "expected", "reason"))
    if (not isinstance(identifier, str) or not re.fullmatch(r"r_\d{4,}", identifier)
            or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 300):
        raise SeedError("请先选择当前提醒，并填写不超过 300 字的修改原因。")
    data = {"reminder_id": identifier, "expected": expected, "reason": reason.strip()}
    operation_id = requests.identifier(request_id)
    if action == "revise":
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > hands.TEXT_CHARS:
            raise SeedError("提醒内容需要 1 到 120 字。")
        data.update(text=hands._clean_text(text), due_on=deadlines.calendar_date(payload.get("due_on")))

    def current():
        raw = read_json(hands.hands_path(pack), {})
        state = hands.load_hands(pack)
        if len(raw.get("reminders", [])) != len(state["reminders"]):
            raise SeedError("提醒记录不完整；原文件已保留。")
        # Upgrade must not silently normalize away malformed or duplicate old rows.
        hands._normalize({**deepcopy(state), "format": hands.REVISION_FORMAT})
        row = next((r for r in state["reminders"] if r["id"] == identifier), None)
        if not row or fingerprint(row) != expected:
            raise SeedError("这条提醒已经变化，请刷新后重新选择；输入仍保留。")
        if row["status"] != "pending":
            raise SeedError("只能修改或取消尚未提醒的事项；已发生的记录保留。")
        pages = list_days(pack)
        if not pages:
            raise SeedError("当前日页必须有明确日期。")
        page = pages[-1]
        on = deadlines.calendar_date(page["date"])
        if page["day"] < row["created_day"]:
            raise SeedError("当前日页早于提醒创建记录。")
        if action == "revise":
            if data["due_on"] < on or (row.get("created_on") and on < row["created_on"]):
                raise SeedError("提醒日期不能早于当前记录日，且当前日页必须有明确日期。")
            if row["text"] == data["text"] and row.get("due_on") == data["due_on"]:
                raise SeedError("提醒内容和日期没有变化。")
            if not row.get("due_on") and not deadlines.page_date(pack, row["created_day"]):
                raise SeedError("旧提醒缺少明确创建日期，无法改为日历提醒；可以取消后重新建立。")
        return row, page

    def apply():
        row, page = current()
        all_rows = hands.load_hands(pack)
        row = deepcopy(row)
        before = snapshot(row)
        if action == "revise":
            row.update(text=data["text"], due_day=None, due_on=data["due_on"],
                       created_on=row.get("created_on") or deadlines.page_date(pack, row["created_day"]),
                       said_day=None, said_on=None, said_via="")
        else:
            row["status"] = "cancelled"
        row["updated_at"] = now_iso()
        history = row.setdefault("history", [])
        history.append({"revision": len(history) + 1, "action": action, "reason": data["reason"],
                        "request_id": operation_id,
                        "day": page["day"], "on": page["date"], "at": row["updated_at"],
                        "before": before, "after": snapshot(row)})
        all_rows["format"] = hands.REVISION_FORMAT
        all_rows["reminders"] = [row if item["id"] == identifier else item for item in all_rows["reminders"]]
        hands._normalize(deepcopy(all_rows))
        hands.save_hands(pack, all_rows)
        return {"reminder": row}

    return requests.run(pack, {"kind": "reminder_change", "action": action, "data": data}, apply,
                        request_id=operation_id, validate=current)
