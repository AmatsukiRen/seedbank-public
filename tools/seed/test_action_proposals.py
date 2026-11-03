"""Offline action reasons: original proposal, execution, privacy and reopening."""
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import test_action_outcomes as fixtures
from seedbank import cognition, development, disclosure, experience
from seedbank.memory_state import MemoryPolicy


class ActionProposalTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp
    proposal = fixtures.ActionOutcomesTest.proposal
    execute = fixtures.ActionOutcomesTest.execute

    def generation(self, **extra):
        return {"runner": "proposal-fixture", "model": "proposer", "proposal_activity": "initiative",
                "context_dependencies": [self.memory["id"]], **extra}

    def test_rest_reason_survives_reopen_and_is_distinct_from_result(self):
        receipt = self.execute("rest", generation=self.generation())
        proposal = receipt["data"].get("proposal", {})
        self.assertEqual(proposal.get("reason"), "推进当前目标")
        self.assertEqual(proposal["generation"]["proposal_activity"], "initiative")
        self.assertNotEqual(proposal["reason"], receipt["data"]["detail"])
        before = (self.pack / "mind/development.jsonl").read_bytes()
        code = "import json,sys; from seedbank.development import current_state; print(json.dumps(current_state(sys.argv[1])['outcomes'][-1],ensure_ascii=False))"
        child = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(self.pack)],
                               capture_output=True, encoding="utf-8", check=True, timeout=30)
        reopened = json.loads(child.stdout)
        self.assertEqual(reopened["proposal"], proposal)
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)

    def test_composition_keeps_proposer_and_creator_separate(self):
        receipt = self.execute("compose", generation=self.generation())
        proposal = receipt["data"].get("proposal", {})
        self.assertEqual(proposal.get("reason"), "推进当前目标")
        self.assertEqual(proposal["generation"]["runner"], "proposal-fixture")
        self.assertEqual(receipt["data"]["generation"]["runner"], self.brain.name)
        self.assertEqual(proposal["source"], self.source)
        self.assertIn(self.input["id"], [ref["id"] for ref in proposal["evidence"]])
        self.assertNotEqual(receipt["source"], proposal["source"])

    def test_blocked_and_failed_attempts_keep_the_original_reason(self):
        blocked = self.execute("unsupported", generation=self.generation())
        with patch.object(self.brain, "compose", side_effect=ValueError("fixture invalid response")):
            failed = self.execute("compose", generation=self.generation())
        for receipt, status in ((blocked, "blocked"), (failed, "failed")):
            self.assertEqual(receipt["data"]["status"], status)
            self.assertEqual(receipt["data"].get("proposal", {}).get("reason"), "推进当前目标")
        self.assertEqual(blocked["data"]["attempt_state"], "not_started")
        self.assertEqual(failed["data"]["attempt_state"], "started")

    def isolated_receipt(self, *, proposal_source=None, generation=None, execution_generation=None, execution_source=None):
        from seedbank.action_proposals import capture
        proposal = capture({"reason": "REASON_SOURCE_ONLY"}, source=proposal_source or experience.source_of(self.input),
                           generation=generation or self.generation(), evidence=[])
        event = experience.record(self.pack, kind="action_attempt", text="独立的执行结果",
            source="art/independent.md", actor="runtime", day=self.day["dayNo"], metadata=execution_generation or {})
        return development.record_outcome(self.pack, action="rest", status="succeeded", detail="已休息",
            day=self.day["dayNo"], source=execution_source or experience.source_of(event),
            generation=execution_generation or {}, proposal=proposal)

    def test_reason_dependencies_hide_outcome_and_derivatives_after_forgetting(self):
        receipt = self.isolated_receipt()
        ctx = {"development": development.summary(self.pack)}
        self.assertIn("REASON_SOURCE_ONLY", development.prompt_lines(ctx["development"]))
        refs = cognition._context_dependencies(ctx)
        self.assertIn(self.memory["id"], refs)
        derived = experience.record(self.pack, kind="thought", text="由理由形成的后续解释",
            source="art/derived.md", day=self.day["dayNo"], depends_on=refs)
        before = (self.pack / "mind/development.jsonl").read_bytes()
        cognition.forget_memory(self.pack, self.memory["id"])
        summary = development.summary(self.pack)
        self.assertNotIn("REASON_SOURCE_ONLY", json.dumps(summary, ensure_ascii=False))
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)
        self.assertIn(receipt["id"], [r["id"] for r in development.load_development(self.pack)["outcomes"]])

    def test_reason_audience_and_revoked_sharing_are_enforced(self):
        audience = "qq-group:123"
        shared = disclosure.perform(self.pack, "profile", {"scope": audience, "text": "公开的人工素材",
            "reason": "人工测试分享"})["record"]
        share_source = "mind/experiences.jsonl#" + shared["event_id"]
        generation = {**disclosure.stamp(audience), "runner": "fixture", "proposal_activity": "conversation",
                      "context_dependencies": [shared["event_id"]]}
        receipt = self.isolated_receipt(proposal_source=share_source, generation=generation,
            execution_generation=disclosure.stamp(audience))
        scoped = lambda scope: development.summary(self.pack, policy=disclosure.policy_for(self.pack, scope))
        self.assertIn("REASON_SOURCE_ONLY", json.dumps(scoped(audience), ensure_ascii=False))
        self.assertNotIn("REASON_SOURCE_ONLY", json.dumps(scoped("qq-group:456"), ensure_ascii=False))
        disclosure.perform(self.pack, "revoke", {"target": shared["key"], "expected": shared["id"], "reason": "撤回人工分享"})
        self.assertNotIn("REASON_SOURCE_ONLY", json.dumps(scoped(audience), ensure_ascii=False))
        self.assertIn(receipt["id"], [r["id"] for r in development.load_development(self.pack)["outcomes"]])

    def test_prompt_budget_removes_reason_and_dependencies_together(self):
        from seedbank.context_window import fit
        self.isolated_receipt()
        ctx = {"development": development.summary(self.pack), "_cfg": {"input_budget": 2048}}
        def builder(selected):
            return {"system": "x" * 1300 + development.prompt_lines(selected["development"]), "user": "request"}
        prompt, used, budget = fit(ctx, builder)
        self.assertTrue(budget["limited"])
        self.assertNotIn("REASON_SOURCE_ONLY", prompt["system"])
        self.assertNotIn(self.memory["id"], cognition._context_dependencies(used))
        self.assertIn("REASON_SOURCE_ONLY", json.dumps(ctx, ensure_ascii=False))

    def test_normal_followup_prompt_and_saved_reply_keep_reason_sources(self):
        from seedbank.brain import RemoteBrain, _CfgBrain
        receipt = self.execute("rest", generation=self.generation())
        transport = Mock(return_value='{"reply":"当时记录的说明是推进当前目标。","memory_writes":[]}')
        remote = _CfgBrain({"adapter": "codex", "model": "offline-fixture", "input_budget": 16000,
                           "codex_max_calls": 1}, RemoteBrain("codex", transport))
        cognition.chat_turn(self.pack, "回顾刚才的行动及当时留下的说明。", remote)
        self.assertEqual(transport.call_count, 1)
        supplied = "\n".join(transport.call_args.args[1:])
        # The reason may arrive in recent development or sourced archive recall
        # after fitting; neither channel is required to duplicate the other.
        self.assertIn("推进当前目标", supplied)
        self.assertIn(receipt["id"], supplied)
        reply = next(row for row in reversed(experience.read(self.pack))
                     if row.get("metadata", {}).get("runner") == "codex")
        self.assertTrue({self.memory["id"], receipt["id"]} & set(reply["depends_on"]))
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(reply))

    def test_legacy_and_direct_work_never_acquire_an_invented_reason(self):
        from seedbank.action_proposals import display_lines
        legacy = development.record_outcome(self.pack, action="rest", status="succeeded", detail="旧执行记录",
            day=self.day["dayNo"], source=self.source)
        direct = cognition.compose_work(self.pack, "letter", self.brain)
        before = (self.pack / "mind/development.jsonl").read_bytes()
        for row in (legacy["data"], direct["receipt"]["data"]):
            self.assertNotIn("proposal", row)
            self.assertEqual(display_lines(row), ["当时未记录行动理由。"])
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)

    def test_proposal_capture_is_independent_and_labels_fixed_output(self):
        from seedbank.action_proposals import capture, display_lines
        generation = self.generation(fallback=True)
        proposal = capture({"reason": "模板里的说明"}, source=self.source, generation=generation, evidence=[])
        generation["context_dependencies"].clear()
        self.assertIn(self.memory["id"], proposal["generation"]["context_dependencies"])
        self.assertIn("固定或回退响应", "\n".join(display_lines({"proposal": proposal})))

    def test_reason_length_and_missing_reason_are_explicit(self):
        from seedbank.action_proposals import capture, display_lines
        long = capture({"reason": "长" * 1100}, source=self.source, generation={}, evidence=[])
        self.assertEqual(len(long["reason"]), 1000)
        self.assertTrue(long["reason_truncated"])
        self.assertIn("理由过长，此处保留前 1000 字。", display_lines({"proposal": long}))
        missing = capture({}, source=self.source, generation={}, evidence=[])
        self.assertEqual(missing["reason"], "")
        self.assertIn("本次未提供行动理由。", display_lines({"proposal": missing}))


if __name__ == "__main__":
    unittest.main()
