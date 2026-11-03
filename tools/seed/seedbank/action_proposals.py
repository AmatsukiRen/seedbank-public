"""Recorded explanations for action proposals, separate from execution facts."""
from copy import deepcopy
import json

from .goal_provenance import ACTIVITIES, LABELS
from .memory_state import dependencies as source_dependencies, is_template, source_file
from .util import now_iso

FORMAT = "seedbank/action-proposal@1"
REASON_LIMIT = 1000


def capture(action, *, source, generation, evidence):
    raw = action.get("reason")
    reason = raw.replace("\x00", "").strip() if isinstance(raw, str) else ""
    return {"format": FORMAT, "at": now_iso(), "reason": reason[:REASON_LIMIT],
            "reason_truncated": len(reason) > REASON_LIMIT, "source": str(source),
            "generation": deepcopy(generation), "evidence": deepcopy(list(evidence))}


def valid(proposal):
    return (isinstance(proposal, dict) and proposal.get("format") == FORMAT
            and isinstance(proposal.get("reason"), str) and len(proposal["reason"]) <= REASON_LIMIT
            and isinstance(proposal.get("reason_truncated"), bool)
            and isinstance(proposal.get("at"), str) and bool(proposal["at"])
            and isinstance(proposal.get("source"), str)
            and isinstance(proposal.get("generation"), dict)
            and isinstance(proposal.get("evidence"), list)
            and all(isinstance(ref, dict) and isinstance(ref.get("id"), str)
                    and isinstance(ref.get("source"), str) for ref in proposal["evidence"]))


def visible(proposal, policy):
    if proposal is None:  # A legacy or directly requested action has no proposal.
        return True
    source = proposal["source"]
    refs = proposal["evidence"]
    return (policy.allows_source(source) and policy.allows_generation(proposal["generation"])
            and len(policy.supports(refs)) == len(refs)
            and ("#" in source or source_file(source) not in policy.affected_sources))


def dependencies(proposal):
    if not proposal:
        return set()
    refs = source_dependencies(proposal) - {"current"}
    parts = proposal["source"].split("#", 1)
    if len(parts) == 2 and parts[1]:
        refs.add(parts[1])
    return refs


def activity(proposal):
    generation = proposal["generation"]
    if is_template(generation) or generation.get("runtime_guard"):
        return "fixed"
    kind = generation.get("proposal_activity")
    return kind if kind in ACTIVITIES else "unrecorded"


def prompt_lines(outcome):
    proposal = outcome.get("proposal")
    if not proposal:
        return []  # Do not spend prompt budget repeating unknown legacy reasons.
    reason = json.dumps(proposal["reason"], ensure_ascii=False)
    return [f"  Reported proposal reason [{activity(proposal)}]: {reason}; "
            f"truncated={str(proposal['reason_truncated']).lower()}. "
            "This is the proposer's explanation, not verified motive or execution evidence."]


def display_lines(outcome):
    from .desktop.text import t
    proposal = outcome.get("proposal")
    if not proposal:
        return [t("当时未记录行动理由。")]
    lines = [t("提出场景：{source}", source=t(LABELS[activity(proposal)]))]
    lines.append(t("提出时的说明：{text}", text=proposal["reason"]) if proposal["reason"] else t("本次未提供行动理由。"))
    if proposal["reason_truncated"]:
        lines.append(t("理由过长，此处保留前 1000 字。"))
    return lines
