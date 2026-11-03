"""Offline regressions for the recorded status/snapshot energy discrepancy."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from seedbank.bridge import Bridge
from seedbank.cognition import build_context
from seedbank.desktop.session import Session
from seedbank.pack import hatch


class ResourceStatusTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="seedbank-resource-status-")
        self.addCleanup(self.directory.cleanup)
        self.pack = Path(self.directory.name) / "resource.life"
        root = Path(__file__).resolve().parents[2]
        hatch(self.pack, root / "eggs/open.egg", "资源状态")
        self.mood_file = self.pack / "mind/mood.json"
        self.body_file = self.pack / "mind/body.json"
        self.mood_file.write_text(json.dumps({
            "mood": "疲惫", "energy": 0.69,
            "updated_at": "2026-11-03T06:00:00+08:00",
        }, ensure_ascii=False), encoding="utf-8")
        clock = patch("seedbank.body.datetime")
        frozen = clock.start()
        self.addCleanup(clock.stop)
        frozen.now.return_value = datetime.fromisoformat("2026-11-03T07:00:00+08:00")

    def test_legacy_energy_recovers_without_changing_mood_or_persisting(self):
        original = self.mood_file.read_bytes()
        bridge = Bridge(self.pack)
        for operation in ("hello", "status", "status"):
            result = bridge.handle({"op": operation})
            self.assertTrue(result["ok"], result)
            status = result["status"] if operation == "hello" else result
            self.assertEqual(status["energy"], 0.77)
            self.assertEqual(status["mood"], "疲惫")
        self.assertEqual(self.mood_file.read_bytes(), original)
        self.assertFalse(self.body_file.exists())

    def test_body_energy_agrees_across_status_snapshot_and_context(self):
        self.body_file.write_text(json.dumps({
            "format": "seedbank/body@1", "energy": 0.5, "resting": True,
            "updated_at": "2026-11-03T06:00:00+08:00",
        }), encoding="utf-8")
        original = {path: path.read_bytes() for path in (self.mood_file, self.body_file)}
        session = Session(self.pack)
        status = session.call("status")
        snapshot = session.snapshot()
        context = build_context(self.pack, snapshot["day"], snapshot["date"], use_semantic=False)
        self.assertEqual(status["energy"], 0.58)
        self.assertEqual(snapshot["states"]["body"]["energy"], status["energy"])
        self.assertEqual(snapshot["states"]["mood"]["energy"], status["energy"])
        self.assertEqual(context["energy"], status["energy"])
        self.assertTrue(snapshot["states"]["body"]["resting"])
        self.assertEqual(status["mood"], "疲惫")
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)

