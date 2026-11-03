"""User-run offline cases. All plugin source and state are artificial and temporary."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

from seedbank.plugins import PluginManager, PROTOCOL, _stop_process
from seedbank.plugin_worker import main as worker_main


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="seedbank-plugin-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.manifest = {"id": "sample.notes", "name": "Notes", "version": "0.0.1",
                         "author": "Artificial", "description": "Offline fixture",
                         "protocol": PROTOCOL, "entry": "main.py", "access": [],
                         "settings": [{"key": "prefix", "label": "Prefix", "default": "Note"}]}
        self.write_manifest()
        self.entry = self.source / "main.py"
        self.entry.write_text("def handle(request):\n    return {'text': request['settings']['prefix'] + ': ' + request['input']}\n", encoding="utf-8")
        self.manager = PluginManager(self.base / "managed")

    def write_manifest(self):
        (self.source / "plugin.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def install(self, enabled=False):
        identifier = self.manager.install(self.source)
        if enabled:
            self.manager.enable(identifier, True)
        return identifier

    def test_import_never_executes_and_starts_disabled(self):
        self.entry.write_text("raise RuntimeError('must not execute on install')", encoding="utf-8")
        with mock.patch("seedbank.plugins.subprocess.Popen") as spawn:
            identifier = self.install()
            row = self.manager.list()[0]
            self.assertFalse(row["enabled"])
            self.assertEqual(row["id"], identifier)
            with self.assertRaisesRegex(ValueError, "启用"):
                self.manager.run(identifier, "input")
            spawn.assert_not_called()

    def test_import_uses_copy_and_preserves_original(self):
        original = self.entry.read_bytes()
        identifier = self.install()
        folder = Path(self.manager.list()[0]["folder"])
        self.assertNotEqual(folder, self.source)
        self.entry.write_text("changed original", encoding="utf-8")
        self.assertEqual((folder / "main.py").read_bytes(), original)
        self.assertEqual(self.manager.list()[0]["error"], "")
        self.manager.remove(identifier)
        self.assertTrue(folder.is_dir())
        self.assertEqual(self.manager.list(), [])

    def test_entry_cannot_escape_bundle(self):
        (self.base / "outside.py").write_text("pass", encoding="utf-8")
        self.manifest["entry"] = "../outside.py"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "目录内"):
            self.install()

    def test_unknown_protocol_and_duplicate_fields_rejected(self):
        self.manifest["protocol"] = "other@2"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.install()
        self.manifest["protocol"] = PROTOCOL
        self.manifest["settings"] *= 2
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "重复"):
            self.install()

    def test_managed_file_changes_require_reimport(self):
        identifier = self.install(enabled=True)
        folder = Path(self.manager.list()[0]["folder"])
        (folder / "main.py").write_text("changed", encoding="utf-8")
        self.assertIn("改变", self.manager.list()[0]["error"])
        with self.assertRaisesRegex(ValueError, "改变"):
            self.manager.run(identifier, "input")
        self.install()
        self.assertFalse(self.manager.list()[0]["enabled"])

    def test_config_and_enable_persist_but_no_automatic_run(self):
        identifier = self.install(enabled=True)
        self.manager.configure(identifier, {"prefix": "Saved"})
        with mock.patch("seedbank.plugins.subprocess.Popen") as spawn:
            reopened = PluginManager(self.manager.root)
            row = reopened.list()[0]
            self.assertTrue(row["enabled"])
            self.assertEqual(row["config"], {"prefix": "Saved"})
            spawn.assert_not_called()

    def test_config_rejects_unknown_or_non_text_fields(self):
        identifier = self.install()
        for values in ({"unknown": "x"}, {"prefix": 5}, {"prefix": "x" * 1001}):
            with self.subTest(values_type=type(values[ next(iter(values)) ])):
                with self.assertRaises(ValueError):
                    self.manager.configure(identifier, values)
        self.assertEqual(self.manager.list()[0]["config"], {"prefix": "Note"})

    def test_worker_only_receives_manual_fields_and_no_inherited_key(self):
        identifier = self.install(enabled=True)
        captured = {}
        class Finished:
            returncode = 0
            def poll(self):
                return 0
        def spawn(command, **options):
            captured.update(options)
            request = json.load(options["stdin"])
            self.assertEqual(set(request), {"protocol", "input", "settings"})
            self.assertEqual(request["input"], "artificial input")
            options["stdout"].write(json.dumps({"protocol": PROTOCOL, "text": "done"}).encode())
            options["stdout"].flush()
            return Finished()
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "artificial-secret", "BOT_TOKEN": "artificial-secret"}), \
                mock.patch("seedbank.plugins.subprocess.Popen", side_effect=spawn):
            self.assertEqual(self.manager.run(identifier, "artificial input"), "done")
        self.assertNotIn("OPENAI_API_KEY", captured["env"])
        self.assertNotIn("BOT_TOKEN", captured["env"])
        self.assertNotEqual(Path(captured["cwd"]), self.source)

    def test_pre_cancel_does_not_start_worker(self):
        identifier = self.install(enabled=True)
        cancelled = threading.Event()
        cancelled.set()
        with mock.patch("seedbank.plugins.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "停止"):
                self.manager.run(identifier, "text", cancel=cancelled)
            spawn.assert_not_called()
        self.assertEqual(self.manager._running, "")

    def test_timeout_terminates_worker_and_releases_manager(self):
        identifier = self.install(enabled=True)
        process = mock.Mock()
        process.poll.side_effect = lambda: 0 if process.kill.called else None
        with mock.patch("seedbank.plugins.subprocess.Popen", return_value=process), \
                mock.patch("seedbank.plugins.time.monotonic", side_effect=[0, 1]):
            with self.assertRaisesRegex(ValueError, "30 秒"):
                self.manager.run(identifier, "text", timeout=0.1)
        process.kill.assert_called_once()
        process.wait.assert_called_once()
        self.assertEqual(self.manager._running, "")

    def test_bad_protocol_output_not_accepted_as_success(self):
        identifier = self.install(enabled=True)
        def spawn(command, **options):
            options["stdout"].write(b'{"text":"wrong protocol"}')
            options["stdout"].flush()
            return mock.Mock(returncode=0, poll=mock.Mock(return_value=0))
        with mock.patch("seedbank.plugins.subprocess.Popen", side_effect=spawn):
            with self.assertRaisesRegex(ValueError, "格式"):
                self.manager.run(identifier, "input")

    @unittest.skipUnless(os.name == "nt", "Windows bootloader process tree")
    def test_windows_cancel_targets_only_worker_tree(self):
        process = mock.Mock(pid=123456)
        process.poll.return_value = None
        with mock.patch("seedbank.plugins.subprocess.run") as taskkill:
            _stop_process(process)
        self.assertEqual(taskkill.call_args.args[0][1:], ["/PID", "123456", "/T", "/F"])
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_large_plugin_is_rejected_before_copy(self):
        with mock.patch("seedbank.plugins.MAX_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "过大"):
                self.install()
        self.assertFalse(self.manager.registry.exists())

    def test_corrupt_registry_is_not_overwritten(self):
        self.manager.root.mkdir()
        self.manager.registry.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(self.manager.registry.read_text(encoding="utf-8"), "{broken")

    def test_worker_does_not_mix_prints_into_response(self):
        self.entry.write_text("print('diagnostic')\ndef handle(request):\n    return {'text': '<b>literal</b>'}\n", encoding="utf-8")
        request = {"protocol": PROTOCOL, "input": "sample", "settings": {}}
        incoming = io.TextIOWrapper(io.BytesIO(json.dumps(request).encode()), encoding="utf-8")
        outgoing, diagnostic = io.StringIO(), io.StringIO()
        self.addCleanup(incoming.close)
        with mock.patch.object(sys, "stdin", incoming), mock.patch.object(sys, "stdout", outgoing), \
                mock.patch.object(sys, "stderr", diagnostic), mock.patch.object(sys, "path", list(sys.path)):
            result = worker_main([str(self.entry)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(outgoing.getvalue()), {"protocol": PROTOCOL, "text": "<b>literal</b>"})
        self.assertIn("diagnostic", diagnostic.getvalue())

    def test_actual_one_shot_subprocess_uses_artificial_bundle(self):
        identifier = self.install(enabled=True)
        self.manager.configure(identifier, {"prefix": "人工"})
        self.assertEqual(self.manager.run(identifier, "你好"), "人工: 你好")
        self.assertIsNone(self.manager._process)

    def test_worker_response_survives_a_windowed_ascii_stream(self):
        self.entry.write_text("def handle(request):\n    return {'text': '中文 • ☔'}\n", encoding="utf-8")
        incoming = io.TextIOWrapper(io.BytesIO(json.dumps({"protocol": PROTOCOL}).encode()), encoding="utf-8")
        outgoing = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        self.addCleanup(incoming.close)
        self.addCleanup(outgoing.close)
        with mock.patch.object(sys, "stdin", incoming), mock.patch.object(sys, "stdout", outgoing), \
                mock.patch.object(sys, "stderr", io.StringIO()), mock.patch.object(sys, "path", list(sys.path)):
            code = worker_main([str(self.entry)])
        self.assertEqual(code, 0)
        outgoing.flush()
        self.assertEqual(json.loads(outgoing.buffer.getvalue())["text"], "中文 • ☔")


if __name__ == "__main__":
    unittest.main()
