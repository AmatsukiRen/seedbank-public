"""User-run regressions for time-aware recollection. Authored, not executed."""
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
from seedbank import disclosure, experience, facts, fact_time
from seedbank.brain import RemoteBrain, build_chat_prompt
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import build_context, chat_turn, start_day, _context_dependencies
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.util import SeedError

ROOT = Path(__file__).resolve().parents[2]


class FactTimeTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="seedbank-fact-time-")
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        env = patch.dict(os.environ, {"HOME": str(self.folder / "home"), "USERPROFILE": str(self.folder / "home"),
                                     "SEEDBANK_LANG": "zh_CN"})
        env.start()
        self.addCleanup(env.stop)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No real service"))
        guard.start()
        self.addCleanup(guard.stop)
        self.pack = self.folder / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="time-fixture",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)

    def add(self, value, since="", aspect="居住地", **kwargs):
        data = {"subject": "owner", "aspect": aspect, "value": value}
        if since:
            data["starts_on"] = since
        return facts.perform(self.pack, "add", data, **kwargs)["record"]

    def resolve(self, chosen, date="", kind="change"):
        group = next(g for g in facts.listing(self.pack)["groups"] if g["id"] == chosen["slot"])
        return facts.perform(self.pack, "resolve", {"slot": group["id"], "expected": group["expected"],
            "selected": chosen["id"], "reason": "用户核对", "change_type": kind, "effective_on": date})["record"]

    def view(self, date="", **kwargs):
        return fact_time.listing(self.pack, on=date, **kwargs)["groups"][0]["temporal"]

    def context(self, message):
        return build_context(self.pack, self.day["dayNo"], self.day["date"], message, use_semantic=False)

    def test_missing_dates_are_not_filled_from_recording_time(self):
        self.add("杭州")
        view = self.view("2020-06-01")
        self.assertEqual(view["status"], "unknown")
        self.assertEqual(view["values"], [])
        self.assertEqual(view["records"][0]["starts_on"], "")
        self.assertTrue(view["records"][0]["recorded_at"])

    def test_change_separates_past_and_present_and_excludes_end_date(self):
        old = self.add("杭州", "2020-01-01")
        new = self.add("成都")
        decision = self.resolve(new, "2021-01-01")
        self.assertEqual(self.view("2020-06-01")["values"], ["杭州"])
        self.assertEqual(self.view("2021-01-01")["values"], ["成都"])
        self.assertEqual(self.view("2019-01-01")["status"], "unknown")
        refs = self.view("2020-06-01")["dependency_ids"]
        self.assertIn(old["evidence"][0]["id"], refs)
        self.assertIn(decision["evidence"][0]["id"], refs)
        self.assertEqual(facts.listing(self.pack)["groups"][0]["claims"][0]["value"], "成都")

    def test_unknown_first_date_does_not_extend_back_indefinitely(self):
        self.add("杭州")
        new = self.add("成都")
        self.resolve(new, "2021-01-01")
        self.assertEqual(self.view("2020-06-01")["status"], "unknown")
        self.assertEqual(self.view("2021-06-01")["values"], ["成都"])

    def test_unknown_change_date_does_not_become_recorded_date(self):
        self.add("杭州", "2020-01-01")
        new = self.add("成都")
        self.resolve(new)
        result = self.view("2021-06-01")
        self.assertEqual(result["values"], [])
        self.assertTrue(any("unknown_end" in r["reasons"] for r in result["records"]))

    def test_correction_never_relabels_wrong_claim_as_historical_truth(self):
        wrong = self.add("杭州", "2020-01-01")
        right = self.add("成都", "2020-01-01")
        self.resolve(right, kind="correction")
        result = self.view("2020-06-01")
        self.assertEqual(result["values"], ["成都"])
        self.assertNotIn(wrong["id"], {r["id"] for r in result["records"]})

    def test_corrected_transition_cannot_keep_asserting_old_date_boundary(self):
        self.add("杭州", "2020-01-01")
        wrong = self.add("成都")
        self.resolve(wrong, "2021-01-01")
        right = self.add("深圳")
        self.resolve(right, kind="correction")
        self.assertEqual(self.view("2021-06-01")["status"], "unknown")
        self.assertNotIn("成都", json.dumps(self.view(), ensure_ascii=False))

    def test_undated_competing_claim_keeps_uncertainty(self):
        self.add("杭州", "2020-01-01")
        self.add("成都")
        result = self.view("2020-06-01")
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["values"], [])

    def test_dated_overlap_is_conflict_and_repetition_does_not_vote(self):
        self.add("杭州", "2020-01-01")
        self.add("杭州", "2020-01-01")
        self.add("成都", "2021-01-01")
        self.assertEqual(self.view("2020-06-01")["values"], ["杭州"])
        self.assertEqual(self.view("2021-06-01")["status"], "conflict")

    def test_reversed_and_disagreeing_dates_do_not_produce_a_certain_value(self):
        self.add("杭州", "2022-01-01")
        new = self.add("成都", "2020-01-01")
        self.resolve(new, "2021-01-01")
        result = self.view("2021-06-01")
        self.assertNotEqual(result["status"], "reported")
        reasons = {reason for r in result["records"] for reason in r["reasons"]}
        self.assertIn("reversed_dates", reasons)
        self.assertIn("conflicting_start_dates", reasons)

    def test_multiple_changes_in_one_day_do_not_assert_whole_day_state(self):
        self.add("杭州", "2020-01-01")
        middle = self.add("成都")
        self.resolve(middle, "2021-01-01")
        final = self.add("深圳")
        self.resolve(final, "2021-01-01")
        self.assertEqual(self.view("2021-01-01")["status"], "uncertain")
        self.assertEqual(self.view("2021-01-02")["values"], ["深圳"])

    def test_hidden_candidates_keep_conflict_and_source_dependencies(self):
        rows = [self.add("杭州", "2020-01-01") for _ in range(9)]
        other = self.add("成都", "2020-01-01")
        group = facts.context(self.pack, "2020-06-01 居住地")["groups"][0]
        self.assertEqual(len(group["temporal"]["records"]), 8)
        self.assertEqual(group["temporal"]["status"], "conflict")
        deps = _context_dependencies({"facts": {"groups": [group]}})
        self.assertTrue({r["evidence"][0]["id"] for r in rows + [other]}.issubset(deps))

    def test_past_query_never_restores_forgotten_sources(self):
        self.add("杭州", "2020-01-01")
        group = facts.listing(self.pack)["groups"][0]
        facts.perform(self.pack, "forget", {"slot": group["id"], "expected": group["expected"], "reason": "放下"})
        self.assertEqual(fact_time.listing(self.pack, on="2020-06-01")["groups"], [])

    def test_a_generated_historical_answer_keeps_dependencies_for_later_withdrawal(self):
        old = self.add("杭州", "2020-01-01")
        new = self.add("成都")
        self.resolve(new, "2021-01-01")

        class OfflineBrain:
            name = "stub-time-fixture"

            def chat(self, ctx):
                return {"reply": "TIME_DERIVED_REPLY", "memory_writes": []}

        chat_turn(self.pack, "2020-06-01 我的居住地是哪里？", OfflineBrain())
        answer = next(r for r in experience.read(self.pack) if r["text"] == "TIME_DERIVED_REPLY")
        group = facts.listing(self.pack)["groups"][0]
        facts.perform(self.pack, "forget", {"slot": group["id"], "expected": group["expected"], "reason": "放下"})
        self.assertFalse(MemoryPolicy.load(self.pack).allows(answer))

    def test_private_dates_and_claims_do_not_enter_group_projection(self):
        self.add("PRIVATE_CITY", "2020-01-01")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        result = fact_time.listing(self.pack, on="2020-06-01", policy=policy)
        self.assertEqual(result["groups"], [])
        self.assertNotIn("PRIVATE_CITY", json.dumps(facts.context(self.pack, "居住地", policy=policy)))

    def test_literal_dates_and_model_extracted_dates_require_original_text(self):
        text = "从2020年1月1日起，我住在杭州。"
        event = experience.record(self.pack, kind="conversation", text=text, day=1, source="mind/experiences.jsonl", actor="user")
        proposal = {"subject": "owner", "aspect": "居住地", "value": "杭州", "quote": text, "starts_on": "2020-01-01"}
        saved = facts.apply_proposals(self.pack, [proposal], event=event, allowed_entities=["owner"], runner="fake")
        self.assertEqual(saved["added"][0]["starts_on"], "2020-01-01")
        self.assertEqual(saved["added"][0]["origin"], "model")
        rejected = facts.apply_proposals(self.pack, [{**proposal, "starts_on": "2021-01-01"}], event=event,
                                         allowed_entities=["owner"], runner="fake")
        self.assertEqual(rejected["rejected"], 1)
        self.assertEqual(fact_time.explicit_day("2020-01-01 和 2021-01-01"), "")
        self.assertEqual(fact_time.explicit_day("昨天"), "")
        self.assertEqual(fact_time.explicit_day("2020-02-30"), "")

    def test_invalid_or_future_dates_reject_before_writing(self):
        before = facts.path(self.pack).read_bytes() if facts.path(self.pack).exists() else None
        for value in ("2020-02-30", "9999-01-01", "2020-1-1", True):
            with self.subTest(value=value), self.assertRaises(SeedError):
                facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "杭州", "starts_on": value})
        self.assertEqual(facts.path(self.pack).read_bytes() if facts.path(self.pack).exists() else None, before)

    def test_same_request_cannot_silently_change_effective_date(self):
        self.add("杭州", "2020-01-01", request_id="dated-input")
        with self.assertRaises(SeedError):
            self.add("杭州", "2021-01-01", request_id="dated-input")

    def test_normal_chat_and_rephrased_search_use_target_date_not_record_date(self):
        self.add("杭州", "2020-01-01")
        new = self.add("成都")
        self.resolve(new, "2021-01-01")
        ctx = self.context("2020-06-01 我的居住地是哪里？")
        self.assertEqual(ctx["facts"]["on"], "2020-06-01")
        self.assertEqual(ctx["facts"]["groups"][0]["temporal"]["values"], ["杭州"])
        prompts = []

        def transport(cfg, system, user):
            prompts.append(system + user)
            return json.dumps({"memory_search": {"query": "居住地", "facts_on": "2020-06-01"}}
                              if len(prompts) == 1 else {"reply": "登记时间线显示当时是杭州。", "memory_writes": []}, ensure_ascii=False)

        result = RemoteBrain("openai-compatible", transport).chat({**ctx, "_cfg": {"model": "fixture", "input_budget": 64000}})
        self.assertFalse(result["_generation"].get("fallback", False))
        self.assertEqual(result["_used_facts"]["on"], "2020-06-01")
        self.assertEqual(result["_generation"]["fact_time"]["on"], "2020-06-01")
        self.assertEqual(result["_generation"]["fact_time"]["basis"], "model_search_date")
        self.assertEqual(result["_used_facts"]["groups"][0]["temporal"]["values"], ["杭州"])
        self.assertIn("recorded_at 只是保存时刻", prompts[-1])

    def test_read_only_bridge_cli_and_pagination_preserve_original_records(self):
        rows = [self.add("城市" + str(n), "2020-01-01") for n in range(32)]
        before = facts.path(self.pack).read_bytes()
        bridge = Bridge(self.pack, "stub")
        response = bridge.handle({"op": "facts", "action": "timeline", "on": "2020-06-01"})
        self.assertTrue(response["ok"], response)
        first = response["fact_time"]["groups"][0]["temporal"]
        second = fact_time.listing(self.pack, on="2020-06-01", slot=rows[0]["slot"], record_offset=30)["groups"][0]["temporal"]
        self.assertEqual((len(first["records"]), len(second["records"])), (30, 2))
        self.assertFalse({r["id"] for r in first["records"]} & {r["id"] for r in second["records"]})
        self.assertEqual(second["status"], "conflict")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["facts", "timeline", str(self.pack), "--on", "2020-06-01"]), 0)
        self.assertEqual(json.loads(output.getvalue())["on"], "2020-06-01")
        self.assertEqual(facts.path(self.pack).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
