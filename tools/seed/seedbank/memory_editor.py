"""Explicit user revisions and an audit view. No model call or identity rewrite."""
from copy import deepcopy

from . import experience, requests
from .memory_state import MemoryPolicy, effective_date, provenance, revise_memory
from .pack_lock import serialized
from .util import SeedError, now_iso

RUNNER = "user-memory-revision-v1"


def _payload(memory_id, text, reason, change_type, effective_on):
    identifier = str(memory_id or "").strip()
    content, reason = str(text or "").strip(), str(reason or "").strip()
    if not identifier:
        raise SeedError("请选择要修订的记忆。")
    if not content or not reason:
        raise SeedError("请填写修订内容和理由。")
    if len(content) > 1000 or len(reason) > 500:
        raise SeedError("修订内容最多 1000 字，理由最多 500 字。")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in content + reason):
        raise SeedError("修订内容含有无法保存的控制字符。")
    if change_type not in ("correction", "change"):
        raise SeedError("请选择原来记错或后来改变。")
    effective_on = effective_date(effective_on)
    if change_type != "change" and effective_on:
        raise SeedError("只有后来发生的变化才填写变化日期。")
    return {"kind": "memory_revision", "memory_id": identifier, "text": content,
            "reason": reason, "change_type": change_type, "effective_on": effective_on}


def _target(pack, identifier, content):
    policy = MemoryPolicy.load(pack)
    target = policy.by_id.get(identifier)
    if target is None or not policy.allows(target):
        raise SeedError("这条记忆已改变或放下，请先查看当前版本。")
    if str(target.get("text", "")).strip() == content:
        raise SeedError("修订内容与当前记忆相同，无需另存一个版本。")
    return target


@serialized
def revise(pack, memory_id, text, *, reason, change_type="correction", effective_on="", request_id=""):
    payload = _payload(memory_id, text, reason, change_type, effective_on)

    def apply():
        from .cognition import _append_journal, start_day
        day = start_day(pack)
        at = now_iso()
        event = experience.record(
            pack, kind="memory_revision", text=payload["text"], day=day["dayNo"],
            source="mind/experiences.jsonl", actor="用户", occurred_at=at,
            metadata={"runner": RUNNER, "target_id": payload["memory_id"], "reason": payload["reason"],
                      "change_type": payload["change_type"], "effective_on": payload["effective_on"]})
        source = experience.source_of(event)
        row = revise_memory(
            pack, payload["memory_id"], payload["text"], reason=payload["reason"],
            day=day["dayNo"], source=source, runner=RUNNER, at=at,
            change_type=payload["change_type"], effective_on=payload["effective_on"],
            evidence=[{"id": event["id"], "source": source, "kind": "memory_revision"}],
            generation={"runner": RUNNER, "origin": "user", "model": ""})
        _append_journal(pack, {"mode": "memory_revision", "at": at, "day": day["dayNo"],
                               "target_id": payload["memory_id"], "memory_id": row["id"], "event_id": event["id"]})
        return {"memory": row}

    return requests.run(pack, payload, apply, request_id=request_id,
                        validate=lambda: _target(pack, payload["memory_id"], payload["text"]))


def _view(row, policy):
    identifier = str(row.get("id", ""))
    return {**policy.annotate(row), "forgotten": identifier in policy.blocked,
            "superseded": identifier in policy.superseded, "recallable": policy.allows(row),
            "can_revise": policy.allows(row) and row.get("kind") != "forget", "provenance": provenance(row)}


@serialized
def history(pack, memory_id):
    """An explicit human audit view may show archived/set-aside originals."""
    records = MemoryPolicy.load(pack)
    identifier = str(memory_id or "").strip()
    if identifier not in records.by_id:
        raise SeedError("没有找到这条记忆，请刷新后再试。")
    # Traverse only actual revision edges; unrelated records from the same day
    # never become versions of the selected claim.
    neighbors = {}
    for row in records.records:
        if row.get("supersedes"):
            a, b = str(row["id"]), str(row["supersedes"])
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
    family, remaining = set(), [identifier]
    while remaining:
        current = remaining.pop()
        if current in family:
            continue
        family.add(current)
        remaining.extend(neighbors.get(current, set()) - family)
    versions = [_view(row, records) for row in records.records if str(row.get("id")) in family]
    active = [row for row in versions if row["recallable"]]
    selected = _view(records.by_id[identifier], records)
    refs = {str(ref.get("id")): ref for ref in selected.get("evidence", [])
            if isinstance(ref, dict) and ref.get("id")}
    for event_id in selected.get("event_ids", []):
        refs.setdefault(str(event_id), {"id": str(event_id)})
    source = str(selected.get("source") or "")
    if "#" in source:
        ref_id = source.split("#", 1)[1]
        refs.setdefault(ref_id, {"id": ref_id, "source": source})
    events = {row["id"]: row for row in experience.read(pack)} if refs else {}
    evidence = []
    for ref_id, ref in refs.items():
        original = events.get(ref_id) or records.by_id.get(ref_id)
        evidence.append({**ref, "missing": original is None,
                         "text": original.get("text", "") if original else "",
                         "kind": original.get("kind", "") if original else ref.get("kind", ""),
                         "at": original.get("occurred_at", original.get("at", "")) if original else "",
                         "source": ref.get("source") or (original.get("source", "") if original else ""),
                         "provenance": provenance(original) if original else "历史记录，来源待确认"})
    pending = [record for record in requests.pending(pack)
               if record["payload"].get("kind") == "memory_revision"
               and record["payload"].get("memory_id") == identifier]
    return deepcopy({"selected": selected, "current": active[0] if len(active) == 1 else {},
                     "versions": versions, "evidence": evidence, "pending": pending,
                     "conflict": len(active) > 1})
