"""Append-only amendments to claim and transition dates, including history.

No value or resolution choice is changed. Previous generated interpretations
are retired conservatively by source dependencies and append order.
"""
from __future__ import annotations

import re

from . import experience, requests
from .fact_time import query_day
from .pack_lock import serialized
from .util import SeedError, canonical_json, sha256

FORMAT = "seedbank/facts@2"


def digest(row):
    return sha256(canonical_json(row))


def input_matches(revision, originals):
    ref = revision["evidence"][0]
    event = originals.get(ref["id"])
    return bool(event and event.get("kind") == "fact_time_revision"
                and event.get("metadata", {}).get("target") == revision["target"]
                and ref["source"] == experience.source_of(event)
                and digest(event) == revision["input_hash"])


def validate(row):
    from .facts import _text
    for name, maximum in (("id", 100), ("at", 100), ("target", 100), ("reason", 500)):
        _text(row.get(name), maximum, name)
    if (row.get("format") != FORMAT or row.get("kind") != "timing"
            or not isinstance(row.get("supersedes"), str) or len(row["supersedes"]) > 100
            or not isinstance(row.get("target_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["target_hash"])
            or not isinstance(row.get("input_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["input_hash"])
            or not isinstance(row.get("date"), str) or query_day(row["date"]) != row["date"]
            or not isinstance(row.get("evidence"), list) or len(row["evidence"]) != 1):
        raise SeedError("日期修订记录不完整；原文件已保留。")
    ref = row["evidence"][0]
    if not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ("id", "source", "kind")):
        raise SeedError("日期修订缺少来源；原文件已保留。")


def overlay(rows, policy, originals):
    latest = {row["target"]: row for row in rows if row["kind"] == "timing"}
    result = []
    for row in rows:
        if row["kind"] not in ("claim", "resolve"):
            result.append(row)
            continue
        item = {**row, "date_revision": "", "date_state": "original", "date_evidence": []}
        revision = latest.get(row["id"])
        if revision:
            refs = [r for r in policy.supports(revision["evidence"])
                    if r["id"] in originals and policy.allows(originals[r["id"]])
                    and input_matches(revision, originals)]
            key = "starts_on" if row["kind"] == "claim" else "effective_on"
            # Losing a revised date never silently restores its earlier value.
            item.update({key: revision["date"] if refs else "", "date_revision": revision["id"],
                         "date_state": "revised" if refs else "unavailable", "date_evidence": refs,
                         "date_updated_at": revision["at"]})
        result.append(item)
    return result


def suppressed(rows, events):
    """No MemoryPolicy calls: this is an input to that policy's dependency fold."""
    revisions = [row for row in rows if row["kind"] == "timing"]
    if not revisions:
        return set()
    targets = {row["id"]: row for row in rows}
    latest = {row["target"]: row for row in revisions}
    originals = {row["id"]: row for row in events}
    retired = {r["evidence"][0]["id"] for r in revisions
               if latest[r["target"]]["id"] != r["id"] or not input_matches(r, originals)}
    cutoffs = {}
    # The latest amendment already supersedes every earlier interpretation of
    # this target. An older missing cutoff must not poison fresh repaired input.
    for row in latest.values():
        cutoffs.setdefault(row["evidence"][0]["id"], set()).update(ref["id"] for ref in targets[row["target"]]["evidence"])
    # If the amendment event is missing, its position is unknown: fail closed
    # for generated interpretations, retaining original inputs and raw files.
    active = {source for cutoff, sources in cutoffs.items() if cutoff not in originals for source in sources}
    for row in reversed(events):
        active.update(cutoffs.get(row["id"], ()))
        metadata = row.get("metadata", {})
        if "context_dependencies" in metadata and (set(metadata["context_dependencies"]) | set(row.get("depends_on", []))) & active:
            retired.add(row["id"])
    return retired


def _target(pack, identifier):
    from .facts import read, _state
    rows = read(pack)
    raw = next((r for r in rows if r["id"] == identifier), None)
    if not raw or (raw["kind"] != "claim" and not (raw["kind"] == "resolve" and raw["change_type"] == "change")):
        raise SeedError("只能修订说法的生效起日或明确变化的日期。")
    _, groups = _state(pack)
    group = groups.get(raw["slot"], {})
    claims = {r["id"]: r for r in group.get("history", [])}
    if raw["kind"] == "claim":
        target = claims.get(identifier, {})
        editable = bool(target) and not target["unavailable"] and target.get("change_type") != "correction"
    else:
        target = next((r for r in group.get("decisions", []) if r["id"] == identifier), {})
        chosen = claims.get(raw["selected"], {})
        editable = bool(target.get("usable_for_time")) and bool(chosen) and not chosen["unavailable"] and chosen.get("change_type") != "correction"
    return rows, raw, target, group, editable


@serialized
def detail(pack, identifier):
    rows, raw, target, group, editable = _target(pack, identifier)
    versions = [r for r in rows if r["kind"] == "timing" and r["target"] == identifier]
    key = "starts_on" if raw["kind"] == "claim" else "effective_on"
    related = [r for r in rows if (r["kind"] == "claim" and r["id"] == identifier)
               or (r["kind"] == "resolve" and r["change_type"] == "change"
                   and (identifier in r["targets"] or r["id"] == identifier))]
    if raw["kind"] == "resolve":
        related.extend(r for r in rows if r["kind"] == "claim" and r["id"] in raw["targets"])
    return {"target": identifier, "target_hash": digest(raw), "expected": versions[-1]["id"] if versions else "",
            "kind": raw["kind"], "date": target.get(key, ""), "date_state": target.get("date_state", "unavailable"),
            "original_date": raw.get(key, ""), "original": raw, "versions": versions,
            "editable": editable, "label": group.get("label", ""), "aspect": group.get("aspect", ""),
            "related": [{"id": r["id"], "kind": r["kind"], "text": r.get("value") or r.get("reason", "")} for r in related],
            "pending": [r for r in requests.pending(pack) if r["payload"].get("kind") == "fact_time_edit"
                        and r["payload"]["data"].get("target") == identifier]}


@serialized
def perform(pack, payload, *, request_id=""):
    from .facts import _append, _text
    if not isinstance(payload, dict):
        raise SeedError("日期修订需要 data 对象。")
    if "date" not in payload or not isinstance(payload["date"], str):
        raise SeedError("请明确填写日期，或留空表示未知。")
    data = {"target": _text(payload.get("target"), 100, "目标编号"),
            "target_hash": _text(payload.get("target_hash"), 64, "目标摘要"),
            "expected": payload.get("expected"), "date": query_day(payload.get("date")),
            "reason": _text(payload.get("reason"), 500, "修订理由")}
    if not isinstance(data["expected"], str) or len(data["expected"]) > 100 or not re.fullmatch(r"[0-9a-f]{64}", data["target_hash"]):
        raise SeedError("缺少日期版本或目标摘要，请刷新后重新编辑。")

    def validate_current():
        current = detail(pack, data["target"])
        if not current["editable"]:
            raise SeedError("这条说法或变化已经记错、放下或失去依据，不能通过改日期恢复。")
        if current["expected"] != data["expected"] or current["target_hash"] != data["target_hash"]:
            raise SeedError("日期或原记录已经改变，请刷新后重新核对。")

    def apply():
        from .cognition import _latest_day
        from .disclosure import stamp
        _, raw, _, _, _ = _target(pack, data["target"])
        label = "生效起日" if raw["kind"] == "claim" else "变化日期"
        event = experience.record(pack, kind="fact_time_revision", day=_latest_day(pack)["day"],
            source="mind/experiences.jsonl", actor="user", depends_on=[r["id"] for r in raw["evidence"]],
            text=f"用户修订 {data['target']} 的{label}为 {data['date'] or '未知'}。理由：{data['reason']}",
            metadata={**stamp("owner"), "runner": "user-fact-time-v1", "target": data["target"]})
        row = _append(pack, "timing", target=data["target"], target_hash=data["target_hash"],
                      supersedes=data["expected"], date=data["date"], reason=data["reason"],
                      input_hash=digest(event),
                      evidence=[{"id": event["id"], "source": experience.source_of(event), "kind": event["kind"]}])
        return {"record": row}

    return requests.run(pack, {"kind": "fact_time_edit", "data": data}, apply, request_id=request_id, validate=validate_current)
