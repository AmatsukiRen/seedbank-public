"""Offline QQ intake, delivery and cross-channel privacy regression entry."""
import os
import argparse
import sys
import tempfile
import unittest
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compatibility-only", action="store_true")
    options = parser.parse_args()
    def block_network(event, _args):
        if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
            raise RuntimeError("Security regressions must stay offline")
    sys.addaudithook(block_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-security-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory,
            APPDATA=str(Path(directory) / "Roaming"), LOCALAPPDATA=str(Path(directory) / "Local"),
            QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", SEEDBANK_LANG="zh_CN")
        names = ["test_qq_security", "test_qq.PureTest", "test_qq.DecideTest", "test_qq.ConfigTest",
                 "test_qq.BridgeClientTest", "test_channels", "test_disclosure", "test_lifecycle",
                 "test_media_intake", "test_cross_channel_actions"]
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters/qq-onebot"))
        names = ["test_qq_onebot"] if options.compatibility_only else names + ["test_qq_onebot"]
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
