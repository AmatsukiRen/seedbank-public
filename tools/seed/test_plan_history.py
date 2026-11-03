"""User-run regressions for persistent choices; authored only, not executed."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import agency, backup, cli, cognition, development, experience, learning, planning
from seedbank.bridge import Bridge
from seedbank.pack import hatch, check
from seedbank.util import SeedError, append_memories, read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class PlanHistoryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-plan-history-")
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
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="plan-history",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = cognition.start_day(self.pack)
        self.config = agency.agency_path(self.pack)

    def legacy(self, count=130):
        plans = [{"day": i, "plan": f"第 {i} 页的打算" + "长内容" * 100,
                  "reason": "当时的理由" * 100, "done": i % 2 == 0, "goal_id": "", "extra": {"i": i}}
                 for i in range(1, count + 1)]
        return {"format": agency.AGENCY_FORMAT, "plans": plans, "extra_config": "keep"}

    def goal(self, *, identifier="", next_step="先写初稿", status="active", current_evidence=None):
        return development.apply_proposals(self.pack, {"goals": [{"id": identifier, "title": "感谢这次帮助",
            "next_step": next_step, "status": status, "reason": "把事情说具体", "evidence": ["current"]}]},
            day=self.day["dayNo"], source=self.day["file"], runner="fixture", current_evidence=current_evidence)[0]

    def user_payload(self, **extra):
        return {"title": "记录帮助", "skill": "具体表达", "reason": "记住真实的帮助", "next_step": "先写初稿",
                "criteria": [{"text": "写出具体事例", "group": "信", "check": "feedback"}], **extra}

    def test_long_legacy_history_is_not_truncated_or_rewritten_on_read(self):
        raw = self.legacy()
        raw["plans"].append(deepcopy(raw["plans"][0]))
        write_json_atomic(self.config, raw)
        before = self.config.read_bytes()
        self.assertEqual(agency.load_agency(self.pack)["plans"], raw["plans"])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(planning.path(self.pack).exists())
        agency.add_boundary(self.pack, "留点安静时间")
        saved = read_json(self.config)
        self.assertEqual(saved["plans"], raw["plans"])
        self.assertEqual(saved["extra_config"], "keep")
        agency.plan_for_day(self.pack, 131)
        rows = planning.read(self.pack)
        self.assertEqual(rows[0]["plans"], raw["plans"])
        self.assertEqual(len(agency.plan_history(self.pack, limit=200)["records"]), 132)
        legacy = [r for r in agency.plan_history(self.pack, limit=200)["records"] if r["kind"] == "legacy"]
        self.assertTrue(all(row["at"] == "" for row in legacy))
        self.assertEqual(len([r for r in legacy if r["plan"]["day"] == 1]), 2)
        self.assertEqual(agency.current_plan(self.pack, 1)["plan"], raw["plans"][0]["plan"])

    def test_replanning_keeps_versions_and_noop_does_not_append(self):
        goal = self.goal()
        identifier = goal["data"]["id"]
        first = agency.plan_for_day(self.pack, self.day["dayNo"])
        self.assertEqual(first["goal_event_id"], goal["id"])
        self.goal(identifier=identifier, next_step="先列出两件具体的帮助")
        changed = agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertEqual(changed["replaces"], first["plan_id"])
        before = planning.path(self.pack).read_bytes()
        self.assertEqual(agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True), changed)
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.goal(identifier=identifier, status="paused")
        paused = agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertEqual(paused["goal_id"], "")
        history = agency.plan_history(self.pack)["records"]
        self.assertEqual(len(history), 3)
        self.assertTrue(history[0]["is_current"])
        self.assertTrue(all(not r["is_current"] for r in history[1:]))
        self.assertEqual(history[-1]["plan"]["plan"], "先写初稿")

    def test_legacy_done_is_a_separate_unverified_record(self):
        first = agency.plan_for_day(self.pack, self.day["dayNo"])
        agency.mark_plan_done(self.pack, self.day["dayNo"])
        records = agency.plan_history(self.pack)["records"]
        self.assertEqual(records[0]["kind"], "legacy_flag")
        self.assertEqual(records[0]["previous"], first["plan_id"])
        self.assertFalse(records[1]["plan"]["done"])
        self.assertIn("待核对", agency.plan_status(agency.current_plan(self.pack, self.day["dayNo"])))

    def test_empty_plan_patch_does_not_delete_history_and_old_projection_cannot_override(self):
        choice = agency.plan_for_day(self.pack, 1)
        agency.save_agency(self.pack, {"plans": []})
        self.assertEqual(agency.current_plan(self.pack, 1)["plan_id"], choice["plan_id"])
        write_json_atomic(self.config, self.legacy(1))  # Simulated old runner; ledger stays authoritative.
        self.assertEqual(agency.current_plan(self.pack, 1)["plan_id"], choice["plan_id"])

    def test_paging_is_stable_when_new_choices_arrive_and_bad_queries_fail(self):
        for day in range(1, 7):
            agency.plan_for_day(self.pack, day)
        page = agency.plan_history(self.pack, limit=2)
        agency.plan_for_day(self.pack, 7)
        older = agency.plan_history(self.pack, before=page["next_before"], limit=2)
        self.assertEqual([r["plan"]["day"] for r in page["records"]], [6, 5])
        self.assertEqual([r["plan"]["day"] for r in older["records"]], [4, 3])
        for kwargs in ({"limit": True}, {"limit": 0}, {"limit": 201}, {"day": -1}, {"day": 1.2},
                       {"day": True}, {"before": "missing"}, {"before": True},
                       {"day": 7, "before": page["next_before"]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SeedError):
                agency.plan_history(self.pack, **kwargs)

    def test_corrupt_config_or_missing_ledger_never_becomes_empty_state(self):
        for raw in ([], None, {"format": "future"}, {"plans": None}, {"plans": [{"day": True, "plan": "bad"}]}):
            with self.subTest(raw=raw):
                write_json_atomic(self.config, raw)
                before = self.config.read_bytes()
                with self.assertRaises(SeedError):
                    agency.add_interest(self.pack, "写作")
                self.assertEqual(self.config.read_bytes(), before)
        write_json_atomic(self.config, {"format": agency.AGENCY_FORMAT, "plan_store": planning.FORMAT})
        with self.assertRaises(SeedError):
            agency.plan_for_day(self.pack, 1)
        self.assertFalse(planning.path(self.pack).exists())

    def test_broken_version_chain_and_duplicate_ids_are_rejected_without_rewrite(self):
        agency.plan_for_day(self.pack, 1)
        agency.mark_plan_done(self.pack, 1)
        original = planning.read(self.pack)
        variants = []
        broken = deepcopy(original)
        broken[-1]["previous"] = "p_missing"
        variants.append(broken)
        duplicate = deepcopy(original)
        duplicate[-1]["id"] = duplicate[1]["id"]
        variants.append(duplicate)
        variants.append(original[1:])
        variants.append([])
        for rows in variants:
            with self.subTest(rows=rows):
                planning.path(self.pack).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
                before = planning.path(self.pack).read_bytes()
                with self.assertRaises(SeedError):
                    agency.plan_for_day(self.pack, 2)
                with self.assertRaises(SeedError):
                    check(self.pack)
                self.assertEqual(planning.path(self.pack).read_bytes(), before)

    def test_first_choice_rolls_back_ledger_if_store_marker_cannot_be_written(self):
        write_json_atomic(self.config, self.legacy(2))
        before = self.config.read_bytes()
        with patch("seedbank.planning.write_json_atomic", side_effect=OSError("fixture marker failure")):
            with self.assertRaises(OSError):
                agency.plan_for_day(self.pack, 3)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(planning.path(self.pack).exists())
        agency.plan_for_day(self.pack, 3)
        self.assertEqual(len(planning.read(self.pack)), 2)

    def test_user_goal_edit_refreshes_plan_once_and_fault_keeps_goal_and_plan_together(self):
        payload = self.user_payload()
        result = learning.perform(self.pack, "plan", payload, request_id="fixture-plan-create")
        current = agency.current_plan(self.pack, self.day["dayNo"])
        self.assertEqual(current["goal_id"], result["goal_id"])
        before = planning.path(self.pack).read_bytes()
        replay = learning.perform(self.pack, "plan", payload, request_id="fixture-plan-create")
        self.assertEqual(replay["goal_id"], result["goal_id"])
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        goal = development.current_state(self.pack)["goals"][result["goal_id"]]
        update = self.user_payload(goal_id=goal["id"], expected=goal["event_id"], next_step="先列具体事例")
        original_append = planning.jsonl.append

        def fail_after_append(pack, file, rows, validator=None):
            original_append(pack, file, rows, validator)
            if Path(file) == planning.path(self.pack):
                raise OSError("fixture after plan append")

        with patch("seedbank.planning.jsonl.append", side_effect=fail_after_append):
            with self.assertRaises(OSError):
                learning.perform(self.pack, "plan", update, request_id="fixture-plan-edit")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(development.current_state(self.pack)["goals"][goal["id"]]["event_id"], goal["event_id"])
        learning.perform(self.pack, "plan", update, request_id="fixture-plan-edit")
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["plan"], "先列具体事例")
        self.assertEqual(len(agency.plan_history(self.pack)["records"]), 2)

    def test_plan_evidence_is_not_replaced_by_new_goal_evidence(self):
        old = experience.record(self.pack, kind="conversation", text="最初的打算", day=self.day["dayNo"], source=self.day["file"])
        memory = {"id": "m_old_plan", "day": self.day["dayNo"], "kind": "thought", "text": "最初的打算",
                  "source": experience.source_of(old), "event_ids": [old["id"]]}
        append_memories(self.pack, [memory])
        goal = self.goal(current_evidence=[{"id": old["id"], "source": experience.source_of(old), "kind": "conversation"}])
        agency.plan_for_day(self.pack, self.day["dayNo"])
        new = experience.record(self.pack, kind="conversation", text="改变想法", day=self.day["dayNo"], source=self.day["file"])
        self.goal(identifier=goal["data"]["id"], next_step="另一种安排", current_evidence=[{
            "id": new["id"], "source": experience.source_of(new), "kind": "conversation"}])
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertIn("待重新安排", ctx["plan"])
        self.assertIn(old["id"], cognition._context_dependencies({"_plan_evidence": ctx["_plan_evidence"]}))
        cognition.forget_memory(self.pack, memory["id"])
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertEqual(ctx["plan"], "")
        self.assertTrue(agency.plan_history(self.pack)["records"])  # Explicit historical view remains available.

    def test_verified_goal_completion_replans_without_erasing_earlier_choice(self):
        class Brain:
            name = "plan-history-fixture"

            def compose(self, ctx):
                return {"title": "感谢信", "text": "谢谢你昨天帮助我整理资料。"}

        goal = learning.perform(self.pack, "plan", self.user_payload())["goal_id"]
        first = agency.current_plan(self.pack, self.day["dayNo"])
        current = learning.listing(self.pack, goal)
        receipt = learning.practice(self.pack, goal, "letter", "感谢整理资料", Brain(),
                                    criteria_id=current["criteria"]["id"])["receipt"]["id"]
        learning.perform(self.pack, "feedback", {"goal_id": goal, "criteria_id": current["criteria"]["id"],
            "outcome_id": receipt, "ratings": {"c1": "met"}, "reason": "提到了具体帮助", "next_step": "以后继续练习"})
        current = learning.listing(self.pack, goal)
        learning.perform(self.pack, "complete", {"goal_id": goal, "criteria_id": current["criteria"]["id"],
            "expected": current["goal"]["event_id"], "evidence": {"c1": receipt}, "reason": "这次符合具体条件"})
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["goal_id"], "")
        history = agency.plan_history(self.pack)["records"]
        self.assertEqual(history[-1]["id"], first["plan_id"])
        self.assertEqual(history[-1]["plan"]["goal_id"], goal)
        self.assertFalse(history[-1]["plan"]["done"])  # Goal and free-text plan remain distinct.

    def test_cli_bridge_and_backup_keep_full_history(self):
        agency.plan_for_day(self.pack, 1)
        agency.mark_plan_done(self.pack, 1)
        agency.plan_for_day(self.pack, 2)
        result = Bridge(self.pack, "stub").handle({"op": "agency", "action": "history", "day": 1, "limit": 1})
        self.assertTrue(result["ok"])
        self.assertTrue(result["has_more"])
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli.main(["agency", str(self.pack), "--history", "--day", "1", "--limit", "1"]), 0)
        self.assertEqual(json.loads(output.getvalue())["records"][0]["id"], result["records"][0]["id"])
        saved = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(saved["file"], restored)
        self.assertEqual(planning.path(restored).read_bytes(), planning.path(self.pack).read_bytes())
        self.assertEqual(agency.plan_history(restored), agency.plan_history(self.pack))


if __name__ == "__main__":
    unittest.main()
