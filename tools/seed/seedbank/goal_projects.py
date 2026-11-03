"""Atomic, sourced proposals of new goals with explicit stage dependencies."""
import json
import re
import uuid

from . import development, experience, learning
from .memory_state import MemoryPolicy
from .pack_lock import durable
from .util import SeedError, canonical_json, sha256

FORMAT = "seedbank/goal-project@1"


def clean(raw):
    if not isinstance(raw, dict) or set(raw) != {"title", "reason", "evidence", "stages"}:
        raise SeedError("分阶段安排需要主题、理由、依据和阶段列表。")
    title = learning.text(raw["title"], 120, "安排主题")
    reason = learning.text(raw["reason"], 300, "安排理由")
    refs = raw["evidence"]
    if (not isinstance(refs, list) or not 1 <= len(refs) <= 6
            or any(not isinstance(ref, str) or not ref or len(ref) > 100 for ref in refs)
            or len(set(refs)) != len(refs)):
        raise SeedError("分阶段安排需要一到六条不重复的实际依据。")
    if not isinstance(raw["stages"], list) or not 2 <= len(raw["stages"]) <= 4:
        raise SeedError("一次分阶段安排需要二到四个新目标。")
    stages, keys, titles = [], set(), set()
    for stage in raw["stages"]:
        if not isinstance(stage, dict) or set(stage) != {"key", "title", "next_step", "skill", "criteria", "after"}:
            raise SeedError("阶段需要临时标记、目标、下一步、练习方向、完成条件和前置关系。")
        key = stage["key"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key) or key in keys:
            raise SeedError("阶段标记需要不重复的英文小写字母、数字或下划线。")
        row = {"key": key, **{name: learning.text(stage[name], limit, label) for name, limit, label in (
            ("title", 120, "阶段目标"), ("next_step", 200, "下一步"), ("skill", 80, "练习方向"))}}
        if row["title"] in titles:
            raise SeedError("同一次安排不能重复阶段目标。")
        row["criteria"] = learning.clean_criteria(stage["criteria"])
        if not any(item["check"] == "feedback" for item in row["criteria"]):
            raise SeedError("每个新阶段至少需要一项外部反馈条件。")
        after, seen = [], set()
        if not isinstance(stage["after"], list) or len(stage["after"]) > 6:
            raise SeedError("每个阶段最多依赖六个前置目标。")
        for ref in stage["after"]:
            if isinstance(ref, dict) and set(ref) == {"stage"} and isinstance(ref["stage"], str):
                value = {"stage": learning.text(ref["stage"], 32, "前置阶段")}
                identity = ("stage", value["stage"])
            else:
                from .goal_dependencies import clean as clean_dependencies
                value = clean_dependencies([ref])[0]
                identity = ("goal", value["goal_id"])
            if identity in seen:
                raise SeedError("阶段不能重复依赖同一个目标。")
            seen.add(identity)
            after.append(value)
        row["after"] = after
        stages.append(row)
        keys.add(key)
        titles.add(row["title"])
    pending, ordered, done = list(stages), [], set()
    if any(ref["stage"] not in keys for stage in stages for ref in stage["after"] if "stage" in ref):
        raise SeedError("前置阶段没有对应的新目标。")
    while pending:
        ready = next((stage for stage in pending if all(ref["stage"] in done for ref in stage["after"] if "stage" in ref)), None)
        if ready is None:
            raise SeedError("阶段形成循环，不能保存这份安排。")
        ordered.append(ready)
        done.add(ready["key"])
        pending.remove(ready)
    return {"title": title, "reason": reason, "evidence": list(refs), "stages": ordered}


def stored(event):
    if (not event or event.get("kind") != "goal_project" or event.get("actor") != "model"
            or event.get("source") != "mind/development.jsonl"
            or event.get("metadata", {}).get("project_format") != FORMAT):
        return None
    try:
        payload = json.loads(event["text"])
        proposal = clean(payload["proposal"])
        identifiers = payload["goal_ids"]
        if (proposal != payload["proposal"] or sha256(canonical_json(proposal)) != event["metadata"].get("proposal_hash")
                or not isinstance(identifiers, dict) or set(identifiers) != {s["key"] for s in proposal["stages"]}
                or any(not isinstance(value, str) or not re.fullmatch(r"g_[a-f0-9]{16}", value) for value in identifiers.values())
                or len(set(identifiers.values())) != len(identifiers)):
            return None
        return payload
    except (ValueError, KeyError, TypeError, SeedError):
        return None


def valid_link(goal, originals, policy=None):
    ref = goal.get("project")
    if not isinstance(ref, dict) or set(ref) != {"event_id", "sha256", "stage"}:
        return False
    if not all(isinstance(value, str) for value in ref.values()):
        return False
    event = originals.get(ref["event_id"])
    payload = stored(event)
    return bool(payload and sha256(canonical_json(event)) == ref["sha256"]
                and payload["goal_ids"].get(ref["stage"]) == goal.get("id")
                and (policy is None or policy.allows(event)))


def audit_standards(rows, originals):
    known = {}
    for row in rows:
        if row["kind"] != "criteria":
            continue
        if row["format"] == "seedbank/learning@5":
            goal = {"id": row["goal_id"], "project": row["data"].get("project")}
            if not valid_link(goal, originals):
                raise SeedError("阶段条件缺少对应的原始安排；原记录已保留。")
            event = originals[goal["project"]["event_id"]]
            payload = stored(event)
            stage = next(item for item in payload["proposal"]["stages"] if item["key"] == goal["project"]["stage"])
            if (row["source"] != experience.source_of(event) or row["data"]["items"] != stage["criteria"]
                    or any(row["data"][key] != stage[key] for key in ("title", "skill"))
                    or len(row["data"]["prerequisites"]) != len(stage["after"])):
                raise SeedError("阶段条件与原始安排不一致；原记录已保留。")
            for proposed, bound in zip(stage["after"], row["data"]["prerequisites"]):
                if "stage" in proposed:
                    identifier = payload["goal_ids"][proposed["stage"]]
                    parent = known.get(bound["criteria_id"], {})
                    valid = (parent.get("format") == "seedbank/learning@5"
                             and parent.get("goal_id") == identifier and bound["goal_id"] == identifier
                             and parent.get("data", {}).get("project", {}).get("event_id") == event["id"])
                else:
                    valid = all(bound[key] == proposed[key] for key in ("goal_id", "criteria_id"))
                if not valid:
                    raise SeedError("阶段先后关系与原始安排不一致；原记录已保留。")
        known[row["id"]] = row


def projection(goal, loaded):
    if not valid_link(goal, loaded["originals"]):
        return {}
    event = loaded["originals"][goal["project"]["event_id"]]
    payload = stored(event)
    stages = []
    for stage in payload["proposal"]["stages"]:
        identifier = payload["goal_ids"][stage["key"]]
        current = loaded["state"]["goals"].get(identifier)
        stages.append({"goal_id": identifier, "title": current["title"] if current else "",
                       "status": current["status"] if current else "unavailable", "selected": identifier == goal["id"]})
    return {"title": payload["proposal"]["title"], "reason": payload["proposal"]["reason"],
            "origin": "model", "stages": stages}


@durable
def apply(pack, raw, *, ctx, day, generation):
    if raw is None:
        return {}
    if ctx.get("_audience_id", "owner") != "owner":
        return {"status": "rejected", "reason": "本次交流不建立私人分阶段安排。"}
    if (any(not isinstance(generation.get(key), str) or not generation[key].strip() for key in ("model", "runner")) or generation["runner"] == "runtime"
            or str(generation["runner"]).startswith("stub") or generation.get("fallback") or generation.get("runtime_guard")):
        return {"status": "rejected", "reason": "回退或固定响应不作为个体的分阶段安排。"}
    # Read failures and storage errors propagate; malformed proposals alone are rejected.
    policy = MemoryPolicy.load(pack)
    loaded = learning.view(pack, policy=policy)
    all_goals = development.load_development(pack)["goals"]
    shown = {g["id"]: g for g in ctx.get("development", {}).get("goals", [])}
    supplied = {item["goal_id"]: item.get("criteria", {}) for item in ctx.get("learning", [])}
    available = {row["id"]: row for row in ctx.get("evidence", []) if policy.allows(row)
                 and row.get("kind") not in ("forget", "dream", "creation", "goal_project", "plan_decision")
                 and "梦" not in (row.get("tags") or [])}
    known_refs = {(event["id"], experience.source_of(event)) for event in loaded["originals"].values()}
    known_refs.update((row["id"], row.get("source", "")) for row in policy.records)
    try:
        proposal = clean(raw)
        if not policy.allows_generation(generation):
            raise SeedError("本轮上下文的依据已变化，需要重新考虑安排。")
        refs = []
        for identifier in proposal["evidence"]:
            resolved = development._evidence({"evidence": [identifier]}, available, "mind/development.jsonl", ctx.get("current_evidence", []))
            if (not resolved or len(policy.supports(resolved)) != len(resolved)
                    or any((ref["id"], ref["source"]) not in known_refs for ref in resolved)):
                raise SeedError("分阶段安排只能引用本次实际提供且仍有效的依据。")
            refs.extend(resolved)
        fingerprint = sha256(canonical_json(proposal))
        previous = next((event for event in loaded["originals"].values()
                         if event.get("kind") == "goal_project" and event.get("metadata", {}).get("proposal_hash") == fingerprint), None)
        if previous:
            payload = stored(previous)
            if not payload or not policy.allows(previous) or any(identifier not in loaded["state"]["goals"] for identifier in payload["goal_ids"].values()):
                raise SeedError("先前安排的依据已不可用，不能自动重新建立。")
            return {"status": "unchanged", "project_id": previous["id"], "goal_ids": payload["goal_ids"], "title": proposal["title"]}
        if sum(goal["status"] == "active" for goal in all_goals.values()) + len(proposal["stages"]) > development.MAX_ACTIVE_GOALS:
            raise SeedError("当前进行中的目标过多，请先明确完成、暂停或放下部分目标。")
        occupied = {goal["title"] for goal in all_goals.values() if goal["status"] in ("active", "paused")}
        if any(stage["title"] in occupied for stage in proposal["stages"]):
            raise SeedError("阶段与已有目标重名，请明确区分，不能覆盖已有目标。")
        from .goal_dependencies import bind
        for stage in proposal["stages"]:
            for ref in stage["after"]:
                if "stage" in ref:
                    continue
                identifier = ref["goal_id"]
                standard = loaded["criteria"].get(identifier)
                goal = loaded["state"]["goals"].get(identifier)
                if (not standard or not goal or shown.get(identifier, {}).get("event_id") != goal["event_id"]
                        or supplied.get(identifier) != standard):
                    raise SeedError("已有前置目标及其完整条件必须是本次实际提供的当前版本。")
                _, evidence = bind([ref], goal_id="", loaded=loaded)
                refs.extend(evidence)
    except SeedError as error:
        return {"status": "rejected", "reason": str(error)}
    identifiers = {stage["key"]: "g_" + uuid.uuid4().hex[:16] for stage in proposal["stages"]}
    from .disclosure import stamp
    metadata = {**generation, **stamp("owner"), "project_format": FORMAT, "proposal_hash": fingerprint}
    metadata["context_dependencies"] = sorted(set(generation.get("context_dependencies", [])) | {ref["id"] for ref in refs})
    event = experience.record(pack, kind="goal_project", actor="model", day=day["dayNo"], source="mind/development.jsonl",
        text=canonical_json({"proposal": proposal, "goal_ids": identifiers}),
        depends_on=metadata["context_dependencies"], metadata=metadata)
    source = experience.source_of(event)
    evidence = [{"id": event["id"], "source": source, "kind": event["kind"]}]
    changes, criteria = [], {}
    for stage in proposal["stages"]:
        dependencies = [{"goal_id": identifiers[ref["stage"]], "criteria_id": criteria[ref["stage"]]["id"]}
                        if "stage" in ref else ref for ref in stage["after"]]
        # Include each newly saved stage without reloading a partially built graph.
        bound, _ = bind(dependencies, goal_id=identifiers[stage["key"]], loaded=loaded)
        data = {"id": identifiers[stage["key"]], "title": stage["title"], "next_step": stage["next_step"],
                "reason": proposal["reason"], "status": "active", "created_day": day["dayNo"],
                "origin": "model", "evidence": evidence, "generation": metadata,
                "project": {"event_id": event["id"], "sha256": sha256(canonical_json(event)), "stage": stage["key"]}}
        row = development._append(pack, "goal", data, day=day["dayNo"], source=source, runner=generation["runner"])
        standard = learning.define(pack, data, stage["criteria"], skill=stage["skill"], evidence=evidence,
                                   source=source, origin="model", prerequisites=bound)
        changes.append(row)
        criteria[stage["key"]] = standard
        loaded["state"]["goals"][data["id"]] = {**data, "event_id": row["id"]}
        loaded["criteria"][data["id"]] = standard
        loaded["rows"].append(standard)
    return {"status": "accepted", "project_id": event["id"], "goal_ids": identifiers,
            "title": proposal["title"], "changes": changes}
