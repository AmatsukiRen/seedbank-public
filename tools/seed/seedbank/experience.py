"""Portable, runtime-authored experience records beside the readable diary.

The original event is distinct from a model's interpretation. No historical
Markdown is rewritten or migrated on read. Records use opaque stable IDs.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from .util import SeedError, now_iso
from . import jsonl
from .pack_lock import serialized

FORMAT = "seedbank/experience@1"


def path(pack):
    return Path(pack) / "mind" / "experiences.jsonl"


def read(pack):
    return jsonl.read(path(pack), _validate)


def _validate(row, number):
    if (not isinstance(row, dict) or row.get("format") != FORMAT
            or not isinstance(row.get("id"), str) or not row["id"]
            or not isinstance(row.get("day"), int)
            or not all(isinstance(row.get(key), str) for key in ("kind", "text", "source", "actor", "occurred_at"))
            or not isinstance(row.get("depends_on", []), list)
            or not all(isinstance(ref, str) for ref in row.get("depends_on", []))
            or not isinstance(row.get("metadata", {}), dict)):
        raise SeedError(f"第 {number} 条经历记录格式不完整；原文件已保留。")


@serialized
def record(pack, *, kind, text, day, source, actor="runtime", depends_on=(),
           occurred_at=None, metadata=None, identifier=None):
    existing = jsonl.find(path(pack), identifier, _validate) if identifier else None
    identifier = identifier or "x_" + uuid.uuid4().hex
    if existing:
        expected = {"kind": kind, "text": str(text), "day": int(day),
                    "source": str(source).split("#", 1)[0], "actor": str(actor),
                    "depends_on": sorted(set(str(ref) for ref in depends_on if ref)),
                    "metadata": dict(metadata or {})}
        if any(existing.get(key) != value for key, value in expected.items()):
            raise SeedError("经历编号已存在，但内容不同；原记录已保留。")
        return existing
    at = now_iso()
    row = {"format": FORMAT, "id": identifier, "kind": kind, "text": str(text),
           "day": int(day), "source": str(source).split("#", 1)[0],
           "actor": str(actor), "occurred_at": occurred_at or at, "recorded_at": at,
           "depends_on": sorted(set(str(ref) for ref in depends_on if ref)),
           "metadata": dict(metadata or {})}
    jsonl.append(pack, path(pack), [row], _validate)
    return row


def transcript_events(pack, source, transcript):
    """Attach new event IDs without changing legacy transcript/UI file format."""
    candidates = [row for row in read(pack) if row.get("source") == source
                  and row.get("kind") == "conversation"]
    matched = []
    # New rows are appended to the day. Reverse matching preserves repeated text
    # when older legacy turns have no event ledger entry.
    for message in reversed(transcript):
        found = next((row for row in reversed(candidates)
                      if row.get("actor") == message["who"] and row.get("text") == message["text"]), None)
        if found:
            candidates.remove(found)
        matched.append({**message, "event_id": found["id"] if found else "",
                        "source": source + ("#" + found["id"] if found else ""),
                        "metadata": found.get("metadata", {}) if found else {},
                        "depends_on": found.get("depends_on", []) if found else []})
    return list(reversed(matched))


def source_of(event):
    return str(event["source"]) + "#" + event["id"]
