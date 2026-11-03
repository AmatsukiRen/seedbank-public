"""User-run history checks with artificial packs and blocked/mock transports.

Authored only. Earlier goal-history results do not establish these cases.
"""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import test_action_outcomes as fixtures
import test_goal_history as goal_fixtures
from seedbank import cognition, development, disclosure, experience, life_story, retrieval, semantic
from seedbank.memory_state import MemoryPolicy, describe


class JudgmentHistoryTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp
    new_basis = goal_fixtures.GoalHistoryTest.new_basis

    def change(self, kind="belief", reason="OLD_BELIEF_晴川", *, identifier="", content="整理原记录比补齐故事更可靠",
               topic="整理资料", stance="like", generation=None):
        data = {"id": identifier, "reason": reason, "evidence": [self.memory["id"]]}
        data.update({"text": content, "confidence": .6} if kind == "belief" else {"topic": topic, "stance": stance})
        plural = "beliefs" if kind == "belief" else "preferences"
        return development.apply_proposals(self.pack, {plural: [data]},
            day=self.day["dayNo"], source=experience.source_of(self.input), runner="judgment-history-fixture",
            memories=[self.memory], generation=generation if generation is not None else {
                "runner": "judgment-history-fixture", "proposal_activity": "conversation", **disclosure.stamp("owner")})[0]

    def search(self, query="OLD_BELIEF_晴川", **kwargs):
        return retrieval.search(self.pack, query, 20, use_semantic=False, **kwargs)

    def row(self, event, query="OLD_BELIEF_晴川"):
        return next(r["memory"] for r in self.search(query) if r["memory"]["id"] == event["id"])

    def test_belief_versions_remain_recallable_beyond_current_summary(self):
        first = self.change()
        identifier = first["data"]["id"]
        middle = self.change(reason="MIDDLE_BELIEF_调整", identifier=identifier, content="也要留意材料遗漏的背景")
        latest = self.change(reason="LATEST_BELIEF_重新理解", identifier=identifier, content="原文和背景需要分别核对")
        for index in range(21):
            self.change(reason=f"后来形成 {index}", content=f"独立人工看法 {index}")
        before = (self.pack / "mind/development.jsonl").read_bytes()
        self.assertNotIn(identifier, [r["id"] for r in development.summary(self.pack)["beliefs"]])
        old = self.row(first)
        self.assertEqual(old["kind"], "belief_history")
        self.assertEqual(old["judgment_id"], identifier)
        self.assertEqual(old["source"], "mind/development.jsonl#" + first["id"])
        self.assertEqual(old["judgment_version"]["event_id"], latest["id"])
        self.assertFalse(old["judgment_version"]["is_latest"])
        self.assertIn("LATEST_BELIEF_重新理解", describe(old))
        self.assertIn(middle["id"], [r["memory"]["id"] for r in self.search("MIDDLE_BELIEF_调整")])
        self.assertEqual(development.current_state(self.pack)["beliefs"][identifier]["text"], latest["data"]["text"])
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)

    def test_preference_changes_keep_past_stance_separate_from_latest(self):
        first = self.change("preference", "OLD_PREFERENCE_林窗", stance="like")
        identifier = first["data"]["id"]
        self.change("preference", "MIDDLE_PREFERENCE_厌倦", identifier=identifier, stance="avoid")
        latest = self.change("preference", "LATEST_PREFERENCE_保留判断", identifier=identifier, stance="unsure")
        for index in range(21):
            self.change("preference", f"其他偏好依据 {index}", topic=f"其他人工主题 {index}")
        old = self.row(first, "OLD_PREFERENCE_林窗")
        self.assertEqual(old["kind"], "preference_history")
        self.assertIn("倾向喜欢", old["text"])
        self.assertIn("尚不确定", old["judgment_version"]["statement"])
        self.assertEqual(old["judgment_version"]["event_id"], latest["id"])
        self.assertTrue(self.search("MIDDLE_PREFERENCE_厌倦"))
        self.assertEqual(development.current_state(self.pack)["preferences"][identifier]["stance"], "unsure")

    def test_unavailable_latest_does_not_disclose_it_or_restore_old_attitude(self):
        first = self.change()
        self.new_basis()
        latest = self.change(reason="PRIVATE_LATEST_JUDGMENT", identifier=first["data"]["id"], content="私人新版看法")
        cognition.forget_memory(self.pack, self.memory["id"])
        old = self.row(first)
        self.assertFalse(old["judgment_version"]["current_available"])
        self.assertNotIn("PRIVATE_LATEST_JUDGMENT", describe(old))
        self.assertNotIn(latest["id"], json.dumps(old))
        self.assertNotIn(first["data"]["id"], development.current_state(self.pack)["beliefs"])

    def test_old_basis_withdrawal_blocks_version_only_derivatives_not_independent_revision(self):
        first = self.change("preference", "OLD_PREFERENCE_独立来源")
        initial_memory = self.memory["id"]
        derived = experience.record(self.pack, kind="thought", text="JUDGMENT_VERSION_ONLY_DERIVED",
            day=self.day["dayNo"], source="art/artificial-note.md", depends_on=[first["id"]])
        self.new_basis()
        later = self.change("preference", "INDEPENDENT_PREFERENCE_晚风", identifier=first["data"]["id"], stance="avoid")
        cognition.forget_memory(self.pack, initial_memory)
        for historical in (False, True):
            found = self.search("OLD_PREFERENCE_独立来源", historical=historical)
            self.assertNotIn(first["id"], [r["memory"]["id"] for r in found])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertIn(later["id"], [r["memory"]["id"] for r in self.search("INDEPENDENT_PREFERENCE_晚风")])

    def test_private_history_and_explicit_excerpt_have_separate_scope(self):
        first = self.change()
        self.assertEqual(self.search(policy=disclosure.policy_for(self.pack, "qq-group:123")), [])
        original = MemoryPolicy.load(self.pack).judgment_rows[first["id"]]
        share = disclosure.perform(self.pack, "excerpt", {"scope": "qq-group:123", "text": "OLD_BELIEF_晴川",
            "source_id": first["id"], "source_hash": disclosure._hash(original), "reason": "人工分享这一段旧看法"})["record"]
        self.change(reason="LATER_PRIVATE_JUDGMENT", identifier=first["data"]["id"], content="仅供个人回看的新版")
        found = self.search(policy=disclosure.policy_for(self.pack, "qq-group:123"))
        self.assertIn(share["event_id"], [r["memory"]["id"] for r in found])
        self.assertNotIn(first["id"], [r["memory"]["id"] for r in found])
        self.assertNotIn("LATER_PRIVATE_JUDGMENT", json.dumps(found))
        self.assertEqual(self.search(policy=disclosure.policy_for(self.pack, "qq-group:456")), [])

    def test_semantic_catalog_uses_canonical_history_and_obeys_withdrawal(self):
        first = self.change()
        semantic.configure(self.pack, {"enabled": True, "model": "judgment-fixture", "min_similarity": .9})
        sent = []
        def fake(cfg, texts):
            sent.extend(texts)
            return {"model": "judgment-fixture", "data": [{"index": i,
                "embedding": [1., 0.] if "OLD_BELIEF_晴川" in value or value == "当初看法的理由" else [0., 1.]}
                for i, value in enumerate(texts)]}
        with patch("seedbank.semantic._request", side_effect=fake):
            semantic.manage(self.pack, "index", limit=64)
            found = retrieval.search(self.pack, "当初看法的理由", 20)
        self.assertIn(first["id"], [r["memory"]["id"] for r in found])
        cognition.forget_memory(self.pack, self.memory["id"])
        sent.clear()
        with patch("seedbank.semantic._request", side_effect=fake):
            semantic.manage(self.pack, "index", limit=64)
            found = retrieval.search(self.pack, "当初看法的理由", 20)
        self.assertNotIn(first["id"], [r["memory"]["id"] for r in found])
        self.assertNotIn("OLD_BELIEF_晴川", "\n".join(sent))

    def test_v11_cache_rebuild_adds_judgments_without_changing_source(self):
        first = self.change()
        self.assertTrue(self.search())
        before = (self.pack / "mind/development.jsonl").read_bytes()
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            db.execute("UPDATE metadata SET value='11' WHERE key='version'")
            db.execute("DELETE FROM entries WHERE id=?", (first["id"],))
            db.commit()
        self.assertIn(first["id"], [r["memory"]["id"] for r in self.search()])
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0], retrieval.VERSION)
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)

    def test_reopen_bad_index_and_date_filter_keep_original_history(self):
        first = self.change()
        self.assertTrue(self.search())
        code = "import json,sys; from seedbank.retrieval import search; print(json.dumps(search(sys.argv[1],'OLD_BELIEF_晴川',20,use_semantic=False),ensure_ascii=False))"
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(self.pack)],
            capture_output=True, encoding="utf-8", timeout=30, check=True)
        self.assertIn(first["id"], [r["memory"]["id"] for r in json.loads(result.stdout)])
        (self.pack / "mind/search.sqlite3").write_bytes(b"invalid artificial cache")
        self.assertIn(first["id"], [r["memory"]["id"] for r in self.search()])
        self.assertEqual(self.search(date_to="2020-01-01"), [])

    def test_cache_cannot_forge_latest_attitude_or_historical_text(self):
        first = self.change()
        self.assertTrue(self.search())
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            payload = json.loads(db.execute("SELECT payload FROM entries WHERE id=?", (first["id"],)).fetchone()[0])
            payload["judgment_version"] = {"current_available": True, "statement": "FAKED_CURRENT_ATTITUDE"}
            db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(payload), first["id"]))
            db.commit()
        self.assertNotIn("FAKED_CURRENT_ATTITUDE", json.dumps(self.search()))
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            payload.update(text=payload["text"] + " FAKED_JUDGMENT_TEXT", origin="experience")
            db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(payload), first["id"]))
            db.commit()
        self.assertNotIn("FAKED_JUDGMENT_TEXT", json.dumps(self.search()))

    def test_final_prompt_and_latest_dependency_cannot_be_replaced_by_memory_correction(self):
        from seedbank.brain import RemoteBrain, _CfgBrain
        first = self.change()
        self.new_basis()
        latest = self.change(reason="LATEST_JUDGMENT_REASON", identifier=first["data"]["id"], content="新的有来源看法")
        old = self.row(first)
        self.assertIn(latest["id"], cognition._context_dependencies({"evidence": [old]}))
        transport = Mock(return_value=json.dumps({"reply": "人工回顾旧看法", "memory_writes": [],
            "corrections": [{"target_id": first["id"], "new": "这是已经核实的事实", "reason": "不应改写成长事件"}]}, ensure_ascii=False))
        brain = _CfgBrain({"adapter": "codex", "model": "fixture", "input_budget": 16000, "codex_max_calls": 1}, RemoteBrain("codex", transport))
        result = cognition.chat_turn(self.pack, "回查 OLD_BELIEF_晴川 的当时理由。", brain)
        self.assertEqual(result["corrections"], 0)
        prompt = "\n".join(transport.call_args.args[1:])
        self.assertIn("OLD_BELIEF_晴川", prompt)
        self.assertIn("LATEST_JUDGMENT_REASON", prompt)
        reply = next(row for row in reversed(experience.read(self.pack)) if row["text"] == "人工回顾旧看法")
        self.assertIn(latest["id"], reply["depends_on"])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(reply))

    def test_prompt_channels_keep_latest_note_until_entire_history_is_trimmed(self):
        from seedbank.brain import build_chat_prompt
        from seedbank.context_window import fit
        first = self.change()
        latest = self.change(reason="LATEST_JUDGMENT_FOR_FIT_" + "界" * 180,
            identifier=first["data"]["id"], content="后来形成的看法")
        old = next(row for row in self.search() if row["memory"]["id"] == first["id"])
        base = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        for key in ("development", "facts", "practice", "relationships", "life_story", "inner", "daily_choice"):
            base[key] = {}
        for key in ("transcript", "evidence", "recalled", "learning", "disclosed", "senses", "news", "works", "friends"):
            base[key] = []
        for key in ("beliefs", "selfMd", "recentDays", "plan"):
            base[key] = ""
        base.update(message="回看当时的看法和后来的变化", _compact_protocol=True)
        empty = build_chat_prompt({**base, "context_limited": True})
        budget = sum(len(value.encode("utf-8")) for value in empty.values()) + 512 + 32
        for channel in ("evidence", "recalled"):
            with self.subTest(channel=channel):
                ctx = {**base, channel: [old["memory"]] if channel == "evidence" else [old], "_cfg": {"input_budget": budget}}
                before = json.dumps(ctx, ensure_ascii=False)
                full = "\n".join(build_chat_prompt(ctx).values())
                self.assertIn("LATEST_JUDGMENT_FOR_FIT_", full)
                self.assertIn(latest["id"], cognition._context_dependencies(ctx))
                prompt, used, measured = fit(ctx, build_chat_prompt)
                self.assertTrue(measured["limited"])
                self.assertNotIn("OLD_BELIEF_晴川", "\n".join(prompt.values()))
                self.assertNotIn("LATEST_JUDGMENT_FOR_FIT_", "\n".join(prompt.values()))
                self.assertNotIn(first["id"], cognition._context_dependencies(used))
                self.assertNotIn(latest["id"], cognition._context_dependencies(used))
                self.assertEqual(json.dumps(ctx, ensure_ascii=False), before)

    def test_life_review_anchors_past_belief_without_rewriting_it_as_latest(self):
        first = self.change()
        original = MemoryPolicy.load(self.pack).judgment_rows[first["id"]]
        saved = life_story.perform(self.pack, "save", {"kind": "chapter", "title": "回看曾经的理解",
            "interpretation": "曾认为整理原文尤其重要。", "change": "", "question": "", "status": "open",
            "reason": "依据当时的看法记录", "target": "", "expected": "",
            "anchors": [{"id": first["id"], "quote": "OLD_BELIEF_晴川", "hash": life_story._digest(original)}]})["record"]
        self.change(reason="后来补充了理解", identifier=first["data"]["id"], content="也需要核对背景")
        self.assertIn(saved["id"], [r["id"] for r in life_story.context(self.pack)["chapters"]])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertEqual(life_story.context(self.pack)["chapters"], [])

    def test_fixed_or_unrecorded_activity_is_not_inferred_as_autonomy(self):
        fixed = self.change(reason="FIXED_JUDGMENT_REASON", generation={"runner": "stub"})
        self.assertTrue(self.row(fixed, "FIXED_JUDGMENT_REASON")["template_generated"])
        self.assertIn("固定或回退响应", describe(self.row(fixed, "FIXED_JUDGMENT_REASON")))
        unknown = self.change("preference", "UNRECORDED_PREFERENCE_REASON", generation={})
        self.assertIn("当时未记录形成场景", self.row(unknown, "UNRECORDED_PREFERENCE_REASON")["text"])


if __name__ == "__main__":
    unittest.main()
