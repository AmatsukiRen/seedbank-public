"""Withdraw a mistaken model extraction without withdrawing its raw source."""
from __future__ import annotations

import re

from . import experience, requests
from .fact_dates import digest
from .pack_lock import serialized
from .util import SeedError

FORMAT = "seedbank/facts@3"


def validate(row):
    from .facts import _text
    for key, maximum in (("id", 100), ("at", 100), ("slot", 100), ("target", 100), ("reason", 500)):
        _text(row.get(key), maximum, key)
    if (row.get("format") != FORMAT or row.get("kind") != "retract"
            or row.get("targets") != [row["target"]]
            or any(not isinstance(row.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}", row[k])
                   for k in ("target_hash", "input_hash"))
            or not isinstance(row.get("evidence"), list) or len(row["evidence"]) != 1):
        raise SeedError("提取撤回记录不完整；原文件已保留。")
    ref = row["evidence"][0]
    if not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ("id", "source", "kind")):
        raise SeedError("提取撤回缺少来源；原文件已保留。")


def input_matches(row, originals):
    ref = row["evidence"][0]
    event = originals.get(ref["id"])
    return bool(event and event.get("kind") == "fact_retraction"
                and event.get("metadata", {}).get("target") == row["target"]
                and ref["source"] == experience.source_of(event) and digest(event) == row["input_hash"])


def supported(row, policy, originals):
    return bool(input_matches(row, originals) and policy.supports(row["evidence"])
                and policy.allows(originals[row["evidence"][0]["id"]]))


def suppressed(rows, events):
    """Older dependencies name sources, so retirement is source-granular."""
    claims = {r["id"]: r for r in rows if r["kind"] == "claim"}
    originals = {r["id"]: r for r in events}
    cutoffs, retired = {}, set()
    for row in rows:
        if row["kind"] != "retract":
            continue
        ref = row["evidence"][0]["id"]
        cutoffs.setdefault(ref, set()).update(r["id"] for r in claims[row["target"]]["evidence"])
        if not input_matches(row, originals):
            retired.add(ref)
    active = {source for cutoff, sources in cutoffs.items() if cutoff not in originals for source in sources}
    for event in reversed(events):
        active.update(cutoffs.get(event["id"], ()))
        metadata = event.get("metadata", {})
        if "context_dependencies" in metadata and (set(metadata["context_dependencies"]) | set(event.get("depends_on", []))) & active:
            retired.add(event["id"])
    return retired


@serialized
def perform(pack, payload, *, request_id=""):
    from . import facts
    if not isinstance(payload, dict) or not isinstance(payload.get("expected"), list):
        raise SeedError("缺少当前说法编号，请刷新后再操作。")
    if not all(isinstance(v, str) for v in payload["expected"]):
        raise SeedError("缺少当前说法编号，请刷新后再操作。")
    data = {key: facts._text(payload.get(key), maximum, label) for key, maximum, label in (
        ("slot", 100, "事项编号"), ("target", 100, "说法编号"),
        ("target_hash", 64, "原说法摘要"), ("reason", 500, "理由"))}
    data["expected"] = sorted(set(payload["expected"]))

    def current():
        _, groups = facts._state(pack)
        group = groups.get(data["slot"], {})
        item = next((r for r in group.get("claims", []) if r["id"] == data["target"]), None)
        raw = next((r for r in facts.read(pack) if r["id"] == data["target"]), None)
        if (not item or item["origin"] != "model" or group.get("expected") != data["expected"]
                or not raw or digest(raw) != data["target_hash"]):
            raise SeedError("这条提取已改变、撤回或不可用，请刷新后重新核对。")
        return raw

    def apply():
        from .cognition import _latest_day
        from .disclosure import stamp
        raw = current()
        event = experience.record(pack, kind="fact_retraction",
            text=f"撤回模型对 {raw['subject']} · {raw['aspect']} 的提取，不采用 {raw['value']}。理由：{data['reason']}",
            day=_latest_day(pack)["day"], source="mind/experiences.jsonl", actor="user",
            depends_on=[r["id"] for r in raw["evidence"]],
            metadata={**stamp("owner"), "runner": "user-fact-retraction-v1", "target": raw["id"]})
        record = facts._append(pack, "retract", **{k: v for k, v in data.items() if k != "expected"},
            targets=[raw["id"]], input_hash=digest(event),
            evidence=[{"id": event["id"], "source": experience.source_of(event), "kind": event["kind"]}])
        return {"record": record}

    return requests.run(pack, {"kind": "fact_edit", "action": "retract", "data": data}, apply,
                        request_id=request_id, validate=current)
