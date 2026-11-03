"""User-run cases: stable startup paths only; no registry writes or processes."""
import tempfile
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


if __name__ == "__main__":
    unittest.main()
