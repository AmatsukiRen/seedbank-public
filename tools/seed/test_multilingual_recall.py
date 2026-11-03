"""Offline local recall regressions with isolated archives and no service calls."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import unicodedata
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import disclosure, experience, facts, life_story, retrieval
from seedbank.cognition import forget_memory, start_day
from seedbank.memory_state import revise_memory
from seedbank.pack import hatch
from seedbank.util import append_memories, write_file_atomic

ROOT = Path(__file__).resolve().parents[2]


class RecallTermsTest(unittest.TestCase):
    def test_han_english_and_identifier_matching_is_preserved(self):
        terms = retrieval.tokens("丹顶鹤 Blue_ID_42 BLUE_ID_42")
        self.assertTrue({"丹顶", "顶鹤", "丹顶鹤", "blue_id_42"} <= set(terms))
        self.assertEqual(terms.count("blue_id_42"), 1)

    def test_kana_and_hangul_are_not_empty_or_absorbed_by_latin_words(self):
        for text, expected in (
            ("ほたる", {"ほた", "たる", "ほたる"}),
            ("메모리", {"메모", "모리", "메모리"}),
            ("SEEDbankメモリ", {"seedbank", "メモ", "モリ", "メモリ"}),
            ("SEEDbank메모리", {"seedbank", "메모", "모리", "메모리"}),
        ):
            with self.subTest(text=text):
                self.assertTrue(expected <= set(retrieval.tokens(text)))

    def test_width_and_canonical_composition_match_without_dropping_accents(self):
        for first, second in (("ＳＥＥＤｂａｎｋ４２", "seedbank42"),
                              ("ｶﾞｰﾃﾞﾝ", "ガーデン"),
                              (unicodedata.normalize("NFD", "기억"), "기억"),
                              ("CAFE\u0301", "café")):
            with self.subTest(first=first):
                self.assertEqual(retrieval.tokens(first), retrieval.tokens(second))
        self.assertNotEqual(retrieval.tokens("café"), retrieval.tokens("cafe"))
        self.assertEqual(retrieval.tokens("Straße"), ["strasse"])

    def test_punctuation_does_not_join_words_or_create_search_terms(self):
        self.assertEqual(retrieval.tokens("✨…！？ ()"), [])
        self.assertEqual(retrieval.tokens("café, tea"), ["café", "tea"])
        self.assertNotIn("るこ", retrieval.tokens("ほたる、ことり"))


class MultilingualRecallTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-unicode-recall-")
        self.addCleanup(folder.cleanup)
        self.pack = Path(folder.name) / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="unicode-recall",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("No network"))
        guard.start()
        self.addCleanup(guard.stop)

    def event(self, text, **extra):
        return experience.record(self.pack, kind="conversation", text=text,
                                 actor="user", day=self.day["dayNo"],
                                 source=self.day["file"], **extra)

    def memory(self, identifier, text):
        row = {"id": identifier, "text": text, "day": self.day["dayNo"],
               "at": self.day["date"] + "T00:00:00Z", "kind": "thought",
               "source": self.day["file"], "importance": .6, "runner": "fixture"}
        append_memories(self.pack, [row])
        return row

    def recall(self, query, **kwargs):
        return retrieval.search(self.pack, query, 50, use_semantic=False, **kwargs)

    def test_indexed_original_events_are_found_in_all_four_ui_languages(self):
        for query, text in (("丹顶鹤", "北坡有两只丹顶鹤。"),
                            ("garden", "We visited the garden."),
                            ("ほたる", "きのう、ほたるをみました。"),
                            ("푸른등대", "어제 푸른등대를 보았어요."),
                            ("ｶﾞｰﾃﾞﾝ", "ガーデンで会いましょう。"),
                            ("cafe\u0301", "Nous avons visité le café.")):
            with self.subTest(query=query):
                original = self.event(text)
                before = experience.path(self.pack).read_bytes()
                found = next(r["memory"] for r in self.recall(query) if r["memory"]["id"] == original["id"])
                self.assertIn(text, found["text"])
                self.assertEqual(found["source"], experience.source_of(original))
                self.assertEqual(experience.path(self.pack).read_bytes(), before)
        self.assertEqual(self.recall("✨…！？"), [])

    def test_unextracted_legacy_diary_can_be_recalled_without_rewriting_it(self):
        file = self.pack / self.day["file"]
        write_file_atomic(file, file.read_text(encoding="utf-8") + "\n## 对话\n\n**主人**：ソラネコと約束しました。\n")
        before = file.read_bytes()
        found = self.recall("ソラネコ")
        self.assertTrue(any(r["memory"].get("origin") == "legacy_archive" for r in found))
        self.assertEqual(file.read_bytes(), before)

    def test_single_cjk_query_finds_characters_inside_words_without_broadening_long_queries(self):
        for query, text in (("光", "今晚准备看看月光"), ("る", "ほたるを見ました"), ("달", "내일달빛을봐요")):
            with self.subTest(query=query):
                original = self.event(text)
                self.assertIn(original["id"], {r["memory"]["id"] for r in self.recall(query)})
        unrelated = self.event("月台和风光")
        self.assertNotIn(unrelated["id"], {r["memory"]["id"] for r in self.recall("月光")})
        latin = self.event("garden")
        self.assertNotIn(latin["id"], {r["memory"]["id"] for r in self.recall("e")})

    def test_single_cjk_query_rebuilds_v6_cache_and_matches_raw_fallback(self):
        original = self.event("今晚的月光")
        self.recall("月光")
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db, db:
            db.execute("UPDATE metadata SET value='6' WHERE key='version'")
            db.execute("DELETE FROM terms WHERE length(token)=1")
        before = experience.path(self.pack).read_bytes()
        self.assertIn(original["id"], {r["memory"]["id"] for r in self.recall("光")})
        with patch.object(retrieval, "_connection", side_effect=sqlite3.DatabaseError("fixture")):
            self.assertIn(original["id"], {r["memory"]["id"] for r in self.recall("光")})
        self.assertEqual(experience.path(self.pack).read_bytes(), before)

    def test_single_cjk_query_preserves_revision_and_forgetting(self):
        old = self.memory("m_light", "月光")
        current = revise_memory(self.pack, old["id"], "阳光", reason="明确更正", day=self.day["dayNo"],
                                source=self.day["file"], runner="fixture")
        found = {r["memory"]["id"] for r in self.recall("月")}
        self.assertIn(current["id"], found)
        self.assertNotIn(old["id"], found)
        forget_memory(self.pack, current["id"])
        self.assertEqual(self.recall("月"), [])

    def test_single_cjk_query_preserves_audience_rules(self):
        # Use a fresh archive: forgetting an unanchored legacy memory above
        # deliberately suppresses its whole day source, regardless of audience.
        private = self.event("月色 PRIVATE", metadata=disclosure.stamp("owner"))
        public = self.event("月色 PUBLIC", metadata=disclosure.stamp("qq-group:123"))
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        found = {r["memory"]["id"] for r in self.recall("月", policy=policy)}
        self.assertIn(public["id"], found)
        self.assertNotIn(private["id"], found)

    def test_v4_cache_is_rebuilt_even_when_original_source_stamps_match(self):
        original = self.event("비밀등대에서 만났어요.")
        self.assertTrue(self.recall("비밀등대"))
        index = self.pack / "mind/search.sqlite3"
        with closing(sqlite3.connect(index)) as db, db:
            db.execute("UPDATE metadata SET value='4' WHERE key='version'")
            # Simulate a legacy cache with no Hangul terms but current stamps.
            db.execute("DELETE FROM terms")
        before = experience.path(self.pack).read_bytes()
        self.assertIn(original["id"], {r["memory"]["id"] for r in self.recall("비밀등대")})
        with closing(sqlite3.connect(index)) as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0], retrieval.VERSION)
            self.assertIsNotNone(db.execute("SELECT 1 FROM terms WHERE token='비밀'").fetchone())
        self.assertEqual(experience.path(self.pack).read_bytes(), before)

    def test_corrupt_index_fallback_uses_the_same_unicode_matching(self):
        original = self.event("ソラネコと約束しました。")
        self.memory("m_korean", "푸른등대를 기억해요.")
        index = self.pack / "mind/search.sqlite3"
        index.write_bytes(b"not a sqlite database")
        before = experience.path(self.pack).read_bytes()
        self.assertIn(original["id"], {r["memory"]["id"] for r in self.recall("ソラネコ")})
        self.assertIn("m_korean", {r["memory"]["id"] for r in self.recall("푸른등대")})
        self.assertEqual(experience.path(self.pack).read_bytes(), before)

    def test_normalized_query_still_obeys_forgetting(self):
        original = self.memory("m_width", "ＳＥＥＤｂａｎｋ４２")
        self.assertTrue(self.recall("seedbank42"))
        forget_memory(self.pack, original["id"])
        before = (self.pack / "mind/memories.jsonl").read_bytes()
        self.assertEqual(self.recall("ＳＥＥＤｂａｎｋ４２"), [])
        self.assertEqual(self.recall("seedbank42"), [])
        self.assertEqual((self.pack / "mind/memories.jsonl").read_bytes(), before)

    def test_korean_old_word_finds_current_revision_without_reviving_original(self):
        original = self.memory("m_previous", "비밀등대")
        self.assertTrue(self.recall("비밀등대"))
        current = revise_memory(self.pack, original["id"], "새로운약속", reason="明确更正",
                                day=self.day["dayNo"], source=self.day["file"], runner="fixture")
        identifiers = {r["memory"]["id"] for r in self.recall("비밀등대")}
        self.assertIn(current["id"], identifiers)
        self.assertNotIn(original["id"], identifiers)
        historical = self.recall("비밀등대", historical=True)
        self.assertIn(original["id"], {r["memory"]["id"] for r in historical})

    def test_rebuilt_index_does_not_disclose_private_korean_records(self):
        private = self.event("푸른등대 PRIVATE_DETAIL", metadata=disclosure.stamp("owner"))
        public = self.event("푸른등대 SHARED_DETAIL", metadata=disclosure.stamp("qq-group:123"))
        self.recall("푸른등대")
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db, db:
            db.execute("UPDATE metadata SET value='4' WHERE key='version'")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        rows = self.recall("푸른등대", policy=policy)
        identifiers = {r["memory"]["id"] for r in rows}
        self.assertIn(public["id"], identifiers)
        self.assertNotIn(private["id"], identifiers)
        self.assertFalse(any("PRIVATE_DETAIL" in r["memory"]["text"] for r in rows))

    def test_korean_single_claim_context_keeps_disagreements(self):
        for value in ("서울", "부산"):
            facts.perform(self.pack, "add", {"subject": "owner", "aspect": "주소", "value": value})
        view = facts.context(self.pack, "주소")
        group = next(g for g in view["groups"] if g["aspect"] == "주소")
        self.assertEqual(group["status"], "conflict")
        self.assertEqual({r["value"] for r in group["claims"]}, {"서울", "부산"})

    def test_kana_query_prioritizes_an_older_life_chapter(self):
        original = self.event("ソラネコとの思い出")
        target = None
        for index, title in enumerate(("ソラネコ", "hiking", "painting", "reading", "music", "cooking", "travel")):
            with patch("seedbank.life_story.now_iso", return_value=f"2026-11-01T00:00:{index:02d}Z"):
                row = life_story.perform(self.pack, "save", {
                    "kind": "chapter", "title": title, "interpretation": "我对这段经历的理解。",
                    "change": "开始尝试理解。", "question": "仍然有问题。", "status": "open",
                    "reason": "依据这段记录整理", "target": "", "expected": "",
                    "anchors": [{"id": original["id"], "quote": original["text"], "hash": life_story._digest(original)}],
                })["record"]
            if title == "ソラネコ":
                target = row["id"]
        self.assertEqual(life_story.context(self.pack, "ソラネコ")["chapters"][0]["id"], target)


if __name__ == "__main__":
    unittest.main()
