"""Memory versions and recall policy. Historical rows are never rewritten.

This module has no model dependency. A tombstone is an audit event, not a
recollection. Old day-level sources are conservatively withheld when their
content cannot be separated from a memory the user has set aside.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date
from itertools import chain
import json
import re
import uuid

from .util import SeedError, append_memories, now_iso
from .pack_lock import serialized
from .memory_sources import PolicySources


def source_file(value):
    return str(value or "").replace("\\", "/").split("#", 1)[0]


def is_template(row):
    """Only explicit runtime metadata establishes template origin."""
    if not isinstance(row, dict):
        return False
    if row.get("template_generated") is True:
        return True
    for metadata in (row, row.get("generation"), row.get("metadata")):
        if not isinstance(metadata, dict):
            continue
        runner = metadata.get("runner")
        if metadata.get("fallback") is True or (isinstance(runner, str) and runner.strip().startswith("stub")):
            return True
    return False


def dependencies(row):
    result = {str(ref) for ref in row.get("depends_on", []) if isinstance(ref, str)}
    metadata = row.get("metadata", row.get("generation", {}))
    if isinstance(metadata, dict):
        result.update(str(ref) for ref in metadata.get("context_dependencies", []) if isinstance(ref, str))
    for ref in row.get("evidence", []):
        if isinstance(ref, dict) and ref.get("id"):
            result.add(str(ref["id"]))
    return result


def _closure(seeds, *graphs):
    reached = set(seeds)
    pending = deque(reached)
    while pending:
        identifier = pending.popleft()
        for graph in graphs:
            for related in graph.get(identifier, ()):
                if related not in reached:
                    reached.add(related)
                    pending.append(related)
    return reached


def _blocked_ids(rows, forgotten):
    if not forgotten:
        return set()
    revisions, origins, dependents = (defaultdict(set) for _ in range(3))
    for row in rows:
        identifier = str(row.get("id") or "")
        parent = str(row.get("supersedes") or "")
        if parent:
            revisions[identifier].add(parent)
            revisions[parent].add(identifier)
        source_refs = {str(ref) for ref in row.get("event_ids", [])}
        parts = str(row.get("source", "")).split("#", 1)
        if len(parts) == 2:
            source_refs.add(parts[1])
        if source_refs:
            origins[identifier].update(source_refs)
        for ref in dependencies(row):
            dependents[ref].add(identifier)
    # Explicit withdrawal follows original sources; loss of derived support
    # only follows descendants. Do not let a retired interpretation erase its
    # independent ancestors or sibling interpretations.
    direct = _closure(forgotten, revisions, origins)
    return _closure(direct, revisions, dependents)


class MemoryPolicy:
    def __init__(self, records, experiences=(), extra_blocked=(), *, outcomes=(), goal_events=(), judgment_events=()):
        self.records = [row for row in records if isinstance(row, dict)]
        experiences = tuple(experiences)
        from .goal_history import project as goal_project
        self.goal_events = {row["id"]: row for row in goal_events if row["kind"] == "goal"}
        self.goal_rows = {key: goal_project(row) for key, row in self.goal_events.items()}
        self.goal_heads = {row["data"]["id"]: row for row in self.goal_events.values()}
        from .judgment_history import project as judgment_project, KINDS
        self.judgment_events = {row["id"]: row for row in judgment_events if row["kind"] in KINDS}
        self.judgment_rows = {key: judgment_project(row) for key, row in self.judgment_events.items()}
        self.judgment_heads = {(row["kind"], row["data"]["id"]): row for row in self.judgment_events.values()}
        self._goal_project_events = {row["id"]: row for row in experiences if row.get("kind") == "goal_project"}
        from .action_archive import project
        self.action_outcomes, self.action_rows = {}, {}
        for outcome in outcomes:
            projected = project(outcome)
            if projected:
                self.action_outcomes[outcome["id"]] = outcome
                self.action_rows[outcome["id"]] = projected
        experiences = (*experiences, *self.action_rows.values(), *self.goal_rows.values(), *self.judgment_rows.values())
        self.template_diaries = defaultdict(list)
        for row in experiences:
            if row.get("kind") == "diary" and is_template(row) and row.get("text"):
                self.template_diaries[source_file(row.get("source"))].append(" ".join(row["text"].split()))
        self.by_id = {str(row.get("id")): row for row in self.records}
        self.forgotten = {str(row["forgets"]) for row in self.records
                          if row.get("kind") == "forget" and row.get("forgets")}
        self.forgotten.update(extra_blocked)
        self.superseded_by = {}
        self.revised_sources = set()
        for revision in self.records:
            if not revision.get("supersedes"):
                continue
            target_id = str(revision["supersedes"])
            target = self.by_id.get(target_id, {})
            replaced = {target_id, *[str(ref) for ref in target.get("event_ids", [])]}
            original_source = str(revision.get("superseded_source") or target.get("source") or "")
            if "#" in original_source:
                replaced.add(original_source.split("#", 1)[1])
            if original_source:
                self.revised_sources.add(source_file(original_source))
            for identifier in replaced:
                self.superseded_by[identifier] = str(revision["id"])
        # A model can correct an original event instead of its extracted memory.
        # Hide interpretations of that same event too, without treating every
        # later record that merely saw the old context as superseded.
        changed = True
        while changed:
            changed = False
            for row in self.records:
                identifier = str(row.get("id") or "")
                if identifier in self.superseded_by:
                    continue
                refs = [str(ref) for ref in row.get("event_ids", [])]
                parts = str(row.get("source", "")).split("#", 1)
                if len(parts) == 2:
                    refs.append(parts[1])
                replacement = next((self.superseded_by[ref] for ref in refs
                                    if ref in self.superseded_by and self.superseded_by[ref] != identifier), None)
                if replacement:
                    self.superseded_by[identifier] = replacement
                    changed = True
        self.superseded = set(self.superseded_by)
        self.blocked = _blocked_ids(chain(self.records, experiences), self.forgotten)
        self.sources = {source_file(row.get("source")) for key, row in self.by_id.items()
                        if key in self.blocked and not row.get("event_ids")
                        and "#" not in str(row.get("source", ""))
                        and source_file(row.get("source")).startswith("life/")}
        self.sources.update(source_file(row["superseded_source"]) for row in self.records
                            if row.get("supersedes") in self.blocked and row.get("superseded_source")
                            and "#" not in row["superseded_source"])
        self.affected_sources = self.sources | {
            source_file(row.get("source")) for row in experiences
            if row.get("id") in self.blocked}

    @classmethod
    def load(cls, pack, *, _sources=None):
        from .facts import suppressed_ids
        from .relationships import suppressed_ids as relationship_suppressed_ids
        from .life_story import suppressed_ids as story_suppressed_ids
        from .media_archive import suppressed_ids as media_suppressed_ids
        from .learning_strategies import suppressed as strategy_suppressed_ids
        from .learning_observations import suppressed as observation_suppressed_ids
        sources = _sources if _sources is not None else PolicySources(pack)
        records, experiences = sources.memories, sources.experiences
        blocked = (suppressed_ids(pack, sources=sources) | relationship_suppressed_ids(pack)
                   | story_suppressed_ids(pack, sources=sources) | media_suppressed_ids(pack, sources=sources)
                   | strategy_suppressed_ids(pack, sources=sources) | observation_suppressed_ids(pack, sources=sources))
        outcomes = tuple(sources.outcomes.values())
        goal_events = [row for row in sources.development_events if row["kind"] == "goal"]
        from .judgment_history import KINDS, visible as judgment_visible
        judgment_events = [row for row in sources.development_events if row["kind"] in KINDS]
        policy = cls(records, experiences, blocked, outcomes=outcomes, goal_events=goal_events, judgment_events=judgment_events)
        # Full-day withdrawal or superseded explicit evidence may make a
        # receipt unavailable without one of its named IDs already being
        # blocked. Propagate that loss through archive-ID-only descendants.
        from .development import outcome_visible
        unavailable = {identifier for identifier, row in policy.action_outcomes.items()
                       if not outcome_visible(row, policy)} - policy.blocked
        from .goal_history import visible as goal_visible
        unavailable.update(identifier for identifier, row in policy.goal_events.items()
                           if not goal_visible(row, policy) and identifier not in policy.blocked)
        unavailable.update(identifier for identifier, row in policy.judgment_events.items()
                           if not judgment_visible(row, policy) and identifier not in policy.blocked)
        return cls(records, experiences, blocked | unavailable, outcomes=outcomes, goal_events=goal_events,
                   judgment_events=judgment_events) if unavailable else policy

    def allows_source(self, source):
        parts = str(source or "").split("#", 1)
        return source_file(source) not in self.sources and (len(parts) == 1 or parts[1] not in self.blocked)

    def allows_generation(self, metadata):
        return not isinstance(metadata, dict) or not (set(metadata.get("context_dependencies", [])) & self.blocked)

    def allows(self, row, *, historical=False):
        if not isinstance(row, dict) or row.get("kind") == "forget":
            return False
        identifier = str(row.get("event_id") or row.get("id") or "")
        if identifier in self.blocked or dependencies(row) & self.blocked:
            return False
        if not historical and identifier in self.superseded:
            return False
        return self.allows_source(row.get("source"))

    def visible(self, *, historical=False):
        return [row for row in self.records if self.allows(row, historical=historical)]

    def annotate(self, row):
        """Keep historical results explicit about a newer interpretation."""
        if row.get("id") in self.goal_rows:
            from .goal_history import annotate
            row = annotate(row, self)
        if row.get("id") in self.judgment_rows:
            from .judgment_history import annotate
            row = annotate(row, self)
        if (row.get("origin") == "legacy_archive" and row.get("kind") == "diary"
                and self.template_diary_fragment(row.get("source"), row.get("text"))):
            row = {**row, "template_generated": True}
        replacement = self.superseded_by.get(str(row.get("id") or ""))
        if replacement:
            revision = self.by_id.get(replacement, {})
            return {**row, "superseded_by": replacement,
                    "superseded_reason": revision.get("change_type", ""),
                    "superseded_effective_on": revision.get("effective_on", "")}
        return dict(row)


    def template_diary_fragment(self, source, text):
        fragment = " ".join(str(text or "").split())
        return bool(fragment) and any(fragment in original or original in fragment
                                      for original in self.template_diaries.get(source_file(source), ()))

    def supports(self, evidence):
        """Keep independent support; never restore a superseded interpretation."""
        if not isinstance(evidence, list):
            return []
        return [ref for ref in evidence if isinstance(ref, dict)
                and str(ref.get("id")) not in self.blocked
                and str(ref.get("id")) not in self.superseded
                and self.allows_source(ref.get("source"))]


@serialized
def revise_memory(pack, target_id, text, *, reason, day, source, runner,
                  evidence=(), change_type="correction", at=None, target_record=None, generation=None,
                  effective_on=""):
    """A runtime-validated revision, independent of the extraction quota."""
    policy = MemoryPolicy.load(pack)
    target_id = str(target_id or "").strip()
    target = policy.by_id.get(target_id)
    if target is None and isinstance(target_record, dict) and target_record.get("id") == target_id:
        target = target_record
    if target is None or not policy.allows(target):
        raise SeedError("要更正的记忆不存在、已被替代或已经放下。")
    content = str(text or "").strip()
    reason = str(reason or "").strip()
    if not content or not reason:
        raise SeedError("更正需要新的内容和具体理由。")
    if change_type not in ("correction", "change"):
        raise SeedError("更正类型必须是 correction（记错）或 change（后来改变）。")
    effective_on = effective_date(effective_on)
    if effective_on and change_type != "change":
        raise SeedError("只有后来发生的变化才填写变化日期。")
    ancestor = target
    visited = set()
    while ancestor.get("supersedes") in policy.by_id and ancestor["id"] not in visited:
        visited.add(ancestor["id"])
        ancestor = policy.by_id[ancestor["supersedes"]]
    at = at or now_iso()
    row = {
        "id": "m_" + uuid.uuid4().hex,
        "day": int(day), "at": at, "recorded_at": at, "kind": "correction",
        "text": content[:1000], "importance": 0.9, "tags": ["更正"],
        "source": str(source), "runner": str(runner), "reason": reason[:500],
        "generation": dict(generation or {}),
        "supersedes": target_id, "change_type": change_type,
        "claim_id": target.get("claim_id") or ancestor.get("supersedes") or ancestor["id"],
        "effective_on": effective_on,
        "superseded_source": target.get("source", ""),
        "valid_from": at, "evidence": list(evidence),
        "depends_on": [target_id],
        "event_ids": [str(ref["id"]) for ref in evidence if isinstance(ref, dict)
                      and str(ref.get("id", "")).startswith("x_")],
    }
    append_memories(pack, [row])
    return row


def effective_date(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        parsed = date.fromisoformat(value)
    except ValueError:
        raise SeedError("变化日期需要有效的 YYYY-MM-DD 日期，也可以留空。") from None
    if parsed > date.today():
        raise SeedError("变化日期不能晚于今天；尚未发生的事应记录为计划。")
    return value


def provenance(row):
    if row.get("kind") in ("belief_history", "preference_history"):
        return ("看法或偏好的历史版本，只说明当时表达的理解与理由，不证明当前态度、固定身份或外部事实"
                + ("；表达来自固定或回退响应" if is_template(row) else ""))
    if row.get("kind") == "goal_history":
        return "目标的历史版本，只说明当时记录的意图与理由，不证明当前意愿、独立动机或实际完成"
    if row.get("kind") == "action_proposal":
        return ("当时给出的行动说明与运行器执行结果；说明不证明动机已核实，结果不证明技能或完整自主性"
                + ("；提议来自固定或回退响应" if is_template(row) else ""))
    if is_template(row):
        return "离线或回退模板记录，不是亲历、感受或自主选择的证据"
    if row.get("kind") == "plan_decision":
        return "模型当时表达的日程选择，不代表当前安排、已完成的行动或外部事实"
    if row.get("kind") == "life_story":
        return "人生回顾中的解释，不是独立核实的事实"
    if row.get("kind") == "runtime_gap":
        return "运行器记录的时间空档，期间实际活动未知"
    if row.get("kind") == "disclosure":
        return "用户明确分享的正文；" + str(row.get("disclosure_basis") or "来源性质待确认，不能推定为亲历")
    if row.get("kind") == "fact_input":
        return "用户提供的单项说法或核对，未独立核实"
    if row.get("kind") == "fact_retraction":
        return "用户指出模型提取有误，不表示相反说法已经核实"
    if row.get("kind") == "learning_strategy":
        return "来自具体反馈的尝试策略，适用性和效果仍需观察"
    if row.get("runner") == "user-memory-revision-v1" or row.get("kind") == "memory_revision":
        return "用户提供的修订，未独立核实"
    if row.get("kind") == "dream" or "梦" in (row.get("tags") or []):
        return "梦境，不是亲历"
    if row.get("kind") == "conversation":
        if row.get("utterance_role") == "model":
            return "模型回复，可能有误，不能覆盖原始发言或证明没有其他记录"
        if row.get("utterance_role") == "speaker":
            return "对方的原始发言；证明表达过这些话，不独立证明所述情节真实发生"
        if (row.get("generation") or {}).get("requested_adapter"):
            return "模型提炼的对话解释，需要回查原始发言，不能自行作为事实"
    return {"conversation": "对话记录/提炼", "hearsay": "听说或读到，未独立核实",
            "perception": "感知输入或识别解释", "thought": "个人想法/推断",
            "feeling": "感受", "diary": "日记中的解释", "correction": "已修订的说法",
            "creation": "创作内容，不是外部事实", "event": "原始记录", "outcome": "运行器执行回执"}.get(row.get("kind"), "历史记录，来源待确认")


def describe(row):
    day = row.get("day", "?")
    status = f"旧版本，已由 {row['superseded_by']} 替代；" if row.get("superseded_by") else ""
    if row.get("superseded_reason") == "correction":
        status += "后续记录指出原先说法有误；"
    elif row.get("superseded_reason") == "change":
        status += "后续记录说明情况发生变化；"
        if row.get("superseded_effective_on"):
            status += f"变化日期 {row['superseded_effective_on']}；"
    if row.get("source_has_revision"):
        status += "此日档案含后续更正，需结合新版本核对；"
    if row.get("life_story_note"):
        status += row["life_story_note"] + "；"
    if row.get("change_type") == "change":
        status += "后来发生变化；" + (f"变化日期 {row['effective_on']}；" if row.get("effective_on") else "变化日期未注明；")
    elif row.get("change_type") == "correction":
        status += "更正原先说法，不表示此前曾为真；"
    notes = ("\n单项核对（仅作用于指定事项；conflict 不能选边，unavailable 没有可用结论）："
             + json.dumps(row["fact_notes"], ensure_ascii=False)) if row.get("fact_notes") else ""
    if row.get("interpretation_updates"):
        notes += "\n相关人生理解的版本说明（不自动替换当前看法或选择）：" + json.dumps(row["interpretation_updates"], ensure_ascii=False)
    if row.get("goal_version"):
        from .goal_provenance import LABELS
        current = row["goal_version"]
        notes += (f"\n同一目标最新可见记录：{current['event_id']}；第 {current['day']} 日页，记录时间 {current['at']}；"
                  f"记录的状态 {current['status']}；理由 {current['reason']}。"
                  f"来源：{LABELS.get(current.get('activity'), LABELS['unrecorded'])}。历史版本不能自动恢复成当前打算。" if current.get("current_available")
                  else "\n同一目标的当前版本来源不可用，不能用较早版本推定当前意愿。")
    if row.get("judgment_version"):
        from .goal_provenance import LABELS
        current = row["judgment_version"]
        notes += (f"\n同一看法或偏好的最新可见记录：{current['event_id']}；第 {current['day']} 日页，记录时间 {current['at']}；"
                  f"记录内容：{current['statement']}；理由：{current['reason']}。"
                  f"来源：{LABELS.get(current.get('activity'), LABELS['unrecorded'])}。历史表达不自动成为当前态度。" if current.get("current_available")
                  else "\n同一看法或偏好的当前版本来源不可用，不能用较早版本推定当前态度。")
    return (f"[{row.get('id', '?')} | 第 {day} 天 | {status}{provenance(row)} | "
            f"来源 {row.get('source') or '未记录'}] {row.get('text', '')}" + notes)
