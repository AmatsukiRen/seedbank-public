"""User-run offline coverage for Codex transport; every subprocess is mocked."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import brain, codex_transport as codex, settings


class CodexTransportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-codex-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for item in (patch.object(codex, "usage_directory", return_value=self.root / "usage"),
                     patch.object(codex, "resolve_cli", return_value=str(self.root / "codex.exe")),
                     patch.dict(os.environ, {"SEEDBANK_OFFLINE_REGRESSION": ""})):
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(codex.subprocess, "run")
        self.run = item.start()
        self.addCleanup(item.stop)
        self.run.side_effect = self.respond
        self.usage = {"input_tokens": 120, "cached_input_tokens": 80, "output_tokens": 9}
        self.events = [{"type": "turn.started"}, {"type": "turn.completed", "usage": self.usage}]
        self.failure = None
        self.exit_code = 0

    def respond(self, command, **kwargs):
        if "login" in command:
            return subprocess.CompletedProcess(command, 0, "", "Logged in using ChatGPT")
        if self.failure:
            raise self.failure
        Path(command[command.index("-o") + 1]).write_text('{"reply":"你好"}', encoding="utf-8")
        return subprocess.CompletedProcess(command, self.exit_code,
                                           "\n".join(json.dumps(e) for e in self.events), "secret must not leak")

    def test_success_preserves_unicode_and_records_usage_without_prompt(self):
        reply = codex.transport({}, "runtime", "人工样本：小杉")
        self.assertEqual(self.run.call_args_list[0].args[0][1:], ["login", "status"])
        self.assertEqual(json.loads(reply)["reply"], "你好")
        self.assertEqual(reply.usage, self.usage)
        command = self.run.call_args.args[0]
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("read-only", command)
        self.assertEqual(command[command.index("-m") + 1], "gpt-6-astra")
        self.assertEqual(self.run.call_args.kwargs["input"], "runtime\n\n人工样本：小杉")
        receipts = list((self.root / "usage").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        self.assertNotIn("小杉", receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(codex.usage_summary()["input_tokens"], 120)

    def test_timeout_is_unknown_and_never_retried(self):
        self.failure = subprocess.TimeoutExpired("codex", 120)
        with self.assertRaises(brain.BrainConfigError):
            codex.transport({}, "runtime", "input")
        self.assertEqual(self.run.call_count, 2)  # Local login status + one request.
        self.assertEqual(codex.usage_summary()["unknown"], 1)

    def test_usage_is_independent_of_life_pack_rollback(self):
        with patch("seedbank.durability.before_write", side_effect=AssertionError("must not join life transaction")):
            codex.transport({}, "runtime", "input")
        self.assertEqual(codex.usage_summary()["calls"], 1)

    def test_nonzero_exit_retains_usage_and_hides_raw_stderr(self):
        self.exit_code = 1
        with self.assertRaises(brain.BrainConfigError) as caught:
            codex.transport({}, "runtime", "input")
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(codex.usage_summary()["failed"], 1)
        self.assertEqual(codex.usage_summary()["output_tokens"], 9)

    def test_api_key_login_does_not_launch_model(self):
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 0, "Logged in using an API key", "")
        with self.assertRaises(brain.BrainConfigError):
            codex.transport({}, "runtime", "input")
        self.assertEqual(self.run.call_count, 1)
        self.assertEqual(codex.usage_summary()["calls"], 0)

    def test_offline_guard_blocks_even_subprocess_network(self):
        with patch.dict(os.environ, {"SEEDBANK_OFFLINE_REGRESSION": "1"}):
            with self.assertRaises(brain.BrainConfigError):
                codex.transport({}, "runtime", "input")
        self.run.assert_not_called()

    def test_tool_events_are_rejected_even_with_successful_exit(self):
        self.events.insert(1, {"type": "item.started", "item": {"type": "command_execution"}})
        with self.assertRaises(brain.BrainConfigError):
            codex.transport({}, "runtime", "input")
        self.assertEqual(codex.usage_summary()["failed"], 1)

    def test_known_pre_turn_warning_is_not_a_tool_or_failure(self):
        self.events.insert(0, {"type": "item.completed", "item": {"type": "error", "message":
            "Under-development features enabled: skip_host_skill_discovery. Experimental."}})
        self.assertTrue(codex.transport({}, "runtime", "input"))

    def test_incomplete_or_invalid_events_cannot_be_success(self):
        for events in ([], [{"type": "turn.failed"}], [None],
                       [{"type": "turn.completed"}, {"type": "turn.completed"}]):
            with self.subTest(events=events):
                self.events = events
                with self.assertRaises(brain.BrainConfigError):
                    codex.transport({}, "runtime", "input")

    def test_missing_usage_and_corrupt_receipts_are_visible(self):
        self.events = [{"type": "turn.completed"}]
        codex.transport({}, "runtime", "input")
        (self.root / "usage" / "broken.json").write_text("broken", encoding="utf-8")
        self.assertEqual(codex.usage_summary()["unknown"], 1)
        self.assertEqual(codex.usage_summary()["unreadable"], 1)

    def test_multiple_completions_do_not_report_only_the_last_usage(self):
        self.events.append({"type": "turn.completed", "usage": self.usage})
        with self.assertRaises(brain.BrainConfigError):
            codex.transport({}, "runtime", "input")
        self.assertEqual(codex.usage_summary()["unknown"], 1)
        self.assertEqual(codex.usage_summary()["input_tokens"], 0)

    def test_api_credentials_and_remote_overrides_are_not_inherited(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret",
                                    "OPENAI_BASE_URL": "https://invalid", "CODEX_HOME": str(self.root)}):
            env = codex.cli_environment()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("OPENAI_BASE_URL", env)
        self.assertEqual(env["CODEX_HOME"], str(self.root))


class CodexBrainTest(unittest.TestCase):
    def setUp(self):
        item = patch.object(brain, "fit_context", side_effect=lambda ctx, builder:
                            ({"system": "runtime", "user": "input"}, ctx, {}))
        item.start()
        self.addCleanup(item.stop)

    def test_limit_stops_followup_with_truthful_runtime_response(self):
        transport = Mock(return_value=codex.Reply('{"memory_search":{"query":"旧事"}}',
                                                 {"input_tokens": 100, "output_tokens": 5}, "one"))
        result = brain.RemoteBrain("codex", transport).chat({"_cfg": {"codex_max_calls": 1}})
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(result["_generation"]["runtime_guard"], "model_call_limit")
        self.assertEqual(result["_generation"]["usage"]["calls"], 1)
        self.assertEqual(result["memory_writes"], [])

    def test_recall_followup_usage_is_aggregated(self):
        from contextlib import ExitStack
        transport = Mock(side_effect=[
            codex.Reply('{"memory_search":{"query":"旧事"}}', {"input_tokens": 100, "output_tokens": 5}, "one"),
            codex.Reply('{"reply":"还没有可靠记录","memory_writes":[]}', {"input_tokens": 110, "output_tokens": 9}, "two")])
        with ExitStack() as stack:
            for target, value in (("seedbank.retrieval.search", []), ("seedbank.disclosure.policy_for", {}),
                                  ("seedbank.semantic.last_status", {}), ("seedbank.facts.context", {}),
                                  ("seedbank.life_story.context", {})):
                stack.enter_context(patch(target, return_value=value))
            result = brain.RemoteBrain("codex", transport).chat({"packDir": "unused", "_cfg": {"codex_max_calls": 2}})
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(result["_generation"]["usage"]["input_tokens"], 210)
        self.assertEqual(result["_generation"]["usage"]["output_tokens"], 14)
        self.assertEqual(result["_generation"]["model"], "gpt-6-astra")

    def test_invalid_reply_never_becomes_offline_speech(self):
        with self.assertRaises(brain.BrainConfigError):
            brain.RemoteBrain("codex", Mock(return_value="not JSON")).chat({})

    def test_failed_auto_activity_waits_for_successful_manual_reply(self):
        transport = Mock(side_effect=[brain.BrainConfigError("offline"), '{"reply":"你好"}', '{"reply":""}'])
        remote = brain.RemoteBrain("codex", transport)
        with self.assertRaises(brain.BrainConfigError):
            remote.chat({"initiative": {"day": 1}})
        for _ in range(2):
            with self.assertRaises(brain.BrainConfigError):
                remote.chat({"initiative": {"day": 1}})
        self.assertEqual(transport.call_count, 1)
        remote.chat({})
        remote.chat({"initiative": {"day": 1}})
        self.assertEqual(transport.call_count, 3)

    def test_new_adapter_is_optional_and_birth_configuration_is_unchanged(self):
        self.assertEqual(brain.default_brain_config()["adapter"], "stub")
        self.assertNotIn("codex_max_calls", brain.birth_brain_config())
        presets = [item for item in settings.PRESETS if item.get("provider") == "codex"]
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]["adapter"], "codex")
        self.assertEqual(settings._clean_brain_patch({"adapter": "codex", "codex_max_calls": "2"})["codex_max_calls"], 2)
        for value in (0, 4, "bad"):
            with self.assertRaises(ValueError):
                settings._clean_brain_patch({"codex_max_calls": value})


if __name__ == "__main__":
    unittest.main()
