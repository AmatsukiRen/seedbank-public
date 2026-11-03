"""User-run fault-injection regressions. Temporary packs, no network or GUI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import backup
from seedbank.cognition import chat_turn
from seedbank.durability import Mutation, RecoveryRequired, operation, replace_bytes
from seedbank.pack import hatch
from seedbank.pack_lock import writer
from seedbank.requests import get, pending
from seedbank.util import SeedError, read_memories, write_file_atomic

ROOT = Path(__file__).resolve().parents[2]


class Brain:
    name = "fixture"

    def chat(self, ctx):
        return {"reply": "这是隔离夹具的回复。", "memory_writes": [
            {"text": "保留一条带来源的测试记忆。", "importance": 0.7}]}


class DurabilityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-recovery-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.pack = self.folder / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="durability",
              born_at_override="2026-11-01T00:00:00Z")

    def contents(self):
        return {p.relative_to(self.pack).as_posix(): p.read_bytes() for p in self.pack.rglob("*")
                if p.is_file() and not p.relative_to(self.pack).as_posix().startswith(
                    ("mind/.transactions/", "mind/requests/", "mind/search.sqlite3", "mind/.writer.lock"))
                and ".tmp-" not in p.name}

    def crash(self, script):
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (
            str(ROOT / "tools/seed"), os.environ.get("PYTHONPATH", ""))))}
        result = subprocess.run([sys.executable, "-c", script, str(self.pack)], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 86, result.stderr)

    def test_exception_rolls_back_every_mutated_file_and_keeps_input(self):
        before = self.contents()
        with patch("seedbank.cognition.body.spend", side_effect=OSError("injected disk error")):
            with self.assertRaises(OSError):
                chat_turn(self.pack, "不能丢失的输入", Brain(), request_id="once")
        self.assertEqual(self.contents(), before)
        self.assertEqual(pending(self.pack)[0]["payload"]["text"], "不能丢失的输入")

    def test_hard_exit_after_partial_turn_recovers_on_next_writer(self):
        before = self.contents()
        self.crash('''
import os, sys
from unittest.mock import patch
from seedbank.cognition import chat_turn
class Brain:
    name = "fixture"
    def chat(self, ctx):
        return {"reply": "fixture reply", "memory_writes": [{"text": "partial memory", "importance": 0.7}]}
with patch("seedbank.cognition.body.spend", side_effect=lambda *a, **k: os._exit(86)):
    chat_turn(sys.argv[1], "saved before the model", Brain(), request_id="crash")
''')
        with writer(self.pack) as recovered:
            self.assertEqual(len(recovered), 1)
        self.assertEqual(self.contents(), before)
        self.assertEqual(get(self.pack, "crash")["status"], "pending")

    def test_hard_exit_before_model_reply_keeps_input_without_resending(self):
        self.crash('''
import os, sys
from seedbank.cognition import chat_turn
class Brain:
    name = "fixture"
    def chat(self, ctx):
        os._exit(86)
chat_turn(sys.argv[1], "unfinished input", Brain(), request_id="before-reply")
''')
        with writer(self.pack):
            self.assertEqual(get(self.pack, "before-reply")["status"], "pending")
        self.assertEqual(pending(self.pack)[0]["payload"]["text"], "unfinished input")

    def test_committed_retry_does_not_call_model_or_mutate_memory(self):
        first = chat_turn(self.pack, "重复送达的一条请求", Brain(), request_id="stable-id")
        before = self.contents()
        with patch.object(Brain, "chat", side_effect=AssertionError("model must not be called")):
            repeated = chat_turn(self.pack, "重复送达的一条请求", Brain(), request_id="stable-id")
        self.assertTrue(repeated["replayed"])
        self.assertEqual(repeated["reply"], first["reply"])
        self.assertEqual(self.contents(), before)
        self.assertEqual(pending(self.pack), [])
        with self.assertRaises(SeedError):
            chat_turn(self.pack, "不同内容", Brain(), request_id="stable-id")

    def test_completed_turn_survives_lost_client_response(self):
        self.crash('''
import os, sys
from seedbank.cognition import chat_turn
from seedbank.brain import create_stub_brain
chat_turn(sys.argv[1], "commit then lose response", create_stub_brain(), request_id="delivered")
os._exit(86)
''')
        before = self.contents()
        with patch.object(Brain, "chat", side_effect=AssertionError("no replay")):
            result = chat_turn(self.pack, "commit then lose response", Brain(), request_id="delivered")
        self.assertTrue(result["replayed"])
        self.assertEqual(self.contents(), before)

    def test_crash_after_request_receipt_before_commit_restores_pending_input(self):
        before = self.contents()
        self.crash('''
import os, sys
from unittest.mock import patch
from seedbank import durability
from seedbank.cognition import chat_turn
from seedbank.brain import create_stub_brain
save = durability._save
def cut(folder, manifest):
    if manifest["state"] == "committed":
        os._exit(86)
    return save(folder, manifest)
with patch("seedbank.durability._save", side_effect=cut):
    chat_turn(sys.argv[1], "restore my pending input", create_stub_brain(), request_id="before-commit")
''')
        with writer(self.pack):
            self.assertEqual(get(self.pack, "before-commit")["status"], "pending")
        self.assertEqual(self.contents(), before)

    def test_failed_nested_action_restores_savepoint_but_parent_can_commit(self):
        file = self.pack / "mind/fixture.txt"
        write_file_atomic(file, "original")
        with writer(self.pack), operation(self.pack, "outer"):
            write_file_atomic(file, "parent")
            try:
                with operation(self.pack, "action"):
                    write_file_atomic(file, "partial action")
                    write_file_atomic(self.pack / "art/partial.txt", "partial")
                    raise ValueError("action failed")
            except ValueError:
                pass
            self.assertEqual(file.read_text(), "parent")
            self.assertFalse((self.pack / "art/partial.txt").exists())
        self.assertEqual(file.read_text(), "parent")

    def test_recovery_refuses_to_overwrite_external_changes(self):
        file = self.pack / "mind/fixture.txt"
        write_file_atomic(file, "original")
        with writer(self.pack):
            mutation = Mutation(self.pack.resolve(), "crash fixture")
            mutation.prepare(file, b"partial")
            replace_bytes(file, b"partial")
        file.write_text("external edit", encoding="utf-8")
        with self.assertRaises(RecoveryRequired):
            with writer(self.pack):
                pass
        self.assertEqual(file.read_text(), "external edit")
        self.assertTrue((mutation.folder / "manifest.json").exists())

    def test_backup_restore_preserves_all_archived_bytes_and_pending_input(self):
        with patch.object(Brain, "chat", side_effect=ValueError("interrupted")):
            with self.assertRaises(ValueError):
                chat_turn(self.pack, "pending backup input", Brain(), request_id="saved")
        saved = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(saved["file"], restored)
        for relative, path in backup._files(self.pack):
            self.assertEqual(path.read_bytes(), (restored / relative).read_bytes(), relative)
        self.assertEqual(pending(restored)[0]["payload"]["text"], "pending backup input")
        self.assertFalse((restored / "mind/search.sqlite3").exists())
        with self.assertRaises(SeedError):
            backup.restore(saved["file"], restored)

    def test_tampered_backup_is_not_published(self):
        saved = backup.create(self.pack)
        tampered = self.folder / "tampered.zip"
        with zipfile.ZipFile(saved["file"]) as original, zipfile.ZipFile(tampered, "w") as changed:
            for name in original.namelist():
                content = original.read(name)
                if name == "pack/birth.json":
                    content = content.replace(b'"name"', b'"namo"', 1)
                changed.writestr(name, content)
        destination = self.folder / "invalid.life"
        with self.assertRaises(SeedError):
            backup.restore(tampered, destination)
        self.assertFalse(destination.exists())
        self.assertTrue((self.pack / "birth.json").exists())

    def test_restore_rejects_paths_outside_destination(self):
        import hashlib
        bad = self.folder / "outside.zip"
        payload = b"must not escape"
        manifest = {"format": backup.LEGACY_FORMAT, "files": [
            {"path": "../escaped.txt", "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]}
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr(backup.MANIFEST, json.dumps(manifest))
            archive.writestr("pack/../escaped.txt", payload)
        with self.assertRaises(SeedError):
            backup.restore(bad, self.folder / "outside.life")
        self.assertFalse((self.folder / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main()
