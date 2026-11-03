"""Explicit user-run, offline credential and settings UI checks."""
import os
import sys
import tempfile
import unittest
from pathlib import Path


def block_network(event, _args):
    if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
        raise RuntimeError("API key regressions must stay offline")


if __name__ == "__main__":
    sys.addaudithook(block_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-api-key-regression-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory,
                          APPDATA=str(Path(directory) / "Roaming"),
                          LOCALAPPDATA=str(Path(directory) / "Local"),
                          QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", SEEDBANK_LANG="zh_CN")
        names = ["test_api_credentials",
                 "test_quick.QuickTest.test_api_key_is_masked_and_saved_outside_life_pack",
                 "test_quick.QuickTest.test_api_key_draft_clears_when_provider_changes",
                 "test_quick.QuickTest.test_codex_settings_draft_fields_and_usage_do_not_contact_model",
                 "test_quick.QuickTest.test_all_pages_load_without_qml_errors"]
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
