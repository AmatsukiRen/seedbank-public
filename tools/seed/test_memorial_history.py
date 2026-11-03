"""User-run history and legacy-export regressions. Authored, not executed."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import backup, cognition, friends, memorial
from seedbank.bridge import Bridge
from seedbank.pack import hatch, check
from seedbank.util import SeedError, list_days, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class MemorialHistoryTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-memorial-history-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        environment = patch.dict(os.environ, {"HOME": str(self.folder / "home"),
            "USERPROFILE": str(self.folder / "home"), "SEEDBANK_LANG": "zh_CN"})
        environment.start()
        self.addCleanup(environment.stop)
        network = patch("seedbank.semantic._request", side_effect=AssertionError("No real service"))
        network.start()
        self.addCleanup(network.stop)
        self.pack = self.folder / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="memorial-history",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = cognition.open_day(self.pack)
        self.file = memorial.memorial_path(self.pack)

    def long_history(self, count=80):
        return {"format": memorial.MEMORIAL_FORMAT, "extension": {"retained": True},
            "anniversaries": [{"name": f"日子 {n}", "day": n, "kind": "custom", "note": "",
                               "created_at": "old", "extra": n} for n in range(count)],
            "regrets": [{"text": f"遗憾 {n}", "day": n, "resolved_day": None, "created_at": "old",
                         "extra": n} for n in range(count)],
            "farewells": [{"name": f"告别 {n}", "day": n, "kind": "goodbye", "note": "原来的记录",
                           "at": "old", "extra": n} for n in range(count)],
            "missing": [{"days": 1, "at": "old", "extra": n} for n in range(count)]}

    def test_old_limits_do_not_discard_or_reject_new_life_records(self):
        data = self.long_history()
        write_json_atomic(self.file, data)
        before = self.file.read_bytes()
        loaded = memorial.load_memorial(self.pack)
        self.assertEqual(self.file.read_bytes(), before)
        memorial.add_anniversary(self.pack, "继续记住", day=81)
        regret = memorial.add_regret(self.pack, "继续记录", day=81)
        farewell = memorial.add_farewell(self.pack, "之后的告别", day=81)
        memorial.note_missing(self.pack, 2)
        after = memorial.load_memorial(self.pack)
        for key in ("anniversaries", "regrets", "farewells", "missing"):
            self.assertEqual(after[key][:80], loaded[key])
            self.assertEqual(len(after[key]), 81)
        self.assertEqual(regret["index"], 81)
        self.assertEqual(after["farewells"][-1], farewell)
        self.assertEqual(after["extension"], data["extension"])
        summary = memorial.memorial_summary(self.pack, 81)
        self.assertEqual((summary["regret_count"], summary["farewell_count"], summary["missing_days"]), (81, 81, 82))
        self.assertEqual(len(summary["regrets"]), 3)
        self.assertEqual(len(summary["farewells"]), 3)

    def test_read_and_unrelated_write_preserve_duplicates_text_and_unknown_dates(self):
        data = self.long_history(2)
        data["regrets"][1]["text"] = data["regrets"][0]["text"] = "原始长记录" * 40
        data["anniversaries"][1]["name"] = data["anniversaries"][0]["name"]
        del data["regrets"][0]["created_at"]
        del data["farewells"][0]["at"]
        write_json_atomic(self.file, data)
        before = self.file.read_bytes()
        first, second = memorial.load_memorial(self.pack), memorial.load_memorial(self.pack)
        self.assertEqual(first, second)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertNotIn("created_at", first["regrets"][0])
        self.assertNotIn("at", first["farewells"][0])
        memorial.add_farewell(self.pack, "新的告别")
        after = memorial.load_memorial(self.pack)
        self.assertEqual(after["regrets"], data["regrets"])
        self.assertEqual(after["anniversaries"], data["anniversaries"])
        self.assertEqual(after["farewells"][:2], data["farewells"])

    def test_display_indices_stay_bound_to_full_history_after_resolving(self):
        for text in ("第一件", "第二件", "第三件"):
            memorial.add_regret(self.pack, text, day=1)
        memorial.resolve_regret(self.pack, 1, day=2)
        self.assertEqual([r["index"] for r in memorial.open_regrets(self.pack)], [2, 3])
        shown = "\n".join(memorial.describe_memorial(self.pack))
        self.assertIn("#2 第二件", shown)
        self.assertIn("#3 第三件", shown)
        self.assertNotIn("#1 第二件", shown)
        memorial.resolve_regret(self.pack, "2", day=2)
        self.assertEqual([r["text"] for r in memorial.open_regrets(self.pack)], ["第三件"])
        self.assertEqual(len(memorial.load_memorial(self.pack)["regrets"]), 3)

    def test_invalid_indices_and_earlier_resolution_cannot_change_history(self):
        memorial.add_regret(self.pack, "保留这件事", day=5)
        before = self.file.read_bytes()
        for index in (0, -1, True, False, 1.5, "1.5", "", None, 2):
            with self.subTest(index=index), self.assertRaises(SeedError):
                memorial.resolve_regret(self.pack, index, day=5)
            self.assertEqual(self.file.read_bytes(), before)
        with self.assertRaises(SeedError):
            memorial.resolve_regret(self.pack, 1, day=4)
        self.assertEqual(self.file.read_bytes(), before)
        bridge = Bridge(self.pack, "stub")
        for value in (0, False, 1.5):
            result = bridge.handle({"op": "memorial", "action": "resolve", "index": value, "day": 5})
            self.assertFalse(result["ok"])
            self.assertEqual(self.file.read_bytes(), before)

    def test_invalid_rows_block_unrelated_writes_and_pack_check_without_replacing_file(self):
        cases = [None, [], {"format": "unknown"}, {"farewells": "broken"}, {"missing": None},
                 {"farewells": [{"name": "旧记录", "day": -1}]}, {"regrets": [{"text": "旧记录", "day": True}]},
                 {"regrets": [{"text": "旧记录", "resolved_day": "bad"}]}, {"missing": [{"days": 0}]}]
        for data in cases:
            self.file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            before = self.file.read_bytes()
            with self.subTest(data=data):
                with self.assertRaises(SeedError):
                    memorial.add_farewell(self.pack, "不应保存")
                with redirect_stdout(StringIO()), self.assertRaises(SeedError):
                    check(self.pack)
                self.assertEqual(self.file.read_bytes(), before)
        self.file.write_bytes(b'{"regrets":')
        with self.assertRaises(SeedError):
            memorial.add_regret(self.pack, "不应覆盖")
        self.assertEqual(self.file.read_bytes(), b'{"regrets":')

    def test_legacy_missing_total_remains_without_an_invented_timestamp(self):
        write_json_atomic(self.file, {"missing_days": 9})
        self.assertEqual(memorial.total_missing_days(self.pack), 9)
        memorial.note_missing(self.pack, 2)
        memorial.note_missing(self.pack, 3)
        data = memorial.load_memorial(self.pack)
        self.assertEqual(memorial.total_missing_days(self.pack), 14)
        self.assertEqual(data["missing"][0], {"days": 9, "at": "", "basis": "legacy_total"})
        self.assertEqual(data["missing_days"], 9)
        shown = "\n".join(memorial.describe_memorial(self.pack))
        self.assertIn("期间经历未知", shown)
        self.assertNotIn("睡过去", shown)

    def test_summary_reuses_one_read_and_keeps_recent_projection_separate(self):
        write_json_atomic(self.file, self.long_history())
        with patch.object(memorial, "load_memorial", wraps=memorial.load_memorial) as reads:
            result = memorial.memorial_summary(self.pack)
        self.assertEqual(reads.call_count, 1)
        self.assertEqual([r["index"] for r in result["regrets"]], [78, 79, 80])
        self.assertEqual(len(memorial.load_memorial(self.pack)["regrets"]), 80)

    def test_mourn_failure_rolls_back_friend_farewell_memory_and_journal(self):
        friends.record_visit(self.pack, name="同伴", day=self.day["dayNo"])
        files = [friends.friends_path(self.pack), self.file, self.pack / "mind/memories.jsonl", self.pack / "journal/loop.jsonl"]
        before = {p: p.read_bytes() if p.exists() else None for p in files}
        with patch.object(cognition, "_append_journal", side_effect=OSError("fixture save interrupted")):
            with self.assertRaises(OSError):
                cognition.mourn(self.pack, "同伴", day=self.day)
        self.assertEqual({p: p.read_bytes() if p.exists() else None for p in files}, before)
        cognition.mourn(self.pack, "同伴", day=self.day)
        self.assertEqual(friends.list_friends(self.pack)[0]["status"], "lost")
        self.assertEqual(len(memorial.farewells_of(self.pack)), 1)

    def test_full_history_survives_backup_and_restore(self):
        write_json_atomic(self.file, self.long_history())
        before = self.file.read_bytes()
        saved = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(memorial.memorial_path(restored).read_bytes(), before)
        self.assertEqual(len(memorial.farewells_of(restored)), 80)

    def test_legacy_export_does_not_invent_gender_species_death_or_authorship(self):
        memorial.add_regret(self.pack, "尚未说清楚的事", day=1)
        birth = (self.pack / "birth.json").read_bytes()
        pages = {p["file"]: (self.pack / "life" / p["file"]).read_bytes() for p in list_days(self.pack)}
        result = cognition.legacy_letter(self.pack)
        self.assertEqual(Path(result["path"]).read_text(encoding="utf-8"), result["text"])
        self.assertIn("运行器根据已有记录整理", result["text"])
        self.assertIn("私人档案摘要", result["text"])
        self.assertIn("#1 尚未说清楚的事", result["text"])
        for unsupported in ("她是一只", "她不在了以后", "一生是公开可读", "'resolved_day'"):
            self.assertNotIn(unsupported, result["text"])
        self.assertEqual((self.pack / "birth.json").read_bytes(), birth)
        self.assertEqual({p["file"]: (self.pack / "life" / p["file"]).read_bytes() for p in list_days(self.pack)}, pages)

    def test_legacy_uses_numeric_page_order_and_skips_unwritten_latest_diary(self):
        for number, date, text in ((9999, "2053-12-31", "OLDER_DIARY"), (10000, "2054-01-01", "LATEST_DIARY"),
                                   (10001, "2054-01-02", "")):
            file = self.pack / "life" / f"{number:04d}-{date}.md"
            file.write_text(f"# 第 {number} 天 · {date}\n" + ("\n## 今天\n\n" + text + "\n" if text else ""), encoding="utf-8")
        (self.pack / "life/unrelated.md").write_text("## 今天\n\nNOT_A_DAY", encoding="utf-8")
        result = cognition.legacy_letter(self.pack, out=self.folder / "private-summary.md")
        self.assertIn("LATEST_DIARY", result["text"])
        self.assertNotIn("OLDER_DIARY", result["text"])
        self.assertNotIn("NOT_A_DAY", result["text"])
        self.assertIn("life/10000-2054-01-01.md", result["text"])
        self.assertEqual(result["days"], len(list_days(self.pack)))


if __name__ == "__main__":
    unittest.main()
