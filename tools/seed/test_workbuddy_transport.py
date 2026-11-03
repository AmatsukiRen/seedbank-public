"""User-run offline coverage. All CLI calls and account locations are fake."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from seedbank import brain, settings, model_budget, workbuddy_transport as wb
from seedbank.providers import validate_connection


def events(answer='{"reply":"人工回答"}', **changes):
    result = dict(type="result", subtype="success", is_error=False, num_turns=1,
                  result=answer, usage={"input_tokens": 120, "output_tokens": 9})
    result.update(changes)
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in (
        {"type": "system", "subtype": "init", "tools": [], "mcp_servers": []},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}}, result))


class WorkBuddyTransportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-workbuddy-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for item in (patch.object(wb, "usage_directory", return_value=self.root / "usage"),
                     patch.object(wb, "resolve_cli", return_value=[str(self.root / "codebuddy.exe")]),
                     patch.dict(os.environ, {"SEEDBANK_OFFLINE_REGRESSION": ""})):
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(wb, "run_cli")
        self.run = item.start()
        self.addCleanup(item.stop)
        self.run.return_value = subprocess.CompletedProcess([], 0, events(), "private diagnostic")

    def call(self):
        return wb.transport({"model": "artificial-model"}, "SeedBank system 人工", "用户输入")

    def test_text_reply_uses_isolated_workdir_and_counts_usage_without_prompt(self):
        def respond(command, user, directory):
            self.assertEqual(Path(command[command.index("--system-prompt-file") + 1]).read_text(encoding="utf-8"), "SeedBank system 人工")
            self.assertEqual(user, "用户输入")
            self.assertNotIn("用户输入", str(command))
            self.assertTrue(Path(directory).name.startswith("seedbank-workbuddy-"))
            config = json.loads(Path(command[command.index("--settings") + 1]).read_text())
            self.assertTrue(config["disableAllHooks"])
            self.assertFalse(config["memory"]["autoMemoryEnabled"])
            return subprocess.CompletedProcess(command, 0, events(), "private diagnostic")
        self.run.side_effect = respond
        reply = self.call()
        self.assertEqual(json.loads(reply)["reply"], "人工回答")
        self.run.assert_called_once()
        command = self.run.call_args.args[0]
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(command[command.index("--max-turns") + 1], "1")
        self.assertEqual(command[command.index("--model") + 1], "artificial-model")
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertNotIn("--continue", command)
        record = next((self.root / "usage").glob("*.json")).read_text(encoding="utf-8")
        self.assertNotIn("用户输入", record)
        self.assertNotIn("人工回答", record)
        self.assertEqual(wb.usage_summary()["input_tokens"], 120)

    def test_missing_model_stops_before_process_or_receipt(self):
        for value in ("", "  ", "--bad-option", "two words"):
            with self.subTest(model=value), self.assertRaises(brain.BrainConfigError):
                wb.transport({"model": value}, "system", "input")
        self.run.assert_not_called()
        self.assertFalse((self.root / "usage").exists())

    def test_timeout_records_unknown_usage_and_does_not_retry(self):
        self.run.side_effect = subprocess.TimeoutExpired("fake", 120)
        with self.assertRaises(brain.BrainConfigError):
            self.call()
        self.run.assert_called_once()
        self.assertEqual(wb.usage_summary()["unknown"], 1)

    def test_nonzero_exit_keeps_usage_without_exposing_stderr(self):
        self.run.return_value.returncode = 1
        with self.assertRaises(brain.BrainConfigError) as caught:
            self.call()
        self.assertNotIn("private diagnostic", str(caught.exception))
        self.assertEqual(wb.usage_summary()["failed"], 1)
        self.assertEqual(wb.usage_summary()["output_tokens"], 9)

    def test_incomplete_duplicate_and_malformed_streams_are_not_success(self):
        for data in ("", "not-json", "null", events() + "\n" + events()):
            with self.subTest(data=data):
                _, usage, failure = wb.parse_events(data)
                self.assertTrue(failure)
                self.assertIsNone(usage)

    def test_tools_enabled_or_executed_and_extra_turns_are_rejected(self):
        cases = [events().replace('"tools": []', '"tools": ["Bash"]'),
                 events().replace('"type": "text"', '"type": "tool_use"'),
                 events(num_turns=2), events(is_error=True), events(subtype="error_max_turns"),
                 events(answer=""), events() + '\n{"type":"user","message":{"content":[]}}']
        for data in cases:
            with self.subTest(data=data):
                self.assertTrue(wb.parse_events(data)[2])

    def test_unknown_usage_is_not_zero_and_oversized_output_fails(self):
        self.assertIsNone(wb.parse_events(events(usage=None))[1])
        self.assertEqual(wb.parse_events("x" * (wb.MAX_OUTPUT + 1))[2], "oversized_output")

    def test_offline_guard_blocks_subprocess(self):
        with patch.dict(os.environ, {"SEEDBANK_OFFLINE_REGRESSION": "1"}):
            with self.assertRaises(brain.BrainConfigError):
                self.call()
        self.run.assert_not_called()

    def test_environment_excludes_keys_injection_and_remote_overrides(self):
        with patch.dict(os.environ, {"CODEBUDDY_AUTH_TOKEN": "secret", "CODEBUDDY_API_KEY": "secret",
                                    "CODEBUDDY_BASE_URL": "https://wrong.invalid", "NODE_OPTIONS": "--require evil",
                                    "CODEBUDDY_PLUGIN_DIRS": "evil", "CODEBUDDY_CONFIG_DIR": str(self.root)}):
            env = wb.cli_environment()
        for name in ("CODEBUDDY_AUTH_TOKEN", "CODEBUDDY_API_KEY", "CODEBUDDY_BASE_URL", "NODE_OPTIONS", "CODEBUDDY_PLUGIN_DIRS"):
            self.assertNotIn(name, env)
        self.assertEqual(env["CODEBUDDY_CONFIG_DIR"], str(self.root))
        self.assertEqual(env["CODEBUDDY_CODE_DISABLE_BACKGROUND_TASKS"], "1")

    def test_receipt_write_failure_prevents_dispatch(self):
        with patch.object(wb, "write_receipt", side_effect=OSError("disk")):
            with self.assertRaises(brain.BrainConfigError):
                self.call()
        self.run.assert_not_called()


class WorkBuddyBrainTest(unittest.TestCase):
    def setUp(self):
        item = patch.object(brain, "fit_context", side_effect=lambda ctx, builder:
                            ({"system": "runtime", "user": "input"}, ctx, {}))
        item.start()
        self.addCleanup(item.stop)

    def test_recall_limit_is_shared_with_other_calls_in_same_activity(self):
        transport = Mock(return_value=wb.Reply('{"memory_search":{"query":"旧事"}}', None, "one"))
        remote = brain.RemoteBrain("workbuddy", transport)
        ctx = {"_cfg": {"model": "artificial-model", "workbuddy_max_calls": 1}}
        with model_budget.scope():
            result = remote.chat(ctx)
            self.assertEqual(result["_generation"]["runtime_guard"], "model_call_limit")
            self.assertEqual(result["memory_writes"], [])
            with self.assertRaises(model_budget.Exhausted):
                remote.compose(ctx)
        transport.assert_called_once()

    def test_failure_stops_automatic_calls_until_manual_success(self):
        transport = Mock(side_effect=[brain.BrainConfigError("failed"), '{"reply":"人工回复"}', '{"reply":""}'])
        remote = brain.RemoteBrain("workbuddy", transport)
        with self.assertRaises(brain.BrainConfigError):
            remote.chat({"initiative": {"day": 1}})
        with self.assertRaises(brain.BrainConfigError):
            remote.chat({"initiative": {"day": 1}})
        self.assertEqual(transport.call_count, 1)
        remote.chat({})
        remote.chat({"initiative": {"day": 1}})
        self.assertEqual(transport.call_count, 3)

    def test_invalid_model_reply_never_becomes_stub_speech(self):
        transport = Mock(return_value="not JSON")
        with self.assertRaises(brain.BrainConfigError):
            brain.RemoteBrain("workbuddy", transport).chat({})
        transport.assert_called_once()

    def test_settings_require_model_and_do_not_discover_a_desktop_default(self):
        preset = next(p for p in settings.PRESETS if p["adapter"] == "workbuddy")
        self.assertEqual(preset["model"], "")
        self.assertEqual(brain._requested_model({}, "workbuddy"), "")
        with self.assertRaises(ValueError):
            validate_connection(preset)
        for limit in (0, 4, "bad"):
            with self.assertRaises(ValueError):
                settings._clean_brain_patch({"workbuddy_max_calls": limit})

    def test_connection_check_requires_structured_reply(self):
        with patch.object(settings, "_merged_brain_config", return_value={"adapter": "workbuddy", "model": "fake"}), \
                patch.object(settings, "workbuddy_transport", return_value='{"message":"好"}') as transport:
            self.assertTrue(settings.test_brain("unused")[0])
            transport.assert_called_once()
            transport.return_value = '{"reply":"different protocol"}'
            self.assertFalse(settings.test_brain("unused")[0])


class WorkBuddyProcessTest(unittest.TestCase):
    def test_process_deadline_stops_only_its_own_child(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(wb.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(wb.time, "monotonic", side_effect=[0, wb.TIMEOUT + 1]), \
                patch("seedbank.plugins._stop_process") as stop:
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(subprocess.TimeoutExpired):
                wb.run_cli(["unused-fake-cli"], "人工", directory)
        stop.assert_called_once_with(process)
        self.assertNotIn("shell", spawn.call_args.kwargs)

    def test_completed_process_output_is_bounded_and_returned_as_utf8(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        def spawn(_command, **kwargs):
            self.assertEqual(kwargs["stdin"].read().decode("utf-8"), "人工输入")
            kwargs["stdout"].write("人工回复".encode("utf-8"))
            kwargs["stdout"].flush()
            return process
        with patch.object(wb.subprocess, "Popen", side_effect=spawn), tempfile.TemporaryDirectory() as directory:
            result = wb.run_cli(["unused-fake-cli"], "人工输入", directory)
        self.assertEqual(result.stdout, "人工回复")

    @unittest.skipUnless(os.name == "nt", "Windows npm launcher")
    def test_npm_launcher_uses_declared_node_entry_without_cmd_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shim = root / "codebuddy.cmd"
            shim.write_text("must never execute this wrapper")
            package = root / "node_modules/@tencent-ai/codebuddy-code"
            package.mkdir(parents=True)
            (package / "cli.js").write_text("not executed")
            manifest = package / "package.json"
            manifest.write_text(json.dumps({"name": "@tencent-ai/codebuddy-code", "bin": {"codebuddy": "cli.js"}}))
            with patch.dict(os.environ, {"SEEDBANK_WORKBUDDY_CLI": str(shim)}), \
                    patch.object(wb.shutil, "which", return_value=str(root / "node.exe")):
                command = wb.resolve_cli()
                self.assertEqual(command, [str(root / "node.exe"), str(package / "cli.js")])
                manifest.write_text(json.dumps({"name": "@tencent-ai/codebuddy-code", "bin": {"codebuddy": "../../outside.js"}}))
                with self.assertRaises(brain.BrainConfigError):
                    wb.resolve_cli()


if __name__ == "__main__":
    unittest.main()
