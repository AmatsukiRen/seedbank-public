"""User-run dormancy regressions. No real packs, model requests or GUI."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from seedbank import backup, cognition, lifecycle, live
from seedbank.brain import create_stub_brain
from seedbank.bridge import Bridge
from seedbank.clock import tick
from seedbank.pack import hatch, check
from seedbank.pack_lock import writer
from seedbank.requests import prepare, pending
from seedbank.util import SeedError, list_days, local_date

ROOT = Path(__file__).resolve().parents[2]
PAUSE_AT = "2026-11-02T10:00:00Z"
RESUME_AT = "2026-11-07T10:00:00Z"


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-lifecycle-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        guard = patch.dict(os.environ, {"HOME": str(self.folder / "home"),
            "USERPROFILE": str(self.folder / "home"), "SEEDBANK_LANG": "zh_CN"})
        guard.start()
        self.addCleanup(guard.stop)
        self.pack = self.folder / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="lifecycle",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = cognition.start_day(self.pack)
        self.brain = Mock()
        self.brain.chat.side_effect = AssertionError("No model during dormancy")
        self.brain.diary.side_effect = AssertionError("No diary during dormancy")
        self.brain.initiate.side_effect = AssertionError("No initiation during dormancy")

    def files(self):
        return {rel: path.read_bytes() for rel, path in backup._files(self.pack)}

    def pause(self):
        return lifecycle.transition(self.pack, "pause", note="测试：记录明确告别的背景。",
                                    expected=0, confirmed=True, now=PAUSE_AT)

    def resume(self):
        return lifecycle.transition(self.pack, "resume", note="测试：明确选择继续。",
                                    expected=1, confirmed=True, now=RESUME_AT)

    def test_legacy_pack_is_active_without_migration(self):
        before = self.files()
        self.assertEqual(lifecycle.status(self.pack)["state"], "active")
        self.assertEqual(lifecycle.status(self.pack)["revision"], 0)
        self.assertEqual(self.files(), before)

    def test_requires_explicit_confirmation_note_and_current_revision(self):
        before = self.files()
        for fields in ({"confirmed": False}, {"confirmed": 1}, {"note": " "},
                       {"expected": 4}, {"expected": True}, {"action": "death"}):
            data = dict(action="pause", note="明确说明", expected=0, confirmed=True, now=PAUSE_AT)
            data.update(fields)
            with self.subTest(fields=fields), self.assertRaises(SeedError):
                lifecycle.transition(self.pack, **data)
        self.assertEqual(self.files(), before)

    def test_pause_preserves_archives_and_blocks_generation(self):
        before = self.files()
        self.pause()
        paused = self.files()
        self.assertEqual({key: paused[key] for key in before}, before)
        for operation in (
            lambda: cognition.chat_turn(self.pack, "继续说话", self.brain),
            lambda: cognition.run_days(self.pack, 1, self.brain),
            lambda: cognition.start_day(self.pack),
            lambda: cognition.feed_news(self.pack, ["消息"]),
            lambda: cognition.sense_media(self.pack, note="看见什么"),
            lambda: cognition.compose_work(self.pack, brain=self.brain, day=self.day),
            lambda: cognition.perform_inner(self.pack, {}, self.brain, self.day, "dream"),
        ):
            with self.assertRaises(SeedError):
                operation()
        self.assertEqual(self.files(), paused)
        self.brain.chat.assert_not_called()
        self.brain.diary.assert_not_called()

    def test_time_and_force_initiation_cannot_wake_a_dormant_pack(self):
        self.pause()
        before = self.files()
        self.assertFalse(tick(self.pack, self.brain, now="2099-11-02T10:00:00Z")["advanced"])
        self.assertIsNone(cognition.maybe_initiate(self.pack, self.brain, force=True))
        from seedbank.offline import grow
        self.assertIsNone(grow(self.pack))
        self.assertEqual(self.files(), before)
        self.brain.initiate.assert_not_called()

    def test_inbox_is_preserved_in_place_not_failed_or_consumed(self):
        queued = live.enqueue_event(self.pack, {"kind": "note", "text": "等待处理", "at": PAUSE_AT})
        self.pause()
        before = self.files()
        self.assertEqual(live.process_inbox(self.pack, brain=self.brain),
                         {"processed": [], "failed": [], "dormant": True})
        self.assertTrue(queued.exists())
        self.assertEqual(self.files(), before)

    def test_reopen_and_external_message_do_not_resume_or_connect(self):
        self.pause()
        bridge = Bridge(self.pack, "stub")
        self.assertFalse(bridge.handle({"op": "message", "text": "醒来"})["ok"])
        self.assertEqual(bridge.status()["lifecycle"]["state"], "dormant")
        from seedbank.qq import QQAdapter
        adapter = QQAdapter(self.pack, "123", [])
        with patch.object(adapter, "_get_bridge") as connection, patch.object(adapter, "_get_sender") as sender:
            self.assertEqual(adapter.handle({})["reason"], "dormant")
        connection.assert_not_called()
        sender.assert_not_called()

    def test_resume_keeps_old_pages_and_does_not_replay_pending_input(self):
        with writer(self.pack):
            prepare(self.pack, {"kind": "chat", "text": "之前未完成", "speaker": "主人"}, request_id="pending")
        pages = {p: p.read_bytes() for p in (self.pack / "life").glob("*.md")}
        self.pause()
        result = self.resume()
        self.assertEqual(result["state"], "active")
        self.assertEqual([r["to"] for r in result["history"]], ["dormant", "active"])
        self.assertTrue(all(r["actor"] == "user" for r in result["history"]))
        self.assertEqual({p: p.read_bytes() for p in pages}, pages)
        days = list_days(self.pack)
        self.assertEqual(len(days), len(pages) + 1)
        self.assertEqual(days[-1]["date"], local_date(RESUME_AT))
        self.assertNotIn("## 今天", (self.pack / "life" / days[-1]["file"]).read_text(encoding="utf-8"))
        self.assertEqual(len(pending(self.pack)), 1)
        check(self.pack)  # Authored assertion, executed only by the user.
        self.assertFalse(tick(self.pack, self.brain, now=RESUME_AT)["advanced"])
        self.brain.diary.assert_not_called()

    def test_same_day_resume_preserves_page_count(self):
        before = {p: p.read_bytes() for p in (self.pack / "life").glob("*.md")}
        self.pause()
        lifecycle.transition(self.pack, "resume", note="同日明确恢复", expected=1, confirmed=True, now=PAUSE_AT)
        self.assertEqual({p: p.read_bytes() for p in (self.pack / "life").glob("*.md")}, before)

    def test_old_age_or_offline_gap_does_not_automatically_pause(self):
        tick(self.pack, self.brain, now="2099-11-02T10:00:00Z")
        self.assertEqual(lifecycle.status(self.pack)["state"], "active")
        self.assertEqual(lifecycle.status(self.pack)["revision"], 0)

    def test_reply_prepared_before_pause_is_not_sent_after_pause(self):
        from seedbank.qq import QQAdapter
        fake_bridge, sender = Mock(), Mock()

        def reply(*args, **kwargs):
            self.pause()
            return {"ok": True, "reply": "旧回复"}

        fake_bridge.call.side_effect = reply
        adapter = QQAdapter(self.pack, "123", [], bridge=fake_bridge, sender=sender)
        event = {"post_type": "message", "message_type": "private", "user_id": 123,
                 "self_id": 999, "message_id": 1,
                 "message": [{"type": "text", "data": {"text": "之前的消息"}}]}
        self.assertEqual(adapter.handle(event)["reason"], "dormant")
        sender.send_private.assert_not_called()
        sender.send_group.assert_not_called()

    def test_stale_and_duplicate_transitions_do_not_override_new_choice(self):
        self.pause()
        self.resume()
        before = self.files()
        with self.assertRaises(SeedError):
            lifecycle.transition(self.pack, "pause", note="旧窗口", expected=0, confirmed=True, now=RESUME_AT)
        with self.assertRaises(SeedError):
            lifecycle.transition(self.pack, "resume", note="重复恢复", expected=2, confirmed=True, now=RESUME_AT)
        self.assertEqual(self.files(), before)

    def test_unreadable_state_fails_closed_without_overwriting(self):
        self.pause()
        path = self.pack / "mind/lifecycle.json"
        for data in (b"{broken", b'{"format":"seedbank/lifecycle@1","state":"active","revision":1,"history":[]}'):
            path.write_bytes(data)
            self.assertEqual(lifecycle.status(self.pack)["state"], "unavailable")
            self.assertFalse(tick(self.pack, self.brain, now=RESUME_AT)["advanced"])
            with self.assertRaises(SeedError):
                self.resume()
            self.assertEqual(path.read_bytes(), data)

    def test_backup_restore_retains_dormancy(self):
        self.pause()
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertEqual(lifecycle.status(restored), lifecycle.status(self.pack))
        self.assertFalse(tick(restored, self.brain, now=RESUME_AT)["advanced"])

    def test_failed_resume_rolls_back_new_page_clock_and_transition(self):
        self.pause()
        before = self.files()
        with patch("seedbank.lifecycle.write_json_atomic", side_effect=OSError("fixture write failure")):
            with self.assertRaises(OSError):
                self.resume()
        self.assertEqual(self.files(), before)

    def test_chat_farewell_words_are_not_lifecycle_commands(self):
        cognition.chat_turn(self.pack, "我们讨论告别和休眠，但现在没有作出选择。", create_stub_brain())
        self.assertEqual(lifecycle.status(self.pack)["revision"], 0)

    def test_cli_and_bridge_require_confirmation_and_revision(self):
        from seedbank.cli import _cmd_lifecycle
        bridge = Bridge(self.pack, "stub")
        self.assertFalse(bridge.handle({"op": "lifecycle", "action": "pause", "note": "说明", "expected": 0})["ok"])
        with redirect_stdout(io.StringIO()) as output:
            _cmd_lifecycle([str(self.pack), "status"])
        self.assertEqual(json.loads(output.getvalue())["revision"], 0)
        with self.assertRaises(SeedError):
            _cmd_lifecycle([str(self.pack), "pause", "--note", "说明", "--confirm"])


if __name__ == "__main__":
    unittest.main()
