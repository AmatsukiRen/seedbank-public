"""Exact, private links between a saved schedule and local action receipts."""
from copy import deepcopy

from . import planning
from .memory_state import MemoryPolicy
from .util import canonical_json, sha256

FORMAT = "seedbank/plan-link@1"


def _digest(entry):
    # Hash an immutable entry, not the append-only file containing it.
    return sha256(canonical_json(entry))


def _visible(pack, entry, policy):
    plan = entry["plan"]
    refs = plan.get("evidence", [])
    # Imported extension fields remain on disk; malformed provenance cannot
    # become a usable link or crash otherwise readable legacy history.
    if "generation" in plan and not isinstance(plan["generation"], dict):
        return False
    if (getattr(policy, "audience_id", "owner") != "owner"
            or len(policy.supports(refs)) != len(refs)
            or not policy.allows_generation(plan.get("generation"))):
        return False
    if plan.get("origin") == "model":
        from .deliberation import valid
        return valid(pack, plan, policy=policy)
    return True


def _entries(pack):
    from .agency import load_agency
    return planning.entries(pack, load_agency(pack)["plans"])


def capture(pack, day, *, execution, audience_id="owner"):
    """Read only. Legacy rows without a stable entry are deliberately unlinked."""
    if audience_id != "owner":
        return {}
    if execution not in ("automatic", "requested"):
        raise ValueError("Unknown action origin")
    entries = _entries(pack)
    entry = planning._heads(entries).get(day)
    if not entry or entry["kind"] == "legacy" or not _visible(pack, entry, MemoryPolicy.load(pack)):
        return {}
    return {"format": FORMAT, "plan_id": entry["id"], "entry_sha256": _digest(entry),
            "day": day, "execution": execution}


def _matches(reference, entry, digest):
    if (not isinstance(reference, dict) or reference.get("format") != FORMAT
            or reference.get("execution") not in ("automatic", "requested")
            or type(reference.get("day")) is not int or reference["day"] < 1):
        return False
    return (entry["kind"] != "legacy" and entry["id"] == reference.get("plan_id")
            and entry["plan"]["day"] == reference["day"] and digest == reference.get("entry_sha256"))


def resolve(pack, reference, *, policy=None, entries=None):
    if not isinstance(reference, dict):
        return None
    rows = entries if entries is not None else _entries(pack)
    entry = next((row for row in rows if row["id"] == reference.get("plan_id")), None)
    if not entry or not _matches(reference, entry, _digest(entry)):
        return None
    return entry if _visible(pack, entry, policy or MemoryPolicy.load(pack)) else None


def recent(pack, *, state, policy, limit=6):
    """Bounded review of currently usable receipts; never infer old links or completion."""
    if getattr(policy, "audience_id", "owner") != "owner":
        return []
    entries = _entries(pack)
    selected = [entry for entry in entries if entry["kind"] != "legacy"][-limit:]
    return review(pack, selected=selected, state=state, policy=policy, entries=entries)


def review(pack, *, selected, state, policy, entries=None):
    if getattr(policy, "audience_id", "owner") != "owner":
        return []
    from .development import execution_state, outcome_dependencies
    entries = _entries(pack) if entries is None else entries
    heads = {row["id"] for row in planning._heads(entries).values()}
    from . import learning, plan_checkpoints
    rubric_state = learning.view(pack, state=state, policy=policy) if any(row["plan"].get("checkpoint") for row in selected) else None
    result = []
    for entry in selected:
        if not _visible(pack, entry, policy):
            continue
        plan = entry["plan"]
        digest = _digest(entry)
        linked = []
        for outcome in state["outcomes"]:
            ref = outcome.get("plan_reference", {})
            if outcome["day"] == plan["day"] and _matches(ref, entry, digest):
                linked.append(outcome)
        counts = {origin: {status: 0 for status in ("succeeded", "failed", "blocked")}
                  for origin in ("automatic", "requested")}
        deps = set(plan.get("generation", {}).get("context_dependencies", []))
        deps.update(ref["id"] for ref in plan.get("evidence", []) if ref.get("id") not in (None, "", "current"))
        for outcome in linked:
            status = outcome.get("status")
            if status in counts[outcome["plan_reference"]["execution"]]:
                counts[outcome["plan_reference"]["execution"]][status] += 1
            deps.update(outcome_dependencies(outcome))
        checkpoint = plan_checkpoints.evaluate(pack, entry, loaded=rubric_state, policy=policy) if plan.get("checkpoint") else {}
        deps.update(checkpoint.get("dependencies", []))
        result.append({"plan_id": entry["id"], "entry_sha256": digest,
                       "day": plan["day"], "selected_at": entry["at"], "plan": plan["plan"],
                       "reason": plan.get("reason", ""), "goal_id": plan.get("goal_id", ""),
                       "goal_event_id": plan.get("goal_event_id", ""), "continuity": deepcopy(plan.get("continuity", {})),
                       "mode": plan.get("mode", ""), "origin": plan.get("origin", "runtime"),
                       "is_latest_for_day": entry["id"] in heads, "counts": counts,
                       "outcomes": [{**{k: deepcopy(row.get(k, "")) for k in
                           ("id", "action", "status", "detail", "goal_id")},
                           "execution": row["plan_reference"]["execution"],
                           "attempt_state": execution_state(row)} for row in linked[-3:]],
                       "omitted_outcomes": max(0, len(linked) - 3), "dependencies": sorted(deps),
                       "checkpoint": {k: v for k, v in checkpoint.items() if k not in ("dependencies", "evidence")}})
    return result


def prompt_lines(rows):
    if not rows:
        return ""
    visible = [{k: v for k, v in row.items() if k != "dependencies"} for row in rows]
    return ("\n计划与实际行动（仅当前依据可用且绑定到具体版本的回执）：\n"
            + canonical_json(visible)
            + "\nautomatic 是模型提议的动作，requested 是用户直接要求的操作；记录当时的安排不证明动作符合该安排。"
              "成功仅说明该动作成功，blocked 表示没有进入执行流程，failed 不证明完整执行；attempt_state=unknown 时不能推断已开始尝试。均不自动完成文字计划。"
              "没有关联回执仅表示此处没有可用记录；旧结果未推断归属，也不能据此认定什么都没做。"
              "checkpoint 若存在，仅核对选择时绑定的完整条件与该版本下的成果/反馈；passed 表示这些条件当前满足，不证明自由文字的其他含义或长期目标已完成。"
              "条件满足后先选择下一步再自动创作/反思；反馈修订或作品变化会改变当前核对结果。"
              "历史安排不代表今天的选择，可据实际结果提出新的 daily_plan。")


def display_lines(rows):
    from .i18n import t
    from .development import attempt_label
    result = []
    for row in reversed(rows):
        lines = [t("第 {number} 天", number=row["day"]) + " · " + row["selected_at"],
                 t("当日最新安排" if row["is_latest_for_day"] else "历史安排") + " · " + row["plan"]]
        if row.get("continuity"):
            from .plan_continuity import link_line
            lines.append(link_line(row["continuity"]))
        if row.get("reason"):
            lines.append(t("理由：{text}", text=row["reason"]))
        if row.get("checkpoint"):
            from .plan_checkpoints import label
            lines.append(label(row["checkpoint"]))
            lines.extend(item["group"] + " · " + item["text"] for item in row["checkpoint"].get("criteria", []))
            lines.extend(match["group"] + " · " + match.get("detail", "") for match in row["checkpoint"].get("matches", []))
        for origin, label in (("automatic", "模型提议的动作"), ("requested", "用户直接要求的操作")):
            counts = row["counts"][origin]
            lines.append(t(label) + " · " + t("动作成功 {succeeded} · 失败 {failed} · 未执行 {blocked}", **counts))
        lines.extend(t("用户直接要求的操作" if receipt["execution"] == "requested" else "模型提议的动作")
                     + " · " + t(receipt["status"]) + " · " + attempt_label(receipt)
                     + " · " + receipt["detail"] for receipt in row["outcomes"])
        if row["omitted_outcomes"]:
            lines.append(t("另有 {count} 条关联回执保留在档案中。", count=row["omitted_outcomes"]))
        lines.append(t("仅统计当前可用的关联回执；没有记录不等于没有行动，动作成功不代表计划完成。"))
        result.append("\n".join(lines))
    return result
