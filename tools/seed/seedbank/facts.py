"""Sourced, single-valued assertions; disagreement never means latest wins.

This is a record of claims, not an oracle. Entity IDs and exact aspect keys
avoid merging people or predicates by semantic similarity. Original material
and decisions are append-only; only explicit user decisions resolve conflicts.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import unicodedata
import uuid

from . import experience, jsonl, requests
from .pack_lock import durable, serialized
from .util import SeedError, now_iso, read_json, sha256

FORMAT = "seedbank/facts@1"
BUILTINS = {"owner": "用户", "self": "这个个体"}


def path(pack):
    return Path(pack) / "mind/facts.jsonl"


def _text(value, maximum, label):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise SeedError(f"{label}不能为空，且最多 {maximum} 字。")
    value = value.strip()
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise SeedError("事实记录含有无法保存的控制字符。")
    return value


def slot_id(subject, aspect):
    # Preserve negation, punctuation and digits. No fuzzy/semantic aliasing.
    key = unicodedata.normalize("NFC", aspect.strip()).casefold()
    return "s_" + sha256(json.dumps([subject, key], ensure_ascii=False))[:32]


def _validate(row, number):
    try:
        if row.get("kind") == "retract":
            from .fact_retractions import validate
            validate(row)
            return
        if row.get("kind") == "timing":
            from .fact_dates import validate
            validate(row)
            return
        if row.get("format") != FORMAT or row.get("kind") not in ("entity", "claim", "resolve", "forget"):
            raise ValueError()
        for key in ("id", "at"):
            _text(row.get(key), 100, key)
        kind = row["kind"]
        if kind == "entity":
            _text(row.get("label"), 80, "人物名称")
            if "identity_key" in row:
                _text(row["identity_key"], 100, "身份依据")
        elif kind == "claim":
            _text(row.get("subject"), 100, "人物编号")
            _text(row.get("aspect"), 60, "事项")
            _text(row.get("value"), 240, "说法")
            _text(row.get("quote"), 800, "原文")
            if "starts_on" in row:
                from .memory_state import effective_date
                if not isinstance(row["starts_on"], str) or effective_date(row["starts_on"]) != row["starts_on"]:
                    raise ValueError()
            if row["value"] not in row["quote"] or row.get("slot") != slot_id(row["subject"], row["aspect"]):
                raise ValueError()
            if row.get("origin") not in ("user", "model") or not isinstance(row.get("evidence"), list) or not row["evidence"]:
                raise ValueError()
            for ref in row["evidence"]:
                if not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ("id", "source", "kind")):
                    raise ValueError()
        else:
            _text(row.get("slot"), 100, "事项编号")
            _text(row.get("reason"), 500, "理由")
            if not isinstance(row.get("targets"), list) or not row["targets"] or not all(isinstance(v, str) for v in row["targets"]):
                raise ValueError()
            if kind == "resolve":
                if row.get("selected") not in row["targets"] or row.get("change_type") not in ("correction", "change"):
                    raise ValueError()
                from .memory_state import effective_date
                effective_date(row.get("effective_on", ""))
                if row.get("effective_on") and row["change_type"] != "change":
                    raise ValueError()
            if not isinstance(row.get("evidence"), list) or not row["evidence"]:
                raise ValueError()
            if any(not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k]
                   for k in ("id", "source", "kind")) for ref in row["evidence"]):
                raise ValueError()
    except (SeedError, ValueError, TypeError, KeyError):
        raise SeedError(f"第 {number} 条事实记录格式不完整；原文件已保留。") from None


def read(pack):
    rows = jsonl.read(path(pack), _validate)
    ids, entities, claims, withdrawn = set(), set(BUILTINS), {}, set()
    identity_keys = set()
    nodes, latest_times = {}, {}
    for row in rows:
        if row["id"] in ids:
            raise SeedError("事实记录编号重复；原文件已保留。")
        ids.add(row["id"])
        if row["kind"] == "entity":
            if row["id"] in entities:
                raise SeedError("人物编号重复；原文件已保留。")
            entities.add(row["id"])
            if row.get("identity_key"):
                if row["identity_key"] in identity_keys:
                    raise SeedError("人物的出生依据重复；原文件已保留。")
                identity_keys.add(row["identity_key"])
        elif row["kind"] == "claim":
            if row["subject"] not in entities:
                raise SeedError("事实引用了不存在的人物；原文件已保留。")
            claims[row["id"]] = row
        elif row["kind"] == "timing":
            from .fact_dates import digest
            target = nodes.get(row["target"], {})
            if (target.get("kind") != "claim" and not (target.get("kind") == "resolve" and target.get("change_type") == "change")):
                raise SeedError("日期修订的目标无法识别；原文件已保留。")
            if row["target_hash"] != digest(target) or row["supersedes"] != latest_times.get(row["target"], ""):
                raise SeedError("日期修订的来源或版本关系不完整；原文件已保留。")
            latest_times[row["target"]] = row["id"]
        else:
            if any(target not in claims or claims[target]["slot"] != row["slot"] for target in row["targets"]):
                raise SeedError("事实决定的引用不完整；原文件已保留。")
            if len(set(row["targets"])) != len(row["targets"]):
                raise SeedError("事实决定的编号重复；原文件已保留。")
            if row["kind"] == "retract":
                from .fact_dates import digest
                target = claims[row["target"]]
                if (target["origin"] != "model" or digest(target) != row["target_hash"]
                        or row["target"] in withdrawn):
                    raise SeedError("提取撤回的来源或版本关系不完整；原文件已保留。")
                withdrawn.add(row["target"])
            elif row["kind"] == "resolve":
                if set(row["targets"]) & withdrawn:
                    raise SeedError("事实决定引用了已退出当前状态的说法；原文件已保留。")
                withdrawn.update(set(row["targets"]) - {row["selected"]})
            else:
                withdrawn.update(row["targets"])
        nodes[row["id"]] = row
    return rows


def entities(pack):
    """Stable registry only; no claim inference or name-based person matching."""
    result = dict(BUILTINS)
    result["self"] = str((read_json(Path(pack) / "birth.json", {}) or {}).get("name") or BUILTINS["self"])
    result.update({r["id"]: r["label"] for r in read(pack) if r["kind"] == "entity"})
    return result


@durable
def register_visitor(pack, label, identity_key):
    """A local birth-document key identifies copies, not an authenticated sender."""
    label = _text(label, 80, "人物名称")
    identity_key = _text(identity_key, 100, "身份依据")
    rows = [r for r in read(pack) if r["kind"] == "entity" and r.get("identity_key") == identity_key]
    if len(rows) > 1:
        raise SeedError("来访身份对应多条人物记录，请先核对原文件。")
    return rows[0] if rows else _append(pack, "entity", label=label, identity_key=identity_key)


def _append(pack, kind, **fields):
    row = {"format": "seedbank/facts@3" if kind == "retract" else "seedbank/facts@2" if kind == "timing" else FORMAT,
           "id": "f_" + uuid.uuid4().hex, "kind": kind, "at": now_iso(), **fields}
    jsonl.append(pack, path(pack), [row], _validate)
    return row


def suppressed_ids(pack, *, sources=None):
    """Used by MemoryPolicy without depending on MemoryPolicy ourselves."""
    from .memory_sources import PolicySources
    sources = sources if sources is not None else PolicySources(pack)
    rows = read(pack)
    forgotten = {identifier for row in rows if row["kind"] == "forget" for identifier in row["targets"]}
    refs = set(forgotten)
    for row in rows:
        if row["kind"] == "claim" and row["id"] in forgotten:
            refs.update(ref["id"] for ref in row["evidence"])
        elif row["kind"] in ("resolve", "forget") and set(row["targets"]) & forgotten:
            refs.update(ref["id"] for ref in row["evidence"])
    if any(r["kind"] == "timing" for r in rows):
        from .fact_dates import suppressed
        refs.update(suppressed(rows, sources.experiences))
    if any(r["kind"] == "retract" for r in rows):
        from .fact_retractions import suppressed
        refs.update(suppressed(rows, sources.experiences))
    if any(r["kind"] == "resolve" and r["change_type"] == "correction" for r in rows):
        from .fact_corrections import suppressed
        refs.update(suppressed(rows, sources.experiences))
    return refs


def _extraction_generation(row, originals):
    """The sibling reply is an output of extraction, not its input evidence.

    Old chat records included that reply among extraction dependencies. Keep
    its ID as provenance, while retaining all other context dependencies.
    """
    generation = dict(row["generation"]) if isinstance(row.get("generation"), dict) else {}
    inputs = {r["id"] for r in row.get("evidence", [])}
    outputs = {identifier for identifier in generation.get("context_dependencies", [])
               if identifier in originals and originals[identifier].get("kind") == "conversation"
               and "context_dependencies" in originals[identifier].get("metadata", {})
               and inputs & set(originals[identifier].get("depends_on", []))}
    if outputs:
        generation["context_dependencies"] = [r for r in generation["context_dependencies"] if r not in outputs]
        generation["extraction_reply_ids"] = sorted(set(generation.get("extraction_reply_ids", [])) | outputs)
    return generation


def _state(pack, policy=None):
    from .memory_state import MemoryPolicy
    rows = read(pack)
    entities = dict(BUILTINS)
    entities["self"] = str((read_json(Path(pack) / "birth.json", {}) or {}).get("name") or BUILTINS["self"])
    if not rows:
        return entities, {}
    policy = policy if policy is not None else MemoryPolicy.load(pack)
    claims, removed, decisions, forgotten = {}, {}, defaultdict(list), set()
    retractions = defaultdict(list)
    originals = {row["id"]: row for row in experience.read(pack)}
    from .fact_dates import overlay
    rows = overlay(rows, policy, originals)
    for row in rows:
        if row["kind"] == "entity":
            entities[row["id"]] = row["label"]
        elif row["kind"] == "claim":
            claims[row["id"]] = row
        elif row["kind"] == "forget":
            forgotten.update(row["targets"])
        elif row["kind"] == "retract":
            from .fact_retractions import supported
            item = {**row, "available": supported(row, policy, originals)}
            retractions[row["slot"]].append(item)
            removed[row["target"]] = item
        elif row["kind"] == "resolve":
            decisions[row["slot"]].append(row)
            # A withdrawn source never resurrects a rejected old assertion.
            for target in row["targets"]:
                if target != row["selected"]:
                    removed[target] = row
    groups = {}
    for row in claims.values():
        supported = [ref for ref in policy.supports(row["evidence"])
                     if ref["id"] in originals and policy.allows(originals[ref["id"]])
                     and row["quote"] in originals[ref["id"]]["text"]]
        hidden = row["id"] in forgotten or row["id"] in policy.blocked or not supported
        removal = removed.get(row["id"], {})
        retracted = removal.get("kind") == "retract"
        if retracted and not removal["available"]:
            hidden = True
        choosing = [d for d in decisions[row["slot"]] if d["selected"] == row["id"]]
        adopted = False
        if choosing:
            decision_support = policy.supports(choosing[-1]["evidence"])
            adopted = any(ref["id"] in originals and policy.allows(originals[ref["id"]]) for ref in decision_support)
            if not adopted:
                hidden = True
        # Explicit user adoption supplies a new basis for the reported value.
        # It still requires the original quote and a currently usable decision;
        # removing old model context must not undo that deliberate adoption.
        if not adopted and not policy.allows_generation(_extraction_generation(row, originals)):
            hidden = True
        group = groups.setdefault(row["slot"], {"id": row["slot"], "subject": row["subject"],
                                  "label": entities[row["subject"]], "aspect": row["aspect"],
                                  "claims": [], "history": [], "decisions": decisions[row["slot"]],
                                  "retractions": retractions[row["slot"]]})
        item = {**row, "recallable": not hidden and row["id"] not in removed,
                "unavailable": hidden, "retracted": retracted,
                "superseded_by": removal.get("selected", removal.get("id", "")),
                "change_type": "correction" if retracted else removal.get("change_type", ""),
                "effective_on": removed.get(row["id"], {}).get("effective_on", "")}
        group["history"].append(item)
        if item["recallable"]:
            group["claims"].append(item)
    for group in groups.values():
        values = {row["value"] for row in group["claims"]}
        group["status"] = "conflict" if len(values) > 1 else "reported" if values else "unavailable"
        group["expected"] = sorted(row["id"] for row in group["claims"])
        group["updated_at"] = max([row.get("date_updated_at", row["at"]) for row in group["history"] + group["decisions"] + group["retractions"]])
        group["decisions"] = [{**row, "usable_for_time": any(
            ref["id"] in originals and policy.allows(originals[ref["id"]])
            for ref in policy.supports(row["evidence"]))} for row in group["decisions"]]
        if getattr(policy, "restricted", False):
            group["label"] = policy.entity_label(group["subject"])
            group["decisions"] = [r for r in group["decisions"] if policy.supports(r["evidence"])]
            group["retractions"] = [r for r in group["retractions"] if r["available"]]
    if getattr(policy, "restricted", False):
        entities = {key: policy.entity_label(key) for key in entities}
    return entities, groups


@serialized
def listing(pack, query="", *, audit=False, limit=100, offset=0):
    entities, groups = _state(pack)
    from .fact_dates import digest
    raw_claims = {r["id"]: r for r in read(pack) if r["kind"] == "claim"}
    needle = str(query).strip().casefold()
    selected = [g for g in groups.values() if (audit or g["claims"]) and
                (not needle or needle in (g["label"] + " " + g["aspect"] + " " + " ".join(
                    row["value"] for row in g["history"] if audit or row["recallable"])).casefold())]
    selected.sort(key=lambda g: (g["status"] != "conflict", -len(g["claims"]), g["updated_at"], g["id"]))
    start = max(0, int(offset))
    selected_page = selected[start:start + max(1, min(100, int(limit)))]
    for group in selected_page:
        for item in group["history"]:
            if item["recallable"] and item["origin"] == "model":
                item["target_hash"] = digest(raw_claims[item["id"]])
    if not audit:
        selected_page = [{**g, "history": [], "decisions": [], "retractions": []} for g in selected_page]
    pending = []
    for request in requests.pending(pack):
        if request["payload"].get("kind") != "fact_edit":
            continue
        target = request["payload"].get("data", {}).get("target")
        preview = raw_claims.get(target, {}) if request["payload"].get("action") == "retract" else {}
        pending.append({**request, "target_preview": {k: preview[k] for k in ("value", "quote") if k in preview}})
    return {"entities": [{"id": key, "label": value} for key, value in entities.items()],
            "groups": selected_page, "total": len(selected), "offset": start,
            "pending": pending,
            "conflicts": sum(g["status"] == "conflict" for g in groups.values())}


def context(pack, query="", *, policy=None, references=(), limit=8, on=None):
    from .retrieval import tokens
    from .fact_time import explicit_day, project, query_day
    on_basis = "single_literal_date_hint" if on is None else "retrieval_request"
    on = explicit_day(query) if on is None else query_day(on)
    entities, groups = _state(pack, policy)
    if getattr(policy, "restricted", False):
        entities = {key: policy.entity_label(key) for key in entities}
    terms, refs = set(tokens(query)), set(references)
    ranked = []
    for group in groups.values():
        available = [r for r in group["history"] if not r["unavailable"]]
        visible_retractions = [r for r in group["retractions"] if r["available"]
                               and any(c["id"] == r["target"] for c in available)]
        if not group["claims"] and not (on and available) and not visible_retractions:
            continue
        related = any(ref["id"] in refs for row in available for ref in row["evidence"])
        words = set(tokens(group["label"] + " " + group["aspect"] + " " + " ".join(row["value"] for row in available)))
        score = len(terms & words) + (4 if related else 0)
        if query and not score:
            continue
        ranked.append((score, group))
    ranked.sort(key=lambda pair: (pair[0], pair[1]["status"] == "conflict", pair[1]["updated_at"]), reverse=True)
    result = []
    for _, group in ranked[:limit]:
        result.append({key: group[key] for key in ("id", "subject", "label", "aspect", "status")}
                      | {"claims": [{key: row.get(key, "") for key in ("id", "value", "quote", "at", "origin", "evidence", "starts_on", "date_state", "date_evidence")}
                                    for row in group["claims"][:4]],
                         "candidate_count": len(group["claims"]),
                         "retractions": [{**{k: r[k] for k in ("target", "reason", "evidence")},
                                          "value": c["value"], "quote": c["quote"]}
                                         for r in group["retractions"] if r["available"]
                                         for c in group["history"] if c["id"] == r["target"] and not c["unavailable"]][-4:],
                         "retraction_dependencies": sorted({ref["id"] for r in group["retractions"] if r["available"]
                                                            and any(c["id"] == r["target"] and not c["unavailable"] for c in group["history"])
                                                            for ref in r["evidence"]}),
                         "retraction_count": sum(r["retracted"] and not r["unavailable"] for r in group["history"]),
                         "temporal": project(group, on),
                         "decisions": [{k: row[k] for k in ("selected", "change_type", "effective_on", "evidence")}
                                       for row in group["decisions"][-1:]]})
    # Only referenced people enter the prompt; names are never merged as aliases.
    subjects = {"owner", "self"} | {g["subject"] for g in result}
    if getattr(policy, "restricted", False):
        subjects.discard("owner")
        if policy.person_id:
            subjects.add(policy.person_id)
    else:
        subjects.update([key for key, label in entities.items() if label and label in query][:8])
    return {"entities": [{"id": key, "label": value} for key, value in entities.items() if key in subjects],
            "groups": result, "on": on, "on_basis": on_basis if on else "unspecified", "scope": "selected_reported_claims"}


def annotate_recalled(pack, results, policy=None):
    """Keep a resolved/conflicted facet visible beside otherwise intact prose."""
    if not results:
        return results
    _, groups = _state(pack, policy)
    by_source = defaultdict(list)
    for group in groups.values():
        date_rows = [r for r in group["history"] if not r["unavailable"] and r.get("date_revision")]
        date_rows.extend(r for r in group["decisions"] if r.get("usable_for_time") and r.get("date_revision"))
        retractions = [r for r in group["retractions"] if r["available"]
                       and any(c["id"] == r["target"] and not c["unavailable"] for c in group["history"])]
        if group["status"] != "conflict" and not group["decisions"] and not date_rows and not retractions:
            continue
        note = {"slot": group["id"], "label": group["label"], "aspect": group["aspect"],
                "applies_to": "current_claims_only",
                "status": group["status"], "values": list(dict.fromkeys(r["value"] for r in group["claims"]))[:4],
                "candidate_count": len(group["claims"]),
                "evidence_ids": sorted({ref["id"] for r in group["claims"] for ref in r["evidence"]})}
        if retractions:
            note["retractions"] = [{**{k: r[k] for k in ("target", "reason")},
                                    "value": c["value"]} for r in retractions[-4:]
                                   for c in group["history"] if c["id"] == r["target"]]
            note["retraction_count"] = len(retractions)
            note["evidence_ids"] = sorted(set(note["evidence_ids"]) | {ref["id"] for r in retractions for ref in r["evidence"]})
        if date_rows:
            note.update(time_revised=True, date_revision_count=len(date_rows),
                        date_notes=[{"target": r["id"], "kind": r["kind"],
                                     "date": r.get("starts_on", "") if r["kind"] == "claim" else r.get("effective_on", ""),
                                     "state": r["date_state"]} for r in date_rows[:4]])
            note["evidence_ids"] = sorted(set(note["evidence_ids"]) | {ref["id"] for r in date_rows for ref in r.get("date_evidence", [])})
        if group["decisions"]:
            latest = group["decisions"][-1]
            note.update(change_type=latest["change_type"], effective_on=latest["effective_on"])
            note["evidence_ids"] = sorted(set(note["evidence_ids"]) | {r["id"] for r in latest["evidence"]})
        for ref in {ref["id"] for r in group["history"] if not r["unavailable"] for ref in r["evidence"]}:
            by_source[ref].append(note)
    output = []
    for result in results:
        # Notes are a current, scoped projection, never trusted stored content.
        row = {k: v for k, v in result["memory"].items() if k != "fact_notes"}
        refs = {row.get("id"), row.get("event_id"), *row.get("event_ids", [])}
        if "#" in str(row.get("source", "")):
            refs.add(row["source"].split("#", 1)[1])
        notes = {note["slot"]: note for ref in refs for note in by_source.get(ref, [])}
        output.append({**result, "memory": {**row, "fact_notes": list(notes.values())} if notes else row})
    return output


def annotate_records(pack, rows, policy=None):
    """Attach current, audience-filtered fact notes to unmodified source text."""
    return [r["memory"] for r in annotate_recalled(pack, [{"memory": row} for row in rows], policy)]


def prompt_lines(data):
    # Dependencies include omitted candidates so later withdrawal invalidates a
    # derived answer. The model needs visible evidence, not this bookkeeping.
    shown = {**data, "groups": [{**{k: v for k, v in g.items() if k != "retraction_dependencies"},
                                "temporal": {k: v for k, v in g.get("temporal", {}).items()
                                                 if k != "dependency_ids"}} for g in data.get("groups", [])]}
    return ("以下是有来源的单项说法，不代表客观核实。conflict 必须保留分歧并向用户核对，不能按新旧、次数或模型自信选边。"
            "reported 只代表当前保留的说法。修订只针对指定人物和事项，不否定同一段原文中的其他内容。"
            "retractions 表示用户指出模型提取有误；不得把已撤回提取当作当前或过去的事实，也不能自动推断相反命题为真。"
            "原话仍保留，要重读人物、否定、条件和转述关系。撤回理由是用户的纠错说明，不是独立核实。"
            "change 是后来变化，correction 是旧说法有误；没有变化日期就承认不知道。"
            "temporal 是按现有来源回查时间：recorded_at 只是保存时刻，starts_on 才是明确起日，until_on 当天已结束。"
            "回答指定日期只使用 temporal.on 对应结果：reported 仅表示登记时间线支持，conflict/uncertain/unknown 不得选一个值作结论。"
            "on_basis=single_literal_date_hint 只表示问题里出现一个完整日期，需判断它是否真是所问时间；不要把顺带提到的生日等当作查询目标。"
            "未记录结束不证明现实没有变化；空起日不能往过去外推，不能把当前 claims 或原文旁的当前核对标注套用到过去。"
            "省略部分候选时仍保留完整分歧状态；缺少日期请澄清，不能把保存日期当成生效日期。"
            "date_state=revised 表示日期有用户修订依据，原文可能仍带旧日期；time_revised 标注要求重新查看当前时间视图。"
            "date_state=unavailable 表示最新日期依据不可用，不能退回原文旧日期。日期修订不修改说法内容或核对选择。"
            "人物编号不同就不能合并；未列出的事项不能当作不存在。\n" + json.dumps(shown, ensure_ascii=False))


def protects_source(pack, row):
    """A model cannot resolve a facet conflict by replacing its whole source."""
    refs = {row.get("id"), row.get("event_id"), *row.get("event_ids", [])}
    source = str(row.get("source", ""))
    if "#" in source:
        refs.add(source.split("#", 1)[1])
    return any(ref["id"] in refs for claim in read(pack) if claim["kind"] == "claim" for ref in claim["evidence"])


@durable
def apply_proposals(pack, proposals, *, event, allowed_entities, runner, generation=None):
    """Only quotes from this incoming message; no assistant self-confirmation."""
    if not isinstance(proposals, list) or not event:
        return {"added": [], "rejected": 0}
    from .memory_state import MemoryPolicy
    policy = MemoryPolicy.load(pack)
    originals = {row["id"]: row for row in experience.read(pack)}
    original = originals.get(event.get("id"))
    if (original is None or original.get("kind") != "conversation" or not policy.allows(original)
            or original.get("metadata", {}).get("runner") or original.get("actor") in ("运行器", "runtime", "fish")):
        return {"added": [], "rejected": len(proposals)}
    entities, groups = _state(pack, policy)
    allowed = set(allowed_entities) & set(entities)
    added, rejected = [], 0
    for raw in proposals[:8]:
        try:
            if not isinstance(raw, dict) or not isinstance(raw.get("subject"), str) or raw["subject"] not in allowed:
                raise SeedError("事实提案的人物不明确。")
            aspect = _text(raw.get("aspect"), 60, "事项")
            value = _text(raw.get("value"), 240, "说法")
            quote = _text(raw.get("quote"), 800, "原文").replace("\r", " ").replace("\n", " ")
            if value not in quote or quote not in original["text"]:
                raise SeedError("事实提案没有逐字对应的输入原文。")
            starts_on = ""
            if "starts_on" in raw and raw["starts_on"] not in ("", None):
                from .fact_time import explicit_day, query_day
                starts_on = query_day(raw["starts_on"])
                if not starts_on or explicit_day(quote) != starts_on:
                    raise SeedError("生效起日必须逐字对应原句中的唯一完整日期。")
            slot = slot_id(raw["subject"], aspect)
            if any(row["slot"] == slot and row["value"] == value and any(ref["id"] == original["id"] for ref in row["evidence"])
                   for row in groups.get(slot, {}).get("history", []) + added):
                continue
        except SeedError:
            rejected += 1
            continue
        row = _append(pack, "claim", subject=raw["subject"], aspect=aspect, slot=slot,
                      value=value, quote=quote, origin="model", runner=runner,
                      **({"starts_on": starts_on} if starts_on else {}),
                      generation=_extraction_generation({"generation": generation, "evidence": [{"id": original["id"]}]}, originals),
                      evidence=[{"id": original["id"], "source": experience.source_of(original), "kind": "conversation"}])
        added.append(row)
    return {"added": added, "rejected": rejected + max(0, len(proposals) - 8)}


@serialized
def perform(pack, action, payload, *, request_id=""):
    """Explicit user edits are durable, retryable and never invoke a model."""
    if action == "retract":
        from .fact_retractions import perform as retract
        return retract(pack, payload, request_id=request_id)
    from .memory_state import effective_date
    if not isinstance(payload, dict):
        raise SeedError("事实修改需要 data 对象。")
    data = dict(payload)
    if action == "entity":
        data = {"label": _text(data.get("label"), 80, "人物名称")}
    elif action == "add":
        if "starts_on" in data and not isinstance(data["starts_on"], str):
            raise SeedError("生效起日需要 YYYY-MM-DD，不知道时请留空。")
        data = {"subject": _text(data.get("subject"), 100, "人物编号"),
                "aspect": _text(data.get("aspect"), 60, "事项"), "value": _text(data.get("value"), 240, "说法"),
                **({"starts_on": effective_date(data["starts_on"])} if data.get("starts_on") else {})}
    elif action in ("resolve", "forget"):
        if not isinstance(data.get("expected"), list) or not all(isinstance(v, str) for v in data["expected"]):
            raise SeedError("缺少当前说法编号，请刷新后再操作。")
        data = {"slot": _text(data.get("slot"), 100, "事项编号"),
                "expected": sorted(set(data["expected"])), "reason": _text(data.get("reason"), 500, "理由"),
                **({"selected": _text(data.get("selected"), 100, "采用的说法编号"),
                    "change_type": data.get("change_type", "correction"),
                    "effective_on": effective_date(data.get("effective_on", ""))} if action == "resolve" else {})}
        if action == "resolve" and (data["change_type"] not in ("correction", "change") or
                                      (data["effective_on"] and data["change_type"] != "change")):
            raise SeedError("请选择原来记错或后来改变；只有后来改变才填写变化日期。")
    else:
        raise SeedError("事实修改操作只能是 entity / add / resolve / forget / retract。")

    def validate():
        entities, groups = _state(pack)
        if action == "entity" and data["label"].casefold() in {label.casefold() for label in entities.values()}:
            raise SeedError("这个人物名称已存在；同名人物请补充不同的身份说明。")
        if action == "add" and data["subject"] not in entities:
            raise SeedError("这个人物编号不存在，请刷新后再试。")
        if action in ("resolve", "forget"):
            group = groups.get(data["slot"])
            if not group or group["expected"] != data["expected"] or not group["expected"]:
                raise SeedError("这些说法已改变或放下，请刷新后重新核对。")
            if action == "resolve" and (data["selected"] not in group["expected"] or len(group["expected"]) < 2):
                raise SeedError("请选择当前的一条说法，并至少有两条可核对的记录。")

    def apply():
        if action == "entity":
            return {"record": _append(pack, "entity", label=data["label"])}
        from .cognition import _latest_day
        entities, groups = _state(pack)
        text = (f"{entities[data['subject']]} · {data['aspect']}：{data['value']}" if action == "add" else data["reason"])
        if action == "add" and data.get("starts_on"):
            text += f"（用户报告生效起日：{data['starts_on']}；未独立核实）"
        event = experience.record(pack, kind="fact_input", text=text, day=_latest_day(pack)["day"],
                                  source="mind/experiences.jsonl", actor="用户",
                                  metadata={"runner": "user-fact-edit-v1", "action": action})
        ref = {"id": event["id"], "source": experience.source_of(event), "kind": "fact_input"}
        if action == "add":
            row = _append(pack, "claim", **data, slot=slot_id(data["subject"], data["aspect"]),
                          quote=text, origin="user", runner="user-fact-edit-v1", evidence=[ref])
        else:
            fields = {k: v for k, v in data.items() if k != "expected"}
            targets = data["expected"] if action == "resolve" else [r["id"] for r in groups[data["slot"]]["history"]]
            row = _append(pack, action, **fields, targets=targets, evidence=[ref])
        return {"record": row}

    return requests.run(pack, {"kind": "fact_edit", "action": action, "data": data}, apply,
                        request_id=request_id, validate=validate)
