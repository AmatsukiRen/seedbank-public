"""User-run reminder revision regressions. These cases have not been executed."""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

import test_calendar_deadlines as fixtures
from seedbank import backup, experience, hands, reminder_changes as changes, requests
from seedbank.brain import _hands_lines
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import read_transcript
from seedbank.pack import check
from seedbank.util import SeedError, read_json, write_json_atomic


class ReminderChangesTest(unittest.TestCase):
    setUp = fixtures.CalendarDeadlinesTest.setUp
    on = fixtures.CalendarDeadlinesTest.on
    advance = fixtures.CalendarDeadlinesTest.advance
    schedule = fixtures.CalendarDeadlinesTest.schedule

    def payload(self, row, **extra):
        current = hands.find_reminder(self.pack, row["id"])
        return {"reminder_id": row["id"], "expected": changes.fingerprint(current),
                "reason": "安排改变，需要调整", **extra}

    def test_reschedule_preserves_original_and_only_delivers_the_revised_content(self):
        original = self.schedule()
        revised = changes.perform(self.pack, "revise", self.payload(original, text="改为检查盆土", due_on=self.on(4)))["reminder"]
        self.assertEqual(revised["id"], original["id"])
        self.assertEqual(revised["created_on"], original["created_on"])
        self.assertEqual(revised["history"][0]["before"], changes.snapshot(original))
        self.assertEqual(revised["history"][0]["after"], changes.snapshot(revised))
        self.assertEqual(hands.load_hands(self.pack)["format"], hands.REVISION_FORMAT)
        earlier = self.advance(2)
        self.assertEqual(hands.due_reminders(self.pack, earlier["day"]), [])
        self.assertFalse(any("检查盆土" in r["text"] for r in read_transcript(self.pack, earlier["day"])))
        later = self.advance(4)
        row = hands.find_reminder(self.pack, original["id"])
        self.assertEqual(row["status"], "said")
        self.assertEqual(row["said_on"], self.on(4))
        self.assertEqual(row["history"], revised["history"])
        self.assertEqual(sum("检查盆土" in r["text"] for r in read_transcript(self.pack, later["day"])), 1)
        event = next(r for r in experience.read(self.pack) if r["metadata"].get("reminder_id") == original["id"])
        self.assertEqual(event["metadata"]["reminder_revision"], 1)
        check(self.pack)

    def test_cancel_retains_history_and_cannot_be_delivered_or_resurrected_by_done(self):
        original = self.schedule()
        revised = changes.perform(self.pack, "revise", self.payload(original, text="另一件事", due_on=self.on(3)))["reminder"]
        cancelled = changes.perform(self.pack, "cancel", self.payload(revised))["reminder"]
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(len(cancelled["history"]), 2)
        self.assertEqual(cancelled["history"][0], revised["history"][0])
        self.assertEqual(cancelled["history"][1]["before"], revised["history"][0]["after"])
        result = self.advance(10)
        self.assertEqual(hands.due_reminders(self.pack, result["day"]), [])
        self.assertEqual(hands.overdue_reminders(self.pack, result["day"]), [])
        self.assertEqual(hands.hands_summary(self.pack, result["day"])["pending"], [])
        self.assertFalse(any(r["metadata"].get("reminder_id") == original["id"] for r in experience.read(self.pack)))
        with self.assertRaises(SeedError):
            hands.mark_said(self.pack, original["id"], result["day"])
        self.assertEqual(read_json(self.pack / "mind/memorial.json", {}).get("regrets", []), [])
        self.assertEqual(hands.find_reminder(self.pack, original["id"]), cancelled)

    def test_stale_edit_and_already_delivered_are_rejected_without_pending_input(self):
        row = self.schedule(due_on=self.on(0))
        stale = self.payload(row, text="晚点再提醒", due_on=self.on(2))
        hands.mark_said(self.pack, row["id"], self.day["dayNo"])
        before = hands.hands_path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            changes.perform(self.pack, "revise", stale)
        with self.assertRaises(SeedError):
            changes.perform(self.pack, "cancel", self.payload(row))
        self.assertEqual(requests.pending(self.pack), [])
        self.assertEqual(hands.hands_path(self.pack).read_bytes(), before)

    def test_completed_request_replay_does_not_revert_later_cancellation(self):
        row = self.schedule()
        data = self.payload(row, text="修订后的内容", due_on=self.on(4))
        result = changes.perform(self.pack, "revise", data, request_id="same-change")
        cancelled = changes.perform(self.pack, "cancel", self.payload(row))["reminder"]
        replay = changes.perform(self.pack, "revise", data, request_id="same-change")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["reminder"], result["reminder"])
        self.assertEqual(hands.find_reminder(self.pack, row["id"]), cancelled)
        with self.assertRaises(SeedError):
            changes.perform(self.pack, "revise", {**data, "text": "不同内容"}, request_id="same-change")

    def test_failed_completion_rolls_back_change_and_resume_appends_once(self):
        row = self.schedule()
        data = self.payload(row, text="恢复后提醒", due_on=self.on(5))
        original = hands.hands_path(self.pack).read_bytes()
        real_write = requests.write_json_atomic

        def fail_result(path, payload):
            if "completed" in path.parts:
                raise OSError("fixture interrupted receipt")
            return real_write(path, payload)

        with patch("seedbank.requests.write_json_atomic", side_effect=fail_result), self.assertRaises(OSError):
            changes.perform(self.pack, "revise", data, request_id="resume-change")
        self.assertEqual(hands.hands_path(self.pack).read_bytes(), original)
        self.assertEqual(requests.get(self.pack, "resume-change")["status"], "pending")
        result = Bridge(self.pack, "stub").handle({"op": "resume", "request_id": "resume-change"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(hands.find_reminder(self.pack, row["id"])["history"]), 1)
        self.assertTrue(changes.perform(self.pack, "revise", data, request_id="resume-change")["replayed"])

    def test_abandoning_failed_change_does_not_cancel_existing_reminder(self):
        row = self.schedule()
        data = self.payload(row)
        with patch("seedbank.hands.save_hands", side_effect=OSError("fixture")), self.assertRaises(OSError):
            changes.perform(self.pack, "cancel", data, request_id="pending-cancel")
        stopped = hands.cancel_pending(self.pack, "pending-cancel")
        self.assertTrue(stopped["cancelled"])
        self.assertTrue(changes.perform(self.pack, "cancel", data, request_id="pending-cancel")["cancelled"])
        self.assertEqual(hands.find_reminder(self.pack, row["id"]), row)

    def test_invalid_changes_and_old_fingerprint_never_overwrite_current(self):
        row = self.schedule()
        data = self.payload(row, text="保留输入", due_on=self.on(4))
        for extra in ({"reason": ""}, {"due_on": self.on(-1)}, {"due_on": "明天"},
                      {"due_on": "2027-02-29"}, {"text": "太长" * 121}, {"expected": ""}):
            with self.subTest(extra=extra), self.assertRaises(SeedError):
                changes.perform(self.pack, "revise", {**data, **extra})
        self.assertEqual(requests.pending(self.pack), [])
        result = changes.perform(self.pack, "revise", data)["reminder"]
        with self.assertRaises(SeedError):
            changes.perform(self.pack, "revise", {**data, "text": "旧编辑框内容"})
        self.assertEqual(hands.find_reminder(self.pack, row["id"]), result)

    def test_legacy_cancel_and_explicit_calendar_conversion_keep_original_deadline(self):
        legacy = hands.add_reminder(self.pack, "旧日页提醒", self.day["dayNo"] + 2, created_day=self.day["dayNo"])
        converted = changes.perform(self.pack, "revise", self.payload(legacy, text=legacy["text"], due_on=self.on(3)))["reminder"]
        self.assertIsNone(converted["due_day"])
        self.assertEqual(converted["history"][0]["before"]["due_day"], legacy["due_day"])
        other = hands.add_reminder(self.pack, "另一个旧提醒", self.day["dayNo"] + 4, created_day=self.day["dayNo"])
        cancelled = changes.perform(self.pack, "cancel", self.payload(other))["reminder"]
        self.assertEqual(cancelled["due_day"], other["due_day"])
        self.assertNotIn("due_on", cancelled)
        self.assertEqual(hands.load_hands(self.pack)["format"], hands.REVISION_FORMAT)
        check(self.pack)

    def test_broken_history_or_malformed_legacy_row_blocks_write_without_loss(self):
        row = self.schedule()
        changes.perform(self.pack, "revise", self.payload(row, text="新内容", due_on=self.on(3)))
        good = hands.load_hands(self.pack)
        for mutation in ("before", "current", "cancelled", "version", "duplicate"):
            raw = deepcopy(good)
            target = raw["reminders"][0]
            if mutation == "before":
                target["history"][0]["before"]["status"] = "said"
            elif mutation == "current":
                target["text"] = "未记录的变化"
            elif mutation == "cancelled":
                target["status"] = "cancelled"
            elif mutation == "version":
                raw["format"] = hands.CALENDAR_FORMAT
            else:
                raw["reminders"].append(deepcopy(target))
            write_json_atomic(hands.hands_path(self.pack), raw)
            before = hands.hands_path(self.pack).read_bytes()
            with self.subTest(mutation=mutation), self.assertRaises(SeedError):
                hands.add_reminder(self.pack, "不能覆写", due_on=self.on(6), created_day=self.day["dayNo"])
            self.assertEqual(hands.hands_path(self.pack).read_bytes(), before)
        # Legacy loaders used to skip malformed rows; editing must not lose them on upgrade.
        write_json_atomic(hands.hands_path(self.pack), {"format": hands.CALENDAR_FORMAT, "reminders": [row, {"text": "损坏旧行"}]})
        before = hands.hands_path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            changes.perform(self.pack, "cancel", {"reminder_id": row["id"], "expected": changes.fingerprint(row), "reason": "取消"})
        self.assertEqual(hands.hands_path(self.pack).read_bytes(), before)

    def test_backup_preserves_history_and_pending_revision_without_automatic_resume(self):
        row = self.schedule()
        changes.perform(self.pack, "revise", self.payload(row, text="调整后的事项", due_on=self.on(4)))
        data = self.payload(row)
        with patch("seedbank.hands.save_hands", side_effect=OSError("fixture")), self.assertRaises(OSError):
            changes.perform(self.pack, "cancel", data, request_id="backup-cancel")
        archive = backup.create(self.pack)
        restored = self.pack.parent / "reminder-restored.life"
        backup.restore(archive["file"], restored)
        self.assertEqual(hands.hands_path(restored).read_bytes(), hands.hands_path(self.pack).read_bytes())
        self.assertEqual(hands.find_reminder(restored, row["id"])["status"], "pending")
        self.assertEqual(requests.get(restored, "backup-cancel")["status"], "pending")
        result = Bridge(restored, "stub").handle({"op": "resume", "request_id": "backup-cancel"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(hands.find_reminder(restored, row["id"])["status"], "cancelled")
        self.assertEqual(hands.find_reminder(self.pack, row["id"])["status"], "pending")
        check(restored)

    def test_cli_listing_and_bridge_use_the_same_revision_guard(self):
        row = self.schedule()
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["reminder-change", str(self.pack), "list"]), 0)
        entry = json.loads(output.getvalue())["reminders"][0]
        self.assertEqual(entry["expected"], changes.fingerprint(row))
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["reminder-change", str(self.pack), "revise", "--id", row["id"],
                "--expected", entry["expected"], "--reason", "日期调整", "--text", "新内容", "--due-on", self.on(3)]), 0)
        reply = Bridge(self.pack, "stub").handle({"op": "reminder", "action": "cancel", **self.payload(row), "id": "rpc-correlation"})
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(hands.find_reminder(self.pack, row["id"])["status"], "cancelled")
        text = _hands_lines({"hands": hands.hands_summary(self.pack, self.day["dayNo"])})
        self.assertNotIn("新内容", text)
        self.assertIn("不能仅因曾经提及", text)


if __name__ == "__main__":
    unittest.main()
