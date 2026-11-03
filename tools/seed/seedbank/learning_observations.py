"""User observations of a particular strategy in a particular artifact.

These are attributed judgments, never proof of adoption, causation or mastery.
The original strategy is not made dependent on its later evaluations.
"""
from __future__ import annotations

import json
import re

from . import experience
from .util import SeedError, canonical_json
from .learning_strategies import digest, latest

FORMAT = "seedbank/learning@3"


def clean(value):
    from .learning import text
    if not isinstance(value, list) or len(value) > 3:
        raise SeedError("每次最多观察三条实际提供的经验。")
    result, seen = [], set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"lesson_id", "fit", "use", "effect", "reason", "quote"}:
            raise SeedError("经验观察需要适用性、体现情况、效果、理由和作品片段。")
        row = {k: text(item.get(k), n, label) for k, n, label in (
            ("lesson_id", 100, "经验编号"), ("reason", 500, "经验观察理由"))}
        for key, options in (("fit", ("applicable", "not_applicable", "uncertain")),
                             ("use", ("observed", "not_observed", "uncertain")),
                             ("effect", ("helpful", "harmful", "no_clear_effect", "uncertain"))):
            if item.get(key) not in options:
                raise SeedError("经验观察的选项无效。")
            row[key] = item[key]
        if not isinstance(item.get("quote"), str) or len(item["quote"].strip()) > 300:
            raise SeedError("作品片段最多 300 字。")
        row["quote"] = text(item["quote"], 300, "作品片段") if item["quote"].strip() else ""
        if row["use"] == "observed" and not row["quote"]:
            raise SeedError("认为作品体现了这条经验时，请摘录一段作品原文。")
        if row["use"] != "observed" and row["effect"] != "uncertain":
            raise SeedError("尚未观察到作品体现这条经验，效果应保持不确定。")
        if row["lesson_id"] in seen:
            raise SeedError("同一次反馈不能重复评价同一条经验。")
        seen.add(row["lesson_id"])
        result.append(row)
    return result


def validate(row):
    data = row["data"]
    observations = clean(data.get("lesson_observations"))
    hashes = data.get("lesson_hashes")
    if (row["kind"] != "feedback" or row["origin"] != "user"
            or observations != data["lesson_observations"] or not isinstance(hashes, dict)
            or set(hashes) != {r["lesson_id"] for r in observations}
            or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                   for v in [data.get("input_hash"), *hashes.values()])
            or not isinstance(data.get("supersedes"), str) or "#" not in row["source"]):
        raise SeedError("经验观察的来源或版本不完整；原文件已保留。")


def strategy_ids(outcome):
    """Receipt references for same-rubric strategies and cross-task lessons.

    Scope is checked by callers: mere availability is not proof of supply.
    Keep the two original receipt fields distinct; do not relabel local reuse
    as cross-task transfer.
    """
    practice = outcome.get("practice", {})
    return set(practice.get("adjustment_ids", [])) | set(practice.get("lesson_ids", []))


def offered(outcome, loaded):
    if outcome.get("practice", {}).get("scope") != "provided_to_creator":
        return {}
    identifiers = strategy_ids(outcome)
    return {r["id"]: r for r in loaded["adjustments"].values() if r["id"] in identifiers}


def check(pack, observations, outcome, loaded):
    from .learning import artifact_state
    candidates = offered(outcome, loaded)
    asset = artifact_state(pack, outcome)
    if observations and (asset["state"] != "unchanged" or outcome.get("status") != "succeeded"):
        raise SeedError("经验观察需要内容未改变的成功创作成果。")
    for observation in observations:
        if observation["lesson_id"] not in candidates:
            raise SeedError("只能观察本次实际提供且当前仍可用的经验。")
        if observation["quote"] and observation["quote"] not in asset.get("text", ""):
            raise SeedError("经验观察的作品片段必须来自这份成果的原文。")
    return {r["lesson_id"]: candidates[r["lesson_id"]] for r in observations}


def valid(pack, row, outcomes, strategies, originals):
    from .learning import artifact_state
    data = row["data"]
    event = originals.get(row["source"].split("#", 1)[-1])
    outcome = outcomes.get(data["outcome_id"], {})
    expected = {k: v for k, v in data.items() if k not in (
        "supersedes", "artifact_snapshot", "generation", "lesson_hashes", "input_hash")}
    expected.update(goal_id=row["goal_id"], expected=data["supersedes"])
    try:
        if (not event or digest(event) != data["input_hash"] or event.get("kind") != "learning_feedback"
                or experience.source_of(event) != row["source"]
                or canonical_json(json.loads(event["text"])) != canonical_json(expected)):
            return False
    except (ValueError, TypeError):
        return False
    observations = data["lesson_observations"]
    if not observations:
        return True
    asset = artifact_state(pack, outcome)
    provided = strategy_ids(outcome)
    return bool(outcome.get("status") == "succeeded" and asset["state"] == "unchanged"
                and data["artifact_snapshot"] == outcome.get("artifact_snapshot")
                and outcome.get("practice", {}).get("scope") == "provided_to_creator"
                and all(r["lesson_id"] in provided and r["lesson_id"] in strategies
                        and digest(strategies[r["lesson_id"]]) == data["lesson_hashes"][r["lesson_id"]]
                        and (not r["quote"] or r["quote"] in asset["text"]) for r in observations))


def suppressed(pack, *, sources=None):
    """Source-only fold: no MemoryPolicy or learning.view recursion."""
    from .memory_sources import PolicySources
    sources = sources if sources is not None else PolicySources(pack)
    rows = sources.learning
    extended = [r for r in rows if r["format"] == FORMAT]
    if not extended:
        return set()
    current = {(r["data"]["criteria_id"], r["data"]["outcome_id"]): r
               for r in rows if r["kind"] == "feedback"}
    standards = {r["goal_id"]: r["id"] for r in rows if r["kind"] == "criteria"}
    strategies = {r["id"]: r for r in latest(rows).values()}
    originals = sources.originals
    outcomes = sources.outcomes
    return {r["source"].split("#", 1)[1] for r in extended
            if current[(r["data"]["criteria_id"], r["data"]["outcome_id"])]["id"] != r["id"]
            or standards.get(r["goal_id"]) != r["data"]["criteria_id"]
            or not valid(pack, r, outcomes, strategies, originals)}


def history(pack, lesson_id, loaded, *, search=None):
    """Only current, scope-filtered feedback; contradictory judgments coexist."""
    from .learning import artifact_state
    result = []
    reviews = {row["id"]: row for row in loaded["feedback"].values()}
    for review in reviews.values():
        if review["format"] != FORMAT:
            continue
        matches = [r for r in review["data"]["lesson_observations"] if r["lesson_id"] == lesson_id]
        outcome = loaded["outcomes"][review["data"]["outcome_id"]]
        if not matches or artifact_state(pack, outcome)["state"] != "unchanged":
            continue
        standard = loaded["criteria"][review["goal_id"]]
        result.append({**matches[0], "feedback_id": review["id"], "outcome_id": outcome["id"],
                       "at": review["at"], "goal_title": standard["data"]["title"],
                       "criteria": standard["data"]["items"], "ratings": review["data"]["ratings"],
                       "task": outcome.get("practice", {}).get("task", {}),
                       "generation": {k: outcome.get("generation", {}).get(k) for k in ("runner", "model", "fallback")},
                       "origin": "user", "evidence": review["evidence"]})
    from .learning_retrieval import observations
    recent = observations(result, search)
    from .learning_choices import for_feedback
    for item in recent:
        choices = for_feedback(pack, reviews[item["feedback_id"]], loaded)
        model_choice = next((r for r in choices["items"] if r["strategy_id"] == lesson_id and r["currently_available"]), None)
        item["model_choice"] = {"origin": "model_statement", **model_choice} if model_choice else {}
    return {"observations": recent, "observation_count": len(result),
            "observation_evidence": list({r["id"]: r for item in recent for r in item["evidence"]}.values())}
