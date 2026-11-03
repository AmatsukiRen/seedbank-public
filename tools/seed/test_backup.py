"""User-run archive regressions. Authored but not executed by the agent."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import backup
from seedbank.pack import hatch
from seedbank.util import SeedError

ROOT = Path(__file__).resolve().parents[2]


class BackupTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-backup-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.pack = self.folder / "source.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "档案测试", seed_override="backup-v2", born_at_override="2026-11-01T00:00:00Z")

    def legacy(self, entries=None, name="legacy.zip"):
        payloads = entries or {rel: file.read_bytes() for rel, file in backup._files(self.pack)}
        file = self.folder / name
        rows = [{"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for rel, data in payloads.items()]
        with zipfile.ZipFile(file, "w") as archive:
            archive.writestr(backup.MANIFEST, json.dumps({"format": backup.LEGACY_FORMAT, "files": rows}))
            for rel, data in payloads.items():
                archive.writestr("pack/" + rel, data)
        return file

    def rewrite(self, source, edit):
        target = self.folder / (Path(source).stem + "-changed.zip")
        with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
            for name in old.namelist():
                new.writestr(name, edit(name, old.read(name)))
        return target

    def assert_bytes_restored(self, target):
        for relative, file in backup._files(self.pack):
            self.assertEqual(file.read_bytes(), (target / relative).read_bytes(), relative)

    def test_backup_uses_consistent_handle_metadata_when_path_ctime_differs(self):
        original = backup.os.fstat

        def handle_stat(fd):
            stat = original(fd)
            return SimpleNamespace(**{name: getattr(stat, name) for name in
                ("st_dev", "st_ino", "st_size", "st_mtime_ns")}, st_ctime_ns=stat.st_ctime_ns + 123456)

        with patch.object(backup.os, "fstat", side_effect=handle_stat):
            created = backup.create(self.pack)
        restored = self.folder / "handle-stat.life"
        backup.restore(created["file"], restored)
        self.assert_bytes_restored(restored)

    def test_new_index_can_exceed_legacy_manifest_budget_and_restore_original_bytes(self):
        for number in range(80):
            path = self.pack / "mind/requests/completed" / f"{number:02d}" / "fixture.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"fixture": number}), encoding="utf-8")
        created = backup.create(self.pack)
        with zipfile.ZipFile(created["file"]) as archive:
            header = json.loads(archive.read(backup.MANIFEST))
            self.assertNotIn("files", header)
            self.assertEqual(header["format"], backup.FORMAT)
            self.assertGreater(archive.getinfo(backup.INDEX).file_size, 512)
        restored = self.folder / "restored.life"
        # A reduced legacy budget is a small fixture, not a many-year performance claim.
        with patch.object(backup, "MANIFEST_LIMIT", 512):
            preview = backup.inspect_backup(created["file"])
            result = backup.restore(created["file"], restored, expected=preview["manifest_digest"])
        self.assertFalse(preview["contents_verified"])
        self.assertTrue(result["contents_verified"])
        self.assert_bytes_restored(restored)

    def test_valid_legacy_backup_remains_readable(self):
        source = self.legacy()
        preview = backup.inspect_backup(source)
        self.assertEqual(preview["format"], backup.LEGACY_FORMAT)
        restored = self.folder / "legacy.life"
        backup.restore(source, restored, expected=preview["manifest_digest"])
        self.assert_bytes_restored(restored)

    def test_tampered_index_is_rejected_before_extraction(self):
        source = backup.create(self.pack)["file"]
        bad = self.rewrite(source, lambda name, data: data.replace(b'"sha256":"', b'"sha256":"0', 1) if name == backup.INDEX else data)
        destination = self.folder / "bad.life"
        with self.assertRaises(SeedError):
            backup.restore(bad, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.folder.glob(".bad.life.restore-*")), [])

    def test_preview_is_not_a_payload_integrity_claim(self):
        source = backup.create(self.pack)["file"]
        bad = self.rewrite(source, lambda name, data: data.replace(b'"name"', b'"namo"', 1) if name == "pack/birth.json" else data)
        preview = backup.inspect_backup(bad)
        self.assertFalse(preview["contents_verified"])
        with self.assertRaises(SeedError):
            backup.restore(bad, self.folder / "bad.life", expected=preview["manifest_digest"])
        self.assertFalse((self.folder / "bad.life").exists())

    def test_changed_preview_is_rejected(self):
        source = backup.create(self.pack)["file"]
        preview = backup.inspect_backup(source)
        changed = self.rewrite(source, lambda name, data: json.dumps({**json.loads(data), "pack_name": "different.life"}).encode()
                               if name == backup.MANIFEST else data)
        with self.assertRaisesRegex(SeedError, "清单已变化"):
            backup.restore(changed, self.folder / "changed.life", expected=preview["manifest_digest"])

    def test_path_and_portable_alias_collisions_are_rejected(self):
        birth = (self.pack / "birth.json").read_bytes()
        cases = [
            {"birth.json": birth, "../escaped.txt": b"escape"},
            {"birth.json": birth, "Folder/a.txt": b"a", "folder/b.txt": b"b"},
            {"birth.json": birth, "same": b"file", "same/child": b"child"},
            {"birth.json": birth, "mind/.transactions/bad": b"reserved"},
            {"birth.json": birth, "mind/a/./b": b"noncanonical"},
        ]
        for i, entries in enumerate(cases):
            with self.subTest(i=i), self.assertRaises(SeedError):
                backup.restore(self.legacy(entries, name=f"unsafe-{i}.zip"), self.folder / f"unsafe-{i}.life")
        self.assertFalse((self.folder / "escaped.txt").exists())

    def test_extra_members_and_symbolic_links_are_rejected(self):
        source = self.legacy()
        with zipfile.ZipFile(source, "a") as archive:
            archive.writestr("unlisted.txt", "unlisted")
        with self.assertRaises(SeedError):
            backup.inspect_backup(source)
        source = self.legacy(name="link.zip")
        with zipfile.ZipFile(source, "a") as archive:
            info = zipfile.ZipInfo("link")
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "outside")
        with self.assertRaises(SeedError):
            backup.inspect_backup(source)

    def test_external_edit_during_backup_stops_publication(self):
        target = self.folder / "unstable.zip"
        source = self.pack / "mind" / "fixture.txt"
        source.write_text("before", encoding="utf-8")
        def progress(info):
            if info["stage"] == "writing":
                source.write_text("changed source", encoding="utf-8")
        with self.assertRaises(SeedError):
            backup.create(self.pack, target, progress=progress)
        self.assertFalse(target.exists())
        self.assertEqual(source.read_text(), "changed source")

    def test_cancel_backup_and_restore_publish_nothing_and_preserve_source(self):
        original = (self.pack / "birth.json").read_bytes()
        target = self.folder / "cancelled.zip"
        cancelled = Event()
        def cancel_write(info):
            if info["stage"] == "writing":
                cancelled.set()
        with self.assertRaises(backup.BackupCancelled):
            backup.create(self.pack, target, progress=cancel_write, cancel=cancelled)
        self.assertFalse(target.exists())
        self.assertEqual((self.pack / "birth.json").read_bytes(), original)
        created = backup.create(self.pack)
        cancelled.clear()
        def cancel_restore(info):
            if info["stage"] == "restoring":
                cancelled.set()
        with self.assertRaises(backup.BackupCancelled):
            backup.restore(created["file"], self.folder / "cancelled.life", progress=cancel_restore, cancel=cancelled)
        self.assertFalse((self.folder / "cancelled.life").exists())
        self.assertEqual(list(self.folder.glob(".cancelled.life.restore-*")), [])

    def test_existing_destinations_and_publication_races_are_preserved(self):
        target = self.folder / "occupied.zip"
        target.write_bytes(b"existing backup")
        with self.assertRaises(SeedError):
            backup.create(self.pack, target)
        self.assertEqual(target.read_bytes(), b"existing backup")
        source = backup.create(self.pack)["file"]
        destination = self.folder / "race.life"
        def occupy(info):
            if info["stage"] == "publishing":
                destination.mkdir()
                (destination / "keep.txt").write_text("preserve", encoding="utf-8")
        with self.assertRaises(SeedError):
            backup.restore(source, destination, progress=occupy)
        self.assertEqual((destination / "keep.txt").read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
