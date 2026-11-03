"""Local task relevance for candidate experiences, never a mastery score.

Only already-visible, currently supported records enter this module. Matching
an exclusion is a reason to surface a caution, not to recommend its use.
"""
from collections import Counter
import math
import re
import unicodedata

METHOD = "task-terms-v1"
STOP = {"the", "and", "for", "with", "this", "that", "from", "when", "into",
        "什么", "怎么", "如何", "这个", "那个", "我们", "可以", "需要", "时候"}


def terms(value):
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    result = set()
    for part in re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3]+|[^\W_]+", value):
        if re.fullmatch(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3]+", part):
            result.update(part[i:i + size] for size in (2, 3) for i in range(len(part) - size + 1))
        elif len(part) > 1:
            result.add(part)
    return result - STOP


def query(standard, goal, task=None):
    task = task or {}
    return {"task": str(task.get("topic", "")),
            "goal": "\n".join([standard["data"]["title"], str(goal.get("next_step", "")),
                                *[item["text"] for item in standard["data"]["items"]]])}


def rank(documents, search):
    """Return indexes and explanations; duplicate words do not add weight."""
    search = search or {}
    task_terms, goal_terms = terms(search.get("task", "")), terms(search.get("goal", ""))
    wanted = task_terms | goal_terms
    fields = [{key: terms(value) for key, value in doc.items()} for doc in documents]
    flattened = [set().union(*doc.values()) if doc else set() for doc in fields]
    frequency = Counter(word for words in flattened for word in words & wanted)
    weights = {word: (4 if word in task_terms else 1) * (1 + math.log((len(fields) + 1) / (frequency[word] + 1)))
               for word in wanted}
    reports = []
    for index, words in enumerate(flattened):
        matched = words & wanted
        score = sum(weights[word] for word in sorted(matched))
        reports.append({"method": METHOD,
                        "basis": "task_match" if matched & task_terms else "goal_match" if matched else "recent_fallback",
                        "matched_terms": sorted(matched, key=lambda word: (-weights[word], word))[:8],
                        "matched_fields": [key for key, values in fields[index].items() if values & wanted],
                        "_score": score})
    order = sorted(range(len(fields)), key=lambda index: (reports[index]["_score"], index), reverse=True)
    for position, index in enumerate(order):
        reports[index].pop("_score")
        reports[index]["rank"] = position + 1
    return order, reports


def experiences(rows, search, limit=3):
    documents = [{"strategy": row["data"]["text"],
                  "applies_when": row["data"]["transfer"]["applies_when"],
                  "avoid_when": row["data"]["transfer"]["avoid_when"],
                  "source_task": row.get("source_task", {}).get("topic", ""),
                  "source_goal": row["source_goal_title"],
                  "source_criteria": "\n".join(item["text"] for item in row["source_criteria"])} for row in rows]
    order, reports = rank(documents, search)
    return [{**rows[index], "retrieval": reports[index]} for index in order[:limit]]


def feedback(rows, search, *, goal_id, outcomes, adjustments, limit=4):
    """Select supported same-rubric feedback without losing the current review.

    Inputs have already passed visibility, revision and artifact checks. Rank
    only those inputs; matching must never recover an obsolete ledger record.
    Keep ledger order for display and attach read-only retrieval explanations.
    """
    if not rows or limit <= 0:
        return []
    documents = []
    for row in rows:
        outcome = outcomes[row["data"]["outcome_id"]]
        adjustment = adjustments.get(row["id"], {}).get("data", {})
        documents.append({
            "source_task": outcome.get("practice", {}).get("task", {}).get("topic", ""),
            "reason": row["data"]["reason"], "next_step": row["data"]["next_step"],
            "strategy": adjustment.get("text", ""),
            **adjustment.get("transfer", {}),
        })
    order, reports = rank(documents, search)
    current = next((index for index in reversed(range(len(rows))) if rows[index]["goal_id"] == goal_id), None)
    chosen = [current] if current is not None else []
    chosen += [index for index in order if index not in chosen][:max(0, limit - len(chosen))]
    return [{**rows[index], "retrieval": {**reports[index], "current_goal_latest": index == current}}
            for index in sorted(chosen)]


def observations(rows, search, limit=3):
    documents = [{"task": row.get("task", {}).get("topic", ""), "goal": row["goal_title"],
                  "criteria": "\n".join(item["text"] for item in row["criteria"]),
                  "reason": row["reason"]} for row in rows]
    order, reports = rank(documents, search)
    chosen = order[:1]
    # Preserve the most relevant caution and positive observation separately.
    # Votes do not cancel each other out, and repetition is not a success rate.
    for predicate in (lambda row: row["fit"] == "not_applicable" or row["effect"] == "harmful",
                      lambda row: row["fit"] == "applicable" and row["use"] == "observed" and row["effect"] == "helpful"):
        candidate = next((index for index in order if predicate(rows[index])), None)
        if candidate is not None and candidate not in chosen and len(chosen) < limit:
            chosen.append(candidate)
    chosen += [index for index in order if index not in chosen][:max(0, limit - len(chosen))]
    # Display observations in ledger order so differing judgments keep context.
    return [{**rows[index], "retrieval": reports[index]} for index in sorted(chosen)]
