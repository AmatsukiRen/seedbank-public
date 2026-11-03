"""User-run intake recovery cases; no tests executed by the agent."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from seedbank import backup, experience, media_archive, media_intake, requests
from seedbank.bridge import Bridge
from seedbank.cognition import sense_media
from seedbank.durability import operation
from seedbank.pack import hatch
from seedbank.pack_lock import writer
from seedbank.qq import QQAdapter
from seedbank.util import SeedError, read_memories
from test_qq import private_event, group_event

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "tools/seed/testdata"


class MediaIntakeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="seedbank-intake-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.pack = self.folder / "source.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="intake-fixture", born_at_override="2026-11-01T00:00:00Z")
        self.image = self.folder / "source.png"
        self.image.write_bytes((DATA / "bright-warm.png").read_bytes())
        guard = patch("seedbank.cognition.vision_translate", side_effect=AssertionError("No real vision calls"))
        guard.start()
        self.addCleanup(guard.stop)

    def send(self, identifier="once", **kwargs):
        return sense_media(self.pack, image=self.image, vision=False, note="原始随附说明。", request_id=identifier, **kwargs)

    def fail(self, identifier="once"):
        with patch("seedbank.cognition.analyze_image", side_effect=SeedError("decoder interrupted")):
            with self.assertRaisesRegex(SeedError, "原件已保存"):
                self.send(identifier)
        return requests.get(self.pack, identifier)

    def test_acceptance_and_note_survive_processing_error_and_deleted_input(self):
        pending = self.fail()
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(len(media_archive.read(self.pack)), 1)
        note_id = pending["payload"]["note_event_id"]
        original_note = next(e for e in experience.read(self.pack) if e["id"] == note_id)
        self.image.unlink()
        result = media_intake.resume(self.pack, "once")
        self.assertFalse(result["replayed"])
        self.assertEqual(requests.get(self.pack, "once")["status"], "complete")
        self.assertEqual(next(e for e in experience.read(self.pack) if e["id"] == note_id), original_note)
        self.assertEqual(len([e for e in experience.read(self.pack) if e["id"] == note_id]), 1)
        self.assertEqual(len(media_archive.read(self.pack)), 1)

    def test_duplicate_pending_delivery_acknowledges_without_restarting_analysis(self):
        self.fail()
        with patch("seedbank.cognition.analyze_image", side_effect=AssertionError("No automatic retry")):
            duplicate = self.send()
            inspected = media_intake.probe(self.pack, "once", expected=requests.get(self.pack, "once")["payload"]["submission"])
        self.assertTrue(duplicate["pending"])
        self.assertTrue(inspected["pending"])
        self.assertEqual(len(media_archive.read(self.pack)), 1)

    def test_duplicate_completed_delivery_does_not_write_another_interpretation(self):
        first = self.send()
        events = experience.read(self.pack)
        memories = read_memories(self.pack)
        self.image.unlink()
        with patch("seedbank.cognition.analyze_image", side_effect=AssertionError("No repeated analysis")):
            second = self.send()
        self.assertTrue(second["replayed"])
        self.assertEqual(first["assets"], second["assets"])
        self.assertEqual(events, experience.read(self.pack))
        self.assertEqual(memories, read_memories(self.pack))

    def test_same_request_rejects_changed_bytes_note_or_scope(self):
        self.send()
        self.image.write_bytes((DATA / "bright-warm.jpg").read_bytes())
        with self.assertRaises(SeedError):
            self.send()
        self.image.write_bytes((DATA / "bright-warm.png").read_bytes())
        with self.assertRaises(SeedError):
            sense_media(self.pack, image=self.image, note="另一份说明", vision=False, request_id="once")
        with self.assertRaises(SeedError):
            self.send(person_id="", audience_id="qq-group:123")
        self.assertEqual(len(media_archive.read(self.pack)), 1)

    def test_failed_acceptance_does_not_leave_orphan_original_or_receipt(self):
        before = experience.read(self.pack)
        with patch("seedbank.media_intake.requests.prepare", side_effect=SeedError("disk full")):
            with self.assertRaises(SeedError):
                self.send()
        self.assertIsNone(requests.lookup(self.pack, "once"))
        self.assertEqual(media_archive.read(self.pack), [])
        self.assertEqual(experience.read(self.pack), before)
        self.assertEqual(list((self.pack / "media").rglob("*.png")), [])

    def test_interruption_immediately_after_acceptance_keeps_request_and_bytes(self):
        with patch("seedbank.media_intake.resume", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.send()
        self.assertEqual(requests.get(self.pack, "once")["status"], "pending")
        row = media_archive.read(self.pack)[0]
        self.assertEqual((self.pack / row["blob"]).read_bytes(), self.image.read_bytes())

    def test_partial_interpretation_rolls_back_without_erasing_accepted_input(self):
        before = read_memories(self.pack)
        with patch("seedbank.cognition.append_memories", side_effect=SeedError("memory write failed")):
            with self.assertRaises(SeedError):
                self.send()
        self.assertEqual(read_memories(self.pack), before)
        events = [e for e in experience.read(self.pack) if e.get("metadata", {}).get("intake_id") == "once"]
        self.assertFalse(any(e["kind"] == "perception" for e in events))
        self.assertEqual(requests.get(self.pack, "once")["status"], "pending")
        self.assertEqual(len(media_archive.read(self.pack)), 1)

    def test_cancel_keeps_original_and_never_restarts_after_duplicate(self):
        pending = self.fail()
        reference = pending["payload"]["assets"]["image"]
        cancelled = media_intake.cancel(self.pack, "once")
        self.assertTrue(cancelled["cancelled"])
        self.image.unlink()
        with patch("seedbank.cognition.analyze_image", side_effect=AssertionError("No processing after cancel")):
            self.assertTrue(self.send()["cancelled"])
            self.assertTrue(media_intake.resume(self.pack, "once")["cancelled"])
        row = media_archive.detail(self.pack, reference["id"])
        self.assertEqual(row["processing"]["state"], "cancelled")
        self.assertEqual(row["state"], "available")
        self.assertEqual(requests.pending(self.pack), [])

    def test_pending_request_and_original_travel_together_in_backup(self):
        self.fail()
        created = backup.create(self.pack)
        self.image.unlink()
        restored = self.folder / "restored.life"
        backup.restore(created["file"], restored)
        with patch("seedbank.cognition.vision_translate", side_effect=AssertionError("Keep explicit vision=False")):
            result = media_intake.resume(restored, "once")
        self.assertEqual(len(result["assets"]), 1)
        self.assertEqual(requests.get(restored, "once")["status"], "complete")
        self.assertEqual(requests.get(self.pack, "once")["status"], "pending")

    def test_withdrawn_media_prevents_pending_processing_and_completed_replay(self):
        self.fail("pending")
        first = media_archive.read(self.pack)[0]
        media_archive.perform(self.pack, "forget", {"asset_id": first["id"], "reason": "暂时放下"})
        with self.assertRaises(SeedError):
            media_intake.resume(self.pack, "pending")
        completed = self.send("completed")
        media_archive.perform(self.pack, "forget", {"asset_id": completed["assets"][0], "reason": "不再使用"})
        with self.assertRaises(SeedError):
            media_intake.resume(self.pack, "completed")

    def test_group_request_probe_rejects_owner_header(self):
        result = self.send(person_id="", audience_id="qq-group:123")
        expected = deepcopy(requests.get(self.pack, "once")["payload"]["submission"])
        expected.update(person_id="owner", audience_id="owner")
        with self.assertRaises(SeedError):
            media_intake.probe(self.pack, "once", expected=expected)
        self.assertEqual(media_archive.detail(self.pack, result["assets"][0])["audience_id"], "qq-group:123")

    def test_withdrawn_interpretation_does_not_escape_through_completed_receipt(self):
        from seedbank.cognition import forget_memory
        self.send()
        interpreted = next(m for m in read_memories(self.pack) if m.get("generation", {}).get("intake_id") == "once" and m["kind"] == "perception")
        forget_memory(self.pack, interpreted["id"], reason="不再使用这段解释")
        with self.assertRaises(SeedError):
            media_intake.resume(self.pack, "once")

    def test_lost_queue_file_does_not_duplicate_known_receipt(self):
        self.fail()
        record = media_archive.read(self.pack)[0]
        requests._path(self.pack, "once").unlink()
        self.assertEqual(media_archive.detail(self.pack, record["id"])["processing"]["state"], "unavailable")
        with self.assertRaises(SeedError):
            self.send()
        self.assertEqual(len(media_archive.read(self.pack)), 1)
        self.assertTrue(Path(media_archive.export(self.pack, record["id"])["file"]).is_file())

    def test_nested_acceptance_is_rejected_before_persisting_material(self):
        with writer(self.pack), operation(self.pack, "outer"):
            with self.assertRaisesRegex(SeedError, "独立操作"):
                self.send()
        self.assertEqual(media_archive.read(self.pack), [])

    def test_calendar_work_starts_only_after_input_is_durably_accepted(self):
        observed = []

        def calendar():
            observed.append(requests.get(self.pack, "once")["status"])
            self.assertEqual(len(media_archive.read(self.pack)), 1)
            raise SeedError("calendar interrupted")

        with self.assertRaisesRegex(SeedError, "原件已保存"):
            self.send(before_process=calendar)
        self.assertEqual(observed, ["pending"])
        self.assertEqual(requests.get(self.pack, "once")["status"], "pending")

    def test_image_and_sound_share_one_acceptance_and_complete_once(self):
        result = sense_media(self.pack, image=self.image, sound=DATA / "sound.wav", note="一起收到", vision=False, request_id="both")
        self.assertEqual(len(result["assets"]), 2)
        rows = media_archive.read(self.pack)
        self.assertEqual({r["intake_id"] for r in rows}, {"both"})
        self.assertEqual({r["media_kind"] for r in rows}, {"image", "sound"})
        self.assertTrue(media_intake.resume(self.pack, "both")["replayed"])

    def qq_adapter(self):
        core = Bridge(self.pack, "stub")
        core._tick = lambda: None

        class LocalBridge:
            def call(self, op, **fields):
                result = core.handle({"op": op, **fields})
                if not result.get("ok"):
                    raise RuntimeError(result.get("error"))
                return result

        adapter = QQAdapter(str(self.pack), "7", ["123"], bridge=LocalBridge(), sender=Mock(), log=lambda message: None)
        adapter.sender.send_group.return_value = adapter.sender.send_private.return_value = {"status": "ok", "retcode": 0}
        count = []

        def download(url):
            folder = self.folder / f"download-{len(count)}"
            folder.mkdir()
            file = folder / "photo.png"
            file.write_bytes((DATA / "bright-warm.png").read_bytes())
            count.append(file)
            return file

        adapter._download = download
        return adapter, count

    def qq_image(self, *, group=False, message_id=1234):
        event = group_event(123, 7) if group else private_event(7)
        event["message_id"] = message_id
        event["message"].append({"type": "image", "data": {"url": "https://fixture.invalid/photo"}})
        return event

    def test_qq_duplicate_uses_saved_result_after_temporary_download_is_removed(self):
        adapter, downloads = self.qq_adapter()
        with patch("seedbank.cognition.vision_translate", return_value={"ok": True, "text": "假视觉描述", "provider": "fake", "model": "fixture"}) as vision:
            first = adapter.handle(self.qq_image())
            second = adapter.handle(self.qq_image())
        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        self.assertEqual(len(downloads), 1)
        self.assertFalse(downloads[0].exists())
        self.assertEqual(vision.call_count, 1)
        self.assertEqual(len(media_archive.read(self.pack)), 1)

    def test_qq_duplicate_pending_does_not_download_or_retry_model(self):
        adapter, downloads = self.qq_adapter()
        with patch("seedbank.cognition.analyze_image", side_effect=SeedError("interrupted")):
            self.assertFalse(adapter.handle(self.qq_image())["ok"])
        with patch("seedbank.cognition.analyze_image", side_effect=AssertionError("No automatic retry")):
            result = adapter.handle(self.qq_image())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["reason"], "duplicate")
        adapter.sender.send_private.assert_not_called()
        self.assertEqual(len(downloads), 1)
        self.assertEqual(len(requests.pending(self.pack)), 1)

    def test_qq_same_message_id_in_different_conversations_is_not_merged(self):
        adapter, downloads = self.qq_adapter()
        with patch("seedbank.cognition.vision_translate", return_value={"ok": False, "reason": "fixture"}):
            self.assertTrue(adapter.handle(self.qq_image())["ok"])
            self.assertTrue(adapter.handle(self.qq_image(group=True))["ok"])
        self.assertEqual(len(downloads), 2)
        self.assertEqual({r["audience_id"] for r in media_archive.read(self.pack)}, {"owner", "qq-group:123"})


if __name__ == "__main__":
    unittest.main()
