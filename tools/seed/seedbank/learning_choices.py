"""Attributed strategy choices returned with a work, never proof of internal use."""
from collections import Counter

from .util import canonical_json, sha256

FORMAT = "seedbank/strategy-choices@1"
MAX_CHOICES = 12
CHOICES = ("adopt", "adapt", "skip", "uncertain")


def strategy_hash(row):
    # Projections add observation history; bind the actual strategy version only.
    return sha256(canonical_json({key: row.get(key) for key in
        ("format", "id", "at", "kind", "goal_id", "source", "origin", "evidence", "data")}))


def candidates(practice):
    rows = practice.get("adjustments", []) + practice.get("lessons", [])
    return {row["id"]: row for row in rows if row.get("kind") == "adjustment" and row.get("id")}


def _text(value, *, required=True):
    return (isinstance(value, str) and len(value) <= 300 and (bool(value.strip()) or not required)
            and not any(ord(c) < 32 and c not in "\n\r\t" for c in value))


def collect(raw, practice, generation):
    available = candidates(practice)
    report = {"format": FORMAT, "origin": "model_statement", "state": "not_reported",
              "candidate_ids": sorted(available), "items": [], "unreported_ids": sorted(available), "rejected_count": 0}
    if (generation.get("fallback") or generation.get("runtime_guard") or not generation.get("model")
            or generation.get("runner") in (None, "", "runtime") or str(generation.get("runner")).startswith("stub")):
        report["state"] = "no_model_report"
        return report
    if raw is None:
        return report
    if not isinstance(raw, list) or len(raw) > MAX_CHOICES:
        report.update(state="invalid_report", rejected_count=len(raw) if isinstance(raw, list) else 1)
        return report
    counts = Counter(item.get("strategy_id") for item in raw if isinstance(item, dict) and isinstance(item.get("strategy_id"), str))
    for item in raw:
        if (not isinstance(item, dict) or set(item) != {"strategy_id", "choice", "reason", "application"}
                or not isinstance(item["strategy_id"], str) or item["strategy_id"] not in available
                or counts[item["strategy_id"]] != 1 or item["choice"] not in CHOICES
                or not _text(item["reason"]) or not _text(item["application"], required=item["choice"] in ("adopt", "adapt"))
                or (item["choice"] in ("skip", "uncertain") and item["application"].strip())):
            report["rejected_count"] += 1
            continue
        report["items"].append({"strategy_id": item["strategy_id"], "choice": item["choice"],
                                "reason": item["reason"].strip(), "application": item["application"].strip(),
                                "strategy_hash": strategy_hash(available[item["strategy_id"]])})
    reported = {item["strategy_id"] for item in report["items"]}
    report["unreported_ids"] = sorted(set(available) - reported)
    report["state"] = ("partial" if report["rejected_count"] else "recorded") if reported else (
        "invalid_report" if report["rejected_count"] else "not_reported")
    return report


def _valid(report):
    if (not isinstance(report, dict) or report.get("format") != FORMAT or report.get("origin") != "model_statement"
            or report.get("state") not in ("not_reported", "no_model_report", "invalid_report", "recorded", "partial")
            or type(report.get("rejected_count")) is not int or report["rejected_count"] < 0
            or not isinstance(report.get("items"), list) or len(report["items"]) > MAX_CHOICES):
        return False
    for key in ("candidate_ids", "unreported_ids"):
        if (not isinstance(report.get(key), list) or any(not isinstance(value, str) or not value for value in report[key])
                or report[key] != sorted(set(report[key]))):
            return False
    identifiers = []
    for item in report["items"]:
        if (not isinstance(item, dict) or not isinstance(item.get("strategy_id"), str)
                or item["strategy_id"] not in report["candidate_ids"] or item.get("choice") not in CHOICES
                or not _text(item.get("reason")) or not _text(item.get("application"), required=item["choice"] in ("adopt", "adapt"))
                or (item["choice"] in ("skip", "uncertain") and item["application"].strip())
                or not isinstance(item.get("strategy_hash"), str) or len(item["strategy_hash"]) != 64):
            return False
        identifiers.append(item["strategy_id"])
    return (len(identifiers) == len(set(identifiers))
            and report["unreported_ids"] == sorted(set(report["candidate_ids"]) - set(identifiers))
            and bool(identifiers) == (report["state"] in ("recorded", "partial")))


def projection(pack, outcome, loaded):
    """Only display or reuse statements tied to their original work and source."""
    from . import experience, learning
    report = outcome.get("practice", {}).get("strategy_choices")
    empty = {"state": "not_recorded", "origin": "model_statement", "items": [], "unreported_ids": [], "rejected_count": 0}
    if report is None:
        return empty
    if not _valid(report) or outcome.get("practice", {}).get("scope") != "provided_to_creator":
        return {**empty, "state": "invalid_source"}
    original = loaded["originals"].get(outcome.get("source", "").split("#", 1)[-1], {})
    asset = learning.artifact_state(pack, outcome)
    offered = set(outcome["practice"].get("adjustment_ids", [])) | set(outcome["practice"].get("lesson_ids", []))
    generation = outcome.get("generation", {})
    if (original.get("kind") != "creation" or experience.source_of(original) != outcome.get("source")
            or original.get("metadata", {}).get("strategy_choices") != report
            or set(report["candidate_ids"]) != offered
            or any(original.get("metadata", {}).get(key) != generation.get(key) for key in ("runner", "model", "fallback"))):
        return {**empty, "state": "invalid_source"}
    if asset["state"] != "unchanged":
        return {**empty, "state": "artifact_unavailable"}
    if original["text"] != asset["title"] + "\n" + asset["text"]:
        return {**empty, "state": "invalid_source"}
    rows = {row["id"]: row for row in loaded["rows"] if row["kind"] == "adjustment"}
    usable = {row["id"] for row in loaded["adjustments"].values()}
    items = []
    for item in report["items"]:
        row = rows.get(item["strategy_id"])
        if not row or strategy_hash(row) != item["strategy_hash"]:
            return {**empty, "state": "invalid_source"}
        items.append({**item, "strategy": row["data"]["text"], "currently_available": row["id"] in usable})
    return {**report, "items": items}


def for_feedback(pack, review, loaded):
    outcome = loaded["outcomes"][review["data"]["outcome_id"]]
    return {"outcome_id": outcome["id"], "task": outcome.get("practice", {}).get("task", {}),
            **projection(pack, outcome, loaded)}
