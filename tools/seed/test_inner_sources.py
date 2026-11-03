"""User-run regressions for source-bound inner records; not agent-executed."""
from copy import deepcopy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import test_life_story as fixtures
from seedbank import backup, cognition, experience, inner, inner_sources
from seedbank.brain import RemoteBrain, _inner_lines
from seedbank.context_window import fit
from seedbank.memory_state import MemoryPolicy, revise_memory
from seedbank.util import append_memories, now_iso, write_file_atomic, write_json_atomic


GENERATION = {"runner": "inner-fixture", "model": "test-only", "fallback": False}


class InnerSourcesTest(unittest.TestCase):
    event = fixtures.LifeStoryTest.event
    data = fixtures.LifeStoryTest.data
    save = fixtures.LifeStoryTest.save

    def setUp(self):
        home = tempfile.TemporaryDirectory(prefix="seedbank-inner-home-")
        self.addCleanup(home.cleanup)
        environment = patch.dict(os.environ, {"HOME": home.name, "USERPROFILE": home.name, "SEEDBANK_LANG": "zh_CN"})
        environment.start()
        self.addCleanup(environment.stop)
        fixtures.LifeStoryTest.setUp(self)

    def memory(self, event):
        row = {"id": "memory-" + event["id"], "kind": "thought", "text": event["text"],
               "source": experience.source_of(event), "day": self.day["dayNo"], "at": now_iso(),
               "event_ids": [event["id"]], "tags": [], "importance": 0.5}
        append_memories(self.pack, [row])
        return row

    def narrate(self, text, *dependencies, generation=GENERATION):
        return inner.set_narrative(self.pack, text, day=self.day["dayNo"], generation=generation,
                                   depends_on=dependencies)["narrative"]

    def context(self):
        return cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)

    def test_user_model_and_template_origins_are_distinct(self):
        inner.add_dream(self.pack, 1, "用户补充的梦。")
        inner.add_dream(self.pack, 1, "模型生成的梦。", generation=GENERATION)
        inner.add_dream(self.pack, 1, "模板生成的梦。", generation={"runner": "stub-fixture"})
        shown = inner_sources.project(self.pack)
        self.assertEqual([r["origin"] for r in shown["dreams"]], ["user", "model", "template"])
        prompt = _inner_lines(self.context())
        self.assertIn("用户补充的梦", prompt)
        self.assertIn("模型生成的梦", prompt)
        self.assertNotIn("模板生成的梦", prompt)
        self.assertIn("不是亲历", prompt)

    def test_withdrawal_removes_only_related_inner_records(self):
        first, second = self.event("要放下的输入。"), self.event("独立的另一段输入。")
        memory = self.memory(first)
        bad = inner.add_dream(self.pack, 1, "有关的梦。", generation=GENERATION, depends_on=[first["id"]])
        good = inner.add_dream(self.pack, 1, "独立的梦。", generation=GENERATION, depends_on=[second["id"]])
        self.narrate("从独立经历形成的认识。", second["id"])
        before = inner.inner_path(self.pack).read_bytes()
        cognition.forget_memory(self.pack, memory["id"])
        shown = self.context()["inner"]
        self.assertEqual([r["event_id"] for r in shown["last_dreams"]], [good["event_id"]])
        self.assertEqual(shown["narrative"]["text"], "从独立经历形成的认识。")
        self.assertNotIn(bad["event_id"], json.dumps(shown))
        self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)

    def test_current_narrative_does_not_revert_when_its_source_is_withdrawn(self):
        source = self.event()
        memory = self.memory(source)
        first = self.narrate("早先的叙述。")
        second = self.narrate("后来形成的叙述。", source["id"])
        cognition.forget_memory(self.pack, memory["id"])
        self.assertFalse(self.context()["inner"]["narrative"]["text"])
        view = inner_sources.project(self.pack)
        self.assertEqual(view["narrative"]["availability"], "unavailable")
        self.assertEqual(view["narrative_history"][0]["event_id"], first["event_id"])
        self.assertEqual(inner.narrative(self.pack)["event_id"], second["event_id"])

    def test_legacy_read_preserves_bytes_and_new_write_preserves_old_narrative(self):
        legacy = {"format": "seedbank/inner@1", "dreams": [{"day": 1, "text": "来源不明的旧梦。", "at": "old"}],
                  "narrative": {"text": "旧自我叙述。", "updated_day": 1}}
        write_json_atomic(inner.inner_path(self.pack), legacy)
        before = inner.inner_path(self.pack).read_bytes()
        self.assertEqual(inner_sources.project(self.pack)["narrative"]["origin"], "legacy")
        self.assertNotIn("旧自我叙述", _inner_lines(self.context()))
        self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)
        self.narrate("新叙述。")
        saved = json.loads(inner.inner_path(self.pack).read_text(encoding="utf-8"))
        self.assertEqual(saved["format"], "seedbank/inner@2")
        self.assertEqual(saved["narrative_history"][0], legacy["narrative"])
        self.assertEqual(saved["dreams"], legacy["dreams"])

    def test_cache_edit_and_event_edit_are_not_used_as_current_understanding(self):
        entry = self.narrate("原来的叙述。")
        data = inner.load_inner(self.pack)
        data["narrative"]["text"] = "缓存后来被改写。"
        inner.save_inner(self.pack, data)
        self.assertEqual(inner_sources.project(self.pack)["narrative"]["availability"], "unavailable")
        data["narrative"] = entry
        inner.save_inner(self.pack, data)
        events = experience.read(self.pack)
        next(r for r in events if r["id"] == entry["event_id"])["text"] = "来源后来被改写。"
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in events))
        self.assertEqual(inner_sources.project(self.pack)["narrative"]["availability"], "unavailable")

    def test_missing_event_does_not_downgrade_to_trusted_legacy(self):
        self.narrate("缺少来源的叙述。")
        write_file_atomic(experience.path(self.pack), "")
        self.assertEqual(inner_sources.project(self.pack)["narrative"]["availability"], "unavailable")
        self.assertFalse(self.context()["inner"]["narrative"]["text"])

    def test_revised_memory_reaches_inner_prompt_without_rewriting_history(self):
        source = self.event("旧说法。")
        old = self.memory(source)
        derived = self.event("参考旧说法的想法。", depends_on=[old["id"]])
        self.narrate("当时形成的叙述。", derived["id"])
        before = inner.inner_path(self.pack).read_bytes()
        updated = revise_memory(self.pack, old["id"], "后来补充的新说法。", reason="明确更正",
            day=1, source="fixture", runner="user-memory-revision-v1")
        ctx = self.context()
        row = ctx["inner"]["narrative"]
        self.assertEqual(row["text"], "当时形成的叙述。")
        self.assertEqual(row["memory_updates"][0]["id"], updated["id"])
        self.assertIn(updated["id"], cognition._context_dependencies({"inner": ctx["inner"]}))
        self.assertIn("后来补充的新说法", _inner_lines(ctx))
        self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)

    def test_life_story_revision_reaches_inner_prompt_and_dependencies(self):
        source = self.event()
        old = self.save(source)
        self.narrate("当时对自己的理解。", old["event_id"])
        current = self.save(source, target=old["key"], expected=old["id"], interpretation="后来更愿意倾听。")
        ctx = self.context()
        note = ctx["inner"]["narrative"]["interpretation_updates"][0]
        self.assertEqual(note["current_id"], current["id"])
        self.assertIn(current["event_id"], cognition._context_dependencies({"inner": ctx["inner"]}))

    def test_supplied_inner_sources_propagate_to_later_outputs(self):
        source = self.event()
        memory = self.memory(source)
        first = self.narrate("第一次叙述。", source["id"])
        ctx = {"inner": self.context()["inner"]}
        dependencies = cognition._context_dependencies(ctx)
        self.assertIn(first["event_id"], dependencies)
        second = self.narrate("参考过第一次叙述的新想法。", *dependencies)
        cognition.forget_memory(self.pack, memory["id"])
        self.assertIn(second["event_id"], MemoryPolicy.load(self.pack).blocked)

    def test_fitted_inner_is_not_recorded_as_an_unseen_input(self):
        first = self.narrate("会被预算裁掉的叙述。")
        ctx = {"inner": self.context()["inner"]}
        before = deepcopy(ctx)
        brain = type("FixtureBrain", (), {"name": "inner-fixture"})()
        entry = cognition.save_inner_result(self.pack, ctx, {"text": "只看了本次输入。",
            "_used_inner": {}, "_generation": GENERATION}, brain, self.day, "narrative")
        event = next(r for r in experience.read(self.pack) if r["id"] == entry["event_id"])
        self.assertNotIn(first["event_id"], event["depends_on"])
        self.assertEqual(ctx, before)

    def test_budget_removes_whole_records_without_mutating_original_or_silence(self):
        ctx = {"inner": {"silence": {"on": True, "note": "安静"}, "narrative": {"text": "很长的叙述" * 1200,
            "event_id": "fixture-event", "memory_updates": [{"id": "revision", "text": "更新"}]}},
            "_cfg": {"input_budget": 2048}}
        before = deepcopy(ctx)
        _, fitted, info = fit(ctx, lambda supplied: {"system": _inner_lines(supplied), "user": "当前消息"})
        self.assertTrue(info["limited"])
        self.assertEqual(fitted["inner"]["narrative"], {})
        self.assertTrue(fitted["inner"]["silence"]["on"])
        self.assertEqual(cognition._context_dependencies({"inner": fitted["inner"]}), [])
        self.assertEqual(ctx, before)

    def test_remote_result_reports_inner_actually_sent_to_transport(self):
        self.narrate("实际提供的叙述。")
        ctx = self.context()
        ctx["_cfg"] = {"input_budget": 1000000, "model": "fixture"}
        captured = []
        def transport(config, system, user):
            captured.append(system)
            return json.dumps({"text": "收到这些资料后的叙述。"})
        result = RemoteBrain("openai-compatible", transport).narrative(ctx)
        self.assertEqual(result["_used_inner"], ctx["inner"])
        self.assertIn("实际提供的叙述", captured[0])

    def test_failed_cache_write_rolls_back_event_and_previous_history(self):
        self.narrate("已经保存的叙述。")
        before = (inner.inner_path(self.pack).read_bytes(), experience.path(self.pack).read_bytes())
        with patch("seedbank.inner.write_json_atomic", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                self.narrate("未能保存的新叙述。")
        self.assertEqual((inner.inner_path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()), before)

    def test_failed_dream_memory_rolls_back_source_and_cache(self):
        inner.add_dream(self.pack, 1, "已经保存的梦。")
        before = (inner.inner_path(self.pack).read_bytes(), experience.path(self.pack).read_bytes())
        brain = type("FixtureBrain", (), {"name": "inner-fixture"})()
        with patch("seedbank.cognition.append_memories", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                cognition.save_inner_result(self.pack, {}, {"dream": "未能完整保存的梦。", "_generation": GENERATION},
                                             brain, self.day, "dream")
        self.assertEqual((inner.inner_path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()), before)

    def test_private_inner_records_do_not_enter_visitor_context(self):
        self.narrate("只在私人范围里的叙述。")
        ctx = cognition.build_context(self.pack, 1, self.day["date"], audience_id="qq-group:123", use_semantic=False)
        self.assertEqual(ctx["inner"], {})
        self.assertNotIn("只在私人范围里的叙述", json.dumps(ctx, ensure_ascii=False))

    def test_backup_restores_current_and_previous_bound_versions(self):
        self.narrate("以前的叙述。")
        self.narrate("当前的叙述。")
        before = inner_sources.project(self.pack)
        saved = backup.create(self.pack)
        restored = self.pack.parent / "restored-inner.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(inner_sources.project(restored), before)


if __name__ == "__main__":
    unittest.main()
