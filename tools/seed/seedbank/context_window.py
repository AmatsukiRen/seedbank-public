"""Bounded prompt assembly without deleting source material.

UTF-8 byte count is a conservative proxy for byte-tokenized models, not a
provider's tokenizer. The configurable budget is for input, excluding output.
Whole records are removed; the current user request and runtime rules remain.
"""
from __future__ import annotations

from copy import deepcopy


class ContextBudgetError(ValueError):
    pass


def _trim_transcript(rows, count):
    # A long series of our own replies must not erase the speaker's input
    # those replies were about. Even the newest model reply has lower priority
    # than original speech: a long last answer must not evict its own source.
    # Within each role retain the most recent rows. Keep annotations intact.
    replies = [index for index, row in enumerate(rows)
               if row.get("who") == "fish" and not row.get("person_id")]
    removed = set(replies[:len(rows) - count])
    for index in range(len(rows)):
        if len(rows) - len(removed) <= count:
            break
        removed.add(index)
    return [row for index, row in enumerate(rows) if index not in removed]


def _trim_practice(rows, key):
    count = len(rows) // 2
    if key == "lessons":
        return rows[:count]
    if all(isinstance(row.get("retrieval", {}).get("rank"), int) for row in rows):
        # Selection is displayed in ledger order. Retain the latest feedback
        # for this goal, then task relevance; age alone must not undo retrieval.
        priority = sorted(range(len(rows)), key=lambda index: (
            not rows[index]["retrieval"].get("current_goal_latest", False),
            rows[index]["retrieval"]["rank"]))
        kept = set(priority[:count])
        return [row for index, row in enumerate(rows) if index in kept]
    return rows[max(1, len(rows) // 2):]


def fit(ctx, builder):
    selected = {**ctx, "development": deepcopy(ctx.get("development", {})),
                "facts": deepcopy(ctx.get("facts", {})), "practice": deepcopy(ctx.get("practice", {})),
                "relationships": deepcopy(ctx.get("relationships", {})), "life_story": deepcopy(ctx.get("life_story", {})),
                "inner": deepcopy(ctx.get("inner", {}))}
    configured = (ctx.get("_cfg") or {}).get("input_budget", 16000)
    try:
        budget = max(2048, min(int(configured), 1000000)) - 512
    except (TypeError, ValueError):
        budget = 15488
    removed = False

    def render():
        selected["context_limited"] = removed
        prompt = builder(selected)
        size = sum(len(str(value).encode("utf-8")) for value in prompt.values())
        return prompt, size

    prompt, size = render()
    if size <= budget:
        return prompt, selected, {"input_bytes": size, "budget": budget, "limited": False}
    # Compact instructions before discarding experiences. This preserves all
    # proposal capabilities and original source data at the default budget.
    selected["_compact_protocol"] = True
    prompt, size = render()
    if size <= budget:
        return prompt, selected, {"input_bytes": size, "budget": budget, "limited": False}
    # Optional legacy prose has the weakest provenance. Current structured
    # state and recent turns take precedence over this accumulated text.
    for key in ("beliefs", "selfMd", "recentDays", "news", "senses", "works", "friends"):
        selected[key] = [] if isinstance(selected.get(key), list) else {} if isinstance(selected.get(key), dict) else ""
        removed = True
        prompt, size = render()
        if size <= budget:
            return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    # Remove whole inner entries with their source/revision notes, retaining
    # the explicit silence choice. Never count removed text as supplied.
    for key in ("last_dreams", "recent_corrections", "narrative"):
        selected["inner"][key] = {} if key == "narrative" else []
        prompt, size = render()
        if size <= budget:
            return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    for key in ("transcript", "evidence", "recalled", "learning", "disclosed"):
        # Keep recent conversation and a few relevant sources while pruning
        # other categories. Emptying the transcript first made ordinary
        # follow-up questions forget the input even with redundant recall
        # and optional summaries still occupying the prompt.
        minimum = {"transcript": 8, "evidence": 2, "recalled": 3,
                   "learning": 0 if selected.get("practice") else 1, "disclosed": 1}[key]
        while len(selected.get(key) or []) > minimum:
            rows = selected[key]
            count = max(minimum, len(rows) // 2)
            selected[key] = _trim_transcript(rows, count) if key == "transcript" else rows[:count]
            prompt, size = render()
            if size <= budget:
                return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    for key in ("previous_versions", "chapters"):
        while selected.get("life_story", {}).get(key):
            selected["life_story"][key] = selected["life_story"][key][:-1]
            selected["life_story"]["omitted"] = True
            prompt, size = render()
            if size <= budget:
                return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    for key in ("notes", "issues", "agreements"):
        while selected.get("relationships", {}).get(key):
            rows = selected["relationships"][key]
            selected["relationships"][key] = rows[max(1, len(rows) // 2):]
            selected["relationships"]["context_limited"] = True
            prompt, size = render()
            if size <= budget:
                return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    for key in ("plan_review", "prior_choices", "beliefs", "preferences", "outcomes", "goals"):
        while selected.get("development", {}).get(key):
            rows = selected["development"][key]
            selected["development"][key] = rows[max(1, len(rows) // 2):]
            prompt, size = render()
            if size <= budget:
                return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    for key in ("lessons", "feedback", "adjustments"):
        while selected.get("practice", {}).get(key):
            rows = selected["practice"][key]
            selected["practice"][key] = _trim_practice(rows, key)
            if key == "feedback":
                kept = {row.get("id") for row in selected["practice"][key]}
                removed_feedback = {row.get("id") for row in rows if row.get("id")} - kept
                # Do not leave a strategy whose feedback was just omitted and
                # then claim its basis was supplied to this generation.
                selected["practice"]["adjustments"] = [row for row in selected["practice"].get("adjustments", [])
                    if row.get("data", {}).get("feedback_id") not in removed_feedback]
            selected["practice"]["context_limited"] = True
            prompt, size = render()
            if size <= budget:
                return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    while selected.get("facts", {}).get("groups"):
        rows = selected["facts"]["groups"]
        selected["facts"]["groups"] = rows[:len(rows) // 2]
        selected["facts"]["omitted"] = True
        subjects = {"owner", "self"} | {g["subject"] for g in selected["facts"]["groups"]}
        selected["facts"]["entities"] = [r for r in selected["facts"].get("entities", []) if r["id"] in subjects]
        prompt, size = render()
        if size <= budget:
            return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    # Last resort for a small budget/large current input: remove whole sources,
    # not partial quotes stripped of their provenance or correction notes.
    # Recent raw dialogue outlives duplicated evidence/recall summaries.
    for key in ("evidence", "recalled", "learning", "disclosed", "transcript"):
        while selected.get(key):
            selected[key] = _trim_transcript(selected[key], len(selected[key]) - 1) if key == "transcript" else selected[key][:-1]
            prompt, size = render()
            if size <= budget:
                return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    # The optional new-goal protocol must not make an otherwise viable minimal
    # conversation fail. Existing stages and their runtime constraints persist.
    selected["goal_project_protocol"] = False
    prompt, size = render()
    if size <= budget:
        return prompt, selected, {"input_bytes": size, "budget": budget, "limited": True}
    raise ContextBudgetError("当前输入与必要身份信息超过上下文预算；请缩短消息或调整 input_budget。原始经历未删除。")
