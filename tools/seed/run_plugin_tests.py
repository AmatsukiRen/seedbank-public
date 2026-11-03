"""User entry: temporary local plugins, software Qt, no model/platform calls."""
import os
from pathlib import Path
import sys
import tempfile
import unittest


def block_network(event, _args):
    if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
        raise RuntimeError("Plugin regressions must stay offline")


if __name__ == "__main__":
    sys.addaudithook(block_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-plugin-regression-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory,
                          APPDATA=str(Path(directory) / "Roaming"),
                          LOCALAPPDATA=str(Path(directory) / "Local"),
                          QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", SEEDBANK_LANG="zh_CN")
        names = ["test_plugins",
                 "test_quick.QuickTest.test_plugins_page_import_enable_and_remove_never_launches_code",
                 "test_quick.QuickTest.test_plugin_output_is_plain_text_and_uses_visible_config"]
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
