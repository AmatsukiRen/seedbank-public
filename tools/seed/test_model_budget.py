"""User-run offline checks: a response and its actions share one allowance."""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
from unittest.mock import Mock, patch

import test_action_outcomes as fixtures
from seedbank import actions, brain, cognition, development, model_budget


class ModelBudgetScopeTest(unittest.TestCase):
    def test_nested_scope_cannot_reset_allowance_and_next_activity_is_fresh(self):
        with model_budget.scope():
            model_budget.reserve(2)
            first = model_budget.snapshot()["id"]
            with model_budget.scope():
                model_budget.reserve(3)
                self.assertEqual(model_budget.snapshot()["id"], first)
                with self.assertRaises(model_budget.Exhausted):
                    model_budget.reserve(3)
        self.assertEqual(model_budget.snapshot(), {})
        with model_budget.scope():
            model_budget.reserve(1)
            self.assertNotEqual(model_budget.snapshot()["id"], first)

    def test_exception_and_parallel_activities_do_not_leak_allowance(self):
        def activity():
            with model_budget.scope():
                model_budget.reserve(1)
                return model_budget.snapshot()
        with self.assertRaises(ValueError):
            with model_budget.scope():
                model_budget.reserve(1)
                raise ValueError("fixture")
        with ThreadPoolExecutor(max_workers=2) as executor:
            rows = list(executor.map(lambda _: activity(), range(2)))
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        self.assertTrue(all(row["reserved_calls"] == 1 for row in rows))
        self.assertEqual(model_budget.snapshot(), {})


class ModelActionBudgetTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp
    proposal = fixtures.ActionOutcomesTest.proposal

    def configured(self, limit, replies):
        transport = Mock(side_effect=[json.dumps(reply, ensure_ascii=False) for reply in replies])
        inner = brain.RemoteBrain("codex", transport)
        return brain._CfgBrain({"codex_max_calls": limit, "input_budget": 16000}, inner), transport

    def prompts(self):
        # Keep real admission, actions, durable receipts and retrieval; only the
        # serialization cost and external service are replaced in this fixture.
        return patch.object(brain, "fit_context", side_effect=lambda ctx, builder:
                            ({"system": "runtime", "user": "synthetic input"}, ctx, {}))

    def response(self):
        return {"reply": "想试写一份初稿，执行结果以回执为准。", "actions": [self.proposal("compose")]}

    def test_one_call_stops_nested_creation_before_attempt_and_replay_is_free(self):
        remote, transport = self.configured(1, [self.response()])
        with self.prompts():
            result = cognition.chat_turn(self.pack, "请记录这次帮助。", remote, request_id="budget-one")
            repeated = cognition.chat_turn(self.pack, "请记录这次帮助。", remote, request_id="budget-one")
        self.assertEqual(transport.call_count, 1)
        receipt = result["actionResults"][0]["data"]
        self.assertEqual((receipt["status"], receipt["attempt_state"]), ("blocked", "not_started"))
        self.assertEqual(receipt["detail"], model_budget.BLOCKED)
        self.assertFalse(receipt["artifact"])
        self.assertEqual(development.current_state(self.pack)["skills"], {})
        self.assertEqual(result["modelBudget"]["reserved_calls"], 1)
        self.assertEqual(result["modelBudget"], repeated["modelBudget"])
        self.assertIn(model_budget.BLOCKED, result["reply"])

    def test_two_calls_allow_response_and_creation_in_one_activity(self):
        remote, transport = self.configured(2, [self.response(), {"title": "初稿", "text": "谢谢你一起整理资料。"}])
        with self.prompts():
            result = cognition.chat_turn(self.pack, "可以试写一份初稿。", remote)
        self.assertEqual(transport.call_count, 2)
        receipt = result["actionResults"][0]["data"]
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(receipt["generation"]["activity_budget"]["id"], result["modelBudget"]["id"])
        self.assertEqual(result["modelBudget"]["reserved_calls"], 2)

    def test_single_action_object_still_uses_runtime_admission(self):
        remote, transport = self.configured(1, [{"reply": "提出一个运行器不支持的动作。",
            "actions": {"type": "unsupported", "reason": "人工协议验收"}}])
        with self.prompts():
            result = cognition.chat_turn(self.pack, "检查动作提议。", remote)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(len(result["actionResults"]), 1)
        receipt = result["actionResults"][0]["data"]
        self.assertEqual((receipt["status"], receipt["attempt_state"]), ("blocked", "not_started"))
        self.assertEqual(result["modelBudget"]["reserved_calls"], 1)

    def test_action_array_keeps_one_execution_limit(self):
        remote, transport = self.configured(1, [{"reply": "这轮只休息。",
            "actions": [{"type": "rest", "reason": "先休息"}, self.proposal("compose")]}])
        with self.prompts():
            result = cognition.chat_turn(self.pack, "按自己的状态安排。", remote)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(len(result["actionResults"]), 1)
        self.assertEqual(result["actionResults"][0]["data"]["action"], "rest")
        self.assertEqual(result["modelBudget"]["reserved_calls"], 1)

    def test_memory_lookup_uses_the_same_slots_as_subsequent_creation(self):
        remote, transport = self.configured(2, [{"memory_search": {"query": "整理资料"}}, self.response()])
        with self.prompts():
            result = cognition.chat_turn(self.pack, "先回忆这次帮助，再考虑创作。", remote)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(result["actionResults"][0]["data"]["attempt_state"], "not_started")
        self.assertEqual(result["modelBudget"]["reserved_calls"], 2)

    def test_budget_stop_does_not_suspend_the_next_independent_activity(self):
        remote, transport = self.configured(1, [self.response(), {"reply": "继续聊。"}])
        with self.prompts():
            first = cognition.chat_turn(self.pack, "先考虑初稿。", remote)
            second = cognition.chat_turn(self.pack, "下一轮先聊天。", remote)
        self.assertEqual(transport.call_count, 2)
        self.assertNotEqual(first["modelBudget"]["id"], second["modelBudget"]["id"])
        self.assertEqual(second["modelBudget"]["reserved_calls"], 1)

    def test_quiet_initiative_does_not_reset_budget_before_its_action(self):
        remote, transport = self.configured(1, [{"reply": "", "actions": [self.proposal("compose")]}])
        with self.prompts():
            result = cognition.maybe_initiate(self.pack, remote, force=True)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["actionResults"][0]["data"]["attempt_state"], "not_started")

    def test_diary_and_inner_generation_share_allowance_but_next_page_is_fresh(self):
        diary = {"diary": "整理了已有记录。", "mood": "安静", "memories": [], "inner_activity": "dream"}
        remote, transport = self.configured(1, [diary, diary])
        with self.prompts():
            result = cognition.run_days(self.pack, 2, remote)
        self.assertEqual(transport.call_count, 2)
        self.assertNotEqual(result["days"][0]["modelBudget"]["id"], result["days"][1]["modelBudget"]["id"])
        for row in result["days"]:
            self.assertEqual(row["innerResult"]["reason"], "model_budget")
            self.assertEqual(row["innerResult"]["receipt"]["data"]["attempt_state"], "not_started")

    def test_last_minute_budget_refusal_is_not_a_failed_practice(self):
        with patch("seedbank.actions._perform", side_effect=model_budget.Exhausted(model_budget.BLOCKED)):
            receipt = actions.execute(self.pack, [self.proposal("compose")], day=self.day,
                source=self.source, brain=self.brain, memories=[self.memory])[0]
        self.assertEqual(receipt["data"]["status"], "blocked")
        self.assertEqual(receipt["data"]["attempt_state"], "not_started")


if __name__ == "__main__":
    unittest.main()
