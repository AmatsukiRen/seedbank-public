"""User-run original-media regressions; authored, not executed by the agent."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import backup, disclosure, experience, media_archive, persona
from seedbank.bridge import Bridge
from seedbank.cognition import analyze_image, build_context, open_day, sense_media
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.retrieval import search
from seedbank.util import SeedError, read_memories, write_file_atomic, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "tools/seed/testdata"


class MediaArchiveTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-media-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.pack = self.folder / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="media-fixture", born_at_override="2026-11-01T00:00:00Z")
        self.image = self.folder / "独特的原图.png"
        self.image.write_bytes((DATA / "bright-warm.png").read_bytes())
        guard = patch("seedbank.cognition.vision_translate", side_effect=AssertionError("No network"))
        guard.start()
        self.addCleanup(guard.stop)

    def receive(self, **kwargs):
        return sense_media(self.pack, image=self.image, vision=False, **kwargs)

    def asset(self, result):
        return media_archive.detail(self.pack, result["assets"][0])

    def interpreted(self):
        with patch("seedbank.cognition.vision_translate", return_value={"ok": True, "text": "画面里或许有一棵紫色银杏。",
                   "provider": "fake-vision", "model": "fixture", "sha256": media_archive.sha256(self.image.read_bytes())}):
            return self.asset(sense_media(self.pack, image=self.image, note="独立的说明文字。"))

    def test_analysis_reads_preserved_snapshot_even_when_external_file_disappears(self):
        original = self.image.read_bytes()

        def inspect(file):
            self.assertTrue(Path(file).is_relative_to(self.pack / "media"))
            self.image.unlink()
            return analyze_image(file)

        with patch("seedbank.cognition.analyze_image", side_effect=inspect):
            row = self.asset(self.receive(note="给你看旧相册。"))
        self.assertEqual((self.pack / row["blob"]).read_bytes(), original)
        self.assertEqual(row["name"], "独特的原图.png")
        self.assertNotIn(str(self.folder), media_archive.path(self.pack).read_text(encoding="utf-8"))
        self.assertEqual(row["state"], "available")
        memories = read_memories(self.pack)
        self.assertEqual(len({m["id"] for m in memories}), len(memories))

    def test_same_bytes_have_one_blob_but_distinct_receipts_and_scopes(self):
        private = self.asset(self.receive())
        group = self.asset(self.receive(person_id="", audience_id="qq-group:123"))
        self.assertNotEqual(private["id"], group["id"])
        self.assertEqual(private["blob"], group["blob"])
        policy = disclosure.policy_for(self.pack, "qq-group:123")
        nodes = {e["id"]: e for e in experience.read(self.pack)}
        self.assertFalse(policy.allows(nodes[private["event_id"]]))
        self.assertTrue(policy.allows(nodes[group["event_id"]]))
        media_archive.perform(self.pack, "forget", {"asset_id": private["id"], "reason": "私人回忆暂时放下。"})
        self.assertEqual(media_archive.detail(self.pack, group["id"])["state"], "available")
        self.assertTrue((self.pack / private["blob"]).is_file())

    def test_backup_retains_original_and_ledger_without_integrity_cache(self):
        row = self.asset(self.receive())
        expected = self.image.read_bytes()
        self.image.unlink()
        created = backup.create(self.pack)
        with zipfile.ZipFile(created["file"]) as archive:
            self.assertIn("pack/" + row["blob"], archive.namelist())
            self.assertNotIn("pack/mind/media-cache.sqlite3", archive.namelist())
        restored = self.folder / "restored.life"
        backup.restore(created["file"], restored)
        self.assertEqual((restored / row["blob"]).read_bytes(), expected)
        self.assertEqual(media_archive.detail(restored, row["id"])["state"], "available")

    def test_corrupt_original_withdraws_interpretations_and_raw_diary_fallback(self):
        row = self.interpreted()
        file = self.pack / row["blob"]
        original = file.read_bytes()
        file.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        stat = file.stat()
        os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        policy = MemoryPolicy.load(self.pack)
        self.assertIn(row["event_id"], policy.blocked)
        self.assertEqual(media_archive.detail(self.pack, row["id"])["state"], "changed")
        self.assertEqual(search(self.pack, "紫色银杏", use_semantic=False), [])
        day = open_day(self.pack)
        ctx = build_context(self.pack, day["dayNo"], day["date"], "紫色银杏", use_semantic=False)
        self.assertEqual(ctx["senses"], [])
        with self.assertRaises(SeedError):
            media_archive.export(self.pack, row["id"])

    def test_missing_original_is_unavailable_and_revisit_does_not_call_model(self):
        row = self.asset(self.receive())
        (self.pack / row["blob"]).unlink()
        self.assertEqual(media_archive.detail(self.pack, row["id"])["state"], "missing")
        with self.assertRaises(SeedError):
            media_archive.perform(self.pack, "revisit", {"asset_id": row["id"]})

    def test_unchanged_blob_uses_disk_hash_cache_and_changed_signature_rehashes(self):
        row = self.asset(self.receive())
        original_open = Path.open

        def guarded(file, *args, **kwargs):
            if file == self.pack / row["blob"]:
                raise AssertionError("Unchanged original should use its cached digest")
            return original_open(file, *args, **kwargs)

        with patch.object(Path, "open", guarded):
            media_archive.listing(self.pack)
        file = self.pack / row["blob"]
        file.write_bytes(b"broken")
        self.assertEqual(media_archive.listing(self.pack)["records"][0]["state"], "changed")

    def test_corrupt_cache_falls_back_to_original_and_is_preserved(self):
        row = self.asset(self.receive())
        cache = self.pack / "mind/media-cache.sqlite3"
        cache.write_bytes(b"damaged-cache")
        self.assertEqual(media_archive.detail(self.pack, row["id"])["state"], "available")
        self.assertEqual(cache.read_bytes(), b"damaged-cache")

    def test_receipt_tampering_does_not_establish_another_origin(self):
        row = self.asset(self.receive())
        rows = media_archive.read(self.pack)
        rows[0]["audience_id"] = "public"
        write_file_atomic(media_archive.path(self.pack), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        self.assertEqual(media_archive.detail(self.pack, row["id"])["state"], "unbound")
        self.assertIn(row["event_id"], MemoryPolicy.load(self.pack).blocked)

    def test_failed_analysis_preserves_accepted_original_for_explicit_resume(self):
        with patch("seedbank.cognition.analyze_image", side_effect=SeedError("decoder failed")):
            with self.assertRaises(SeedError):
                self.receive()
        rows = media_archive.read(self.pack)
        self.assertEqual(len(rows), 1)
        self.assertEqual((self.pack / rows[0]["blob"]).read_bytes(), self.image.read_bytes())
        self.assertEqual(media_archive.detail(self.pack, rows[0]["id"])["processing"]["state"], "pending")
        self.assertTrue(any(e["kind"] == "media_input" for e in experience.read(self.pack)))

    def test_failed_second_intake_keeps_shared_blob_and_first_receipt(self):
        first = self.asset(self.receive())
        with patch("seedbank.cognition.analyze_image", side_effect=SeedError("decoder failed")):
            with self.assertRaises(SeedError):
                self.receive()
        self.assertEqual(len(media_archive.read(self.pack)), 2)
        self.assertEqual(media_archive.detail(self.pack, first["id"])["state"], "available")

    def test_revisit_is_new_interpretation_of_old_receipt_and_retry_is_idempotent(self):
        row = self.asset(self.receive())
        response = {"ok": True, "text": "后来注意到了窗边的植物。", "provider": "fake", "model": "new-fixture", "sha256": row["sha256"]}
        with patch("seedbank.cognition.vision_translate", return_value=response) as vision:
            first = media_archive.perform(self.pack, "revisit", {"asset_id": row["id"], "note": "看看窗边"}, request_id="review-once")
            second = media_archive.perform(self.pack, "revisit", {"asset_id": row["id"], "note": "看看窗边"}, request_id="review-once")
        self.assertEqual(vision.call_count, 1)
        self.assertTrue(second["replayed"])
        self.assertFalse(first["replayed"])
        self.assertEqual(len([r for r in media_archive.read(self.pack) if r["kind"] == "receipt"]), 1)
        interpretations = [e for e in media_archive.detail(self.pack, row["id"])["events"] if e["metadata"].get("review")]
        self.assertTrue(interpretations)
        self.assertTrue(all(row["at"] in e["text"] for e in interpretations))
        media_archive.perform(self.pack, "forget", {"asset_id": row["id"], "reason": "暂时放下。"})
        with self.assertRaises(SeedError):
            media_archive.perform(self.pack, "revisit", {"asset_id": row["id"], "note": "看看窗边"}, request_id="review-once")

    def test_forget_keeps_audit_copy_and_independent_note(self):
        row = self.interpreted()
        data = {"asset_id": row["id"], "reason": "不再据此推断。"}
        media_archive.perform(self.pack, "forget", data, request_id="forget-once")
        self.assertTrue(media_archive.perform(self.pack, "forget", data, request_id="forget-once")["replayed"])
        self.assertEqual(search(self.pack, "紫色银杏", use_semantic=False), [])
        self.assertTrue(search(self.pack, "独立的说明文字", use_semantic=False))
        exported = Path(media_archive.export(self.pack, row["id"])["file"])
        self.assertEqual(exported.read_bytes(), self.image.read_bytes())
        exported.write_bytes(b"edited-copy")
        self.assertEqual((self.pack / row["blob"]).read_bytes(), self.image.read_bytes())

    def test_local_review_of_group_image_keeps_new_note_and_interpretation_private(self):
        row = self.asset(self.receive(person_id="", audience_id="qq-group:123"))
        with patch("seedbank.cognition.vision_translate", return_value={"ok": True, "text": "私人回看注意到的紫色银杏。", "provider": "fake", "model": "fixture"}):
            media_archive.perform(self.pack, "revisit", {"asset_id": row["id"], "note": "这份私人说明不应进入群聊。"})
        group_policy = disclosure.policy_for(self.pack, "qq-group:123")
        events = experience.read(self.pack)
        receipt = next(e for e in events if e["id"] == row["event_id"])
        self.assertTrue(group_policy.allows(receipt))
        private = [e for e in events if "私人" in e["text"]]
        self.assertTrue(private)
        self.assertTrue(all(e["metadata"]["audience_id"] == "owner" for e in private))
        self.assertTrue(all(not group_policy.allows(e) for e in private))
        self.assertEqual(search(self.pack, "私人", policy=group_policy, use_semantic=False), [])
        media_archive.perform(self.pack, "forget", {"asset_id": row["id"], "reason": "私人的放下理由。"})
        action = next(e for e in experience.read(self.pack) if e["kind"] == "media_forget")
        self.assertFalse(disclosure.policy_for(self.pack, "qq-group:123").allows(action))

    def test_note_only_has_no_receipt_and_unsupported_file_rolls_back(self):
        self.assertEqual(sense_media(self.pack, note="一条独立的感知说明。")["assets"], [])
        self.image.write_bytes(b"<html>not an image</html>")
        with self.assertRaises(SeedError):
            self.receive()
        self.assertEqual(media_archive.read(self.pack), [])

    def test_vision_note_does_not_assume_owner_and_keeps_full_review_note(self):
        from seedbank.brain import build_vision_prompt
        note = "前面的说明。" * 30 + "最后请留意窗边的植物。"
        prompt = build_vision_prompt(note)
        self.assertIn("最后请留意窗边的植物。", prompt)
        self.assertNotIn("主人递给她", prompt)

    def test_webp_can_be_archived_without_claiming_pixel_decoding(self):
        self.image.write_bytes(b"RIFF" + (12).to_bytes(4, "little") + b"WEBPVP8 " + b"fixture")
        result = self.receive()
        row = self.asset(result)
        self.assertEqual(row["extension"], "webp")
        self.assertTrue(any("未能解析" in e["text"] for e in row["events"]))

    def test_sound_bridge_preserves_actual_scope_and_lists_original(self):
        bridge = Bridge(self.pack, "stub")
        with patch.object(bridge, "_tick"):
            result = bridge.handle({"op": "sound", "path": str(DATA / "sound.wav"), "person_id": "", "audience_id": "qq-group:123"})
        self.assertTrue(result["ok"], result)
        row = self.asset(result)
        self.assertEqual(row["audience_id"], "qq-group:123")
        self.assertEqual(row["media_kind"], "sound")
        self.assertEqual((self.pack / row["blob"]).read_bytes(), (DATA / "sound.wav").read_bytes())
        self.assertTrue(bridge.handle({"op": "media", "action": "detail", "asset_id": row["id"]})["ok"])

    def test_media_receipt_expires_continuity_sample_and_old_source_set_is_legacy(self):
        baseline = persona.capture(self.pack)
        self.receive()
        with patch("seedbank.persona.create_brain", side_effect=AssertionError("No model")):
            self.assertIn("mind/media.jsonl", persona.check(self.pack)["archive"]["changed"])
        baseline["sources"].pop("mind/media.jsonl")
        baseline["sample_digest"] = persona._sample_digest(baseline)
        write_json_atomic(self.pack / "mind/persona.json", baseline)
        self.assertEqual(persona.check(self.pack)["reason"], "legacy_baseline")

    def test_missing_original_expires_a_frozen_continuity_sample(self):
        row = self.asset(self.receive())
        persona.capture(self.pack)
        (self.pack / row["blob"]).unlink()
        with patch("seedbank.persona.create_brain", side_effect=AssertionError("No model")):
            report = persona.check(self.pack)
        self.assertIn("mind/media.jsonl", report["archive"]["changed"])


if __name__ == "__main__":
    unittest.main()
