"""Read-only archive projections of recorded proposals and runtime outcomes."""
from .action_proposals import activity
from .memory_state import is_template


def project(outcome):
    proposal = outcome.get("proposal")
    if not proposal or not proposal["reason"]:
        return None
    from .development import execution_state, outcome_dependencies
    text = (f"当时提出的说明 [{activity(proposal)}]：{proposal['reason']}\n"
            f"运行器结果：{outcome['action']} / {outcome['status']} / {execution_state(outcome)}；{outcome['detail']}")
    if proposal["reason_truncated"]:
        text += "\n理由过长，原记录只保留前 1000 字。"
    execution, proposed = outcome.get("generation", {}), proposal["generation"]
    scope = execution.get("audience_id", "owner")
    # A derived archive node never expands either source's recipient scope.
    # Unanchored legacy day sources remain private even if mislabeled as shared.
    sources = [outcome.get("source", ""), proposal["source"],
               *(ref.get("source", "") for ref in outcome.get("evidence", []) + proposal["evidence"])]
    if (proposed.get("audience_id", "owner") != scope
            or execution.get("disclosure_version") != 1 or proposed.get("disclosure_version") != 1
            or any("#" not in str(source) for source in sources)):
        scope = "owner"
    return {"id": outcome["id"], "kind": "action_proposal", "origin": "action_archive",
            "source": "mind/development.jsonl#" + outcome["id"],
            "day": outcome["day"], "at": proposal["at"], "text": text,
            "importance": 0.4, "tags": ["行动提议", "执行结果"], "runner": "runtime",
            "depends_on": outcome_dependencies(outcome),
            "metadata": {"runner": "runtime", "audience_id": scope, "disclosure_version": 1},
            "template_generated": is_template(proposed) or bool(proposed.get("runtime_guard"))}


def from_event(event):
    if event["kind"] != "outcome":
        return None
    return project({**event["data"], "id": event["id"], "day": event["day"],
                    "at": event["at"], "source": event["source"]})


def eligible(row, policy):
    """Use current sources, not a cached claim that a proposal was visible."""
    identifier = row.get("id")
    canonical = policy.action_rows.get(identifier)
    if not canonical or any(row.get(key) != value for key, value in canonical.items()):
        return False
    from .development import outcome_visible
    return outcome_visible(policy.action_outcomes[identifier], policy)
