"""Read-only goal versions: past intentions are not current instructions."""
from .memory_state import dependencies, source_file
from .goal_provenance import activity as _activity


def project(event):
    if event["kind"] != "goal":
        return None
    from .goal_provenance import LABELS
    data = event["data"]
    reason = data.get("reason") or "当时未记录理由"
    text = (f"过去记录的目标版本：{data['title']}\n"
            f"当时状态：{data['status']}；当时下一步：{data.get('next_step', '')}\n"
            f"当时提出或修订的理由：{reason}\n"
            f"形成场景：{LABELS[_activity(event)]}。这份记录不能证明现在仍想这样做或已实际完成。")
    refs = dependencies(data) - {"current"}
    parts = str(event.get("source", "")).split("#", 1)
    if len(parts) == 2 and parts[1]:
        refs.add(parts[1])
    link = data.get("project")
    project_event = link.get("event_id") if isinstance(link, dict) else None
    if project_event:
        refs.add(project_event)
    return {"id": event["id"], "kind": "goal_history", "origin": "goal_archive",
            "source": "mind/development.jsonl#" + event["id"], "day": event["day"], "at": event["at"],
            "text": text, "goal_id": data["id"], "importance": .5, "tags": ["目标历史"],
            "depends_on": sorted(refs), "template_generated": _activity(event) == "fixed",
            # Private intentions do not become public because one input was shared.
            "metadata": {"runner": "runtime", "audience_id": "owner", "disclosure_version": 1}}


def visible(event, policy):
    if getattr(policy, "audience_id", "owner") != "owner":
        return False
    data, source = event["data"], event.get("source", "")
    refs = data.get("evidence", [])
    if (event["id"] in policy.blocked or not refs or len(policy.supports(refs)) != len(refs)
            or not policy.allows_source(source) or not policy.allows_generation(data.get("generation"))
            or ("#" not in source and source_file(source) in policy.affected_sources)):
        return False
    if "project" in data:
        from .goal_projects import valid_link
        return valid_link(data, policy._goal_project_events, policy)
    return True


def eligible(row, policy):
    identifier = row.get("id")
    canonical = policy.goal_rows.get(identifier)
    return bool(canonical and all(row.get(key) == value for key, value in canonical.items())
                and visible(policy.goal_events[identifier], policy))


def annotate(row, policy):
    # Reconstruct from the canonical event; cached annotations cannot claim
    # that an old goal is active or disclose a withdrawn newer version.
    result = dict(policy.goal_rows[row["id"]])
    latest = policy.goal_heads.get(result["goal_id"])
    note = {"current_available": False, "dependency_ids": []}
    if latest and visible(latest, policy):
        data = latest["data"]
        note = {"current_available": True, "is_latest": latest["id"] == row["id"],
                "event_id": latest["id"], "status": data["status"], "reason": data.get("reason", ""),
                "day": latest["day"], "at": latest["at"],
                "activity": _activity(latest), "dependency_ids": [latest["id"]]}
    return {**result, "goal_version": note}


def context_dependencies(ctx):
    rows = list(ctx.get("evidence", [])) + [item["memory"] for item in ctx.get("recalled", [])]
    return {ref for row in rows for ref in row.get("goal_version", {}).get("dependency_ids", [])}
