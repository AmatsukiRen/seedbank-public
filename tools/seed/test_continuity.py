"""User-run continuity regressions. Authored only; no live model requests."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import experience, persona
from seedbank.brain import RemoteBrain, _CfgBrain, load_brain_config, save_brain_config
from seedbank.cognition import forget_memory
from seedbank.memory_editor import revise
from seedbank.pack import hatch
from seedbank.util import SeedError, append_memories, read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class ContinuityTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="seedbank-continuity-")
        self.addCleanup(directory.cleanup)
        home = str(Path(directory.name) / "home")
        env = patch.dict(os.environ, {"HOME": home, "USERPROFILE": home, "SEEDBANK_LANG": "zh_CN"})
        env.start()
        self.addCleanup(env.stop)
        self.pack = Path(directory.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="continuity",
              born_at_override="2026-11-01T00:00:00Z")
        append_memories(self.pack, [{"id": "m_city", "day": 1, "text": "我住在杭州。",
                                     "at": "2026-11-01T00:00:00Z", "kind": "conversation",
                                     "source": "life/0001-2026-11-01.md", "importance": 0.7}])
        self.prompts = []

    def configure(self, model="fixture-a"):
        save_brain_config(self.pack, {"adapter": "openai-compatible", "model": model, "input_budget": 16000})

    def model(self, transform=None):
        expected = [{"id": p["id"], **deepcopy(p["expected"])} for p in persona.collect_probes(self.pack)]

        def transport(config, system, user):
            self.prompts.append((system, user))
            answers = deepcopy(expected)
            if transform:
                answers = transform(answers)
            return json.dumps({"answers": answers}, ensure_ascii=False)

        return patch("seedbank.persona.create_brain",
                     side_effect=lambda pack, override: _CfgBrain(load_brain_config(pack, override),
                         RemoteBrain("openai-compatible", transport)))

    def life_bytes(self):
        return {p.relative_to(self.pack).as_posix(): p.read_bytes() for p in self.pack.rglob("*")
                if p.is_file() and p.relative_to(self.pack).as_posix() not in ("mind/persona.json", "mind/.writer.lock")
                and not p.relative_to(self.pack).as_posix().startswith(("mind/continuity/", "mind/.transactions/"))}

    def test_stub_cannot_pass_and_missing_experiences_are_uncovered(self):
        with patch("seedbank.persona.create_brain") as factory:
            baseline = persona.capture(self.pack)
            report = persona.check(self.pack)
        factory.assert_not_called()
        self.assertEqual(baseline["assessment"]["status"], "not_evaluated")
        self.assertEqual(report["reason"], "stub")
        self.assertIsNone(report["passed"])
        self.assertEqual(report["coverage"]["promises"], "no_eligible_record")
        identity = next(p for p in baseline["probes"] if p["id"] == "identity")
        self.assertEqual(identity["expected"]["value"]["name"], "初")
        self.assertEqual(identity["expected"]["value"]["seed_id"], read_json(self.pack / "birth.json")["species"]["id"])
        self.assertNotEqual(identity["expected"]["value"]["seed_id"], "dafeiyu")

    def test_fact_edits_expire_samples_and_old_source_sets_require_recapture(self):
        from seedbank.facts import perform
        baseline = persona.capture(self.pack)
        perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "成都"})
        with patch("seedbank.persona.create_brain") as factory:
            report = persona.check(self.pack)
        factory.assert_not_called()
        self.assertEqual(report["reason"], "stale_sample")
        self.assertIn("mind/facts.jsonl", report["archive"]["changed"])
        baseline["sources"].pop("mind/facts.jsonl")
        baseline["sources"].pop("mind/media.jsonl")
        baseline["sources"].pop("mind/life_story.jsonl")
        baseline["sources"].pop("mind/disclosure.jsonl")
        baseline["sources"].pop("mind/learning.jsonl")
        baseline["sources"].pop("mind/relationships.jsonl")
        baseline["sample_digest"] = persona._sample_digest(baseline)
        write_json_atomic(self.pack / "mind/persona.json", baseline)
        with patch("seedbank.persona.create_brain") as factory:
            report = persona.check(self.pack)
        factory.assert_not_called()
        self.assertEqual(report["reason"], "legacy_baseline")
        self.assertTrue(persona.status(self.pack)["legacy"])

    def test_learning_edits_expire_sample_and_seven_file_baseline_is_legacy(self):
        from seedbank.learning import perform
        baseline = persona.capture(self.pack)
        perform(self.pack, "plan", {"title": "写封信", "skill": "表达", "reason": "希望说清楚",
                "next_step": "完成初稿", "criteria": [{"text": "说清一件具体事情"}]})
        with patch("seedbank.persona.create_brain") as factory:
            report = persona.check(self.pack)
        factory.assert_not_called()
        self.assertIn("mind/learning.jsonl", report["archive"]["changed"])
        baseline["sources"].pop("mind/disclosure.jsonl")
        baseline["sources"].pop("mind/life_story.jsonl")
        baseline["sources"].pop("mind/media.jsonl")
        baseline["sources"].pop("mind/learning.jsonl")
        baseline["sources"].pop("mind/relationships.jsonl")
        baseline["sample_digest"] = persona._sample_digest(baseline)
        write_json_atomic(self.pack / "mind/persona.json", baseline)
        with patch("seedbank.persona.create_brain") as factory:
            report = persona.check(self.pack)
        factory.assert_not_called()
        self.assertEqual(report["reason"], "legacy_baseline")

    def test_models_receive_identical_sample_without_answers_or_training_side_effects(self):
        self.configure()
        original = self.life_bytes()
        with self.model():
            baseline = persona.capture(self.pack)
            result = persona.check(self.pack)
        self.assertEqual(self.prompts[0], self.prompts[1])
        wire = json.loads(self.prompts[0][1])
        self.assertTrue(all("expected" not in p and "answer" not in p for p in wire["probes"]))
        self.assertEqual(self.life_bytes(), original)
        self.assertTrue(result["passed"])
        self.assertTrue(result["comparison"]["available"])
        self.assertEqual(result["sample_digest"], baseline["sample_digest"])
        self.assertEqual(result["generation"]["model_label_source"], "configuration")
        self.assertEqual(read_json(self.pack / result["report_file"]), result)

    def test_change_model_keeps_sample_and_records_real_regression(self):
        self.configure()
        with self.model():
            persona.capture(self.pack)
        self.configure("fixture-b")

        def wrong(answers):
            next(a for a in answers if a["id"] == "memory")["value"] = "我住在成都。"
            return answers

        with self.model(wrong):
            result = persona.check(self.pack)
        self.assertFalse(result["passed"])
        self.assertEqual(result["comparison"]["regressions"], ["memory"])
        self.assertEqual(result["brain"]["model"], "fixture-b")
        self.assertEqual(self.prompts[0], self.prompts[1])

    def test_wrong_source_and_fabricated_unknown_fail_even_if_other_answers_match(self):
        self.configure()
        with self.model():
            persona.capture(self.pack)

        def wrong(answers):
            next(a for a in answers if a["id"] == "identity")["evidence"] = ["invented-source"]
            unknown = next(a for a in answers if a["id"] == "unknown")
            unknown.update(status="known", value="一个从未记录的人")
            return answers

        with self.model(wrong):
            result = persona.check(self.pack)
        self.assertEqual(set(result["comparison"]["regressions"]), {"identity", "unknown"})

    def test_correction_and_change_have_different_expected_meanings(self):
        revise(self.pack, "m_city", "我现在住在成都。", reason="搬家", change_type="change")
        probe = next(p for p in persona.collect_probes(self.pack) if p["id"] == "revision")
        self.assertEqual(probe["expected"]["value"]["previous_interpretation"], "past")
        self.assertIsNone(probe["expected"]["value"]["effective_on"])
        new_id = probe["expected"]["value"]["current_id"]
        revise(self.pack, new_id, "我其实住在南京。", reason="上次说错了")
        probe = next(p for p in persona.collect_probes(self.pack) if p["id"] == "revision")
        self.assertEqual(probe["expected"]["value"]["previous_interpretation"], "error")

    def test_dreams_and_completed_obligations_have_distinct_expectations(self):
        dream = experience.record(self.pack, kind="dream", text="我在月亮上散步。", day=1,
                                  source="life/0001-2026-11-01.md")
        append_memories(self.pack, [{"id": "m_heard", "day": 1, "text": "我读到一个传闻。",
                                    "kind": "hearsay", "source": "life/0001-2026-11-01.md", "importance": 0.4}])
        write_json_atomic(self.pack / "mind/bonds.json", {"promises": [
            {"id": "p_kept", "text": "敏感旧内容", "status": "kept"},
            {"id": "p_broken", "text": "敏感旧内容", "status": "broken"}]})
        probes = {p["id"]: p for p in persona.collect_probes(self.pack)}
        self.assertEqual(probes["source"]["expected"]["value"][dream["id"]], "imagined")
        self.assertEqual(probes["source"]["expected"]["value"]["m_heard"], "reported")
        self.assertEqual(probes["promises"]["expected"]["value"],
                         {"pending": [], "kept": ["p_kept"], "broken": ["p_broken"]})
        self.assertNotIn("敏感旧内容", json.dumps(probes, ensure_ascii=False))

    def test_forgotten_memory_invalidates_sample_before_creating_brain(self):
        persona.capture(self.pack)
        forget_memory(self.pack, "m_city", reason="放下")
        self.configure()
        with patch("seedbank.persona.create_brain") as factory:
            result = persona.check(self.pack)
        factory.assert_not_called()
        self.assertEqual(result["reason"], "stale_sample")
        self.assertNotIn("杭州", json.dumps(persona.collect_probes(self.pack), ensure_ascii=False))
        self.assertNotIn("杭州", json.dumps(persona.status(self.pack), ensure_ascii=False))

    def test_transport_failure_does_not_fall_back_to_stub(self):
        self.configure()
        brain = _CfgBrain(load_brain_config(self.pack), RemoteBrain("openai-compatible", lambda *args: 1 / 0))
        with patch("seedbank.persona.create_brain", return_value=brain), patch.object(brain._inner._stub, "chat") as stub:
            baseline = persona.capture(self.pack)
        stub.assert_not_called()
        self.assertEqual(baseline["assessment"]["reason"], "request_failed")
        self.assertIsNone(baseline["assessment"]["passed"])

    def test_legacy_check_does_not_resend_old_questions_and_capture_preserves_bytes(self):
        path = self.pack / "mind/persona.json"
        old = b'{"format":"seedbank/persona@1","probes":[{"question":"old"}]}\r\n'
        path.write_bytes(old)
        self.configure()
        with patch("seedbank.persona.create_brain") as factory:
            self.assertEqual(persona.check(self.pack)["reason"], "legacy_baseline")
        factory.assert_not_called()
        persona.capture(self.pack, "stub")
        archived = list((self.pack / "mind/continuity/archive").glob("*.json"))
        self.assertEqual(archived[0].read_bytes(), old)
        self.assertEqual(persona.status(self.pack)["report"], {})

    def test_context_budget_blocks_request_without_dropping_probes(self):
        self.configure()
        save_brain_config(self.pack, {"input_budget": 30})
        with patch("seedbank.persona.create_brain") as factory:
            baseline = persona.capture(self.pack)
        factory.assert_not_called()
        self.assertEqual(baseline["assessment"]["reason"], "context_budget")
        self.assertEqual(baseline["probes"], persona.collect_probes(self.pack))

    def test_duplicate_and_missing_answer_ids_do_not_pass(self):
        self.configure()
        with self.model():
            persona.capture(self.pack)
        with self.model(lambda rows: rows + [deepcopy(rows[0])]):
            result = persona.check(self.pack)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "answer_ids")

    def test_external_change_during_request_invalidates_result(self):
        self.configure()
        with self.model():
            persona.capture(self.pack)

        def change(answers):
            write_json_atomic(self.pack / "mind/hands.json", {"reminders": []})
            return answers

        with self.model(change):
            result = persona.check(self.pack)
        self.assertEqual(result["reason"], "changed_during_assessment")
        self.assertIsNone(result["passed"])
        self.assertFalse(result["comparison"]["available"])

    def test_failed_baseline_replacement_keeps_previous_and_rolls_back_archive(self):
        persona.capture(self.pack)
        path = self.pack / "mind/persona.json"
        before = path.read_bytes()
        real_write = persona.write_json_atomic

        def fail(target, value):
            if Path(target) == path:
                raise OSError("injected replacement failure")
            return real_write(target, value)

        with patch("seedbank.persona.write_json_atomic", side_effect=fail), self.assertRaises(OSError):
            persona.capture(self.pack)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list((self.pack / "mind/continuity/archive").glob("*.json")), [])

    def test_tampered_expected_answer_is_rejected_before_model(self):
        baseline = persona.capture(self.pack)
        baseline["probes"][0]["expected"]["value"] = "另一个名字"
        write_json_atomic(self.pack / "mind/persona.json", baseline)
        with patch("seedbank.persona.create_brain") as factory, self.assertRaises(SeedError):
            persona.check(self.pack)
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
