"""User-run regressions for factual corrections reaching generated memories.

Authored only. All packs, clocks and model/embedding transports are fixtures.
"""
from copy import deepcopy
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_fact_time as fixtures
from seedbank import backup, development, disclosure, experience, facts, requests, semantic
from seedbank.brain import RemoteBrain, _development_contract, _transcript_lines, build_chat_prompt
from seedbank.bridge import Bridge
from seedbank.cognition import (build_context, chat_turn, forget_memory, read_transcript,
                               _context_dependencies, _evidence_memories)
from seedbank.memory_state import MemoryPolicy
from seedbank.retrieval import RecallRangeError, search, _event_row
from seedbank.util import SeedError, append_memories, read_memories, write_file_atomic


class FactCorrectionsTest(unittest.TestCase):
    setUp = fixtures.FactTimeTest.setUp
    add = fixtures.FactTimeTest.add

    def data(self, chosen, *, kind="correction", reason="核对后确认原来记错"):
        group = next(g for g in facts.listing(self.pack)["groups"] if g["id"] == chosen["slot"])
        return {"slot": group["id"], "expected": group["expected"], "selected": chosen["id"],
                "change_type": kind, "reason": reason}

    def resolve(self, chosen, **kwargs):
        return facts.perform(self.pack, "resolve", self.data(chosen, **kwargs))["record"]

    def exchange(self, text, reply, *, claims=(), memory="", belief=""):
        class LocalBrain:
            name = "stub-correction-fixture"

            def chat(inner, ctx):
                return {"reply": reply, "fact_claims": [{"subject": "owner", "aspect": aspect,
                            "value": value, "quote": text} for aspect, value in claims],
                        "memory_writes": [{"text": memory, "importance": 0.7}] if memory else [],
                        "development": {"beliefs": [{"text": belief, "confidence": 0.5,
                            "reason": "当时的理解", "evidence": ["current"]}]} if belief else {}}

        chat_turn(self.pack, text, LocalBrain())
        return next(r for r in experience.read(self.pack) if r["text"] == reply)

    def generated(self, source, text, *, scope="owner"):
        return experience.record(self.pack, kind="conversation", text=text, day=1,
            source="mind/experiences.jsonl", actor="fixture",
            metadata={**disclosure.stamp(scope), "runner": "fixture", "context_dependencies": [source]})

    def test_correction_retires_reply_summary_and_belief_without_erasing_input_or_other_facet(self):
        old = self.exchange("我住杭州，也养猫。", "OLD_REPLY_731", memory="OLD_SUMMARY_834",
                            belief="OLD_BELIEF_529", claims=[("居住地", "杭州"), ("养宠情况", "养猫")])
        original = next(r for r in experience.read(self.pack) if r["text"] == "我住杭州，也养猫。")
        self.assertTrue(any(r["text"] == "OLD_BELIEF_529" for r in development.summary(self.pack)["beliefs"]))
        chosen = self.add("成都")
        before = facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        self.resolve(chosen)
        self.assertTrue(facts.path(self.pack).read_bytes().startswith(before[0]))
        self.assertTrue(experience.path(self.pack).read_bytes().startswith(before[1]))
        policy = MemoryPolicy.load(self.pack)
        self.assertTrue(policy.allows(original))
        self.assertFalse(policy.allows(old))
        self.assertFalse(any(r["text"] == "OLD_SUMMARY_834" for r in policy.visible()))
        self.assertTrue(any(r["text"] == "OLD_SUMMARY_834" for r in read_memories(self.pack)))
        self.assertFalse(any(r["text"] == "OLD_BELIEF_529" for r in development.summary(self.pack)["beliefs"]))
        groups = {g["aspect"]: g for g in facts.listing(self.pack)["groups"]}
        self.assertEqual([r["value"] for r in groups["居住地"]["claims"]], ["成都"])
        self.assertEqual([r["value"] for r in groups["养宠情况"]["claims"]], ["养猫"])
        for historical in (False, True):
            self.assertFalse(search(self.pack, "OLD_REPLY_731", use_semantic=False, historical=historical))
        self.assertTrue(any(r["text"] == "OLD_REPLY_731" for r in read_transcript(self.pack, self.day["dayNo"])))

    def test_cutoff_uses_append_order_and_fresh_interpretations_are_not_automatically_retired(self):
        old, chosen = self.add("杭州"), self.add("成都")
        source = old["evidence"][0]["id"]
        previous = self.generated(source, "BEFORE_367")
        with patch("seedbank.experience.now_iso", return_value="1900-01-01T00:00:00Z"):
            self.resolve(chosen)
        fresh = self.generated(source, "AFTER_328")
        policy = MemoryPolicy.load(self.pack)
        self.assertFalse(policy.allows(previous))
        self.assertTrue(policy.allows(fresh))
        self.assertTrue(policy.allows(next(r for r in experience.read(self.pack) if r["id"] == source)))

    def test_later_change_keeps_past_interpretation_and_adds_current_notes(self):
        old_reply = self.exchange("我住杭州。", "PAST_READING_837", claims=[("居住地", "杭州")])
        chosen = self.add("成都")
        self.resolve(chosen, kind="change", reason="后来搬家")
        self.assertTrue(MemoryPolicy.load(self.pack).allows(old_reply))
        context = build_context(self.pack, self.day["dayNo"], self.day["date"], "无关的问题", use_semantic=False)
        original = next(r for r in context["transcript"] if r["text"] == "我住杭州。")
        self.assertEqual(original["fact_notes"][0]["change_type"], "change")
        self.assertIn("不能套用到过去日期", _transcript_lines(context))

    def test_user_adoption_keeps_selected_model_claim_after_old_context_is_retired(self):
        old_reply = self.exchange("我住杭州。", "OLD_CONTEXT_328", claims=[("居住地", "杭州")])
        self.exchange("我住成都。", "NEW_VALUE_REPLY_392", claims=[("居住地", "成都")])
        group = facts.listing(self.pack)["groups"][0]
        chosen = next(r for r in group["claims"] if r["value"] == "成都")
        self.assertIn(old_reply["id"], chosen["generation"]["context_dependencies"])
        self.resolve(chosen)
        self.assertFalse(MemoryPolicy.load(self.pack).allows(old_reply))
        group = facts.listing(self.pack)["groups"][0]
        self.assertEqual(group["expected"], [chosen["id"]])
        self.assertEqual(group["status"], "reported")
        self.add("深圳")
        self.assertEqual(facts.listing(self.pack)["groups"][0]["status"], "conflict")

    def test_working_transcript_keeps_correction_even_when_question_has_no_topic_overlap(self):
        self.exchange("我住杭州。", "WRONG_REPLY_734", claims=[("居住地", "杭州")])
        decision = self.resolve(self.add("成都"))
        context = build_context(self.pack, self.day["dayNo"], self.day["date"], "随便聊聊", use_semantic=False)
        original = next(r for r in context["transcript"] if r["text"] == "我住杭州。")
        self.assertEqual(original["fact_notes"][0]["values"], ["成都"])
        self.assertEqual(original["fact_notes"][0]["change_type"], "correction")
        self.assertNotIn("WRONG_REPLY_734", build_chat_prompt(context)["user"])
        self.assertIn("原文的当前单项核对", build_chat_prompt(context)["user"])
        self.assertIn(decision["evidence"][0]["id"], _context_dependencies({"transcript": [original]}))

    def test_recent_evidence_deduplication_and_development_contract_preserve_fact_notes(self):
        old, chosen = self.add("杭州"), self.add("成都")
        decision = self.resolve(chosen)
        ref = old["evidence"][0]
        append_memories(self.pack, [{"id": "m_direct_quote", "kind": "thought", "day": 1,
            "text": "原文摘录", "source": ref["source"], "event_ids": [ref["id"]]}])
        row = next(r for r in read_memories(self.pack) if r["id"] == "m_direct_quote")
        retrieved = facts.annotate_recalled(self.pack, [{"memory": row}])
        evidence = _evidence_memories(self.pack, recalled=retrieved)
        item = next(r for r in evidence if r["id"] == row["id"])
        self.assertEqual(item["fact_notes"][0]["values"], ["成都"])
        self.assertIn('"fact_notes"', _development_contract({"evidence": [item]}))
        self.assertIn(decision["evidence"][0]["id"], _context_dependencies({"evidence": [item]}))

    def test_withdrawing_decision_support_hides_fresh_dependent_reply_without_restoring_old_value(self):
        self.exchange("我住杭州。", "FIRST_REPLY_746", claims=[("居住地", "杭州")])
        decision = self.resolve(self.add("成都"))
        fresh = self.exchange("聊聊别的", "CORRECTED_REPLY_925")
        ref = decision["evidence"][0]
        self.assertIn(ref["id"], fresh["metadata"]["context_dependencies"])
        append_memories(self.pack, [{"id": "m_decision", "kind": "thought", "day": 1, "text": "核对来源",
            "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_decision")
        self.assertFalse(MemoryPolicy.load(self.pack).allows(fresh))
        self.assertEqual(facts.listing(self.pack)["groups"], [])

    def test_private_correction_retires_old_group_output_without_disclosing_private_reason_or_value(self):
        source = experience.record(self.pack, kind="conversation", text="我住杭州。", day=1,
            source="mind/experiences.jsonl", actor="user", metadata=disclosure.stamp("qq-group:123"))
        facts.apply_proposals(self.pack, [{"subject": "owner", "aspect": "居住地", "value": "杭州", "quote": source["text"]}],
            event=source, allowed_entities=["owner"], runner="fixture", generation=disclosure.stamp("qq-group:123"))
        old = self.generated(source["id"], "GROUP_OLD_REPLY_249", scope="qq-group:123")
        self.resolve(self.add("PRIVATE_VALUE_531"), reason="PRIVATE_REASON_792")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        self.assertFalse(policy.allows(old))
        self.assertTrue(policy.allows(source))
        context = build_context(self.pack, self.day["dayNo"], self.day["date"], "杭州", use_semantic=False,
                                person_id="", audience_id="qq-group:123")
        encoded = json.dumps(context, ensure_ascii=False)
        self.assertNotIn("PRIVATE_VALUE_531", encoded)
        self.assertNotIn("PRIVATE_REASON_792", encoded)
        stale = {**_event_row(source), "fact_notes": [{"reason": "PRIVATE_REASON_792"}]}
        self.assertNotIn("PRIVATE_REASON_792", json.dumps(facts.annotate_records(self.pack, [stale], policy), ensure_ascii=False))

    def test_missing_or_changed_decision_source_does_not_restore_old_or_assert_selected_value(self):
        for mode in ("missing", "changed"):
            with self.subTest(mode=mode):
                old, chosen = self.add("旧值", aspect=mode), self.add("新值", aspect=mode)
                previous = self.generated(old["evidence"][0]["id"], "BEFORE_" + mode)
                decision = self.resolve(chosen)
                identifier = decision["evidence"][0]["id"]
                rows = deepcopy(experience.read(self.pack))
                if mode == "missing":
                    rows = [r for r in rows if r["id"] != identifier]
                else:
                    next(r for r in rows if r["id"] == identifier)["text"] = "外部改动"
                write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
                self.assertFalse(MemoryPolicy.load(self.pack).allows(previous))
                self.assertFalse(any(g["id"] == chosen["slot"] for g in facts.listing(self.pack)["groups"]))

    def test_backup_and_explicit_request_resume_apply_the_same_correction(self):
        old, chosen = self.add("杭州"), self.add("成都")
        previous = self.generated(old["evidence"][0]["id"], "RECOVERY_OLD_REPLY_397")
        data = self.data(chosen)
        with patch("seedbank.facts._append", side_effect=OSError("fixture")), self.assertRaises(OSError):
            facts.perform(self.pack, "resolve", data, request_id="recover-correction")
        self.assertEqual(requests.get(self.pack, "recover-correction")["status"], "pending")
        self.assertTrue(MemoryPolicy.load(self.pack).allows(previous))
        saved = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(saved["file"], restored)
        result = Bridge(restored, "stub").handle({"op": "resume", "request_id": "recover-correction"})
        self.assertTrue(result["ok"], result)
        self.assertFalse(MemoryPolicy.load(restored).allows(previous))
        before = facts.path(restored).read_bytes(), experience.path(restored).read_bytes()
        self.assertTrue(facts.perform(restored, "resolve", data, request_id="recover-correction")["replayed"])
        self.assertEqual(before, (facts.path(restored).read_bytes(), experience.path(restored).read_bytes()))
        self.assertTrue(MemoryPolicy.load(self.pack).allows(previous))

    def test_semantic_candidates_and_broken_index_fallback_do_not_revive_corrected_output(self):
        old, chosen = self.add("杭州"), self.add("成都")
        previous = self.generated(old["evidence"][0]["id"], "UNIQUE_WRONG_583")
        self.resolve(chosen)
        semantic.configure(self.pack, {"enabled": True, "model": "fixture"})
        with patch("seedbank.semantic.candidates", return_value=[(_event_row(previous), 0.99)]):
            self.assertFalse(search(self.pack, "UNIQUE_WRONG_583"))
        with patch("seedbank.retrieval._connection", side_effect=sqlite3.DatabaseError("fixture")):
            self.assertFalse(search(self.pack, "UNIQUE_WRONG_583", use_semantic=False))

    def test_invalid_date_filters_are_rejected_before_index_or_embedding_work(self):
        for filters in ({"date_from": "2026-02-30"}, {"date_to": "昨天"}, {"date_from": True},
                        {"date_from": "2026-11-02T00:00:00"}, {"date_from": "2026-11-02", "date_to": "2026-11-01"}):
            with self.subTest(filters=filters), self.assertRaises(RecallRangeError), \
                    patch("seedbank.retrieval._connection", side_effect=AssertionError("No index work")), \
                    patch("seedbank.semantic.configuration", side_effect=AssertionError("No service configuration")):
                search(self.pack, "往事", **filters)

    def test_valid_record_date_range_is_inclusive_and_excludes_other_dates(self):
        append_memories(self.pack, [{"id": "m_range", "day": 1, "at": "2026-02-28T12:00:00Z",
            "text": "RANGE_RECORD_328", "kind": "thought", "source": "fixture"}])
        self.assertTrue(search(self.pack, "RANGE_RECORD_328", date_from="2026-02-28", date_to="2026-02-28", use_semantic=False))
        self.assertFalse(search(self.pack, "RANGE_RECORD_328", date_from="2026-03-01", use_semantic=False))

    def test_model_invalid_search_range_returns_a_runtime_explanation_without_stub_or_unbounded_retry(self):
        calls = []

        def transport(cfg, system, user):
            calls.append(user)
            return json.dumps({"memory_search": {"query": "往事", "date_from": "2026-02-30"}})

        context = build_context(self.pack, self.day["dayNo"], self.day["date"], "以前发生什么？", use_semantic=False)
        context["_cfg"] = {"model": "fixture", "input_budget": 100000}
        with patch("seedbank.retrieval._connection", side_effect=AssertionError("Invalid range cannot search")):
            result = RemoteBrain("openai-compatible", transport).chat(context)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["_generation"]["runner"], "runtime")
        self.assertEqual(result["_generation"]["runtime_guard"], "invalid_search_range")
        self.assertEqual(result["_generation"]["retrieval"]["state"], "invalid_date_range")
        self.assertIsNone(result["_generation"]["model"])
        self.assertFalse(result["_generation"]["fallback"])
        self.assertEqual(result["_generation"]["memory_searches"], 0)
        self.assertEqual(result["memory_writes"], [])


if __name__ == "__main__":
    unittest.main()
