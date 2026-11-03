"""Calendar versus page deadline regressions for user execution. Not run."""
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import test_learning as fixtures
from seedbank import backup, clock, deadlines, experience, hands, learning, relationships, requests
from seedbank.brain import _hands_lines, _memorial_lines, create_stub_brain
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import chat_turn, read_transcript
from seedbank.pack import check
from seedbank.util import SeedError, list_days, read_json, write_json_atomic


class CalendarDeadlinesTest(unittest.TestCase):
    plan = fixtures.LearningTest.plan

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-calendar-home-")
        self.addCleanup(folder.cleanup)
        environment = patch.dict(os.environ, {"HOME": folder.name, "USERPROFILE": folder.name, "SEEDBANK_LANG": "zh_CN"})
        environment.start()
        self.addCleanup(environment.stop)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No real service"))
        guard.start()
        self.addCleanup(guard.stop)
        fixtures.LearningTest.setUp(self)
        self.base = date.fromisoformat(self.day["date"])

    def on(self, days):
        return (self.base + timedelta(days=days)).isoformat()

    def advance(self, days, *, deliver=True):
        clock.save_clock(self.pack, {"last_seen_date": self.on(0)})
        now = datetime.fromisoformat(self.on(days) + "T12:00:00").astimezone().isoformat()
        with patch("seedbank.clock._resolve_brain", side_effect=AssertionError("No invented diaries")):
            if deliver:
                return clock.tick(self.pack, now=now)
            with patch("seedbank.cognition._speak_due_reminders"):
                return clock.tick(self.pack, now=now)

    def schedule(self, **changes):
        return hands.schedule(self.pack, {"text": "记得浇花", "due_on": self.on(2), **changes})["reminder"]

    def agreement(self, goal, **changes):
        return relationships.perform(self.pack, "agreement", {"person_id": "owner", "reason": "记录明确约定",
            "goal_id": goal, "criteria_id": learning.listing(self.pack, goal)["criteria"]["id"], **changes})["record"]

    def test_dates_handle_month_year_and_leap_boundaries_without_page_conversion(self):
        self.assertEqual(deadlines.calendar_date("2028-02-29"), "2028-02-29")
        self.assertEqual(deadlines.state({"due_on": "2026-12-31"}, 2, "2027-01-01")["state"], "overdue")
        for value in ("2027-02-29", "2026-13-01", "2026-1-01", "明天", True, 20261104, "2026-11-04T12:00:00"):
            with self.subTest(value=value), self.assertRaises(SeedError):
                deadlines.calendar_date(value)

    def test_offline_gap_makes_date_due_while_legacy_page_stays_in_future(self):
        calendar = self.schedule()
        legacy = hands.add_reminder(self.pack, "旧日页事项", self.day["dayNo"] + 2, created_day=self.day["dayNo"])
        result = self.advance(10, deliver=False)
        self.assertEqual(result["day"], self.day["dayNo"] + 1)
        self.assertEqual([r["id"] for r in hands.due_reminders(self.pack, result["day"])], [calendar["id"]])
        self.assertEqual([r["id"] for r in hands.overdue_reminders(self.pack, result["day"])], [calendar["id"]])
        self.assertEqual(hands.sweep_missed(self.pack, result["day"]), [])
        self.assertEqual(hands.find_reminder(self.pack, calendar["id"])["status"], "pending")
        self.assertEqual(hands.find_reminder(self.pack, legacy["id"])["due_day"], legacy["due_day"])
        text = _hands_lines({"hands": hands.hands_summary(self.pack, result["day"])})
        self.assertIn("不假装准时送达", text)
        self.assertIn("旧日页", text)
        self.assertEqual(read_json(self.pack / "mind/memorial.json", {}).get("regrets", []), [])

    def test_clock_records_late_reminder_once_without_claiming_external_delivery(self):
        reminder = self.schedule()
        before = list_days(self.pack)
        result = self.advance(10)
        row = hands.find_reminder(self.pack, reminder["id"])
        self.assertEqual(row["status"], "said")
        self.assertEqual(row["said_on"], self.on(10))
        self.assertEqual(row["said_via"], "local_transcript")
        transcript = read_transcript(self.pack, result["day"])
        self.assertEqual(sum("记得浇花" in r["text"] for r in transcript), 1)
        self.assertTrue(any(self.on(2) in r["text"] and "补上" in r["text"] for r in transcript))
        event = next(r for r in experience.read(self.pack) if r["metadata"].get("reminder_id") == reminder["id"])
        self.assertEqual(event["metadata"]["runner"], "runtime")
        self.assertEqual(event["metadata"]["delivery_scope"], "local_transcript")
        clock.tick(self.pack, now=datetime.fromisoformat(self.on(10) + "T13:00:00").astimezone().isoformat())
        self.assertEqual(read_transcript(self.pack, result["day"]), transcript)
        self.assertEqual(len(list_days(self.pack)), len(before) + 1)
        check(self.pack)

    def test_local_record_and_status_roll_back_together_before_retry(self):
        reminder = self.schedule()
        pages = list_days(self.pack)
        with patch("seedbank.cognition.mark_said", side_effect=SeedError("fixture interrupted status write")), self.assertRaises(SeedError):
            self.advance(10)
        self.assertEqual(list_days(self.pack), pages)
        self.assertEqual(hands.find_reminder(self.pack, reminder["id"])["status"], "pending")
        self.assertEqual(clock.load_clock(self.pack)["last_seen_date"], self.on(0))
        self.assertFalse(any(r["metadata"].get("reminder_id") == reminder["id"] for r in experience.read(self.pack)))
        result = self.advance(10)
        self.assertEqual(sum("记得浇花" in r["text"] for r in read_transcript(self.pack, result["day"])), 1)

    def test_quoting_reminder_text_does_not_complete_calendar_reminder(self):
        reminder = self.schedule(due_on=self.on(0))
        brain = create_stub_brain()
        with patch.object(brain, "chat", return_value={"reply": "你刚才提到记得浇花，我不能据此确认这条提醒已经发出。"}):
            chat_turn(self.pack, "这条提醒已经发出了吗？", brain)
        self.assertEqual(hands.find_reminder(self.pack, reminder["id"])["status"], "pending")

    def test_missing_page_date_does_not_guess_calendar_status(self):
        self.schedule()
        unknown_day = self.day["dayNo"] + 99
        self.assertEqual(hands.due_reminders(self.pack, unknown_day), [])
        self.assertEqual(hands.hands_summary(self.pack, unknown_day)["pending"][0]["deadline"]["state"], "unknown")

    def test_invalid_past_and_conflicting_dates_do_not_create_pending_inputs(self):
        for value in (self.on(-1), "2026-02-30", "tomorrow", ""):
            with self.subTest(value=value), self.assertRaises(SeedError):
                hands.schedule(self.pack, {"text": "提醒", "due_on": value})
        with self.assertRaises(SeedError):
            hands.add_reminder(self.pack, "两种期限", 3, due_on=self.on(2), created_day=self.day["dayNo"])
        self.assertEqual(requests.pending(self.pack), [])
        self.assertFalse(hands.hands_path(self.pack).exists())

    def test_legacy_and_calendar_fields_survive_subsequent_writes_and_backup(self):
        legacy = hands.add_reminder(self.pack, "旧事项", self.day["dayNo"] + 2, created_day=self.day["dayNo"])
        calendar = self.schedule()
        hands.add_reminder(self.pack, "另一旧事项", self.day["dayNo"] + 3, created_day=self.day["dayNo"])
        self.assertEqual(hands.load_hands(self.pack)["format"], hands.CALENDAR_FORMAT)
        self.assertEqual(hands.find_reminder(self.pack, legacy["id"]), legacy)
        self.assertEqual(hands.find_reminder(self.pack, calendar["id"]), calendar)
        saved = backup.create(self.pack)
        restored = self.pack.parent / "calendar-restored.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(hands.hands_path(restored).read_bytes(), hands.hands_path(self.pack).read_bytes())
        check(restored)

    def test_bad_calendar_state_is_rejected_without_overwriting_file(self):
        self.schedule()
        raw = hands.load_hands(self.pack)
        raw["reminders"][0]["status"] = "missed"
        write_json_atomic(hands.hands_path(self.pack), raw)
        before = hands.hands_path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            hands.load_hands(self.pack)
        with self.assertRaises(SeedError):
            check(self.pack)
        self.assertEqual(hands.hands_path(self.pack).read_bytes(), before)

    def test_incomplete_calendar_records_cannot_be_silently_dropped_on_next_write(self):
        reminder = self.schedule()
        raw = hands.load_hands(self.pack)
        for changes in ({"text": ""}, {"text": "过长" * 121}, {"created_day": True}, {"due_on": None},
                        {"id": ""}, {"said_day": 2}, {"status": "said", "said_on": self.on(1), "said_via": "manual"}):
            with self.subTest(changes=changes):
                raw["reminders"] = [{**reminder, **changes}]
                write_json_atomic(hands.hands_path(self.pack), raw)
                before = hands.hands_path(self.pack).read_bytes()
                with self.assertRaises(SeedError):
                    hands.add_reminder(self.pack, "后续写入", 10, created_day=self.day["dayNo"])
                self.assertEqual(hands.hands_path(self.pack).read_bytes(), before)

    def test_model_date_action_accepts_only_one_valid_deadline(self):
        results = hands.apply_actions(self.pack, self.day["dayNo"], "fixture", [
            {"type": "remind", "text": "日期事项", "due_on": self.on(2)},
            {"type": "remind", "text": "冲突", "due_on": self.on(2), "due_day": 3},
            {"type": "remind", "text": "坏日期", "due_on": "2026-02-30"}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["due_on"], self.on(2))

    def test_calendar_agreement_after_gap_needs_review_not_automatic_blame(self):
        goal = self.plan()
        modern = self.agreement(goal, due_on=self.on(2))
        legacy = self.agreement(goal, due_day=self.day["dayNo"] + 2)
        self.assertEqual(modern["format"], "seedbank/relationships@2")
        result = self.advance(10)
        assessment = relationships.assessment(self.pack, modern, day=result["day"])
        self.assertEqual(assessment["state"], "due_for_review")
        self.assertFalse(assessment["verified"])
        self.assertEqual(relationships.assessment(self.pack, legacy, day=result["day"])["state"], "pending")
        self.assertEqual(relationships.view(self.pack)["visible"][modern["key"]]["data"]["status"], "pending")
        before = relationships.path(self.pack).read_bytes()
        updated = relationships.perform(self.pack, "review", {"person_id": "owner", "target": modern["key"],
            "expected": modern["id"], "reason": "双方需要重新协商", "status": "withdrawn"})["record"]
        self.assertEqual(updated["data"]["due_on"], self.on(2))
        self.assertEqual(updated["format"], "seedbank/relationships@2")
        self.assertTrue(relationships.path(self.pack).read_bytes().startswith(before))

    def test_invalid_agreement_dates_and_mixed_deadlines_are_rejected(self):
        goal = self.plan()
        for values in ({"due_on": self.on(-1)}, {"due_on": "2026-02-30"}, {"due_on": self.on(2), "due_day": 3}):
            with self.subTest(values=values), self.assertRaises(SeedError):
                self.agreement(goal, **values)
        row = self.agreement(goal, due_on=None)
        self.assertEqual(relationships.assessment(self.pack, row, day=self.day["dayNo"])["deadline"]["state"], "unscheduled")

    def test_retry_after_failed_write_and_expired_input_cancellation(self):
        data = {"text": "保存中断", "due_on": self.on(2)}
        with patch("seedbank.hands.save_hands", side_effect=OSError("fixture")), self.assertRaises(OSError):
            hands.schedule(self.pack, data, request_id="calendar-retry")
        self.assertEqual(requests.get(self.pack, "calendar-retry")["status"], "pending")
        self.advance(10)
        with self.assertRaises(SeedError):
            hands.schedule(self.pack, data, request_id="calendar-retry")
        result = Bridge(self.pack, "stub").handle({"op": "reminder", "action": "cancel_pending", "request_id": "calendar-retry"})
        self.assertTrue(result["ok"], result)
        self.assertTrue(hands.schedule(self.pack, data, request_id="calendar-retry")["cancelled"])
        self.assertTrue(hands.cancel_pending(self.pack, "calendar-retry")["cancelled"])
        self.assertEqual(hands.list_reminders(self.pack), [])
        self.assertEqual(requests.pending(self.pack), [])

    def test_backup_pending_request_requires_explicit_resume_and_preserves_idempotency(self):
        data = {"text": "恢复输入", "due_on": self.on(2)}
        with patch("seedbank.hands.save_hands", side_effect=OSError("fixture")), self.assertRaises(OSError):
            hands.schedule(self.pack, data, request_id="calendar-restore")
        saved = backup.create(self.pack)
        restored = self.pack.parent / "pending-restored.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(hands.list_reminders(restored), [])
        result = Bridge(restored, "stub").handle({"op": "resume", "request_id": "calendar-restore"})
        self.assertTrue(result["ok"], result)
        self.assertTrue(hands.schedule(restored, data, request_id="calendar-restore")["replayed"])
        self.assertEqual(len(hands.list_reminders(restored)), 1)
        with self.assertRaises(SeedError):
            hands.cancel_pending(restored, "calendar-restore")
        with self.assertRaises(SeedError):
            hands.schedule(restored, {**data, "text": "不同内容"}, request_id="calendar-restore")

    def test_cli_calendar_flags_and_manual_recording(self):
        output = StringIO()
        with redirect_stdout(output), patch("seedbank.cli.clock_tick", return_value={}):
            self.assertEqual(main(["remind", str(self.pack), "CLI日期", "--due-on", self.on(2), "--request-id", "cli-calendar"]), 0)
        row = json.loads(output.getvalue())["reminder"]
        saved = hands.mark_said(self.pack, row["id"], self.day["dayNo"])
        self.assertEqual(saved["said_via"], "manual")
        self.assertEqual(saved["said_on"], self.on(0))
        self.assertEqual(hands.mark_said(self.pack, row["id"], self.day["dayNo"]), saved)

    def test_old_absence_counts_do_not_claim_observed_sleep(self):
        text = _memorial_lines({"memorial": {"missing_days": 10}})
        self.assertIn("无法据此确定", text)
        self.assertNotIn("睡过去", text)


if __name__ == "__main__":
    unittest.main()
