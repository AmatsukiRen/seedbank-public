"""User-run life reflection regressions; authored, not executed by the agent."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import clock, disclosure, experience, life_story, persona, requests
from seedbank.brain import build_chat_prompt, create_stub_brain
from seedbank.bridge import Bridge
from seedbank.cognition import build_context, chat_turn, maybe_initiate, open_day, read_transcript, start_day
from seedbank.memory_state import MemoryPolicy, describe
from seedbank.pack import hatch, check
from seedbank.retrieval import search
from seedbank.timeline import render_timeline
from seedbank.util import SeedError, append_memories, list_days, read_text, write_file_atomic, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class LifeStoryTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-life-story-")
        self.addCleanup(folder.cleanup)
        self.pack = Path(folder.name) / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="story-fixture",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No network"))
        guard.start()
        self.addCleanup(guard.stop)

    def event(self, text="我今天尝试解释自己的想法。", **kwargs):
        return experience.record(self.pack, kind=kwargs.pop("kind", "conversation"), text=text,
                                 day=self.day["dayNo"], source=self.day["file"], actor="user", **kwargs)

    def data(self, event, **changes):
        return {"kind": "chapter", "title": "学习表达", "interpretation": "这次交流让我开始重视说清楚想法。",
                "change": "开始尝试解释。", "question": "怎样理解没有说出口的部分？", "status": "open",
                "reason": "结合本次实际记录整理", "target": "", "expected": "",
                "anchors": [{"id": event["id"], "quote": event["text"], "hash": life_story._digest(event)}], **changes}

    def save(self, event, **changes):
        return life_story.perform(self.pack, "save", self.data(event, **changes))["record"]

    def test_current_and_explicit_history_preserve_original_experience(self):
        original = self.event()
        first = self.save(original)
        before = experience.path(self.pack).read_bytes()
        second = self.save(original, target=first["key"], expected=first["id"], interpretation="我现在更重视先听完对方。")
        self.assertTrue(experience.path(self.pack).read_bytes().startswith(before))
        current = life_story.context(self.pack)
        self.assertEqual([r["id"] for r in current["chapters"]], [second["id"]])
        self.assertEqual(current["previous_versions"], [])
        history = life_story.context(self.pack, historical=True)
        self.assertEqual(history["previous_versions"][0]["version_state"], "historical_interpretation")
        self.assertEqual(history["previous_versions"][0]["id"], first["id"])
        self.assertTrue(MemoryPolicy.load(self.pack).allows(original))
        self.assertFalse(any(r["memory"].get("kind") == "life_story" for r in search(self.pack, "表达", use_semantic=False)))

    def test_old_derived_reply_is_labelled_after_reinterpretation(self):
        source = self.event()
        first = self.save(source)
        derived = experience.record(self.pack, kind="conversation", text="关于表达的旧解释", day=self.day["dayNo"],
                                    source=self.day["file"], depends_on=[first["event_id"]])
        self.save(source, target=first["key"], expected=first["id"], interpretation="理解已经改变。")
        recalled = search(self.pack, "旧解释", use_semantic=False)
        item = next(r["memory"] for r in recalled if r["memory"]["id"] == derived["id"])
        self.assertIn("不代表当前理解", describe(item))

    def test_exact_quote_stale_version_and_duplicate_request(self):
        event = self.event()
        bad = self.data(event, anchors=[{"id": event["id"], "hash": life_story._digest(event), "quote": "不存在的引文"}])
        with self.assertRaises(SeedError):
            life_story.perform(self.pack, "save", bad)
        data = self.data(event)
        first = life_story.perform(self.pack, "save", data, request_id="story-save-once")
        replay = life_story.perform(self.pack, "save", data, request_id="story-save-once")
        self.assertEqual(first["record"]["id"], replay["record"]["id"])
        self.assertEqual(len(life_story.read(self.pack)), 1)
        row = first["record"]
        self.save(event, target=row["key"], expected=row["id"], interpretation="新的理解")
        with self.assertRaises(SeedError):
            self.save(event, target=row["key"], expected=row["id"])

    def test_source_change_invalidates_latest_without_reviving_old_version(self):
        original = self.event()
        first = self.save(original)
        second_source = self.event("后来我决定先倾听。")
        second = self.save(second_source, target=first["key"], expected=first["id"])
        derived = experience.record(self.pack, kind="thought", text="依赖这次回顾的后续理解", day=self.day["dayNo"],
                                    source="mind/experiences.jsonl", depends_on=[second["event_id"]])
        rows = experience.read(self.pack)
        for row in rows:
            if row["id"] == second_source["id"]:
                row["text"] = "外部编辑修改了来源。"
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        self.assertEqual(life_story.context(self.pack)["chapters"], [])
        self.assertEqual(life_story.view(self.pack)["states"][first["key"]], "needs_review")
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))

    def test_setting_aside_interpretation_preserves_sources_and_cannot_restore(self):
        event = self.event()
        row = self.save(event)
        life_story.perform(self.pack, "forget", {"target": row["key"], "expected": row["id"], "reason": "不再使用这个解释"})
        self.assertEqual(life_story.context(self.pack, historical=True)["chapters"], [])
        self.assertTrue(MemoryPolicy.load(self.pack).allows(event))
        latest = life_story.read(self.pack)[-1]
        with self.assertRaises(SeedError):
            self.save(event, target=row["key"], expected=latest["id"])

    def test_model_requires_shown_sources_and_cannot_overwrite_user_reflection(self):
        event = self.event()
        user = self.save(event)
        ctx = {"evidence": [event], "life_story": life_story.context(self.pack)}
        generation = {"runner": "story-fixture", "model": "test-only", **disclosure.stamp("owner")}
        result = life_story.apply_proposals(self.pack, [self.data(event, target=user["key"], expected=user["id"])], ctx=ctx, generation=generation)
        self.assertEqual(result, [])
        self.assertEqual(life_story.apply_proposals(self.pack, [self.data(event, title="另一个标题")], ctx={"evidence": []}, generation=generation), [])
        current = self.data(event, title="模型的解释", anchors=[{"id": "current", "quote": event["text"]}])
        created = life_story.apply_proposals(self.pack, [current], ctx={"current_evidence": [{"id": event["id"]}]}, generation=generation)
        self.assertEqual(created[0]["origin"], "model")
        self.assertEqual(created[0]["anchors"][0]["id"], event["id"])

    def test_private_reflections_are_excluded_from_guest_context(self):
        self.save(self.event("PRIVATE_LIFE_STORY_SOURCE"), title="PRIVATE_LIFE_STORY_TITLE")
        ctx = build_context(self.pack, self.day["dayNo"], self.day["date"], person_id="", audience_id="qq-group:123", use_semantic=False)
        self.assertEqual(ctx["life_story"]["chapters"], [])
        self.assertEqual(ctx["life_story"]["time"], {})
        self.assertNotIn("PRIVATE_LIFE_STORY", json.dumps(build_chat_prompt(ctx)))

    def test_model_reflection_carries_uncited_context_dependencies(self):
        private = self.event("SHARED_CONTEXT_MARKER")
        shared = disclosure.perform(self.pack, "excerpt", {"source_id": private["id"], "source_hash": disclosure._hash(private),
                    "text": private["text"], "scope": "qq-group:123", "reason": "批准这段材料"})["record"]
        source = self.event("这次群聊输入。", metadata=disclosure.stamp("qq-group:123"))
        proposal = self.data(source)
        ctx = {"_audience_id": "qq-group:123", "evidence": [source]}
        made = life_story.apply_proposals(self.pack, [proposal], ctx=ctx,
                 generation={"runner": "story-fixture", "model": "test-only", **disclosure.stamp("qq-group:123"),
                             "context_dependencies": [shared["event_id"]]})[0]
        policy = disclosure.policy_for(self.pack, "qq-group:123")
        self.assertEqual(life_story.context(self.pack, policy=policy)["chapters"][0]["id"], made["id"])
        disclosure.perform(self.pack, "revoke", {"target": shared["key"], "expected": shared["id"], "reason": "撤回背景"})
        self.assertEqual(life_story.context(self.pack, policy=disclosure.policy_for(self.pack, "qq-group:123"))["chapters"], [])

    def test_chat_proposal_is_bound_to_actual_input_and_response(self):
        class Brain:
            name = "stub-story-fixture"
            def chat(inner, ctx):
                return {"reply": "我会继续尝试说清楚。", "_generation": {"runner": "story-fixture", "model": "test-only"}, "life_story": [{"kind": "chapter", "title": "尝试表达",
                        "interpretation": "我正在尝试理解表达。", "reason": "本次交流", "anchors": [{"id": "current", "quote": "我们一起尝试表达。"}]}]}
        result = chat_turn(self.pack, "我们一起尝试表达。", Brain())
        self.assertEqual(result["lifeStoryChanges"], 1)
        chapter = life_story.read(self.pack)[0]
        events = {r["id"]: r for r in experience.read(self.pack)}
        anchor = events[chapter["anchors"][0]["id"]]
        self.assertEqual(anchor["text"], "我们一起尝试表达。")
        deps = events[chapter["event_id"]]["metadata"]["context_dependencies"]
        self.assertTrue(any(events.get(identifier, {}).get("text") == "我会继续尝试说清楚。" for identifier in deps))

    def test_quiet_initiative_can_reconsider_visible_history_without_speaking(self):
        event = self.event()
        append_memories(self.pack, [{"id": "m_quiet_anchor", "text": event["text"],
            "day": self.day["dayNo"], "kind": "conversation", "source": experience.source_of(event),
            "event_ids": [event["id"]], "importance": 0.7}])
        before_dialogue = read_transcript(self.pack, self.day["dayNo"])
        test = self

        class QuietReviewer:
            name = "quiet-story-fixture"

            def chat(self, ctx):
                test.assertIn("m_quiet_anchor", [row["id"] for row in ctx["evidence"]])
                return {"reply": "", "_generation": {"runner": self.name, "model": "offline-fixture", "fallback": False},
                        "life_story": [{"kind": "chapter", "title": "尝试表达",
                            "interpretation": "我正在学习把想法说清楚。", "reason": "重新看待已有交流",
                            "anchors": [{"id": "m_quiet_anchor", "quote": event["text"]}]}]}

        result = maybe_initiate(self.pack, QuietReviewer(), now=f"{self.day['date']}T16:00:00+08:00")
        self.assertEqual(result["lifeStoryChanges"], 1)
        self.assertEqual(life_story.read(self.pack)[0]["origin"], "model")
        self.assertEqual(read_transcript(self.pack, self.day["dayNo"]), before_dialogue)
        self.assertEqual(result["reply"], "")

    def test_failed_write_can_resume_without_duplicate_reflection(self):
        data = self.data(self.event())
        with patch("seedbank.life_story._append", side_effect=OSError("fixture write failure")):
            with self.assertRaises(OSError):
                life_story.perform(self.pack, "save", data, request_id="resume-story")
        self.assertEqual(requests.pending(self.pack)[0]["id"], "resume-story")
        result = Bridge(self.pack, "stub").handle({"op": "resume", "request_id": "resume-story"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(life_story.read(self.pack)), 1)

    def test_private_export_preserves_questions_and_never_overwrites(self):
        self.save(self.event(), title="<script>example</script>")
        result = life_story.export(self.pack)
        exported = Path(result["file"]).read_text(encoding="utf-8")
        self.assertIn("怎样理解没有说出口的部分", exported)
        with self.assertRaises(FileExistsError):
            life_story.export(self.pack, result["file"])
        rendered = render_timeline(self.pack)["html"]
        self.assertIn("&lt;script&gt;example&lt;/script&gt;", rendered)
        self.assertNotIn("<script>example</script>", rendered)

    def test_life_story_expires_continuity_baseline_and_ten_source_format_is_legacy(self):
        baseline = persona.capture(self.pack)
        self.save(self.event())
        with patch("seedbank.persona.create_brain", side_effect=AssertionError("No model")):
            report = persona.check(self.pack)
        self.assertIn("mind/life_story.jsonl", report["archive"]["changed"])
        baseline["sources"].pop("mind/life_story.jsonl")
        baseline["sources"].pop("mind/media.jsonl")
        baseline["sample_digest"] = persona._sample_digest(baseline)
        write_json_atomic(self.pack / "mind/persona.json", baseline)
        self.assertEqual(persona.check(self.pack)["reason"], "legacy_baseline")

    def test_gap_preserves_open_page_and_resumes_calendar_without_fiction(self):
        day_file = self.pack / self.day["file"]
        original = day_file.read_bytes()
        clock.save_clock(self.pack, {"last_seen_date": "2026-11-02"})
        with patch("seedbank.clock._resolve_brain", side_effect=AssertionError("No diary on missing days")):
            result = clock.tick(self.pack, now="2026-11-07T12:00:00+08:00")
        self.assertEqual(result["date"], "2026-11-07")
        self.assertTrue(day_file.read_bytes().startswith(original))
        self.assertIn("## 记录暂停", read_text(day_file))
        self.assertNotIn("## 今天", read_text(day_file))
        self.assertEqual([d["date"] for d in list_days(self.pack)], ["2026-11-01", "2026-11-02", "2026-11-07"])
        check(self.pack)
        coverage = life_story.chronology(self.pack, now="2026-11-07T12:00:00+08:00")
        self.assertEqual(coverage["recorded_pages"], 3)
        self.assertEqual(coverage["unrecorded_calendar_days_between_pages"], 4)
        self.assertFalse(clock.tick(self.pack, now="2026-11-07T13:00:00+08:00")["advanced"])
        # Removing the runtime explanation must not make arbitrary missing dates valid.
        rows = [r for r in experience.read(self.pack) if r["kind"] != "runtime_gap"]
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        with self.assertRaises(SeedError):
            check(self.pack)

    def test_calendar_rollback_and_future_pages_do_not_rewrite_history(self):
        clock.save_clock(self.pack, {"last_seen_date": "2026-11-05"})
        before = list_days(self.pack)
        result = clock.tick(self.pack, now="2026-11-03T12:00:00+08:00")
        self.assertFalse(result["advanced"])
        self.assertEqual(clock.load_clock(self.pack)["last_seen_date"], "2026-11-05")
        self.assertEqual(list_days(self.pack), before)
        self.assertEqual(life_story.chronology(self.pack, now="2026-10-31T12:00:00+08:00")["calendar_days_since_birth"], None)


if __name__ == "__main__":
    unittest.main()
