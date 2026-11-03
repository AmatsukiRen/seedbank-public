"""Offline full-history recall of recorded action explanations."""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import test_action_outcomes as fixtures
from seedbank import actions, cognition, development, disclosure, experience, retrieval, semantic
from seedbank.action_proposals import capture
from seedbank.memory_state import MemoryPolicy, describe
from seedbank.util import append_memories


class ActionArchiveTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp
    proposal = fixtures.ActionOutcomesTest.proposal
    execute = fixtures.ActionOutcomesTest.execute

    def record(self, reason="OLD_ACTION_REASON_ZQ81", *, refs=None, source=None, generation=None, status="succeeded"):
        generation = generation or {"runner": "fixture", "proposal_activity": "initiative", **disclosure.stamp("owner")}
        proposal = capture({"reason": reason}, source=source or experience.source_of(self.input),
            generation=generation, evidence=[] if refs is None else refs)
        return development.record_outcome(self.pack, action="rest", status=status, detail="人工执行结果",
            source=source or experience.source_of(self.input), day=self.day["dayNo"], generation=generation, proposal=proposal)

    def search(self, query="OLD_ACTION_REASON_ZQ81", **kwargs):
        return retrieval.search(self.pack, query, 20, use_semantic=False, **kwargs)

    def test_old_reason_beyond_recent_summary_is_searchable_with_original_receipt(self):
        first = self.record()
        for number in range(12):
            self.record("LATER_DISTINCT_REASON_" + str(number))
        before = (self.pack / "mind/development.jsonl").read_bytes()
        self.assertNotIn(first["id"], [r["id"] for r in development.summary(self.pack)["outcomes"]])
        found = next((r["memory"] for r in self.search() if r["memory"]["id"] == first["id"]), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["source"], "mind/development.jsonl#" + first["id"])
        self.assertIn("OLD_ACTION_REASON_ZQ81", found["text"])
        self.assertIn("人工执行结果", found["text"])
        self.assertIn("当时", describe(found))
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)

    def test_reopening_and_broken_index_fallback_return_the_same_source(self):
        receipt = self.record()
        self.assertIn(receipt["id"], [r["memory"]["id"] for r in self.search()])
        code = "import json,sys; from seedbank.retrieval import search; print(json.dumps(search(sys.argv[1],'OLD_ACTION_REASON_ZQ81',20,use_semantic=False),ensure_ascii=False))"
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(self.pack)],
            capture_output=True, encoding="utf-8", check=True, timeout=30)
        self.assertIn(receipt["id"], [r["memory"]["id"] for r in json.loads(result.stdout)])
        (self.pack / "mind/search.sqlite3").write_bytes(b"intentionally invalid synthetic index")
        self.assertIn(receipt["id"], [r["memory"]["id"] for r in self.search()])

    def test_incremental_append_and_external_source_replacement_are_seen(self):
        self.assertEqual(self.search(), [])
        receipt = self.record()
        self.assertIn(receipt["id"], [r["memory"]["id"] for r in self.search()])
        path = self.pack / "mind/development.jsonl"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("OLD_ACTION_REASON_ZQ81", "REPLACED_ACTION_REASON_65"), encoding="utf-8")
        self.assertEqual(self.search(), [])
        self.assertIn(receipt["id"], [r["memory"]["id"] for r in self.search("REPLACED_ACTION_REASON_65")])

    def test_mutating_one_policy_projection_does_not_change_later_reads(self):
        receipt = self.record()
        before = (self.pack / "mind/development.jsonl").read_bytes()
        policy = MemoryPolicy.load(self.pack)
        policy.action_rows[receipt["id"]]["text"] = "MUTATED_PROJECTION"
        policy.action_outcomes[receipt["id"]]["proposal"]["reason"] = "MUTATED_LEDGER_VIEW"
        fresh = MemoryPolicy.load(self.pack)
        self.assertIn("OLD_ACTION_REASON_ZQ81", fresh.action_rows[receipt["id"]]["text"])
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)
        self.assertTrue(self.search())

    def test_forgotten_source_blocks_cached_historical_and_derived_recall(self):
        receipt = self.record(refs=[{"id": self.memory["id"], "source": self.memory["source"]}])
        self.assertTrue(self.search())
        derived = experience.record(self.pack, kind="thought", text="DERIVED_REASON_RESULT_X9",
            day=self.day["dayNo"], source="art/future.md", depends_on=[receipt["id"]])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertEqual(self.search(), [])
        self.assertEqual(self.search(historical=True), [])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertEqual(self.search("DERIVED_REASON_RESULT_X9"), [])

    def test_new_read_scope_sees_proposal_edits_withdrawal_and_rollback(self):
        from seedbank.desktop.session import Session
        from seedbank.durability import operation
        from seedbank.pack_lock import writer
        receipt = self.record(refs=[{"id": self.memory["id"], "source": self.memory["source"]}])
        session = Session(self.pack, "stub")
        self.addCleanup(session.close)
        def shown():
            return session.snapshot()["states"]["development"]["outcomes"]
        def context():
            return cognition.build_context(self.pack, self.day["dayNo"], self.day["date"],
                "OLD_ACTION_REASON_ZQ81", use_semantic=False)
        shown()[0]["proposal"]["reason"] = "caller mutation"
        self.assertEqual(shown()[0]["proposal"]["reason"], "OLD_ACTION_REASON_ZQ81")
        context()["development"]["outcomes"][0]["proposal"]["reason"] = "context mutation"
        self.assertEqual(context()["development"]["outcomes"][0]["proposal"]["reason"], "OLD_ACTION_REASON_ZQ81")
        ledger = self.pack / "mind/development.jsonl"
        original = ledger.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "scope rollback"):
            with writer(self.pack), operation(self.pack, "action read scope rollback"):
                cognition.forget_memory(self.pack, self.memory["id"])
                self.assertEqual(shown(), [])
                self.assertEqual(context()["development"]["outcomes"], [])
                self.assertNotIn(receipt["id"], [r["memory"]["id"] for r in context()["recalled"]])
                raise RuntimeError("scope rollback")
        self.assertEqual(ledger.read_bytes(), original)
        self.assertEqual(shown()[0]["id"], receipt["id"])
        ledger.write_text(original.decode("utf-8").replace("OLD_ACTION_REASON_ZQ81", "EXTERNAL_ACTION_REASON_76"), encoding="utf-8")
        self.assertEqual(shown()[0]["proposal"]["reason"], "EXTERNAL_ACTION_REASON_76")
        self.assertEqual(context()["development"]["outcomes"][0]["proposal"]["reason"], "EXTERNAL_ACTION_REASON_76")
        self.assertEqual(self.search(), [])

    def test_withdrawn_day_source_blocks_reason_only_derivatives(self):
        legacy = {"id": "m_old_day", "day": self.day["dayNo"], "kind": "thought", "text": "旧日页独立内容",
                  "source": self.source, "at": self.input["recorded_at"]}
        append_memories(self.pack, [legacy])
        receipt = self.record(source=self.source)
        derived = experience.record(self.pack, kind="thought", text="DERIVED_LEGACY_REASON_B4",
            day=self.day["dayNo"], source="art/future.md", depends_on=[receipt["id"]])
        self.assertTrue(self.search())
        cognition.forget_memory(self.pack, legacy["id"])
        self.assertEqual(self.search(), [])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))

    def test_shared_reason_and_derived_reply_follow_scope_and_revocation(self):
        audience = "qq-group:123"
        shared = disclosure.perform(self.pack, "profile", {"scope": audience, "text": "共同看到的人工素材",
            "reason": "人工测试分享"})["record"]
        source = "mind/experiences.jsonl#" + shared["event_id"]
        generation = {"runner": "fixture", "proposal_activity": "conversation", **disclosure.stamp(audience)}
        receipt = self.record(source=source, generation=generation)
        policy = lambda scope: disclosure.policy_for(self.pack, scope)
        self.assertTrue(self.search(policy=policy(audience)))
        self.assertFalse(self.search(policy=policy("qq-group:456")))
        derived = experience.record(self.pack, kind="thought", text="DERIVED_SHARED_REASON_Q2",
            day=self.day["dayNo"], source="art/shared.md", depends_on=[receipt["id"]], metadata=generation)
        self.assertTrue(policy(audience).allows(derived))
        disclosure.perform(self.pack, "revoke", {"target": shared["key"], "expected": shared["id"], "reason": "结束人工分享"})
        self.assertEqual(self.search(policy=policy(audience), historical=True), [])
        self.assertFalse(policy(audience).allows(derived))

    def test_dates_and_failed_results_remain_explicit(self):
        receipt = self.record(status="blocked")
        row = self.search()[0]["memory"]
        self.assertEqual(row["id"], receipt["id"])
        self.assertIn("blocked", row["text"])
        self.assertIn("not_started", row["text"])
        self.assertEqual(self.search(date_to="2020-01-01"), [])

    def test_life_review_can_anchor_recorded_reason_without_inventing_an_event(self):
        from seedbank import life_story
        receipt = self.record(refs=[{"id": self.memory["id"], "source": self.memory["source"]}])
        original = MemoryPolicy.load(self.pack).action_rows[receipt["id"]]
        saved = life_story.perform(self.pack, "save", {"kind": "chapter", "title": "回顾一次选择",
            "interpretation": "当时选择先休息，我还需要观察这对后来的安排有何影响。", "change": "", "question": "", "status": "open",
            "reason": "依据当时记录的说明", "target": "", "expected": "",
            "anchors": [{"id": receipt["id"], "quote": "OLD_ACTION_REASON_ZQ81", "hash": life_story._digest(original)}]})["record"]
        self.assertIn(saved["id"], [r["id"] for r in life_story.context(self.pack)["chapters"]])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertEqual(life_story.context(self.pack)["chapters"], [])

    def test_tampered_cache_payload_cannot_change_recorded_reason(self):
        receipt = self.record()
        self.assertTrue(self.search())
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            payload = json.loads(db.execute("SELECT payload FROM entries WHERE id=?", (receipt["id"],)).fetchone()[0])
            payload["text"] += " FAKED_SUCCESS"
            payload["origin"] = "experience"
            db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(payload), receipt["id"]))
            db.commit()
        self.assertNotIn("FAKED_SUCCESS", json.dumps(self.search(), ensure_ascii=False))

    def test_legacy_missing_reason_is_not_invented_or_indexed_as_a_proposal(self):
        legacy = development.record_outcome(self.pack, action="rest", status="succeeded", detail="LEGACY_RESULT_Q8",
            source=self.source, day=self.day["dayNo"])
        self.assertNotIn(legacy["id"], [r["memory"]["id"] for r in self.search("LEGACY_RESULT_Q8")])

    def test_semantic_catalog_never_sends_withdrawn_reason(self):
        self.record(refs=[{"id": self.memory["id"], "source": self.memory["source"]}])
        self.assertTrue(self.search())
        cognition.forget_memory(self.pack, self.memory["id"])
        semantic.configure(self.pack, {"enabled": True, "model": "offline-embedding"})
        sent = []
        def fake(cfg, texts):
            sent.extend(texts)
            return {"model": "offline-embedding", "data": [{"index": i, "embedding": [1., 0.]} for i, _ in enumerate(texts)]}
        with patch("seedbank.semantic._request", side_effect=fake):
            semantic.manage(self.pack, "index", limit=64)
        self.assertNotIn("OLD_ACTION_REASON_ZQ81", "\n".join(sent))

    def test_semantic_matches_and_model_cannot_correct_a_runtime_receipt(self):
        from seedbank.brain import RemoteBrain, _CfgBrain
        receipt = self.record()
        semantic.configure(self.pack, {"enabled": True, "model": "offline-embedding", "min_similarity": .9})
        sent = []
        def fake(cfg, texts):
            sent.extend(texts)
            return {"model": "offline-embedding", "data": [{"index": i,
                "embedding": [1., 0.] if "OLD_ACTION_REASON_ZQ81" in text or "独特的旧决定" in text else [0., 1.]}
                for i, text in enumerate(texts)]}
        with patch("seedbank.semantic._request", side_effect=fake):
            semantic.manage(self.pack, "index", limit=64)
            rows = retrieval.search(self.pack, "独特的旧决定", 20)
        self.assertIn(receipt["id"], [row["memory"]["id"] for row in rows])
        self.assertIn("OLD_ACTION_REASON_ZQ81", "\n".join(sent))
        semantic.configure(self.pack, {"enabled": False})
        transport = Mock(return_value=json.dumps({"reply": "人工测试回复", "memory_writes": [],
            "corrections": [{"target_id": receipt["id"], "new": "声称原先创作成功", "reason": "不应采用"}]}, ensure_ascii=False))
        brain = _CfgBrain({"adapter": "codex", "model": "fixture", "input_budget": 16000, "codex_max_calls": 1}, RemoteBrain("codex", transport))
        result = cognition.chat_turn(self.pack, "回查 OLD_ACTION_REASON_ZQ81 的当时说明与结果。", brain)
        self.assertEqual(result["corrections"], 0)
        self.assertNotIn(receipt["id"], MemoryPolicy.load(self.pack).superseded)
        self.assertIn("OLD_ACTION_REASON_ZQ81", "\n".join(transport.call_args.args[1:]))


if __name__ == "__main__":
    unittest.main()
