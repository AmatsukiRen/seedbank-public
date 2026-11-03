"""Explicit excerpts and delivery-scoped recall. Local callers are trusted carriers.

Names/person IDs are not authentication. A scope describes who receives a reply,
not just who authored the incoming message. Legacy unscoped records stay private.
"""
from __future__ import annotations

from pathlib import Path
import re
import uuid

from . import experience, jsonl, requests
from .memory_state import MemoryPolicy, dependencies, is_template
from .pack_lock import serialized
from .util import SeedError, canonical_json, now_iso, sha256

FORMAT = "seedbank/disclosure@1"


def path(pack):
    return Path(pack) / "mind" / "disclosure.jsonl"


def _validate(row, number):
    if (not isinstance(row, dict) or row.get("format") != FORMAT
            or row.get("kind") not in ("excerpt", "profile", "revoke")
            or not all(isinstance(row.get(k), str) for k in
                       ("id", "key", "event_id", "scope", "text", "source_id", "source_hash", "reason", "at", "supersedes"))
            or not all(row[k] for k in ("id", "key", "event_id", "scope", "reason", "at"))):
        raise SeedError(f"第 {number} 条分享记录格式不完整；原文件已保留。")


def read(pack):
    rows = jsonl.read(path(pack), _validate)
    known, latest = set(), {}
    for row in rows:
        if row["id"] in known or (row["supersedes"] and latest.get(row["key"]) != row["supersedes"]):
            raise SeedError("分享版本关系不完整；原文件已保留。")
        if not row["supersedes"] and row["key"] != row["id"]:
            raise SeedError("分享起始编号不完整；原文件已保留。")
        known.add(row["id"])
        latest[row["key"]] = row["id"]
    return rows


def scope(value, *, allow_public=False):
    if not isinstance(value, str):
        raise SeedError("分享范围应为字符串。")
    if value == "owner" or (allow_public and value == "public"):
        return value
    if re.fullmatch(r"person:[A-Za-z0-9_-]{1,100}|qq-group:[0-9]{1,24}|turn:[a-f0-9]{64}|channel:(telegram|discord|feishu|dingtalk|astrbot):[a-f0-9]{64}", value):
        return value
    raise SeedError("分享范围无效；请选择一个人物、QQ群或公开摘录。")


def audience(person_id="owner", requested=None, request_id="", *, interaction_kind="direct"):
    if requested is None:
        return "owner" if person_id == "owner" or interaction_kind == "reported" else "person:" + person_id if person_id else "turn:" + sha256(request_id or uuid.uuid4().hex)
    value = scope(requested)
    if value == "owner" and person_id != "owner" and interaction_kind != "reported":
        raise SeedError("私人上下文仅用于用户的私人交流。")
    if value.startswith("person:") and value != "person:" + person_id:
        raise SeedError("人物与交流范围不一致。")
    return value


def _hash(row):
    return sha256(canonical_json(row))


def _sources(pack, base):
    return {r["id"]: r for r in [*base.records, *experience.read(pack), *base.action_rows.values(),
                                *base.goal_rows.values(), *base.judgment_rows.values()]}


def _active(pack, base, nodes):
    latest = {r["key"]: r for r in read(pack)}
    active = {}
    for key, row in latest.items():
        event = nodes.get(row["event_id"])
        if row["kind"] == "revoke" or not event or not base.allows(event):
            continue
        if (event["text"] != row["text"] or event.get("metadata", {}).get("share_id") != row["id"]
                or event.get("metadata", {}).get("scope") != row["scope"]):
            continue
        if row["kind"] == "excerpt":
            original = nodes.get(row["source_id"])
            if (not original or not base.allows(original) or _hash(original) != row["source_hash"]
                    or row["text"] not in original.get("text", "")):
                continue
        active[key] = row
    return latest, active


class AudiencePolicy:
    """Compose recall suppression with recursive, all-source disclosure checks."""
    restricted = True

    def __init__(self, pack, audience_id, person_id=""):
        self.pack, self.audience_id, self.person_id = pack, scope(audience_id), person_id
        self.base = MemoryPolicy.load(pack)
        self.nodes = _sources(pack, self.base)
        _, active = _active(pack, self.base, self.nodes)
        self.shares = [r for r in active.values() if r["scope"] in ("public", audience_id)]
        self.approved = {r["event_id"] for r in self.shares}
        self.memo = {}

    def __getattr__(self, name):
        return getattr(self.base, name)

    def refresh(self):
        return AudiencePolicy(self.pack, self.audience_id, self.person_id)

    def _allows_id(self, identifier):
        # Iterative traversal avoids a Python recursion-depth lifetime limit.
        stack, visiting = [(identifier, None)], set()
        while stack:
            current, expanded_refs = stack.pop()
            if current in self.memo:
                visiting.discard(current)
                continue
            if expanded_refs is not None:
                visiting.discard(current)
                self.memo[current] = all(self.memo.get(ref, False) for ref in expanded_refs)
                continue
            row = self.nodes.get(current)
            if not row or current in visiting or not self.base.allows(row, historical=True):
                self.memo[current] = False
                continue
            # Only the approved COPY is disclosed. Its private parent stays private.
            if current in self.approved:
                self.memo[current] = True
                continue
            metadata = row.get("metadata", row.get("generation", {}))
            if (metadata.get("audience_id") != self.audience_id
                    or metadata.get("disclosure_version") != 1 or row.get("kind") == "disclosure"):
                self.memo[current] = False
                continue
            refs = dependencies(row) | set(metadata.get("context_dependencies", [])) | set(row.get("event_ids", []))
            parts = str(row.get("source", "")).split("#", 1)
            if len(parts) == 2 and parts[1] != current:
                refs.add(parts[1])
            visiting.add(current)
            stack.append((current, refs))
            stack.extend((ref, None) for ref in refs if ref not in self.memo)
        return self.memo.get(identifier, False)

    def allows(self, row, *, historical=False):
        identifier = str(row.get("event_id") or row.get("id") or "") if isinstance(row, dict) else ""
        return self.base.allows(row, historical=historical) and self._allows_id(identifier)

    def allows_source(self, source):
        parts = str(source or "").split("#", 1)
        return len(parts) == 2 and self.base.allows_source(source) and self._allows_id(parts[1])

    def supports(self, evidence):
        supported = self.base.supports(evidence)
        if not isinstance(evidence, list) or len(supported) != len(evidence):
            return []
        return supported if all(self._allows_id(str(r.get("id", ""))) for r in supported) else []

    def visible(self, *, historical=False):
        return [r for r in self.base.records if self.allows(r, historical=historical)]

    def annotate(self, row):
        # Revision metadata may contain a private reason. Only expose a revision
        # if its complete replacement is available to this recipient.
        replacement = self.base.superseded_by.get(str(row.get("id", "")))
        result = self.base.annotate(row) if not replacement or self._allows_id(replacement) else dict(row)
        # Search aliases can include replaced/private text; they never leave the
        # local index. Only canonical content belongs in a model context.
        result.pop("search_text", None)
        result.pop("search_aliases", None)
        result.pop("aliases", None)
        result.pop("archive_actor", None)
        return result

    def entity_label(self, identifier):
        return "当前交流对象" if identifier == self.person_id else "这个个体" if identifier == "self" else "另一个人物"

    def allows_generation(self, metadata):
        return (isinstance(metadata, dict) and metadata.get("audience_id") == self.audience_id
                and metadata.get("disclosure_version") == 1
                and all(self._allows_id(str(ref)) for ref in metadata.get("context_dependencies", [])))


def policy_for(pack, audience_id="owner", person_id=""):
    return MemoryPolicy.load(pack) if audience_id == "owner" else AudiencePolicy(pack, audience_id, person_id)


def stamp(audience_id):
    return {"audience_id": audience_id, "disclosure_version": 1}


def _transcript_speaker(row):
    """Keep channel-assigned identity and roles, without private display names."""
    metadata = row.get("metadata", {})
    runner = metadata.get("runner")
    if runner:
        return {**row, "who": "runtime" if runner == "runtime" else "fish"}
    identity = ({"person_id": metadata["person_id"],
                 "interaction_kind": metadata.get("interaction_kind", "direct")}
                if "person_id" in metadata else {})
    return {**row, "who": "访客", **identity}


def context(pack, day, date, message, *, policy, person_id, use_semantic):
    """An explicit allowlist: legacy private prose never enters a guest prompt."""
    from . import cognition, development, facts, learning, relationships, life_story
    from .retrieval import _event_row
    from .semantic import last_status
    source = f"life/{cognition._memory_filename(day, date)}"
    transcript = [r for r in experience.transcript_events(pack, source, cognition.read_transcript(pack, day)) if policy.allows(r)]
    transcript = facts.annotate_records(pack, transcript, policy)
    recalled = cognition.recall(pack, message, cognition.RECALL_K, policy=policy, use_semantic=use_semantic) if message else []
    # Approved profile/excerpts are supplied even when the query uses other words.
    shares = [_event_row(policy.nodes[r["event_id"]]) for r in policy.shares][-16:]
    evidence = {r["id"]: r for r in cognition._evidence_memories(pack, message, policy=policy, recalled=recalled) + shares}
    relation = relationships.context(pack, person_id, policy=policy, day=day)
    relation["label"] = policy.entity_label(person_id) if person_id else "未关联身份的发言者"
    # Operational private-contact controls are not themselves shared information.
    relation["proactive"] = "not_assigned"
    return {
        "packDir": str(pack), "_audience_id": policy.audience_id, "_person_id": person_id,
        "birth": {}, "name": "SEEDbank", "speciesId": "", "speciesName": "未分享出生背景",
        "dayNo": day, "date": date, "message": message, "mood": "未分享", "energy": 0.6,
        "moods": [], "traitsPicked": [], "profile": {}, "worldBible": "", "identity": "", "values": "",
        "selfMd": "", "beliefs": "", "interests": [], "boundaries": [], "plan": "",
        "bond": {}, "works": {}, "memorial": {}, "inner": {}, "hands": {}, "friends": {},
        "recentDays": [], "senses": [], "news": [], "relationships": relation,
        "development": development.summary(pack, policy=policy), "learning": learning.context(pack, policy=policy),
        "life_story": life_story.context(pack, message, policy=policy),
        "memories": policy.visible(), "recalled": recalled, "evidence": list(evidence.values()),
        "facts": facts.context(pack, message, policy=policy, references=list(evidence)),
        "transcript": [_transcript_speaker(r) for r in transcript],
        "current_evidence": [{"id": r["event_id"], "source": r["source"], "kind": "conversation"}
                             for r in transcript if not is_template(r)][-6:],
        "retrieval_status": last_status(pack) if message else {"state": "not_used"},
        "disclosed": [{"id": r["id"], "text": r["text"], "kind": r.get("disclosure_basis", "user_approved_excerpt"),
                       "category": policy.nodes[r["id"]].get("metadata", {}).get("share_kind", "excerpt")} for r in shares],
    }


def _text(value, maximum, label):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise SeedError(label + f"不能为空且不能超过 {maximum} 字。")
    return value.strip()


@serialized
def perform(pack, action, payload, *, request_id=""):
    from .cognition import open_day
    from .facts import entities
    if not isinstance(payload, dict) or action not in ("excerpt", "profile", "revoke"):
        raise SeedError("分享操作应为 excerpt / profile / revoke，并提供 data 对象。")
    data = {"target": str(payload.get("target") or ""), "expected": str(payload.get("expected") or ""),
            "reason": _text(payload.get("reason"), 600, "分享或撤回说明")}
    if action != "revoke":
        data.update(scope=scope(payload.get("scope"), allow_public=True), text=_text(payload.get("text"), 2000, "分享正文"),
                    source_id=str(payload.get("source_id") or "") if action == "excerpt" else "",
                    source_hash=str(payload.get("source_hash") or "") if action == "excerpt" else "")
        if data["scope"] == "owner" or data["scope"].startswith("turn:"):
            raise SeedError("请选择公开、已登记人物或QQ群作为分享范围。")

    def validate():
        base = MemoryPolicy.load(pack)
        nodes = _sources(pack, base)
        latest, active = _active(pack, base, nodes)
        previous = latest.get(data["target"])
        if data["target"] and not previous or data["expected"] != (previous["id"] if previous else ""):
            raise SeedError("分享记录已变化，请刷新后再操作。")
        if action == "revoke":
            if not previous or previous["kind"] == "revoke":
                raise SeedError("请先选择尚未撤回的分享记录。")
            return
        if data["scope"].startswith("person:") and (data["scope"][7:] not in entities(pack) or data["scope"][7:] in ("self", "owner")):
            raise SeedError("分享对象不存在，请先登记人物。")
        if action == "excerpt":
            original = nodes.get(data["source_id"])
            if (not original or original.get("kind") in ("forget", "disclosure") or not base.allows(original)
                    or _hash(original) != data["source_hash"] or data["text"] not in original.get("text", "")):
                raise SeedError("原记录已变化或摘录不是原文，请重新选择来源。")

    def apply():
        previous = {r["key"]: r for r in read(pack)}.get(data["target"])
        identifier = "s_" + uuid.uuid4().hex
        row = {"format": FORMAT, "id": identifier, "key": previous["key"] if previous else identifier,
               "kind": action, "scope": data.get("scope", previous["scope"] if previous else ""),
               "text": data.get("text", ""), "source_id": data.get("source_id", ""),
               "source_hash": data.get("source_hash", ""), "reason": data["reason"], "at": now_iso(),
               "supersedes": previous["id"] if previous else ""}
        original = _sources(pack, MemoryPolicy.load(pack)).get(row["source_id"], {})
        from .memory_state import provenance
        basis = provenance(original) if action == "excerpt" else "用户提供的对外自我介绍，未独立核实"
        event = experience.record(pack, kind="disclosure", text=row["text"], day=open_day(pack)["dayNo"],
                    source="mind/disclosure.jsonl", actor="user", depends_on=[row["source_id"]] if row["source_id"] else [],
                    metadata={"share_id": identifier, "scope": row["scope"], "basis": "explicit_user_approval", "source_basis": basis,
                              "share_kind": action})
        row["event_id"] = event["id"]
        jsonl.append(pack, path(pack), [row], _validate)
        return {"record": row}

    return requests.run(pack, {"kind": "disclosure_edit", "action": action, "data": data}, apply,
                        request_id=request_id, validate=validate)


@serialized
def listing(pack, *, query="", offset=0, limit=30, record_offset=0, history=False):
    from .facts import entities
    base = MemoryPolicy.load(pack)
    nodes = _sources(pack, base)
    latest, active = _active(pack, base, nodes)
    needle = str(query).strip().casefold()
    sources = [r for r in reversed(list(nodes.values())) if base.allows(r) and r.get("kind") not in ("forget", "disclosure")
               and (not needle or needle in str(r.get("text", "")).casefold())]
    start, count = max(0, int(offset)), max(1, min(100, int(limit)))
    record_start = max(0, int(record_offset))
    records = list(reversed(read(pack) if history else list(latest.values())))
    return {"records": [{**r, "current": latest[r["key"]]["id"] == r["id"],
                          "available": active.get(r["key"], {}).get("id") == r["id"]}
                         for r in records[record_start:record_start + count]],
            "record_offset": record_start, "record_total": len(records), "history": bool(history),
            "sources": [{"id": r["id"], "text": r["text"], "kind": r["kind"], "source": r.get("source", ""),
                         "hash": _hash(r)} for r in sources[start:start + count]],
            "offset": start, "total": len(sources), "query": str(query),
            "people": [{"id": key, "label": label} for key, label in entities(pack).items() if key not in ("owner", "self")],
            "pending": [r for r in requests.pending(pack) if r["payload"].get("kind") == "disclosure_edit"]}
