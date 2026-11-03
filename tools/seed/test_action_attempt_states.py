"""User-run attempt-state regressions. Authored only; all archives are fixtures."""
import json
import unittest
from unittest.mock import patch

import test_action_outcomes as fixtures
from seedbank import actions, agency, backup, cognition, development, experience, learning, plan_links
from seedbank.durability import RecoveryRequired
from seedbank.memory_state import MemoryPolicy
from seedbank.util import SeedError, append_memories


class ActionAttemptStatesTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp
    proposal = fixtures.ActionOutcomesTest.proposal
    execute = fixtures.ActionOutcomesTest.execute
    contents = fixtures.ActionOutcomesTest.contents

    def call(self, proposal):
        return actions.execute(self.pack, [proposal], day=self.day, source=self.source, brain=self.brain,
            memories=[self.memory], evidence=[{"id": self.input["id"], "source": experience.source_of(self.input), "kind": "conversation"}])[0]

    def test_invalid_proposals_do_not_dispatch_or_increase_attempts(self):
        proposals = [
            {**self.proposal("compose"), "reason": "", "attempt_state": "started"},
            {**self.proposal("compose"), "goal_id": "g_missing"},
            {**self.proposal("compose"), "kind": "unsupported"},
            self.proposal("unsupported"),
            {**self.proposal("reflect"), "memory_ids": []},
            {**self.proposal("reflect"), "memory_ids": ["m_missing"]},
            {**self.proposal("reflect"), "text": ""},
        ]
        before = self.contents()
        with patch.object(self.brain, "compose", side_effect=AssertionError("No model invocation")), \
                patch("seedbank.actions.write_file_atomic", side_effect=AssertionError("No reflection write")), \
                patch("seedbank.actions.body.spend", side_effect=AssertionError("No spending")):
            for proposal in proposals:
                with self.subTest(proposal=proposal):
                    data = self.call(proposal)["data"]
                    self.assertEqual(data["status"], "blocked")
                    self.assertEqual(data["attempt_state"], "not_started")
        self.assertEqual(self.contents(), before)
        self.assertEqual(development.current_state(self.pack)["skills"], {})

    def test_low_energy_does_not_start_practice(self):
        before = self.contents()
        with patch("seedbank.actions.body.state", return_value={"energy": 0.01}), \
                patch.object(self.brain, "compose", side_effect=AssertionError("No model invocation")):
            receipt = self.execute("compose")
        self.assertEqual(receipt["data"]["status"], "blocked")
        self.assertEqual(receipt["data"]["attempt_state"], "not_started")
        self.assertEqual(development.current_state(self.pack)["skills"], {})
        self.assertEqual(self.contents(), before)

    def test_daily_quota_rejection_is_not_a_fifth_attempt(self):
        for _ in range(4):
            self.assertEqual(self.execute("compose")["data"]["status"], "succeeded")
        before = self.contents()
        with patch.object(self.brain, "compose", side_effect=AssertionError("No fifth invocation")):
            receipt = self.execute("compose")
        self.assertEqual(receipt["data"]["attempt_state"], "not_started")
        self.assertEqual(development.current_state(self.pack)["skills"]["compose"],
            {"attempts": 4, "completed": 4, "unknown_attempts": 0})
        self.assertEqual(self.contents(), before)

    def test_preparation_storage_errors_are_not_failed_practice_receipts(self):
        before = self.contents()
        for error in (OSError("fixture storage"), SeedError("fixture archive"), RecoveryRequired("fixture recovery")):
            with self.subTest(error=type(error).__name__), \
                    patch("seedbank.deliberation.blocked_reason", side_effect=error):
                with self.assertRaises(type(error)):
                    self.execute("compose")
            self.assertEqual(development.load_development(self.pack)["outcomes"], [])
            self.assertEqual(self.contents(), before)

    def test_dispatched_failure_is_recorded_once_without_partial_work(self):
        before = self.contents()
        with patch.object(self.brain, "compose", side_effect=OSError("fixture provider unavailable")) as compose:
            data = self.execute("compose")["data"]
        compose.assert_called_once()
        self.assertEqual((data["status"], data["attempt_state"]), ("failed", "started"))
        self.assertEqual(development.current_state(self.pack)["skills"]["compose"],
            {"attempts": 1, "completed": 0, "unknown_attempts": 0})
        self.assertEqual(self.contents(), before)

    def test_post_write_failure_rolls_back_success_before_failed_receipt(self):
        before = self.contents()
        original = development.record_outcome

        def fail(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs["status"] == "succeeded":
                raise OSError("fixture after success receipt")
            return result

        with patch("seedbank.development.record_outcome", side_effect=fail):
            data = self.execute("reflect")["data"]
        self.assertEqual((data["status"], data["attempt_state"]), ("failed", "started"))
        self.assertEqual(self.contents(), before)
        self.assertEqual(list(self.pack.glob("art/reflections/*.md")), [])
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def legacy_failure(self):
        reference = plan_links.capture(self.pack, self.day["dayNo"], execution="automatic")
        row = development.record_outcome(self.pack, action="compose", status="failed", detail="旧记录只写了失败",
            day=self.day["dayNo"], source=experience.source_of(self.input), goal_id=self.goal,
            evidence=[{"id": self.input["id"], "source": experience.source_of(self.input)}], plan_reference=reference)
        events = development.events(self.pack)
        next(event for event in events if event["id"] == row["id"])["data"].pop("attempt_state")
        development._path(self.pack).write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")
        return row["id"]

    def test_old_failure_stays_unknown_without_rewriting_the_archive(self):
        identifier = self.legacy_failure()
        before = development._path(self.pack).read_bytes()
        state = development.summary(self.pack)
        self.assertEqual(state["skills"]["compose"], {"attempts": 0, "completed": 0, "unknown_attempts": 1})
        self.assertEqual(state["outcomes"][-1]["status"], "failed")
        self.assertNotIn("attempt_state", state["outcomes"][-1])
        self.assertIn("未记录是否开始执行", development.prompt_lines(state))
        selected = next(row for row in state["plan_review"] if row["plan_id"] == agency.current_plan(self.pack, self.day["dayNo"])["plan_id"])
        self.assertEqual(selected["outcomes"][-1]["attempt_state"], "unknown")
        listing = learning.listing(self.pack, self.goal)
        self.assertEqual(next(row for row in listing["attempts"] if row["id"] == identifier)["attempt_state"], "unknown")
        self.assertEqual(development._path(self.pack).read_bytes(), before)

    def test_scheduler_uses_known_visible_attempts_instead_of_old_unknown_failures(self):
        second = development.apply_proposals(self.pack, {"goals": [{"title": "另一个写作目标", "next_step": "写一个例子",
            "reason": "另一种尝试", "evidence": ["current"]}]}, day=self.day["dayNo"], source=self.source, runner="fixture",
            current_evidence=[{"id": self.input["id"], "source": experience.source_of(self.input)}])[0]["data"]["id"]
        self.legacy_failure()
        self.assertEqual(development.choose_plan(self.pack, self.day["dayNo"])["goal_id"], self.goal)
        event = experience.record(self.pack, kind="thought", text="独立的执行结果依据", day=self.day["dayNo"],
            source="art/fixture-attempt.txt", actor="runtime")
        development.record_outcome(self.pack, action="compose", status="failed", attempt_state="started", detail="尝试失败",
            day=self.day["dayNo"], source=experience.source_of(event), goal_id=self.goal,
            evidence=[{"id": event["id"], "source": experience.source_of(event)}])
        self.assertEqual(development.choose_plan(self.pack, self.day["dayNo"])["goal_id"], second)
        append_memories(self.pack, [{"id": "m_attempt_basis", "day": self.day["dayNo"], "kind": "thought",
            "text": event["text"], "source": experience.source_of(event), "event_ids": [event["id"]]}])
        cognition.forget_memory(self.pack, "m_attempt_basis")
        self.assertEqual(development.choose_plan(self.pack, self.day["dayNo"])["goal_id"], self.goal)
        self.assertEqual(development.current_state(self.pack)["skills"]["compose"]["unknown_attempts"], 1)

    def test_inconsistent_attempt_state_is_rejected_and_corrupt_file_is_preserved(self):
        before = development._path(self.pack).read_bytes()
        for status, state in (("succeeded", "not_started"), ("blocked", "started"), ("failed", "not_started")):
            with self.subTest(status=status), self.assertRaises(SeedError):
                development.record_outcome(self.pack, action="compose", status=status, attempt_state=state,
                    detail="invalid fixture", day=self.day["dayNo"], source=self.source)
        self.assertEqual(development._path(self.pack).read_bytes(), before)
        self.execute("compose")
        rows = development.events(self.pack)
        rows[-1]["data"]["attempt_state"] = "not_started"
        development._path(self.pack).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        bad = development._path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            development.load_development(self.pack)
        self.assertEqual(development._path(self.pack).read_bytes(), bad)

    def test_statistics_keep_dependencies_older_than_the_displayed_receipts(self):
        sources, receipts = [], []
        for index in range(12):
            event = experience.record(self.pack, kind="thought", text="执行依据 " + str(index), day=self.day["dayNo"],
                source="art/aggregate-" + str(index) + ".txt", actor="runtime")
            sources.append(event)
            receipts.append(development.record_outcome(self.pack, action="compose", status="failed", attempt_state="started",
                detail="fixture dispatched failure", day=self.day["dayNo"], source=experience.source_of(event),
                evidence=[{"id": event["id"], "source": experience.source_of(event)}]))
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertNotIn(receipts[0]["id"], {row["id"] for row in ctx["development"]["outcomes"]})
        self.assertEqual(ctx["development"]["skills"]["compose"]["attempts"], 12)
        self.assertIn(sources[0]["id"], cognition._context_dependencies(ctx))
        derived = experience.record(self.pack, kind="thought", text="依赖这些统计的后续解释", day=self.day["dayNo"],
            source="art/aggregate-summary.txt", actor="model", depends_on=cognition._context_dependencies(ctx))
        append_memories(self.pack, [{"id": "m_aggregate_old", "day": self.day["dayNo"], "kind": "thought",
            "text": sources[0]["text"], "source": experience.source_of(sources[0]), "event_ids": [sources[0]["id"]]}])
        cognition.forget_memory(self.pack, "m_aggregate_old")
        self.assertEqual(development.current_state(self.pack)["skills"]["compose"]["attempts"], 11)
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))

    def test_invalid_direct_work_kind_is_rejected_before_model_call(self):
        before = self.contents()
        with patch.object(self.brain, "compose", side_effect=AssertionError("No model invocation")), self.assertRaises(SeedError):
            cognition.compose_work(self.pack, "unsupported", self.brain, day=self.day)
        self.assertEqual(self.contents(), before)

    def test_replay_and_backup_preserve_one_started_failure(self):
        class FailedBrain:
            name = "stub-attempt-state-fixture"

            def chat(inner, ctx):
                return {"reply": "我准备试试。", "actions": [self.proposal("compose")]}

            def compose(inner, ctx):
                raise SeedError("fixture no result")

        brain = FailedBrain()
        result = cognition.chat_turn(self.pack, "试试写一封信。", brain, request_id="attempt-state-replay")
        replay = cognition.chat_turn(self.pack, "试试写一封信。", brain, request_id="attempt-state-replay")
        self.assertTrue(replay["replayed"])
        self.assertEqual(result["actionResults"][0]["data"]["attempt_state"], "started")
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertEqual(development.current_state(restored)["skills"], development.current_state(self.pack)["skills"])


if __name__ == "__main__":
    unittest.main()
