"""User-run template provenance regressions; isolated files, no real services."""
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import disclosure, experience, retrieval
from seedbank.brain import (RemoteBrain, build_chat_prompt, build_diary_prompt,
                            build_initiate_prompt, create_stub_brain)
from seedbank.cognition import (append_transcript, build_context, chat_turn,
                                open_day, run_days, start_day)
from seedbank.memory_state import MemoryPolicy, is_template, provenance
from seedbank.pack import hatch
from seedbank.util import append_memories, read_memories, write_file_atomic

ROOT = Path(__file__).resolve().parents[2]


class TemplateMemoryTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-template-memory-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.pack = self.folder / "open.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="template-memory",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No network"))
        guard.start()
        self.addCleanup(guard.stop)

    def context(self, query="模板标记"):
        day = open_day(self.pack)
        return build_context(self.pack, day["dayNo"], day["date"], query, use_semantic=False)

    def event(self, text="模板标记：我数了泡泡。", **extra):
        return experience.record(self.pack, text=text, kind=extra.pop("kind", "thought"),
                                 day=self.day["dayNo"], source=self.day["file"], actor="初", **extra)

    def recall(self, query="模板标记"):
        return retrieval.search(self.pack, query, 50, use_semantic=False)

    def test_only_explicit_generation_metadata_marks_templates(self):
        for row in ({"runner": "stub-v1"}, {"generation": {"runner": "stub-v2"}},
                    {"metadata": {"runner": "api", "fallback": True}}, {"template_generated": True}):
            with self.subTest(row=row):
                self.assertTrue(is_template(row))
                self.assertIn("模板", provenance(row))
        for row in ({"text": "stub-v1 是一种模板", "actor": "stub-v1"},
                    {"metadata": {"runner": "api", "fallback": False, "model": "fixture"}},
                    {"metadata": {"fallback": "false"}}, {"runner": "runtime", "kind": "outcome"}, {}):
            with self.subTest(row=row):
                self.assertFalse(is_template(row))

    def test_original_speech_and_model_interpretation_keep_distinct_provenance(self):
        spoken = self.event("我想写一封感谢信。", kind="conversation", metadata={"person_id": "owner"})
        answer = self.event("没有找到相关记录。", kind="conversation", metadata={"runner": "anthropic"})
        self.assertIn("原始发言", provenance(retrieval._event_row(spoken)))
        self.assertIn("模型回复", provenance(retrieval._event_row(answer)))
        self.assertIn("模型提炼", provenance({"kind": "conversation", "generation": {"requested_adapter": "anthropic"}}))
        self.assertEqual(provenance({"kind": "conversation", "actor": "anthropic"}), "对话记录/提炼")

    def test_both_birth_types_keep_identity_without_fabricating_a_physical_day(self):
        for seed in ("open", "dafeiyu"):
            with self.subTest(seed=seed):
                pack = self.folder / (seed + "-identity.life")
                hatch(pack, ROOT / "eggs" / (seed + ".egg"), "旧名字", seed_override="preserve-identity",
                      born_at_override="2026-11-01T00:00:00Z")
                birth = (pack / "birth.json").read_bytes()
                day = start_day(pack)
                ctx = build_context(pack, day["dayNo"], day["date"], "你是谁", use_semantic=False)
                brain = create_stub_brain()
                identity = brain.chat(ctx)["reply"]
                self.assertIn("旧名字", identity)
                if seed == "dafeiyu":
                    self.assertIn(ctx["speciesName"], identity)
                diary = brain.diary(ctx)
                self.assertEqual(diary["memories"], [])
                for invented in ("水有点凉", "数泡泡", "数了泡", "盯着光", "房间很安静"):
                    self.assertNotIn(invented, identity + diary["diary"] + brain.narrative(ctx)["text"])
                self.assertIn("没有记录到新的对话", diary["diary"])
                self.assertEqual((pack / "birth.json").read_bytes(), birth)

    def test_diary_repeats_supplied_reports_as_reports_not_new_sensations(self):
        ctx = self.context()
        ctx.update(transcript=[{"who": "owner", "text": "今天我去爬山了。"}],
                   senses=["图像输入：蓝色背景"], news=["公开报道：车站开放了。"])
        before = deepcopy(ctx)
        result = create_stub_brain().diary(ctx)
        self.assertIn("对方说过", result["diary"])
        self.assertIn("收到的感知描述", result["diary"])
        self.assertIn("这是见闻", result["diary"])
        self.assertEqual(result["memories"], [])
        self.assertEqual(ctx, before)

    def test_offline_day_keeps_old_history_and_adds_no_invented_memories(self):
        old = read_memories(self.pack)
        birth = (self.pack / "birth.json").read_bytes()
        result = run_days(self.pack, days=1, brain=create_stub_brain())
        self.assertEqual(result["days"][0]["memoriesAdded"], 0)
        self.assertEqual(read_memories(self.pack), old)
        diaries = [r for r in experience.read(self.pack) if r["kind"] == "diary"]
        self.assertTrue(diaries)
        self.assertTrue(is_template(diaries[-1]))
        self.assertEqual((self.pack / "birth.json").read_bytes(), birth)

    def test_failed_remote_diary_retains_fallback_origin(self):
        def unavailable(*args):
            raise RuntimeError("fixture unavailable")
        result = RemoteBrain("openai-compatible", unavailable).diary(self.context())
        self.assertTrue(result["_generation"]["fallback"])
        self.assertEqual(result["memories"], [])
        self.assertIn("没有记录到新的对话", result["diary"])

    def test_known_template_memories_stay_readable_but_out_of_growth_evidence(self):
        source = self.event(metadata={"runner": "stub-v1", **disclosure.stamp("owner")})
        memory = {"id": "m_template", "text": "模板标记的旧感受", "kind": "feeling", "day": self.day["dayNo"],
                  "source": experience.source_of(source), "runner": "stub-v1", "importance": .8}
        append_memories(self.pack, [memory])
        original = self.event("模板标记是对方提供的测试词。", kind="conversation",
                              metadata={"person_id": "owner", **disclosure.stamp("owner")})
        before = (self.pack / "mind/memories.jsonl").read_bytes()
        ctx = self.context()
        recalled = {r["memory"]["id"]: r["memory"] for r in ctx["recalled"]}
        self.assertTrue(is_template(recalled[source["id"]]))
        self.assertIn("模板", provenance(recalled[memory["id"]]))
        evidence = {r["id"] for r in ctx["evidence"]}
        self.assertFalse({source["id"], memory["id"]} & evidence)
        self.assertIn(original["id"], evidence)
        self.assertIn("不是亲历", build_chat_prompt(ctx)["user"])
        self.assertEqual((self.pack / "mind/memories.jsonl").read_bytes(), before)

    def test_current_transcript_labels_template_reply_and_keeps_user_source(self):
        chat_turn(self.pack, "模板标记：你好", create_stub_brain())
        ctx = self.context()
        templated = [m for m in ctx["transcript"] if is_template(m)]
        self.assertTrue(templated)
        current = {r["id"] for r in ctx["current_evidence"]}
        self.assertFalse(current & {m["event_id"] for m in templated})
        self.assertTrue(current)
        for builder in (build_chat_prompt, build_diary_prompt, build_initiate_prompt):
            self.assertIn("离线或回退模板", json.dumps(builder(ctx), ensure_ascii=False))

    def test_legacy_day_excerpt_and_duplicate_diary_fragment_keep_template_label(self):
        diary = "模板标记：旧模板说水很凉。"
        self.event(diary, kind="diary", metadata={"runner": "stub-v1"})
        file = self.pack / self.day["file"]
        write_file_atomic(file, file.read_text(encoding="utf-8") + "\n## 今天\n\n" + diary + "\n\n---\n")
        before = file.read_bytes()
        rows = self.recall()
        archived = [r["memory"] for r in rows if r["memory"].get("origin") == "legacy_archive"]
        self.assertTrue(archived)
        self.assertTrue(all(is_template(r) for r in archived))
        start_day(self.pack)
        ctx = self.context()
        self.assertIn("模板日记", ctx["recentDays"][-1]["excerpt"])
        self.assertEqual(file.read_bytes(), before)

    def test_old_cache_rebuild_and_raw_fallback_preserve_template_origin(self):
        event = self.event(metadata={"runner": "api", "fallback": True})
        self.recall()
        index = self.pack / "mind/search.sqlite3"
        with closing(sqlite3.connect(index)) as db, db:
            db.execute("UPDATE metadata SET value='5' WHERE key='version'")
            stored = json.loads(db.execute("SELECT payload FROM entries WHERE id=?", (event["id"],)).fetchone()[0])
            stored.pop("template_generated", None)
            db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(stored), event["id"]))
        self.assertTrue(is_template(next(r["memory"] for r in self.recall() if r["memory"]["id"] == event["id"])))
        with patch.object(retrieval, "_connection", side_effect=sqlite3.DatabaseError("fixture")):
            self.assertTrue(all(is_template(r["memory"]) for r in self.recall()))

    def test_another_paragraph_in_the_same_day_is_not_assumed_to_be_a_template(self):
        self.event("旧模板的独有内容。", kind="diary", metadata={"runner": "stub-v1"})
        policy = MemoryPolicy.load(self.pack)
        different = policy.annotate({"id": "unrelated", "origin": "legacy_archive", "kind": "diary",
                                     "source": self.day["file"], "text": "后来补充的不同记录。"})
        self.assertFalse(is_template(different))
        self.assertTrue(policy.template_diary_fragment(self.day["file"], "旧模板的独有内容。"))

    def test_external_transcript_keeps_labels_without_disclosing_private_templates(self):
        self.event("PRIVATE_TEMPLATE", metadata={"runner": "stub-v1", **disclosure.stamp("owner")})
        append_transcript(self.pack, self.day, [
            {"who": "访客", "text": "模板标记", "metadata": disclosure.stamp("qq-group:123")},
            {"who": "fish", "text": "模板标记的旧回应", "metadata": {"runner": "stub-v1", **disclosure.stamp("qq-group:123")}},
        ])
        ctx = build_context(self.pack, self.day["dayNo"], self.day["date"], "模板标记", use_semantic=False,
                            person_id="", audience_id="qq-group:123")
        raw = json.dumps(build_chat_prompt(ctx), ensure_ascii=False)
        self.assertNotIn("PRIVATE_TEMPLATE", raw)
        self.assertIn("离线或回退模板", raw)
        self.assertFalse(any(is_template(r) for r in ctx["evidence"]))


if __name__ == "__main__":
    unittest.main()
