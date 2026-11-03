"""User-run reply delivery tests: artificial packs and fake transport only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from seedbank import experience
from seedbank.brain import RemoteBrain, _validate_chat_result, build_chat_prompt
from seedbank.bridge import Bridge
from seedbank.cognition import build_context, start_day
from seedbank.pack import hatch
from seedbank.presentation import normalize, utterance
from seedbank.util import read_json


class PresentationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-delivery-")
        self.addCleanup(temporary.cleanup)
        self.pack = Path(temporary.name) / "人工.life"
        hatch(self.pack, Path(__file__).resolve().parents[2] / "eggs/open.egg", "人工")
        self.day = start_day(self.pack)

    def test_missing_or_malformed_cues_keep_legacy_reply_and_neutral_delivery(self):
        for cue in (None, [], "happy", {"expression": ["happy"], "gesture": {}},
                    {"expression": "think", "gesture": "../model.motion3.json"}):
            with self.subTest(cue=cue):
                result = _validate_chat_result({"reply": "引用中有开心，不代表我的语气。", "presentation": cue})
                self.assertEqual(result["reply"], "引用中有开心，不代表我的语气。")
                self.assertEqual(result["presentation"], {"expression": "neutral", "gesture": "none"})

    def test_delivery_cannot_forward_files_parameters_or_unbounded_durations(self):
        cue = {"expression": " WARM ", "gesture": "wave", "file": "elsewhere", "duration_ms": 9999999,
               "parameters": {"Costume": 1}}
        self.assertEqual(normalize(cue), {"expression": "warm", "gesture": "wave"})
        self.assertEqual(utterance("短句", cue)["duration_ms"], 3000)
        self.assertEqual(utterance("长" * 5000, cue)["duration_ms"], 12000)
        self.assertEqual(set(utterance("短句", cue)), {"expression", "gesture", "duration_ms"})

    def test_full_and_compact_prompts_request_delivery_with_the_same_reply(self):
        context = build_context(self.pack, self.day["dayNo"], self.day["date"], "你好", use_semantic=False)
        for compact in (False, True):
            user = build_chat_prompt({**context, "_compact_protocol": compact})["user"]
            self.assertIn('"presentation":{"expression":"neutral","gesture":"none"}', user)
            self.assertIn("not a mood or identity update", user)

    def test_reply_cue_survives_carrier_and_request_replay_without_another_call(self):
        cue = {"expression": "warm", "gesture": "wave"}
        transport = mock.Mock(return_value=json.dumps({"reply": "你好，很高兴见到你。", "presentation": cue}))
        carrier = Bridge(self.pack, "stub")
        carrier._brain = RemoteBrain("artificial", transport)
        birth = (self.pack / "birth.json").read_bytes()
        mood = read_json(self.pack / "mind/mood.json", {}).get("mood")
        with mock.patch.object(carrier, "_tick"):
            first = carrier.message("你好", request_id="delivery-cue")
            again = carrier.message("你好", request_id="delivery-cue")
        transport.assert_called_once()
        self.assertEqual(first["reply"], "你好，很高兴见到你。")
        self.assertEqual(first["presentation"], cue)
        self.assertEqual(again["presentation"], cue)
        self.assertTrue(again["replayed"])
        # The archive stores the display name, not the internal "fish" sentinel.
        events = [row for row in experience.read(self.pack)
                  if row["kind"] == "conversation" and row["actor"] == carrier.name and row["text"] == first["reply"]]
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["metadata"]["presentation"], cue)
        self.assertEqual(read_json(self.pack / "mind/mood.json", {}).get("mood"), mood)
        self.assertEqual((self.pack / "birth.json").read_bytes(), birth)


if __name__ == "__main__":
    unittest.main()
