"""Sourced daily choices from model output, distinct from runtime scheduling."""
from . import body, development, experience, jsonl, planning
from .memory_state import MemoryPolicy
from .pack_lock import durable
from .util import SeedError

CORE = ("day", "plan", "reason", "goal_id", "goal_event_id", "mode", "origin")


def _core(plan):
    result = {key: plan.get(key, "") for key in CORE}
    for key in ("checkpoint", "continuity"):
        if key in plan:
            result[key] = plan[key]
    return result


def valid(pack, plan, *, policy=None):
    if plan.get("origin") != "model" or plan.get("mode") not in ("focus", "rest", "open"):
        return False
    policy = policy or MemoryPolicy.load(pack)
    refs = plan.get("evidence", [])
    event = jsonl.find(experience.path(pack), plan.get("decision_id"), experience._validate)
    return bool(event and event["kind"] == "plan_decision" and policy.allows(event)
                and event["day"] == plan.get("day") and event["actor"] == "model"
                and event["source"] == "mind/plans.jsonl"
                and event["text"] == plan.get("plan", "") + "\n选择理由：" + plan.get("reason", "")
                and event.get("metadata", {}).get("plan_choice") == _core(plan)
                and {k: v for k, v in event["metadata"].items() if k != "plan_choice"} == plan.get("generation")
                and any(ref.get("id") == event["id"] and ref.get("source") == experience.source_of(event) for ref in refs)
                and len(policy.supports(refs)) == len(refs) and policy.allows_generation(plan.get("generation")))


def _text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise SeedError(label + "需要非空文字，且不超过 " + str(limit) + " 字。")
    return value.strip()


@durable
def apply(pack, raw, *, ctx, day, generation, goal_changes=()):
    if raw is None:
        return {}
    if ctx.get("_audience_id", "owner") != "owner":
        return {"status": "rejected", "reason": "本次交流不改动私人日程。"}
    if generation.get("fallback") or str(generation.get("runner", "")).startswith("stub") or generation.get("runtime_guard"):
        return {"status": "rejected", "reason": "回退或固定响应不作为个体的计划选择。"}
    policy = MemoryPolicy.load(pack)
    if not policy.allows_generation(generation):
        return {"status": "rejected", "reason": "本轮上下文的依据已变化，需要重新考虑安排。"}
    state = development.current_state(pack, policy=policy)
    # Storage errors stay outside the proposal-error boundary.
    from .agency import current_plan, load_agency
    existing = current_plan(pack, day["dayNo"])
    known = {r["id"]: r for r in ctx.get("evidence", []) if policy.allows(r)
             and r.get("kind") not in ("forget", "dream", "creation", "plan_decision")
             and "梦" not in (r.get("tags") or [])}
    shown = {g["id"]: g for g in ctx.get("development", {}).get("goals", [])}
    changed = {row["id"] for row in goal_changes if row["kind"] == "goal"}
    from . import learning, plan_checkpoints, plan_continuity, plan_links
    rubric_state = learning.view(pack, state=state, policy=policy) if isinstance(raw, dict) and (raw.get("checkpoint") is not None or raw.get("mode") == "focus") else None
    from .goal_dependencies import readiness, BLOCKED
    required = readiness(pack, raw["goal_id"], loaded=rubric_state) if rubric_state is not None and isinstance(raw.get("goal_id"), str) else {}
    earlier = plan_links._entries(pack) if isinstance(raw, dict) and raw.get("continuity") is not None else []
    eligible = plan_continuity._eligible(pack, entries=earlier, day=day["dayNo"], policy=policy) if earlier else []
    try:
        if not isinstance(raw, dict) or raw.get("mode") not in ("focus", "rest", "open"):
            raise SeedError("每日选择需要 focus、rest 或 open 模式。")
        mode = raw["mode"]
        step = _text(raw.get("next_step"), "今天的安排", 200)
        reason = _text(raw.get("reason"), "选择理由", 300)
        goal_id = raw.get("goal_id", "")
        if not isinstance(goal_id, str) or (mode != "focus" and goal_id):
            raise SeedError("休息或留白不绑定某个目标。")
        goal = state["goals"].get(goal_id)
        refs = []
        if mode == "focus":
            if not goal or goal["status"] != "active" or goal_id not in shown:
                raise SeedError("只能选择本次实际提供且仍在进行中的目标。")
            if goal["event_id"] != shown[goal_id]["event_id"] and goal["event_id"] not in changed:
                raise SeedError("目标版本已变化，需要重新考虑这次选择。")
            if not required.get("ready", True):
                raise SeedError(BLOCKED)
            if required.get("requirements"):
                offered = next((item for item in ctx.get("learning", []) if item.get("goal_id") == goal_id), {})
                if offered.get("criteria", {}).get("id") != rubric_state["criteria"][goal_id]["id"] or offered.get("readiness") != required:
                    raise SeedError("本次未提供有效的前置目标核对结果，请重新考虑安排。")
                refs.extend(required["evidence"])
            refs.extend(goal.get("evidence", []))
        checkpoint, checkpoint_refs = plan_checkpoints.bind(raw.get("checkpoint"), mode=mode, goal_id=goal_id,
                                                            ctx=ctx, loaded=rubric_state)
        refs.extend(checkpoint_refs)
        continuity, prior_refs, prior_deps = plan_continuity.bind(raw.get("continuity"), mode=mode,
            goal_id=goal_id, goal=goal, ctx=ctx, eligible=eligible, policy=policy)
        refs.extend(prior_refs)
        supplied = raw.get("evidence", [])
        if not isinstance(supplied, list) or len(supplied) > 6 or any(not isinstance(ref, str) for ref in supplied):
            raise SeedError("选择依据最多引用六个本次可见来源。")
        for identifier in supplied:
            if identifier == "current":
                current = ctx.get("current_evidence", [])
                if not current or len(policy.supports(current)) != len(current):
                    raise SeedError("这次选择没有可用的当前输入依据。")
                refs.extend(current)
            elif identifier in known:
                row = known[identifier]
                refs.append({"id": identifier, "source": row.get("source", ""), "kind": row.get("kind", "thought")})
            else:
                raise SeedError("选择引用了未提供、已放下或不能作为依据的记录。")
    except SeedError as error:
        return {"status": "rejected", "reason": str(error)}
    refs = list({(ref["id"], ref["source"]): ref for ref in refs}.values())
    core = {"day": day["dayNo"], "plan": step, "reason": reason, "goal_id": goal_id,
            "goal_event_id": goal["event_id"] if mode == "focus" else "", "mode": mode, "origin": "model"}
    if checkpoint is not None:
        core["checkpoint"] = checkpoint
    if continuity is not None:
        core["continuity"] = continuity
    if existing and valid(pack, existing, policy=policy) and _core(existing) == core:
        old_refs = {(r["id"], r["source"]) for r in existing.get("evidence", []) if r["id"] != existing.get("decision_id")}
        if old_refs == {(r["id"], r["source"]) for r in refs}:
            return {"status": "unchanged", "plan": existing}
    generation = {**generation, "audience_id": "owner", "disclosure_version": 1}
    if prior_deps:
        generation["context_dependencies"] = sorted(set(generation.get("context_dependencies", [])) | set(prior_deps))
    if required.get("requirements"):
        generation["context_dependencies"] = sorted(set(generation.get("context_dependencies", [])) | set(required["dependencies"]))
    event = experience.record(pack, kind="plan_decision", text=step + "\n选择理由：" + reason,
        day=day["dayNo"], source="mind/plans.jsonl", actor="model",
        depends_on=[r["id"] for r in refs if r["id"] != "current"] + list(generation.get("context_dependencies", [])),
        metadata={**generation, "plan_choice": core})
    choice = {**core, "done": False, "decision_id": event["id"], "generation": generation,
        "evidence": [{"id": event["id"], "source": experience.source_of(event), "kind": "plan_decision"}, *refs]}
    plan = planning.choose(pack, choice, legacy=load_agency(pack)["plans"], kind="decision", trigger="model_choice",
                           context={"offered_energy": ctx.get("energy"), "energy_at_recording": body.state(pack)["energy"]})
    return {"status": "accepted", "plan": plan}


EXTERNAL_BLOCKED = "本次未执行这项操作；当前暂不安排自动创作或反思。"


def blocked_reason(pack, *, day, action, goal_id, policy, audience_id="owner"):
    """Enforce one schedule across carriers without disclosing its private basis."""
    if action not in ("compose", "reflect"):
        return ""
    private = policy if audience_id == "owner" else MemoryPolicy.load(pack)
    reason = _private_blocked_reason(pack, day=day, goal_id=goal_id, policy=private)
    return EXTERNAL_BLOCKED if reason and audience_id != "owner" else reason


def _private_blocked_reason(pack, *, day, goal_id, policy):
    from .agency import current_plan
    plan = current_plan(pack, day)
    if planning.awaiting_choice(pack, plan):
        return "今天的安排还在等待重新选择，暂不自动创作或反思。"
    if not plan or plan.get("origin") != "model":
        from .plan_continuity import needs_choice
        if needs_choice(pack, day=day, policy=policy):
            return "先前还有值得重新考虑的打算，先明确今天的选择再自动创作或反思。"
        return ""
    if not valid(pack, plan, policy=policy):
        return "今天安排的依据已变化，先重新选择再自动行动。"
    if plan["mode"] == "rest":
        return "今天已选择休息；调整安排前暂不自动创作或反思。"
    if plan["mode"] == "focus":
        current = development.current_state(pack, policy=policy)["goals"].get(plan["goal_id"])
        if not current or current["status"] != "active" or current["event_id"] != plan["goal_event_id"]:
            return "原目标已变化，先调整今天的安排。"
        if goal_id != plan["goal_id"]:
            return "这项自动行动不属于今天选择的目标；先调整安排。"
        from .goal_dependencies import readiness, BLOCKED
        if not readiness(pack, plan["goal_id"])["ready"]:
            return BLOCKED
        from .plan_checkpoints import for_plan, label
        checkpoint = for_plan(pack, plan, policy=policy)
        if checkpoint.get("passed") or checkpoint.get("state") in ("unavailable", "criteria_changed"):
            return label(checkpoint, waiting=True)
    return ""
