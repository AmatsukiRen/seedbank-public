"""User-run offline coverage for observing strategies in repeated practice.

Uses temporary artificial packs and fixture responses only. Authored, not run.
"""
from copy import deepcopy
import json
import unittest

import test_learning as fixtures
import test_learning_observations as observation_fixtures
import test_learning_choices as choice_fixtures
from seedbank import backup, disclosure, experience, learning, learning_observations, requests, works
from seedbank.brain import build_compose_prompt
from seedbank.cognition import _context_dependencies, forget_memory
from seedbank.context_window import fit
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories, write_json_atomic


class SameGoalObservationsTest(unittest.TestCase):
    setUp = observation_fixtures.LearningObservationsTest.setUp
    plan = observation_fixtures.LearningObservationsTest.plan
    practice = observation_fixtures.LearningObservationsTest.practice
    listing = observation_fixtures.LearningObservationsTest.listing
    review = observation_fixtures.LearningObservationsTest.review
    source = observation_fixtures.LearningObservationsTest.source
    data = observation_fixtures.LearningObservationsTest.data
    strategy = observation_fixtures.LearningObservationsTest.strategy
    observation = observation_fixtures.LearningObservationsTest.observation
    observe = observation_fixtures.LearningObservationsTest.observe

    def prepare(self):
        goal, _, original_review = self.source()
        strategy = self.strategy(goal, original_review, transfer={})
        outcome = self.practice(goal)["receipt"]["id"]
        return goal, strategy, outcome, original_review

    def current_strategy(self, goal, identifier):
        return next(row for row in learning.for_goal(self.pack, goal)["adjustments"] if row["id"] == identifier)

    def test_same_goal_observation_reaches_next_prompt_receipt_and_dependencies(self):
        goal, strategy, outcome, _ = self.prepare()
        shown = next(row for row in self.listing(goal)["attempts"] if row["id"] == outcome)
        self.assertEqual(shown["practice"]["lesson_ids"], [])
        self.assertEqual(shown["practice"]["adjustment_ids"], [strategy["id"]])
        self.assertEqual([r["id"] for r in shown["offered_lessons"]], [strategy["id"]])
        review = self.observe(strategy, goal, outcome, reason="SAME_GOAL_OBSERVATION: this attempt was specific")
        candidate = self.current_strategy(goal, strategy["id"])
        self.assertEqual(candidate["observations"][0]["feedback_id"], review["id"])
        self.assertEqual(candidate["observations"][0]["origin"], "user")
        later = self.practice(goal)["receipt"]["data"]
        self.assertIn("SAME_GOAL_OBSERVATION", build_compose_prompt(self.brain.calls[-1])["user"])
        self.assertEqual(later["practice"]["lesson_observation_ids"], [review["id"]])
        self.assertEqual(later["practice"]["lesson_ids"], [])
        self.assertIn(review["evidence"][0]["id"], later["generation"]["context_dependencies"])
        provided = self.listing(goal)["attempts"][0]["offered_observations"]
        self.assertEqual(provided[0]["observations"][0]["lesson_id"], strategy["id"])
        self.assertEqual(next(r for r in learning.read(self.pack) if r["id"] == strategy["id"]), strategy)
        self.assertEqual(self.listing(goal)["goal"]["status"], "active")

    def test_same_rubric_other_goal_is_observable_without_claiming_transfer(self):
        source, _, original_review = self.source()
        strategy = self.strategy(source, original_review, transfer={})
        target = self.plan(title="再写一封感谢信")
        outcome = self.practice(target)["receipt"]["id"]
        review = self.observe(strategy, target, outcome)
        row = self.current_strategy(target, strategy["id"])
        self.assertEqual(row["observations"][0]["feedback_id"], review["id"])
        self.assertEqual(learning.for_goal(self.pack, target)["lessons"], [])
        self.assertEqual(row["data"]["transfer"], {})

    def test_model_adoption_and_disagreeing_user_observation_remain_distinct(self):
        goal, _, original_review = self.source()
        strategy = self.strategy(goal, original_review, transfer={})
        declaration = {"strategy_id": strategy["id"], "choice": "adopt",
                       "reason": "这次需要具体表达", "application": "写出具体帮助"}
        outcome = self.practice(goal, brain=choice_fixtures.ChoiceBrain([declaration]))["receipt"]["id"]
        self.observe(strategy, goal, outcome, use="not_observed", effect="uncertain", quote="",
                     reason="用户没有在作品中确认这个做法")
        item = self.current_strategy(goal, strategy["id"])["observations"][0]
        self.assertEqual(item["model_choice"]["choice"], "adopt")
        self.assertEqual(item["use"], "not_observed")
        self.assertEqual(item["effect"], "uncertain")
        self.assertNotIn("mastery", item)
        self.assertEqual(self.listing(goal)["goal"]["status"], "active")

    def test_not_supplied_and_available_only_are_rejected(self):
        goal, original_outcome, original_review = self.source()
        strategy = self.strategy(goal, original_review, transfer={})
        with self.assertRaises(SeedError):
            self.observe(strategy, goal, original_outcome)
        identifier = self.practice(goal)["receipt"]["id"]
        loaded = learning.view(self.pack)
        for changes in ({"scope": "available_at_execution"}, {"adjustment_ids": []}):
            with self.subTest(changes=changes):
                outcome = deepcopy(loaded["outcomes"][identifier])
                outcome["practice"].update(changes)
                with self.assertRaises(SeedError):
                    learning_observations.check(self.pack, [self.observation(strategy)], outcome, loaded)
        self.assertEqual(requests.pending(self.pack), [])

    def test_revised_observation_retires_derived_output_but_not_source_strategy(self):
        goal, strategy, outcome, _ = self.prepare()
        first = self.observe(strategy, goal, outcome)
        derived = self.practice(goal)["receipt"]
        before = learning.path(self.pack).read_bytes()
        revised = self.observe(strategy, goal, outcome, effect="harmful", reason="重新核对后认为照搬有妨碍")
        self.assertTrue(learning.path(self.pack).read_bytes().startswith(before))
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(first["evidence"][0]["id"], policy.blocked)
        self.assertIn(derived["source"].split("#", 1)[1], policy.blocked)
        self.assertNotIn(strategy["evidence"][0]["id"], policy.blocked)
        observations = self.current_strategy(goal, strategy["id"])["observations"]
        self.assertEqual([row["feedback_id"] for row in observations], [revised["id"]])
        self.review(goal, outcome, lesson_observations=[])
        self.assertEqual(self.current_strategy(goal, strategy["id"])["observations"], [])

    def test_revised_strategy_does_not_inherit_old_version_observations(self):
        goal, strategy, outcome, original_review = self.prepare()
        observed = self.observe(strategy, goal, outcome)
        revised = self.strategy(goal, original_review, transfer={}, text="只描述资料明确的具体帮助。")
        selected = learning.for_goal(self.pack, goal)["adjustments"]
        self.assertNotIn(strategy["id"], [row["id"] for row in selected])
        self.assertEqual(self.current_strategy(goal, revised["id"])["observations"], [])
        self.assertIn(observed["id"], [row["id"] for row in learning.read(self.pack)])

    def test_changed_work_removes_observation_without_erasing_source_strategy(self):
        goal, strategy, outcome, _ = self.prepare()
        observed = self.observe(strategy, goal, outcome)
        receipt = learning.view(self.pack)["outcomes"][outcome]
        contents = works.load_works(self.pack)
        identifier = receipt["artifact"].split("#", 1)[1]
        next(row for row in contents["works"] if row["id"] == identifier)["text"] = "修改后的人工作品"
        write_json_atomic(self.pack / "mind/works.json", contents)
        self.assertEqual(self.current_strategy(goal, strategy["id"])["observations"], [])
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(observed["evidence"][0]["id"], policy.blocked)
        self.assertNotIn(strategy["evidence"][0]["id"], policy.blocked)

    def test_private_and_forgotten_observations_do_not_return_as_current_context(self):
        goal, strategy, outcome, _ = self.prepare()
        observed = self.observe(strategy, goal, outcome, reason="PRIVATE_SAME_GOAL_384")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        self.assertNotIn("PRIVATE_SAME_GOAL_384", json.dumps(learning.context(self.pack, policy=policy)))
        ref = observed["evidence"][0]
        append_memories(self.pack, [{"id": "m_same_goal_observation", "day": 1, "kind": "thought",
                                    "text": "人工观察依据", "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_same_goal_observation")
        self.assertEqual(self.current_strategy(goal, strategy["id"])["observations"], [])
        self.assertIn(ref["id"], MemoryPolicy.load(self.pack).blocked)

    def test_budget_omission_removes_entire_strategy_observation_and_dependencies(self):
        goal, strategy, outcome, _ = self.prepare()
        observed = self.observe(strategy, goal, outcome, reason="bounded_observation " * 20)
        candidate = self.current_strategy(goal, strategy["id"])
        context = {"_cfg": {"input_budget": 2048}, "practice": {"adjustments": [candidate]}}
        original = deepcopy(context)
        rendered, used, report = fit(context, lambda ctx: {"user": json.dumps(ctx["practice"], ensure_ascii=False)})
        self.assertTrue(report["limited"])
        self.assertEqual(used["practice"]["adjustments"], [])
        self.assertNotIn("bounded_observation", rendered["user"])
        self.assertNotIn(observed["evidence"][0]["id"], _context_dependencies(used))
        reference = learning.practice_reference(used["practice"], "provided_to_creator")
        self.assertEqual(reference["adjustment_ids"], [])
        self.assertEqual(reference["lesson_observation_ids"], [])
        self.assertEqual(context, original)

    def test_saved_receipt_uses_trimmed_task_observations_only(self):
        goal, strategy, outcome, _ = self.prepare()
        self.observe(strategy, goal, outcome)

        class TrimmedBrain(fixtures.FixtureBrain):
            def compose(self, ctx):
                result = super().compose(ctx)
                practice = deepcopy(ctx["practice"])
                practice["adjustments"] = []
                return {**result, "_used_practice": practice, "_used_learning": []}

        receipt = self.practice(goal, brain=TrimmedBrain())["receipt"]["data"]
        self.assertEqual(receipt["practice"]["adjustment_ids"], [])
        self.assertEqual(receipt["practice"]["lesson_observation_ids"], [])
        context = learning.for_goal(self.pack, goal)
        reference = learning.practice_reference({"feedback": []}, "provided_to_creator", additional=[context])
        self.assertEqual(reference["adjustment_ids"], [])
        self.assertEqual(reference["lesson_observation_ids"], [])

    def test_backup_restore_preserves_raw_history_and_projected_observation(self):
        goal, strategy, outcome, _ = self.prepare()
        self.observe(strategy, goal, outcome)
        before = learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        expected = learning.for_goal(self.pack, goal)["adjustments"]
        saved = backup.create(self.pack)
        restored = self.pack.parent / "same-goal-restored.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(learning.for_goal(restored, goal)["adjustments"], expected)
        self.assertEqual(before, (learning.path(restored).read_bytes(), experience.path(restored).read_bytes()))


if __name__ == "__main__":
    unittest.main()
