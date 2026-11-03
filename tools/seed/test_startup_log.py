"""User-run diagnostics regressions; no application, GUI, SDK or life pack."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from seedbank import startup_log


class StartupLogTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.executable = self.root / "seedbank.exe"
        self.patches = [
            patch.object(startup_log, "_stream", None),
            patch.object(startup_log, "_path", None),
            patch.object(sys, "excepthook", Mock()),
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(self.executable)),
            patch.object(startup_log.faulthandler, "enable"),
            patch.object(startup_log.atexit, "register"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.close_log)

    def close_log(self):
        if startup_log._stream is not None:
            startup_log._stream.close()

    def test_native_trace_uses_the_live_log_stream_and_enable_is_idempotent(self):
        filename = startup_log.enable()
        stream = startup_log._stream
        startup_log.mark("entry.main")
        self.assertEqual(startup_log.enable(), filename)
        self.assertIs(startup_log._stream, stream)
        self.assertFalse(stream.closed)
        startup_log.faulthandler.enable.assert_called_once_with(file=stream, all_threads=True)
        self.assertIn("entry.main", Path(filename).read_text(encoding="utf-8"))

    def test_error_capture_omits_exception_message_and_locals(self):
        filename = startup_log.enable()
        try:
            private_content = "PRIVATE-LIFE-CONTENT-DO-NOT-LOG"
            raise RuntimeError(private_content)
        except RuntimeError as error:
            startup_log.exception(error)
        output = Path(filename).read_text(encoding="utf-8")
        self.assertIn("exception RuntimeError", output)
        self.assertIn("in test_error_capture_omits_exception_message_and_locals", output)
        self.assertNotIn("PRIVATE-LIFE-CONTENT", output)

    def test_unwritable_executable_directory_uses_temp(self):
        fallback = self.root / "fallback"
        fallback.mkdir()
        original_open = Path.open

        def open_file(path, *args, **kwargs):
            if path.parent == self.root:
                raise PermissionError("read-only delivery")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", open_file), \
             patch.object(startup_log.tempfile, "gettempdir", return_value=str(fallback)):
            filename = startup_log.enable()
        self.assertEqual(Path(filename).parent, fallback)

    def test_unavailable_log_does_not_block_startup(self):
        with patch.object(Path, "open", side_effect=PermissionError("unavailable")):
            self.assertEqual(startup_log.enable(), "")
        startup_log.mark("ignored")
        startup_log.faulthandler.enable.assert_not_called()

    def test_previous_pack_lookup_failure_reaches_error_dialog(self):
        filename = Path(__file__).resolve().parents[2] / "packaging" / "windows_entry.py"
        spec = importlib.util.spec_from_file_location("seedbank_startup_test_entry", filename)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch.object(entry, "_remembered_hint", side_effect=ValueError("invalid hint")), \
             patch.object(entry, "_write_crash_log", return_value="fixture-error.log"), \
             patch.object(entry, "_message_box") as dialog:
            self.assertEqual(entry._run_gui(), 1)
        self.assertIn("fixture-error.log", dialog.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
