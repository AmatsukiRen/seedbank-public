"""Retire earlier model interpretations after an explicit factual correction.

Keep the reported inputs and other facets. A later real-world change is not a
correction of the past. Event append order, not wall-clock time, sets the cutoff.
"""
from . import experience


def input_matches(decision, ref, originals):
    event = originals.get(ref["id"])
    return bool(event and event.get("kind") == "fact_input"
                and event.get("metadata", {}).get("action") == "resolve"
                and ref["source"] == experience.source_of(event)
                and event["text"] == decision["reason"])


def suppressed(rows, events):
    claims = {row["id"]: row for row in rows if row["kind"] == "claim"}
    originals = {row["id"]: row for row in events}
    cutoffs, unknown, retired = {}, set(), set()
    for row in rows:
        if row["kind"] != "resolve" or row["change_type"] != "correction":
            continue
        rejected = [claims[key] for key in row["targets"] if key != row["selected"]]
        roots = {r["id"] for r in rejected} | {ref["id"] for r in rejected for ref in r["evidence"]}
        for ref in row["evidence"]:
            if input_matches(row, ref, originals):
                cutoffs.setdefault(ref["id"], set()).update(roots)
            else:
                # The position or content of the decision is unavailable. Do
                # not resurrect rejected values or silently trust the new one.
                unknown.update(roots)
                retired.add(ref["id"])
    active = set(unknown)
    for event in reversed(events):
        active.update(cutoffs.get(event["id"], ()))
        metadata = event.get("metadata", {})
        if ("context_dependencies" in metadata
                and (set(metadata["context_dependencies"]) | set(event.get("depends_on", []))) & active):
            retired.add(event["id"])
    return retired
