"""Offline strategy-choice regressions with temporary packs and fixture brains."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_learning as fixtures
import test_learning_observations as observations
from seedbank import backup, disclosure, experience, learning, learning_choices as choices, requests
from seedbank.brain import RemoteBrain, _validate_compose_result, build_compose_prompt
from seedbank.cognition import forget_memory
from seedbank.context_window import fit
from seedbank.util import read_json


class ChoiceBrain(fixtures.FixtureBrain):
    def __init__(self, declarations):
        super().__init__()
        self.declarations = declarations

    def compose(self, ctx):
        return {**super().compose(ctx), "strategy_choices": deepcopy(self.declarations)}


class LearningChoicesTest(unittest.TestCase):
    setUp = observations.LearningObservationsTest.setUp
    plan = observations.LearningObservationsTest.plan
    practice = observations.LearningObservationsTest.practice
    listing = observations.LearningObservationsTest.listing
    review = observations.LearningObservationsTest.review
    source = observations.LearningObservationsTest.source
    data = observations.LearningObservationsTest.data
    strategy = observations.LearningObservationsTest.strategy
    next_goal = observations.LearningObservationsTest.next_goal
    observation = observations.LearningObservationsTest.observation
    observe = observations.LearningObservationsTest.observe

    def setup_strategy(self):
        source, _, review = self.source()
        strategy = self.strategy(source, review)
        goal = self.next_goal()
        return strategy, goal

    def declaration(self, strategy, choice="adapt", **extra):
        return {"strategy_id": strategy["id"], "choice": choice, "reason": "这次需要说明合作贡献，而不是泛泛感谢",
                "application": "先交代整理材料的行动，再说明自己的贡献" if choice in ("adopt", "adapt") else "", **extra}

    def test_response_shape_requests_choices_for_both_candidate_sources(self):
        strategy, goal = self.setup_strategy()
        self.practice(goal)
        ctx = deepcopy(self.brain.calls[-1])
        for source in ("adjustments", "lessons"):
            with self.subTest(source=source):
                ctx["practice"]["adjustments"] = []
                ctx["practice"]["lessons"] = []
                ctx["practice"][source] = [strategy]
                prompt = build_compose_prompt(ctx)["user"]
                shape = json.loads(prompt.rsplit("\n", 1)[-1])
                self.assertEqual(set(shape), {"title", "text", "strategy_choices"})
                declaration = shape["strategy_choices"][0]
                self.assertEqual(set(declaration), {"strategy_id", "choice", "reason", "application"})
                self.assertEqual(set(declaration["choice"].split("|")), set(choices.CHOICES))
                self.assertIn(strategy["id"], prompt)

    def test_no_candidates_keep_simple_work_shape_and_task_criteria(self):
        goal = self.plan()
        self.practice(goal)
        ctx = deepcopy(self.brain.calls[-1])
        for practice in (ctx["practice"], {}):
            with self.subTest(practice=bool(practice)):
                prompt = build_compose_prompt({**ctx, "practice": practice})["user"]
                self.assertEqual(set(json.loads(prompt.rsplit("\n", 1)[-1])), {"title", "text"})
                self.assertNotIn("strategy_choices", prompt)
                if practice:
                    self.assertIn(practice["criteria"]["id"], prompt)

    def test_actual_context_trim_removes_choice_request_without_mutating_sources(self):
        _, goal = self.setup_strategy()
        self.practice(goal)
        ctx = deepcopy(self.brain.calls[-1])
        # Force the real fitter to remove this whole candidate, not merely
        # hide a field in a fixture brain's reported context.
        ctx["practice"]["lessons"][0]["data"]["text"] += " oversized-candidate" * 20000
        before = deepcopy(ctx)
        prompt, used, report = fit(ctx, build_compose_prompt)
        self.assertTrue(report["limited"])
        self.assertEqual(choices.candidates(used["practice"]), {})
        self.assertEqual(set(json.loads(prompt["user"].rsplit("\n", 1)[-1])), {"title", "text"})
        self.assertEqual(ctx, before)

    def test_default_budget_accepts_work_without_statement_without_retry(self):
        strategy, goal = self.setup_strategy()
        calls = []

        def transport(config, system, user):
            calls.append(user)
            return json.dumps({"title": "合作回顾", "text": "我负责整理材料并说明其中的分工。"}, ensure_ascii=False)

        result = self.practice(goal, brain=RemoteBrain("openai-compatible", transport))
        self.assertEqual(len(calls), 1)
        self.assertIn(strategy["id"], calls[0])
        self.assertIn("strategy_choices", json.loads(calls[0].rsplit("\n", 1)[-1]))
        self.assertTrue(result["succeeded"])
        receipt = result["receipt"]["data"]
        self.assertFalse(receipt["generation"]["fallback"])
        report = receipt["practice"]["strategy_choices"]
        self.assertEqual(report["state"], "not_reported")
        self.assertEqual(report["items"], [])
        self.assertEqual(report["unreported_ids"], [strategy["id"]])

    def test_each_choice_is_attributed_and_does_not_complete_goal_or_change_feedback(self):
        strategy, goal = self.setup_strategy()
        for choice in choices.CHOICES:
            result = self.practice(goal, brain=ChoiceBrain([self.declaration(strategy, choice)]))
            report = result["receipt"]["data"]["practice"]["strategy_choices"]
            self.assertEqual(report["state"], "recorded")
            self.assertEqual(report["items"][0]["choice"], choice)
            self.assertEqual(report["items"][0]["strategy_hash"], choices.strategy_hash(strategy))
            self.assertEqual(report["origin"], "model_statement")
            listing = self.listing(goal)
            shown = listing["attempts"][0]["strategy_choices"]
            self.assertEqual(shown["items"][0]["strategy"], strategy["data"]["text"])
            self.assertTrue(shown["items"][0]["currently_available"])
            self.assertEqual(listing["attempts"][0]["feedback"], {})
            self.assertEqual(listing["goal"]["status"], "active")
            self.assertFalse(learning.evaluate(self.pack, goal, {})["passed"])

    def test_unknown_ids_duplicates_and_bad_fields_do_not_turn_into_use_claims(self):
        strategy, goal = self.setup_strategy()
        good = self.declaration(strategy)
        practice = learning.for_goal(self.pack, goal)
        generation = {"runner": "fixture", "model": "fixture", "fallback": False}
        for raw in ([{**good, "strategy_id": "invented"}], [good, {**good, "choice": "adopt"}],
                    [{**good, "reason": ""}], [{**good, "application": "x" * 301}],
                    [{**good, "choice": "skip"}], [{**good, "choice": "mastered"}],
                    [{**good, "score": 100}], [None], True, [good] * 13):
            with self.subTest(raw=raw):
                result = choices.collect(raw, practice, generation)
                self.assertEqual(result["state"], "invalid_report")
                self.assertEqual(result["items"], [])
                self.assertEqual(result["unreported_ids"], [strategy["id"]])
        made = self.practice(goal, brain=ChoiceBrain([good, {**good, "strategy_id": "invented"}]))
        self.assertEqual(made["receipt"]["data"]["status"], "succeeded")
        report = self.listing(goal)["attempts"][0]["strategy_choices"]
        self.assertEqual(report["state"], "partial")
        self.assertEqual(report["rejected_count"], 1)
        self.assertEqual(len(report["items"]), 1)

    def test_missing_statement_and_fallback_never_mean_rejected_or_used(self):
        strategy, goal = self.setup_strategy()
        result = self.practice(goal)["receipt"]["data"]
        report = result["practice"]["strategy_choices"]
        self.assertEqual(report["state"], "not_reported")
        self.assertEqual(report["items"], [])
        self.assertEqual(report["unreported_ids"], [strategy["id"]])

        class Fallback(ChoiceBrain):
            def compose(self, ctx):
                return {**super().compose(ctx), "_generation": {"runner": "stub", "model": None, "fallback": True}}

        result = self.practice(goal, brain=Fallback([self.declaration(strategy)]))["receipt"]["data"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["artifact"], "")
        self.assertEqual(result["practice"]["scope"], "available_at_execution")
        self.assertNotIn("strategy_choices", result["practice"])
        # A fallback has no saved work or model declaration. The standalone
        # declaration collector also refuses to attribute its text to a model.
        report = choices.collect([self.declaration(strategy)], learning.for_goal(self.pack, goal),
                                 {"runner": "stub", "model": None, "fallback": True})
        self.assertEqual(report["state"], "no_model_report")
        self.assertEqual(report["items"], [])

    def test_candidates_removed_by_actual_prompt_cannot_be_claimed(self):
        strategy, goal = self.setup_strategy()

        class Trimmed(ChoiceBrain):
            def compose(self, ctx):
                practice = deepcopy(ctx["practice"])
                practice["lessons"] = []
                return {**super().compose(ctx), "_used_practice": practice, "_used_learning": []}

        receipt = self.practice(goal, brain=Trimmed([self.declaration(strategy)]))["receipt"]["data"]
        self.assertEqual(receipt["practice"]["lesson_ids"], [])
        report = receipt["practice"]["strategy_choices"]
        self.assertEqual(report["candidate_ids"], [])
        self.assertEqual(report["items"], [])
        self.assertEqual(report["state"], "invalid_report")

    def test_same_rubric_adjustments_are_choices_too(self):
        source, _, review = self.source()
        strategy = self.strategy(source, review)
        outcome = self.practice(source, brain=ChoiceBrain([self.declaration(strategy)]))["receipt"]["data"]
        self.assertEqual(outcome["practice"]["lesson_ids"], [])
        self.assertEqual(outcome["practice"]["adjustment_ids"], [strategy["id"]])
        self.assertEqual(self.listing(source)["attempts"][0]["strategy_choices"]["items"][0]["strategy_id"], strategy["id"])

    def test_conflicting_user_observation_stays_distinct_and_reaches_next_attempt(self):
        strategy, goal = self.setup_strategy()
        result = self.practice(goal, brain=ChoiceBrain([self.declaration(strategy, "adopt")]))
        review = self.observe(strategy, goal, result["receipt"]["id"], use="not_observed", effect="uncertain",
                              reason="自述参考了经验，但作品没有清楚说明个人贡献", quote="")
        context = learning.for_goal(self.pack, goal)
        past = next(r for r in context["feedback"] if r["id"] == review["id"])["attempt_choices"]
        self.assertEqual(past["items"][0]["choice"], "adopt")
        lesson = context["lessons"][0]
        observation = lesson["observations"][0]
        self.assertEqual(observation["model_choice"]["choice"], "adopt")
        self.assertEqual(observation["use"], "not_observed")
        self.assertEqual(observation["effect"], "uncertain")
        self.practice(goal)
        prompt = build_compose_prompt(self.brain.calls[-1])["user"]
        self.assertIn("自述参考了经验", prompt)
        self.assertIn("model_statement", prompt)
        self.assertIn("not_observed", prompt)
        self.assertIn("strategy_choices", prompt)

    def test_source_or_receipt_mismatch_cannot_supply_statement_to_prompt(self):
        strategy, goal = self.setup_strategy()
        identifier = self.practice(goal, brain=ChoiceBrain([self.declaration(strategy)]))["receipt"]["id"]
        loaded = learning.view(self.pack)
        outcome = loaded["outcomes"][identifier]
        for target in ("receipt", "source", "hash", "offered"):
            row, state = deepcopy(outcome), deepcopy(loaded)
            source_id = row["source"].split("#")[-1]
            if target == "receipt":
                row["practice"]["strategy_choices"]["items"][0]["reason"] = "被替换的理由"
            elif target == "source":
                state["originals"].pop(source_id)
            elif target == "hash":
                row["practice"]["strategy_choices"]["items"][0]["strategy_hash"] = "0" * 64
                state["originals"][source_id]["metadata"]["strategy_choices"] = deepcopy(row["practice"]["strategy_choices"])
            else:
                row["practice"]["lesson_ids"] = []
            with self.subTest(target=target):
                projection = choices.projection(self.pack, row, state)
                self.assertEqual(projection["state"], "invalid_source")
                self.assertEqual(projection["items"], [])

    def test_changed_work_hides_statement_while_preserving_source_history(self):
        strategy, goal = self.setup_strategy()
        result = self.practice(goal, brain=ChoiceBrain([self.declaration(strategy)]))
        loaded = learning.view(self.pack)
        outcome = loaded["outcomes"][result["receipt"]["id"]]
        before = experience.path(self.pack).read_bytes()
        with patch("seedbank.learning.artifact_state", return_value={"state": "changed", "text": ""}):
            report = choices.projection(self.pack, outcome, loaded)
        self.assertEqual(report["state"], "artifact_unavailable")
        self.assertEqual(report["items"], [])
        self.assertEqual(experience.path(self.pack).read_bytes(), before)

    def test_private_statements_do_not_reach_group_and_retired_strategy_is_not_reused(self):
        strategy, goal = self.setup_strategy()
        made = self.practice(goal, brain=ChoiceBrain([self.declaration(strategy, reason="PRIVATE_CHOICE_915")]))
        self.observe(strategy, goal, made["receipt"]["id"])
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        self.assertNotIn("PRIVATE_CHOICE_915", json.dumps(learning.context(self.pack, policy=policy), ensure_ascii=False))
        self.assertNotIn("PRIVATE_CHOICE_915", json.dumps(learning.context(self.pack, policy=policy)))
        from seedbank.util import append_memories
        source_id = strategy["evidence"][0]["id"]
        append_memories(self.pack, [{"id": "m_choice_source", "day": self.day["dayNo"], "text": "来源标记",
                                   "kind": "thought", "source": strategy["source"], "event_ids": [source_id]}])
        forget_memory(self.pack, "m_choice_source")
        self.assertEqual(learning.for_goal(self.pack, goal)["lessons"], [])

    def test_completed_retry_and_backup_keep_one_work_and_choice_report(self):
        strategy, goal = self.setup_strategy()
        brain = ChoiceBrain([self.declaration(strategy)])
        first = self.practice(goal, brain=brain, identifier="choice-once")
        second = self.practice(goal, brain=brain, identifier="choice-once")
        self.assertTrue(second["replayed"])
        self.assertEqual(len(brain.calls), 1)
        self.assertEqual(first["receipt"], second["receipt"])
        archive = backup.create(self.pack)
        restored = self.pack.parent / "choices-restored.life"
        backup.restore(archive["file"], restored)
        report = learning.listing(restored, goal)["attempts"][0]["strategy_choices"]
        self.assertEqual(report["items"][0]["strategy_id"], strategy["id"])
        self.assertEqual(report["state"], "recorded")

    def test_interrupted_outcome_rolls_back_work_and_source_until_explicit_resume(self):
        strategy, goal = self.setup_strategy()
        brain = ChoiceBrain([self.declaration(strategy)])
        previous = read_json(self.pack / "mind/works.json")
        events = experience.path(self.pack).read_bytes()
        with patch("seedbank.development.record_outcome", side_effect=OSError("fixture interrupted receipt")), self.assertRaises(OSError):
            self.practice(goal, brain=brain, identifier="pending-choice")
        self.assertEqual(read_json(self.pack / "mind/works.json"), previous)
        self.assertEqual(experience.path(self.pack).read_bytes(), events)
        self.assertEqual(requests.get(self.pack, "pending-choice")["status"], "pending")
        result = self.practice(goal, brain=brain, identifier="pending-choice")
        self.assertFalse(result["replayed"])
        self.assertEqual(self.listing(goal)["attempts"][0]["strategy_choices"]["state"], "recorded")
        self.assertEqual(len(brain.calls), 2)  # The interrupted model call was not a committed work.

    def test_remote_json_parser_retains_choice_and_old_records_stay_unreported(self):
        strategy, goal = self.setup_strategy()
        declaration = self.declaration(strategy)
        payload = {"title": "合作回顾", "text": "我负责整理材料并说明其中的分工。", "strategy_choices": [declaration]}
        self.assertEqual(_validate_compose_result(payload)["strategy_choices"], [declaration])
        calls = []
        def transport(config, system, user):
            calls.append(user)
            return json.dumps(payload, ensure_ascii=False)
        class WideContextRemote(RemoteBrain):
            def compose(self, ctx):
                return super().compose({**ctx, "_cfg": {**ctx.get("_cfg", {}), "input_budget": 100000}})
        remote = WideContextRemote("openai-compatible", transport)
        result = self.practice(goal, brain=remote)
        self.assertEqual(len(calls), 1)
        self.assertIn("strategy_choices", calls[0])
        self.assertEqual(result["receipt"]["data"]["practice"]["strategy_choices"]["items"][0]["strategy_id"], strategy["id"])
        old = deepcopy(learning.view(self.pack)["outcomes"][result["receipt"]["id"]])
        old["practice"].pop("strategy_choices")
        self.assertEqual(choices.projection(self.pack, old, learning.view(self.pack))["state"], "not_recorded")


if __name__ == "__main__":
    unittest.main()
