"""Authored for user execution only; temporary packs and fixture models."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_daily_choices as fixtures
import test_learning as learning_fixtures
from seedbank import agency, backup, cognition, deliberation, development, experience, learning, plan_checkpoints, plan_continuity, plan_links, planning, requests
from seedbank.context_window import fit
from seedbank.disclosure import policy_for
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories, read_json


class PlanContinuityTest(unittest.TestCase):
    setUp = fixtures.DailyChoicesTest.setUp
    goal = fixtures.DailyChoicesTest.goal
    context = fixtures.DailyChoicesTest.context
    proposal = fixtures.DailyChoicesTest.proposal
    choose = fixtures.DailyChoicesTest.choose
    execute = fixtures.DailyChoicesTest.execute
    plan = learning_fixtures.LearningTest.plan
    practice = learning_fixtures.LearningTest.practice
    review = learning_fixtures.LearningTest.review
    listing = learning_fixtures.LearningTest.listing

    def next_day(self):
        with (self.pack / self.day["file"]).open("a", encoding="utf-8") as file:
            file.write("\n## 今天\n隔离用例中的一天。\n")
        self.day = cognition.start_day(self.pack)
        agency.plan_for_day(self.pack, self.day["dayNo"])

    def previous(self, **extra):
        result = self.choose(self.proposal(**extra))
        self.assertEqual(result["status"], "accepted", result)
        self.next_day()
        return result["plan"]

    def response(self, previous, relation="continue", **extra):
        mode = extra.pop("mode", "open" if relation == "release" else "focus")
        goal = extra.pop("goal", previous["goal_id"])
        return self.proposal(mode, goal=goal, continuity={"plan_id": previous["plan_id"], "relation": relation}, **extra)

    def candidates(self, **extra):
        return development.summary(self.pack, day=self.day["dayNo"], **extra)["prior_choices"]

    def test_old_intention_survives_many_runtime_days_without_automatic_carry(self):
        previous = self.previous()
        for _ in range(9):
            self.next_day()
        before = planning.path(self.pack).read_bytes()
        rows = self.candidates()
        self.assertEqual([r["plan_id"] for r in rows], [previous["plan_id"]])
        self.assertFalse(rows[0]["responded_by"])
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertNotEqual(agency.current_plan(self.pack, self.day["dayNo"]).get("origin"), "model")
        self.assertTrue(self.context()["choice_pending"])
        brain = fixtures.Brain()
        receipt = self.execute(brain, self.first)
        self.assertEqual(receipt["data"]["status"], "blocked")
        self.assertEqual(brain.compositions, 0)
        self.assertIn(previous["decision_id"], {r["id"] for r in receipt["data"]["evidence"]})
        # A direct user request is still a request, not an automatic carryover.
        requested = cognition.compose_work(self.pack, "letter", brain, day=self.day)
        self.assertEqual(requested["receipt"]["data"]["status"], "succeeded")

    def test_explicit_continue_keeps_parent_and_moves_next_day_to_child(self):
        previous = self.previous()
        raw = self.response(previous)
        accepted = self.choose(raw)
        self.assertEqual(accepted["status"], "accepted", accepted)
        current = accepted["plan"]
        self.assertEqual(current["continuity"]["plan_id"], previous["plan_id"])
        self.assertEqual(agency.current_plan(self.pack, previous["day"]), previous)
        self.assertTrue(deliberation.valid(self.pack, current))
        self.assertFalse(current["done"])
        self.assertEqual(self.candidates()[0]["responded_by"], current["plan_id"])
        before = planning.path(self.pack).read_bytes()
        self.assertEqual(self.choose(raw)["status"], "unchanged")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(self.execute(fixtures.Brain(), previous["goal_id"])["data"]["status"], "succeeded")
        self.next_day()
        self.assertEqual([r["plan_id"] for r in self.candidates()], [current["plan_id"]])

    def test_rest_can_defer_response_and_release_does_not_abandon_goal(self):
        previous = self.previous()
        self.choose(self.proposal("rest"))
        self.assertEqual(self.candidates()[0]["plan_id"], previous["plan_id"])
        self.assertFalse(self.candidates()[0]["responded_by"])
        self.assertEqual(self.execute(fixtures.Brain(), previous["goal_id"])["data"]["status"], "blocked")
        result = self.choose(self.response(previous, "release", mode="rest"))
        self.assertEqual(result["status"], "accepted", result)
        self.assertEqual(development.current_state(self.pack)["goals"][previous["goal_id"]]["status"], "active")
        self.next_day()
        self.assertEqual(self.candidates(), [])
        self.assertNotEqual(agency.current_plan(self.pack, self.day["dayNo"]).get("origin"), "model")

    def test_later_rest_does_not_erase_intention_but_revised_release_does(self):
        previous = self.choose()["plan"]
        self.choose(self.proposal("rest"))
        self.next_day()
        self.assertEqual(self.candidates()[0]["plan_id"], previous["plan_id"])
        continued = self.choose(self.response(previous))["plan"]
        self.choose(self.proposal("rest"))
        self.next_day()
        self.assertEqual([r["plan_id"] for r in self.candidates()], [continued["plan_id"]])
        self.choose(self.response(continued))
        self.choose(self.response(continued, "release", mode="rest"))
        self.next_day()
        self.assertEqual(self.candidates(), [])

    def test_changed_goal_requires_revise_and_cannot_continue_other_goal(self):
        previous = self.previous()
        self.goal("重新整理想法", identifier=previous["goal_id"], next_step="先列三个问题")
        self.assertTrue(self.candidates()[0]["goal_changed"])
        cases = [self.response(previous), self.response(previous, goal=self.first),
                 self.response(previous, "revise", mode="rest"),
                 self.response(previous, "release", mode="focus", goal=previous["goal_id"])]
        before = planning.path(self.pack).read_bytes()
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.choose(raw)["status"], "rejected")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        result = self.choose(self.response(previous, "revise", next_step="先整理三个问题"))
        self.assertEqual(result["status"], "accepted", result)
        self.assertNotEqual(result["plan"]["goal_event_id"], previous["goal_event_id"])

    def test_release_allows_another_goal_and_today_response_can_be_revised(self):
        previous = self.previous()
        first = self.choose(self.response(previous))["plan"]
        stale = self.context()
        released = self.choose(self.response(previous, "release", mode="focus", goal=self.first))
        self.assertEqual(released["status"], "accepted", released)
        self.assertNotEqual(released["plan"]["plan_id"], first["plan_id"])
        self.assertEqual(self.choose(self.response(previous), ctx=stale)["status"], "rejected")
        self.assertEqual(self.candidates()[0]["responded_by"], released["plan"]["plan_id"])
        self.next_day()
        self.assertEqual([r["plan_id"] for r in self.candidates()], [released["plan"]["plan_id"]])

    def test_only_shown_exact_prior_focus_choices_can_be_referenced(self):
        previous = self.previous()
        raw = self.response(previous)
        ctx = self.context()
        ctx["development"]["prior_choices"] = []
        changed = self.context()
        changed["development"]["prior_choices"][0]["entry_sha256"] = "0" * 64
        current = agency.current_plan(self.pack, self.day["dayNo"])
        cases = [(raw, ctx), (raw, changed), (self.response(current), None),
                 (self.proposal(continuity={"plan_id": previous["plan_id"], "relation": "continue", "day": 1}), None),
                 (self.proposal(continuity={"plan_id": "p_unknown", "relation": "continue"}), None)]
        before = planning.path(self.pack).read_bytes()
        for proposal, context in cases:
            with self.subTest(proposal=proposal):
                self.assertEqual(self.choose(proposal, ctx=context)["status"], "rejected")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)

    def test_actual_trimmed_candidates_are_used_for_chat_initiation_and_diary(self):
        previous = self.previous()
        shown = deepcopy(self.context()["development"])
        shown["prior_choices"] = []
        brain = fixtures.Brain({"reply": "再考虑一下。", "daily_plan": self.response(previous), "_used_development": shown})
        self.assertEqual(cognition.chat_turn(self.pack, "继续昨天的打算吗？", brain)["planDecision"]["status"], "rejected")
        self.assertEqual(cognition.maybe_initiate(self.pack, brain, force=True)["planDecision"]["status"], "rejected")
        cognition.run_days(self.pack, 1, brain)
        self.assertFalse(any(row.get("plan", {}).get("continuity") for row in planning.read(self.pack)))

    def test_candidates_and_context_dependencies_are_trimmed_together(self):
        previous = self.previous()
        ctx = self.context()
        ctx["development"]["plan_review"] = []
        ctx["development"]["prior_choices"][0]["dependencies"].append("only-in-prior-choice")
        self.assertIn("only-in-prior-choice", cognition._context_dependencies(ctx))
        ctx["_cfg"] = {"input_budget": 2048}
        _, used, _ = fit(ctx, lambda c: {"system": "x" * (1800 if c["development"].get("prior_choices") else 100)})
        self.assertEqual(used["development"]["prior_choices"], [])
        self.assertNotIn("only-in-prior-choice", cognition._context_dependencies(used))
        self.assertEqual(ctx["development"]["prior_choices"][0]["plan_id"], previous["plan_id"])

    def test_private_candidates_are_not_shared_and_external_action_is_generic(self):
        previous = self.previous()
        policy = policy_for(self.pack, "qq-group:123", "owner")
        self.assertEqual(self.candidates(policy=policy), [])
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False,
                                      person_id="owner", audience_id="qq-group:123")
        self.assertEqual(ctx["development"]["prior_choices"], [])
        self.assertEqual(self.choose(self.response(previous), ctx=ctx)["status"], "rejected")
        reason = deliberation.blocked_reason(self.pack, day=self.day["dayNo"], action="compose",
            goal_id="", policy=policy, audience_id="qq-group:123")
        self.assertEqual(reason, deliberation.EXTERNAL_BLOCKED)

    def test_forgetting_basis_hides_continuation_and_blocks_automatic_action(self):
        previous = self.previous(evidence=["current"])
        selected = self.choose(self.response(previous))["plan"]
        append_memories(self.pack, [{"id": "m_continuity_basis", "day": previous["day"], "kind": "thought",
            "text": "今天可以自己安排。", "source": experience.source_of(self.input), "event_ids": [self.input["id"]]}])
        cognition.forget_memory(self.pack, "m_continuity_basis")
        self.assertFalse(deliberation.valid(self.pack, selected))
        self.assertEqual(self.candidates(), [])
        self.assertEqual(self.execute(fixtures.Brain(), previous["goal_id"])["data"]["status"], "blocked")

    def test_hidden_release_does_not_reactivate_parent_intention(self):
        previous = self.previous()
        released = self.choose(self.response(previous, "release"))["plan"]
        event = next(row for row in experience.read(self.pack) if row["id"] == released["decision_id"])
        append_memories(self.pack, [{"id": "m_release", "day": released["day"], "kind": "thought",
            "text": event["text"], "source": experience.source_of(event), "event_ids": [event["id"]]}])
        cognition.forget_memory(self.pack, "m_release")
        self.assertTrue(deliberation.valid(self.pack, previous))
        self.next_day()
        self.assertEqual(self.candidates(), [])

    def test_old_checkpoint_success_does_not_finish_new_continuation(self):
        self.brain = fixtures.Brain()
        target = self.plan()
        rubric = self.listing(target)["criteria"]["id"]
        previous = self.choose(self.proposal(goal=target, checkpoint={"criteria_id": rubric}))["plan"]
        receipt = self.execute(self.brain, target)
        self.review(target, receipt["id"])
        self.assertTrue(plan_checkpoints.for_plan(self.pack, previous)["passed"])
        self.next_day()
        result = self.choose(self.response(previous, checkpoint={"criteria_id": rubric}))
        self.assertEqual(result["status"], "accepted", result)
        self.assertFalse(plan_checkpoints.for_plan(self.pack, result["plan"])["passed"])
        self.assertTrue(plan_checkpoints.for_plan(self.pack, previous)["passed"])
        self.assertEqual(planning.read(self.pack)[-1]["format"], planning.CONTINUITY_FORMAT)

    def test_failed_write_rolls_back_and_request_replay_keeps_single_response(self):
        previous = self.previous()
        brain = fixtures.Brain({"reply": "今天接着整理。", "daily_plan": self.response(previous)})
        before = planning.path(self.pack).read_bytes()
        original = planning.choose

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("fixture after continuity write")

        with patch("seedbank.deliberation.planning.choose", side_effect=fail):
            with self.assertRaises(OSError):
                cognition.chat_turn(self.pack, "继续昨天的打算。", brain, request_id="continuity-retry")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertTrue(requests.pending(self.pack))
        result = cognition.chat_turn(self.pack, "继续昨天的打算。", brain, request_id="continuity-retry")
        self.assertEqual(result["planDecision"]["status"], "accepted")
        before = planning.path(self.pack).read_bytes()
        replay = cognition.chat_turn(self.pack, "继续昨天的打算。", brain, request_id="continuity-retry")
        self.assertTrue(replay["replayed"])
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(sum(bool(row.get("plan", {}).get("continuity")) for row in planning.read(self.pack)), 1)

    def test_storage_failure_is_not_misreported_as_rejected_choice(self):
        previous = self.previous()
        ctx = self.context()
        before = planning.path(self.pack).read_bytes()
        with patch("seedbank.plan_continuity._eligible", side_effect=SeedError("unreadable history")):
            with self.assertRaisesRegex(SeedError, "unreadable history"):
                self.choose(self.response(previous), ctx=ctx)
        self.assertEqual(planning.path(self.pack).read_bytes(), before)

    def test_backup_keeps_links_and_format_marker_never_downgrades(self):
        previous = self.previous()
        selected = self.choose(self.response(previous))["plan"]
        self.choose(self.proposal("rest"))
        self.assertEqual(read_json(agency.agency_path(self.pack))["plan_store"], planning.CONTINUITY_FORMAT)
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertEqual(planning.read(restored), planning.read(self.pack))
        self.assertTrue(deliberation.valid(restored, selected))

    def test_parent_entry_change_is_not_silently_rebound(self):
        previous = self.previous()
        self.choose(self.response(previous))
        rows = planning.read(self.pack)
        next(row for row in rows if row["id"] == previous["plan_id"])["context"]["tampered"] = True
        planning.path(self.pack).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        altered = planning.path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            agency.load_agency(self.pack)
        self.assertEqual(planning.path(self.pack).read_bytes(), altered)


if __name__ == "__main__":
    unittest.main()
