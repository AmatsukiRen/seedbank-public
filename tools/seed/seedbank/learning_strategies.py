"""Revisable practice strategies with explicit limits on cross-task reuse."""
from __future__ import annotations

import re
import unicodedata

from . import experience, requests
from .pack_lock import serialized
from .util import SeedError, canonical_json, sha256

FORMAT = "seedbank/learning@2"


def digest(row):
    return sha256(canonical_json(row))


def transfer(value):
    from .learning import text
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict) or set(value) != {"applies_when", "avoid_when"}:
        raise SeedError("复用经验需要同时说明适用和不适用的情形。")
    return {key: text(value[key], 500, "经验适用范围") for key in ("applies_when", "avoid_when")}


def validate(row):
    data = row["data"]
    if (row["kind"] != "adjustment" or not isinstance(data.get("supersedes"), str)
            or len(data["supersedes"]) > 100 or "transfer" not in data or transfer(data["transfer"]) != data["transfer"]
            or any(not isinstance(data.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}", data[k])
                   for k in ("feedback_hash", "criteria_hash", "input_hash"))
            or "#" not in row["source"]):
        raise SeedError("经验版本的来源或适用范围不完整；原文件已保留。")


def latest(rows):
    return {r["data"]["feedback_id"]: r for r in rows if r["kind"] == "adjustment"}


def _valid(row, reviews, standards, originals):
    data = row["data"]
    review = reviews.get(data["feedback_id"])
    standard = standards.get(row["goal_id"])
    event = originals.get(row["source"].split("#", 1)[-1])
    return bool(review and standard and event and digest(review) == data["feedback_hash"]
                and digest(standard) == data["criteria_hash"] and digest(event) == data["input_hash"]
                and event["text"] == canonical_json({k: v for k, v in data.items() if k != "input_hash"})
                and experience.source_of(event) == row["source"]
                and event.get("kind") == "learning_strategy"
                and event.get("metadata", {}).get("feedback_id") == data["feedback_id"]
                and event.get("metadata", {}).get("origin") == row["origin"])


def suppressed(pack, *, sources=None):
    """Pure ledger/source fold for MemoryPolicy; never calls learning.view."""
    from . import learning
    from .memory_sources import PolicySources
    sources = sources if sources is not None else PolicySources(pack)
    rows = sources.learning
    extended = [r for r in rows if r["format"] == FORMAT]
    if not extended:
        return set()
    standards, reviews = {}, {}
    for row in rows:
        if row["kind"] == "criteria":
            standards[row["goal_id"]] = row
        elif row["kind"] == "feedback":
            reviews[(row["data"]["criteria_id"], row["data"]["outcome_id"])] = row
    reviews = {r["id"]: r for r in reviews.values()
               if standards.get(r["goal_id"], {}).get("id") == r["data"]["criteria_id"]}
    originals = sources.originals
    outcomes = sources.outcomes
    current = latest(rows)
    revised = {r["data"]["feedback_id"] for r in extended}
    retired = set()
    for row in rows:
        if row["kind"] != "adjustment" or row["data"]["feedback_id"] not in revised:
            continue
        obsolete = current[row["data"]["feedback_id"]]["id"] != row["id"]
        if row["format"] == FORMAT:
            review = reviews.get(row["data"]["feedback_id"], {})
            outcome = outcomes.get(review.get("data", {}).get("outcome_id"), {})
            obsolete = (obsolete or not _valid(row, reviews, standards, originals)
                        or learning.artifact_state(pack, outcome)["state"] != "unchanged")
        if obsolete and "#" in row["source"]:
            retired.add(row["source"].split("#", 1)[1])
    return retired


def reusable(pack, standard, loaded, *, task=None):
    from . import learning
    skill = unicodedata.normalize("NFC", standard["data"]["skill"]).casefold()
    result = []
    for row in loaded["adjustments"].values():
        if row["format"] != FORMAT or not row["data"].get("transfer"):
            continue
        previous = loaded["criteria"][row["goal_id"]]
        if (unicodedata.normalize("NFC", previous["data"]["skill"]).casefold() != skill
                or learning.rubric_key(previous) == learning.rubric_key(standard)):
            continue
        review = next((r for r in loaded["feedback"].values() if r["id"] == row["data"]["feedback_id"]), None)
        if not review:
            continue
        outcome = loaded["outcomes"][review["data"]["outcome_id"]]
        if learning.artifact_state(pack, outcome)["state"] != "unchanged":
            continue
        result.append({**row, "source_goal_title": previous["data"]["title"],
                       "source_criteria": previous["data"]["items"],
                       "source_feedback": {k: review["data"][k] for k in ("ratings", "reason", "next_step")},
                       "source_task": outcome.get("practice", {}).get("task", {}),
                       "source_generation": {k: outcome.get("generation", {}).get(k) for k in ("runner", "model", "fallback")}})
    # Search all supported candidates; ledger order only breaks relevance ties.
    order = {r["id"]: i for i, r in enumerate(loaded["rows"])}
    result.sort(key=lambda r: order[r["id"]])
    from .learning_retrieval import query, experiences
    search = query(standard, loaded["state"]["goals"].get(standard["goal_id"], {}), task)
    from .learning_observations import history
    return [{**row, **history(pack, row["id"], loaded, search=search)}
            for row in experiences(result, search)]


def append(pack, review, loaded, *, strategy, expected_result, reuse, origin, day, source, runner, generation=None):
    from . import learning
    previous = latest(loaded["rows"]).get(review["id"])
    data = {"feedback_id": review["id"], "text": strategy, "expected_result": expected_result,
            "transfer": reuse, "supersedes": previous["id"] if previous else "",
            "feedback_hash": digest(review), "criteria_hash": digest(loaded["criteria"][review["goal_id"]])}
    from .disclosure import stamp
    metadata = {**(stamp("owner") if origin == "user" else dict(generation or {})),
                "runner": runner, "feedback_id": review["id"], "origin": origin}
    event = experience.record(pack, kind="learning_strategy", text=canonical_json(data), day=day,
        source=source, actor="user" if origin == "user" else "model",
        depends_on=[r["id"] for r in review["evidence"]], metadata=metadata)
    refs = [{"id": event["id"], "source": experience.source_of(event), "kind": event["kind"]}, *review["evidence"]]
    return learning._append(pack, "adjustment", review["goal_id"], {**data, "input_hash": digest(event)},
                            evidence=refs, source=experience.source_of(event), origin=origin)


@serialized
def perform(pack, payload, *, request_id=""):
    from . import learning
    if not isinstance(payload, dict):
        raise SeedError("经验修改需要 data 对象。")
    data = {k: learning.text(payload.get(k), limit, label) for k, limit, label in (
        ("goal_id", 100, "目标编号"), ("feedback_id", 100, "反馈编号"),
        ("text", 500, "下一次尝试的策略"), ("expected_result", 500, "如何观察这次改动"))}
    if not isinstance(payload.get("expected"), str) or len(payload["expected"]) > 100:
        raise SeedError("经验版本已改变，请刷新后重新整理。")
    data.update(expected=payload["expected"], transfer=transfer(payload.get("transfer")))

    def current():
        loaded = learning.view(pack)
        review = next((r for r in loaded["feedback"].values() if r["id"] == data["feedback_id"]
                       and r["goal_id"] == data["goal_id"]), None)
        previous = latest(loaded["rows"]).get(data["feedback_id"], {})
        if not review or previous.get("id", "") != data["expected"]:
            raise SeedError("反馈或经验版本已改变，请刷新后重新整理。")
        outcome = loaded["outcomes"][review["data"]["outcome_id"]]
        if learning.artifact_state(pack, outcome)["state"] != "unchanged":
            raise SeedError("经验所依据的成果已改变或不可用，请先重新核对。")
        return loaded, review

    def apply():
        from .cognition import _latest_day
        loaded, review = current()
        return {"record": append(pack, review, loaded, strategy=data["text"], expected_result=data["expected_result"],
            reuse=data["transfer"], origin="user", day=_latest_day(pack)["day"], source="mind/experiences.jsonl", runner="user-learning-strategy-v1")}

    return requests.run(pack, {"kind": "learning_edit", "action": "strategy", "data": data}, apply,
                        request_id=request_id, validate=current)
