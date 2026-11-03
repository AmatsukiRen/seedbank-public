"""User-run date revision regressions. No tests have been executed by the agent."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

import test_fact_time as fixtures
from seedbank import backup, disclosure, experience, fact_dates, fact_time, facts, requests
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import chat_turn, forget_memory
from seedbank.memory_state import MemoryPolicy
from seedbank.retrieval import search
from seedbank.util import SeedError, append_memories, write_file_atomic


class FactDatesTest(unittest.TestCase):
    setUp = fixtures.FactTimeTest.setUp
    add = fixtures.FactTimeTest.add
    resolve = fixtures.FactTimeTest.resolve
    view = fixtures.FactTimeTest.view
    context = fixtures.FactTimeTest.context

    def data(self, target, date="2020-01-01", reason="根据原始材料核对日期"):
        current = fact_dates.detail(self.pack, target)
        return {"target": target, "target_hash": current["target_hash"], "expected": current["expected"],
                "date": date, "reason": reason}

    def amend(self, target, date="2020-01-01", **kwargs):
        return fact_dates.perform(self.pack, self.data(target, date), **kwargs)["record"]

    def reply(self, text):
        class OfflineBrain:
            name = "stub-date-revision-fixture"

            def chat(self, ctx):
                return {"reply": text, "memory_writes": []}

        chat_turn(self.pack, "2020-06-01 我的居住地是什么？", OfflineBrain())
        return next(r for r in experience.read(self.pack) if r["text"] == text)

    def test_amending_historical_start_keeps_raw_bytes_and_current_choice(self):
        old = self.add("杭州")
        new = self.add("成都")
        self.resolve(new, "2021-01-01")
        self.assertEqual(self.view("2020-06-01")["status"], "unknown")
        before = facts.path(self.pack).read_bytes()
        original_event = next(r for r in experience.read(self.pack) if r["id"] == old["evidence"][0]["id"])
        revision = self.amend(old["id"])
        self.assertTrue(facts.path(self.pack).read_bytes().startswith(before))
        self.assertEqual(next(r for r in experience.read(self.pack) if r["id"] == original_event["id"]), original_event)
        self.assertEqual(self.view("2020-06-01")["values"], ["杭州"])
        self.assertEqual(facts.listing(self.pack)["groups"][0]["claims"][0]["id"], new["id"])
        self.assertEqual(revision["format"], "seedbank/facts@2")
        self.assertEqual(fact_dates.detail(self.pack, old["id"])["versions"][0]["id"], revision["id"])

    def test_amending_transition_updates_both_adjacent_ranges(self):
        old, new = self.add("杭州", "2020-01-01"), self.add("成都")
        transition = self.resolve(new, "2021-01-01")
        self.amend(transition["id"], "2022-01-01")
        self.assertEqual(self.view("2021-06-01")["values"], ["杭州"])
        self.assertEqual(self.view("2022-01-01")["values"], ["成都"])
        original = next(r for r in facts.read(self.pack) if r["id"] == transition["id"])
        self.assertEqual(original["effective_on"], "2021-01-01")
        self.assertEqual(original["selected"], new["id"])
        self.assertEqual({r["id"] for r in fact_dates.detail(self.pack, old["id"])["related"]}, {old["id"], transition["id"]})

    def test_date_can_be_cleared_without_restoring_original_date(self):
        row = self.add("杭州", "2020-01-01")
        self.amend(row["id"], "")
        self.assertEqual(self.view("2020-06-01")["status"], "unknown")
        details = fact_dates.detail(self.pack, row["id"])
        self.assertEqual(details["date"], "")
        self.assertEqual(details["original_date"], "2020-01-01")
        self.assertEqual(details["date_state"], "revised")

    def test_stale_editor_and_reused_request_content_are_rejected(self):
        row = self.add("杭州")
        stale = self.data(row["id"])
        fact_dates.perform(self.pack, stale, request_id="date-once")
        with self.assertRaises(SeedError):
            fact_dates.perform(self.pack, {**stale, "date": "2021-01-01"})
        with self.assertRaises(SeedError):
            fact_dates.perform(self.pack, {**stale, "reason": "其他输入"}, request_id="date-once")
        before = facts.path(self.pack).read_bytes()
        replay = fact_dates.perform(self.pack, stale, request_id="date-once")
        self.assertTrue(replay["replayed"])
        self.assertEqual(facts.path(self.pack).read_bytes(), before)

    def test_completed_replay_does_not_overwrite_later_date(self):
        row = self.add("杭州")
        first = self.data(row["id"])
        fact_dates.perform(self.pack, first, request_id="first-date")
        self.amend(row["id"], "2021-01-01")
        replay = fact_dates.perform(self.pack, first, request_id="first-date")
        self.assertEqual(replay["record"]["date"], "2020-01-01")
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date"], "2021-01-01")

    def test_partial_write_rolls_back_but_keeps_pending_input_for_resume(self):
        row = self.add("杭州")
        data = self.data(row["id"])
        before, events = facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        with patch("seedbank.facts._append", side_effect=OSError("fixture write failure")), self.assertRaises(OSError):
            fact_dates.perform(self.pack, data, request_id="interrupted-date")
        self.assertEqual(facts.path(self.pack).read_bytes(), before)
        self.assertEqual(experience.path(self.pack).read_bytes(), events)
        self.assertEqual(requests.get(self.pack, "interrupted-date")["status"], "pending")
        result = Bridge(self.pack, "stub").handle({"op": "resume", "request_id": "interrupted-date"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.view("2020-06-01")["values"], ["杭州"])

    def test_known_old_generated_answers_retire_but_inputs_and_new_answers_remain(self):
        row = self.add("杭州", "2020-01-01")
        old_answer = self.reply("OLD_DATE_DERIVED_721")
        self.assertTrue(any("OLD_DATE_DERIVED_721" in r["memory"]["text"] for r in search(self.pack, "OLD_DATE_DERIVED_721", use_semantic=False)))
        # The cutoff is append order, not a wall clock which could move backward.
        with patch("seedbank.experience.now_iso", return_value="1900-01-01T00:00:00Z"):
            self.amend(row["id"], "2021-01-01")
        new_answer = self.reply("NEW_DATE_DERIVED_913")
        policy = MemoryPolicy.load(self.pack)
        self.assertFalse(policy.allows(old_answer))
        self.assertTrue(policy.allows(new_answer))
        original = next(r for r in experience.read(self.pack) if r["id"] == row["evidence"][0]["id"])
        self.assertTrue(policy.allows(original))
        self.assertFalse(any("OLD_DATE_DERIVED_721" in r["memory"]["text"] for r in search(self.pack, "OLD_DATE_DERIVED_721", use_semantic=False)))

    def test_old_date_revision_is_not_recalled_as_current_evidence(self):
        row = self.add("杭州")
        first = self.amend(row["id"], "2020-01-01")
        second = self.amend(row["id"], "2021-01-01")
        policy = MemoryPolicy.load(self.pack)
        events = {r["id"]: r for r in experience.read(self.pack)}
        self.assertFalse(policy.allows(events[first["evidence"][0]["id"]]))
        self.assertTrue(policy.allows(events[second["evidence"][0]["id"]]))
        self.assertEqual(len(fact_dates.detail(self.pack, row["id"])["versions"]), 2)

    def test_amending_date_retires_direct_generated_reply_without_retiring_raw_source(self):
        row = self.add("杭州", "2020-01-01")
        original = next(r for r in experience.read(self.pack) if r["id"] == row["evidence"][0]["id"])
        reply = experience.record(self.pack, kind="conversation", text="原日期的生成回复", day=1,
            source="mind/experiences.jsonl", depends_on=[original["id"]],
            metadata={"runner": "fixture", "context_dependencies": []})
        append_memories(self.pack, [{"id": "m_shared_source", "day": 1, "kind": "thought", "text": "旧日期摘要",
            "source": experience.source_of(original), "event_ids": [original["id"], reply["id"]],
            "generation": {"context_dependencies": [reply["id"]]}}])
        self.amend(row["id"], "2021-01-01")
        policy = MemoryPolicy.load(self.pack)
        self.assertFalse(policy.allows(reply))
        self.assertTrue(policy.allows(original))
        self.assertEqual(self.view("2021-06-01")["values"], ["杭州"])

    def test_withdrawn_latest_date_never_falls_back_and_can_receive_new_evidence(self):
        row = self.add("杭州", "2019-01-01")
        revision = self.amend(row["id"], "2020-01-01")
        ref = revision["evidence"][0]
        append_memories(self.pack, [{"id": "m_date_source", "day": 1, "kind": "thought", "text": "日期依据",
                                    "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_date_source")
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date_state"], "unavailable")
        self.assertEqual(self.view("2020-06-01")["status"], "unknown")
        self.amend(row["id"], "2020-02-01")
        self.assertEqual(self.view("2020-06-01")["values"], ["杭州"])

    def test_original_recalled_prose_has_latest_date_annotation(self):
        row = self.add("杭州", "2020-01-01")
        self.amend(row["id"], "2021-01-01")
        result = next(r for r in search(self.pack, "杭州", use_semantic=False) if r["memory"]["id"] == row["evidence"][0]["id"])
        note = result["memory"]["fact_notes"][0]
        self.assertTrue(note["time_revised"])
        self.assertEqual(note["date_notes"][0]["date"], "2021-01-01")

    def test_private_date_amendment_does_not_leak_through_public_claim(self):
        metadata = disclosure.stamp("qq-group:123")
        event = experience.record(self.pack, kind="conversation", text="从2020-01-01起住杭州", day=1,
                                  source="mind/experiences.jsonl", actor="user", metadata=metadata)
        row = facts.apply_proposals(self.pack, [{"subject": "owner", "aspect": "居住地", "value": "杭州",
                    "quote": event["text"], "starts_on": "2020-01-01"}], event=event, allowed_entities=["owner"],
                    runner="fixture", generation=metadata)["added"][0]
        self.amend(row["id"], "2022-02-02")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        view = fact_time.listing(self.pack, on="2020-06-01", policy=policy)
        self.assertEqual(view["groups"][0]["temporal"]["status"], "unknown")
        self.assertNotIn("2022-02-02", json.dumps(view))
        self.assertEqual(view["pending"], [])

    def test_wrong_or_forgotten_claim_cannot_be_revived_by_changing_date(self):
        wrong, right = self.add("杭州"), self.add("成都")
        before = self.data(wrong["id"])
        self.resolve(right, kind="correction")
        with self.assertRaises(SeedError):
            fact_dates.perform(self.pack, before)
        group = facts.listing(self.pack)["groups"][0]
        data = self.data(right["id"])
        facts.perform(self.pack, "forget", {"slot": group["id"], "expected": group["expected"], "reason": "放下"})
        with self.assertRaises(SeedError):
            fact_dates.perform(self.pack, data)

    def test_modified_amendment_input_makes_latest_date_unavailable(self):
        row = self.add("杭州", "2019-01-01")
        revision = self.amend(row["id"], "2020-01-01")
        answer = self.reply("ANSWER_BEFORE_DATE_SOURCE_CHANGED")
        events = experience.read(self.pack)
        next(r for r in events if r["id"] == revision["evidence"][0]["id"])["text"] = "changed outside the app"
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in events))
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date_state"], "unavailable")
        self.assertEqual(self.view("2020-06-01")["status"], "unknown")
        self.assertFalse(MemoryPolicy.load(self.pack).allows(answer))

    def test_repair_after_a_missing_old_revision_does_not_retire_new_answers_forever(self):
        row = self.add("杭州")
        revision = self.amend(row["id"], "2020-01-01")
        missing = revision["evidence"][0]["id"]
        events = [r for r in experience.read(self.pack) if r["id"] != missing]
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in events))
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date_state"], "unavailable")
        self.amend(row["id"], "2020-02-01")
        answer = self.reply("ANSWER_AFTER_NEW_DATE_EVIDENCE")
        self.assertTrue(MemoryPolicy.load(self.pack).allows(answer))
        self.assertEqual(self.view("2020-06-01")["values"], ["杭州"])

    def test_missing_date_field_cannot_accidentally_clear_a_date(self):
        row = self.add("杭州", "2020-01-01")
        data = self.data(row["id"])
        del data["date"]
        with self.assertRaises(SeedError):
            fact_dates.perform(self.pack, data)
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date"], "2020-01-01")

    def test_backup_preserves_pending_date_input_and_explicit_resume(self):
        row = self.add("杭州")
        data = self.data(row["id"])
        with patch("seedbank.facts._append", side_effect=OSError("fixture")), self.assertRaises(OSError):
            fact_dates.perform(self.pack, data, request_id="date-backup")
        saved = backup.create(self.pack)
        target = self.folder / "restored.life"
        backup.restore(saved["file"], target)
        self.assertEqual(requests.get(target, "date-backup")["status"], "pending")
        response = Bridge(target, "stub").handle({"op": "resume", "request_id": "date-backup"})
        self.assertTrue(response["ok"], response)
        self.assertEqual(fact_dates.detail(target, row["id"])["date"], "2020-01-01")
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date"], "")

    def test_cli_and_bridge_expose_date_versions_without_model_calls(self):
        row = self.add("杭州")
        response = Bridge(self.pack, "stub").handle({"op": "facts", "action": "date_detail", "target": row["id"]})
        self.assertTrue(response["ok"], response)
        data_file = self.folder / "date.json"
        data_file.write_text(json.dumps(self.data(row["id"])), encoding="utf-8")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["facts", "date", str(self.pack), "--data-file", str(data_file)]), 0)
        self.assertEqual(json.loads(output.getvalue())["record"]["date"], "2020-01-01")


if __name__ == "__main__":
    unittest.main()
