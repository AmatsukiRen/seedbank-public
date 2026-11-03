"""Explicit user-run offline checks for local avatar framing preferences."""
import os
import sys
import tempfile
import unittest
from pathlib import Path


def block_network(event, _args):
    if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
        raise RuntimeError("Avatar view regressions must stay offline")


if __name__ == "__main__":
    sys.addaudithook(block_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-avatar-regression-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory,
                          APPDATA=str(Path(directory) / "Roaming"),
                          LOCALAPPDATA=str(Path(directory) / "Local"),
                          QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", SEEDBANK_LANG="zh_CN")
        names = [
            "test_live2d_lifecycle.Live2DLifecycleTest.test_panning_redraws_a_paused_model_without_advancing_animation",
            "test_live2d_lifecycle.Live2DLifecycleTest.test_pan_preview_keeps_the_animation_timer_stopped",
            "test_live2d_lifecycle.Live2DLifecycleTest.test_invalid_view_coordinates_cannot_reach_the_native_renderer",
            "test_quick.QuickTest.test_avatar_view_persists_together_and_preserves_other_preferences",
            "test_quick.QuickTest.test_avatar_view_failed_save_does_not_change_in_memory_state",
            "test_quick.QuickTest.test_selecting_a_different_model_resets_the_view_only",
            "test_quick.QuickTest.test_all_pages_load_without_qml_errors",
        ]
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
