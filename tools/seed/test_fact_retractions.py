"""User-run regressions for mistaken extractions. Authored, not executed."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

import test_fact_time as fixtures
from seedbank import backup, disclosure, experience, facts, fact_dates, fact_time, requests
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import chat_turn, forget_memory, _context_dependencies
from seedbank.memory_state import MemoryPolicy
from seedbank.retrieval import search
from seedbank.util import SeedError, append_memories, write_file_atomic


class FactRetractionsTest(unittest.TestCase):
    setUp = fixtures.FactTimeTest.setUp
    add = fixtures.FactTimeTest.add
    resolve = fixtures.FactTimeTest.resolve

    def proposal(self, text="我不住杭州，也养猫。", *, scope="owner", aspect="居住地", value="杭州", event=None, **extra):
        metadata = disclosure.stamp(scope)
        event = event or experience.record(self.pack, kind="conversation", text=text, day=1,
            source="mind/experiences.jsonl", actor="user", metadata=metadata)
        result = facts.apply_proposals(self.pack, [{"subject": "owner", "aspect": aspect,
            "value": value, "quote": event["text"], **extra}], event=event,
            allowed_entities=["owner"], runner="fixture", generation=metadata)
        return event, result

    def data(self, claim, reason="提取丢失了原句中的否定"):
        group = next(g for g in facts.listing(self.pack)["groups"] if g["id"] == claim["slot"])
        item = next(r for r in group["claims"] if r["id"] == claim["id"])
        return {"slot": group["id"], "expected": group["expected"], "target": item["id"],
                "target_hash": item["target_hash"], "reason": reason}

    def retract(self, claim, **kwargs):
        return facts.perform(self.pack, "retract", self.data(claim), **kwargs)["record"]

    def reply(self, text):
        class OfflineBrain:
            name = "stub-retraction-fixture"

            def chat(self, ctx):
                return {"reply": text, "memory_writes": []}

        chat_turn(self.pack, "我的居住地是什么？", OfflineBrain())
        return next(r for r in experience.read(self.pack) if r["text"] == text)

    def test_single_mistaken_extraction_retires_without_losing_source_or_other_facet(self):
        original, result = self.proposal()
        claim = result["added"][0]
        _, other = self.proposal(event=original, aspect="养宠情况", value="养猫")
        before = facts.path(self.pack).read_bytes()
        retraction = self.retract(claim)
        self.assertTrue(facts.path(self.pack).read_bytes().startswith(before))
        self.assertEqual(retraction["format"], "seedbank/facts@3")
        self.assertEqual(next(r for r in experience.read(self.pack) if r["id"] == original["id"]), original)
        current = facts.listing(self.pack)["groups"]
        self.assertEqual([c["id"] for g in current for c in g["claims"]], [other["added"][0]["id"]])
        history = next(g for g in facts.listing(self.pack, audit=True)["groups"] if g["id"] == claim["slot"])
        self.assertTrue(history["history"][0]["retracted"])
        self.assertFalse(history["history"][0]["recallable"])
        self.assertEqual(history["retractions"][0]["reason"], retraction["reason"])
        self.assertTrue(MemoryPolicy.load(self.pack).allows(original))

    def test_source_recall_and_zero_candidate_context_explain_retraction_without_inventing_opposite(self):
        original, result = self.proposal()
        row = self.retract(result["added"][0])
        ctx = facts.context(self.pack, "居住地")
        group = ctx["groups"][0]
        self.assertEqual(group["claims"], [])
        self.assertEqual(group["retractions"][0]["value"], "杭州")
        self.assertEqual(group["retractions"][0]["quote"], original["text"])
        self.assertIn(row["evidence"][0]["id"], _context_dependencies({"facts": ctx}))
        recalled = next(r["memory"] for r in search(self.pack, "养猫", use_semantic=False, k=100)
                        if r["memory"]["id"] == original["id"])
        self.assertEqual(recalled["fact_notes"][0]["retractions"][0]["reason"], row["reason"])
        self.assertIn("不能自动推断相反命题", facts.prompt_lines(ctx))

    def test_old_generated_readings_retire_but_fresh_answers_and_raw_input_remain(self):
        original, result = self.proposal()
        old = self.reply("OLD_READING_573")
        with patch("seedbank.experience.now_iso", return_value="1900-01-01T00:00:00Z"):
            self.retract(result["added"][0])
        fresh = self.reply("FRESH_READING_294")
        policy = MemoryPolicy.load(self.pack)
        self.assertFalse(policy.allows(old))
        self.assertTrue(policy.allows(fresh))
        self.assertTrue(policy.allows(original))
        self.assertFalse(any("OLD_READING_573" in r["memory"]["text"]
                             for r in search(self.pack, "OLD_READING_573", use_semantic=False)))

    def test_actual_chat_extraction_retires_its_reply_and_summary_without_losing_raw_input_or_sibling(self):
        class ExtractingBrain:
            name = "stub-extraction-fixture"

            def chat(self, ctx):
                return {"reply": "ORIGINAL_WRONG_REPLY_267",
                    "memory_writes": [{"text": "WRONG_SUMMARY_728", "importance": 0.6}],
                    "fact_claims": [{"subject": "owner", "aspect": a, "value": v, "quote": "我不住杭州，也养猫。"}
                                    for a, v in (("居住地", "杭州"), ("养宠情况", "养猫"))]}

        chat_turn(self.pack, "我不住杭州，也养猫。", ExtractingBrain())
        groups = facts.listing(self.pack)["groups"]
        claim = next(g for g in groups if g["aspect"] == "居住地")["claims"][0]
        self.assertTrue(any(r["text"] == "WRONG_SUMMARY_728" for r in MemoryPolicy.load(self.pack).visible()))
        self.retract(claim)
        policy = MemoryPolicy.load(self.pack)
        events = experience.read(self.pack)
        original = next(r for r in events if r["text"] == "我不住杭州，也养猫。")
        reply = next(r for r in events if r["text"] == "ORIGINAL_WRONG_REPLY_267")
        self.assertTrue(policy.allows(original))
        self.assertFalse(policy.allows(reply))
        self.assertFalse(any(r["text"] == "WRONG_SUMMARY_728" for r in policy.visible()))
        self.assertEqual([g["aspect"] for g in facts.listing(self.pack)["groups"]], ["养宠情况"])
        self.assertEqual([r["value"] for r in facts.listing(self.pack)["groups"][0]["claims"]], ["养猫"])

    def test_dependency_failure_does_not_propagate_backwards_but_explicit_forget_does(self):
        source = {"id": "raw", "source": "mind/experiences.jsonl", "depends_on": []}
        reply = {"id": "reply", "source": "mind/experiences.jsonl", "depends_on": ["raw"]}
        summary = {"id": "summary", "event_ids": ["raw", "reply"], "source": "mind/experiences.jsonl#raw",
                   "generation": {"context_dependencies": ["reply"]}}
        policy = MemoryPolicy([summary], [source, reply], {"reply"})
        self.assertFalse(policy.allows(summary))
        self.assertTrue(policy.allows(source))
        forgotten = MemoryPolicy([summary, {"id": "forget", "kind": "forget", "forgets": "summary"}], [source, reply])
        self.assertFalse(forgotten.allows(source))
        self.assertFalse(forgotten.allows(reply))

    def test_legacy_chat_extraction_dependency_can_be_read_without_rewriting_old_claims(self):
        original, result = self.proposal()
        reply = experience.record(self.pack, kind="conversation", text="旧版生成回复", day=1,
            source="mind/experiences.jsonl", depends_on=[original["id"]],
            metadata={"runner": "fixture", "context_dependencies": []})
        rows = facts.read(self.pack)
        claim = result["added"][0]
        next(r for r in rows if r["id"] == claim["id"])["generation"]["context_dependencies"] = [reply["id"]]
        write_file_atomic(facts.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        before = facts.path(self.pack).read_bytes()
        self.retract(claim)
        self.assertTrue(facts.path(self.pack).read_bytes().startswith(before))
        group = facts.context(self.pack, "居住地")["groups"][0]
        self.assertEqual(group["retraction_count"], 1)
        self.assertTrue(MemoryPolicy.load(self.pack).allows(original))

    def test_same_source_extraction_cannot_reappear_but_new_input_can_be_recorded(self):
        original, result = self.proposal()
        self.retract(result["added"][0])
        _, repeated = self.proposal(event=original)
        self.assertEqual(repeated["added"], [])
        _, fresh = self.proposal("我后来搬到杭州了。")
        self.assertEqual(len(fresh["added"]), 1)
        current = facts.listing(self.pack)["groups"][0]
        self.assertEqual(current["expected"], [fresh["added"][0]["id"]])

    def test_withdrawn_claim_is_not_a_historical_fact_and_cannot_be_revived_by_a_date_edit(self):
        _, result = self.proposal("假如从2020-01-01起住杭州，我会养猫。", starts_on="2020-01-01")
        claim = result["added"][0]
        details = fact_dates.detail(self.pack, claim["id"])
        self.retract(claim)
        self.assertEqual(fact_time.listing(self.pack, on="2020-06-01")["groups"], [])
        self.assertFalse(fact_dates.detail(self.pack, claim["id"])["editable"])
        with self.assertRaises(SeedError):
            fact_dates.perform(self.pack, {"target": claim["id"], "target_hash": details["target_hash"],
                "expected": details["expected"], "date": "2021-01-01", "reason": "不能复活"})

    def test_retracting_selected_claim_does_not_restore_previously_corrected_claim(self):
        old = self.add("成都")
        _, result = self.proposal()
        claim = result["added"][0]
        self.resolve(claim, kind="correction")
        self.retract(claim)
        self.assertEqual(facts.listing(self.pack)["groups"], [])
        self.assertEqual(fact_time.listing(self.pack, on="2020-06-01")["groups"], [])
        group = facts.listing(self.pack, audit=True)["groups"][0]
        self.assertFalse(next(r for r in group["history"] if r["id"] == old["id"])["recallable"])

    def test_stale_set_or_target_digest_is_rejected_before_a_request_is_prepared(self):
        _, result = self.proposal()
        claim = result["added"][0]
        data = self.data(claim)
        self.add("成都")
        with self.assertRaises(SeedError):
            facts.perform(self.pack, "retract", data)
        fresh = self.data(claim)
        with self.assertRaises(SeedError):
            facts.perform(self.pack, "retract", {**fresh, "target_hash": "0" * 64})
        self.assertEqual(requests.pending(self.pack), [])

    def test_retry_is_idempotent_and_completed_receipt_does_not_withdraw_new_input(self):
        _, result = self.proposal()
        data = self.data(result["added"][0])
        first = facts.perform(self.pack, "retract", data, request_id="repeat")
        fresh = self.add("成都")
        before = facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        repeated = facts.perform(self.pack, "retract", data, request_id="repeat")
        self.assertTrue(repeated["replayed"])
        self.assertEqual(first["record"], repeated["record"])
        self.assertEqual(before, (facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))
        self.assertEqual(facts.listing(self.pack)["groups"][0]["expected"], [fresh["id"]])
        with self.assertRaises(SeedError):
            facts.perform(self.pack, "retract", {**data, "reason": "另一条输入"}, request_id="repeat")

    def test_failed_write_preserves_input_and_backup_can_explicitly_resume(self):
        _, result = self.proposal()
        data = self.data(result["added"][0])
        before = facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        with patch("seedbank.facts._append", side_effect=OSError("fixture")), self.assertRaises(OSError):
            facts.perform(self.pack, "retract", data, request_id="recover")
        self.assertEqual(before, (facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))
        listing = facts.listing(self.pack)
        self.assertEqual(listing["pending"][0]["target_preview"]["quote"], "我不住杭州，也养猫。")
        saved = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(saved["file"], restored)
        response = Bridge(restored, "stub").handle({"op": "resume", "request_id": "recover"})
        self.assertTrue(response["ok"], response)
        self.assertEqual(facts.listing(restored)["groups"], [])
        self.assertEqual(len(facts.listing(self.pack)["groups"]), 1)

    def test_private_reason_does_not_leak_through_group_source(self):
        original, result = self.proposal(scope="qq-group:123")
        claim = result["added"][0]
        facts.perform(self.pack, "retract", self.data(claim, "PRIVATE_REASON_482"))
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        view = facts.context(self.pack, "居住地", policy=policy)
        recalled = search(self.pack, "杭州", use_semantic=False, policy=policy)
        self.assertEqual(view["groups"], [])
        self.assertNotIn("PRIVATE_REASON_482", json.dumps(recalled, ensure_ascii=False))
        self.assertTrue(policy.allows(original))

    def test_missing_or_changed_retraction_evidence_never_restores_old_claim(self):
        for mode in ("changed", "missing"):
            with self.subTest(mode=mode):
                _, result = self.proposal(aspect=mode)
                claim = result["added"][0]
                row = self.retract(claim)
                events = experience.read(self.pack)
                event_id = row["evidence"][0]["id"]
                if mode == "missing":
                    events = [r for r in events if r["id"] != event_id]
                else:
                    next(r for r in events if r["id"] == event_id)["text"] = "外部改动"
                write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in events))
                group = next(g for g in facts.listing(self.pack, audit=True)["groups"] if g["id"] == claim["slot"])
                self.assertEqual(group["claims"], [])
                self.assertTrue(group["history"][0]["unavailable"])
                self.assertFalse(group["retractions"][0]["available"])

    def test_forgetting_retraction_evidence_retires_derived_answer_without_restoring_claim(self):
        _, result = self.proposal()
        row = self.retract(result["added"][0])
        answer = self.reply("AFTER_RETRACTION_105")
        ref = row["evidence"][0]
        append_memories(self.pack, [{"id": "m_review", "day": 1, "kind": "thought", "text": "撤回依据",
            "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_review")
        self.assertEqual(facts.listing(self.pack)["groups"], [])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(answer))

    def test_cli_retraction_is_local_and_bridge_lists_history(self):
        _, result = self.proposal()
        data_file = self.folder / "retract.json"
        data_file.write_text(json.dumps(self.data(result["added"][0])), encoding="utf-8")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["facts", "retract", str(self.pack), "--data-file", str(data_file)]), 0)
        self.assertEqual(json.loads(output.getvalue())["record"]["kind"], "retract")
        response = Bridge(self.pack, "stub").handle({"op": "facts", "action": "list", "audit": True})
        self.assertTrue(response["ok"], response)
        self.assertTrue(response["facts"]["groups"][0]["history"][0]["retracted"])


if __name__ == "__main__":
    unittest.main()
