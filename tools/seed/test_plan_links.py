"""User-run regressions; authored only, using temporary packs and local fixtures."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_daily_choices as fixtures
from seedbank import agency, backup, cognition, development, experience, plan_links, planning
from seedbank.context_window import fit
from seedbank.util import append_memories, read_json, write_json_atomic


class PlanLinksTest(unittest.TestCase):
    setUp = fixtures.DailyChoicesTest.setUp
    goal = fixtures.DailyChoicesTest.goal
    context = fixtures.DailyChoicesTest.context
    proposal = fixtures.DailyChoicesTest.proposal
    choose = fixtures.DailyChoicesTest.choose
    execute = fixtures.DailyChoicesTest.execute

    def review(self, identifier):
        return next(row for row in development.summary(self.pack)["plan_review"] if row["plan_id"] == identifier)

    def test_same_goal_revisions_keep_separate_receipts(self):
        first = self.choose()["plan"]
        receipt1 = self.execute(fixtures.Brain(), self.second)
        second = self.choose(self.proposal(next_step="再写一个不同的例子"))["plan"]
        receipt2 = self.execute(fixtures.Brain(), self.second)
        for plan, receipt in ((first, receipt1), (second, receipt2)):
            self.assertEqual(receipt["data"]["plan_reference"]["plan_id"], plan["plan_id"])
            review = self.review(plan["plan_id"])
            self.assertEqual([r["id"] for r in review["outcomes"]], [receipt["id"]])
            self.assertEqual(review["counts"]["automatic"]["succeeded"], 1)
        self.assertFalse(self.review(first["plan_id"])["is_latest_for_day"])
        self.assertTrue(self.review(second["plan_id"])["is_latest_for_day"])
        self.assertFalse(agency.current_plan(self.pack, self.day["dayNo"])["done"])

    def test_rest_distinguishes_blocked_model_action_and_direct_request(self):
        selected = self.choose(self.proposal("rest"))["plan"]
        blocked = self.execute(fixtures.Brain(), self.first)
        requested = cognition.compose_work(self.pack, "letter", fixtures.Brain(), day=self.day, goal_id=self.first)["receipt"]
        self.assertEqual(blocked["data"]["plan_reference"]["execution"], "automatic")
        self.assertEqual(requested["data"]["plan_reference"]["execution"], "requested")
        review = self.review(selected["plan_id"])
        self.assertEqual(review["counts"], {
            "automatic": {"succeeded": 0, "failed": 0, "blocked": 1},
            "requested": {"succeeded": 1, "failed": 0, "blocked": 0}})
        self.assertIn(selected["decision_id"], {r["id"] for r in blocked["data"]["evidence"]})
        self.assertEqual(development.current_state(self.pack)["skills"]["compose"]["attempts"], 1)

    def test_failure_rolls_back_work_and_records_one_failed_link(self):
        selected = self.choose()["plan"]
        before = self.pack.joinpath("mind/works.json").read_bytes() if self.pack.joinpath("mind/works.json").exists() else None
        original = development.record_outcome

        def fail_after_receipt(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs["status"] == "succeeded":
                raise OSError("fixture after receipt write")
            return result

        with patch("seedbank.development.record_outcome", side_effect=fail_after_receipt):
            receipt = self.execute(fixtures.Brain(), self.second)
        self.assertEqual(receipt["data"]["status"], "failed")
        after = self.pack.joinpath("mind/works.json").read_bytes() if self.pack.joinpath("mind/works.json").exists() else None
        self.assertEqual(after, before)
        self.assertEqual(self.review(selected["plan_id"])["counts"]["automatic"]["failed"], 1)
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def test_append_preserves_old_link_but_changed_entry_is_not_rebound(self):
        first = self.choose()["plan"]
        receipt = self.execute(fixtures.Brain(), self.second)
        reference = receipt["data"]["plan_reference"]
        self.choose(self.proposal("open"))
        self.assertIsNotNone(plan_links.resolve(self.pack, reference))
        rows = planning.read(self.pack)
        next(row for row in rows if row["id"] == first["plan_id"])["context"]["changed"] = True
        planning.path(self.pack).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        self.assertIsNone(plan_links.resolve(self.pack, reference))
        self.assertEqual(self.review(first["plan_id"])["outcomes"], [])
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def test_old_receipts_are_not_inferred_and_legacy_capture_is_read_only(self):
        selected = agency.current_plan(self.pack, self.day["dayNo"])
        development.record_outcome(self.pack, action="rest", status="succeeded", detail="old unlinked",
            day=self.day["dayNo"], source=experience.source_of(self.input), goal_id=self.first, evidence=[self.ref])
        self.assertEqual(self.review(selected["plan_id"])["outcomes"], [])
        config = read_json(agency.agency_path(self.pack))
        config.pop("plan_store", None)
        config["plans"] = [{"day": self.day["dayNo"], "plan": "旧安排", "done": False, "reason": "旧理由", "goal_id": self.first}]
        write_json_atomic(agency.agency_path(self.pack), config)
        planning.path(self.pack).unlink()  # Isolated fixture, never a real life pack.
        before = agency.agency_path(self.pack).read_bytes()
        self.assertEqual(plan_links.capture(self.pack, self.day["dayNo"], execution="requested"), {})
        self.assertEqual(development.summary(self.pack)["plan_review"], [])
        self.assertEqual(agency.agency_path(self.pack).read_bytes(), before)
        self.assertFalse(planning.path(self.pack).exists())

    def test_forgotten_basis_disappears_from_review_and_dependencies_propagate(self):
        append_memories(self.pack, [{"id": "m_link_basis", "day": self.day["dayNo"], "kind": "thought",
            "text": "今天可以自己安排。", "source": experience.source_of(self.input), "event_ids": [self.input["id"]]}])
        selected = self.choose(self.proposal("rest", evidence=["current"]))["plan"]
        self.execute(fixtures.Brain(), self.first)
        ctx = self.context()
        self.assertIn(selected["decision_id"], cognition._context_dependencies(ctx))
        cognition.forget_memory(self.pack, "m_link_basis")
        self.assertNotIn(selected["plan_id"], {r["plan_id"] for r in development.summary(self.pack)["plan_review"]})
        self.assertNotIn(selected["decision_id"], cognition._context_dependencies(self.context()))

    def test_review_is_private_even_when_owner_uses_external_audience(self):
        self.choose(self.proposal("rest"))
        self.execute(fixtures.Brain(), self.first)
        self.assertEqual(plan_links.capture(self.pack, self.day["dayNo"], execution="requested", audience_id="person:visitor"), {})
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False,
            person_id="owner", audience_id="qq-group:123")
        self.assertEqual(ctx["development"]["plan_review"], [])
        self.assertFalse(any(row.get("plan_reference") for row in ctx["development"]["outcomes"]))

    def test_review_details_are_bounded_but_counts_include_all_visible_links(self):
        selected = self.choose(self.proposal("rest"))["plan"]
        for _ in range(5):
            self.execute(fixtures.Brain(), self.first)
        review = self.review(selected["plan_id"])
        self.assertEqual(review["counts"]["automatic"]["blocked"], 5)
        self.assertEqual(len(review["outcomes"]), 3)
        self.assertEqual(review["omitted_outcomes"], 2)

    def test_review_can_be_trimmed_without_mutating_saved_state(self):
        self.choose(self.proposal("rest"))
        self.execute(fixtures.Brain(), self.first)
        ctx = self.context()
        original = deepcopy(ctx["development"]["plan_review"])
        ctx["_cfg"] = {"input_budget": 2048}
        _, used, _ = fit(ctx, lambda c: {"system": "x" * (1800 if c["development"].get("plan_review") else 100)})
        self.assertEqual(used["development"]["plan_review"], [])
        self.assertEqual(ctx["development"]["plan_review"], original)

    def test_request_replay_and_backup_keep_exact_links(self):
        brain = fixtures.Brain({"reply": "先试试。", "daily_plan": self.proposal(),
            "actions": [{"type": "compose", "goal_id": self.second, "reason": "练习"}]})
        result = cognition.chat_turn(self.pack, "安排并尝试。", brain, request_id="plan-link-replay")
        reference = result["actionResults"][0]["data"]["plan_reference"]
        before = development._path(self.pack).read_bytes()
        replay = cognition.chat_turn(self.pack, "安排并尝试。", brain, request_id="plan-link-replay")
        self.assertTrue(replay["replayed"])
        self.assertEqual(development._path(self.pack).read_bytes(), before)
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertIsNotNone(plan_links.resolve(restored, reference))
        self.assertEqual(development.summary(restored)["plan_review"], development.summary(self.pack)["plan_review"])

    def test_creator_dependencies_use_actually_supplied_development(self):
        ctx = self.context()
        ctx["development"]["plan_review"] = [{"dependencies": ["review-only-fixture"]}]

        class TrimmedBrain(fixtures.Brain):
            def compose(self, actual):
                return {"title": "初稿", "text": "留下一个例子。", "_used_development": {}}

        with patch("seedbank.cognition.build_context", return_value=ctx):
            result = cognition.compose_work(self.pack, "letter", TrimmedBrain(), day=self.day)
        self.assertNotIn("review-only-fixture", result["receipt"]["data"]["generation"]["context_dependencies"])


if __name__ == "__main__":
    unittest.main()
