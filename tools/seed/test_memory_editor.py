"""User-run tests for explicit memory revisions. Authored, not executed.

All data is temporary; no model, GUI or real life pack is required.
"""
from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import development, experience, requests
from seedbank.bridge import Bridge
from seedbank.cli import main
from seedbank.cognition import forget_memory, list_memories, visible_memories
from seedbank.memory_editor import history, revise
from seedbank.memory_state import describe
from seedbank.pack import hatch
from seedbank.retrieval import search
from seedbank.util import SeedError, append_memories, read_memories

ROOT = Path(__file__).resolve().parents[2]


class MemoryEditorTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-memory-edit-")
        self.addCleanup(folder.cleanup)
        environment = patch.dict(os.environ, {"HOME": str(Path(folder.name) / "home"),
                                               "USERPROFILE": str(Path(folder.name) / "home"), "SEEDBANK_LANG": "zh_CN"})
        environment.start()
        self.addCleanup(environment.stop)
        self.pack = Path(folder.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="memory-editor",
              born_at_override="2026-11-01T00:00:00Z")
        self.original = {"id": "m_home", "text": "我现在住在杭州。", "day": 1, "kind": "conversation",
                         "at": "2026-11-01T01:00:00Z", "source": "life/0001-2026-11-01.md", "importance": 0.7}
        append_memories(self.pack, [self.original])

    def change(self, **fields):
        return revise(self.pack, "m_home", "我现在住在成都。", reason="刚搬到新家。",
                      change_type="change", **fields)

    def contents(self):
        return {p.relative_to(self.pack).as_posix(): p.read_bytes() for p in self.pack.rglob("*")
                if p.is_file() and not p.relative_to(self.pack).as_posix().startswith(
                    ("mind/requests/", "mind/.transactions/", "mind/search.sqlite3", "mind/.writer.lock"))}

    def test_user_change_retains_original_and_has_distinct_source_and_effective_date(self):
        before = (self.pack / "mind/memories.jsonl").read_bytes()
        result = self.change(effective_on="2026-10-31")
        row = result["memory"]
        self.assertTrue((self.pack / "mind/memories.jsonl").read_bytes().startswith(before))
        self.assertEqual(row["supersedes"], "m_home")
        self.assertEqual(row["claim_id"], "m_home")
        self.assertEqual(row["effective_on"], "2026-10-31")
        event = next(e for e in experience.read(self.pack) if e["id"] == row["event_ids"][0])
        self.assertEqual(event["kind"], "memory_revision")
        self.assertEqual(event["actor"], "用户")
        self.assertEqual(event["metadata"]["reason"], "刚搬到新家。")
        self.assertEqual(row["generation"]["origin"], "user")
        self.assertEqual(row["generation"]["model"], "")
        detail = history(self.pack, "m_home")
        self.assertEqual([r["id"] for r in detail["versions"]], ["m_home", row["id"]])
        self.assertEqual(detail["current"]["id"], row["id"])
        self.assertFalse(detail["selected"]["can_revise"])
        self.assertTrue(history(self.pack, row["id"])["evidence"])
        self.assertEqual(next(m for m in read_memories(self.pack) if m["id"] == "m_home"), self.original)

    def test_correcting_an_error_is_distinct_from_a_change_in_historical_recall(self):
        row = revise(self.pack, "m_home", "我一直住在成都。", reason="上次写错城市了。", request_id="correct")["memory"]
        current = search(self.pack, "杭州", k=20)
        self.assertNotIn("m_home", [r["memory"]["id"] for r in current])
        past = next(r["memory"] for r in search(self.pack, "杭州", k=20, historical=True) if r["memory"]["id"] == "m_home")
        self.assertEqual(past["superseded_reason"], "correction")
        self.assertIn("原先说法有误", describe(past))
        self.assertIn("不表示此前曾为真", describe(row))

    def test_unknown_change_date_is_not_invented_from_save_time(self):
        row = self.change()["memory"]
        self.assertEqual(row["effective_on"], "")
        self.assertIn("变化日期未注明", describe(row))
        self.assertEqual(row["recorded_at"], row["at"])

    def test_invalid_and_future_dates_empty_reason_and_oversize_are_rejected_before_writes(self):
        before = self.contents()
        invalid = [dict(text="新内容", reason=""), dict(text="x" * 1001, reason="说明"),
                   dict(text="新内容", reason="x" * 501),
                   dict(text="新内容", reason="说明", change_type="change", effective_on="2026-02-30"),
                   dict(text="新内容", reason="说明", change_type="change", effective_on=(date.today() + timedelta(days=1)).isoformat()),
                   dict(text="新内容", reason="说明", effective_on="2026-01-01")]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(SeedError):
                revise(self.pack, "m_home", **fields)
        self.assertEqual(self.contents(), before)
        self.assertEqual(requests.pending(self.pack), [])

    def test_committed_request_can_be_replayed_without_duplicate_event_or_revision(self):
        first = self.change(request_id="same-edit")
        before = self.contents()
        repeated = self.change(request_id="same-edit")
        self.assertTrue(repeated["replayed"])
        self.assertEqual(first["memory"], repeated["memory"])
        self.assertEqual(self.contents(), before)
        with self.assertRaises(SeedError):
            revise(self.pack, "m_home", "别的内容", reason="不同修改", request_id="same-edit")

    def test_stale_target_is_rejected_without_overwriting_newer_revision(self):
        first = self.change()["memory"]
        before = self.contents()
        with self.assertRaises(SeedError):
            revise(self.pack, "m_home", "我住在北京。", reason="旧界面中的修改")
        self.assertEqual(self.contents(), before)
        self.assertEqual(requests.pending(self.pack), [])
        second = revise(self.pack, first["id"], "我住在西安。", reason="又搬家了。", change_type="change")["memory"]
        self.assertEqual(second["claim_id"], "m_home")
        self.assertEqual(len(history(self.pack, second["id"])["versions"]), 3)

    def test_failure_rolls_back_event_and_memory_but_preserves_input_for_explicit_resume(self):
        before = self.contents()
        with patch("seedbank.cognition._append_journal", side_effect=OSError("injected failure")):
            with self.assertRaises(OSError):
                self.change(request_id="unfinished-edit")
        self.assertEqual(self.contents(), before)
        self.assertEqual(history(self.pack, "m_home")["pending"][0]["payload"]["text"], "我现在住在成都。")
        with patch("seedbank.bridge.create_brain", side_effect=AssertionError("no model call")):
            result = Bridge(self.pack).handle({"op": "resume", "request_id": "unfinished-edit"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(requests.pending(self.pack), [])
        self.assertEqual(len(history(self.pack, result["memory"]["id"])["versions"]), 2)

    def test_forgotten_versions_remain_auditable_but_cannot_be_revised_or_recalled(self):
        row = self.change()["memory"]
        forget_memory(self.pack, row["id"])
        detail = history(self.pack, row["id"])
        self.assertEqual(len(detail["versions"]), 2)
        self.assertEqual(detail["current"], {})
        self.assertFalse(detail["selected"]["can_revise"])
        self.assertNotIn(row["id"], [m["id"] for m in visible_memories(self.pack)])
        self.assertEqual(search(self.pack, "成都", historical=True), [])
        with self.assertRaises(SeedError):
            revise(self.pack, row["id"], "我住在西安。", reason="不能借修改恢复已放下内容")

    def test_revised_evidence_does_not_silently_rewrite_identity_or_keep_unsupported_belief(self):
        before_identity = (self.pack / "genome/identity.md").read_bytes()
        development.apply_proposals(self.pack, {"beliefs": [{"text": "用户住在杭州", "confidence": 0.8,
                                    "reason": "引用他的介绍", "evidence": ["m_home"]}]},
                                    day=1, source=self.original["source"], runner="fixture", memories=[self.original])
        self.assertTrue(development.summary(self.pack)["beliefs"])
        self.change()
        self.assertEqual(development.summary(self.pack)["beliefs"], [])
        self.assertEqual((self.pack / "genome/identity.md").read_bytes(), before_identity)

    def test_bridge_keeps_target_id_separate_from_response_id_and_returns_provenance(self):
        with patch("seedbank.bridge.create_brain", side_effect=AssertionError("no model call")):
            bridge = Bridge(self.pack)
            result = bridge.handle({"op": "memories", "action": "revise", "memory_id": "m_home",
                                    "id": "response-id", "request_id": "edit-id", "text": "我住在成都。", "reason": "说明"})
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["id"], "response-id")
            self.assertEqual(result["requestId"], "edit-id")
            found = bridge.handle({"op": "recall", "query": "成都"})["memories"][0]
            self.assertTrue(found["source"])
            self.assertIn("用户提供", found["provenance"])
            detail = bridge.handle({"op": "memories", "action": "history", "memory_id": "m_home", "id": "inspect"})
            self.assertEqual(detail["history"]["selected"]["id"], "m_home")
            self.assertEqual(detail["id"], "inspect")

    def test_cli_revise_and_history_return_the_same_version_chain(self):
        output = StringIO()
        with redirect_stdout(output):
            status = main(["revise", str(self.pack), "m_home", "--text", "我住在成都。", "--reason", "纠正记录"])
        self.assertEqual(status, 0)
        identifier = json.loads(output.getvalue())["memory"]["id"]
        output = StringIO()
        with redirect_stdout(output):
            status = main(["memory-history", str(self.pack), identifier])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["current"]["id"], identifier)


if __name__ == "__main__":
    unittest.main()
