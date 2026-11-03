"""Bounded personal actions, executed locally with factual receipts."""
from pathlib import Path
import uuid

from . import body, development, experience, learning, model_budget
from .durability import RecoveryRequired
from .hands import apply_actions
from .pack_lock import durable, serialized
from .util import SeedError, now_iso, write_file_atomic


class ActionBlocked(SeedError):
    def __init__(self, detail, evidence=()):
        super().__init__(detail)
        self.evidence = list(evidence)


def _failure_detail(error, audience_id, *, started):
    if audience_id == "owner":
        return str(error)
    # Exceptions and private control reasons may contain local paths or private
    # facts. External receipts report the result, never those diagnostics.
    return "本次操作未完成；请检查请求或稍后再试。" if started else "本次未执行这项操作。"


@serialized
def execute(pack, proposals, *, day, source, brain, memories, evidence=(), generation=None, person_id="owner", audience_id="owner",
            interaction_kind="direct", blocked_reason=""):
    from .lifecycle import require_active
    require_active(pack)
    if not isinstance(proposals, list):
        return []
    from .disclosure import policy_for, stamp
    policy = policy_for(pack, audience_id, person_id)
    state = development.current_state(pack, policy=policy)
    generation = dict(generation or {"runner": getattr(brain, "name", "")})
    generation.update(stamp(audience_id))
    available = {m["id"]: m for m in memories if policy.allows(m)
                 and m.get("kind") not in ("forget", "dream", "creation") and "梦" not in (m.get("tags") or [])}
    receipts = []
    for action in proposals[:1]:
        if not isinstance(action, dict):
            continue
        kind = str(action.get("type") or "")
        goal_id = str(action.get("goal_id") or "")
        from .plan_links import capture
        plan_reference = capture(pack, day["dayNo"], execution="automatic", audience_id=audience_id)
        refs = list(evidence)
        if goal_id in state["goals"]:
            refs.extend(state["goals"][goal_id].get("evidence", []))
        from .action_proposals import capture as capture_proposal
        proposal = capture_proposal(action, source=source, generation=generation, evidence=refs)
        started = False
        try:
            prepared = _prepare(pack, action, kind=kind, goal_id=goal_id, day=day, state=state,
                                policy=policy, available=available, audience_id=audience_id,
                                blocked_reason=blocked_reason)
            started = True
            receipt = _perform(pack, prepared, kind=kind, goal_id=goal_id, day=day, source=source,
                               brain=brain, policy=policy, available=available, refs=refs,
                               generation=generation, person_id=person_id, audience_id=audience_id,
                               interaction_kind=interaction_kind, plan_reference=plan_reference, proposal=proposal)
        except RecoveryRequired:
            # Unresolved recovery must stop the request, not become an ordinary
            # failed action followed by more writes to the same pack.
            raise
        except (SeedError, ValueError, OSError) as error:
            if isinstance(error, model_budget.Exhausted):
                # The nested generation was stopped before model dispatch;
                # _perform's savepoint has already undone preparatory writes.
                started = False
                error = ActionBlocked(str(error))
            if not started and not isinstance(error, ActionBlocked):
                # Broken archives or unavailable storage during preparation are
                # request errors, not evidence of a failed creative attempt.
                raise
            receipt = development.record_outcome(pack, action=kind or "unknown",
                                                  status="failed" if started else "blocked",
                                                  detail=_failure_detail(error, audience_id, started=started),
                                                  day=day["dayNo"], source=source, goal_id=goal_id,
                                                  evidence=list(evidence) + getattr(error, "evidence", []), generation=generation,
                                                  plan_reference=plan_reference, attempt_state="started" if started else "not_started",
                                                  proposal=proposal)
        receipts.append(receipt)
    return receipts


def _prepare(pack, action, *, kind, goal_id, day, state, policy, available, audience_id, blocked_reason=""):
    """Read-only checks under execute's writer lock, before ability dispatch."""
    if blocked_reason:
        raise ActionBlocked(blocked_reason)
    # Check the recipient's goal scope before the private scheduling gate. A
    # guessed private goal ID must not reveal whether it matches today's focus.
    if audience_id != "owner" and goal_id and (goal_id not in state["goals"] or state["goals"][goal_id]["status"] != "active"):
        raise ActionBlocked("行动引用的目标不存在或已经暂停/结束。")
    from .deliberation import blocked_reason as choice_blocks
    reason = choice_blocks(pack, day=day["dayNo"], action=kind, goal_id=goal_id, policy=policy,
                           audience_id=audience_id)
    if reason:
        support = []
        if audience_id == "owner":
            from .agency import current_plan
            from .deliberation import valid
            choice = current_plan(pack, day["dayNo"]) or {}
            support = choice.get("evidence", []) if valid(pack, choice, policy=policy) else []
            if support:
                from .plan_checkpoints import for_plan
                support = list(support) + for_plan(pack, choice, policy=policy).get("evidence", [])
            elif choice.get("origin") != "model":
                from .plan_continuity import pending_evidence
                support = pending_evidence(pack, day=day["dayNo"], policy=policy)
            from .goal_dependencies import readiness, BLOCKED
            if reason == BLOCKED:
                support = list(support) + readiness(pack, goal_id)["evidence"]
        raise ActionBlocked(reason, support)
    if kind not in ("remind", "compose", "reflect", "rest"):
        raise ActionBlocked("当前载体不支持这项行动。")
    if kind == "remind" and audience_id != "owner":
        raise ActionBlocked("私人提醒需要在用户的私人交流中建立。")
    if goal_id and (goal_id not in state["goals"] or state["goals"][goal_id]["status"] != "active"):
        raise ActionBlocked("行动引用的目标不存在或已经暂停/结束。")
    if goal_id and kind in ("compose", "reflect"):
        from .goal_dependencies import readiness, BLOCKED, EXTERNAL_BLOCKED
        required = readiness(pack, goal_id)
        if not required["ready"]:
            raise ActionBlocked(BLOCKED if audience_id == "owner" else EXTERNAL_BLOCKED,
                                required["evidence"] if audience_id == "owner" else [])
    if kind != "remind" and not str(action.get("reason") or "").strip():
        raise ActionBlocked("这次行动还没有留下选择理由。")
    costly = kind in ("compose", "reflect")
    if costly and body.state(pack)["energy"] < 0.15:
        raise ActionBlocked("当前精力不足，先休息或调整计划。")
    if costly and sum(r["day"] == day["dayNo"] and r["status"] == "succeeded"
                      and r["action"] in ("compose", "reflect") for r in development.load_development(pack)["outcomes"]) >= 4:
        raise ActionBlocked("今天已经完成四次创作或整理，下一步留到以后。")
    prepared = dict(action)
    if kind == "compose":
        if model_budget.exhausted():
            raise ActionBlocked(model_budget.BLOCKED)
        from .works import _clean_kind
        try:
            prepared["kind"] = _clean_kind(action.get("kind"))
        except SeedError as error:
            raise ActionBlocked(str(error)) from error
    if kind == "reflect":
        memory_ids = action.get("memory_ids")
        memory_ids = [str(ref) for ref in memory_ids[:6]] if isinstance(memory_ids, list) else []
        text = str(action.get("text") or "").strip()[:1000]
        if not memory_ids or any(ref not in available for ref in memory_ids) or not text:
            raise ActionBlocked("反思需要可召回的真实记忆 ID 和反思正文。")
        prepared.update(memory_ids=memory_ids, text=text)
    return prepared


@durable
def _perform(pack, action, *, kind, goal_id, day, source, brain, policy, available, refs,
             generation, person_id, audience_id, interaction_kind, plan_reference=None, proposal=None):
    """Dispatch a prepared ability and commit its effects with the receipt."""
    if kind == "compose":
        from .cognition import compose_work
        result = compose_work(pack, str(action.get("kind") or "poem"), brain,
                              day=day, topic=str(action.get("topic") or "")[:200], goal_id=goal_id,
                              person_id=person_id, audience_id=audience_id, interaction_kind=interaction_kind,
                              _plan_reference=plan_reference, _action_proposal=proposal)
        return result["receipt"]
    artifact = ""
    action_source = source
    if kind == "remind":
        results = apply_actions(pack, day["dayNo"], now_iso(), [action])
        if not results:
            raise SeedError("提醒未建立：内容或日期无效，或提醒数量已满。")
        artifact = "mind/hands.json#" + results[0]["id"]
        detail = "已建立提醒：" + results[0]["text"] + "；尚未送达。"
    elif kind == "reflect":
        from .goal_dependencies import execution_reference
        prerequisite_check, prerequisite_evidence = execution_reference(pack, goal_id) if goal_id else ({}, [])
        memory_ids, text = action["memory_ids"], action["text"]
        artifact = "art/reflections/" + uuid.uuid4().hex + ".md"
        citations = "\n".join(f"- {ref}：{available[ref]['text']}" for ref in memory_ids)
        write_file_atomic(Path(pack) / artifact,
                          f"# 第 {day['dayNo']} 天的反思\n\n## 依据\n{citations}\n\n## 我的解释（可以修正）\n{text}\n")
        cited = [{"id": identifier, "source": available[identifier].get("source") or source,
                  "kind": available[identifier].get("kind", "thought")} for identifier in memory_ids]
        reflection = experience.record(pack, kind="thought", text=text, day=day["dayNo"], source=artifact,
                                       actor="model", depends_on=[r["id"] for r in refs + cited + prerequisite_evidence],
                                       metadata={**generation, "action": "reflect",
                                           **({"prerequisite_check": prerequisite_check} if prerequisite_check else {})})
        action_source = experience.source_of(reflection)
        refs = [{"id": reflection["id"], "source": action_source, "kind": "thought"}, *cited, *refs]
        body.spend(pack, "reflect")
        detail = "已保存一次有来源的反思；其中的解释尚可修正。"
    else:
        body.spend(pack, "rest")
        detail = "已选择休息；精力按实际经过的时间恢复。"
    return development.record_outcome(pack, action=kind, status="succeeded", detail=detail,
                                      day=day["dayNo"], source=action_source, goal_id=goal_id, artifact=artifact,
                                      evidence=refs, generation=generation, plan_reference=plan_reference, proposal=proposal,
                                      practice=learning.practice_reference(learning.for_goal(pack, goal_id,
                                          loaded=learning.view(pack, policy=policy)), "available_at_execution") if goal_id else {})
