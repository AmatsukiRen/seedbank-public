"""Offline regressions for attributed experience observations."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_learning as fixtures
from test_learning_strategies import LearningStrategiesTest as StrategyFixtures
from seedbank import backup, disclosure, experience, learning, learning_observations, requests, works
from seedbank.brain import build_compose_prompt
from seedbank.bridge import Bridge
from seedbank.cognition import forget_memory
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories, write_file_atomic, write_json_atomic


class LearningObservationsTest(unittest.TestCase):
    setUp = StrategyFixtures.setUp
    plan = StrategyFixtures.plan
    practice = StrategyFixtures.practice
    listing = StrategyFixtures.listing
    review = StrategyFixtures.review
    source = StrategyFixtures.source
    data = StrategyFixtures.data
    strategy = StrategyFixtures.strategy
    next_goal = StrategyFixtures.next_goal

    def prepare(self):
        source, _, review = self.source()
        strategy = self.strategy(source, review)
        goal = self.next_goal()
        outcome = self.practice(goal)["receipt"]["id"]
        return strategy, goal, outcome

    def observation(self, strategy, **changes):
        return {"lesson_id": strategy["id"], "fit": "applicable", "use": "observed", "effect": "helpful",
                "reason": "写出了整理材料的具体事情", "quote": "谢谢你昨天陪我整理材料。", **changes}

    def observe(self, strategy, goal, outcome, **changes):
        return self.review(goal, outcome, lesson_observations=[self.observation(strategy, **changes)])

    def test_observation_reaches_later_task_with_attribution_quote_and_exact_receipt(self):
        strategy, goal, outcome = self.prepare()
        review = self.observe(strategy, goal, outcome)
        later = self.practice(goal)["receipt"]["data"]
        self.assertEqual(review["format"], learning_observations.FORMAT)
        lesson = self.brain.calls[-1]["practice"]["lessons"][0]
        self.assertEqual(lesson["observations"][0]["feedback_id"], review["id"])
        self.assertEqual(lesson["observations"][0]["task"]["topic"], "感谢昨天整理材料的帮助")
        self.assertEqual(lesson["observations"][0]["generation"]["model"], "test-only")
        self.assertIn("写出了整理材料的具体事情", build_compose_prompt(self.brain.calls[-1])["user"])
        self.assertEqual(later["practice"]["lesson_observation_ids"], [review["id"]])
        self.assertIn(review["evidence"][0]["id"], later["generation"]["context_dependencies"])
        supplied = self.listing(goal)["attempts"][0]["offered_observations"]
        self.assertEqual(supplied[0]["observations"][0]["lesson_id"], strategy["id"])
        self.assertEqual(self.listing(goal)["goal"]["status"], "active")

    def test_harmful_and_helpful_judgments_remain_distinct_without_automatic_ranking(self):
        strategy, goal, first = self.prepare()
        self.observe(strategy, goal, first, fit="not_applicable", effect="harmful", reason="机械照搬感谢语气")
        second = self.practice(goal)["receipt"]["id"]
        self.observe(strategy, goal, second)
        candidate = learning.for_goal(self.pack, goal)["lessons"][0]
        self.assertEqual([r["effect"] for r in candidate["observations"]], ["harmful", "helpful"])
        self.assertEqual(candidate["id"], strategy["id"])
        self.assertNotIn("mastery", candidate)

    def test_unobserved_use_cannot_claim_effect_and_observed_use_requires_exact_quote(self):
        strategy, goal, outcome = self.prepare()
        for changes in ({"use": "not_observed"}, {"use": "uncertain"}, {"quote": ""}, {"quote": "作品中没有这些字"}):
            with self.subTest(changes=changes), self.assertRaises(SeedError):
                self.observe(strategy, goal, outcome, **changes)
        self.assertEqual(requests.pending(self.pack), [])
        review = self.observe(strategy, goal, outcome, use="not_observed", effect="uncertain", quote="")
        self.assertEqual(review["data"]["lesson_observations"][0]["use"], "not_observed")

    def test_recent_observation_limit_does_not_delete_feedback_history(self):
        strategy, goal, first = self.prepare()
        reviews = []
        for index in range(4):
            outcome = first if index == 0 else self.practice(goal)["receipt"]["id"]
            reviews.append(self.observe(strategy, goal, outcome, reason=f"独立记录 {index}"))
        candidate = learning.for_goal(self.pack, goal)["lessons"][0]
        self.assertEqual(candidate["observation_count"], 4)
        self.assertEqual([r["feedback_id"] for r in candidate["observations"]], [r["id"] for r in reviews[-3:]])
        self.assertEqual(len([r for r in learning.read(self.pack) if r["format"] == learning_observations.FORMAT]), 4)
        refs = learning.practice_reference({"lessons": [candidate]}, "provided_to_creator")
        self.assertEqual(refs["lesson_observation_ids"], sorted(r["id"] for r in reviews[-3:]))

    def test_no_supplied_lesson_and_merely_available_scope_are_rejected(self):
        source, outcome, review = self.source()
        strategy = self.strategy(source, review)
        with self.assertRaises(SeedError):
            self.observe(strategy, source, outcome)
        goal = self.next_goal()
        identifier = self.practice(goal)["receipt"]["id"]
        loaded = learning.view(self.pack)
        altered = deepcopy(loaded["outcomes"][identifier])
        altered["practice"]["scope"] = "available_at_execution"
        with self.assertRaises(SeedError):
            learning_observations.check(self.pack, [self.observation(strategy)], altered, loaded)

    def test_invalid_and_duplicate_observations_are_rejected_before_pending_request(self):
        strategy, goal, outcome = self.prepare()
        item = self.observation(strategy)
        for values in ([item, item], [item] * 4, [{**item, "fit": "always"}], [{**item, "reason": ""}]):
            with self.subTest(values=values), self.assertRaises(SeedError):
                self.review(goal, outcome, lesson_observations=values)
        self.assertEqual(requests.pending(self.pack), [])

    def test_correction_retires_old_interpretations_but_keeps_source_strategy_and_work(self):
        strategy, goal, outcome = self.prepare()
        review = self.observe(strategy, goal, outcome)
        derived = self.practice(goal)["receipt"]
        before = learning.path(self.pack).read_bytes()
        revised = self.observe(strategy, goal, outcome, effect="harmful", reason="重新核对后认为套用了不合适的语气")
        self.assertTrue(learning.path(self.pack).read_bytes().startswith(before))
        self.assertEqual(revised["data"]["supersedes"], review["id"])
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(review["evidence"][0]["id"], policy.blocked)
        self.assertIn(derived["source"].split("#")[1], policy.blocked)
        self.assertNotIn(strategy["evidence"][0]["id"], policy.blocked)
        original = learning.view(self.pack)["outcomes"][outcome]
        self.assertEqual(learning.artifact_state(self.pack, original)["state"], "unchanged")
        observations = learning.for_goal(self.pack, goal)["lessons"][0]["observations"]
        self.assertEqual([r["feedback_id"] for r in observations], [revised["id"]])

    def test_clearing_observations_preserves_history_without_reviving_previous_judgment(self):
        strategy, goal, outcome = self.prepare()
        review = self.observe(strategy, goal, outcome)
        replacement = self.review(goal, outcome, lesson_observations=[])
        self.assertEqual(replacement["format"], learning_observations.FORMAT)
        self.assertEqual(learning.for_goal(self.pack, goal)["lessons"][0]["observations"], [])
        self.assertIn(review["evidence"][0]["id"], MemoryPolicy.load(self.pack).blocked)

    def test_changed_artifact_excludes_observation_without_erasing_original_strategy(self):
        strategy, goal, outcome = self.prepare()
        review = self.observe(strategy, goal, outcome)
        target = learning.view(self.pack)["outcomes"][outcome]["artifact"].split("#")[1]
        contents = works.load_works(self.pack)
        next(r for r in contents["works"] if r["id"] == target)["text"] = "替换后的作品"
        write_json_atomic(self.pack / "mind/works.json", contents)
        self.assertEqual(learning.for_goal(self.pack, goal)["lessons"][0]["observations"], [])
        self.assertIn(review["evidence"][0]["id"], MemoryPolicy.load(self.pack).blocked)
        self.assertNotIn(strategy["evidence"][0]["id"], MemoryPolicy.load(self.pack).blocked)

    def test_modified_observation_cannot_reuse_original_input_hash(self):
        strategy, goal, outcome = self.prepare()
        review = self.observe(strategy, goal, outcome)
        rows = learning.read(self.pack)
        next(r for r in rows if r["id"] == review["id"])["data"]["lesson_observations"][0]["effect"] = "harmful"
        write_file_atomic(learning.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        self.assertEqual(learning.for_goal(self.pack, goal)["lessons"][0]["observations"], [])
        self.assertEqual(self.listing(goal)["attempts"][0]["feedback"], {})

    def test_forgotten_observation_does_not_revive_previous_feedback(self):
        strategy, goal, outcome = self.prepare()
        self.observe(strategy, goal, outcome)
        latest = self.observe(strategy, goal, outcome, effect="harmful")
        ref = latest["evidence"][0]
        append_memories(self.pack, [{"id": "m_observation", "day": 1, "kind": "thought", "text": "反馈依据",
            "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_observation")
        self.assertEqual(learning.for_goal(self.pack, goal)["lessons"][0]["observations"], [])
        self.assertEqual(self.listing(goal)["attempts"][0]["feedback"], {})

    def test_private_observation_does_not_enter_group_context(self):
        strategy, goal, outcome = self.prepare()
        self.observe(strategy, goal, outcome, reason="PRIVATE_OBSERVATION_869")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        self.assertNotIn("PRIVATE_OBSERVATION_869", json.dumps(learning.context(self.pack, policy=policy)))

    def test_trimmed_candidates_do_not_appear_in_observation_receipt(self):
        strategy, goal, outcome = self.prepare()
        self.observe(strategy, goal, outcome)

        class TrimmedBrain(fixtures.FixtureBrain):
            def compose(self, ctx):
                result = super().compose(ctx)
                practice = deepcopy(ctx["practice"])
                practice["lessons"] = []
                return {**result, "_used_practice": practice, "_used_learning": []}

        later = self.practice(goal, brain=TrimmedBrain())["receipt"]["data"]
        self.assertEqual(later["practice"]["lesson_observation_ids"], [])

    def test_failed_write_and_backup_resume_preserve_observation_input_and_retry_identity(self):
        strategy, goal, outcome = self.prepare()
        data = {"goal_id": goal, "criteria_id": self.listing(goal)["criteria"]["id"], "outcome_id": outcome,
                "expected": "", "ratings": {"c1": "met"}, "reason": "具体反馈", "next_step": "继续观察",
                "lesson_observations": [self.observation(strategy)]}
        before = learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        with patch("seedbank.learning._append", side_effect=OSError("fixture")), self.assertRaises(OSError):
            learning.perform(self.pack, "feedback", data, request_id="observe-retry")
        self.assertEqual(before, (learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))
        saved = backup.create(self.pack)
        restored = self.pack.parent / "observation-restored.life"
        backup.restore(saved["file"], restored)
        result = Bridge(restored, "stub").handle({"op": "resume", "request_id": "observe-retry"})
        self.assertTrue(result["ok"], result)
        replay = learning.perform(restored, "feedback", data, request_id="observe-retry")
        self.assertTrue(replay["replayed"])
        self.assertEqual(len([r for r in learning.read(restored) if r["format"] == learning_observations.FORMAT]), 1)
        with self.assertRaises(SeedError):
            learning.perform(restored, "feedback", {**data, "reason": "另一次输入"}, request_id="observe-retry")
        with self.assertRaises(SeedError):
            learning.perform(restored, "feedback", data, request_id="stale-page")


if __name__ == "__main__":
    unittest.main()
