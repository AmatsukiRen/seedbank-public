"""Versioned prerequisites for goals, evaluated from current completion evidence."""
from .util import SeedError, canonical_json, sha256

FORMAT = "seedbank/learning@4"
BLOCKED = "前置目标尚未按当前依据完成，请先完成或明确修订前置安排。"
EXTERNAL_BLOCKED = "本次未执行这项操作；当前目标暂不具备开始条件。"


def clean(raw, *, stored=False):
    keys = {"goal_id", "criteria_id", "criteria_sha256"} if stored else {"goal_id", "criteria_id"}
    if not isinstance(raw, list) or len(raw) > 6:
        raise SeedError("前置目标应为最多六项的列表。")
    result, seen = [], set()
    for item in raw:
        if (not isinstance(item, dict) or set(item) != keys
                or not all(isinstance(item.get(k), str) and 0 < len(item[k]) <= 100 for k in keys)
                or not item["goal_id"].startswith("g_") or not item["criteria_id"].startswith("l_")
                or item["goal_id"] in seen):
            raise SeedError("前置目标编号或条件版本无效，不能重复选择。")
        if stored and (len(item["criteria_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in item["criteria_sha256"])):
            raise SeedError("前置目标的条件指纹无效；原记录已保留。")
        seen.add(item["goal_id"])
        result.append(dict(item))
    return result


def _acyclic(graph):
    # Iterative DFS supports long histories without a Python recursion limit.
    visited, active = set(), set()
    for root in graph:
        stack = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.remove(node)
                visited.add(node)
                continue
            if node in visited:
                continue
            if node in active:
                raise SeedError("前置目标形成循环，请调整先后关系。")
            active.add(node)
            stack.append((node, True))
            stack.extend((child, False) for child in graph.get(node, []))


def audit(rows):
    known, latest = {}, {}
    for row in rows:
        if row["kind"] != "criteria":
            continue
        if row["format"] == "seedbank/learning@5" and row["goal_id"] in latest:
            raise SeedError("模型不能以新阶段名义替换已有完成条件；原记录已保留。")
        if "prerequisites" in latest.get(row["goal_id"], {}).get("data", {}) and "prerequisites" not in row["data"]:
            raise SeedError("前置安排不能由旧格式静默移除；原记录已保留。")
        for ref in row["data"].get("prerequisites", []):
            prior = known.get(ref["criteria_id"])
            if (not prior or prior["goal_id"] != ref["goal_id"] or ref["goal_id"] == row["goal_id"]
                    or sha256(canonical_json(prior)) != ref["criteria_sha256"]):
                raise SeedError("前置目标没有对应的先前条件版本；原记录已保留。")
        known[row["id"]] = row
        latest[row["goal_id"]] = row
    _acyclic({key: [r["goal_id"] for r in row["data"].get("prerequisites", [])] for key, row in latest.items()})


def bind(raw, *, goal_id, loaded):
    selected, evidence = [], []
    for item in clean(raw):
        standard = loaded["criteria"].get(item["goal_id"])
        goal = loaded["state"]["goals"].get(item["goal_id"])
        if (not standard or not goal or goal["status"] == "abandoned" or item["goal_id"] == goal_id
                or standard["id"] != item["criteria_id"]):
            raise SeedError("前置目标或完成条件已变化，请刷新后重新选择。")
        selected.append({**item, "criteria_sha256": sha256(canonical_json(standard))})
        evidence.extend(standard["evidence"])
    latest = {r["goal_id"]: r for r in loaded["rows"] if r["kind"] == "criteria"}
    graph = {key: [ref["goal_id"] for ref in row["data"].get("prerequisites", [])] for key, row in latest.items()}
    graph[goal_id or "new_goal"] = [ref["goal_id"] for ref in selected]
    _acyclic(graph)
    return selected, evidence


def readiness(pack, goal_id, *, loaded=None):
    from . import learning
    from .development import outcome_dependencies
    loaded = loaded if loaded is not None else learning.view(pack)
    standards = loaded["criteria"]
    raw = {r["goal_id"]: r for r in loaded["rows"] if r["kind"] == "criteria"}
    # Hidden current constraints never fall back to an unconstrained old version.
    if goal_id not in standards:
        constrained = bool(raw.get(goal_id, {}).get("data", {}).get("prerequisites"))
        return {"ready": not constrained, "requirements": [], "dependencies": [], "evidence": [],
                "state": "unavailable" if constrained else "ready"}
    memo, active = {}, set()
    stack = [(goal_id, False)]
    while stack:
        node, leaving = stack.pop()
        if node in memo:
            continue
        standard = standards.get(node)
        requirements = standard["data"].get("prerequisites", []) if standard else []
        if not leaving:
            if node in active:
                raise SeedError("前置目标形成循环，请调整先后关系。")
            active.add(node)
            stack.append((node, True))
            stack.extend((ref["goal_id"], False) for ref in requirements if ref["goal_id"] not in memo)
            continue
        active.remove(node)
        refs, deps, checks = {}, set(), []

        def include(evidence):
            for ref in evidence:
                refs[(ref["id"], ref["source"])] = dict(ref)
                if ref["id"] != "current":
                    deps.add(ref["id"])

        if standard:
            include(standard["evidence"])
        for ref in requirements:
            child = ref["goal_id"]
            goal = loaded["state"]["goals"].get(child)
            current = standards.get(child)
            state = "unavailable"
            title = goal.get("title", "") if goal else ""
            if goal:
                include(goal.get("evidence", []))
            if current:
                include(current["evidence"])
            nested = memo[child]
            include(nested["evidence"])
            deps.update(nested["dependencies"])
            if goal and current:
                if current["id"] != ref["criteria_id"] or sha256(canonical_json(current)) != ref["criteria_sha256"]:
                    state = "changed"
                elif goal["status"] != "completed":
                    state = "not_completed"
                else:
                    result = learning.evaluate_direct(pack, child, goal.get("completion_evidence"), loaded=loaded)
                    state = "met" if result["passed"] and nested["ready"] else "evidence_changed"
                    evidence = goal.get("completion_evidence")
                    for identifier in (set(evidence.values()) if isinstance(evidence, dict) else ()):
                        outcome = loaded["outcomes"].get(identifier, {})
                        include(outcome.get("evidence", []))
                        deps.update(outcome_dependencies(outcome))
                        feedback = loaded["feedback"].get((current["id"], identifier), {})
                        include(feedback.get("evidence", []))
            checks.append({"goal_id": child, "title": title, "criteria_id": ref["criteria_id"],
                           "criteria_sha256": ref["criteria_sha256"],
                           "completion_event_id": goal["event_id"] if state == "met" else "",
                           "ready": state == "met", "state": state})
        ready = all(check["ready"] for check in checks) and (standard is not None or not raw.get(node, {}).get("data", {}).get("prerequisites"))
        memo[node] = {"ready": ready, "state": "ready" if ready else "waiting", "requirements": checks,
                      "dependencies": sorted(deps), "evidence": list(refs.values())}
    return memo[goal_id]


def _completion_events(pack, loaded):
    from .development import events
    if "_completion_events" not in loaded:
        loaded["_completion_events"] = {row["id"]: row for row in events(pack)
            if row["kind"] == "goal" and row["data"]["status"] == "completed"}
    return loaded["_completion_events"]


def execution_reference(pack, goal_id, *, loaded=None):
    """Runtime evidence recorded before an ability; never supplied by a model."""
    from . import learning
    loaded = loaded if loaded is not None else learning.view(pack)
    report = readiness(pack, goal_id, loaded=loaded)
    if not report["ready"]:
        raise SeedError(BLOCKED)
    if not report["requirements"]:
        return {}, []
    versions = _completion_events(pack, loaded)
    standard = loaded["criteria"][goal_id]
    items = [{**{key: row[key] for key in ("goal_id", "criteria_id", "criteria_sha256", "completion_event_id")},
              "completion_sha256": sha256(canonical_json(versions[row["completion_event_id"]]))}
             for row in report["requirements"]]
    return {"format": "seedbank/goal-readiness@1", "criteria_id": standard["id"],
            "criteria_sha256": sha256(canonical_json(standard)), "requirements": items}, report["evidence"]


def satisfied_at_execution(pack, standard, outcome, loaded):
    source = str(outcome.get("source", "")).split("#", 1)
    original = loaded["originals"].get(source[1], {}) if len(source) == 2 else {}
    recorded = original.get("metadata", {}).get("prerequisite_check", {})
    if (not isinstance(recorded, dict) or recorded.get("format") != "seedbank/goal-readiness@1"
            or recorded.get("criteria_id") != standard["id"]
            or recorded.get("criteria_sha256") != sha256(canonical_json(standard))
            or not isinstance(recorded.get("requirements"), list)):
        return False
    rows = recorded["requirements"]
    if len(rows) != len(standard["data"]["prerequisites"]) or any(not isinstance(row, dict) for row in rows):
        return False
    versions = _completion_events(pack, loaded)
    for ref in standard["data"]["prerequisites"]:
        row = next((item for item in rows if item.get("goal_id") == ref["goal_id"]), {})
        event = versions.get(row.get("completion_event_id")) if isinstance(row.get("completion_event_id"), str) else None
        if (any(row.get(key) != value for key, value in ref.items()) or not event
                or event["data"]["id"] != ref["goal_id"]
                or sha256(canonical_json(event)) != row.get("completion_sha256")):
            return False
    return True


def options(loaded, goal_id):
    return [{"goal_id": key, "criteria_id": row["id"], "title": loaded["state"]["goals"][key]["title"]}
            for key, row in loaded["criteria"].items() if loaded["state"]["goals"][key]["status"] != "abandoned"]


def display_lines(report):
    from .i18n import t
    labels = {"met": "当前依据已满足", "changed": "完成条件已修订，请重新选择版本",
              "not_completed": "尚未核对完成", "evidence_changed": "完成依据需要重新核对", "unavailable": "前置目标依据不可用"}
    if not report.get("ready", True) and not report.get("requirements"):
        return [t("前置目标依据不可用")]
    return [(row["title"] or t("前置目标依据不可用")) + " · " + t(labels[row["state"]]) for row in report.get("requirements", [])]
