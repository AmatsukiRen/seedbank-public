"""Core regression cases for the user to run; no network, GUI, or real life packs."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import body, development
from seedbank.actions import execute
from seedbank.agency import current_plan, learn_from_day, load_agency, plan_for_day, record_initiation
from seedbank.brain import (_validate_chat_result, _validate_diary_result, build_chat_prompt,
                            create_stub_brain, load_brain_config, save_brain_config)
from seedbank.cognition import build_context, chat_turn, maybe_initiate, start_day
from seedbank.identity import profile
from seedbank.pack import hatch
from seedbank.util import SeedError, read_json, read_memories, read_text, write_json_atomic
from seedbank.works import add_work, list_works, read_work

ROOT = Path(__file__).resolve().parents[2]


class DevelopmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-development-")
        self.addCleanup(temporary.cleanup)
        self.pack = Path(temporary.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="development",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        self.source = self.day["file"]

    def propose(self, **changes):
        return development.apply_proposals(self.pack, changes, day=self.day["dayNo"],
                                           source=self.source, runner="fixture")

    def goal(self):
        rows = self.propose(goals=[{"title": "写一封感谢信", "next_step": "先完成初稿",
                                    "reason": "今天获得了帮助", "evidence": ["current"]}])
        return rows[0]["data"]["id"]

    def test_open_birth_has_no_invented_whale_body(self):
        self.assertEqual(profile(self.pack)["identity_mode"], "open")
        self.assertEqual(profile(self.pack)["avatar"], "seed")
        first_day = next((self.pack / "life").glob("0001-*.md"))
        self.assertIn("尚未接收到感知输入", read_text(first_day))
        self.assertNotIn("光和水的影子", read_text(self.pack / "mind/self.md"))
        ctx = build_context(self.pack, self.day["dayNo"], self.day["date"], "你是谁？")
        self.assertNotIn("鲸", create_stub_brain().chat(ctx)["reply"])
        self.assertTrue(ctx["traitsPicked"])

    def test_legacy_whale_identity_survives(self):
        other = self.pack.parent / "旧.life"
        hatch(other, ROOT / "eggs/dafeiyu.egg", "旧")
        self.assertEqual(profile(other)["avatar"], "dafeiyu")
        self.assertIn("光和水的影子", read_text(other / "mind/self.md"))

    def test_optional_context_budget_keeps_birth_contract_and_remains_configurable(self):
        birth = (self.pack / "birth.json").read_bytes()
        config = read_json(self.pack / "mind/brain.json")
        self.assertNotIn("input_budget", config)
        self.assertEqual(load_brain_config(self.pack)["input_budget"], 16000)
        save_brain_config(self.pack, {"input_budget": 32000})
        self.assertEqual(load_brain_config(self.pack)["input_budget"], 32000)
        self.assertEqual((self.pack / "birth.json").read_bytes(), birth)

    def test_belief_revision_preserves_history_and_requires_evidence(self):
        invalid = {"text": "确定的事", "reason": "没有依据", "evidence": ["missing"]}
        self.assertEqual(self.propose(beliefs=[invalid]), [])
        first = self.propose(beliefs=[{"text": "也许是这样", "reason": "刚刚的对话",
                                       "evidence": ["current"], "confidence": 0.7}])[0]
        prefix = (self.pack / "mind/development.jsonl").read_bytes()
        self.propose(beliefs=[{"id": first["data"]["id"], "text": "我需要重新理解",
                               "reason": "出现不同的反馈", "evidence": ["current"], "confidence": 0.3}])
        self.assertTrue((self.pack / "mind/development.jsonl").read_bytes().startswith(prefix))
        self.assertEqual(len(development.events(self.pack)), 2)
        self.assertEqual(development.summary(self.pack)["beliefs"][0]["confidence"], 0.3)

    def test_damaged_history_is_not_replaced(self):
        path = self.pack / "mind/development.jsonl"
        path.write_text('{"broken":', encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(SeedError):
            self.goal()
        self.assertEqual(path.read_bytes(), before)

    def test_chat_growth_changes_next_prompt(self):
        class Brain:
            name = "fixture"

            def chat(self, ctx):
                return {"reply": "我会重新考虑。", "self_edits": {"self_append": "我在学习倾听。"},
                        "development": {"beliefs": [{"text": "听完再作判断", "reason": "这次对话提醒了我",
                                                      "evidence": ["current"]}]}}

        chat_turn(self.pack, "请先听完再判断。", Brain())
        ctx = build_context(self.pack, self.day["dayNo"], self.day["date"], "现在呢？")
        prompt = build_chat_prompt(ctx)["system"]
        self.assertIn("听完再作判断", prompt)
        self.assertNotIn("我在学习倾听", prompt)  # Unproven legacy self_edits no longer writes.

    def test_goal_requires_own_successful_receipt(self):
        identifier = self.goal()
        plan_for_day(self.pack, self.day["dayNo"])
        record_initiation(self.pack, day_no=self.day["dayNo"])
        self.assertFalse(current_plan(self.pack, self.day["dayNo"])["done"])
        completion = {"id": identifier, "status": "completed", "reason": "已经说过了", "evidence": ["current"]}
        self.assertEqual(self.propose(goals=[completion]), [])
        failed = execute(self.pack, [{"type": "unsupported", "goal_id": identifier}],
                         day=self.day, source=self.source, brain=create_stub_brain(), memories=[])[0]
        self.assertEqual(failed["data"]["status"], "blocked")
        self.assertEqual(self.propose(goals=[{**completion, "outcome_id": failed["id"]}]), [])
        success = execute(self.pack, [{"type": "compose", "kind": "letter", "topic": "感谢帮助",
                                      "goal_id": identifier, "reason": "完成初稿"}],
                          day=self.day, source=self.source, brain=create_stub_brain(), memories=[])[0]
        self.assertTrue(read_work(self.pack, success["data"]["artifact"].split("#")[1]))
        self.assertEqual(self.propose(goals=[{**completion, "reason": "已保存这封信", "outcome_id": success["id"]}]), [])
        self.assertEqual(development.load_development(self.pack)["goals"][identifier]["status"], "active")
        # Saving a result alone no longer certifies completion. Criteria and
        # user feedback cases live in test_learning.py.

    def test_preference_can_be_revised_and_removed_from_interests(self):
        first = self.propose(preferences=[{"topic": "音乐", "stance": "like", "reason": "一次好的体验",
                                           "evidence": ["current"]}])[0]
        learn_from_day(self.pack, self.day["dayNo"], self.day["date"])
        self.assertEqual(load_agency(self.pack)["interests"][0]["topic"], "音乐")
        self.propose(preferences=[{"id": first["data"]["id"], "topic": "音乐", "stance": "unsure",
                                   "reason": "需要更多经历", "evidence": ["current"]}])
        learn_from_day(self.pack, self.day["dayNo"], self.day["date"])
        self.assertEqual(load_agency(self.pack)["interests"], [])

    def test_silence_counts_as_a_decision(self):
        class QuietBrain:
            name = "quiet-fixture"

            def chat(self, ctx):
                return {"reply": ""}

        when = f"{self.day['date']}T16:00:00+08:00"
        self.assertIsNone(maybe_initiate(self.pack, QuietBrain(), now=when, force=True))
        self.assertEqual(load_agency(self.pack)["initiated"][self.day["date"]], 1)

    def test_quiet_initiative_can_keep_a_private_thought(self):
        class QuietBrain:
            name = "quiet-thought-fixture"

            def chat(self, ctx):
                return {"reply": "", "memory_writes": [{"text": "我想先整理已有的想法，再决定是否开口。",
                        "kind": "thought", "importance": 0.6, "tags": ["想法"]}]}

        result = maybe_initiate(self.pack, QuietBrain(), now=f"{self.day['date']}T16:00:00+08:00")
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["memoriesAdded"], 1)
        thoughts = [row for row in read_memories(self.pack) if row.get("runner") == QuietBrain.name]
        self.assertEqual(len(thoughts), 1)
        self.assertEqual(thoughts[0]["kind"], "thought")

    def test_energy_cost_and_elapsed_recovery(self):
        write_json_atomic(self.pack / "mind/body.json", {"format": "seedbank/body@1", "energy": 0.3,
                                                         "updated_at": "2026-11-01T10:00:00Z"})
        self.assertAlmostEqual(body.state(self.pack, now="2026-11-01T11:00:00Z")["energy"], 0.38)
        self.assertAlmostEqual(body.state(self.pack, now="2026-11-01T09:00:00Z")["energy"], 0.3)

    def test_action_fields_survive_model_validation(self):
        extra = {"actions": [{"type": "rest", "reason": "先休息"}],
                 "development": {"beliefs": []}, "corrections": [{"old": "甲", "new": "乙"}]}
        for value in (_validate_chat_result({"reply": "好", **extra}),
                      _validate_diary_result({"diary": "今天的记录", **extra})):
            for key in extra:
                self.assertEqual(value[key], extra[key])

    def test_works_keep_old_artifacts_and_unique_ids(self):
        first = add_work(self.pack, "poem", "第一份")
        for index in range(125):
            add_work(self.pack, "poem", str(index))
        works = list_works(self.pack)
        self.assertEqual(len(works), 126)
        self.assertEqual(len({w["id"] for w in works}), 126)
        self.assertEqual(read_work(self.pack, first["id"])["text"], "第一份")


if __name__ == "__main__":
    unittest.main()
