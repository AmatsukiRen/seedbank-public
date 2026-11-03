"""Original sensory inputs, separate receipts, and later interpretations.

Blobs are immutable and content addressed. A receipt is scoped to one exchange;
sharing an interpretation never authorizes access to the underlying file.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sqlite3
import uuid

from . import experience, jsonl, requests
from .durability import _safe_path, before_write, replace_bytes
from .pack_lock import durable, serialized
from .util import SeedError, canonical_json, now_iso, sha256

FORMAT = "seedbank/media@1"
MAX_BYTES = 64 * 1024 * 1024
CHUNK = 1024 * 1024
TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "bmp": "image/bmp",
         "ppm": "image/x-portable-pixmap", "pgm": "image/x-portable-graymap", "wav": "audio/wav"}


def path(pack):
    return Path(pack) / "mind" / "media.jsonl"


def _validate(row, number):
    valid = (isinstance(row, dict) and row.get("format") == FORMAT and row.get("kind") in ("receipt", "forget")
             and all(isinstance(row.get(k), str) and row[k] for k in ("id", "at", "event_id")))
    if valid and row["kind"] == "receipt":
        valid = (all(isinstance(row.get(k), str) for k in
                     ("name", "sha256", "extension", "mime", "blob", "source", "audience_id", "person_id", "media_kind"))
                 and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) and row["extension"] in TYPES
                 and row["mime"] == TYPES[row["extension"]] and row["media_kind"] in ("image", "sound")
                 and (row["extension"] == "wav") == (row["media_kind"] == "sound")
                 and row["blob"] == f"media/{row['sha256'][:2]}/{row['sha256']}.{row['extension']}"
                 and type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX_BYTES
                 and type(row.get("day")) is int and row["day"] > 0
                 and ("intake_id" not in row or (isinstance(row["intake_id"], str) and 0 < len(row["intake_id"]) <= 200)))
    elif valid:
        valid = all(isinstance(row.get(k), str) and row[k] for k in ("asset_id", "reason"))
    if not valid:
        raise SeedError(f"第 {number} 条原始材料记录不完整；原文件已保留。")


def read(pack):
    rows = jsonl.read(path(pack), _validate)
    known, receipts, forgotten = set(), set(), set()
    for row in rows:
        if row["id"] in known:
            raise SeedError("原始材料编号重复；原文件已保留。")
        known.add(row["id"])
        if row["kind"] == "receipt":
            receipts.add(row["id"])
        else:
            if row["asset_id"] not in receipts or row["asset_id"] in forgotten:
                raise SeedError("放下的原始材料不存在或已放下；原文件已保留。")
            forgotten.add(row["asset_id"])
    return rows


def _digest(row):
    return sha256(canonical_json(row))


def _signature(file):
    stat = file.stat()
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"


def _cache(pack):
    file = _safe_path(Path(pack).resolve(), "mind/media-cache.sqlite3")
    db = sqlite3.connect(file, timeout=1)
    try:
        db.execute("PRAGMA cache_size=-2048")
        db.execute("CREATE TABLE IF NOT EXISTS blobs (path TEXT PRIMARY KEY, signature TEXT, digest TEXT)")
        return db
    except BaseException:
        db.close()
        raise


def _status(pack, row, *, force=False, db=None):
    try:
        file = _safe_path(Path(pack).resolve(), row["blob"])
        if not file.is_file():
            return "missing"
        before = _signature(file)
        if file.stat().st_size != row["bytes"]:
            return "changed"
        cached = db.execute("SELECT signature,digest FROM blobs WHERE path=?", (row["blob"],)).fetchone() if db and not force else None
        if cached and cached[0] == before:
            digest = cached[1]
        else:
            hashed = hashlib.sha256()
            with file.open("rb") as source:
                remaining = MAX_BYTES + 1
                while remaining:
                    block = source.read(min(CHUNK, remaining))
                    if not block:
                        break
                    hashed.update(block)
                    remaining -= len(block)
            digest = hashed.hexdigest()
            if _signature(file) != before or remaining == 0:
                return "changed"
            if db:
                db.execute("INSERT OR REPLACE INTO blobs VALUES (?,?,?)", (row["blob"], before, digest))
        return "available" if digest == row["sha256"] else "changed"
    except sqlite3.Error:
        return _status(pack, row, force=True)
    except (OSError, SeedError):
        return "unavailable"


def _states(pack, rows, *, force_id="", originals=None):
    receipts = [r for r in rows if r["kind"] == "receipt"]
    forgotten = {r["asset_id"] for r in rows if r["kind"] == "forget"}
    nodes = originals
    if nodes is None:
        nodes = {r["id"]: r for r in experience.read(pack)} if rows else {}
    db = None
    try:
        if receipts:
            try:
                db = _cache(pack)
            except (sqlite3.Error, OSError, SeedError):
                pass  # A corrupt cache is preserved; source bytes remain authoritative.
        states = {}
        for row in receipts:
            event = nodes.get(row["event_id"], {})
            bound = (event.get("kind") == "media_input" and event.get("metadata", {}).get("media_digest") == _digest(row))
            states[row["id"]] = ("forgotten" if row["id"] in forgotten else "unbound" if not bound
                                  else _status(pack, row, force=row["id"] == force_id, db=db))
        return states
    finally:
        if db:
            try:
                db.commit()
            except sqlite3.Error:
                pass
            db.close()


def suppressed_ids(pack, *, sources=None):
    # No MemoryPolicy here: this function is a source of that policy.
    from .memory_sources import PolicySources
    sources = sources if sources is not None else PolicySources(pack)
    rows = read(pack)
    states = _states(pack, rows, originals=sources.originals if rows else {})
    return {r["event_id"] for r in rows if r["kind"] == "receipt" and states[r["id"]] != "available"}


def _extension(data, kind):
    if kind == "sound" and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if kind == "image":
        for signature, extension in ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8", "jpg"), (b"BM", "bmp"),
                                     (b"P6", "ppm"), (b"P5", "pgm")):
            if data.startswith(signature):
                return extension
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp"
    raise SeedError("材料格式不支持；图片使用 PNG / JPEG / WebP / BMP / PPM / PGM，声音使用 WAV。")


@durable
def capture(pack, source_path, *, kind, day, source, audience_id, person_id, intake_id=""):
    from .disclosure import stamp
    original = Path(source_path).expanduser()
    try:
        before = _signature(original)
        if not original.is_file() or original.stat().st_size > MAX_BYTES:
            raise SeedError("原始材料需要是 64 MiB 以内的文件。")
        with original.open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES or _signature(original) != before:
            raise SeedError("原始材料为空、过大或读取期间发生变化，请重新选择。")
    except OSError as error:
        raise SeedError("原始材料无法读取，请重新选择文件。") from error
    extension, digest = _extension(data, kind), sha256(data)
    blob = f"media/{digest[:2]}/{digest}.{extension}"
    target = _safe_path(Path(pack).resolve(), blob)
    row = {"format": FORMAT, "id": "media_" + uuid.uuid4().hex, "kind": "receipt", "at": now_iso(),
           "event_id": "x_" + uuid.uuid4().hex, "name": original.name[:240], "sha256": digest,
           "extension": extension, "mime": TYPES[extension], "blob": blob, "bytes": len(data),
           "day": int(day), "source": source, "audience_id": audience_id, "person_id": person_id,
           "media_kind": kind}
    if intake_id:
        row["intake_id"] = intake_id
    if target.exists():
        if _status(pack, row, force=True) != "available":
            raise SeedError("已保存的同指纹材料发生变化；保留原件，请先处理档案异常。")
    else:
        before_write(target, data)
        replace_bytes(target, data)
    event = experience.record(pack, kind="media_input", text=f"收到一份{'图片' if kind == 'image' else '声音'}原始材料：{row['name']}。接收时间不等于拍摄或录制时间。",
                              day=day, source=source, actor="user", identifier=row["event_id"], occurred_at=row["at"],
                              metadata={**stamp(audience_id), "person_id": person_id, "asset_id": row["id"],
                                        "media_digest": _digest(row), "intake_id": intake_id})
    jsonl.append(pack, path(pack), [row], _validate)
    return row, target, event


@serialized
def detail(pack, identifier):
    rows = read(pack)
    row = next((r for r in rows if r["id"] == identifier and r["kind"] == "receipt"), None)
    if not row:
        raise SeedError("没有找到这份原始材料。")
    state = _states(pack, rows, force_id=identifier)[identifier]
    from .memory_state import MemoryPolicy
    policy = MemoryPolicy.load(pack)
    if state == "available" and row["event_id"] in policy.blocked:
        state = "withheld"
    events = [{"id": e["id"], "text": e["text"], "at": e["recorded_at"], "kind": e["kind"],
               "metadata": e.get("metadata", {}), "recallable": policy.allows(e)}
              for e in experience.read(pack) if e.get("metadata", {}).get("asset_id") == identifier]
    from .media_intake import summary as intake_summary
    return {**row, "state": state, "events": events, "processing": intake_summary(pack, row.get("intake_id", "")),
            "forgotten": any(r.get("asset_id") == identifier for r in rows if r["kind"] == "forget")}


@serialized
def listing(pack, *, query="", offset=0, limit=30):
    rows = read(pack)
    states = _states(pack, rows)
    receipts = [{**r, "state": states[r["id"]]} for r in reversed(rows) if r["kind"] == "receipt"
                and str(query).casefold() in (r["name"] + " " + r["at"] + " " + r["id"]).casefold()]
    offset, limit = max(0, int(offset)), max(1, min(100, int(limit)))
    from .media_intake import summary as intake_summary
    selected = [{**r, "processing": intake_summary(pack, r.get("intake_id", ""))} for r in receipts[offset:offset + limit]]
    return {"records": selected, "total": len(receipts), "offset": offset, "query": str(query),
            "pending": [r for r in requests.pending(pack) if r["payload"].get("kind") in ("media_edit", "media_intake")]}


@serialized
def perform(pack, action, data, *, request_id=""):
    if not isinstance(data, dict) or action not in ("forget", "revisit"):
        raise SeedError("原始材料操作需要 forget / revisit 和 data 对象。")
    identifier = str(data.get("asset_id") or "")
    note = str(data.get("note") or "").strip()
    reason = str(data.get("reason") or "").strip()
    if len(note) > 2000 or len(reason) > 1000 or (action == "forget" and not reason):
        raise SeedError("放下需要理由（最多 1000 字）；重新查看的说明最多 2000 字。")
    # Re-check before completed-request replay, too: old results cannot revive a withdrawn input.
    current = detail(pack, identifier)
    if action == "revisit" and current["processing"]["state"] == "pending":
        raise SeedError("这份材料还在等待首次处理，请先继续处理或选择只保留原件。")
    if action == "revisit" and (current["state"] != "available" or current["media_kind"] != "image"):
        raise SeedError("当前材料不可用于重新理解；原始记录仍保留。")
    payload = {"kind": "media_edit", "action": action, "data": {"asset_id": identifier, "note": note, "reason": reason}}

    def mutate():
        if action == "revisit":
            from .cognition import sense_media
            return sense_media(pack, review_asset=identifier, note=note)
        if current["forgotten"]:
            raise SeedError("这份材料已放下。")
        from .disclosure import stamp
        from .cognition import open_day, _memory_filename
        day = open_day(pack)
        row = {"format": FORMAT, "id": "media_" + uuid.uuid4().hex, "kind": "forget", "at": now_iso(),
               "event_id": "x_" + uuid.uuid4().hex, "asset_id": identifier, "reason": reason}
        experience.record(pack, kind="media_forget", text="用户放下一份原始材料；原件和历史解释保留供本人查看。",
                          day=day["dayNo"], source=f"life/{_memory_filename(day['dayNo'], day['date'])}", actor="user", identifier=row["event_id"],
                          metadata={**stamp("owner"), "person_id": "owner", "asset_id": identifier, "reason": reason,
                                    "received_audience_id": current["audience_id"]})
        jsonl.append(pack, path(pack), [row], _validate)
        return {"asset_id": identifier, "forgotten": True}

    return requests.run(pack, payload, mutate, request_id=request_id)


@serialized
def export(pack, identifier):
    """Local owner's explicit audit export, including set-aside originals."""
    row = detail(pack, identifier)
    receipt = next(r for r in read(pack) if r["id"] == identifier)
    event = next((e for e in experience.read(pack) if e["id"] == row["event_id"]), {})
    if (_status(pack, row, force=True) != "available"
            or event.get("metadata", {}).get("media_digest") != _digest(receipt)):
        raise SeedError("原件缺失或内容已变，无法导出。")
    source = _safe_path(Path(pack).resolve(), row["blob"])
    with source.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) != row["bytes"] or sha256(data) != row["sha256"]:
        raise SeedError("原件读取期间发生变化，未导出。")
    folder = Path(pack).resolve().parent / "SEEDbank-media-exports"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{row['id']}-{uuid.uuid4().hex[:8]}.{row['extension']}"
    with destination.open("xb") as handle:
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            destination.unlink(missing_ok=True)
            raise
    return {"file": str(destination), "asset_id": identifier}
