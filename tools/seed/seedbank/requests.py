"""Durable user input and opt-in idempotency, without automatic model retries."""
from pathlib import Path
import json
import uuid

from .durability import operation, _safe_path
from .util import SeedError, canonical_json, now_iso, sha256, write_json_atomic, delete_file_atomic

FORMAT = "seedbank/request@1"


def _path(pack, identifier, *, complete=False):
    key = sha256(str(identifier))
    folder = f"completed/{key[:2]}" if complete else "pending"
    return _safe_path(Path(pack).expanduser().resolve(), f"mind/requests/{folder}/{key}.json")


def _read(path):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SeedError("未完成输入记录无法读取；已保留原文件。") from error
    if (not isinstance(record, dict) or record.get("format") != FORMAT
            or record.get("status") not in ("pending", "complete")
            or not isinstance(record.get("payload"), dict) or not isinstance(record.get("id"), str)
            or not isinstance(record.get("created_at"), str)
            or (record.get("status") == "complete" and not isinstance(record.get("result"), dict))
            or record.get("fingerprint") != sha256(canonical_json(record["payload"]))):
        raise SeedError("输入记录格式不完整；已保留原文件。")
    return record


def identifier(value=""):
    result = str(value or ("request_" + uuid.uuid4().hex))
    if len(result) > 200 or any(ord(c) < 32 for c in result):
        raise SeedError("请求编号应为不超过 200 字的可见文本。")
    return result


def lookup(pack, request_id):
    """Return None only for a genuinely absent request, never for corrupt data."""
    key = identifier(request_id)
    complete, pending_file = _path(pack, key, complete=True), _path(pack, key)
    file = complete if complete.exists() else pending_file
    if not file.exists():
        return None
    record = _read(file)
    if record["id"] != key:
        raise SeedError("输入请求编号不匹配。")
    return record


def prepare(pack, payload, *, request_id=""):
    """Caller owns writer and, when capturing files, the acceptance transaction."""
    key = identifier(request_id)
    record = lookup(pack, key)
    fingerprint = sha256(canonical_json(payload))
    if record:
        if record["fingerprint"] != fingerprint:
            raise SeedError("这个请求编号已用于另一条内容，请使用原内容或新的编号。")
        return record
    record = {"format": FORMAT, "id": key, "status": "pending", "created_at": now_iso(),
              "payload": payload, "fingerprint": fingerprint}
    write_json_atomic(_path(pack, key), record)
    return record


def run(pack, payload, function, *, request_id="", validate=None):
    """Caller owns writer; input persists outside the mutation being retried."""
    identifier = str(request_id or ("request_" + uuid.uuid4().hex))
    if len(identifier) > 200 or any(ord(c) < 32 for c in identifier):
        raise SeedError("请求编号应为不超过 200 字的可见文本。")
    file = _path(pack, identifier)
    completed = _path(pack, identifier, complete=True)
    fingerprint = sha256(canonical_json(payload))
    record = None
    if file.exists() or completed.exists():
        record = _read(completed if completed.exists() else file)
        if record["id"] != identifier or record["fingerprint"] != fingerprint:
            raise SeedError("这个请求编号已用于另一条内容，请使用原内容或新的编号。")
        if record["status"] == "complete":
            return {**record["result"], "requestId": identifier, "replayed": True}
    if validate is not None:
        validate()
    if record is None:
        record = prepare(pack, payload, request_id=identifier)
    with operation(pack, payload.get("kind", "request")):
        result = function()
        result = {**result, "requestId": identifier, "replayed": False}
        write_json_atomic(completed, {**record, "status": "complete", "completed_at": now_iso(), "result": result})
        delete_file_atomic(file)
    return result


def pending(pack):
    directory = _safe_path(Path(pack).expanduser().resolve(), "mind/requests/pending")
    if not directory.exists():
        return []
    root = Path(pack).expanduser().resolve()
    records = [_read(_safe_path(root, path.relative_to(root).as_posix())) for path in sorted(directory.glob("*.json"))]
    return sorted((r for r in records if r["status"] == "pending"), key=lambda r: r["created_at"])


def get(pack, identifier):
    complete = _path(pack, identifier, complete=True)
    file = complete if complete.exists() else _path(pack, identifier)
    if not file.exists():
        raise SeedError("没有这个输入请求。")
    record = _read(file)
    if record["id"] != str(identifier):
        raise SeedError("输入请求编号不匹配。")
    return record
