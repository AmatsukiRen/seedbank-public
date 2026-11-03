"""User-run observation checks. Artificial packs, fake models, no network."""
import os
from pathlib import Path
import sys
import tempfile
import unittest


def block_network(event, _args):
    if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
        raise RuntimeError("Observation checks must stay offline")


if __name__ == "__main__":
    sys.addaudithook(block_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-observation-checks-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory,
                          APPDATA=str(Path(directory) / "Roaming"),
                          LOCALAPPDATA=str(Path(directory) / "Local"),
                          QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", SEEDBANK_LANG="zh_CN")
        names = ["test_observing",
                 "test_quick.QuickTest.test_observation_settings_and_review_close_in_all_locales",
                 "test_quick.QuickTest.test_observation_pending_review_and_withdraw_without_model"]
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
