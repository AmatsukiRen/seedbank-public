"""A plan may stop at a pinned goal rubric; free text is never auto-certified."""
from .util import SeedError, canonical_json, sha256

FORMAT = "seedbank/plan-checkpoint@1"


def valid_binding(value):
    return (isinstance(value, dict) and set(value) == {"format", "criteria_id", "criteria_sha256"}
            and value.get("format") == FORMAT and isinstance(value.get("criteria_id"), str)
            and value["criteria_id"].startswith("l_") and isinstance(value.get("criteria_sha256"), str)
            and len(value["criteria_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in value["criteria_sha256"]))


def bind(raw, *, mode, goal_id, ctx, loaded):
    """Accept all of one actually offered rubric, never model-supplied standards."""
    if raw is None:
        return None, []
    if mode != "focus" or not isinstance(raw, dict) or set(raw) != {"criteria_id"}:
        raise SeedError("计划结束条件只能绑定专注目标的一份完整条件，不接受自行改写或删减。")
    current = loaded["criteria"].get(goal_id)
    offered = next((item.get("criteria") for item in ctx.get("learning", []) if item.get("goal_id") == goal_id), None)
    if (not current or not offered or raw["criteria_id"] != current["id"]
            or canonical_json(current) != canonical_json(offered)):
        raise SeedError("只能绑定本次实际提供且仍有效的目标完成条件。")
    return {"format": FORMAT, "criteria_id": current["id"], "criteria_sha256": sha256(canonical_json(current))}, current["evidence"]


def evaluate(pack, entry, *, loaded, policy):
    from . import learning, planning, plan_links
    from .development import outcome_dependencies
    plan = entry["plan"]
    binding = plan.get("checkpoint")
    if not binding or getattr(policy, "audience_id", "owner") != "owner":
        return {}
    result = {"passed": False, "state": "unavailable", "criteria_id": "", "criteria": [],
              "matches": [], "dependencies": [], "evidence": []}
    if entry.get("format") not in (planning.CHECKPOINT_FORMAT, planning.CONTINUITY_FORMAT) or not valid_binding(binding) or not plan_links._visible(pack, entry, policy):
        return result
    standard = loaded["criteria"].get(plan["goal_id"])
    if (not standard or standard["id"] != binding["criteria_id"]
            or sha256(canonical_json(standard)) != binding["criteria_sha256"]):
        return {**result, "state": "criteria_changed"}
    refs = {(r["id"], r["source"]): dict(r) for r in standard["evidence"]}
    deps = {r["id"] for r in standard["evidence"]}
    from .goal_dependencies import readiness
    required = readiness(pack, plan["goal_id"], loaded=loaded)
    deps.update(required["dependencies"])
    for ref in required["evidence"]:
        refs[(ref["id"], ref["source"])] = dict(ref)
    if not required["ready"]:
        return {**result, "state": "prerequisites", "dependencies": sorted(deps), "evidence": list(refs.values())}
    groups = {}
    for item in standard["data"]["items"]:
        groups.setdefault(item["group"], []).append(item)
    digest = plan_links._digest(entry)
    eligible = [row for row in reversed(loaded["state"]["outcomes"])
                if row.get("goal_id") == plan["goal_id"] and row.get("day") == plan["day"]
                and row.get("status") == "succeeded"
                and row.get("practice", {}).get("criteria_id") == standard["id"]
                and plan_links._matches(row.get("plan_reference"), entry, digest)]
    candidates = {group: [] for group in groups}
    checked = {}
    for row in eligible:
        deps.update(outcome_dependencies(row))
        for ref in row.get("evidence", []):
            refs[(ref["id"], ref["source"])] = dict(ref)
        review = loaded["feedback"].get((standard["id"], row["id"]))
        if review:
            for ref in review["evidence"]:
                refs[(ref["id"], ref["source"])] = dict(ref)
                deps.add(ref["id"])
        for group, items in groups.items():
            checks = [learning.evaluate_criterion(pack, plan["goal_id"], standard, item, row["id"], loaded) for item in items]
            checked[(group, row["id"])] = checks
            if all(check["met"] for check in checks):
                candidates[group].append(row["id"])
    # Maximum matching: conditions for the same deliverable share one result;
    # distinct deliverables need distinct results. At most six groups exist.
    assigned = {}

    def assign(group, seen):
        for identifier in candidates[group]:
            if identifier in seen:
                continue
            seen.add(identifier)
            if identifier not in assigned or assign(assigned[identifier], seen):
                assigned[identifier] = group
                return True
        return False

    for group in groups:
        assign(group, set())
    matches = {group: identifier for identifier, group in assigned.items()}
    details = {row["id"]: row.get("detail", "") for row in eligible}
    passed = len(matches) == len(groups)
    return {"passed": passed, "state": "met" if passed else "pending", "criteria_id": standard["id"],
            "criteria": standard["data"]["items"],
            "matches": [{"group": group, "outcome_id": matches[group], "detail": details[matches[group]],
                         "checks": checked[(group, matches[group])]}
                        for group in groups if group in matches],
            "reason": "criteria_checked" if passed else "distinct_results_required" if all(candidates.values()) else "awaiting_result_or_feedback",
            "dependencies": sorted(deps), "evidence": list(refs.values())}


def for_plan(pack, plan, *, policy=None, _state=None):
    if not plan.get("checkpoint"):
        return {}
    from . import jsonl, learning, planning
    from .memory_state import MemoryPolicy
    policy = policy or MemoryPolicy.load(pack)
    if getattr(policy, "audience_id", "owner") != "owner":
        return {}
    entry = jsonl.find(planning.path(pack), plan.get("plan_id"), planning._validate)
    if not entry:
        return {"passed": False, "state": "unavailable", "dependencies": [], "evidence": []}
    return evaluate(pack, entry, loaded=learning.view(pack, policy=policy, state=_state), policy=policy)


def label(result, *, waiting=False):
    from .i18n import t
    if not result:
        return ""
    if result.get("passed"):
        return t("本次安排的条件已满足，等待下一次选择" if waiting else "本次安排的条件已满足")
    if result.get("state") == "prerequisites":
        return t("前置目标的完成依据需要重新核对")
    if result.get("state") in ("unavailable", "criteria_changed"):
        return t("本次安排的条件或依据已变化，需要重新选择" if waiting else "本次安排的条件或依据已变化")
    return t("本次安排的条件尚未全部满足")
