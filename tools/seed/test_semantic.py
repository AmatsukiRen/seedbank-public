"""User-run hybrid retrieval tests. Fake embeddings only; authored, not executed."""
from contextlib import redirect_stdout, nullcontext
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import semantic
from seedbank.brain import StubBrain
from seedbank.cognition import chat_turn, forget_memory
from seedbank.memory_editor import revise
from seedbank.pack import hatch
from seedbank.retrieval import _connection, search
from seedbank.settings import load_settings, save_settings
from seedbank.util import append_memories, read_json

ROOT = Path(__file__).resolve().parents[2]


class SemanticTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="seedbank-semantic-")
        self.addCleanup(folder.cleanup)
        home = str(Path(folder.name) / "home")
        env = patch.dict(os.environ, {"HOME": home, "USERPROFILE": home, "SEEDBANK_LANG": "zh_CN"})
        env.start()
        self.addCleanup(env.stop)
        self.pack = Path(folder.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="semantic",
              born_at_override="2026-11-01T00:00:00Z")
        self.add("m_lonely", "离开熟悉的伙伴以后，我觉得很孤单。")
        self.sent = []

    def add(self, identifier, text, at="2026-11-01T01:00:00Z"):
        append_memories(self.pack, [{"id": identifier, "text": text, "day": 1,
                                     "at": at, "kind": "conversation", "importance": .6,
                                     "source": "life/0001-2026-11-01.md"}])

    def enable(self, **fields):
        return semantic.configure(self.pack, {"enabled": True, "model": "test-embed",
                                               "min_similarity": .8, **fields})

    def fake(self, cfg, texts):
        self.sent.extend(texts)
        rows = []
        for index, text in enumerate(texts):
            if "孤单" in text or "分别" in text:
                vector = [1, 0, 0]
            elif "保修编号" in text:
                vector = [0, 0, 1]
            else:
                vector = [0, 1, 0]
            rows.append({"index": index, "embedding": vector})
        # Real services may reorder rows. Index, not arrival order, associates them.
        return {"data": list(reversed(rows)), "model": "test-embed-resolved"}

    def test_disabled_and_status_do_not_send_anything(self):
        before = (self.pack / "mind/memories.jsonl").read_bytes()
        with patch("seedbank.semantic._request") as request:
            search(self.pack, "分别让你难受了吗？")
            status = semantic.manage(self.pack)
        request.assert_not_called()
        self.assertFalse(status["enabled"])
        self.assertGreater(status["pending_chunks"], 0)
        self.assertEqual((self.pack / "mind/memories.jsonl").read_bytes(), before)
        self.assertFalse((self.pack / "mind/semantic.json").exists())

    def test_paraphrase_without_lexical_overlap_reaches_original_record(self):
        query = "分别让你难受了吗？"
        self.assertEqual(search(self.pack, query, use_semantic=False), [])
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            rows = search(self.pack, query)
        self.assertEqual(rows[0]["memory"]["id"], "m_lonely")
        self.assertEqual(rows[0]["memory"]["text"], "离开熟悉的伙伴以后，我觉得很孤单。")
        self.assertGreater(rows[0]["parts"]["semantic_similarity"], .99)
        self.assertEqual(semantic.last_status(self.pack)["state"], "hybrid")

    def test_zero_semantic_matches_is_allowed(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            self.assertEqual(search(self.pack, "保修编号"), [])

    def test_query_vectors_are_reused_but_records_are_checked_again(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            first = search(self.pack, "分别让你难受了吗？")
            calls = len(self.sent)
            second = search(self.pack, "分别让你难受了吗？")
        self.assertEqual(first, second)
        self.assertEqual(len(self.sent), calls)

    def test_forgotten_record_is_not_embedded_or_recalled_after_forgetting(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            search(self.pack, "分别让你难受了吗？")
            forget_memory(self.pack, "m_lonely", reason="放下")
            self.sent.clear()
            rows = search(self.pack, "分别让你难受了吗？")
        self.assertNotIn("m_lonely", [r["memory"]["id"] for r in rows])
        self.assertFalse(any("孤单" in text for text in self.sent))

    def test_revision_remains_current_and_history_is_explicit(self):
        self.enable()
        updated = revise(self.pack, "m_lonely", "我不再因为分别觉得孤单。", reason="交到了新朋友", change_type="change")["memory"]
        with patch("seedbank.semantic._request", side_effect=self.fake):
            current = search(self.pack, "分别让你难受了吗？")
            history = search(self.pack, "分别让你难受了吗？", historical=True)
        self.assertNotIn("m_lonely", [r["memory"]["id"] for r in current])
        self.assertIn(updated["id"], [r["memory"]["id"] for r in current])
        old = next(r["memory"] for r in history if r["memory"]["id"] == "m_lonely")
        self.assertEqual(old["superseded_by"], updated["id"])

    def test_date_filter_applies_to_semantic_candidates(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            rows = search(self.pack, "分别让你难受了吗？", date_from="2026-11-02")
        self.assertNotIn("m_lonely", [r["memory"]["id"] for r in rows])

    def test_failure_preserves_lexical_results_and_stops_repeated_requests_briefly(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=semantic.SemanticError("fixture unavailable")) as request:
            first = search(self.pack, "孤单")
            second = search(self.pack, "孤单")
        self.assertIn("m_lonely", [r["memory"]["id"] for r in first])
        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(semantic.last_status(self.pack)["state"], "lexical_fallback")

    def test_stub_chat_stays_offline_even_with_semantic_config_enabled(self):
        self.enable()
        with patch("seedbank.semantic._request") as request:
            chat_turn(self.pack, "分别让你难受了吗？", StubBrain())
        request.assert_not_called()

    def test_batch_cap_resume_and_cache_clear_keep_original_bytes(self):
        for number in range(75):
            self.add("many_" + str(number), "不同的旧记录 " + str(number))
        self.enable()
        original = (self.pack / "mind/memories.jsonl").read_bytes()
        with patch("seedbank.semantic._request", side_effect=self.fake) as request:
            first = semantic.manage(self.pack, "index")
            self.assertEqual(len(request.call_args.args[1]), 64)
            self.assertGreater(first["pending_chunks"], 0)
            second = semantic.manage(self.pack, "index")
        self.assertEqual(second["pending_chunks"], 0)
        with patch("seedbank.semantic._request") as request:
            cleared = semantic.manage(self.pack, "clear")
        request.assert_not_called()
        self.assertEqual(cleared["indexed_chunks"], 0)
        self.assertEqual((self.pack / "mind/memories.jsonl").read_bytes(), original)

    def test_changed_vector_space_is_not_mixed_and_revision_gets_new_space(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            search(self.pack, "分别让你难受了吗？")

        def changed(cfg, texts):
            return {"model": "same-name-new-version", "data": [
                {"index": i, "embedding": [1, 0, 0, 0]} for i, _ in enumerate(texts)]}

        with patch("seedbank.semantic._request", side_effect=changed):
            search(self.pack, "分别以后呢？")
            self.assertEqual(semantic.last_status(self.pack)["state"], "lexical_fallback")
            self.enable(revision="2")
            result = search(self.pack, "分别以后呢？")
        self.assertTrue(result)
        self.assertEqual(semantic.last_status(self.pack)["state"], "hybrid")

    def test_corrupt_vector_falls_back_without_modifying_source(self):
        self.enable()
        with patch("seedbank.semantic._request", side_effect=self.fake):
            search(self.pack, "分别让你难受了吗？")
            db = _connection(self.pack)
            try:
                with db:
                    db.execute("UPDATE semantic_vectors SET checksum='damaged'")
            finally:
                db.close()
            rows = search(self.pack, "孤单")
        self.assertIn("m_lonely", [r["memory"]["id"] for r in rows])
        self.assertEqual(semantic.last_status(self.pack)["state"], "lexical_fallback")

    def test_response_index_shape_and_nonfinite_vectors_are_rejected(self):
        cfg = self.enable()
        payloads = [
            {"model": "test", "data": [{"index": 0, "embedding": [1, 0]}, {"index": 0, "embedding": [0, 1]}]},
            {"model": "test", "data": [{"index": 0, "embedding": [0, 0]}, {"index": 1, "embedding": [0, 1]}]},
            {"model": "test", "data": [{"index": 0, "embedding": [float('nan'), 1]}, {"index": 1, "embedding": [0, 1]}]},
            {"model": "test", "data": [{"index": 0, "embedding": [1, 0]}, {"index": 1, "embedding": [0, 1, 0]}]},
            {"data": [{"index": 0, "embedding": [1, 0]}, {"index": 1, "embedding": [0, 1]}]},
        ]
        for payload in payloads:
            with self.subTest(payload=payload), patch("seedbank.semantic._request", return_value=payload), self.assertRaises(semantic.SemanticError):
                semantic.embed(cfg, ["一", "二"])

    def test_settings_round_trip_and_invalid_save_is_atomic(self):
        saved = save_settings(self.pack, {"semantic_enabled": True, "semantic_model": "test-embed",
                                         "semantic_min_similarity": "0.7"})
        self.assertEqual(saved["semantic_min_similarity"], .7)
        self.assertEqual(load_settings(self.pack)["semantic_model"], "test-embed")
        previous = (self.pack / "mind/semantic.json").read_bytes()
        with self.assertRaises(semantic.SemanticError):
            save_settings(self.pack, {"model": "uncommitted", "semantic_min_similarity": "nan"})
        self.assertEqual((self.pack / "mind/semantic.json").read_bytes(), previous)
        self.assertNotEqual(load_settings(self.pack)["model"], "uncommitted")

    def test_http_external_endpoint_and_literal_key_are_rejected(self):
        for patch_value in ({"base_url": "http://example.com/v1"}, {"base_url": "https://name:secret@example.com/v1"},
                            {"base_url": "https://example.com/v1?key=secret"}, {"api_key_env": "sk-secret-key"}):
            with self.subTest(patch=patch_value), self.assertRaises(semantic.SemanticError):
                self.enable(**patch_value)

    def test_cli_status_and_bridge_do_not_call_service(self):
        from seedbank.cli import main
        from seedbank.bridge import Bridge
        self.enable()
        with patch("seedbank.semantic._request") as request, redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["semantic", "status", str(self.pack)]), 0)
            response = Bridge(self.pack, "stub").handle({"op": "semantic", "action": "status"})
        request.assert_not_called()
        self.assertTrue(response["ok"])
        self.assertIn("pending_chunks", output.getvalue())

    def test_local_transport_never_sends_key_and_remote_transport_uses_environment(self):
        requests = []

        class Response:
            def read(self, count):
                return b'{"model":"fixture","data":[{"index":0,"embedding":[1,0]}]}'

        class Opener:
            def open(self, request, timeout):
                requests.append((request, timeout))
                return nullcontext(Response())

        with patch.dict(os.environ, {"SEMANTIC_FIXTURE_KEY": "fixture-secret"}), \
                patch("seedbank.semantic.urllib.request.build_opener", return_value=Opener()):
            cfg = self.enable(api_key_env="SEMANTIC_FIXTURE_KEY")
            semantic.embed(cfg, ["一段资料"])
            cfg = self.enable(base_url="https://example.invalid/v1", api_key_env="SEMANTIC_FIXTURE_KEY")
            semantic.embed(cfg, ["一段资料"])
        self.assertIsNone(requests[0][0].get_header("Authorization"))
        self.assertEqual(requests[1][0].get_header("Authorization"), "Bearer fixture-secret")
        self.assertEqual(requests[1][0].full_url, "https://example.invalid/v1/embeddings")
        self.assertEqual(requests[1][1], 15)
        self.assertEqual(json.loads(requests[1][0].data)["encoding_format"], "float")
        self.assertNotIn("fixture-secret", (self.pack / "mind/semantic.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
