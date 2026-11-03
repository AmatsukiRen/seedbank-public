"""Offline check-harness cleanup; no Qt, SDK, real pack or driver required."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from seedbank.quick.avatar_check import isolated_profile


class AvatarCheckCleanupTest(unittest.TestCase):
    def test_success_cleans_profile_and_preserves_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            report = {"ok": True}
            with isolated_profile(output, report) as profile:
                (Path(profile) / "fixture.txt").write_text("isolated fixture")
            self.assertFalse(Path(profile).exists())
            self.assertEqual(json.loads(output.read_text())['temporary_cleanup'], "removed")
            self.assertTrue(report["ok"])

    def test_body_failure_still_propagates_and_records_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            report = {"ok": False}
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                with isolated_profile(output, report):
                    raise RuntimeError("render failed")
            self.assertFalse(json.loads(output.read_text())["ok"])
            self.assertEqual(report["temporary_cleanup"], "removed")

    @unittest.skipUnless(os.name == "nt", "Windows exclusive driver-cache file")
    def test_locked_cache_retains_location_without_failing_completed_check(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = None
        profile = None
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            report = {"ok": True}
            try:
                with isolated_profile(output, report) as profile:
                    cache = Path(profile) / "driver-cache.bin"
                    handle = kernel.CreateFileW(str(cache), 0x40000000, 0, None, 2, 0x80, None)
                    self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
                self.assertTrue(report["ok"])
                self.assertEqual(report["temporary_cleanup"], "retained_locked_files")
                self.assertEqual(json.loads(output.read_text())["temporary_directory"], profile)
            finally:
                if handle not in (None, ctypes.c_void_p(-1).value):
                    kernel.CloseHandle(handle)
                if profile and Path(profile).exists():
                    target = Path(profile).resolve()
                    self.assertEqual(target.parent, Path(tempfile.gettempdir()).resolve())
                    self.assertTrue(target.name.startswith("seedbank-native-avatar-"))
                    shutil.rmtree(target)


if __name__ == "__main__":
    unittest.main()
