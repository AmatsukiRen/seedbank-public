"""User-run regressions for long-history policy reads. Authored, not run."""
from copy import deepcopy
from pathlib import Path
import json
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_learning_observations as fixtures
from seedbank import (development, disclosure, experience, fact_dates, facts, learning,
                      learning_observations, learning_strategies, life_story, media_archive,
                      memory_state, relationships, util, works)
from seedbank.durability import operation
from seedbank.memory_sources import PolicySources
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.pack_lock import writer

ROOT = Path(__file__).resolve().parents[2]


def previous_suppression(rows, seeds):
    """Pre-change fixed-point rules, retained as an independent small oracle."""
    blocked, direct = set(seeds), set(seeds)
    while True:
        previous = set(blocked), set(direct)
        for row in rows:
            identifier, parent = str(row.get("id") or ""), str(row.get("supersedes") or "")
            if parent and (parent in blocked or identifier in blocked):
                blocked.update((identifier, parent))
            if parent and (parent in direct or identifier in direct):
                direct.update((identifier, parent))
            if identifier in direct:
                direct.update(str(ref) for ref in row.get("event_ids", []))
                parts = str(row.get("source", "")).split("#", 1)
                if len(parts) == 2:
                    direct.add(parts[1])
            blocked.update(direct)
            if memory_state.dependencies(row) & blocked:
                blocked.add(identifier)
        if previous == (blocked, direct):
            return blocked


class MemoryPolicyGraphTest(unittest.TestCase):
    def test_reverse_order_long_chain_does_not_rescan_every_dependency(self):
        count = 5000
        events = [{"id": f"x_{n}", "depends_on": [f"x_{n - 1}"] if n else [],
                   "source": "life/0001-2026-11-01.md"} for n in reversed(range(count))]
        with patch.object(memory_state, "dependencies", wraps=memory_state.dependencies) as dependency_reads:
            policy = MemoryPolicy([], iter(events), extra_blocked={"x_0"})
        self.assertEqual(policy.blocked, {f"x_{n}" for n in range(count)})
        self.assertEqual(policy.affected_sources, {"life/0001-2026-11-01.md"})
        self.assertLessEqual(dependency_reads.call_count, count * 2)

    def test_derived_loss_does_not_withdraw_independent_source_but_direct_withdrawal_does(self):
        rows = [{"id": "derived", "depends_on": ["lost"], "event_ids": ["independent"],
                 "source": "life/day.md#independent"},
                {"id": "revised", "supersedes": "derived", "event_ids": ["second_source"]},
                {"id": "sibling", "depends_on": ["independent"]}]
        indirect = MemoryPolicy(rows, extra_blocked={"lost"})
        self.assertEqual(indirect.blocked, {"lost", "derived", "revised"})
        self.assertTrue(indirect.allows_source("life/day.md#independent"))
        direct = MemoryPolicy([*rows, {"id": "withdrawal", "kind": "forget", "forgets": "derived"}])
        self.assertEqual(direct.blocked, {"derived", "revised", "independent", "second_source", "sibling"})
        self.assertFalse(direct.allows_source("life/day.md#independent"))

    def test_cycle_missing_node_all_dependency_kinds_and_legacy_day_mask(self):
        records = [{"id": "a", "supersedes": "b", "source": "life/old.md"},
                   {"id": "b", "supersedes": "a", "depends_on": ["missing"]},
                   {"id": "c", "generation": {"context_dependencies": ["a"]}},
                   {"id": "d", "evidence": [{"id": "c", "source": "somewhere"}]},
                   {"id": "e", "metadata": {"context_dependencies": ["d"]}},
                   {"id": "f", "depends_on": ["e", "f"]}, {"id": "untouched"}]
        policy = MemoryPolicy(records, extra_blocked={"missing"})
        self.assertEqual(policy.blocked, {"missing", "a", "b", "c", "d", "e", "f"})
        self.assertFalse(policy.allows_source("life/old.md"))
        self.assertFalse(policy.allows(records[2], historical=True))
        self.assertFalse(policy.allows_generation({"context_dependencies": ["f"]}))
        self.assertEqual(policy.supports([{"id": "f"}, {"id": "untouched"}]), [{"id": "untouched"}])

    def test_small_mixed_graphs_match_previous_rules_without_mutating_rows(self):
        for seed in range(40):
            rng = random.Random(seed)
            identifiers = [f"n_{n}" for n in range(24)]
            choices = [*identifiers, "missing"]
            rows = []
            for identifier in identifiers:
                row = {"id": identifier, "depends_on": rng.sample(choices, rng.randrange(3)),
                       "event_ids": rng.sample(choices, rng.randrange(3)),
                       "evidence": [{"id": rng.choice(choices)}] if rng.randrange(2) else []}
                if rng.randrange(3) == 0:
                    row["supersedes"] = rng.choice(choices)
                if rng.randrange(3) == 0:
                    row["source"] = "life/day.md#" + rng.choice(choices)
                row[rng.choice(["metadata", "generation"])] = {"context_dependencies": [rng.choice(choices)]}
                rows.append(row)
            rng.shuffle(rows)
            seeds = set(rng.sample(choices, rng.randrange(4)))
            before = deepcopy(rows)
            with self.subTest(seed=seed):
                policy = MemoryPolicy(rows[:12], rows[12:], seeds)
                self.assertEqual(policy.blocked, previous_suppression(rows, seeds))
                self.assertEqual(rows, before)


class MemoryPolicyLoadingTest(unittest.TestCase):
    setUp = fixtures.LearningObservationsTest.setUp
    plan = fixtures.LearningObservationsTest.plan
    practice = fixtures.LearningObservationsTest.practice
    listing = fixtures.LearningObservationsTest.listing
    review = fixtures.LearningObservationsTest.review
    source = fixtures.LearningObservationsTest.source
    data = fixtures.LearningObservationsTest.data
    strategy = fixtures.LearningObservationsTest.strategy
    next_goal = fixtures.LearningObservationsTest.next_goal
    prepare = fixtures.LearningObservationsTest.prepare
    observation = fixtures.LearningObservationsTest.observation
    observe = fixtures.LearningObservationsTest.observe

    def mixed_history(self):
        strategy, goal, outcome = self.prepare()
        self.observe(strategy, goal, outcome)
        event = experience.record(self.pack, kind="conversation", text="我不喜欢咖啡。", day=1,
                                  source=self.day["file"], actor="user", metadata=disclosure.stamp("owner"))
        life_story.perform(self.pack, "save", {"kind": "chapter", "title": "表达偏好", "interpretation": "尝试说清楚偏好。",
            "change": "", "question": "", "status": "open", "reason": "依据原话", "target": "", "expected": "",
            "anchors": [{"id": event["id"], "quote": event["text"], "hash": life_story._digest(event)}]})
        media_archive.capture(self.pack, ROOT / "tools/seed/testdata/bright-warm.png", kind="image", day=1,
                              source=self.day["file"], audience_id="owner", person_id="owner")
        old, new = [facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": value})["record"]
                    for value in ("杭州", "成都")]
        timing = fact_dates.detail(self.pack, old["id"])
        fact_dates.perform(self.pack, {"target": old["id"], "target_hash": timing["target_hash"],
            "expected": timing["expected"], "date": "2020-01-01", "reason": "核对起日"})
        group = next(r for r in facts.listing(self.pack)["groups"] if r["id"] == new["slot"])
        facts.perform(self.pack, "resolve", {"slot": group["id"], "expected": group["expected"],
            "selected": new["id"], "change_type": "correction", "reason": "原来记错"})
        claim = facts.apply_proposals(self.pack, [{"subject": "owner", "aspect": "饮食偏好", "value": "咖啡",
            "quote": event["text"]}], event=event, allowed_entities=["owner"], runner="fixture")["added"][0]
        group = next(r for r in facts.listing(self.pack)["groups"] if r["id"] == claim["slot"])
        shown = next(r for r in group["claims"] if r["id"] == claim["id"])
        facts.perform(self.pack, "retract", {"slot": group["id"], "expected": group["expected"],
            "target": claim["id"], "target_hash": shown["target_hash"], "reason": "漏掉否定"})

    def test_one_policy_reads_each_shared_ledger_once_and_matches_independent_folds(self):
        self.mixed_history()
        paths = [experience.path(self.pack), facts.path(self.pack), learning.path(self.pack),
                 life_story.path(self.pack), media_archive.path(self.pack), self.pack / "mind/development.jsonl"]
        before = {path: path.read_bytes() for path in paths}
        with patch.object(util, "read_memories", wraps=util.read_memories) as memories, \
                patch.object(experience, "read", wraps=experience.read) as events, \
                patch.object(learning, "read", wraps=learning.read) as lessons, \
                patch.object(development, "events", wraps=development.events) as growth:
            policy = MemoryPolicy.load(self.pack)
        self.assertEqual([memories.call_count, events.call_count, lessons.call_count, growth.call_count], [1, 1, 1, 1])
        suppressed = (facts.suppressed_ids(self.pack) | relationships.suppressed_ids(self.pack)
            | life_story.suppressed_ids(self.pack) | media_archive.suppressed_ids(self.pack)
            | learning_strategies.suppressed(self.pack) | learning_observations.suppressed(self.pack))
        expected = MemoryPolicy(util.read_memories(self.pack), experience.read(self.pack), suppressed)
        self.assertEqual(policy.blocked, expected.blocked)
        self.assertEqual(policy.visible(), expected.visible())
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_shared_source_inputs_are_not_mutated_by_suppression_folds(self):
        self.mixed_history()
        sources = PolicySources(self.pack)
        values = (sources.memories, sources.experiences, sources.learning, sources.outcomes)
        before = deepcopy(values)
        for fold in (facts.suppressed_ids, life_story.suppressed_ids, media_archive.suppressed_ids,
                     learning_strategies.suppressed, learning_observations.suppressed):
            fold(self.pack, sources=sources)
        self.assertEqual(values, before)

    def test_source_replacement_is_seen_by_next_load_and_restoration(self):
        strategy, goal, outcome = self.prepare()
        self.observe(strategy, goal, outcome)
        identifier = strategy["source"].split("#", 1)[1]
        self.assertNotIn(identifier, MemoryPolicy.load(self.pack).blocked)
        file = experience.path(self.pack)
        before = file.read_bytes()
        rows = experience.read(self.pack)
        next(r for r in rows if r["id"] == identifier)["text"] += " changed fixture input"
        util.write_file_atomic(file, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        self.assertIn(identifier, MemoryPolicy.load(self.pack).blocked)
        file.write_bytes(before)
        self.assertNotIn(identifier, MemoryPolicy.load(self.pack).blocked)

    def test_append_then_transaction_rollback_does_not_leave_stale_policy(self):
        event = experience.record(self.pack, kind="conversation", text="保留原始输入", day=1,
                                  source=self.day["file"], actor="user")
        self.assertTrue(MemoryPolicy.load(self.pack).allows(event))
        with self.assertRaisesRegex(RuntimeError, "fixture interruption"):
            with writer(self.pack), operation(self.pack, "policy read rollback"):
                util.append_memories(self.pack, [{"id": "fixture-forget", "kind": "forget", "forgets": event["id"]}])
                self.assertFalse(MemoryPolicy.load(self.pack).allows(event))
                raise RuntimeError("fixture interruption")
        self.assertTrue(MemoryPolicy.load(self.pack).allows(event))

    def test_changed_work_still_retires_its_observation_and_derived_reply(self):
        strategy, goal, outcome = self.prepare()
        review = self.observe(strategy, goal, outcome)
        source = review["source"].split("#", 1)[1]
        reply = experience.record(self.pack, kind="conversation", text="基于旧反馈的回答", day=1,
            source=self.day["file"], metadata={"context_dependencies": [source]})
        self.assertTrue(MemoryPolicy.load(self.pack).allows(reply))
        artifact = learning.view(self.pack)["outcomes"][outcome]["artifact"].split("#", 1)[1]
        document = works.load_works(self.pack)
        next(r for r in document["works"] if r["id"] == artifact)["text"] = "用户更改了这份作品"
        util.write_json_atomic(self.pack / "mind/works.json", document)
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(source, policy.blocked)
        self.assertFalse(policy.allows(reply))
        self.assertNotIn(strategy["source"].split("#", 1)[1], policy.blocked)

    def test_missing_original_media_is_rechecked_on_next_policy_load(self):
        receipt, file, event = media_archive.capture(self.pack, ROOT / "tools/seed/testdata/bright-warm.png",
            kind="image", day=1, source=self.day["file"], audience_id="owner", person_id="owner")
        self.assertTrue(MemoryPolicy.load(self.pack).allows(event))
        file.unlink()  # Isolated fixture copy only; never a user asset.
        self.assertIn(receipt["event_id"], MemoryPolicy.load(self.pack).blocked)
        self.assertIn(receipt["event_id"], {r["id"] for r in experience.read(self.pack)})

    def test_mutating_returned_policy_does_not_poison_next_load_or_other_pack(self):
        util.append_memories(self.pack, [{"id": "same-id", "kind": "note", "text": "独立来源"}])
        first = MemoryPolicy.load(self.pack)
        first.by_id["same-id"]["text"] = "not persisted"
        util.append_memories(self.pack, [{"id": "withdraw", "kind": "forget", "forgets": "same-id"}])
        self.assertIn("same-id", MemoryPolicy.load(self.pack).blocked)
        other = self.pack.parent / "other.life"
        hatch(other, ROOT / "eggs/open.egg", "另一个", seed_override="separate-policy",
              born_at_override="2026-11-01T00:00:00Z")
        util.append_memories(other, [{"id": "same-id", "kind": "note", "text": "另一个来源"}])
        self.assertEqual(MemoryPolicy.load(other).by_id["same-id"]["text"], "另一个来源")
        self.assertNotIn("same-id", MemoryPolicy.load(other).blocked)
        self.assertEqual(MemoryPolicy.load(self.pack).by_id["same-id"]["text"], "独立来源")

    def test_broken_shared_ledgers_are_rejected_without_changing_bytes(self):
        self.mixed_history()
        for file in (experience.path(self.pack), learning.path(self.pack), self.pack / "mind/development.jsonl"):
            before = file.read_bytes()
            broken = before + b'{"incomplete":'
            try:
                file.write_bytes(broken)
                with self.subTest(file=file.name), self.assertRaises(util.SeedError):
                    MemoryPolicy.load(self.pack)
                self.assertEqual(file.read_bytes(), broken)
            finally:
                file.write_bytes(before)

    def test_desktop_snapshot_builds_one_policy_for_consistent_projections(self):
        from seedbank.cognition import list_memories
        from seedbank.desktop.session import Session
        from seedbank.inner_sources import project
        self.mixed_history()
        session = Session(self.pack, "stub")
        self.addCleanup(session.close)
        day = util.list_days(self.pack)[-1]["day"]
        expected_memories = list_memories(self.pack)
        expected_inner = project(self.pack)
        expected_development = development.summary(self.pack, day=day)
        with patch.object(MemoryPolicy, "load", wraps=MemoryPolicy.load) as loads, \
                patch.object(development, "events", wraps=development.events) as growth_reads:
            snapshot = session.snapshot()
        self.assertEqual(snapshot["memories"], expected_memories)
        self.assertEqual(snapshot["states"]["inner"], expected_inner)
        self.assertEqual(snapshot["states"]["development"], expected_development)
        self.assertEqual(loads.call_count, 1, "One locked snapshot should not repeat the full source fold")
        self.assertEqual(growth_reads.call_count, 1, "One snapshot should copy the full growth archive only once")

    def test_context_shares_growth_and_preserves_goals_feedback_and_provenance(self):
        from seedbank.cognition import build_context
        self.mixed_history()
        day = util.list_days(self.pack)[-1]
        expected_development = development.summary(self.pack, day=day["day"])
        expected_learning = learning.context(self.pack)
        with patch.object(development, "events", wraps=development.events) as growth_reads:
            context = build_context(self.pack, day["day"], day["date"], "整理材料", use_semantic=False)
        self.assertEqual(context["development"], expected_development)
        self.assertEqual(context["learning"], expected_learning)
        self.assertEqual(growth_reads.call_count, 2, "First index build performs its own validated archive read")
        with patch.object(development, "events", wraps=development.events) as growth_reads:
            repeated = build_context(self.pack, day["day"], day["date"], "整理材料", use_semantic=False)
        self.assertEqual(repeated["development"], expected_development)
        self.assertEqual(repeated["learning"], expected_learning)
        self.assertEqual(growth_reads.call_count, 1, "Recall, growth and feedback must share one read in this context")

    def test_desktop_snapshot_refreshes_after_withdrawal_rollback_and_caller_mutation(self):
        from seedbank.desktop.session import Session
        event = experience.record(self.pack, kind="hearsay", text="人工夹具保留原始来源", day=1,
                                  source=self.day["file"], actor="fixture")
        util.append_memories(self.pack, [{"id": "snapshot-memory", "kind": "hearsay", "day": 1,
            "text": "人工夹具保留原始来源", "source": experience.source_of(event),
            "event_ids": [event["id"]], "tags": ["人工夹具"]}])
        session = Session(self.pack, "stub")
        self.addCleanup(session.close)

        def row():
            return next(item for item in session.snapshot()["memories"] if item["id"] == "snapshot-memory")

        first = row()
        self.assertTrue(first["recallable"])
        first["tags"].append("not persisted")
        self.assertEqual(row()["tags"], ["人工夹具"])
        with self.assertRaisesRegex(RuntimeError, "snapshot rollback"):
            with writer(self.pack), operation(self.pack, "snapshot visibility rollback"):
                util.append_memories(self.pack, [{"id": "snapshot-withdrawal", "kind": "forget",
                                                  "forgets": "snapshot-memory"}])
                self.assertFalse(row()["recallable"])
                raise RuntimeError("snapshot rollback")
        self.assertTrue(row()["recallable"])
        util.append_memories(self.pack, [{"id": "snapshot-withdrawal-committed", "kind": "forget",
                                          "forgets": "snapshot-memory"}])
        self.assertFalse(row()["recallable"])


if __name__ == "__main__":
    unittest.main()
