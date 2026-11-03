"""User-run isolated tests for sourced claims. Authored, not executed."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import experience, facts, requests
from seedbank.brain import build_chat_prompt
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import build_context, chat_turn, forget_memory
from seedbank.memory_state import MemoryPolicy, describe
from seedbank.pack import hatch
from seedbank.retrieval import search
from seedbank.util import SeedError, append_memories, read_memories

ROOT = Path(__file__).resolve().parents[2]


class FactsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-facts-")
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"HOME": str(Path(folder.name) / "home"),
                                     "USERPROFILE": str(Path(folder.name) / "home"), "SEEDBANK_LANG": "zh_CN"})
        env.start()
        self.addCleanup(env.stop)
        self.pack = Path(folder.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="facts",
              born_at_override="2026-11-01T00:00:00Z")

    def add(self, value, aspect="居住地", subject="owner", **kwargs):
        return facts.perform(self.pack, "add", {"subject": subject, "aspect": aspect, "value": value}, **kwargs)["record"]

    def group(self, aspect="居住地", **kwargs):
        return next(g for g in facts.listing(self.pack, **kwargs)["groups"] if g["aspect"] == aspect)

    def resolve(self, chosen, **kwargs):
        group = self.group()
        payload = {"slot": group["id"], "expected": group["expected"], "selected": chosen["id"],
                   "reason": "核对原始情况", "change_type": "correction", **kwargs}
        return facts.perform(self.pack, "resolve", payload)

    def proposal(self, event, value="杭州", aspect="居住地", **extra):
        raw = {"subject": "owner", "aspect": aspect, "value": value, "quote": event["text"], **extra}
        return facts.apply_proposals(self.pack, [raw], event=event, allowed_entities=["owner", "self"], runner="fake")

    def test_empty_read_does_not_create_fact_file_or_call_a_model(self):
        with patch("seedbank.semantic._request", side_effect=AssertionError("no network")):
            self.assertEqual(facts.listing(self.pack)["groups"], [])
        self.assertFalse(facts.path(self.pack).exists())

    def test_different_values_remain_unresolved_and_repetition_does_not_vote(self):
        old = self.add("杭州")
        new = self.add("成都")
        self.add("成都")
        group = self.group()
        self.assertEqual(group["status"], "conflict")
        self.assertIn(old["id"], group["expected"])
        self.assertIn(new["id"], group["expected"])
        view = facts.context(self.pack, "居住地")
        self.assertEqual(view["groups"][0]["status"], "conflict")
        self.assertIn("不能按新旧", facts.prompt_lines(view))

    def test_user_resolution_keeps_original_bytes_and_is_only_a_reported_claim(self):
        old, new = self.add("杭州"), self.add("成都")
        before = facts.path(self.pack).read_bytes()
        self.resolve(new, change_type="change", effective_on="2026-10-31")
        group = self.group(audit=True)
        self.assertTrue(facts.path(self.pack).read_bytes().startswith(before))
        self.assertEqual(group["status"], "reported")
        self.assertEqual(group["expected"], [new["id"]])
        previous = next(r for r in group["history"] if r["id"] == old["id"])
        self.assertEqual(previous["change_type"], "change")
        self.assertEqual(previous["effective_on"], "2026-10-31")
        self.assertEqual(facts.context(self.pack, "居住地")["groups"][0]["decisions"][0]["change_type"], "change")

    def test_a_new_claim_reopens_disagreement_without_resurrecting_rejected_value(self):
        old, new = self.add("杭州"), self.add("成都")
        self.resolve(new)
        third = self.add("深圳")
        group = self.group()
        self.assertEqual(set(group["expected"]), {new["id"], third["id"]})
        self.assertNotIn(old["id"], group["expected"])
        self.assertEqual(group["status"], "conflict")

    def test_stale_decision_is_rejected_before_pending_request_or_writes(self):
        self.add("杭州")
        chosen = self.add("成都")
        old = self.group()
        self.add("深圳")
        before = facts.path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            facts.perform(self.pack, "resolve", {"slot": old["id"], "expected": old["expected"],
                          "selected": chosen["id"], "reason": "旧页面中的决定"})
        self.assertEqual(facts.path(self.pack).read_bytes(), before)
        self.assertEqual(requests.pending(self.pack), [])

    def test_retry_does_not_duplicate_claim_or_event(self):
        first = self.add("杭州", request_id="same")
        before = facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        repeated = self.add("杭州", request_id="same")
        self.assertEqual(first, repeated)
        self.assertEqual(before, (facts.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))

    def test_interrupted_user_edit_rolls_back_and_can_resume(self):
        before = experience.read(self.pack)
        with patch("seedbank.facts._append", side_effect=SeedError("injected")), self.assertRaises(SeedError):
            self.add("杭州", request_id="interrupted")
        self.assertEqual(experience.read(self.pack), before)
        self.assertTrue(requests.pending(self.pack))
        result = Bridge(self.pack, "stub").handle({"op": "resume", "request_id": "interrupted"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.group()["claims"]), 1)

    def test_model_values_require_literal_current_input_and_known_subject(self):
        event = experience.record(self.pack, kind="conversation", text="我住杭州。", actor="主人", day=1, source="life/0001-2026-11-01.md")
        self.assertEqual(len(self.proposal(event)["added"]), 1)
        self.assertEqual(self.proposal(event)["added"], [])
        for fields in ({"value": "成都"}, {"quote": "我住杭州且养猫。"}, {"subject": "a stranger"}, {"subject": []}):
            with self.subTest(fields=fields):
                self.assertEqual(self.proposal(event, **fields)["rejected"], 1)

    def test_dream_and_model_reply_are_not_new_source_evidence(self):
        for kind, metadata in (("dream", {}), ("conversation", {"runner": "fake"})):
            event = experience.record(self.pack, kind=kind, text="我住杭州。", actor="初", day=1,
                                      source="life/0001-2026-11-01.md", metadata=metadata)
            self.assertEqual(self.proposal(event)["added"], [])

    def test_changing_one_facet_preserves_other_facet_and_original_memory(self):
        event = experience.record(self.pack, kind="conversation", text="我住杭州，也养猫。", actor="主人", day=1, source="life/0001-2026-11-01.md")
        self.proposal(event)
        self.proposal(event, value="养猫", aspect="养宠情况")
        original = {"id": "m_two", "day": 1, "kind": "conversation", "text": event["text"],
                    "source": experience.source_of(event), "event_ids": [event["id"]]}
        append_memories(self.pack, [original])
        new = self.add("成都")
        self.resolve(new)
        self.assertEqual(self.group("养宠情况")["claims"][0]["value"], "养猫")
        self.assertEqual(next(r for r in read_memories(self.pack) if r["id"] == "m_two"), original)
        recalled = next(r["memory"] for r in search(self.pack, "养猫", k=100) if r["memory"]["id"] == "m_two")
        self.assertIn("成都", describe(recalled))
        self.assertIn("单项核对", describe(recalled))

    def test_same_value_in_two_different_facets_is_not_deduplicated(self):
        event = experience.record(self.pack, kind="conversation", text="出生地和居住地都是杭州。", actor="主人", day=1, source="life/0001-2026-11-01.md")
        raw = [{"subject": "owner", "aspect": a, "value": "杭州", "quote": event["text"]} for a in ("出生地", "居住地")]
        result = facts.apply_proposals(self.pack, raw, event=event, allowed_entities=["owner"], runner="fake")
        self.assertEqual(len(result["added"]), 2)

    def test_automatic_whole_memory_correction_cannot_bypass_fact_disagreement(self):
        from seedbank.cognition import _apply_corrections
        old = self.add("杭州")
        self.add("成都")
        ref = old["evidence"][0]
        memory = {"id": "m_old", "day": 1, "text": "杭州", "kind": "conversation", "source": ref["source"], "event_ids": [ref["id"]]}
        append_memories(self.pack, [memory])
        result = _apply_corrections(self.pack, {"corrections": [{"target_id": "m_old", "new": "成都", "reason": "模型认为更新的就对"}]},
                                    {"evidence": [memory], "current_evidence": []}, {"dayNo": 1}, "life/0001-2026-11-01.md", "fake")
        self.assertEqual(result, [])
        self.assertEqual(self.group()["status"], "conflict")
        self.assertNotIn("m_old", MemoryPolicy.load(self.pack).superseded)

    def test_forget_propagates_to_original_and_generated_descendants_but_keeps_audit(self):
        claim = self.add("唯一住址标记")
        ref = claim["evidence"][0]
        reply = experience.record(self.pack, kind="conversation", text="你住唯一住址标记", actor="初", day=1,
                                  source="life/0001-2026-11-01.md", depends_on=[ref["id"]])
        append_memories(self.pack, [{"id": "m_derived", "day": 1, "text": "唯一住址标记", "kind": "conversation",
                                    "source": experience.source_of(reply), "depends_on": [ref["id"]]}])
        group = self.group()
        facts.perform(self.pack, "forget", {"slot": group["id"], "expected": group["expected"], "reason": "不再主动提起"})
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(ref["id"], policy.blocked)
        self.assertIn(reply["id"], policy.blocked)
        self.assertEqual(search(self.pack, "唯一住址标记", historical=True), [])
        self.assertEqual(facts.listing(self.pack)["groups"], [])
        self.assertEqual(self.group(audit=True)["history"][0]["value"], "唯一住址标记")

    def test_memory_forget_suppresses_linked_fact_without_resurrecting_old_state(self):
        self.add("杭州")
        current = self.add("成都")
        self.resolve(current)
        ref = current["evidence"][0]
        append_memories(self.pack, [{"id": "m_source", "day": 1, "text": "成都", "kind": "conversation",
                                    "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_source")
        self.assertEqual(facts.listing(self.pack)["groups"], [])
        self.assertEqual(self.group(audit=True)["status"], "unavailable")

    def test_distinct_entities_and_exact_numbers_do_not_merge(self):
        a = facts.perform(self.pack, "entity", {"label": "小张（同事）"})["record"]["id"]
        b = facts.perform(self.pack, "entity", {"label": "小张（邻居）"})["record"]["id"]
        self.add("00120", aspect="编号", subject=a)
        self.add("120", aspect="编号", subject=b)
        groups = facts.listing(self.pack)["groups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(g["status"] == "reported" for g in groups))
        self.add("120", aspect="编号", subject=a)
        self.assertEqual(facts.listing(self.pack)["conflicts"], 1)
        with self.assertRaises(SeedError):
            facts.perform(self.pack, "entity", {"label": "小张（同事）"})

    def test_malformed_file_is_preserved_instead_of_silently_becoming_no_conflict(self):
        self.add("杭州")
        with facts.path(self.pack).open("ab") as stream:
            stream.write(b"{broken\n")
        before = facts.path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            facts.listing(self.pack)
        with self.assertRaises(SeedError):
            self.add("成都")
        self.assertEqual(facts.path(self.pack).read_bytes(), before)

    def test_chat_pipeline_and_later_context_include_sourced_claims(self):
        class Fake:
            name = "fake"
            def chat(self, ctx):
                return {"reply": "我会保留原话。", "memory_writes": [], "fact_claims": [
                    {"subject": "owner", "aspect": "居住地", "value": "杭州", "quote": ctx["message"]}]}
        result = chat_turn(self.pack, "我住杭州。", Fake())
        self.assertEqual(result["factsAdded"], 1)
        ctx = build_context(self.pack, result["dayNo"], result["date"], "居住地", use_semantic=False)
        self.assertIn("杭州", build_chat_prompt(ctx)["system"])
        self.assertEqual(ctx["facts"]["groups"][0]["claims"][0]["origin"], "model")

    def test_limited_candidates_keep_conflict_and_full_count(self):
        for _ in range(4):
            self.add("杭州")
        self.add("成都")
        group = facts.context(self.pack, "居住地")["groups"][0]
        self.assertEqual(len(group["claims"]), 4)
        self.assertEqual(group["candidate_count"], 5)
        self.assertEqual(group["status"], "conflict")
        self.assertEqual({r["value"] for r in group["claims"]}, {"杭州"})

    def test_budget_removes_whole_fact_groups_without_mutating_original(self):
        from copy import deepcopy
        from seedbank.context_window import fit
        group = {"subject": "owner", "status": "conflict", "candidate_count": 6,
                 "claims": [{"quote": "原文" * 400}]}
        ctx = {"_cfg": {"input_budget": 2048}, "facts": {"groups": [deepcopy(group) for _ in range(8)],
               "entities": [{"id": "owner", "label": "用户"}]}}
        before = deepcopy(ctx)
        _, selected, _ = fit(ctx, lambda c: {"system": json.dumps(c["facts"], ensure_ascii=False), "user": "问题"})
        self.assertEqual(ctx, before)
        self.assertTrue(selected["facts"]["omitted"])
        self.assertTrue(all(g["status"] == "conflict" and g["candidate_count"] == 6 for g in selected["facts"]["groups"]))

    def test_bridge_and_cli_lists_are_local_and_support_audit(self):
        self.add("杭州")
        with patch("seedbank.semantic._request", side_effect=AssertionError("no network")):
            result = Bridge(self.pack, "stub").handle({"op": "facts", "audit": True})
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["facts"]["groups"][0]["history"])
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["facts", "list", str(self.pack), "--query", "杭州"]), 0)
            self.assertEqual(json.loads(output.getvalue())["total"], 1)


if __name__ == "__main__":
    unittest.main()
