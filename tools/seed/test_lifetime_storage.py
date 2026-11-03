"""User-run lifetime storage regressions. Temporary packs only; no GUI/network.

These cases have been authored but not executed by the agent.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import durability, experience, file_state, jsonl, offline, retrieval
from seedbank.cognition import open_day, start_day
from seedbank.durability import Mutation, RecoveryRequired, operation, replace_bytes
from seedbank.pack import _DAY_HEADER, hatch
from seedbank.pack_lock import writer
from seedbank.util import SeedError, append_memories, list_days, read_memories, write_file_atomic

ROOT = Path(__file__).resolve().parents[2]


class LifetimeStorageTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-lifetime-")
        self.addCleanup(folder.cleanup)
        self.pack = Path(folder.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="lifetime",
              born_at_override="2026-11-01T00:00:00Z")
        self.log = self.pack / "mind/fixture.jsonl"

    def memory(self, identifier, text, **extra):
        row = {"id": identifier, "day": 1, "text": text, "importance": 0.6,
               "at": "2026-11-01T00:00:00Z", "source": "life/0001-2026-11-01.md", **extra}
        append_memories(self.pack, [row])
        return row

    def crash(self, script):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "tools/seed")}
        result = subprocess.run([sys.executable, "-c", script, str(self.pack)], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 86, result.stderr)

    def test_day_10000_is_listed_and_next_day_does_not_reuse_it(self):
        write_file_atomic(self.pack / "life/9999-2054-03-17.md", "# 第 9999 天 · 2054-03-17\n\n## 今天\n\n结束。\n")
        day = start_day(self.pack)
        self.assertEqual(day["dayNo"], 10000)
        self.assertEqual(open_day(self.pack)["dayNo"], 10000)
        self.assertEqual(list_days(self.pack)[-1]["file"], "10000-2054-03-18.md")
        current = self.pack / day["file"]
        self.assertEqual(_DAY_HEADER.match(current.read_text(encoding="utf-8"))[1], "10000")
        write_file_atomic(current, current.read_text(encoding="utf-8") + "\n## 今天\n\n结束。\n")
        self.assertEqual(start_day(self.pack)["dayNo"], 10001)

    def test_append_preserves_bom_original_spacing_and_missing_final_newline(self):
        original = b'\xef\xbb\xbf{ "id" : "old", "nested": {"value": 1} }'
        self.log.write_bytes(original)
        jsonl.append(self.pack, self.log, [{"id": "new"}])
        self.assertTrue(self.log.read_bytes().startswith(original + b"\n"))
        records = jsonl.read(self.log)
        records[0]["nested"]["value"] = 7
        self.assertEqual(jsonl.read(self.log)[0]["nested"]["value"], 1)
        self.assertEqual([row["id"] for row in records], ["old", "new"])

    def test_malformed_archive_is_not_silently_skipped_or_changed(self):
        original = b'{"id":"old"}\n{"broken":'
        self.log.write_bytes(original)
        with self.assertRaises(SeedError):
            jsonl.append(self.pack, self.log, [{"id": "new"}])
        self.assertEqual(self.log.read_bytes(), original)

    def test_append_recovery_snapshot_contains_new_tail_only(self):
        original = (json.dumps({"id": "old", "text": "a" * 131072}) + "\n").encode()
        self.log.write_bytes(original)
        with writer(self.pack), operation(self.pack, "append fixture") as mutation:
            jsonl.append(self.pack, self.log, [{"id": "new"}])
            entry = mutation.data["files"][0]
            self.assertEqual(entry["before_size"], len(original))
            self.assertEqual(entry["mode"], "append")
            self.assertLess(sum(p.stat().st_size for p in mutation.folder.glob("*.tail")), 1024)
            self.assertFalse(list(mutation.folder.glob("*.before")))
        self.assertTrue(self.log.read_bytes().startswith(original))

    def test_partial_append_process_exit_recovers_exact_original_bytes(self):
        original = b'{ "id": "original" }\r\n'
        self.log.write_bytes(original)
        self.crash('''
import os, sys
from pathlib import Path
from seedbank.durability import operation
from seedbank.pack_lock import writer
pack = Path(sys.argv[1])
file = pack / "mind/fixture.jsonl"
with writer(pack), operation(pack, "torn append") as transaction:
    transaction.prepare_append(file, b'{"id":"unfinished"}\\n')
    with file.open("ab") as output:
        output.write(b'{"id":"un')
        output.flush()
        os.fsync(output.fileno())
    os._exit(86)
''')
        with writer(self.pack) as recovered:
            self.assertEqual(len(recovered), 1)
        self.assertEqual(self.log.read_bytes(), original)
        jsonl.append(self.pack, self.log, [{"id": "after recovery"}])
        self.assertEqual(jsonl.read(self.log)[-1]["id"], "after recovery")

    def test_failed_nested_append_removes_only_nested_records(self):
        jsonl.append(self.pack, self.log, [{"id": "original"}])
        with writer(self.pack), operation(self.pack, "outer"):
            jsonl.append(self.pack, self.log, [{"id": "parent"}])
            with self.assertRaises(ValueError):
                with operation(self.pack, "nested"):
                    jsonl.append(self.pack, self.log, [{"id": "discard"}])
                    raise ValueError("injected")
            self.assertEqual([row["id"] for row in jsonl.read(self.log)], ["original", "parent"])
            jsonl.append(self.pack, self.log, [{"id": "kept"}])
        self.assertEqual([row["id"] for row in jsonl.read(self.log)], ["original", "parent", "kept"])

    def test_outer_rollback_restores_existing_file_and_removes_new_file(self):
        original = b'{"id":"original"}\n'
        self.log.write_bytes(original)
        new_file = self.pack / "mind/new-fixture.jsonl"
        with self.assertRaises(ValueError):
            with writer(self.pack), operation(self.pack, "outer"):
                jsonl.append(self.pack, self.log, [{"id": "discard"}])
                jsonl.append(self.pack, new_file, [{"id": "discard too"}])
                raise ValueError("injected")
        self.assertEqual(self.log.read_bytes(), original)
        self.assertFalse(new_file.exists())
        self.assertEqual([row["id"] for row in jsonl.read(self.log)], ["original"])

    def test_recovery_refuses_external_prefix_or_tail_edits(self):
        for edited in (b'{"id":"external"}\n', b'{"id":"original"}\nunknown tail'):
            with self.subTest(edited=edited):
                # Keep each unresolved recovery in a separate temporary pack.
                folder = tempfile.TemporaryDirectory(prefix="seedbank-external-")
                self.addCleanup(folder.cleanup)
                pack = Path(folder.name) / "fixture.life"
                hatch(pack, ROOT / "eggs/open.egg", "初")
                file = pack / "mind/fixture.jsonl"
                file.write_bytes(b'{"id":"original"}\n')
                with writer(pack):
                    mutation = Mutation(pack.resolve(), "interrupted")
                    mutation.prepare_append(file, b'{"id":"planned"}\n')
                file.write_bytes(edited)
                with self.assertRaises(RecoveryRequired):
                    with writer(pack):
                        pass
                self.assertEqual(file.read_bytes(), edited)
                self.assertTrue((mutation.folder / "manifest.json").exists())

    def test_version_1_pending_replacement_can_still_recover(self):
        self.log.write_bytes(b"original")
        with writer(self.pack):
            mutation = Mutation(self.pack.resolve(), "old runtime")
            mutation.prepare(self.log, b"partial")
            mutation.data["format"] = "seedbank/transaction@1"
            durability._save(mutation.folder, mutation.data)
            replace_bytes(self.log, b"partial")
        with writer(self.pack):
            pass
        self.assertEqual(self.log.read_bytes(), b"original")

    def test_replacement_invalidates_cached_rows_and_append_hints(self):
        jsonl.append(self.pack, self.log, [{"id": "old"}])
        stamp = file_state.stamp(self.log)
        jsonl.append(self.pack, self.log, [{"id": "new"}])
        self.assertEqual(jsonl.changes_since(self.log, stamp), [{"id": "new"}])
        write_file_atomic(self.log, '{"id":"replacement"}\n')
        self.assertIsNone(jsonl.changes_since(self.log, stamp))
        self.assertEqual(jsonl.read(self.log), [{"id": "replacement"}])

    def test_index_updates_known_appends_without_reading_entire_sources(self):
        db = retrieval._connection(self.pack)
        self.addCleanup(db.close)
        retrieval.sync(self.pack, db)
        self.memory("old", "ambermarker")
        experience.record(self.pack, kind="conversation", text="新线索", day=1,
                          source="life/0001-2026-11-01.md", actor="主人")
        # The event ledger was absent on the first sync; index it once.
        retrieval.sync(self.pack, db)
        self.memory("new", "violetmarker", supersedes="old", kind="correction")
        event = experience.record(self.pack, kind="conversation", text="第二条线索", day=1,
                                  source="life/0001-2026-11-01.md", actor="主人")
        with patch.object(retrieval, "read_memories", side_effect=AssertionError("full memories read")), \
                patch.object(experience, "read", side_effect=AssertionError("full experiences read")):
            retrieval.sync(self.pack, db)
        self.assertIsNotNone(db.execute("SELECT id FROM entries WHERE id=?", (event["id"],)).fetchone())
        self.assertEqual(retrieval.search(self.pack, "ambermarker")[0]["memory"]["id"], "new")

    def test_index_forgets_rolled_back_records_and_rebuilds_after_external_edit(self):
        file = self.pack / "mind/memories.jsonl"
        with self.assertRaises(ValueError):
            with writer(self.pack), operation(self.pack, "rollback indexed memory"):
                self.memory("ghost", "ghostmarker")
                self.assertTrue(retrieval.search(self.pack, "ghostmarker"))
                raise ValueError("injected")
        self.assertEqual(retrieval.search(self.pack, "ghostmarker"), [])
        original = read_memories(self.pack)
        write_file_atomic(file, "\n".join(json.dumps(row, ensure_ascii=False) for row in [
            *original, {"id": "external", "day": 1, "text": "externalmarker"}]) + "\n")
        self.assertEqual(retrieval.search(self.pack, "externalmarker")[0]["memory"]["id"], "external")

    def test_old_day_transcript_stops_duplicating_when_event_is_added(self):
        source = "life/0001-2026-11-01.md"
        file = self.pack / source
        write_file_atomic(file, file.read_text(encoding="utf-8") + "\n## 对话\n\n**主人**：oldmarker\n")
        write_file_atomic(self.pack / "life/0002-2026-11-02.md", "# 第 0002 天 · 2026-11-02\n")
        db = retrieval._connection(self.pack)
        self.addCleanup(db.close)
        retrieval.sync(self.pack, db)
        self.assertTrue(any("oldmarker" in row[0] for row in db.execute(
            "SELECT payload FROM entries WHERE source_key=?", (source,))))
        experience.record(self.pack, kind="conversation", text="oldmarker", day=1, source=source, actor="主人")
        retrieval.sync(self.pack, db)
        self.assertFalse(any("oldmarker" in row[0] for row in db.execute(
            "SELECT payload FROM entries WHERE source_key=?", (source,))))

    def test_growth_observations_continue_after_800_records(self):
        offline._append_growth(self.pack, [{"id": str(i)} for i in range(800)])
        offline._append_growth(self.pack, [{"id": "still learning"}])
        self.assertEqual(len(offline.read_growth(self.pack)), 801)
        self.assertEqual(offline.read_growth(self.pack)[-1]["id"], "still learning")


if __name__ == "__main__":
    unittest.main()
