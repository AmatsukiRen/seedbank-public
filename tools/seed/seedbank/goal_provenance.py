"""Read-time goal authorship and activity, not an autonomy or motive score.

Only the runtime's proposal_activity stamp identifies the activity. Never infer
it from a model name, a goal's wording, the hour, or a later revision.
"""
from .memory_state import dependencies, is_template

ACTIVITIES = ("conversation", "initiative", "forced_initiative", "diary")
LABELS = {
    "user": "用户设置",
    "conversation": "对话中提出",
    "initiative": "独处活动中提出",
    "forced_initiative": "强制触发的活动中提出",
    "diary": "日记整理中提出",
    "fixed": "固定或回退响应",
    "unrecorded": "当时未记录形成场景",
    "unavailable": "来源目前不可用",
}


def activity(event):
    """Runtime-stamped activity shared by all structured growth versions."""
    generation = event["data"].get("generation", {})
    generation = generation if isinstance(generation, dict) else {}
    if event.get("runner") == "user-learning-v1":
        return "user"
    if is_template(generation) or generation.get("runtime_guard"):
        return "fixed"
    kind = generation.get("proposal_activity")
    return kind if kind in ACTIVITIES else "unrecorded"


def describe(event, policy):
    data = event["data"]
    evidence = data.get("evidence", [])
    generation = data.get("generation")
    generation = generation if isinstance(generation, dict) else {}
    if (not evidence or len(policy.supports(evidence)) != len(evidence)
            or not policy.allows_source(event.get("source")) or not policy.allows_generation(generation)):
        return {"kind": "unavailable"}
    return {"kind": activity(event), "event_id": event["id"], "dependencies": sorted(dependencies(data) - {"current"})}


def project(events, policy):
    return {key: describe(events[key], policy) for key in ("first", "latest")}


def display_lines(goal):
    from .desktop.text import t
    history = goal.get("provenance", {})
    first, latest = history.get("first", {}), history.get("latest", {})
    lines = [t("最初记录：{source}", source=t(LABELS.get(first.get("kind"), LABELS["unrecorded"])))]
    if latest != first:
        lines.append(t("最近修订：{source}", source=t(LABELS.get(latest.get("kind"), LABELS["unrecorded"]))))
    return lines
