"""User-run birthday/calendar initiative regressions; artificial packs only."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_goal_provenance as goal_fixtures
from seedbank import agency, body, brain, clock, cognition, development, experience
from seedbank.desktop.session import Session
from seedbank.pack import hatch
from seedbank.util import append_memories

ROOT = Path(__file__).resolve().parents[2]
DAY = "2026-11-03"
AFTERNOON = DAY + "T16:00:00+08:00"


class QuietBrain:
    name = "calendar-fixture"

    def __init__(self):
        self.calls = []

    def chat(self, ctx):
        self.calls.append(ctx)
        return {"reply": "", "_generation": {"runner": self.name, "model": "offline-fixture", "fallback": False}}


class Afternoon(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime.fromisoformat(AFTERNOON)
        return value if tz is None else value.astimezone(tz)


class InitiativeCalendarTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-initiative-calendar-")
        self.addCleanup(folder.cleanup)
        self.pack = Path(folder.name) / "人工种子.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "人工种子", seed_override="birth-calendar",
              born_at_override=DAY + "T09:00:00+08:00")
        self.page = self.pack / "life" / ("0001-" + DAY + ".md")
        self.brain = QuietBrain()

    def observe_clock(self):
        # Explicit times are fixture inputs only. Production scheduling keeps
        # its actual clock, default interval, quota and absence of force=True.
        clock.tick(self.pack, self.brain, now=AFTERNOON)

    def test_clock_recognized_birthday_is_open_without_rewriting_genesis(self):
        original = self.page.read_bytes()
        birth = (self.pack / "birth.json").read_bytes()
        self.assertIsNone(agency.should_initiate(self.pack, now=AFTERNOON))
        self.observe_clock()
        decision = agency.should_initiate(self.pack, now=AFTERNOON)
        self.assertEqual((decision["day"], decision["date"]), (1, DAY))
        self.assertEqual(decision["remaining"], 3)
        self.assertEqual(self.page.read_bytes(), original)
        self.assertEqual((self.pack / "birth.json").read_bytes(), birth)
        self.assertEqual(self.brain.calls, [])

    def test_normal_session_pulse_reaches_quiet_birth_day_opportunity_once(self):
        original = self.page.read_bytes()
        session = Session(self.pack)
        self.addCleanup(session.close)
        session.bridge._brain = self.brain
        with patch("seedbank.clock.now_iso", return_value=AFTERNOON), patch("seedbank.agency.datetime", Afternoon):
            first = session.pulse()
            second = session.pulse()
        self.assertIsNone(first["spoken"])
        self.assertIsNone(second["spoken"])
        self.assertEqual(len(self.brain.calls), 1)
        self.assertEqual(self.brain.calls[0]["initiative"]["day"], 1)
        self.assertEqual(agency.load_agency(self.pack)["initiated"][DAY], 1)
        self.assertEqual(self.page.read_bytes(), original)

    def test_birth_day_opportunity_can_save_sourced_goal_with_normal_provenance(self):
        self.observe_clock()
        event = experience.record(self.pack, kind="conversation", text="人工素材：纸船承载着故事。",
                                  source="life/" + self.page.name, actor="owner", day=1)
        memory = {"id": "m_birth_source", "day": 1, "at": event["recorded_at"], "kind": "conversation",
                  "text": event["text"], "importance": 0.8, "tags": [], "source": experience.source_of(event),
                  "event_ids": [event["id"]], "runner": "user"}
        append_memories(self.pack, [memory])
        brain = goal_fixtures.GoalBrain({"title": "整理纸船的故事", "next_step": "记下构想",
            "reason": "这个素材让我产生了构想", "evidence": [memory["id"]]}, quiet=True)
        result = cognition.maybe_initiate(self.pack, brain, now=AFTERNOON)
        self.assertIsNotNone(result)
        goals = list(development.current_state(self.pack)["goals"].values())
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["provenance"]["first"]["kind"], "initiative")
        self.assertIn(memory["id"], goals[0]["provenance"]["first"]["dependencies"])
        self.assertEqual(goals[0]["status"], "active")

    def test_quiet_single_action_object_is_executed_once_and_retained(self):
        # Replays the shape actually returned at the first ordinary GPT
        # opportunity. Only transport/time are fixtures; parsing and execution
        # use the normal Session path, with no service request or forced entry.
        raw = {"reply": "", "memory_writes": [], "self_edits": None,
               "actions": {"type": "rest", "reason": "目前没有待处理的计划，记录的状态是疲惫。我选择先休息，不为了留下记录而安排活动。"}}
        transport = Mock(return_value=json.dumps(raw, ensure_ascii=False))
        session = Session(self.pack)
        self.addCleanup(session.close)
        session.bridge._brain = brain._CfgBrain({"adapter": "codex", "model": "offline-fixture",
            "codex_max_calls": 1, "input_budget": 16000}, brain.RemoteBrain("codex", transport))
        birth = (self.pack / "birth.json").read_bytes()
        with patch("seedbank.clock.now_iso", return_value=AFTERNOON), patch("seedbank.agency.datetime", Afternoon):
            session.pulse()
            session.pulse()
        self.assertEqual(transport.call_count, 1)
        outcomes = development.current_state(self.pack)["outcomes"]
        self.assertEqual(len(outcomes), 1, "A returned rest action must not silently become an empty decision")
        self.assertEqual((outcomes[0]["action"], outcomes[0]["status"]), ("rest", "succeeded"))
        self.assertEqual(outcomes[0]["proposal"]["reason"], raw["actions"]["reason"])
        self.assertEqual(outcomes[0]["proposal"]["generation"]["proposal_activity"], "initiative")
        self.assertTrue(body.state(self.pack)["resting"])
        self.assertEqual(agency.load_agency(self.pack)["initiated"][DAY], 1)
        self.assertFalse(any(e["kind"] == "conversation" and e.get("actor") == "model" for e in experience.read(self.pack)))
        self.assertEqual((self.pack / "birth.json").read_bytes(), birth)

    def test_real_day_and_awake_window_still_gate_opportunities(self):
        self.observe_clock()
        for when in (DAY + "T06:59:59+08:00", DAY + "T23:00:00+08:00", "2026-11-04T16:00:00+08:00"):
            with self.subTest(when=when):
                self.assertIsNone(agency.should_initiate(self.pack, now=when))
        for when in (DAY + "T07:00:00+08:00", DAY + "T22:59:59+08:00"):
            with self.subTest(when=when):
                self.assertIsNotNone(agency.should_initiate(self.pack, now=when))

    def test_default_two_hour_interval_and_three_opportunity_limit_remain(self):
        self.observe_clock()
        for hour, expected in ((16, 1), (17, 1), (18, 2), (20, 3), (22, 3)):
            cognition.maybe_initiate(self.pack, self.brain, now=DAY + f"T{hour}:00:00+08:00")
            self.assertEqual(len(self.brain.calls), expected)
        self.assertEqual(agency.load_agency(self.pack)["initiated"][DAY], 3)

    def test_real_diary_or_paused_page_does_not_reopen_as_genesis(self):
        self.observe_clock()
        original = self.page.read_text(encoding="utf-8")
        for heading in ("## 当日日记", "## 记录暂停"):
            with self.subTest(heading=heading):
                self.page.write_text(original + "\n\n" + heading + "\n\n人工记录。\n", encoding="utf-8")
                self.assertIsNone(agency.should_initiate(self.pack, now=AFTERNOON))

    def test_explicit_pause_controls_still_prevent_model_entry_on_birth_day(self):
        self.observe_clock()
        for target, value in (("seedbank.cognition.life_active", False),
                              ("seedbank.cognition.relationships.may_initiate", False),
                              ("seedbank.cognition.silence_active", True)):
            with self.subTest(target=target), patch(target, return_value=value):
                self.assertIsNone(cognition.maybe_initiate(self.pack, self.brain, now=AFTERNOON))
        self.assertEqual(self.brain.calls, [])
        self.assertEqual(agency.load_agency(self.pack)["initiated"], {})


if __name__ == "__main__":
    unittest.main()
