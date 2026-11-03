"""Read-only belief/preference versions, never current facts or fixed identity."""
from .goal_provenance import LABELS, activity
from .memory_state import dependencies, source_file

KINDS = ("belief", "preference")
LABEL = {"belief": "看法", "preference": "偏好"}


def statement(event):
    data = event["data"]
    if event["kind"] == "belief":
        return f"{data['text']}；当时自评把握 {data['confidence']}（不是校准概率）"
    stance = {"like": "倾向喜欢", "avoid": "倾向回避", "unsure": "尚不确定"}.get(data["stance"], str(data["stance"]))
    return f"{data['topic']}；当时记录的态度 {stance}"


def project(event):
    if event["kind"] not in KINDS:
        return None
    kind, data = event["kind"], event["data"]
    reason = data.get("reason") or "当时未记录理由"
    text = (f"过去记录的{LABEL[kind]}版本：{statement(event)}\n"
            f"当时形成或修订的理由：{reason}\n"
            f"形成场景：{LABELS[activity(event)]}。这是当时表达的理解，不是外部事实、固定身份或当前态度的证明。")
    refs = dependencies(data) - {"current"}
    source = str(event.get("source", "")).split("#", 1)
    if len(source) == 2 and source[1]:
        refs.add(source[1])
    return {"id": event["id"], "kind": kind + "_history", "origin": "judgment_archive",
            "source": "mind/development.jsonl#" + event["id"], "day": event["day"], "at": event["at"],
            "text": text, "judgment_kind": kind, "judgment_id": data["id"],
            "importance": .5, "tags": [LABEL[kind] + "历史"], "depends_on": sorted(refs),
            "template_generated": activity(event) == "fixed",
            "metadata": {"runner": "runtime", "audience_id": "owner", "disclosure_version": 1}}


def visible(event, policy):
    if getattr(policy, "audience_id", "owner") != "owner":
        return False
    data, source = event["data"], event.get("source", "")
    refs = data.get("evidence", [])
    return bool(event["id"] not in policy.blocked and refs and len(policy.supports(refs)) == len(refs)
                and policy.allows_source(source) and policy.allows_generation(data.get("generation"))
                and ("#" in source or source_file(source) not in policy.affected_sources))


def eligible(row, policy):
    identifier = row.get("id")
    canonical = policy.judgment_rows.get(identifier)
    return bool(canonical and all(row.get(key) == value for key, value in canonical.items())
                and visible(policy.judgment_events[identifier], policy))


def annotate(row, policy):
    # Reconstruct from source; neither cached latest notes nor an older visible
    # version may fill in for an unavailable newest judgment.
    result = dict(policy.judgment_rows[row["id"]])
    latest = policy.judgment_heads.get((result["judgment_kind"], result["judgment_id"]))
    note = {"current_available": False, "dependency_ids": []}
    if latest and visible(latest, policy):
        note = {"current_available": True, "is_latest": latest["id"] == row["id"],
                "event_id": latest["id"], "kind": latest["kind"], "statement": statement(latest),
                "reason": latest["data"].get("reason", ""), "day": latest["day"], "at": latest["at"],
                "activity": activity(latest), "dependency_ids": [latest["id"]]}
    return {**result, "judgment_version": note}


def context_dependencies(ctx):
    rows = list(ctx.get("evidence", [])) + [item["memory"] for item in ctx.get("recalled", [])]
    return {ref for row in rows for ref in row.get("judgment_version", {}).get("dependency_ids", [])}
