"""User-run regressions only: isolated life packs and offline fixture models."""
import json
import unittest
from unittest.mock import patch

import test_learning as fixtures
from seedbank import actions, agency, backup, cognition, deliberation, development, goal_dependencies, learning, plan_checkpoints
from seedbank.disclosure import policy_for
from seedbank.util import SeedError, append_memories


class GoalDependenciesTest(unittest.TestCase):
    plan = fixtures.LearningTest.plan
    practice = fixtures.LearningTest.practice
    review = fixtures.LearningTest.review
    listing = fixtures.LearningTest.listing

    def setUp(self):
        fixtures.LearningTest.setUp(self)
        self.folder = self.pack.parent
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No real service"))
        guard.start()
        self.addCleanup(guard.stop)

    def before(self, goal):
        return {"goal_id": goal, "criteria_id": self.listing(goal)["criteria"]["id"]}

    def revise(self, goal, **extra):
        current = self.listing(goal)
        return self.plan(goal_id=goal, expected=current["goal"]["event_id"], **extra)

    def complete(self, goal):
        outcome = self.practice(goal)["receipt"]["id"]
        self.review(goal, outcome)
        current = self.listing(goal)
        learning.perform(self.pack, "complete", {"goal_id": goal, "criteria_id": current["criteria"]["id"],
            "expected": current["goal"]["event_id"], "evidence": {"c1": outcome}, "reason": "这一步已经按条件核对"})
        return outcome

    def choose(self, goal, *, ctx=None):
        ctx = ctx or cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        return deliberation.apply(self.pack, {"mode": "focus", "goal_id": goal, "next_step": "完成下一步",
            "reason": "前面的安排已经核对", "evidence": []}, ctx=ctx, day=self.day,
            generation={"runner": "dependency-fixture", "fallback": False})

    def execute(self, goal, **extra):
        return actions.execute(self.pack, [{"type": "compose", "kind": "letter", "goal_id": goal,
            "reason": "继续这一步"}], day=self.day, source=self.day["file"], brain=self.brain, memories=[], **extra)[0]

    def test_unfinished_prerequisite_blocks_practice_focus_and_automatic_execution(self):
        first = self.plan(title="先整理材料")
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        self.assertFalse(self.listing(second)["readiness"]["ready"])
        self.assertEqual(self.listing(second)["criteria"]["format"], goal_dependencies.FORMAT)
        self.assertEqual(agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)["goal_id"], first)
        with self.assertRaisesRegex(SeedError, "前置目标"):
            self.practice(second)
        with self.assertRaisesRegex(SeedError, "前置目标"):
            cognition.compose_work(self.pack, "letter", self.brain, goal_id=second, day=self.day)
        self.assertEqual(self.choose(second)["status"], "rejected")
        result = self.execute(second)
        self.assertEqual(result["data"]["status"], "blocked")
        self.assertEqual(result["data"]["attempt_state"], "not_started")
        self.assertEqual(self.brain.calls, [])

    def test_feedback_alone_does_not_open_next_step_until_completion_is_recorded(self):
        first = self.plan(title="先整理材料")
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        outcome = self.practice(first)["receipt"]["id"]
        self.review(first, outcome)
        self.assertFalse(self.listing(second)["readiness"]["ready"])
        current = self.listing(first)
        learning.perform(self.pack, "complete", {"goal_id": first, "criteria_id": current["criteria"]["id"],
            "expected": current["goal"]["event_id"], "evidence": {"c1": outcome}, "reason": "逐项核对后完成"})
        self.assertTrue(self.listing(second)["readiness"]["ready"])
        self.assertEqual(self.choose(second)["status"], "accepted")
        self.assertEqual(self.practice(second)["receipt"]["data"]["status"], "succeeded")
        self.assertEqual(self.listing(second)["goal"]["status"], "active")

    def test_revised_feedback_recloses_descendants_without_erasing_history(self):
        first = self.plan(title="先整理材料")
        outcome = self.complete(first)
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        self.complete(second)
        third = self.plan(title="最后回顾", prerequisites=[self.before(second)])
        self.assertTrue(self.listing(third)["readiness"]["ready"])
        before = development.load_development(self.pack)["goals"][second]["completion"]
        self.review(first, outcome, {"c1": "not_met"}, reason="重新检查后发现遗漏")
        self.assertFalse(self.listing(second)["completion_current"]["passed"])
        self.assertFalse(self.listing(third)["readiness"]["ready"])
        self.assertEqual(development.load_development(self.pack)["goals"][second]["completion"], before)
        with self.assertRaises(SeedError):
            self.practice(third)

    def test_changed_prerequisite_standard_requires_explicit_rebinding(self):
        first = self.plan(title="先整理材料")
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        pinned = self.listing(second)["criteria"]["data"]["prerequisites"]
        stale = self.before(first)
        self.revise(first, title="更明确地整理材料", items=[{"text": "整理三个具体例子", "group": "材料"}])
        current = self.listing(second)
        self.assertEqual(current["readiness"]["requirements"][0]["state"], "changed")
        self.assertEqual(current["criteria"]["data"]["prerequisites"], pinned)
        with self.assertRaisesRegex(SeedError, "条件已变化"):
            self.revise(second, prerequisites=[stale])
        self.revise(second, prerequisites=[self.before(first)])
        self.assertEqual(self.listing(second)["readiness"]["requirements"][0]["state"], "not_completed")

    def test_cycle_self_duplicate_and_malformed_edges_do_not_write(self):
        first = self.plan(title="第一步")
        second = self.plan(title="第二步", prerequisites=[self.before(first)])
        before = learning.path(self.pack).read_bytes()
        cases = [[self.before(second)], [self.before(first)], [self.before(second), self.before(second)],
                 [{"goal_id": second, "criteria_id": "l_missing"}], [self.before(second)] * 7]
        for prerequisites in cases:
            with self.subTest(prerequisites=prerequisites), self.assertRaises(SeedError):
                self.revise(first, prerequisites=prerequisites)
        self.assertEqual(learning.path(self.pack).read_bytes(), before)

    def test_omission_preserves_prerequisites_and_explicit_empty_removes_them(self):
        first = self.plan(title="第一步")
        second = self.plan(title="第二步", prerequisites=[self.before(first)])
        saved = self.listing(second)["criteria"]["data"]["prerequisites"]
        self.revise(second, title="更清楚的第二步")
        self.assertEqual(self.listing(second)["criteria"]["data"]["prerequisites"], saved)
        self.assertFalse(self.listing(second)["readiness"]["ready"])
        self.revise(second, title="独立进行的第二步", prerequisites=[])
        self.assertEqual(self.listing(second)["criteria"]["data"]["prerequisites"], [])
        self.assertTrue(self.listing(second)["readiness"]["ready"])
        self.assertEqual(self.listing(first)["goal"]["status"], "active")

    def test_multiple_prerequisites_all_need_current_completion(self):
        first = self.plan(title="材料甲")
        other = self.plan(title="材料乙")
        target = self.plan(title="综合材料", prerequisites=[self.before(first), self.before(other)])
        self.complete(first)
        self.assertFalse(self.listing(target)["readiness"]["ready"])
        self.complete(other)
        self.assertTrue(self.listing(target)["readiness"]["ready"])

    def test_actual_offered_learning_is_required_for_focus(self):
        first = self.plan(title="先整理材料")
        self.complete(first)
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        ctx["learning"] = []
        self.assertEqual(self.choose(second, ctx=ctx)["status"], "rejected")
        self.assertEqual(self.choose(second)["status"], "accepted")

    def test_missing_or_changed_artifact_recloses_the_next_step(self):
        first = self.plan(title="先整理材料")
        outcome = self.complete(first)
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        self.assertTrue(self.listing(second)["readiness"]["ready"])
        source = self.pack / "mind/works.json"
        doc = json.loads(source.read_text(encoding="utf-8"))
        doc["works"][0]["text"] = "内容已经被改写"
        source.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(self.listing(second)["readiness"]["ready"])
        self.assertIn(outcome, {row["id"] for row in development.load_development(self.pack)["outcomes"]})

    def test_current_feedback_dependencies_follow_context_and_choice(self):
        first = self.plan(title="先整理材料")
        outcome = self.complete(first)
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        feedback = self.listing(first)["attempts"][0]["feedback"]
        identifier = feedback["evidence"][0]["id"]
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertIn(identifier, cognition._context_dependencies(ctx))
        selected = self.choose(second)["plan"]
        self.assertIn(identifier, {r["id"] for r in selected["evidence"]})
        revised = self.review(first, outcome, {"c1": "not_met"})
        blocked = self.execute(second)
        self.assertEqual(blocked["data"]["status"], "blocked")
        self.assertIn(revised["evidence"][0]["id"], {r["id"] for r in blocked["data"]["evidence"]})

    def test_plan_checkpoint_rechecks_prerequisites_after_own_results_pass(self):
        first = self.plan(title="先整理材料")
        original = self.complete(first)
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        current = self.listing(second)
        choice = deliberation.apply(self.pack, {"mode": "focus", "goal_id": second, "next_step": "完成总结",
            "reason": "前一步已核对", "checkpoint": {"criteria_id": current["criteria"]["id"]}},
            ctx=ctx, day=self.day, generation={"runner": "dependency-fixture", "fallback": False})
        self.assertEqual(choice["status"], "accepted", choice)
        own = self.practice(second)["receipt"]["id"]
        self.review(second, own)
        self.assertTrue(plan_checkpoints.for_plan(self.pack, choice["plan"])["passed"])
        self.review(first, original, {"c1": "not_met"})
        checked = plan_checkpoints.for_plan(self.pack, choice["plan"])
        self.assertFalse(checked["passed"])
        self.assertEqual(checked["state"], "prerequisites")
        self.assertEqual(self.execute(second)["data"]["status"], "blocked")

    def test_old_work_is_not_retroactively_proof_of_new_prerequisite_order(self):
        target = self.plan(title="后一步")
        old = self.practice(target)["receipt"]["id"]
        first = self.plan(title="前一步")
        self.revise(target, title="后一步", prerequisites=[self.before(first)])
        self.complete(first)
        self.review(target, old)
        report = learning.evaluate(self.pack, target, {"c1": old})
        self.assertFalse(report["passed"])
        self.assertEqual(report["checks"][0]["reason"], "no_prerequisite_execution_evidence")
        current = self.practice(target)["receipt"]["id"]
        self.review(target, current)
        self.assertTrue(learning.evaluate(self.pack, target, {"c1": current})["passed"])

    def test_private_readiness_is_not_disclosed_in_external_context(self):
        first = self.plan(title="私人材料")
        second = self.plan(title="私人整理", prerequisites=[self.before(first)])
        policy = policy_for(self.pack, "qq-group:123", "owner")
        ctx = learning.context(self.pack, policy=policy)
        self.assertEqual(ctx, [])
        result = self.execute(second, audience_id="qq-group:123", person_id="owner")
        self.assertEqual(result["data"]["status"], "blocked")
        self.assertNotIn("私人材料", result["data"]["detail"])
        self.assertEqual(result["data"]["evidence"], [])

    def test_forgotten_completion_source_does_not_leave_descendant_ready(self):
        first = self.plan(title="先整理材料")
        self.complete(first)
        second = self.plan(title="再写总结", prerequisites=[self.before(first)])
        feedback = self.listing(first)["attempts"][0]["feedback"]
        ref = feedback["evidence"][0]
        append_memories(self.pack, [{"id": "m_prerequisite_review", "day": self.day["dayNo"], "kind": "thought",
            "text": "这一步的核对", "source": ref["source"], "event_ids": [ref["id"]]}])
        cognition.forget_memory(self.pack, "m_prerequisite_review")
        self.assertFalse(self.listing(second)["readiness"]["ready"])
        self.assertTrue(any(row["goal_id"] == first for row in learning.read(self.pack)))

    def test_old_goals_have_no_implicit_prerequisites_and_reads_are_pure(self):
        goal = self.plan()
        before = learning.path(self.pack).read_bytes()
        self.assertTrue(self.listing(goal)["readiness"]["ready"])
        self.assertNotIn("prerequisites", self.listing(goal)["criteria"]["data"])
        self.assertEqual(learning.path(self.pack).read_bytes(), before)
        self.assertEqual(self.practice(goal)["receipt"]["data"]["status"], "succeeded")

    def test_failed_define_rolls_back_and_request_replay_preserves_one_plan(self):
        first = self.plan(title="第一步")
        payload = {"title": "第二步", "skill": "整理", "next_step": "整理材料", "reason": "有先后顺序",
            "criteria": [{"text": "写出具体例子", "group": "材料"}], "prerequisites": [self.before(first)]}
        before = learning.path(self.pack).read_bytes()
        original = learning.define

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("fixture after criteria save")

        with patch("seedbank.learning.define", side_effect=fail), self.assertRaises(OSError):
            learning.perform(self.pack, "plan", payload, request_id="dependency-retry")
        self.assertEqual(learning.path(self.pack).read_bytes(), before)
        saved = learning.perform(self.pack, "plan", payload, request_id="dependency-retry")
        before = learning.path(self.pack).read_bytes()
        replay = learning.perform(self.pack, "plan", payload, request_id="dependency-retry")
        self.assertEqual(replay["goal_id"], saved["goal_id"])
        self.assertEqual(learning.path(self.pack).read_bytes(), before)

    def test_backup_preserves_relationships_and_changed_parent_is_not_rebound(self):
        first = self.plan(title="第一步")
        second = self.plan(title="第二步", prerequisites=[self.before(first)])
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertEqual(learning.read(restored), learning.read(self.pack))
        self.assertEqual(learning.listing(restored, second)["readiness"], self.listing(second)["readiness"])
        rows = learning.read(self.pack)
        rows[0]["data"]["title"] = "外部改写的前置目标"
        learning.path(self.pack).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        changed = learning.path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            learning.listing(self.pack, second)
        self.assertEqual(learning.path(self.pack).read_bytes(), changed)


if __name__ == "__main__":
    unittest.main()
