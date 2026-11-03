"""User-run interpretation lineage regressions. Authored, not executed."""
from copy import deepcopy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import test_life_story as fixtures
from seedbank import backup, cognition, development, disclosure, experience, life_story, story_lineage
from seedbank.brain import RemoteBrain
from seedbank.memory_state import MemoryPolicy, describe
from seedbank.util import append_memories, now_iso, write_file_atomic


class StoryLineageTest(unittest.TestCase):
    event = fixtures.LifeStoryTest.event
    data = fixtures.LifeStoryTest.data
    save = fixtures.LifeStoryTest.save

    def setUp(self):
        home = tempfile.TemporaryDirectory(prefix="seedbank-lineage-home-")
        self.addCleanup(home.cleanup)
        environment = patch.dict(os.environ, {"HOME": home.name, "USERPROFILE": home.name, "SEEDBANK_LANG": "zh_CN"})
        environment.start()
        self.addCleanup(environment.stop)
        fixtures.LifeStoryTest.setUp(self)

    def revised(self, *, title="学习表达", new_source=False):
        source = self.event()
        old = self.save(source, title=title)
        derived = self.event("引用旧理解的后续表达。", depends_on=[old["event_id"]])
        later = self.event("后来我学会先问对方的想法。") if new_source else source
        current = self.save(later, title=title, target=old["key"], expected=old["id"],
                            interpretation="现在我更重视先倾听。", change="由急于表达转为先理解。")
        return source, old, derived, current, later

    def grow(self, event):
        common = {"reason": "从实际交流形成的想法", "evidence": ["current"]}
        return development.apply_proposals(self.pack, {
            "beliefs": [{**common, "text": "我仍然愿意解释。", "confidence": 0.6}],
            "preferences": [{**common, "topic": "交流", "stance": "like"}],
            "goals": [{**common, "title": "练习表达", "status": "active", "next_step": "写一段具体想法"}],
        }, day=self.day["dayNo"], source=experience.source_of(event), runner="lineage-fixture",
            current_evidence=[{"id": event["id"], "source": experience.source_of(event)}],
            generation={"runner": "lineage-fixture", "model": "test-only", **disclosure.stamp("owner"),
                        "context_dependencies": [event["id"]]})

    def rewrite_experience(self, identifier, **changes):
        rows = experience.read(self.pack)
        for row in rows:
            if row["id"] == identifier:
                row.update(changes)
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))

    def contents(self):
        return {str(path.relative_to(self.pack)): path.read_bytes() for path in (self.pack / "mind").glob("*.jsonl")}

    def test_growth_annotations_preserve_beliefs_preferences_goals_and_ledgers(self):
        _, old, derived, current, _ = self.revised()
        self.assertEqual(len(self.grow(derived)), 3)
        before = self.contents()
        raw = development.current_state(self.pack)
        shown = development.summary(self.pack)
        for bucket in ("beliefs", "preferences", "goals"):
            row = shown[bucket][0]
            note = row["interpretation_updates"][0]
            self.assertEqual(note["previous_id"], old["id"])
            self.assertEqual(note["current_id"], current["id"])
            self.assertEqual(note["origin"], "user")
            self.assertNotIn("interpretation_updates", raw[bucket][row["id"]])
        self.assertEqual(shown["goals"][0]["status"], "active")
        self.assertEqual(shown["beliefs"][0]["text"], "我仍然愿意解释。")
        self.assertEqual(self.contents(), before)

    def test_memory_event_ids_and_fragment_sources_keep_revision_links(self):
        _, _, derived, current, _ = self.revised()
        lineage = story_lineage.Lineage(self.pack)
        for refs in ({"event_ids": [derived["id"]]}, {"source": experience.source_of(derived)}):
            with self.subTest(refs=refs):
                row = lineage.annotate({"id": "memory-fixture", "text": "当时的想法", **refs})
                self.assertEqual(row["interpretation_updates"][0]["current_id"], current["id"])
                self.assertIn(current["data"]["interpretation"], describe(row))

    def test_recent_memory_fallback_does_not_erase_retrieval_annotation(self):
        _, _, derived, current, _ = self.revised()
        memory = {"id": "lineage-memory", "kind": "conversation", "text": "当时的表达", "day": self.day["dayNo"],
                  "source": experience.source_of(derived), "event_ids": [derived["id"]], "at": now_iso()}
        append_memories(self.pack, [memory])
        annotated = story_lineage.Lineage(self.pack).annotate(memory)
        rows = cognition._evidence_memories(self.pack, recalled=[{"memory": annotated}])
        selected = next(row for row in rows if row["id"] == memory["id"])
        self.assertEqual(selected["interpretation_updates"][0]["current_id"], current["id"])

    def test_current_source_is_not_an_automatic_change_of_belief(self):
        _, _, derived, current, _ = self.revised()
        later = self.event("我还需要想一想。", depends_on=[derived["id"], current["event_id"]])
        self.grow(later)
        belief = development.summary(self.pack)["beliefs"][0]
        note = belief["interpretation_updates"][0]
        self.assertTrue(note["current_version_in_direct_sources"])
        self.assertEqual(belief["text"], "我仍然愿意解释。")
        self.assertTrue(any("不代表已经采纳" in line for line in story_lineage.display_lines(belief)))

    def test_changed_latest_anchor_has_no_current_content_or_old_version_revival(self):
        _, old, derived, current, later = self.revised(new_source=True)
        self.rewrite_experience(later["id"], text="这段来源被外部改写。")
        note = story_lineage.Lineage(self.pack).annotate(derived)["interpretation_updates"][0]
        self.assertEqual(note["state"], "current_unavailable")
        self.assertEqual(note["dependency_ids"], [old["event_id"]])
        self.assertNotIn("interpretation", note)
        self.assertNotIn(current["id"], json.dumps(note))
        self.assertEqual(life_story.context(self.pack)["chapters"], [])

    def test_external_reader_cannot_detect_private_later_revision(self):
        scope = "qq-group:123"
        source = self.event("这是群里的交流。", metadata=disclosure.stamp(scope))
        old = life_story.apply_proposals(self.pack, [self.data(source)],
            ctx={"_audience_id": scope, "evidence": [source]},
            generation={"runner": "lineage-fixture", "model": "test-only", **disclosure.stamp(scope)})[0]
        derived = self.event("群里的旧理解", depends_on=[old["event_id"]], metadata=disclosure.stamp(scope))
        self.save(source, target=old["key"], expected=old["id"], title="PRIVATE_REVISION_TITLE",
                  interpretation="PRIVATE_REVISION_TEXT")
        policy = disclosure.policy_for(self.pack, scope)
        self.assertTrue(policy.allows(derived))
        shown = story_lineage.Lineage(self.pack, policy).annotate(derived)
        self.assertNotIn("interpretation_updates", shown)
        self.assertNotIn("life_story_note", shown)
        self.assertNotIn("PRIVATE_REVISION", json.dumps(shown))

    def test_forgotten_interpretation_retires_dependents_and_keeps_original_input(self):
        source, old, derived, current, _ = self.revised()
        self.grow(derived)
        life_story.perform(self.pack, "forget", {"target": old["key"], "expected": current["id"], "reason": "放下这条解释"})
        self.assertTrue(MemoryPolicy.load(self.pack).allows(source))
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertEqual(development.current_state(self.pack)["beliefs"], {})
        self.assertNotIn("interpretation_updates", story_lineage.Lineage(self.pack).annotate(derived))

    def test_transitive_and_cyclic_sources_terminate_without_linking_unrelated_rows(self):
        _, _, derived, current, _ = self.revised()
        first = derived
        for index in range(40):
            derived = self.event("后续表达 " + str(index), depends_on=[derived["id"]])
        self.rewrite_experience(first["id"], depends_on=first["depends_on"] + [derived["id"]])
        lineage = story_lineage.Lineage(self.pack)
        self.assertEqual(lineage.annotate(derived)["interpretation_updates"][0]["current_id"], current["id"])
        unrelated = self.event("一件独立的事情。")
        self.assertNotIn("interpretation_updates", lineage.annotate(unrelated))

    def test_bounded_notes_report_total_and_only_link_displayed_versions(self):
        rows = [self.revised(title="章节 " + str(index)) for index in range(4)]
        combined = self.event("整理这些想法。", depends_on=[row[2]["id"] for row in rows])
        shown = story_lineage.Lineage(self.pack).annotate(combined)
        notes = shown["interpretation_updates"]
        self.assertEqual(len(notes), 3)
        self.assertEqual(shown["interpretation_update_count"], 4)
        refs = story_lineage.context_dependencies({"evidence": [shown]})
        self.assertEqual(refs, {identifier for note in notes for identifier in note["dependency_ids"]})
        self.assertNotIn(rows[0][3]["event_id"], refs)

    def test_next_read_uses_latest_revision_and_discards_stale_annotations(self):
        source, _, derived, current, _ = self.revised()
        shown = story_lineage.Lineage(self.pack).annotate(derived)
        latest = self.save(source, target=current["key"], expected=current["id"], interpretation="后来我又有了不同的理解。")
        next_read = story_lineage.Lineage(self.pack).annotate(shown)
        self.assertEqual(next_read["interpretation_updates"][0]["current_id"], latest["id"])
        unrelated = self.event("没有引用那些经历。")
        unrelated["interpretation_updates"] = shown["interpretation_updates"]
        unrelated["life_story_note"] = "stale"
        self.assertNotIn("interpretation_updates", story_lineage.Lineage(self.pack).annotate(unrelated))

    def test_chat_links_actual_transcript_note_but_not_trimmed_note(self):
        _, old, _, current, _ = self.revised()
        cognition.append_transcript(self.pack, self.day, [{"who": "fish", "text": "当时我更急于表达。",
                                                        "depends_on": [old["event_id"]]}])
        owner = self

        class Brain:
            name = "stub-lineage-fixture"
            trim = False

            def chat(inner, ctx):
                owner.assertTrue(any(row.get("interpretation_updates") for row in ctx["transcript"]))
                used = {"_used_evidence": [], "_used_recalled": [], "_used_development": {}, "_used_life_story": {},
                        "_used_learning": [], "_used_facts": {}, "_used_relationships": {}, "_used_practice": {}}
                return {"reply": "trimmed" if inner.trim else "shown", **used,
                        "_used_transcript": [] if inner.trim else ctx["transcript"]}

        brain = Brain()
        cognition.chat_turn(self.pack, "继续聊聊表达。", brain)
        shown = next(row for row in experience.read(self.pack) if row["text"] == "shown")
        self.assertIn(current["event_id"], shown["depends_on"])
        brain.trim = True
        cognition.chat_turn(self.pack, "现在只讨论这条新消息。", brain)
        trimmed = next(row for row in experience.read(self.pack) if row["text"] == "trimmed")
        self.assertNotIn(current["event_id"], trimmed["depends_on"])
        life_story.perform(self.pack, "forget", {"target": old["key"], "expected": current["id"], "reason": "放下解释"})
        policy = MemoryPolicy.load(self.pack)
        self.assertFalse(policy.allows(shown))
        self.assertTrue(policy.allows(trimmed))

    def test_inner_source_tracking_uses_fitted_context_without_mutating_shared_context(self):
        _, _, derived, current, _ = self.revised()
        ctx = {"name": "初", "evidence": [story_lineage.Lineage(self.pack).annotate(derived)], "inner_activity": "dream"}
        before = deepcopy(ctx)

        class Brain:
            name = "lineage-fixture"

            def dream(inner, supplied):
                return {"dream": "一个没有引用旧解释的梦。", "_used_evidence": [],
                        "_generation": {"runner": "lineage-fixture", "model": "test-only"}}

            def narrative(inner, supplied):
                return {"text": "只描述眼前的一段叙事。", "_used_evidence": [],
                        "_generation": {"runner": "lineage-fixture", "model": "test-only"}}

        cognition._maybe_inner(self.pack, ctx, Brain(), self.day, now_iso())
        self.assertEqual(ctx, before)
        ctx["inner_activity"] = "narrate"
        cognition._maybe_inner(self.pack, ctx, Brain(), self.day, now_iso())
        generated = [row for row in experience.read(self.pack)
                     if row["kind"] == "dream" or row.get("metadata", {}).get("activity") == "narrative"]
        self.assertEqual(len(generated), 2)
        self.assertTrue(all(current["event_id"] not in row["depends_on"] for row in generated))

    def test_fallback_stub_runtime_and_missing_model_cannot_create_life_chapters(self):
        source = self.event()
        base = {"runner": "lineage-fixture", "model": "test-only", **disclosure.stamp("owner")}
        before = self.contents()
        for changes in ({"fallback": True}, {"runtime_guard": True}, {"runner": "stub-fixture"},
                        {"runner": "runtime"}, {"runner": ""}, {"model": None}, {"model": " "}):
            with self.subTest(changes=changes):
                result = life_story.apply_proposals(self.pack, [self.data(source)], ctx={"evidence": [source]},
                                                   generation={**base, **changes})
                self.assertEqual(result, [])
                self.assertEqual(self.contents(), before)
        self.assertEqual(len(life_story.apply_proposals(self.pack, [self.data(source)],
                             ctx={"evidence": [source]}, generation=base)), 1)

    def test_recalled_sources_and_notes_follow_the_same_context_budget(self):
        _, _, derived, current, _ = self.revised()
        row = story_lineage.Lineage(self.pack).annotate(derived)
        ctx = {"recalled": [{"memory": row}], "current_evidence": [{"id": derived["id"]}],
               "transcript": [{"event_id": derived["id"]}]}
        self.assertIn(current["event_id"], cognition._context_dependencies(ctx))
        cognition._use_supplied_context(ctx, {"_used_recalled": [], "_used_transcript": []})
        self.assertNotIn(current["event_id"], cognition._context_dependencies(ctx))
        self.assertNotIn(derived["id"], cognition._context_dependencies(ctx))
        self.assertEqual(ctx["current_evidence"], [])

    def test_backup_restore_preserves_links_without_new_lineage_ledger(self):
        _, _, derived, _, _ = self.revised()
        self.grow(derived)
        before = self.contents()
        shown = development.summary(self.pack)
        saved = backup.create(self.pack)
        restored = self.pack.parent / "lineage-restored.life"
        backup.restore(saved["file"], restored)
        for bucket in ("beliefs", "preferences", "goals"):
            self.assertEqual(development.summary(restored)[bucket], shown[bucket])
        self.assertEqual(self.contents(), before)
        self.assertFalse((restored / "mind" / "story_lineage.jsonl").exists())

    def test_prompt_builder_reports_only_source_channels_it_renders(self):
        _, _, derived, current, _ = self.revised()
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        row = story_lineage.Lineage(self.pack).annotate(derived)
        ctx.update(evidence=[row], recalled=[{"memory": row}], transcript=[{"who": "fish", "text": row["text"], **row}],
                   development={}, life_story={}, _cfg={"input_budget": 1000000, "model": "test-only"})
        before = deepcopy(ctx)
        captured = []

        def transport(cfg, system, user):
            captured.append(system + user)
            return json.dumps({"dream": "一个单纯的梦。", "text": "我还在慢慢认识自己。", "title": "此刻",
                               "diary": "今天安静地过去了。", "mood": ctx["moods"][0]})

        brain = RemoteBrain("lineage-fixture", transport)
        for method in (brain.dream, brain.narrative, brain.compose):
            with self.subTest(method=method.__name__):
                result = method(ctx)
                self.assertFalse(result["_generation"]["fallback"])
                self.assertEqual(result["_used_evidence"], [])
                self.assertEqual(result["_used_recalled"], [])
                self.assertEqual(result["_used_transcript"], [])
                self.assertNotIn(current["id"], captured[-1])
        diary = brain.diary(ctx)
        self.assertEqual(diary["_used_recalled"], [])
        self.assertEqual(diary["_used_evidence"], [row])
        self.assertIn(current["id"], captured[-1])
        self.assertEqual(ctx, before)


if __name__ == "__main__":
    unittest.main()
