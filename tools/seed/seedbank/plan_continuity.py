"""Explicit responses to earlier daily intentions, without carrying over success."""
from .util import SeedError, canonical_json, list_days

FORMAT = "seedbank/plan-continuity@1"
RELATIONS = ("continue", "revise", "release")


def valid_binding(value):
    return (isinstance(value, dict)
            and set(value) == {"format", "plan_id", "entry_sha256", "day", "relation"}
            and value.get("format") == FORMAT and isinstance(value.get("plan_id"), str)
            and value["plan_id"].startswith("p_") and type(value.get("day")) is int and value["day"] > 0
            and value.get("relation") in RELATIONS and isinstance(value.get("entry_sha256"), str)
            and len(value["entry_sha256"]) == 64 and all(c in "0123456789abcdef" for c in value["entry_sha256"]))


def matches(binding, parent, child):
    from .plan_links import _digest
    linked = (valid_binding(binding) and parent is not None
            and parent["kind"] != "legacy" and parent["id"] == binding["plan_id"]
            and parent["plan"].get("origin") == "model" and parent["plan"].get("mode") == "focus"
            and parent["plan"]["day"] == binding["day"] < child["day"]
            and _digest(parent) == binding["entry_sha256"])
    if not linked:
        return False
    if binding["relation"] == "release":
        return child.get("mode") in ("rest", "open") or (child.get("mode") == "focus" and child.get("goal_id") != parent["plan"].get("goal_id"))
    return (child.get("mode") == "focus" and child.get("goal_id") == parent["plan"].get("goal_id")
            and (binding["relation"] == "revise" or child.get("goal_event_id") == parent["plan"].get("goal_event_id")))


def _eligible(pack, *, entries, day, policy):
    from . import planning, plan_links
    heads = planning._heads(entries)
    current = heads.get(day, {})
    # A recorded response is not undone when its explanation is later hidden.
    # In particular, forgetting a release must not silently reactivate an intent.
    responded = {}
    focus_by_day = {}
    for entry in entries:
        if entry["kind"] == "legacy":
            continue
        if entry["plan"].get("origin") == "model" and entry["plan"].get("mode") == "focus":
            # Rest/open changes today's schedule, not the existence of a prior
            # intention. Keep the final focus version of each day for review.
            focus_by_day[entry["plan"]["day"]] = entry
        binding = entry["plan"].get("continuity")
        if binding and entry["plan"]["day"] <= day:
            responded[binding["plan_id"]] = entry["id"]
    selected = []
    for entry in focus_by_day.values():
        plan = entry["plan"]
        response = responded.get(entry["id"], "")
        parent = plan.get("continuity", {}).get("plan_id")
        if (plan["day"] >= day or (response and response != current.get("id"))
                or (parent and responded.get(parent) != entry["id"])
                or not plan_links._visible(pack, entry, policy)):
            continue
        # Reoffer the parent of today's current response so it can be revised
        # explicitly, and repeated identical responses remain idempotent.
        if response and not plan_links._visible(pack, current, policy):
            continue
        selected.append((entry, response))
    return sorted(selected, key=lambda item: (bool(item[1]), item[0]["plan"]["day"]))


def needs_choice(pack, *, day, policy):
    return bool(pending_evidence(pack, day=day, policy=policy))


def pending_evidence(pack, *, day, policy):
    from .plan_links import _entries
    eligible = _eligible(pack, entries=_entries(pack), day=day, policy=policy)
    return eligible[-1][0]["plan"]["evidence"] if eligible else []


def candidates(pack, *, state, policy, day=None, limit=6):
    if getattr(policy, "audience_id", "owner") != "owner":
        return []
    if day is None:
        days = list_days(pack)
        day = days[-1]["day"] if days else 1
    from . import plan_links
    entries = plan_links._entries(pack)
    selected = _eligible(pack, entries=entries, day=day, policy=policy)[-limit:]
    responses = {entry["id"]: response for entry, response in selected}
    rows = plan_links.review(pack, selected=[entry for entry, _ in selected], state=state, policy=policy, entries=entries)
    by_id = {entry["id"]: entry for entry in entries}
    for row in rows:
        goal = state["goals"].get(row["goal_id"], {})
        row["responded_by"] = responses[row["plan_id"]]
        if row["responded_by"]:
            response = by_id[row["responded_by"]]["plan"]
            row["dependencies"] = sorted(set(row["dependencies"])
                | set(response.get("generation", {}).get("context_dependencies", []))
                | {ref["id"] for ref in response.get("evidence", []) if ref["id"] != "current"})
        row["goal_status"] = goal.get("status", "unavailable")
        row["goal_changed"] = goal.get("event_id") != row["goal_event_id"]
    return rows


def bind(raw, *, mode, goal_id, goal, ctx, eligible, policy):
    if raw is None:
        return None, [], []
    if (not isinstance(raw, dict) or set(raw) != {"plan_id", "relation"}
            or not isinstance(raw.get("plan_id"), str) or raw.get("relation") not in RELATIONS):
        raise SeedError("跨日选择需要一个已提供的旧计划编号，以及 continue、revise 或 release。")
    shown = next((row for row in ctx.get("development", {}).get("prior_choices", [])
                  if row.get("plan_id") == raw["plan_id"]), None)
    found = next(((entry, response) for entry, response in eligible if entry["id"] == raw["plan_id"]), None)
    from .plan_links import _digest
    if (not shown or not found or shown.get("entry_sha256") != _digest(found[0])
            or shown.get("responded_by", "") != found[1]
            or not policy.allows_generation({"context_dependencies": shown.get("dependencies", [])})):
        raise SeedError("只能回应本次实际提供、来源有效且尚可回应的先前选择。")
    parent = found[0]
    previous = parent["plan"]
    relation = raw["relation"]
    if relation in ("continue", "revise"):
        if mode != "focus" or goal_id != previous["goal_id"]:
            raise SeedError("继续或调整旧打算，需要专注同一个仍有效的目标；转向别的目标请明确放下旧打算。")
        if relation == "continue" and goal["event_id"] != previous.get("goal_event_id"):
            raise SeedError("原目标版本已变化，请重新考虑后明确调整，不能原样接续。")
    elif mode == "focus" and goal_id == previous["goal_id"]:
        raise SeedError("放下旧打算时不能同时选择继续专注同一目标；可以休息、留白或选择其他目标。")
    binding = {"format": FORMAT, "plan_id": parent["id"], "entry_sha256": _digest(parent),
               "day": previous["day"], "relation": relation}
    return binding, previous.get("evidence", []), shown.get("dependencies", [])


def prompt_lines(rows):
    if not rows:
        return ""
    visible = [{k: v for k, v in row.items() if k != "dependencies"} for row in rows]
    return ("\n先前的选择（prior_choices；按日页保留的明确专注意图）：\n" + canonical_json(visible)
            + "\n这些是值得重新考虑的旧打算，不自动认定尚未完成、失败或今天仍愿意做。"
              "responded_by 非空表示今天当前安排已经回应它，可以明确修改该回应；空值表示尚无后续回应记录。"
              "如需接续，在 daily_plan.continuity 中明确选择 continue、revise 或 release 并写简短理由；"
              "没有回应不等于放下。不补造离线经历，旧成果不转移成新计划的成果。")


def link_line(binding):
    from .i18n import t
    relation = {"continue": "继续先前的打算", "revise": "调整先前的打算", "release": "放下先前的打算"}
    return t("{relation} · 第 {day} 天", relation=t(relation[binding["relation"]]), day=binding["day"])


def display_lines(rows):
    from .i18n import t
    from .plan_links import display_lines as review_lines
    result = []
    for row in reversed(rows):
        heading = t("今天已回应，可重新考虑" if row["responded_by"] else "尚未记录后续选择")
        body = review_lines([row])[0]
        if row.get("goal_changed"):
            body += "\n" + t("原目标已变化，接续前需要重新考虑。")
        result.append(heading + "\n" + body)
    return result
