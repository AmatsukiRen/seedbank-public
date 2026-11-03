"""User-run cases: stable startup paths only; no registry writes or processes."""
import tempfile
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from seedbank import settings


class ReleaseEntryTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="seedbank-entry-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = self.root / ("seedbank-runtime-" + "a" * 32 + ".exe")
        self.launcher = self.root / "seedbank.exe"

    def test_frozen_runtime_registers_stable_entry_not_retired_binary(self):
        self.launcher.write_bytes(b"fixture only")
        with patch.object(settings.sys, "frozen", True, create=True), \
                patch.object(settings.sys, "executable", str(self.runtime)):
            self.assertEqual(settings.desktop_executable(), str(self.launcher))
            self.assertEqual(settings.autostart_command(), [str(self.launcher)])

    def test_standalone_and_missing_launcher_keep_working_executable(self):
        for executable in (self.runtime, self.root / "standalone.exe"):
            with self.subTest(executable=executable), \
                    patch.object(settings.sys, "frozen", True, create=True), \
                    patch.object(settings.sys, "executable", str(executable)):
                self.assertEqual(settings.autostart_command(), [str(executable)])

    def test_source_run_does_not_redirect_to_nearby_launcher(self):
        self.launcher.write_bytes(b"fixture only")
        with patch.object(settings.sys, "frozen", False, create=True), \
                patch.object(settings.sys, "executable", str(self.runtime)):
            self.assertEqual(settings.desktop_executable(), str(self.runtime))

    def test_recovered_protocol_streams_use_utf8_even_when_already_present(self):
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("seedbank_windows_entry_test", root / "packaging/windows_entry.py")
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        streams = [io.TextIOWrapper(io.BytesIO(), encoding="ascii") for _ in range(3)]
        for stream in streams:
            self.addCleanup(stream.close)
        with patch.object(entry, "_IS_WINDOWS", False), patch.object(entry.sys, "stdin", streams[0]), \
                patch.object(entry.sys, "stdout", streams[1]), patch.object(entry.sys, "stderr", streams[2]):
            entry._recover_stdio()
            self.assertTrue(all(stream.encoding == "utf-8" for stream in streams))
            entry.sys.stdout.write("中文 • ☔")
            entry.sys.stdout.flush()
        self.assertEqual(streams[1].buffer.getvalue().decode("utf-8"), "中文 • ☔")


if __name__ == "__main__":
    unittest.main()
