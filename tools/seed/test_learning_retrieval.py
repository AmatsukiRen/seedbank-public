"""User-run regressions only: temporary packs, offline fixtures, no services."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_learning as fixtures
import test_learning_observations as observation_fixtures
import test_learning_strategies as strategy_fixtures
from seedbank import backup, context_window, disclosure, experience, learning, learning_retrieval
from seedbank.cognition import forget_memory
from seedbank.util import append_memories


class LearningRetrievalTest(unittest.TestCase):
    plan = fixtures.LearningTest.plan
    practice = fixtures.LearningTest.practice
    listing = fixtures.LearningTest.listing
    review = fixtures.LearningTest.review
    source = strategy_fixtures.LearningStrategiesTest.source
    data = strategy_fixtures.LearningStrategiesTest.data
    strategy = strategy_fixtures.LearningStrategiesTest.strategy
    next_goal = strategy_fixtures.LearningStrategiesTest.next_goal
    observation = observation_fixtures.LearningObservationsTest.observation
    observe = observation_fixtures.LearningObservationsTest.observe
    prepare = observation_fixtures.LearningObservationsTest.prepare

    def setUp(self):
        strategy_fixtures.LearningStrategiesTest.setUp(self)
        # This suite exercises selection, not elapsed-time energy recovery.
        spend = patch("seedbank.body.spend")
        spend.start()
        self.addCleanup(spend.stop)

    def pool(self):
        goal = self.plan(title="Reference practice", next_step="Write a note",
                         items=[{"text": "Identify a detail", "group": "note", "check": "feedback"}])
        rows = []
        for topic in ("orchard pruning", "ocean sailing", "volcano geology", "stellar astronomy"):
            result = learning.practice(self.pack, goal, "letter", topic, self.brain,
                                       criteria_id=self.listing(goal)["criteria"]["id"])
            review = self.review(goal, result["receipt"]["id"])
            rows.append(self.strategy(goal, review, text="Explain " + topic,
                                      transfer={"applies_when": topic, "avoid_when": "Insufficient evidence"}))
        target = self.plan(title="Explain a process", next_step="Choose a topic",
                           items=[{"text": "Explain the sequence", "group": "note", "check": "feedback"}])
        return rows, target

    def feedback_pool(self):
        target = self.plan(title="Return to note writing", next_step="Choose a new topic")
        own = self.practice(target)
        pinned = self.review(target, own["receipt"]["id"])
        other = self.plan(title="Other notes", next_step="Choose a topic")
        reviews = []
        for topic in ("orchard pruning", "ocean sailing", "volcano geology", "stellar astronomy", "desert ecology"):
            result = learning.practice(self.pack, other, "letter", topic, self.brain,
                                       criteria_id=self.listing(other)["criteria"]["id"])
            reviews.append(self.review(other, result["receipt"]["id"], reason="Review the evidence",
                                       next_step="Explain the source material"))
        strategy = self.strategy(other, reviews[0], text="Explain the pruning sequence",
                                 transfer={"applies_when": "orchard pruning", "avoid_when": "Missing source material"})
        return target, other, pinned, reviews, strategy

    def test_same_rubric_keeps_old_task_feedback_and_latest_current_goal_review(self):
        goal, _, pinned, reviews, strategy = self.feedback_pool()
        before = learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        selected = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})
        shown = {row["id"]: row for row in selected["feedback"]}
        self.assertEqual(len(shown), 4)
        self.assertIn(pinned["id"], shown)
        self.assertIn(reviews[0]["id"], shown)
        self.assertTrue(shown[pinned["id"]]["retrieval"]["current_goal_latest"])
        self.assertEqual(shown[reviews[0]["id"]]["retrieval"]["basis"], "task_match")
        self.assertEqual(shown[reviews[0]["id"]]["attempt_choices"]["task"]["topic"], "orchard pruning")
        self.assertEqual([row["id"] for row in selected["adjustments"]], [strategy["id"]])
        self.assertEqual(before, (learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))
        self.assertTrue(all("retrieval" not in row for row in learning.read(self.pack)))

    def test_creation_receipt_tracks_only_selected_same_rubric_feedback(self):
        goal, _, pinned, reviews, strategy = self.feedback_pool()
        result = learning.practice(self.pack, goal, "letter", "orchard pruning", self.brain,
                                   criteria_id=self.listing(goal)["criteria"]["id"])
        supplied = self.brain.calls[-1]["practice"]
        actual = result["receipt"]["data"]["practice"]
        self.assertIn(reviews[0]["id"], actual["feedback_ids"])
        self.assertIn(pinned["id"], actual["feedback_ids"])
        self.assertEqual(actual["feedback_ids"], [row["id"] for row in supplied["feedback"]])
        self.assertEqual(actual["adjustment_ids"], [strategy["id"]])
        self.assertEqual(self.listing(goal)["goal"]["status"], "active")

    def test_task_match_does_not_restore_revised_feedback_or_its_strategy(self):
        goal, other, _, reviews, strategy = self.feedback_pool()
        revised = self.review(other, reviews[0]["data"]["outcome_id"], reason="The earlier judgment was mistaken")
        selected = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})
        self.assertIn(revised["id"], [row["id"] for row in selected["feedback"]])
        self.assertNotIn(reviews[0]["id"], [row["id"] for row in selected["feedback"]])
        self.assertNotIn(strategy["id"], [row["id"] for row in selected["adjustments"]])

    def test_task_matching_never_recovers_forgotten_or_private_feedback(self):
        goal, _, _, reviews, _ = self.feedback_pool()
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        self.assertEqual(learning.for_goal(self.pack, goal, loaded=learning.view(self.pack, policy=policy),
                                          task={"topic": "orchard pruning"}), {})
        ref = reviews[0]["evidence"][0]
        append_memories(self.pack, [{"id": "m_old_feedback", "day": 1, "kind": "thought", "text": "source",
                                    "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_old_feedback")
        selected = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})
        self.assertNotIn(reviews[0]["id"], [row["id"] for row in selected.get("feedback", [])])

    def test_old_relevant_experience_survives_three_newer_unrelated_records(self):
        rows, goal = self.pool()
        before = learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        lessons = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})["lessons"]
        self.assertEqual(lessons[0]["id"], rows[0]["id"])
        self.assertEqual(lessons[0]["retrieval"]["basis"], "task_match")
        self.assertEqual(len(lessons), 3)
        self.assertEqual(before, (learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))
        self.assertNotIn("mastery", lessons[0])

    def test_actual_creation_uses_its_task_and_records_only_supplied_lessons(self):
        rows, goal = self.pool()
        result = learning.practice(self.pack, goal, "letter", "orchard pruning", self.brain,
                                   criteria_id=self.listing(goal)["criteria"]["id"])
        supplied = self.brain.calls[-1]["practice"]["lessons"]
        self.assertEqual(supplied[0]["id"], rows[0]["id"])
        self.assertEqual(result["receipt"]["data"]["practice"]["lesson_ids"], sorted(row["id"] for row in supplied))
        self.assertEqual(self.listing(goal)["goal"]["status"], "active")

    def test_different_task_selects_different_experience_without_rewriting_source(self):
        rows, goal = self.pool()
        first = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})["lessons"]
        second = learning.for_goal(self.pack, goal, task={"topic": "stellar astronomy"})["lessons"]
        self.assertEqual(first[0]["id"], rows[0]["id"])
        self.assertEqual(second[0]["id"], rows[-1]["id"])
        self.assertTrue(all("retrieval" not in row for row in learning.read(self.pack)))

    def test_revised_feedback_does_not_restore_an_old_relevant_strategy(self):
        rows, goal = self.pool()
        old = rows[0]
        original = next(row for row in learning.read(self.pack) if row["id"] == old["data"]["feedback_id"])
        self.review(old["goal_id"], original["data"]["outcome_id"], reason="The earlier interpretation was mistaken")
        lessons = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})["lessons"]
        self.assertNotIn(old["id"], [row["id"] for row in lessons])

    def test_forgotten_source_cannot_return_through_task_matching(self):
        rows, goal = self.pool()
        ref = rows[0]["evidence"][0]
        append_memories(self.pack, [{"id": "m_retrieval_source", "day": 1, "kind": "thought", "text": "source",
                                    "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_retrieval_source")
        lessons = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})["lessons"]
        self.assertNotIn(rows[0]["id"], [row["id"] for row in lessons])

    def test_private_experience_does_not_leak_through_query_matching(self):
        rows, goal = self.pool()
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        selected = learning.for_goal(self.pack, goal, loaded=learning.view(self.pack, policy=policy),
                                     task={"topic": "orchard pruning"})
        self.assertEqual(selected, {})
        self.assertNotIn(rows[0]["id"], json.dumps(learning.context(self.pack, policy=policy)))

    def test_old_caution_survives_newer_positive_observations_and_reaches_dependencies(self):
        strategy, goal, first = self.prepare()
        caution = self.observe(strategy, goal, first, fit="not_applicable", effect="harmful", reason="照搬语气不合适")
        for index in range(4):
            outcome = self.practice(goal)["receipt"]["id"]
            self.observe(strategy, goal, outcome, reason=f"这一次表达清楚 {index}")
        selected = learning.for_goal(self.pack, goal)["lessons"][0]
        self.assertEqual(selected["observation_count"], 5)
        self.assertEqual(len(selected["observations"]), 3)
        self.assertIn(caution["id"], [row["feedback_id"] for row in selected["observations"]])
        self.assertIn("helpful", [row["effect"] for row in selected["observations"]])
        result = self.practice(goal)["receipt"]["data"]
        self.assertIn(caution["id"], result["practice"]["lesson_observation_ids"])
        self.assertIn(caution["evidence"][0]["id"], result["generation"]["context_dependencies"])

    def test_revised_caution_is_not_resurrected_by_balanced_selection(self):
        strategy, goal, first = self.prepare()
        caution = self.observe(strategy, goal, first, fit="not_applicable", effect="harmful")
        updated = self.observe(strategy, goal, first, reason="核对后修正了此前判断")
        observations = learning.for_goal(self.pack, goal)["lessons"][0]["observations"]
        self.assertEqual([row["feedback_id"] for row in observations], [updated["id"]])
        self.assertNotIn(caution["id"], [row["feedback_id"] for row in observations])

    def test_trimmed_candidate_and_caution_are_not_claimed_as_supplied(self):
        strategy, goal, first = self.prepare()
        self.observe(strategy, goal, first, effect="harmful")

        class TrimmedBrain(fixtures.FixtureBrain):
            def compose(self, ctx):
                result = super().compose(ctx)
                practice = deepcopy(ctx["practice"])
                practice["lessons"] = []
                return {**result, "_used_practice": practice, "_used_learning": []}

        result = self.practice(goal, brain=TrimmedBrain())["receipt"]["data"]
        self.assertEqual(result["practice"]["lesson_ids"], [])
        self.assertEqual(result["practice"]["lesson_observation_ids"], [])

    def test_backup_preserves_history_and_rebuilds_same_selection(self):
        rows, goal = self.pool()
        saved = backup.create(self.pack)
        restored = self.pack.parent / "retrieval-restored.life"
        backup.restore(saved["file"], restored)
        before = learning.for_goal(self.pack, goal, task={"topic": "orchard pruning"})["lessons"]
        after = learning.for_goal(restored, goal, task={"topic": "orchard pruning"})["lessons"]
        self.assertEqual(before, after)
        self.assertEqual(after[0]["id"], rows[0]["id"])


class RetrievalSelectionTest(unittest.TestCase):
    def test_prompt_budget_preserves_relevant_feedback_with_its_adjustment(self):
        feedback = [{"id": key, "text": "x" * 950, "retrieval": {"rank": rank}}
                    for key, rank in (("old-relevant", 1), ("new-unrelated", 3), ("newest-unrelated", 2))]
        ctx = {"_cfg": {"input_budget": 2600}, "practice": {"feedback": feedback,
               "adjustments": [{"id": "a-" + row["id"], "data": {"feedback_id": row["id"]},
                                "retrieval": dict(row["retrieval"])} for row in feedback]}}
        original = deepcopy(ctx)
        _, used, report = context_window.fit(ctx, lambda current: {"user": json.dumps(current.get("practice", {}))})
        self.assertTrue(report["limited"])
        self.assertEqual([row["id"] for row in used["practice"]["feedback"]], ["old-relevant"])
        self.assertEqual([row["id"] for row in used["practice"]["adjustments"]], ["a-old-relevant"])
        reference = learning.practice_reference(used["practice"], "provided_to_creator")
        self.assertEqual(reference["feedback_ids"], ["old-relevant"])
        self.assertEqual(reference["adjustment_ids"], ["a-old-relevant"])
        self.assertEqual(ctx, original)

    def test_compact_prompt_omits_local_ranks_but_keeps_feedback_and_original_task(self):
        feedback = {"kind": "feedback", "id": "f1", "data": {"reason": "Keep this feedback"},
                    "attempt_choices": {"task": {"topic": "orchard pruning"}},
                    "retrieval": {"rank": 1, "current_goal_latest": True}}
        item = {"feedback": [feedback], "adjustments": [{"kind": "adjustment", "id": "a1",
                "data": {"feedback_id": "f1"}, "retrieval": {"rank": 1}}]}
        before = deepcopy(item)
        supplied = json.loads(learning.prompt_lines([item], compact=True).rsplit("\n", 1)[-1])[0]
        self.assertNotIn("retrieval", supplied["feedback"][0])
        self.assertNotIn("retrieval", supplied["adjustments"][0])
        self.assertEqual(supplied["feedback"][0]["data"], feedback["data"])
        self.assertEqual(supplied["feedback"][0]["attempt_choices"], feedback["attempt_choices"])
        self.assertEqual(item, before)

    def test_prompt_budget_does_not_evict_latest_current_goal_feedback_for_old_match(self):
        rows = [{"id": "current-review", "text": "x" * 1600,
                 "retrieval": {"rank": 2, "current_goal_latest": True}},
                {"id": "old-match", "text": "x" * 1600, "retrieval": {"rank": 1}}]
        ctx = {"_cfg": {"input_budget": 2600}, "practice": {"feedback": rows}}
        _, used, report = context_window.fit(ctx, lambda current: {"user": json.dumps(current.get("practice", {}))})
        self.assertTrue(report["limited"])
        self.assertEqual([row["id"] for row in used["practice"]["feedback"]], ["current-review"])

    def test_matching_exclusion_is_explicit_and_repetition_does_not_boost_rank(self):
        documents = [{"applies_when": "real evidence", "avoid_when": "fiction poetry"},
                     {"applies_when": "fiction fiction fiction", "avoid_when": ""}]
        order, reports = learning_retrieval.rank(documents, {"task": "fiction poetry"})
        self.assertEqual(order[0], 0)
        self.assertIn("avoid_when", reports[0]["matched_fields"])
        repeated = learning_retrieval.rank([{**documents[0], "avoid_when": "fiction poetry " * 100}, documents[1]],
                                           {"task": "fiction poetry"})
        self.assertEqual((order, reports), repeated)

    def test_four_language_terms_and_unmatched_recent_fallback(self):
        for text in ("果园修剪", "果樹の剪定", "과수 가지치기", "ORCHARD PRUNING"):
            with self.subTest(text=text):
                order, reports = learning_retrieval.rank([{"task": text}, {"task": "unrelated"}], {"task": text})
                self.assertEqual(order[0], 0)
                self.assertEqual(reports[0]["basis"], "task_match")
        order, reports = learning_retrieval.rank([{"task": "first"}, {"task": "second"}], {"task": "unmatched"})
        self.assertEqual(order, [1, 0])
        self.assertEqual(reports[1]["basis"], "recent_fallback")

    def test_prompt_budget_keeps_highest_relevance_without_mutating_input(self):
        ctx = {"_cfg": {"input_budget": 2600},
               "practice": {"lessons": [{"id": key, "text": key * 350} for key in ("top", "mid", "low")]}}
        original = deepcopy(ctx)
        _, used, report = context_window.fit(ctx, lambda current: {"user": json.dumps(current.get("practice", {}))})
        self.assertTrue(report["limited"])
        self.assertEqual([row["id"] for row in used["practice"]["lessons"]], ["top"])
        self.assertEqual(ctx, original)


if __name__ == "__main__":
    unittest.main()
