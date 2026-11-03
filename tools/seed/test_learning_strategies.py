"""User-run tests for bounded cross-task experience. Authored, not executed."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_learning as fixtures
from seedbank import backup, disclosure, experience, learning, learning_strategies, requests
from seedbank.brain import build_compose_prompt
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import forget_memory
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories, write_file_atomic, write_json_atomic


class LearningStrategiesTest(unittest.TestCase):
    plan = fixtures.LearningTest.plan
    practice = fixtures.LearningTest.practice
    listing = fixtures.LearningTest.listing
    review = fixtures.LearningTest.review

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-strategy-home-")
        self.addCleanup(folder.cleanup)
        environment = patch.dict(os.environ, {"HOME": folder.name, "USERPROFILE": folder.name, "SEEDBANK_LANG": "zh_CN"})
        environment.start()
        self.addCleanup(environment.stop)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No real service"))
        guard.start()
        self.addCleanup(guard.stop)
        fixtures.LearningTest.setUp(self)

    def source(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        review = self.review(goal, outcome, {"c1": "not_met"}, reason="感谢太笼统", next_step="写出具体的帮助")
        return goal, outcome, review

    def data(self, goal, review, **extra):
        previous = learning_strategies.latest(learning.read(self.pack)).get(review["id"], {})
        return {"goal_id": goal, "feedback_id": review["id"], "expected": previous.get("id", ""),
                "text": "先描述一件具体发生的事，再说明感受。", "expected_result": "读者能指出具体是哪件事。",
                "transfer": {"applies_when": "需要说明一件真实经历时", "avoid_when": "虚构任务，或没有足够事实时"}, **extra}

    def strategy(self, goal, review, **extra):
        return learning.perform(self.pack, "strategy", self.data(goal, review, **extra))["record"]

    def next_goal(self, **extra):
        return self.plan([{"text": "解释一次合作中自己的具体贡献", "group": "说明", "check": "feedback"}],
                         title="写一段合作回顾", **extra)

    def test_different_task_gets_bounded_experience_and_records_what_was_provided(self):
        goal, _, review = self.source()
        strategy = self.strategy(goal, review)
        next_goal = self.next_goal()
        receipt = self.practice(next_goal)["receipt"]["data"]
        ctx = self.brain.calls[-1]
        self.assertEqual(ctx["practice"]["lessons"][0]["id"], strategy["id"])
        self.assertTrue(all("lessons" not in item for item in ctx["learning"]))
        prompt = build_compose_prompt(ctx)["user"]
        self.assertIn(strategy["data"]["text"], prompt)
        self.assertIn("虚构任务", prompt)
        self.assertIn("感谢太笼统", prompt)
        self.assertEqual(receipt["practice"]["lesson_ids"], [strategy["id"]])
        self.assertEqual(receipt["practice"]["task"]["topic"], "感谢昨天整理材料的帮助")
        self.assertEqual(receipt["practice"]["scope"], "provided_to_creator")
        self.assertEqual(self.listing(next_goal)["attempts"][0]["offered_lessons"][0]["id"], strategy["id"])
        self.assertFalse(learning.evaluate(self.pack, next_goal, {})["passed"])

    def test_omitted_experience_is_not_reported_as_provided_to_creator(self):
        goal, _, review = self.source()
        self.strategy(goal, review)
        next_goal = self.next_goal()

        class TrimmedBrain(fixtures.FixtureBrain):
            def compose(self, ctx):
                result = super().compose(ctx)
                practice = deepcopy(ctx["practice"])
                practice["lessons"] = []
                return {**result, "_used_practice": practice, "_used_learning": []}

        self.assertEqual(self.practice(next_goal, brain=TrimmedBrain())["receipt"]["data"]["practice"]["lesson_ids"], [])

    def test_same_rubric_and_other_skill_do_not_claim_cross_task_transfer(self):
        goal, _, review = self.source()
        row = self.strategy(goal, review)
        same = self.plan()
        other = self.next_goal(skill="计算")
        self.assertEqual(learning.for_goal(self.pack, same)["lessons"], [])
        self.assertEqual(learning.for_goal(self.pack, other)["lessons"], [])
        self.assertEqual(learning.for_goal(self.pack, same)["adjustments"][0]["id"], row["id"])

    def test_reuse_requires_both_boundaries_and_can_be_disabled(self):
        goal, _, review = self.source()
        with self.assertRaises(SeedError):
            self.strategy(goal, review, transfer={"applies_when": "任何时候"})
        self.assertEqual(requests.pending(self.pack), [])
        self.strategy(goal, review, transfer={})
        self.assertEqual(learning.for_goal(self.pack, self.next_goal())["lessons"], [])

    def test_user_revision_preserves_history_and_model_cannot_overwrite_it(self):
        goal, _, review = self.source()
        first = self.strategy(goal, review)
        before = learning.path(self.pack).read_bytes()
        second = self.strategy(goal, review, text="先说明事实，再标明不确定之处。")
        self.assertTrue(learning.path(self.pack).read_bytes().startswith(before))
        self.assertEqual(second["data"]["supersedes"], first["id"])
        result = learning.apply_adjustments(self.pack, [{"feedback_id": review["id"], "text": "模型覆盖用户", "expected_result": "替代"}],
            available=[review["id"]], day=self.day["dayNo"], source="mind/experiences.jsonl", runner="fixture")
        self.assertEqual(result, [])
        attempt = self.listing(goal)["attempts"][0]
        self.assertEqual(attempt["adjustment"]["id"], second["id"])
        self.assertEqual(attempt["strategy_history_total"], 2)

    def test_model_may_propose_a_first_bounded_experience_from_visible_feedback(self):
        goal, _, review = self.source()
        data = self.data(goal, review)
        result = learning.apply_adjustments(self.pack, [data], available=[review["id"]], day=self.day["dayNo"],
            source="mind/experiences.jsonl", runner="fixture", generation=disclosure.stamp("owner"))
        self.assertEqual(result[0]["origin"], "model")
        self.assertEqual(result[0]["format"], "seedbank/learning@2")
        self.assertEqual(learning.for_goal(self.pack, self.next_goal())["lessons"][0]["id"], result[0]["id"])

    def test_stale_page_and_retry_identity_are_enforced(self):
        goal, _, review = self.source()
        data = self.data(goal, review)
        first = learning.perform(self.pack, "strategy", data, request_id="same")
        replay = learning.perform(self.pack, "strategy", data, request_id="same")
        self.assertEqual(first["record"], replay["record"])
        self.assertTrue(replay["replayed"])
        with self.assertRaises(SeedError):
            learning.perform(self.pack, "strategy", data, request_id="stale")
        with self.assertRaises(SeedError):
            learning.perform(self.pack, "strategy", {**data, "text": "另一条输入"}, request_id="same")
        self.assertEqual(requests.pending(self.pack), [])

    def test_updated_feedback_retires_strategy_and_known_descendants_but_keeps_original_work(self):
        goal, outcome, review = self.source()
        row = self.strategy(goal, review)
        next_goal = self.next_goal()
        derived = self.practice(next_goal)["receipt"]["data"]
        self.review(goal, outcome, {"c1": "unclear"}, reason="重新核对，原评价不够可靠")
        self.assertEqual(learning.for_goal(self.pack, next_goal)["lessons"], [])
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(row["source"].split("#")[1], policy.blocked)
        self.assertIn(derived["evidence"][0]["id"], policy.blocked)
        self.assertEqual(self.listing(goal)["attempts"][0]["artifact_view"]["state"], "unchanged")

    def test_changed_source_artifact_retires_experience(self):
        goal, _, review = self.source()
        row = self.strategy(goal, review)
        next_goal = self.next_goal()
        path = self.pack / "mind/works.json"
        # The stored work format is a collection with stable work IDs.
        work_id = self.listing(goal)["attempts"][0]["artifact"].split("#")[1]
        from seedbank.works import load_works
        data = load_works(self.pack)
        next(r for r in data["works"] if r["id"] == work_id)["text"] = "外部改动后的正文"
        write_json_atomic(path, data)
        self.assertEqual(learning.for_goal(self.pack, next_goal)["lessons"], [])
        self.assertIn(row["source"].split("#")[1], MemoryPolicy.load(self.pack).blocked)

    def test_completed_source_goal_can_still_support_another_task(self):
        goal, outcome, review = self.source()
        review = self.review(goal, outcome, {"c1": "met"})
        snapshot = self.listing(goal)
        learning.perform(self.pack, "complete", {"goal_id": goal, "criteria_id": snapshot["criteria"]["id"],
            "expected": snapshot["goal"]["event_id"], "evidence": {"c1": outcome}, "reason": "只确认这次条件"})
        row = self.strategy(goal, review)
        self.assertEqual(learning.for_goal(self.pack, self.next_goal())["lessons"][0]["id"], row["id"])

    def test_missing_latest_input_can_be_replaced_by_explicit_new_evidence(self):
        goal, _, review = self.source()
        row = self.strategy(goal, review)
        missing = row["evidence"][0]["id"]
        events = [r for r in experience.read(self.pack) if r["id"] != missing]
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in events))
        self.assertEqual(self.listing(goal)["attempts"][0]["adjustment"], {})
        repaired = self.strategy(goal, review, text="根据仍可用的反馈重新整理")
        self.assertEqual(self.listing(goal)["attempts"][0]["adjustment"]["id"], repaired["id"])
        self.assertEqual(repaired["data"]["supersedes"], row["id"])

    def test_revised_or_withdrawn_latest_strategy_never_restores_previous_version(self):
        goal, _, review = self.source()
        self.strategy(goal, review)
        second = self.strategy(goal, review, text="修订后的做法")
        ref = second["evidence"][0]
        append_memories(self.pack, [{"id": "m_latest_strategy", "day": 1, "kind": "thought", "text": "经验依据",
            "source": ref["source"], "event_ids": [ref["id"]]}])
        forget_memory(self.pack, "m_latest_strategy")
        self.assertEqual(learning.for_goal(self.pack, self.next_goal())["lessons"], [])
        self.assertEqual(self.listing(goal)["attempts"][0]["adjustment"], {})

    def test_changed_strategy_text_is_not_trusted_with_an_old_input_digest(self):
        goal, _, review = self.source()
        row = self.strategy(goal, review)
        rows = learning.read(self.pack)
        next(r for r in rows if r["id"] == row["id"])["data"]["text"] = "没有依据的新策略"
        write_file_atomic(learning.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        self.assertEqual(self.listing(goal)["attempts"][0]["adjustment"], {})
        self.assertIn(row["source"].split("#")[1], MemoryPolicy.load(self.pack).blocked)

    def test_private_experience_is_not_available_in_group_context(self):
        goal, _, review = self.source()
        row = self.strategy(goal, review, text="PRIVATE_LESSON_379")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        view = learning.view(self.pack, policy=policy)
        self.assertNotIn(row["id"], [r["id"] for r in view["adjustments"].values()])
        self.assertNotIn("PRIVATE_LESSON_379", json.dumps(learning.context(self.pack, policy=policy)))

    def test_failed_save_rolls_back_and_backup_requires_explicit_resume(self):
        goal, _, review = self.source()
        data = self.data(goal, review)
        before = learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()
        with patch("seedbank.learning._append", side_effect=OSError("fixture")), self.assertRaises(OSError):
            learning.perform(self.pack, "strategy", data, request_id="recover")
        self.assertEqual(before, (learning.path(self.pack).read_bytes(), experience.path(self.pack).read_bytes()))
        saved = backup.create(self.pack)
        restored = self.pack.parent / "restored.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(requests.get(restored, "recover")["status"], "pending")
        result = Bridge(restored, "stub").handle({"op": "resume", "request_id": "recover"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(learning.listing(restored, goal)["attempts"][0]["adjustment"]["data"]["text"], data["text"])

    def test_cli_saves_a_strategy_without_calling_a_model(self):
        goal, _, review = self.source()
        file = self.pack.parent / "strategy.json"
        file.write_text(json.dumps(self.data(goal, review), ensure_ascii=False), encoding="utf-8")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["learning", "strategy", str(self.pack), "--data-file", str(file), "--brain", "stub"]), 0)
        self.assertEqual(json.loads(output.getvalue())["record"]["format"], "seedbank/learning@2")


if __name__ == "__main__":
    unittest.main()
