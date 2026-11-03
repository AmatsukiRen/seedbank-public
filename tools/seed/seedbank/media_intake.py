"""Durable acceptance before interpretation; retries use archived inputs.

No background retries or network calls on read. A stable request ID identifies
one delivery, not all occurrences of identical content.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

from . import experience, media_archive, requests
from .durability import in_operation, operation
from .pack_lock import serialized
from .util import SeedError, local_date, now_iso, read_json, sha256

KIND = "media_intake"


def submission(*, slots, note="", vision=None, person_id="owner", audience_id=None):
    from .disclosure import audience
    if (not isinstance(slots, list) or not slots or any(not isinstance(s, str) or s not in ("image", "sound") for s in slots)
            or len(set(slots)) != len(slots)):
        raise SeedError("材料输入需要明确的图片或声音类型。")
    if not isinstance(person_id, str) or (vision is not None and type(vision) is not bool):
        raise SeedError("材料的交流身份或视觉选项无效。")
    return {"slots": sorted(slots), "note": str(note or "").strip(), "vision": vision,
            "person_id": person_id, "audience_id": audience(person_id, audience_id)}


def _record(pack, identifier):
    record = requests.get(pack, identifier)
    payload = record["payload"]
    if (payload.get("kind") != KIND or not isinstance(payload.get("submission"), dict)
            or not isinstance(payload.get("assets"), dict) or not isinstance(payload.get("source_keys"), dict)
            or not all(isinstance(payload.get(k), str) for k in ("source", "received_at", "date", "note_event_id"))
            or type(payload.get("day")) is not int or payload["day"] < 1
            or set(payload["submission"]) != {"slots", "note", "vision", "person_id", "audience_id"}):
        raise SeedError("这不是一份完整的材料接收请求；原记录已保留。")
    expected = submission(**payload["submission"])
    if expected != payload["submission"] or set(expected["slots"]) != set(payload["assets"]):
        raise SeedError("材料请求中的类型与原件不一致。")
    for kind, reference in payload["assets"].items():
        if (not isinstance(reference, dict) or not isinstance(reference.get("id"), str) or not reference["id"]
                or not isinstance(reference.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", reference["sha256"])
                or not isinstance(payload["source_keys"].get(kind), str)):
            raise SeedError("材料请求的原件引用不完整。")
    return record


def _path_key(value):
    return sha256(os.path.normcase(str(Path(value).expanduser().absolute())))


def _available(pack, payload, identifier):
    from .disclosure import policy_for
    policy = policy_for(pack, payload["submission"]["audience_id"], payload["submission"]["person_id"])
    nodes = {e["id"]: e for e in experience.read(pack)}
    assets = {}
    for slot, reference in payload["assets"].items():
        if not isinstance(reference, dict) or not isinstance(reference.get("id"), str):
            raise SeedError("材料请求缺少原件编号。")
        row = media_archive.detail(pack, reference["id"])
        if (row["state"] != "available" or row["sha256"] != reference.get("sha256") or row["media_kind"] != slot
                or row.get("intake_id") != identifier or row["person_id"] != payload["submission"]["person_id"]
                or row["audience_id"] != payload["submission"]["audience_id"]
                or not policy.allows(nodes.get(row["event_id"], {}))):
            raise SeedError("原件已退出回忆、缺失或内容变化；停止处理与旧结果重放。")
        assets[slot] = row
    if payload["note_event_id"]:
        note = nodes.get(payload["note_event_id"], {})
        if (not policy.allows(note) or note.get("text") != payload["submission"]["note"]
                or note.get("metadata", {}).get("intake_id") != identifier
                or note.get("metadata", {}).get("audience_id") != payload["submission"]["audience_id"]):
            raise SeedError("随附说明已不可用；停止处理与旧结果重放。")
    return assets


@serialized
def submit(pack, *, image=None, sound=None, note=None, vision=None, person_id="owner", audience_id=None, request_id="", before_process=None):
    from .lifecycle import require_active
    require_active(pack)
    # Joining an outer mutation would silently destroy the acceptance guarantee.
    if in_operation():
        raise SeedError("原始材料接收必须在独立操作中进行，不能嵌入另一轮可回滚写入。")
    identifier = requests.identifier(request_id)
    sources = {k: v for k, v in (("image", image), ("sound", sound)) if v is not None}
    header = submission(slots=list(sources), note=note, vision=vision, person_id=person_id, audience_id=audience_id)
    existing = requests.lookup(pack, identifier)
    if existing:
        record = _record(pack, identifier)
        if record["payload"]["submission"] != header:
            raise SeedError("此材料请求已用于不同说明、类型或交流范围，请使用新的编号。")
        for kind, source in sources.items():
            file = Path(source).expanduser()
            if file.is_file():
                with file.open("rb") as stream:
                    data = stream.read(media_archive.MAX_BYTES + 1)
                if len(data) > media_archive.MAX_BYTES or sha256(data) != record["payload"]["assets"][kind]["sha256"]:
                    raise SeedError("相同请求编号对应的文件内容不同，未替换原件。")
            elif _path_key(source) != record["payload"]["source_keys"].get(kind):
                raise SeedError("重发材料不可读，请从已保存的请求继续处理。")
        # Re-delivery acknowledges accepted work. Only an explicit resume may
        # restart a previously interrupted model invocation.
        return probe(pack, identifier, expected=header)
    if any(r.get("intake_id") == identifier for r in media_archive.read(pack)):
        raise SeedError("这份材料的接收记录仍在，但请求文件缺失；未重复接收，请先保留档案副本。")
    from .cognition import open_day
    from .disclosure import stamp
    from .relationships import person
    if not read_json(Path(pack) / "birth.json"):
        raise SeedError("不是生命包：缺少出生记录。")
    if person_id:
        person(pack, person_id)
    with operation(pack, "media_accept"):
        day = open_day(pack)
        # Receipt evidence lives in the ledger even before a current diary page
        # exists. Calendar bookkeeping is allowed only after this commit.
        source = "mind/media.jsonl"
        assets = {}
        for kind, file in sources.items():
            row, _, _ = media_archive.capture(pack, file, kind=kind, day=day["dayNo"], source=source,
                audience_id=header["audience_id"], person_id=person_id, intake_id=identifier)
            assets[kind] = {"id": row["id"], "sha256": row["sha256"]}
        note_event_id = ""
        if header["note"]:
            event = experience.record(pack, kind="conversation", text=header["note"], day=day["dayNo"], source="mind/experiences.jsonl",
                actor="user", metadata={**stamp(header["audience_id"]), "person_id": person_id,
                    "intake_id": identifier, "input_role": "media_note"})
            note_event_id = event["id"]
        received_at = now_iso()
        payload = {"kind": KIND, "submission": header, "assets": assets, "note_event_id": note_event_id,
                   "source_keys": {k: _path_key(v) for k, v in sources.items()}, "received_at": received_at,
                   "source": source, "day": day["dayNo"], "date": local_date(received_at)}
        requests.prepare(pack, payload, request_id=identifier)
    try:
        if before_process is not None:
            before_process()
        return resume(pack, identifier)
    except Exception as error:
        raise SeedError(f"原件已保存，分析尚未完成。可在「原始图片与声音」继续处理（请求 {identifier}）。{error}") from error


@serialized
def resume(pack, identifier):
    from .lifecycle import require_active
    require_active(pack)
    record = _record(pack, identifier)
    payload = record["payload"]
    if record["status"] == "complete" and record["result"].get("cancelled"):
        return {**record["result"], "requestId": identifier, "replayed": True}
    assets = _available(pack, payload, identifier)  # Also applies before completed replay.
    from .cognition import _sense_media

    def process():
        result = _sense_media(pack, note=payload["submission"]["note"], vision=payload["submission"]["vision"],
                             person_id=payload["submission"]["person_id"], audience_id=payload["submission"]["audience_id"],
                             intake={"id": identifier, "payload": payload, "assets": assets})
        # Retain result dependencies so a later withdrawn interpretation cannot
        # escape through the saved delivery receipt.
        result["intake_id"] = identifier
        return result

    if record["status"] == "complete":
        from .disclosure import policy_for
        policy = policy_for(pack, payload["submission"]["audience_id"], payload["submission"]["person_id"])
        events = {e["id"]: e for e in experience.read(pack)}
        if any(key not in events or not policy.allows(events[key]) for key in record["result"].get("event_ids", [])):
            raise SeedError("旧解释已退出回忆，不能重放。原件与历史仍保留。")
    return requests.run(pack, payload, process, request_id=identifier)


@serialized
def probe(pack, identifier, *, expected):
    """Transport read/replay only: pending delivery never restarts a model."""
    if not identifier:
        return {"found": False}
    record = requests.lookup(pack, identifier)
    if record is None:
        return {"found": False}
    record = _record(pack, identifier)
    if record["payload"]["submission"] != submission(**expected):
        raise SeedError("材料请求的交流范围或内容不匹配。")
    if record["status"] == "complete":
        return {"found": True, "pending": False, **resume(pack, identifier)}
    return {"found": True, "pending": True, "requestId": identifier,
            "replayed": True, "dayNo": record["payload"]["day"], "date": record["payload"]["date"],
            "file": record["payload"]["source"], "memoriesAdded": 0, "vision": {},
            "assets": [r["id"] for r in record["payload"]["assets"].values()],
            "lines": ["材料已保存，等待在本机继续处理。"]}


@serialized
def cancel(pack, identifier):
    record = _record(pack, identifier)
    if record["status"] == "complete":
        if record["result"].get("cancelled"):
            return {**record["result"], "requestId": identifier, "replayed": True}
        raise SeedError("这份材料已经处理完成；如不再使用，请放下对应材料。")
    payload = record["payload"]

    def finish():
        from .cognition import open_day, _memory_filename
        from .disclosure import stamp
        day = open_day(pack)
        experience.record(pack, kind="media_cancel", text="用户停止一份材料的后续分析，原件仍保留。",
            day=day["dayNo"], source=f"life/{_memory_filename(day['dayNo'], day['date'])}", actor="user",
            metadata={**stamp("owner"), "intake_id": identifier})
        return {"cancelled": True, "dayNo": payload["day"], "date": payload["date"], "file": payload["source"],
                "lines": ["材料已保存，后续处理已停止。"], "memoriesAdded": 0, "vision": {},
                "assets": [r["id"] for r in payload["assets"].values()]}

    return requests.run(pack, payload, finish, request_id=identifier)


def summary(pack, identifier):
    if not identifier:
        return {"state": "legacy", "request_id": ""}
    try:
        record = _record(pack, identifier)
    except (SeedError, OSError, ValueError, TypeError, KeyError):
        return {"state": "unavailable", "request_id": identifier}
    return {"state": "pending" if record["status"] == "pending" else "cancelled" if record["result"].get("cancelled") else "complete",
            "request_id": identifier, "received_at": record["payload"]["received_at"],
            "vision": record.get("result", {}).get("vision", {})}
