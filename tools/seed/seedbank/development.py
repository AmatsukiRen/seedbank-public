"""Evidence-backed, portable development. The event log is the source of truth.

Model proposals describe interpretations, never external facts or action results.
Only the runtime writes action receipts. Old life packs opt in lazily.
"""
from __future__ import annotations

import json
import math
import uuid
from copy import deepcopy
from pathlib import Path

from .util import SeedError, now_iso
from . import jsonl
from .memory_state import MemoryPolicy
from .pack_lock import durable

FORMAT = "seedbank/development@1"
MAX_ACTIVE_GOALS = 6


def _text(value, limit=300):
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _path(pack):
    return Path(pack) / "mind" / "development.jsonl"


def events(pack):
    return jsonl.read(_path(pack), _validate)


def _validate(row, number):
    if not isinstance(row, dict) or row.get("format") != FORMAT:
        raise SeedError(f"第 {number} 条成长记录格式无法识别；原文件已保留。")
    kind, data = row.get("kind"), row.get("data")
    required = {"belief": ("id", "text", "confidence", "reason"),
                "goal": ("id", "title", "status", "next_step", "reason"),
                "preference": ("id", "topic", "stance", "reason"),
                "outcome": ("action", "status", "detail")}
    if (not row.get("id") or not isinstance(row.get("day"), int) or not row.get("at")
            or kind not in required or not isinstance(data, dict)
            or any(key not in data for key in required[kind])):
        raise SeedError(f"第 {number} 条成长记录内容不完整；原文件已保留。")
    if kind == "outcome" and "attempt_state" in data and not _valid_attempt_state(data["status"], data["attempt_state"]):
        raise SeedError(f"第 {number} 条行动回执的开始状态与结果不一致；原文件已保留。")
    if kind == "outcome" and "proposal" in data:
        from .action_proposals import valid
        if not valid(data["proposal"]):
            raise SeedError(f"第 {number} 条行动回执的提议来源不完整；原文件已保留。")


def _valid_attempt_state(status, value):
    return (status == "succeeded" and value == "started" or status == "blocked" and value == "not_started"
            or status == "failed" and value in ("started", "unknown"))


def execution_state(outcome):
    """Do not infer whether a legacy failed action reached ability dispatch."""
    fallback = "started" if outcome.get("status") == "succeeded" else "not_started" if outcome.get("status") == "blocked" else "unknown"
    return outcome.get("attempt_state", fallback)


def practice_counts(outcomes):
    counts = {}
    for row in outcomes:
        skill, state = row.get("action"), execution_state(row)
        if skill not in ("compose", "reflect") or state == "not_started":
            continue
        count = counts.setdefault(skill, {"attempts": 0, "completed": 0, "unknown_attempts": 0})
        count["attempts"] += int(state == "started")
        count["completed"] += int(row.get("status") == "succeeded")
        count["unknown_attempts"] += int(state == "unknown")
    return counts


def attempt_label(outcome):
    from .i18n import t
    return t({"started": "已进入执行流程", "not_started": "未进入执行流程"}.get(execution_state(outcome), "未记录是否开始执行"))


def _append(pack, kind, data, *, day, source, runner="runtime"):
    row = {"format": FORMAT, "id": "d_" + uuid.uuid4().hex,
           "at": now_iso(), "day": int(day), "kind": kind,
           "source": str(source), "runner": str(runner), "data": data}
    jsonl.append(pack, _path(pack), [row], _validate)
    return row


def load_development(pack, *, goal_events=None, _events=None):
    state = {"beliefs": {}, "goals": {}, "preferences": {}, "outcomes": [],
             "skills": {}, "recent": []}
    for event in events(pack) if _events is None else _events:
        kind, data = event.get("kind"), event.get("data", {})
        if not isinstance(data, dict):
            continue
        if kind in ("belief", "goal", "preference"):
            if kind == "goal" and goal_events is not None:
                pair = goal_events.setdefault(str(data["id"]), {"first": event})
                pair["latest"] = event
            item = {**data, "event_id": event["id"], "day": event["day"], "updated_at": event["at"]}
            bucket = {"belief": "beliefs", "goal": "goals", "preference": "preferences"}[kind]
            state[bucket].pop(str(data["id"]), None)
            state[bucket][str(data["id"])] = item
        elif kind == "outcome":
            item = {**data, "id": event["id"], "day": event["day"], "at": event["at"], "source": event["source"]}
            state["outcomes"].append(item)
        state["recent"].append(event)
    state["recent"] = state["recent"][-12:]
    state["skills"] = practice_counts(state["outcomes"])
    return state


def current_state(pack, *, policy=None, _events=None):
    goal_events = {}
    state = load_development(pack, goal_events=goal_events, _events=_events)
    policy = policy or MemoryPolicy.load(pack)
    project_sources = None
    for bucket in ("beliefs", "preferences", "goals"):
        visible = {}
        for key, item in state[bucket].items():
            if not policy.allows_generation(item.get("generation")):
                continue
            if bucket == "goals" and "project" in item:
                from .goal_projects import valid_link
                if project_sources is None:
                    from .experience import read
                    project_sources = {event["id"]: event for event in read(pack)}
                if not valid_link(item, project_sources, policy):
                    continue
            support = policy.supports(item.get("evidence", []))
            if support and (not item.get("completion") or len(support) == len(item.get("evidence", []))):
                visible[key] = {**item, "evidence": support,
                                "support_changed": len(support) != len(item.get("evidence", []))}
                if bucket == "goals":
                    from .goal_provenance import project
                    visible[key]["provenance"] = project(goal_events[key], policy)
        state[bucket] = visible
    state["outcomes"] = [r for r in state["outcomes"] if outcome_visible(r, policy)]
    state["skills"] = practice_counts(state["outcomes"])
    visible_outcomes = {row["id"] for row in state["outcomes"]}
    state["recent"] = [event for event in state["recent"]
                       if policy.allows_source(event.get("source"))
                       and (event["kind"] != "outcome" or event["id"] in visible_outcomes)
                       and (event["kind"] == "outcome" or policy.supports(event["data"].get("evidence", [])))]
    return state


def outcome_visible(row, policy):
    from .action_proposals import visible as proposal_visible
    return (row.get("id") not in policy.blocked and policy.allows_source(row.get("source"))
            and policy.allows_generation(row.get("generation"))
            and proposal_visible(row.get("proposal"), policy)
            and (not row.get("evidence") or len(policy.supports(row["evidence"])) == len(row["evidence"]))
            and ("#" in str(row.get("source", "")) or str(row.get("source", "")).split("#", 1)[0] not in policy.affected_sources))


def summary(pack, *, policy=None, day=None, _lineage=None, _state=None):
    policy = policy or MemoryPolicy.load(pack)
    state = current_state(pack, policy=policy) if _state is None else _state
    goals = list(state["goals"].values())
    ongoing = [g for g in goals if g["status"] in ("active", "paused")]
    ended = [g for g in goals if g["status"] in ("completed", "abandoned")]
    selected = ended[-10:] + ongoing
    if any(g.get("completion") for g in selected):
        from . import learning
        loaded = learning.view(pack, state=state, policy=policy)
        selected = [{**g, "completion_current": learning.evaluate(pack, g["id"], g.get("completion_evidence"), loaded=loaded)}
                    if g.get("completion") else g for g in selected]
    from .plan_links import recent as plan_review
    from .plan_continuity import candidates as prior_choices
    from .story_lineage import Lineage
    lineage = _lineage if _lineage is not None else Lineage(pack, policy)
    return {"beliefs": lineage.annotate_many(list(state["beliefs"].values())[-20:]),
            "goals": lineage.annotate_many(selected),
            "preferences": lineage.annotate_many(list(state["preferences"].values())[-20:]),
            "outcomes": state["outcomes"][-10:], "skills": state["skills"],
            # Display-only slice; the prompt already has its recent outcomes.
            "inner_attempts": [row for row in state["outcomes"]
                               if row.get("generation", {}).get("operation") == "inner"][-5:],
            "skill_dependencies": sorted({ref for row in state["outcomes"]
                if row.get("action") in ("compose", "reflect") and execution_state(row) != "not_started"
                for ref in outcome_dependencies(row)}),
            "plan_review": plan_review(pack, state=state, policy=policy),
            "prior_choices": prior_choices(pack, state=state, policy=policy, day=day),
            "recent": state["recent"]}


def _evidence(proposal, available, source, current_evidence=None):
    refs = proposal.get("evidence")
    if not isinstance(refs, list):
        return []
    accepted = []
    for ref in refs[:6]:
        ref = str(ref)
        if ref == "current" and source:
            if current_evidence is not None:
                for item in current_evidence[:6]:
                    if item not in accepted:
                        accepted.append(dict(item))
                continue
            item = {"id": "current", "source": source, "kind": "legacy_current_interaction"}
        elif ref in available:
            memory = available[ref]
            item = {"id": ref, "source": memory.get("source", ""),
                    "kind": memory.get("kind", "thought")}
        else:
            continue
        if item not in accepted:
            accepted.append(item)
    return accepted


@durable
def apply_proposals(pack, proposals, *, day, source, runner, memories=(), current_evidence=None, generation=None,
                    policy=None, permitted_ids=None):
    """Accept bounded, sourced interpretations; preserve all earlier versions."""
    if not isinstance(proposals, dict):
        return []
    policy = policy if policy is not None else MemoryPolicy.load(pack)
    available = {str(m.get("id")): m for m in memories if isinstance(m, dict) and policy.allows(m)
                 and m.get("kind") not in ("forget", "dream", "creation") and "梦" not in (m.get("tags") or [])}
    state = load_development(pack)
    from . import learning
    standards = learning.view(pack, policy=policy)["criteria"]
    applied = []
    for plural, kind in (("beliefs", "belief"), ("goals", "goal"), ("preferences", "preference")):
        items = proposals.get(plural)
        if not isinstance(items, list):
            continue
        for proposal in items[:3]:
            if not isinstance(proposal, dict):
                continue
            evidence = policy.supports(_evidence(proposal, available, source, current_evidence))
            reason = _text(proposal.get("reason"))
            if not evidence or not reason:
                continue
            identifier = _text(proposal.get("id"), 80)
            if identifier and permitted_ids is not None and identifier not in permitted_ids:
                continue
            previous = state[plural].get(identifier)
            if identifier and previous is None:
                continue
            data = dict(previous or {})
            data.update(id=identifier or f"{kind[0]}_{uuid.uuid4().hex[:16]}",
                        reason=reason, evidence=evidence)
            data.pop("event_id", None)
            data.pop("day", None)
            data.pop("updated_at", None)
            data["generation"] = dict(generation or {})
            if kind == "goal" and not previous:
                data["origin"] = "model"
            if previous:
                data["supersedes_event"] = previous.get("event_id", "")
            if kind == "belief":
                content = _text(proposal.get("text"))
                if not content:
                    continue
                try:
                    confidence = float(proposal.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5
                if not math.isfinite(confidence):
                    confidence = 0.5
                data.update(text=content, confidence=round(max(0.05, min(0.95, confidence)), 2))
                if not previous and any(b["text"] == content for b in state[plural].values()):
                    continue
            elif kind == "preference":
                topic = _text(proposal.get("topic"), 60)
                stance = proposal.get("stance")
                if not topic or stance not in ("like", "avoid", "unsure"):
                    continue
                if not previous:
                    previous = next((p for p in state[plural].values() if p["topic"] == topic), None)
                    if previous:
                        if permitted_ids is not None and previous["id"] not in permitted_ids:
                            continue
                        data["id"] = previous["id"]
                        data["supersedes_event"] = previous.get("event_id", "")
                data.update(topic=topic, stance=stance)
            else:
                title = _text(proposal.get("title") or data.get("title"), 120)
                status = proposal.get("status", data.get("status", "active"))
                if not title or status not in ("active", "paused", "completed", "abandoned"):
                    continue
                if previous and previous.get("status") in ("completed", "abandoned"):
                    continue
                standard = standards.get(identifier)
                if standard and title != previous.get("title"):
                    continue
                proposed_criteria = None
                if "criteria" in proposal:
                    try:
                        proposed_criteria = learning.clean_criteria(proposal["criteria"])
                        if not any(item["check"] == "feedback" for item in proposed_criteria):
                            continue
                        if standard and proposed_criteria != standard["data"]["items"]:
                            continue
                    except SeedError:
                        continue
                if not previous and any(g["title"] == title and g["status"] == "active"
                                        for g in state[plural].values()):
                    continue
                if status == "active" and (not previous or previous["status"] != "active"):
                    if sum(g["status"] == "active" for g in state[plural].values()) >= MAX_ACTIVE_GOALS:
                        continue
                if status == "completed":
                    completion_evidence = proposal.get("completion_evidence")
                    if not completion_evidence and standard and proposal.get("outcome_id"):
                        completion_evidence = {c["id"]: str(proposal["outcome_id"]) for c in standard["data"]["items"]}
                    loaded = learning.view(pack, policy=policy)
                    assessment = learning.evaluate(pack, identifier, completion_evidence, loaded=loaded)
                    if not previous or not assessment["passed"]:
                        continue
                    data.update(completion=assessment, completion_evidence=completion_evidence)
                    completion_refs = list(loaded["criteria"][identifier]["evidence"])
                    completion_refs.extend(assessment.get("prerequisites", {}).get("evidence", []))
                    for check in assessment["checks"]:
                        completion_refs.extend(loaded["outcomes"][check["outcome_id"]].get("evidence", []))
                        review = loaded["feedback"].get((assessment["criteria_id"], check["outcome_id"]))
                        if review:
                            completion_refs.extend(review["evidence"])
                    data["evidence"] = list({ref["id"]: ref for ref in evidence + completion_refs}.values())
                data.update(title=title, status=status,
                            next_step=_text(proposal.get("next_step") or data.get("next_step"), 200),
                            created_day=data.get("created_day", int(day)))
            row = _append(pack, kind, data, day=day, source=source, runner=runner)
            if kind == "goal" and proposed_criteria and not standard:
                standards[data["id"]] = learning.define(pack, data, proposed_criteria,
                    skill=_text(proposal.get("skill") or title, 80), evidence=evidence, source=source, origin="model")
            state[plural][data["id"]] = {**data, "day": day, "event_id": row["id"]}
            applied.append(row)
    return applied


@durable
def record_outcome(pack, *, action, status, detail, day, source, goal_id="", artifact="",
                   evidence=(), generation=None, practice=None, plan_reference=None, attempt_state=None, proposal=None):
    if status not in ("succeeded", "failed", "blocked"):
        raise SeedError("行动结果状态无效。")
    attempt_state = attempt_state if attempt_state is not None else execution_state({"status": status})
    if not _valid_attempt_state(status, attempt_state):
        raise SeedError("行动开始状态与结果不一致。")
    data = {"action": str(action), "status": status, "detail": _text(detail, 500),
            "attempt_state": attempt_state,
            "goal_id": str(goal_id), "artifact": str(artifact), "evidence": list(evidence),
            "generation": dict(generation or {}), "practice": dict(practice or {})}
    if proposal is not None:
        data["proposal"] = deepcopy(proposal)
    if plan_reference:
        from .plan_links import resolve
        from .disclosure import stamp
        entry = resolve(pack, plan_reference)
        if not entry or entry["plan"]["day"] != day:
            raise SeedError("行动对应的计划版本或依据已变化；未保存错误关联。")
        data["plan_reference"] = dict(plan_reference)
        for ref in entry["plan"].get("evidence", []):
            if ref not in data["evidence"]:
                data["evidence"].append(dict(ref))
        data["generation"].update(stamp("owner"))
        data["generation"]["context_dependencies"] = sorted(set(
            data["generation"].get("context_dependencies", []))
            | set(entry["plan"].get("generation", {}).get("context_dependencies", [])))
    if status == "succeeded" and action in ("compose", "reflect") and artifact:
        from .learning import snapshot
        data["artifact_snapshot"] = snapshot(pack, artifact)
    return _append(pack, "outcome", data, day=day, source=source)


def choose_plan(pack, day, *, energy=1.0):
    state = current_state(pack)
    if energy < 0.25:
        return {"day": day, "plan": "留些时间休息，再决定下一步", "done": False,
                "reason": "当前精力较低", "goal_id": ""}
    goals = [g for g in state["goals"].values() if g.get("status") == "active"]
    if not goals:
        return None
    from . import learning
    from .goal_dependencies import readiness
    loaded = learning.view(pack, state=state)
    ready = {goal["id"]: readiness(pack, goal["id"], loaded=loaded) for goal in goals}
    goals = [goal for goal in goals if ready[goal["id"]]["ready"]]
    if not goals:
        return None
    attempts = {g["id"]: sum(r.get("goal_id") == g["id"] and r.get("action") in ("compose", "reflect")
                             and execution_state(r) == "started" for r in state["outcomes"]) for g in goals}
    goal = min(goals, key=lambda g: (attempts[g["id"]], g.get("created_day", day)))
    return {"day": day, "plan": goal.get("next_step") or goal["title"], "done": False,
            "reason": goal["reason"], "goal_id": goal["id"], "goal_event_id": goal["event_id"],
            "evidence": list({ref["id"]: ref for ref in goal.get("evidence", []) + ready[goal["id"]]["evidence"]}.values())}


def outcome_dependencies(outcome):
    """References understood by memory/disclosure policy, not ledger-only IDs."""
    refs = {str(ref["id"]) for ref in outcome.get("evidence", []) if ref.get("id") not in (None, "", "current")}
    refs.update(outcome.get("generation", {}).get("context_dependencies", []))
    from .action_proposals import dependencies as proposal_dependencies
    refs.update(proposal_dependencies(outcome.get("proposal")))
    parts = str(outcome.get("source", "")).split("#", 1)
    if len(parts) == 2 and parts[1]:
        refs.add(parts[1])
    return sorted(refs)


def prompt_lines(state, *, compact=False):
    lines = ["Sourced, revisable judgments; not external facts or fixed personality." if compact else
             "以下是由经历形成的当前看法，可修正；不是外部事实或不可改变的性格卡。"]
    def interpretation_notes(item):
        if item.get("interpretation_updates"):
            lines.append("  相关人生理解的版本说明（不自动替换当前看法或选择）：" + json.dumps(item["interpretation_updates"], ensure_ascii=False))
            lines.append("  origin=user 是用户整理的解释；直接来源包含新版本不等于已采纳，current_unavailable 不提供当前解释。")
            if item.get("interpretation_update_count", 0) > len(item["interpretation_updates"]):
                lines.append("  还有相关版本说明未展开，不表示没有其他变化。")
    for belief in state.get("beliefs", []):
        lines.append(f"信念 {belief['id']}：{belief['text']}（把握 {belief['confidence']}；理由：{belief['reason']}）")
        if belief.get("support_changed"):
            lines.append("  部分原有依据已不可用，不能按原把握直接沿用；需要重新审视。")
        interpretation_notes(belief)
    for preference in state.get("preferences", []):
        lines.append(f"偏好 {preference['id']}：{preference['topic']} / {preference['stance']}；{preference['reason']}")
        interpretation_notes(preference)
    if any(goal.get("provenance") for goal in state.get("goals", [])):
        lines.append("Goal provenance records activity, not proof of independent motivation; user=manual setting, conversation=dialogue, initiative=scheduled solitude, forced_initiative=forced run, diary=diary review, fixed=template/fallback, unrecorded=unknown, unavailable=withheld.")
    for goal in state.get("goals", []):
        lines.append(f"目标 {goal['id']} [{goal['status']}]：{goal['title']}；下一步：{goal['next_step']}；{goal['reason']}")
        if goal.get("provenance"):
            lines.append("  provenance: " + ", ".join(key + "=" + goal["provenance"][key]["kind"] for key in ("first", "latest")))
        interpretation_notes(goal)
        if goal["status"] == "completed":
            check = goal.get("completion_current")
            lines.append("  完成仅在记录的条件范围内成立；当前依据仍满足条件。" if check and check.get("passed") else
                         "  这是历史完成记录，当前没有充分的条件核对依据，不能声称已核实完成。")
    for result in state.get("outcomes", []):
        lines.append(f"行动回执 {result['id']}：{result['action']} / {result['status']}；{attempt_label(result)}；目标 {result.get('goal_id', '')}；{result['detail']}")
        from .action_proposals import prompt_lines as proposal_lines
        lines.extend(proposal_lines(result))
    if state.get("skills"):
        lines.append(("Attempt counts, not quality/mastery: " if compact else "执行尝试统计（不等同于练习质量或掌握程度）：")
                     + json.dumps(state["skills"], ensure_ascii=False)
                     + ("; attempts=execution entered, not model calls/finished practice; completed=action succeeded. "
                        "unknown_attempts excluded, not no attempt. Service/format/empty failures prove no artifact, "
                        "not low ability/mood/ineffective learning. available_at_execution != supplied/adopted." if compact else
                       "；attempts 仅计已进入能力执行流程的次数，不证明已经调用模型或完成练习；completed 仅指动作成功。"
                       "unknown_attempts 是未记录是否开始的旧失败或未知记录，不计入已开始次数，也不能当作没有尝试。"
                       "创作服务、格式或空回复故障只说明没有获得作品，不能据此推断能力不足、情绪或经验是否有效。"
                       "available_at_execution 只表示执行前可用的材料，不证明它们已发送给模型或被采用。"))
    from .plan_links import prompt_lines as plan_review_lines
    lines.append(plan_review_lines(state.get("plan_review", [])))
    from .plan_continuity import prompt_lines as prior_choice_lines
    lines.append(prior_choice_lines(state.get("prior_choices", [])))
    return "\n".join(lines)
