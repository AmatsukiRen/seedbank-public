"""User-run regressions only. Temporary archives and local fixture models."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_daily_choices as fixtures
import test_learning as learning_fixtures
from seedbank import agency, backup, cognition, deliberation, development, experience, learning, plan_checkpoints, plan_links, planning, works
from seedbank.disclosure import policy_for
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories, read_json


class PlanCheckpointsTest(unittest.TestCase):
    goal = fixtures.DailyChoicesTest.goal
    context = fixtures.DailyChoicesTest.context
    proposal = fixtures.DailyChoicesTest.proposal
    choose = fixtures.DailyChoicesTest.choose
    execute = fixtures.DailyChoicesTest.execute
    plan = learning_fixtures.LearningTest.plan
    practice = learning_fixtures.LearningTest.practice
    review = learning_fixtures.LearningTest.review
    listing = learning_fixtures.LearningTest.listing

    def setUp(self):
        fixtures.DailyChoicesTest.setUp(self)
        self.brain = fixtures.Brain()
        self.target = self.plan()

    def select(self, **extra):
        raw = self.proposal(goal=self.target, checkpoint={"criteria_id": self.listing(self.target)["criteria"]["id"]}, **extra)
        result = self.choose(raw)
        self.assertEqual(result["status"], "accepted", result)
        return result["plan"]

    def assess(self, plan=None):
        return plan_checkpoints.for_plan(self.pack, plan or agency.current_plan(self.pack, self.day["dayNo"]))

    def revise(self, items):
        return self.plan(items, goal_id=self.target, expected=self.listing(self.target)["goal"]["event_id"])

    def test_success_requires_current_feedback_then_waits_for_next_choice(self):
        selected = self.select()
        self.assertFalse(self.assess()["passed"])
        receipt = self.execute(self.brain, self.target)
        self.assertEqual(receipt["data"]["status"], "succeeded")
        self.assertFalse(self.assess()["passed"])
        feedback = self.review(self.target, receipt["id"])
        checked = self.assess()
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["matches"][0]["outcome_id"], receipt["id"])
        self.assertEqual(checked["matches"][0]["checks"][0]["feedback_id"], feedback["id"])
        self.assertFalse(agency.current_plan(self.pack, self.day["dayNo"])["done"])
        self.assertEqual(self.listing(self.target)["goal"]["status"], "active")
        count = self.brain.compositions
        blocked = self.execute(self.brain, self.target)
        self.assertEqual(blocked["data"]["status"], "blocked")
        self.assertEqual(self.brain.compositions, count)
        self.assertIn(feedback["evidence"][0]["id"], {r["id"] for r in blocked["data"]["evidence"]})
        ctx = self.context()
        self.assertTrue(ctx["choice_pending"])
        self.assertIn("条件已满足", ctx["plan"])
        self.assertIn(feedback["evidence"][0]["id"], cognition._context_dependencies(ctx))
        repeated = self.choose(self.proposal(goal=self.target, checkpoint={"criteria_id": checked["criteria_id"]}))
        self.assertEqual(repeated["status"], "unchanged")
        self.assertTrue(self.assess()["passed"])
        self.choose(self.proposal("open"))
        self.assertEqual(self.execute(self.brain, self.target)["data"]["status"], "succeeded")
        self.assertTrue(self.assess(selected)["passed"])

    def test_only_complete_offered_current_rubric_can_be_bound(self):
        rubric = self.listing(self.target)["criteria"]["id"]
        raw = self.proposal(goal=self.target, checkpoint={"criteria_id": rubric})
        ctx = self.context()
        ctx["learning"] = []
        cases = [(raw, ctx), (self.proposal(goal=self.first, checkpoint={"criteria_id": rubric}), None),
                 (self.proposal("rest", checkpoint={"criteria_id": rubric}), None),
                 ({**raw, "checkpoint": {"criteria_id": rubric, "items": ["c1"]}}, None),
                 ({**raw, "checkpoint": {"criteria_id": "l_missing"}}, None)]
        before = planning.path(self.pack).read_bytes()
        for proposal, context in cases:
            with self.subTest(proposal=proposal):
                self.assertEqual(self.choose(proposal, ctx=context)["status"], "rejected")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)

    def test_actual_trimmed_learning_is_used_in_chat_initiation_and_diary(self):
        raw = self.proposal(goal=self.target, checkpoint={"criteria_id": self.listing(self.target)["criteria"]["id"]})
        brain = fixtures.Brain({"reply": "今天想试试。", "daily_plan": raw, "_used_learning": []})
        result = cognition.chat_turn(self.pack, "今天做什么？", brain)
        self.assertEqual(result["planDecision"]["status"], "rejected")
        result = cognition.maybe_initiate(self.pack, brain, force=True)
        self.assertEqual(result["planDecision"]["status"], "rejected")
        before = agency.current_plan(self.pack, self.day["dayNo"])["plan_id"]
        cognition.run_days(self.pack, 1, brain)
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["plan_id"], before)
        self.assertFalse(any(row.get("plan", {}).get("checkpoint") for row in planning.read(self.pack)))

    def test_old_and_other_plan_results_do_not_finish_new_arrangement(self):
        old = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, old)
        first = self.select()
        self.assertFalse(self.assess()["passed"])
        current = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, current)
        self.assertTrue(self.assess()["passed"])
        second = self.select(next_step="换一种表达，再完成一份新成果")
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        self.assertFalse(self.assess()["passed"])
        self.assertTrue(self.assess(first)["passed"])

    def test_same_result_must_meet_all_conditions_for_one_deliverable(self):
        self.revise([{"text": "具体事情", "group": "信"}, {"text": "具体感受", "group": "信"}])
        self.select()
        first = self.practice(self.target)["receipt"]["id"]
        second = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, first, {"c1": "met", "c2": "not_met"})
        self.review(self.target, second, {"c1": "not_met", "c2": "met"})
        self.assertFalse(self.assess()["passed"])
        self.review(self.target, second, {"c1": "met", "c2": "met"})
        self.assertTrue(self.assess()["passed"])

    def test_distinct_deliverables_use_distinct_results_with_matching(self):
        self.revise([{"text": "第一份成果", "group": "第一封"}, {"text": "第二份成果", "group": "第二封"}])
        self.select()
        first = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, first, {"c1": "met", "c2": "met"})
        self.assertEqual(self.assess()["reason"], "distinct_results_required")
        second = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, second, {"c1": "met", "c2": "not_met"})
        report = self.assess()
        self.assertTrue(report["passed"])
        self.assertEqual({m["outcome_id"] for m in report["matches"]}, {first, second})

    def test_corrected_feedback_and_changed_work_revoke_current_match(self):
        self.select()
        result = self.practice(self.target)
        outcome = result["receipt"]["id"]
        self.review(self.target, outcome)
        self.assertTrue(self.assess()["passed"])
        self.review(self.target, outcome, {"c1": "not_met"}, reason="重新核对后不满足条件")
        self.assertFalse(self.assess()["passed"])
        self.review(self.target, outcome)
        saved = works.load_works(self.pack)
        saved["works"][0]["text"] += " changed fixture"
        works.save_works(self.pack, saved)
        self.assertFalse(self.assess()["passed"])

    def test_changed_criteria_require_new_binding_and_do_not_rewrite_history(self):
        selected = self.select()
        prior = deepcopy(selected["checkpoint"])
        self.revise([{"text": "新增具体细节", "group": "信"}])
        self.assertEqual(self.assess(selected)["state"], "criteria_changed")
        self.assertEqual(self.execute(self.brain, self.target)["data"]["status"], "blocked")
        new = self.select()
        self.assertNotEqual(new["checkpoint"], prior)
        self.assertEqual(next(row for row in planning.read(self.pack) if row["id"] == selected["plan_id"])["plan"]["checkpoint"], prior)

    def test_failed_attempt_never_meets_artifact_condition(self):
        self.revise([{"check": "artifact", "artifact_kind": "letter", "group": "信"}])
        self.select()
        with patch.object(self.brain, "compose", return_value={}):
            self.assertFalse(self.practice(self.target)["succeeded"])
        self.assertFalse(self.assess()["passed"])
        self.assertTrue(self.practice(self.target)["succeeded"])
        self.assertTrue(self.assess()["passed"])

    def test_rubric_storage_error_stops_before_dispatch_without_invented_outcome(self):
        self.select()
        before = development.load_development(self.pack)["outcomes"]
        with patch("seedbank.learning.view", side_effect=OSError("unreadable rubric")), self.assertRaises(OSError):
            self.execute(self.brain, self.target)
        self.assertEqual(self.brain.compositions, 0)
        self.assertEqual(development.load_development(self.pack)["outcomes"], before)

    def test_receipt_day_or_digest_mismatch_never_counts(self):
        selected = self.select()
        outcome = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, outcome)
        entry = next(row for row in planning.read(self.pack) if row["id"] == selected["plan_id"])
        for field, value in (("day", self.day["dayNo"] + 1), ("entry_sha256", "0" * 64)):
            loaded = learning.view(self.pack)
            loaded["outcomes"][outcome]["plan_reference"][field] = value
            self.assertFalse(plan_checkpoints.evaluate(self.pack, entry, loaded=loaded, policy=MemoryPolicy.load(self.pack))["passed"])

    def test_feedback_source_withdrawal_hides_current_match_and_derived_claim(self):
        self.select()
        outcome = self.practice(self.target)["receipt"]["id"]
        feedback = self.review(self.target, outcome)
        source = feedback["evidence"][0]
        ctx = self.context()
        derived = experience.record(self.pack, kind="thought", text="本次条件满足的解释", day=self.day["dayNo"],
            source="art/checkpoint-review.txt", actor="model", depends_on=cognition._context_dependencies(ctx))
        append_memories(self.pack, [{"id": "m_checkpoint_feedback", "day": self.day["dayNo"], "kind": "thought",
            "text": "fixture feedback", "source": source["source"], "event_ids": [source["id"]]}])
        cognition.forget_memory(self.pack, "m_checkpoint_feedback")
        self.assertFalse(self.assess()["passed"])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertIn(feedback["id"], {row["id"] for row in learning.read(self.pack)})

    def test_private_checkpoint_is_not_exposed_and_external_action_uses_generic_hold(self):
        selected = self.select()
        outcome = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, outcome)
        policy = policy_for(self.pack, "qq-group:123", "owner")
        self.assertEqual(plan_checkpoints.for_plan(self.pack, selected, policy=policy), {})
        self.assertEqual(development.summary(self.pack, policy=policy)["plan_review"], [])
        reason = deliberation.blocked_reason(self.pack, day=self.day["dayNo"], action="compose", goal_id=self.target,
            policy=policy, audience_id="qq-group:123")
        self.assertEqual(reason, deliberation.EXTERNAL_BLOCKED)

    def test_read_only_projection_backup_and_marker_keep_version_three(self):
        selected = self.select()
        outcome = self.practice(self.target)["receipt"]["id"]
        self.review(self.target, outcome)
        before = planning.path(self.pack).read_bytes()
        for _ in range(2):
            rows = development.summary(self.pack)["plan_review"]
            self.assertIn("条件已满足", "\n".join(plan_links.display_lines(rows)))
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.choose(self.proposal("open"))
        agency.plan_for_day(self.pack, self.day["dayNo"] + 1)
        self.assertEqual(read_json(agency.agency_path(self.pack))["plan_store"], planning.CHECKPOINT_FORMAT)
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertTrue(plan_checkpoints.for_plan(restored, selected)["passed"])

    def test_corrupt_binding_and_failed_choice_write_preserve_originals(self):
        before = planning.path(self.pack).read_bytes()
        events = experience.read(self.pack)
        original = planning.choose
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("fixture interrupted after plan write")
        with patch("seedbank.planning.choose", side_effect=fail), self.assertRaises(OSError):
            self.select()
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(experience.read(self.pack), events)
        self.select()
        rows = planning.read(self.pack)
        rows[-1]["plan"]["checkpoint"]["criteria_sha256"] = "invalid"
        planning.path(self.pack).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        bad = planning.path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            agency.load_agency(self.pack)
        self.assertEqual(planning.path(self.pack).read_bytes(), bad)


if __name__ == "__main__":
    unittest.main()
