"""User-run regressions only: local fixtures, no services or real life packs."""
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import test_action_outcomes as fixtures
import test_learning as learning_fixtures
from seedbank import cognition, development, experience, learning, requests, works, cli
from seedbank.brain import BrainConfigError, RemoteBrain
from seedbank.bridge import Bridge
from seedbank.context_window import ContextBudgetError
from seedbank.durability import RecoveryRequired
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories, write_file_atomic


class RequestedAttemptsTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp
    contents = fixtures.ActionOutcomesTest.contents
    execute = fixtures.ActionOutcomesTest.execute
    proposal = fixtures.ActionOutcomesTest.proposal
    plan = learning_fixtures.LearningTest.plan
    practice = learning_fixtures.LearningTest.practice
    listing = learning_fixtures.LearningTest.listing
    review = learning_fixtures.LearningTest.review

    def test_direct_failure_is_runtime_evidence_without_work_or_spending(self):
        goal = self.plan()
        before = self.contents()
        with patch.object(self.brain, "compose", side_effect=RuntimeError("secret diagnostics")):
            result = self.practice(goal, identifier="failed")
        data = result["receipt"]["data"]
        self.assertFalse(result["succeeded"])
        self.assertIsNone(result["entry"])
        self.assertEqual((data["status"], data["attempt_state"], data["artifact"]), ("failed", "started", ""))
        self.assertEqual(data["generation"]["runner"], "runtime")
        self.assertEqual(data["practice"]["scope"], "available_at_execution")
        self.assertNotIn("lesson_ids", data["practice"])
        self.assertEqual(data["plan_reference"]["execution"], "requested")
        self.assertNotIn("secret diagnostics", str(result))
        for name in ("mind/body.json", "mind/works.json", "mind/memories.jsonl", "journal/loop.jsonl"):
            self.assertEqual(self.contents()[name], before[name])
        event = next(row for row in experience.read(self.pack) if row["id"] == data["evidence"][0]["id"])
        self.assertEqual((event["kind"], event["actor"]), ("action_attempt", "runtime"))
        self.assertEqual(development.current_state(self.pack)["skills"]["compose"]["completed"], 0)
        self.assertEqual(self.listing(goal)["attempts"][0]["id"], result["receipt"]["id"])
        self.assertFalse(learning.evaluate(self.pack, goal, {"c1": result["receipt"]["id"]})["passed"])
        with self.assertRaises(SeedError):
            self.review(goal, result["receipt"]["id"])

    def test_remote_fallback_template_is_not_a_successful_work(self):
        brain = RemoteBrain("openai-compatible", lambda *args: (_ for _ in ()).throw(RuntimeError("offline fixture")))
        with redirect_stderr(io.StringIO()):
            result = cognition.compose_work(self.pack, "letter", brain, day=self.day)
        self.assertFalse(result["succeeded"])
        self.assertEqual(result["receipt"]["data"]["generation"]["failure_kind"], "fallback")
        self.assertEqual(works.list_works(self.pack), [])
        self.assertFalse(any(row["kind"] == "creation" for row in experience.read(self.pack)))

    def test_invalid_empty_and_guarded_results_have_no_artifact(self):
        cases = [(None, "invalid_output"), ([], "invalid_output"), ({"text": None}, "empty_output"),
                 ({"text": 7}, "empty_output"), ({"text": "  "}, "empty_output"),
                 ({"text": "template", "_generation": {"runtime_guard": "fixture"}}, "runtime_guard"),
                 ({"text": "text", "_generation": []}, "invalid_output")]
        for response, reason in cases:
            with self.subTest(reason=reason), patch.object(self.brain, "compose", return_value=response):
                result = cognition.compose_work(self.pack, "letter", self.brain, day=self.day)
                self.assertEqual(result["receipt"]["data"]["generation"]["failure_kind"], reason)
        self.assertEqual(works.list_works(self.pack), [])

    def test_failed_adapter_partial_local_writes_are_rolled_back(self):
        def interrupted(ctx):
            write_file_atomic(self.pack / "art/interrupted.txt", "partial fixture")
            raise OSError("adapter unavailable")
        with patch.object(self.brain, "compose", side_effect=interrupted):
            result = cognition.compose_work(self.pack, "letter", self.brain, day=self.day)
        self.assertFalse(result["succeeded"])
        self.assertFalse((self.pack / "art/interrupted.txt").exists())
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def test_preparation_and_recovery_errors_stay_pending_without_failure_receipts(self):
        goal = self.plan()
        for error in (BrainConfigError("missing fixture key"), ContextBudgetError("too large"),
                      RecoveryRequired("recovery needed"), SeedError("unreadable source")):
            identifier = type(error).__name__
            with self.subTest(error=identifier), patch.object(self.brain, "compose", side_effect=error):
                with self.assertRaises(type(error)):
                    self.practice(goal, identifier=identifier)
            self.assertEqual(requests.get(self.pack, identifier)["status"], "pending")
        self.assertEqual(development.load_development(self.pack)["outcomes"], [])
        self.assertFalse(any(row["kind"] == "action_attempt" for row in experience.read(self.pack)))

    def test_remote_adapter_does_not_convert_recovery_to_template(self):
        brain = RemoteBrain("openai-compatible", lambda *args: (_ for _ in ()).throw(RecoveryRequired("fixture")))
        with self.assertRaises(RecoveryRequired):
            cognition.compose_work(self.pack, "letter", brain, day=self.day)
        self.assertEqual(development.load_development(self.pack)["outcomes"], [])

    def test_save_failure_keeps_input_pending_for_explicit_retry(self):
        goal = self.plan()
        with patch("seedbank.cognition.add_work", side_effect=OSError("disk fixture")):
            with self.assertRaises(OSError):
                self.practice(goal, identifier="storage")
        self.assertEqual(requests.get(self.pack, "storage")["status"], "pending")
        self.assertEqual(development.load_development(self.pack)["outcomes"], [])
        self.assertTrue(self.practice(goal, identifier="storage")["succeeded"])
        self.assertEqual(requests.get(self.pack, "storage")["status"], "complete")
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def test_failed_receipt_storage_is_atomic_with_event_and_request(self):
        goal = self.plan()
        before = experience.read(self.pack)
        with patch.object(self.brain, "compose", return_value={}), \
                patch("seedbank.development.record_outcome", side_effect=OSError("disk fixture")):
            with self.assertRaises(OSError):
                self.practice(goal, identifier="receipt-storage")
        self.assertEqual(experience.read(self.pack), before)
        self.assertEqual(requests.get(self.pack, "receipt-storage")["status"], "pending")
        with patch.object(self.brain, "compose", return_value={}):
            self.assertFalse(self.practice(goal, identifier="receipt-storage")["succeeded"])
        self.assertEqual(len(self.listing(goal)["attempts"]), 1)

    def test_automatic_fallback_has_one_receipt_owned_by_actions(self):
        with patch.object(self.brain, "compose", return_value={"text": "template", "_generation": {"fallback": True}}):
            receipt = self.execute("compose")
        self.assertEqual(receipt["data"]["status"], "failed")
        self.assertEqual(receipt["data"]["plan_reference"]["execution"], "automatic")
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)
        self.assertFalse(any(row["kind"] == "action_attempt" for row in experience.read(self.pack)))
        self.assertEqual(works.list_works(self.pack), [])

    def test_failure_and_derived_summary_follow_source_visibility(self):
        goal = self.plan()
        with patch.object(self.brain, "compose", return_value={}):
            result = self.practice(goal)
        receipt = result["receipt"]["data"]
        event = next(row for row in experience.read(self.pack) if row["id"] == receipt["evidence"][0]["id"])
        derived = experience.record(self.pack, kind="thought", text="fixture derived review", day=self.day["dayNo"],
            source="art/requested-review.txt", actor="model", depends_on=[event["id"]])
        append_memories(self.pack, [{"id": "m_failed_attempt", "day": self.day["dayNo"], "kind": "thought",
            "text": event["text"], "source": experience.source_of(event), "event_ids": [event["id"]]}])
        cognition.forget_memory(self.pack, "m_failed_attempt")
        self.assertEqual(self.listing(goal)["attempts"], [])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertIn(event["id"], {row["id"] for row in experience.read(self.pack)})

    def test_bridge_and_make_report_failed_attempt_without_success_text(self):
        channel = Bridge(self.pack, "stub")
        channel._brain = self.brain
        with patch.object(self.brain, "compose", return_value={}):
            result = channel.handle({"op": "work", "action": "compose", "kind": "letter"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["work"]["succeeded"])
        output = io.StringIO()
        with patch("seedbank.cli.create_brain", return_value=self.brain), \
                patch.object(self.brain, "compose", return_value={}), redirect_stdout(output):
            code = cli.main(["make", str(self.pack), "--kind", "letter"])
        self.assertEqual(code, 1)
        self.assertIn("尝试已记录", output.getvalue())
        self.assertNotIn("她写了一", output.getvalue())


if __name__ == "__main__":
    unittest.main()
