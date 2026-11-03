"""User-run action/plan regressions. Authored only; no live services or real packs."""
import os
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import actions, agency, cognition, development, experience, hands, planning
from seedbank.brain import build_chat_prompt
from seedbank.durability import RecoveryRequired, operation
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.pack_lock import writer
from seedbank.util import append_memories, now_iso, write_file_atomic, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class FixtureBrain:
    name = "action-fixture"

    def compose(self, ctx):
        return {"title": "初稿", "text": "谢谢你陪我一起整理资料。",
                "_generation": {"runner": self.name, "fallback": False}}


class ActionOutcomesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-action-outcomes-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        for guard in (
            patch.dict(os.environ, {"HOME": str(self.folder / "home"),
                "USERPROFILE": str(self.folder / "home"), "SEEDBANK_LANG": "zh_CN"}),
            patch("seedbank.semantic._request", side_effect=AssertionError("No real service")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.pack = self.folder / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="action-outcomes",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = cognition.start_day(self.pack)
        self.source = self.day["file"]
        self.brain = FixtureBrain()
        self.goal = development.apply_proposals(self.pack, {"goals": [{
            "title": "写一封具体的感谢信", "next_step": "完成一份包含具体事例的初稿",
            "reason": "记录这次帮助", "evidence": ["current"]}]},
            day=self.day["dayNo"], source=self.source, runner="fixture")[0]["data"]["id"]
        agency.plan_for_day(self.pack, self.day["dayNo"])
        self.input = experience.record(self.pack, kind="conversation", text="我们一起整理了资料。",
            day=self.day["dayNo"], source=self.source, actor="owner")
        self.memory = {"id": "m_action_fixture", "day": self.day["dayNo"], "at": now_iso(),
            "kind": "thought", "text": "我们一起整理了资料。", "importance": 0.6, "tags": [],
            "source": experience.source_of(self.input), "event_ids": [self.input["id"]]}
        append_memories(self.pack, [self.memory])
        write_json_atomic(self.pack / "mind/body.json", {
            "format": "seedbank/body@1", "energy": 0.9, "updated_at": now_iso(), "resting": False})

    def proposal(self, kind):
        return {"type": kind, "goal_id": self.goal, "reason": "推进当前目标",
                "kind": "letter", "topic": "感谢帮助", "text": "把这次帮助记下来。",
                "memory_ids": [self.memory["id"]], "due_on": date.today().isoformat()}

    def execute(self, kind, **extra):
        return actions.execute(self.pack, [self.proposal(kind)], day=self.day, source=self.source,
            brain=self.brain, memories=[self.memory], evidence=[{
                "id": self.input["id"], "source": experience.source_of(self.input), "kind": "conversation"}], **extra)[0]

    def contents(self):
        names = ("mind/body.json", "mind/mood.json", "mind/experiences.jsonl", "mind/works.json",
                 "mind/hands.json", "mind/memories.jsonl", "journal/loop.jsonl")
        return {name: (self.pack / name).read_bytes() if (self.pack / name).exists() else None for name in names}

    def fail_after_successful_receipt(self, pack, **kwargs):
        receipt = self.original_record(pack, **kwargs)
        if kwargs["status"] == "succeeded":
            raise OSError("fixture: storage failed after outcome append")
        return receipt

    def test_actions_do_not_complete_daily_plan_or_goal(self):
        for kind in ("rest", "remind", "compose", "reflect"):
            with self.subTest(kind=kind):
                receipt = self.execute(kind)
                self.assertEqual(receipt["data"]["status"], "succeeded")
                plan = agency.current_plan(self.pack, self.day["dayNo"])
                self.assertFalse(plan["done"])
                state = development.current_state(self.pack)
                self.assertEqual(state["goals"][self.goal]["status"], "active")
                self.assertIn("行动回执", agency.plan_status(plan, outcomes=state["outcomes"]))
                self.assertIn("待核对", agency.plan_status(plan, outcomes=state["outcomes"]))
        self.assertEqual(hands.load_hands(self.pack)["reminders"][0]["status"], "pending")

    def test_late_receipt_failure_rolls_back_each_action_and_records_only_failure(self):
        self.original_record = development.record_outcome
        for kind in ("rest", "remind", "reflect", "compose"):
            with self.subTest(kind=kind):
                before = self.contents()
                with patch.object(development, "record_outcome", side_effect=self.fail_after_successful_receipt):
                    receipt = self.execute(kind)
                self.assertEqual(receipt["data"]["status"], "failed")
                self.assertEqual(self.contents(), before)
                self.assertEqual(list((self.pack / "art/reflections").glob("*.md")), [])
        outcomes = development.load_development(self.pack)["outcomes"]
        self.assertEqual(len(outcomes), 4)
        self.assertTrue(all(row["status"] == "failed" for row in outcomes))

    def test_nested_failure_preserves_earlier_parent_work(self):
        self.original_record = development.record_outcome
        with writer(self.pack), operation(self.pack, "parent-request"):
            write_file_atomic(self.pack / "parent.txt", "accepted input")
            before = self.contents()
            with patch.object(development, "record_outcome", side_effect=self.fail_after_successful_receipt):
                receipt = self.execute("reflect")
            self.assertEqual(receipt["data"]["status"], "failed")
            self.assertEqual(self.contents(), before)
            self.assertEqual((self.pack / "parent.txt").read_text(encoding="utf-8"), "accepted input")
        self.assertTrue((self.pack / "parent.txt").exists())
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def test_failure_receipt_write_failure_bubbles_after_action_rollback(self):
        before = self.contents()
        with patch.object(development, "record_outcome", side_effect=OSError("storage unavailable")):
            with self.assertRaises(OSError):
                self.execute("reflect")
        self.assertEqual(self.contents(), before)
        self.assertEqual(development.load_development(self.pack)["outcomes"], [])
        self.assertEqual(list((self.pack / "art/reflections").glob("*.md")), [])

    def test_recovery_required_is_not_swallowed_by_action_or_reminder(self):
        for target, kind in (("seedbank.actions.body.spend", "reflect"),
                             ("seedbank.hands.add_reminder", "remind")):
            with self.subTest(kind=kind):
                before = self.contents()
                with patch(target, side_effect=RecoveryRequired("fixture recovery required")):
                    with self.assertRaises(RecoveryRequired):
                        self.execute(kind)
                self.assertEqual(self.contents(), before)
                self.assertEqual(development.load_development(self.pack)["outcomes"], [])

    def test_compose_memory_recovery_stops_and_rolls_back_work(self):
        before = self.contents()
        with patch("seedbank.cognition.append_memories", side_effect=RecoveryRequired("memory recovery")):
            with self.assertRaises(RecoveryRequired):
                self.execute("compose")
        self.assertEqual(self.contents(), before)
        self.assertEqual(development.load_development(self.pack)["outcomes"], [])

    def test_legacy_done_flag_is_unverified_and_does_not_freeze_replanning(self):
        agency.mark_plan_done(self.pack, self.day["dayNo"])
        plan = agency.current_plan(self.pack, self.day["dayNo"])
        self.assertIn("旧记录", agency.plan_status(plan))
        self.assertTrue(plan["done"])  # Historical flag is not rewritten by reading.
        before = planning.path(self.pack).read_bytes()
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertIn("依据待核对", ctx["plan"])
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        development.apply_proposals(self.pack, {"goals": [{"id": self.goal, "status": "paused",
            "reason": "需要先想清楚", "evidence": ["current"]}]},
            day=self.day["dayNo"], source=self.source, runner="fixture")
        refreshed = agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertEqual(refreshed["goal_id"], "")
        self.assertFalse(refreshed["done"])

    def test_unsupported_action_remains_not_started_in_next_context(self):
        receipt = self.execute("unsupported")
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertEqual(ctx["development"]["outcomes"][-1]["id"], receipt["id"])
        self.assertEqual(ctx["development"]["outcomes"][-1]["status"], "blocked")
        self.assertIn("计划完成待核对", ctx["plan"])
        self.assertIn("unsupported / blocked", build_chat_prompt(ctx)["system"])
        self.assertEqual(ctx["development"]["outcomes"][-1]["attempt_state"], "not_started")

    def test_runtime_transcript_has_runtime_attribution_and_receipt_reference(self):
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        ctx["current_evidence"] = [{"id": self.input["id"], "source": experience.source_of(self.input), "kind": "conversation"}]
        _, receipts = cognition._apply_learning(self.pack, {"actions": [self.proposal("rest")]},
                                               ctx, self.day, self.source, self.brain)
        recorded = experience.read(self.pack)[-1]
        self.assertEqual(recorded["actor"], "运行器")
        self.assertEqual(recorded["metadata"]["runner"], "runtime")
        self.assertEqual(recorded["metadata"]["action_outcome_id"], receipts[0]["id"])
        self.assertIn(self.input["id"], recorded["depends_on"])

    def test_outcome_sources_propagate_to_future_memory_and_stay_private(self):
        receipt = self.execute("reflect")
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        source_id = receipt["source"].split("#")[1]
        # Isolate the outcome contribution; other context slots must not mask it.
        refs = cognition._context_dependencies({"development": {"outcomes": ctx["development"]["outcomes"]}})
        self.assertIn(source_id, refs)
        self.assertIn(self.memory["id"], refs)
        derived = experience.record(self.pack, kind="thought", text="根据上次行动调整计划",
            day=self.day["dayNo"], source=self.source, depends_on=refs)
        guest = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"],
            use_semantic=False, person_id="visitor", audience_id="person:visitor")
        self.assertEqual(guest["plan"], "")
        self.assertEqual(guest["development"]["outcomes"], [])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertNotIn(receipt["id"], {r["id"] for r in development.current_state(self.pack)["outcomes"]})


if __name__ == "__main__":
    unittest.main()
