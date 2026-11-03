"""Append-only daily choices, with an unchanged snapshot of pre-ledger plans.

The runtime selects a next step from current goals. These are scheduling records,
not evidence that the individual completed a plan or consciously chose it.
"""
from copy import deepcopy
from pathlib import Path
import uuid

from . import jsonl
from .pack_lock import durable
from .util import SeedError, now_iso, read_json, write_json_atomic

FORMAT = "seedbank/plans@1"
DECISION_FORMAT = "seedbank/plans@2"
CHECKPOINT_FORMAT = "seedbank/plans@3"
CONTINUITY_FORMAT = "seedbank/plans@4"
SUPPORTED_FORMATS = (FORMAT, DECISION_FORMAT, CHECKPOINT_FORMAT, CONTINUITY_FORMAT)
PROJECTED = ("plan_id", "selected_at", "selection_kind", "replaces")


def path(pack):
    return Path(pack) / "mind" / "plans.jsonl"


def clean_plans(value):
    """Validate existing content without truncation, deduplication or invented time."""
    if not isinstance(value, list):
        raise SeedError("计划记录应为列表；原档案已保留。")
    rows = deepcopy(value)
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("day")) is not int or row["day"] < 1
                or not isinstance(row.get("plan"), str) or not row["plan"].strip()):
            raise SeedError("计划记录缺少有效日页或正文；原档案已保留。")
        for key, default in (("done", False), ("reason", ""), ("goal_id", "")):
            row.setdefault(key, default)
        if type(row["done"]) is not bool or not all(isinstance(row[k], str) for k in ("reason", "goal_id")):
            raise SeedError("计划状态或理由格式不完整；原档案已保留。")
        if "goal_event_id" in row and not isinstance(row["goal_event_id"], str):
            raise SeedError("计划的目标版本无效；原档案已保留。")
        if "evidence" in row and (not isinstance(row["evidence"], list) or any(
                not isinstance(ref, dict) or not isinstance(ref.get("id"), str)
                or not isinstance(ref.get("source"), str) for ref in row["evidence"])):
            raise SeedError("计划依据格式不完整；原档案已保留。")
    return rows


def _validate(row, number):
    if (row.get("format") not in SUPPORTED_FORMATS or row.get("kind") not in ("baseline", "selection", "legacy_flag", "import", "decision")
            or not isinstance(row.get("id"), str) or not row["id"].startswith("p_")
            or not isinstance(row.get("at"), str) or not row["at"]):
        raise SeedError(f"第 {number} 条计划历史格式不完整；原档案已保留。")
    if row["kind"] == "baseline":
        clean_plans(row.get("plans"))
    else:
        clean_plans([row.get("plan")])
        if (not {"day", "plan", "done", "reason", "goal_id"}.issubset(row["plan"])
                or not isinstance(row.get("previous"), str) or not isinstance(row.get("trigger"), str)
                or not isinstance(row.get("context"), dict)):
            raise SeedError("计划修订缺少前一版本或选择背景；原档案已保留。")
        if row["kind"] == "decision" and (row["format"] not in (DECISION_FORMAT, CHECKPOINT_FORMAT, CONTINUITY_FORMAT)
                or row["plan"].get("origin") != "model" or row["plan"].get("mode") not in ("focus", "rest", "open")
                or not isinstance(row["plan"].get("decision_id"), str)
                or not row["plan"]["decision_id"].startswith("x_")
                or not isinstance(row["plan"].get("generation"), dict)
                or not row["plan"].get("evidence")):
            raise SeedError("模型计划选择缺少来源或版本；原档案已保留。")
        if "checkpoint" in row["plan"]:
            from .plan_checkpoints import valid_binding
            if (row["format"] not in (CHECKPOINT_FORMAT, CONTINUITY_FORMAT) or row["plan"].get("mode") != "focus"
                    or row["plan"].get("origin") != "model" or not valid_binding(row["plan"]["checkpoint"])):
                raise SeedError("计划结束条件的版本或来源不完整；原档案已保留。")
        if "continuity" in row["plan"]:
            from .plan_continuity import valid_binding
            if (row["format"] != CONTINUITY_FORMAT or row["plan"].get("origin") != "model"
                    or not valid_binding(row["plan"]["continuity"])):
                raise SeedError("跨日选择的版本或来源不完整；原档案已保留。")


def _legacy_entries(plans):
    return [{"id": f"legacy:{index}", "kind": "legacy", "at": "", "previous": "",
             "trigger": "legacy_snapshot", "context": {}, "plan": plan}
            for index, plan in enumerate(plans)]


def _heads(entries):
    heads = {}
    for entry in entries:
        day = entry["plan"]["day"]
        # The old reader used the first row for a day. Duplicate baseline rows
        # remain inspectable without pretending their order is a revision chain.
        if entry["kind"] != "legacy" or day not in heads:
            heads[day] = entry
    return heads


def read(pack):
    rows = jsonl.read(path(pack), _validate)
    if not rows:
        if path(pack).exists():
            raise SeedError("计划历史缺少起始快照；原文件已保留。")
        return []
    if rows[0]["kind"] != "baseline":
        raise SeedError("计划历史缺少起始快照；原文件已保留。")
    heads = _heads(_legacy_entries(rows[0]["plans"]))
    known = {rows[0]["id"]}
    earlier = {}
    for row in rows[1:]:
        if row["kind"] == "baseline" or row["id"] in known:
            raise SeedError("计划历史编号重复或起始快照重复；原文件已保留。")
        day = row["plan"]["day"]
        if row["previous"] != heads.get(day, {}).get("id", ""):
            raise SeedError("计划版本关系不连续；原文件已保留。")
        if "continuity" in row["plan"]:
            from .plan_continuity import matches
            binding = row["plan"]["continuity"]
            if not matches(binding, earlier.get(binding["plan_id"]), row["plan"]):
                raise SeedError("跨日选择未指向有效的先前计划版本；原文件已保留。")
        heads[day] = row
        earlier[row["id"]] = row
        known.add(row["id"])
    return rows


def entries(pack, legacy):
    rows = read(pack)
    if not rows:
        return _legacy_entries(clean_plans(legacy))
    return _legacy_entries(clean_plans(rows[0]["plans"])) + rows[1:]


def _project(entry):
    return {**deepcopy(entry["plan"]), "plan_id": entry["id"], "selected_at": entry["at"],
            "selection_kind": entry["kind"], "replaces": entry["previous"]}


def project(pack, legacy):
    if not path(pack).exists():
        # Preserve all old rows and extension fields until the first real write.
        return clean_plans(legacy)
    return [_project(entry) for _, entry in sorted(_heads(entries(pack, legacy)).items())]


def awaiting_choice(pack, plan):
    """Operational hold, including earlier records written before the flag existed."""
    if not plan:
        return False
    if plan.get("awaiting_choice") is True:
        return True
    if not str(plan.get("plan_id", "")).startswith("p_"):
        return False
    entry = jsonl.find(path(pack), plan["plan_id"], _validate)
    return bool(entry and entry.get("trigger") == "decision_basis_changed")


@durable
def choose(pack, plan, *, legacy, kind="selection", trigger="", context=None):
    if kind not in ("selection", "legacy_flag", "import", "decision"):
        raise SeedError("计划记录类型无效。")
    plan = clean_plans([plan])[0]
    for key in PROJECTED:
        plan.pop(key, None)
    rows = read(pack)
    old = _legacy_entries(clean_plans(rows[0]["plans"] if rows else legacy)) + rows[1:]
    previous = _heads(old).get(plan["day"])
    comparable = {k: v for k, v in previous["plan"].items() if k not in PROJECTED} if previous else None
    if comparable == plan:
        return _project(previous)
    additions = []
    if not rows:
        # Snapshot time is recorded separately; missing original selection times
        # stay unknown. This also retains duplicates and legacy extension fields.
        additions.append({"format": FORMAT, "id": "p_" + uuid.uuid4().hex, "kind": "baseline",
                          "at": now_iso(), "plans": deepcopy(legacy)})
    version = (CONTINUITY_FORMAT if "continuity" in plan else CHECKPOINT_FORMAT if "checkpoint" in plan
               else DECISION_FORMAT if kind == "decision" else FORMAT)
    row = {"format": version, "id": "p_" + uuid.uuid4().hex, "kind": kind, "at": now_iso(),
           "plan": plan, "previous": previous["id"] if previous else "",
           "trigger": str(trigger), "context": dict(context or {})}
    if "continuity" in plan:
        from .plan_continuity import matches, valid_binding
        binding = plan["continuity"]
        if not valid_binding(binding) or not matches(binding, next((entry for entry in old if entry["id"] == binding["plan_id"]), None), plan):
            raise SeedError("跨日选择未指向有效的先前计划版本；原文件已保留。")
    additions.append(row)
    jsonl.append(pack, path(pack), additions, _validate)
    if not rows or kind == "decision" or version in (CHECKPOINT_FORMAT, CONTINUITY_FORMAT):
        config_path = Path(pack) / "mind" / "agency.json"
        config = read_json(config_path, None) if config_path.exists() else {"format": "seedbank/agency@1"}
        if not isinstance(config, dict) or config.get("format", "seedbank/agency@1") != "seedbank/agency@1":
            raise SeedError("意志档案格式无法读取；原文件已保留。")
        previous_format = config.get("plan_store", FORMAT)
        if previous_format not in SUPPORTED_FORMATS:
            raise SeedError("计划历史版本无法识别；原文件已保留。")
        required = max((version, previous_format, *(row["format"] for row in rows)), key=SUPPORTED_FORMATS.index)
        write_json_atomic(config_path, {**config, "plan_store": required})
    return _project(row)


def history(pack, legacy, *, day=None, before="", limit=20):
    if not isinstance(before, str):
        raise SeedError("计划历史游标应为字符串。")
    if isinstance(limit, str) and limit.isascii() and limit.isdigit():
        limit = int(limit)
    if type(limit) is not int or not 1 <= limit <= 200:
        raise SeedError("计划历史每页数量应为 1 到 200 的整数。")
    if isinstance(day, str) and day.isascii() and day.isdigit():
        day = int(day)
    if day is not None and (type(day) is not int or day < 1):
        raise SeedError("计划历史日页应为正整数。")
    all_entries = entries(pack, legacy)
    current = {row["id"] for row in _heads(all_entries).values()}
    rows = list(reversed(all_entries))
    if day is not None:
        rows = [row for row in rows if row["plan"]["day"] == day]
    if before:
        found = next((i for i, row in enumerate(rows) if row["id"] == before), None)
        if found is None:
            raise SeedError("计划历史游标不存在或不属于所选日页。")
        rows = rows[found + 1:]
    selected = rows[:limit]
    return {"records": [{**row, "is_current": row["id"] in current} for row in selected],
            "next_before": selected[-1]["id"] if len(rows) > limit else "",
            "has_more": len(rows) > limit}
