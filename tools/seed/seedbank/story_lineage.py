"""Read-time links from old interpretations to their current visible versions.

An influence is not a contradiction, an obligation to change, or proof that a
later model adopted the newer interpretation. No historical record is edited.
"""
from . import life_story
from .memory_state import MemoryPolicy, dependencies

NOTE = "这条历史内容使用过后来修订的人生解释，不代表当前理解；请对照版本说明，不自动更改看法或目标。"


def references(row):
    refs = dependencies(row)
    refs.update(value for value in row.get("event_ids", []) if isinstance(value, str))
    for key in ("id", "event_id"):
        if isinstance(row.get(key), str) and row[key]:
            refs.add(row[key])
    source = str(row.get("source", "")).split("#", 1)
    if len(source) == 2 and source[1]:
        refs.add(source[1])
    return refs - {"current"}


class Lineage:
    def __init__(self, pack, policy=None):
        self.rows = life_story.read(pack)
        self.latest = {row["key"]: row for row in self.rows}
        prior = [row for row in self.rows if row["kind"] in life_story.KINDS and self.latest[row["key"]]["id"] != row["id"]]
        self.previous, self.nodes, self.cache, self.states = {}, {}, {}, {}
        self.order = {row["id"]: index for index, row in enumerate(self.rows)}
        if not prior:
            return
        self.policy = policy if policy is not None else MemoryPolicy.load(pack)
        self.nodes = life_story._nodes(pack, self.policy)
        for row in prior:
            if life_story._state(row, self.nodes, self.policy) != "available":
                continue
            current = self.latest[row["key"]]
            if row["key"] not in self.states:
                self.states[row["key"]] = life_story._state(current, self.nodes, self.policy)
            state = self.states[row["key"]]
            # A private later revision must not reveal even its existence to a
            # caller who is only entitled to the earlier public interpretation.
            if state != "available" and getattr(self.policy, "restricted", False):
                continue
            self.previous[row["event_id"]] = row

    def trace(self, seeds):
        cache_key = tuple(sorted(seeds))
        if cache_key in self.cache:
            return self.cache[cache_key]
        pending, seen, found = list(seeds), set(), {}
        while pending:
            identifier = pending.pop()
            if identifier in seen:
                continue
            seen.add(identifier)
            node = self.nodes.get(identifier)
            if not node or not self.policy.allows(node):
                continue
            if identifier in self.previous:
                row = self.previous[identifier]
                if row["key"] not in found or self.order[row["id"]] > self.order[found[row["key"]]["id"]]:
                    found[row["key"]] = row
            pending.extend(references(node) - seen)
        self.cache[cache_key] = found
        return found

    def annotate(self, row):
        result = {key: value for key, value in row.items() if key not in
                  ("interpretation_updates", "interpretation_update_count", "life_story_note")}
        if not self.previous:
            return result
        seeds = references(row)
        found = self.trace(seeds)
        if not found:
            return result
        direct = seeds | {identifier for seed in seeds for identifier in references(self.nodes.get(seed, {}))}
        ordered = sorted(found.values(), key=lambda old: self.order[self.latest[old["key"]]["id"]], reverse=True)
        updates = []
        for old in ordered[:3]:
            current = self.latest[old["key"]]
            item = {"key": old["key"], "previous_id": old["id"], "previous_event_id": old["event_id"],
                    "state": "current_unavailable", "dependency_ids": [old["event_id"]]}
            if self.states[old["key"]] == "available":
                item.update(state="revised", current_id=current["id"], current_event_id=current["event_id"],
                            origin=current["origin"], title=current["data"]["title"],
                            interpretation=current["data"]["interpretation"], change=current["data"]["change"],
                            question=current["data"]["question"], reason=current["reason"],
                            current_version_in_direct_sources=current["event_id"] in direct)
                item["dependency_ids"].append(current["event_id"])
            updates.append(item)
        return {**result, "life_story_note": NOTE, "interpretation_updates": updates,
                "interpretation_update_count": len(ordered)}

    def annotate_many(self, rows):
        return [self.annotate(row) for row in rows]


def context_dependencies(ctx):
    rows = list(ctx.get("evidence", [])) + list(ctx.get("transcript", []))
    rows += [item["memory"] for item in ctx.get("recalled", [])]
    for bucket in ("beliefs", "preferences", "goals"):
        rows += list(ctx.get("development", {}).get(bucket, []))
    return {identifier for row in rows for note in row.get("interpretation_updates", [])
            for identifier in note.get("dependency_ids", [])}


def display_lines(row):
    from .desktop.text import t
    result = []
    for note in row.get("interpretation_updates", []):
        if note["state"] == "current_unavailable":
            result.append(t("曾参考的人生理解已有修订，当前版本的依据尚不可用；旧理解仍是历史。"))
            continue
        result.append(t("曾参考的理解已有修订：{title}", title=note["title"]))
        result.append(t("现在的理解：{text}", text=note["interpretation"][:240]))
        if note["change"]:
            result.append(t("理解的变化：{text}", text=note["change"][:240]))
        if note["current_version_in_direct_sources"]:
            result.append(t("这条记录的直接来源也包含当前版本，不代表已经采纳或改变看法。"))
    if row.get("interpretation_update_count", 0) > len(row.get("interpretation_updates", [])):
        result.append(t("另有相关修订未在此展开，可到人生回顾查看。"))
    return result
