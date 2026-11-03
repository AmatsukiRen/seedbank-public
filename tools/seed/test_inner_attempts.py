"""User-run inner-generation failure regressions; authored, not executed."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_inner_sources as fixtures
from seedbank import backup, cognition, development, experience, inner
from seedbank.brain import BrainConfigError
from seedbank.context_window import ContextBudgetError
from seedbank.durability import RecoveryRequired
from seedbank.util import read_memories


GENERATION = {"runner": "inner-attempt-fixture", "model": "test-only"}


class InnerAttemptsTest(unittest.TestCase):
    setUp = fixtures.InnerSourcesTest.setUp
    event = fixtures.InnerSourcesTest.event
    memory = fixtures.InnerSourcesTest.memory
    narrate = fixtures.InnerSourcesTest.narrate
    context = fixtures.InnerSourcesTest.context

    def brain(self, result=None, *, error=None, name="inner-attempt-fixture"):
        return SimpleNamespace(name=name, dream=Mock(return_value=result, side_effect=error),
                               narrative=Mock(return_value=result, side_effect=error))

    def call(self, brain, *, activity="narrative", ctx=None):
        return cognition.perform_inner(self.pack, self.context() if ctx is None else ctx, brain, self.day, activity)

    def record_files(self):
        paths = [inner.inner_path(self.pack), experience.path(self.pack), self.pack / "mind" / "development.jsonl",
                 self.pack / "mind" / "memories.jsonl", self.pack / "journal" / "loop.jsonl"]
        return {str(path.relative_to(self.pack)): path.read_bytes() if path.exists() else None for path in paths}

    def test_fallback_does_not_replace_current_or_create_dream_memory(self):
        self.narrate("原本有效的自我描述。")
        before = inner.inner_path(self.pack).read_bytes()
        memories = read_memories(self.pack)
        for activity in ("dream", "narrative"):
            with self.subTest(activity=activity):
                result = self.call(self.brain({"text": "不应保存的模板", "dream": "不应保存的模板",
                    "_generation": {**GENERATION, "fallback": True}}), activity=activity)
                self.assertFalse(result["succeeded"])
                self.assertEqual(result["reason"], "fallback")
                self.assertEqual(result["receipt"]["data"]["attempt_state"], "started")
                self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)
        self.assertEqual(read_memories(self.pack), memories)
        self.assertNotIn("不应保存的模板", json.dumps(experience.read(self.pack), ensure_ascii=False))

    def test_invalid_and_unverified_outputs_have_receipts_without_inner_writes(self):
        self.narrate("保留的叙述。")
        before = inner.inner_path(self.pack).read_bytes()
        cases = [(None, "invalid_output"), ([], "invalid_output"), ({"text": "x", "_generation": []}, "invalid_output"),
                 ({"text": ["x"], "_generation": GENERATION}, "invalid_output"),
                 ({"text": "  ", "_generation": GENERATION}, "empty_output"),
                 ({"text": "x"}, "unverified_generation"),
                 ({"text": "x", "_generation": {**GENERATION, "model": 123}}, "unverified_generation"),
                 ({"text": "x", "_generation": {**GENERATION, "runtime_guard": "limit"}}, "runtime_guard")]
        for response, reason in cases:
            with self.subTest(reason=reason, response=response):
                result = self.call(self.brain(response))
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["receipt"]["data"]["status"], "failed")
                self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)

    def test_offline_and_unsupported_do_not_dispatch(self):
        offline = self.brain(error=AssertionError("Must not invoke offline template"), name="stub-test")
        result = self.call(offline)
        self.assertEqual(result["reason"], "offline")
        self.assertEqual(result["receipt"]["data"]["attempt_state"], "not_started")
        offline.narrative.assert_not_called()
        result = self.call(SimpleNamespace(name="unsupported-fixture"))
        self.assertEqual(result["reason"], "unsupported")
        self.assertEqual(result["receipt"]["data"]["status"], "blocked")
        self.assertFalse(inner.inner_path(self.pack).exists())

    def test_success_preserves_old_version_and_receipt_references_saved_event(self):
        old = self.narrate("以前的认识。")
        result = self.call(self.brain({"text": "新的有来源的认识。", "_generation": GENERATION}))
        self.assertTrue(result["succeeded"])
        data = inner.load_inner(self.pack)
        self.assertEqual(data["narrative"]["event_id"], result["event_id"])
        self.assertEqual(data["narrative_history"][0]["event_id"], old["event_id"])
        receipt = result["receipt"]["data"]
        self.assertEqual(receipt["evidence"][0]["id"], result["event_id"])
        self.assertEqual(receipt["generation"]["runner"], "runtime")
        self.assertEqual(receipt["generation"]["producer"]["model"], "test-only")
        self.assertEqual(development.current_state(self.pack)["skills"], {})

    def test_exception_rolls_back_adapter_local_writes_before_failure_receipt(self):
        self.narrate("原叙述。")
        before = inner.inner_path(self.pack).read_bytes()
        def broken(ctx):
            inner.set_narrative(self.pack, "适配器写到一半的内容。", day=1)
            raise RuntimeError("fixture-provider-private-diagnostic")
        brain = self.brain(error=broken)
        result = self.call(brain)
        self.assertEqual(result["reason"], "adapter_error")
        self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)
        archived = json.dumps(experience.read(self.pack), ensure_ascii=False)
        self.assertNotIn("适配器写到一半", archived)
        self.assertNotIn("fixture-provider-private-diagnostic", archived)

    def test_invalid_return_rolls_back_adapter_local_writes_too(self):
        self.narrate("原叙述。")
        before = inner.inner_path(self.pack).read_bytes()
        def broken(ctx):
            inner.set_narrative(self.pack, "无效结果前的意外写入。", day=1)
            return {"text": "", "_generation": GENERATION}
        result = self.call(self.brain(error=broken))
        self.assertEqual(result["reason"], "empty_output")
        self.assertEqual(inner.inner_path(self.pack).read_bytes(), before)

    def test_configuration_and_budget_are_not_started(self):
        for error, reason in ((BrainConfigError("private-key-hint"), "configuration"),
                              (ContextBudgetError("over budget"), "context_budget")):
            with self.subTest(reason=reason):
                result = self.call(self.brain(error=error))
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["receipt"]["data"]["attempt_state"], "not_started")
        self.assertNotIn("private-key-hint", json.dumps(experience.read(self.pack)))

    def test_receipt_storage_failure_rolls_back_generated_entry_and_propagates(self):
        self.narrate("原叙述。")
        ctx = self.context()
        before = self.record_files()
        with patch("seedbank.cognition.development.record_outcome", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                self.call(self.brain({"text": "新叙述。", "_generation": GENERATION}), ctx=ctx)
        self.assertEqual(self.record_files(), before)

    def test_recovery_failure_is_not_swallowed_or_recorded_as_model_failure(self):
        before = self.record_files()
        with self.assertRaises(RecoveryRequired):
            self.call(self.brain(error=RecoveryRequired("fixture recovery pending")))
        self.assertEqual(self.record_files(), before)

    def test_fitted_failure_receipt_does_not_depend_on_trimmed_context(self):
        source = self.event()
        ctx = {"evidence": [source], "inner": {"narrative": {"text": "old", "event_id": source["id"]}}}
        before = deepcopy(ctx)
        result = self.call(self.brain({"text": "template", "_generation": {**GENERATION, "fallback": True},
            "_used_evidence": [], "_used_inner": {}, "_used_transcript": []}), ctx=ctx)
        generation = result["receipt"]["data"]["generation"]
        self.assertEqual(generation["context_scope"], "supplied_to_adapter")
        self.assertNotIn(source["id"], generation["context_dependencies"])
        self.assertEqual(ctx, before)

    def test_failed_response_does_not_archive_arbitrary_metadata_or_content(self):
        result = self.call(self.brain({"text": "private-fallback-body", "_generation": {
            **GENERATION, "fallback": True, "provider_body": "private-provider-body", "api_key": "fixture-secret"}}))
        self.assertEqual(result["reason"], "fallback")
        archived = json.dumps(self.record_files(), default=lambda value: value.decode("utf-8"))
        for hidden in ("private-fallback-body", "private-provider-body", "fixture-secret"):
            self.assertNotIn(hidden, archived)

    def test_new_explicit_attempt_can_succeed_without_automatic_retry(self):
        brain = self.brain({"text": "template", "_generation": {**GENERATION, "fallback": True}})
        failed = self.call(brain)
        brain.narrative.assert_called_once()
        brain.narrative.return_value = {"text": "随后明确再试的叙述。", "_generation": GENERATION}
        succeeded = self.call(brain)
        self.assertTrue(succeeded["succeeded"])
        self.assertNotEqual(failed["receipt"]["id"], succeeded["receipt"]["id"])
        self.assertEqual(len(inner.load_inner(self.pack)["narrative_history"]), 0)

    def test_daily_model_choice_keeps_diary_and_reports_inner_failure(self):
        brain = self.brain({"text": "template", "_generation": {**GENERATION, "fallback": True}})
        brain.diary = Mock(return_value={"diary": "今天留下了实际记录。", "memories": [],
            "inner_activity": "narrate", "_generation": dict(GENERATION)})
        result = cognition.run_days(self.pack, 1, brain=brain)
        self.assertEqual(result["days"][0]["innerResult"]["reason"], "fallback")
        self.assertTrue(any(row["kind"] == "diary" for row in experience.read(self.pack)))
        self.assertFalse(inner.inner_path(self.pack).exists())
        brain.narrative.assert_called_once()

    def test_fallback_diary_cannot_choose_further_inner_generation(self):
        brain = self.brain(error=AssertionError("No inner dispatch from fallback diary"))
        brain.diary = Mock(return_value={"diary": "离线占位记录。", "memories": [],
            "inner_activity": "narrate", "_generation": {**GENERATION, "fallback": True}})
        result = cognition.run_days(self.pack, 1, brain=brain)
        self.assertIsNone(result["days"][0]["innerResult"])
        brain.narrative.assert_not_called()
        for invalid in ({"type": "narrate"}, ["dream"], 42):
            self.assertIsNone(cognition._maybe_inner(self.pack, {"inner_activity": invalid}, brain, self.day, "fixture"))
        brain.narrative.assert_not_called()

    def test_private_receipts_follow_source_withdrawal_and_do_not_leak_to_visitors(self):
        source = self.event()
        memory = self.memory(source)
        result = self.call(self.brain(error=RuntimeError("network")), ctx={"evidence": [source]})
        identifier = result["receipt"]["id"]
        self.assertIn(identifier, [row["id"] for row in development.summary(self.pack)["inner_attempts"]])
        visitor = cognition.build_context(self.pack, 1, self.day["date"], audience_id="qq-group:123", use_semantic=False)
        self.assertNotIn(identifier, json.dumps(visitor))
        cognition.forget_memory(self.pack, memory["id"])
        self.assertNotIn(identifier, [row["id"] for row in development.summary(self.pack)["inner_attempts"]])

    def test_backup_preserves_receipts_and_inner_slice_survives_unrelated_actions(self):
        result = self.call(self.brain(error=RuntimeError("network")), ctx={})
        for number in range(12):
            event = self.event("无关的本地操作 " + str(number))
            development.record_outcome(self.pack, action="unrelated-fixture", status="succeeded", detail="fixture",
                                       day=1, source=experience.source_of(event))
        shown = development.summary(self.pack)["inner_attempts"]
        self.assertEqual([row["id"] for row in shown], [result["receipt"]["id"]])
        saved = backup.create(self.pack)
        restored = self.pack.parent / "restored-inner-attempt.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(development.summary(restored)["inner_attempts"], shown)


if __name__ == "__main__":
    unittest.main()
