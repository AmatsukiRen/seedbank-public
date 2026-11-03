"""User-run regressions only. Isolated packs and offline model fixtures."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_learning as fixtures
import test_learning_strategies as strategy_fixtures
from seedbank import backup, cognition, context_window, development, experience, goal_dependencies, goal_projects, learning
from seedbank.brain import _development_contract
from seedbank.util import SeedError, append_memories, canonical_json, write_file_atomic


class GoalProjectsTest(unittest.TestCase):
    plan = fixtures.LearningTest.plan
    practice = fixtures.LearningTest.practice
    listing = fixtures.LearningTest.listing
    review = fixtures.LearningTest.review

    def setUp(self):
        strategy_fixtures.LearningStrategiesTest.setUp(self)
        spend = patch("seedbank.body.spend")
        spend.start()
        self.addCleanup(spend.stop)
        event = experience.record(self.pack, kind="conversation", text="我想先整理材料，再写信并回顾。",
                                  day=self.day["dayNo"], source=self.day["file"], actor="owner")
        self.ref = {"id": event["id"], "source": experience.source_of(event), "kind": "conversation"}
        self.generation = {"runner": "project-fixture", "model": "test-only", "fallback": False}

    def context(self):
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        ctx["current_evidence"] = [self.ref]
        return ctx

    def proposal(self):
        return {"title": "把感谢写清楚", "reason": "先确认材料再表达", "evidence": ["current"], "stages": [
            {"key": "prepare", "title": "整理这次材料", "next_step": "列出具体帮助", "skill": "表达",
             "criteria": [{"text": "材料包含具体事情", "group": "材料", "check": "feedback"}], "after": []},
            {"key": "write", "title": "写出这封信", "next_step": "依据材料表达感谢", "skill": "表达",
             "criteria": [{"text": "说明帮助和感受", "group": "信", "check": "feedback"}], "after": [{"stage": "prepare"}]}]}

    def apply(self, raw=None, *, ctx=None, generation=None):
        return goal_projects.apply(self.pack, self.proposal() if raw is None else raw,
                                   ctx=self.context() if ctx is None else ctx, day=self.day,
                                   generation=self.generation if generation is None else generation)

    def contents(self):
        return {name: (self.pack / name).read_bytes() if (self.pack / name).exists() else None
                for name in ("mind/development.jsonl", "mind/learning.jsonl", "mind/experiences.jsonl")}

    def finish(self, goal):
        outcome = self.practice(goal)["receipt"]["id"]
        self.review(goal, outcome)
        state = self.listing(goal)
        learning.perform(self.pack, "complete", {"goal_id": goal, "criteria_id": state["criteria"]["id"],
            "expected": state["goal"]["event_id"], "evidence": {"c1": outcome}, "reason": "核对了这次成果"})
        return outcome

    def test_creates_sourced_stages_with_initial_standards_and_waiting_state(self):
        result = self.apply()
        self.assertEqual(result["status"], "accepted")
        first, second = result["goal_ids"]["prepare"], result["goal_ids"]["write"]
        self.assertEqual([row["format"] for row in learning.read(self.pack)], ["seedbank/learning@5"] * 2)
        self.assertTrue(goal_dependencies.readiness(self.pack, first)["ready"])
        self.assertFalse(goal_dependencies.readiness(self.pack, second)["ready"])
        self.assertEqual(development.choose_plan(self.pack, self.day["dayNo"])["goal_id"], first)
        overview = self.listing(second)["project"]
        self.assertEqual(overview["title"], self.proposal()["title"])
        self.assertEqual([row["status"] for row in overview["stages"]], ["active", "active"])
        event = next(row for row in experience.read(self.pack) if row["id"] == result["project_id"])
        self.assertIn(self.ref["id"], event["depends_on"])

    def test_feedback_and_explicit_completion_open_next_stage_without_completing_it(self):
        result = self.apply()
        first, second = result["goal_ids"]["prepare"], result["goal_ids"]["write"]
        outcome = self.practice(first)["receipt"]["id"]
        self.review(first, outcome)
        self.assertFalse(goal_dependencies.readiness(self.pack, second)["ready"])
        self.finish(first)
        self.assertTrue(goal_dependencies.readiness(self.pack, second)["ready"])
        later = self.practice(second)["receipt"]
        original = next(row for row in experience.read(self.pack) if experience.source_of(row) == later["source"])
        self.assertIn("prerequisite_check", original["metadata"])
        self.assertEqual(self.listing(second)["goal"]["status"], "active")

    def test_out_of_order_dag_supports_independent_branches_and_multiple_prerequisites(self):
        raw = self.proposal()
        branch = {**deepcopy(raw["stages"][0]), "key": "other", "title": "另一份材料"}
        raw["stages"][1]["after"].append({"stage": "other"})
        raw["stages"] = [raw["stages"][1], branch, raw["stages"][0]]
        result = self.apply(raw)
        self.assertEqual(result["status"], "accepted")
        self.finish(result["goal_ids"]["prepare"])
        self.assertFalse(goal_dependencies.readiness(self.pack, result["goal_ids"]["write"])["ready"])
        self.finish(result["goal_ids"]["other"])
        self.assertTrue(goal_dependencies.readiness(self.pack, result["goal_ids"]["write"])["ready"])

    def test_invalid_graphs_and_attempted_overwrites_leave_no_partial_goals(self):
        cycle = self.proposal()
        cycle["stages"][0]["after"] = [{"stage": "write"}]
        missing = self.proposal()
        missing["stages"][1]["after"] = [{"stage": "missing"}]
        duplicate = self.proposal()
        duplicate["stages"][1]["after"] *= 2
        overwrite = self.proposal()
        overwrite["stages"][0]["id"] = "g_existing"
        self_only = self.proposal()
        self_only["stages"][0]["criteria"] = [{"check": "artifact", "artifact_kind": "letter"}]
        before = self.contents()
        for raw in (cycle, missing, duplicate, overwrite, self_only):
            with self.subTest(raw=raw):
                self.assertEqual(self.apply(raw)["status"], "rejected")
                self.assertEqual(self.contents(), before)

    def test_second_stage_save_failure_rolls_back_entire_project(self):
        before = self.contents()
        original = learning.define
        calls = []

        def interrupted(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                raise OSError("fixture second-stage interruption")
            return original(*args, **kwargs)

        with patch("seedbank.learning.define", side_effect=interrupted), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.apply()["status"], "accepted")

    def test_repeated_project_is_idempotent_and_renamed_copy_cannot_overwrite(self):
        first = self.apply()
        before = self.contents()
        repeated = self.apply()
        self.assertEqual(repeated["status"], "unchanged")
        self.assertEqual(repeated["goal_ids"], first["goal_ids"])
        self.assertEqual(self.contents(), before)
        changed = self.proposal()
        changed["reason"] = "换个理由重提"
        self.assertEqual(self.apply(changed)["status"], "rejected")
        self.assertEqual(self.contents(), before)

    def test_capacity_does_not_drop_or_pause_existing_goals(self):
        for index in range(5):
            self.plan(title=f"已有目标 {index}")
        before = self.contents()
        self.assertEqual(self.apply()["status"], "rejected")
        self.assertEqual(self.contents(), before)
        self.assertTrue(all(goal["status"] == "active" for goal in development.current_state(self.pack)["goals"].values()))

    def test_existing_prerequisite_requires_actual_current_goal_and_full_standard(self):
        goal = self.plan(title="已有材料")
        raw = self.proposal()
        raw["stages"][0]["after"] = [{"goal_id": goal, "criteria_id": self.listing(goal)["criteria"]["id"]}]
        ctx = self.context()
        absent = {**ctx, "learning": []}
        self.assertEqual(self.apply(raw, ctx=absent)["status"], "rejected")
        stale = deepcopy(ctx)
        state = self.listing(goal)
        self.plan(title="已有材料", goal_id=goal, expected=state["goal"]["event_id"],
                  items=[{"text": "修订后的明确条件", "check": "feedback"}])
        self.assertEqual(self.apply(raw, ctx=stale)["status"], "rejected")
        raw["stages"][0]["after"][0]["criteria_id"] = self.listing(goal)["criteria"]["id"]
        self.assertEqual(self.apply(raw)["status"], "accepted")

    def test_completed_goal_standard_can_be_shown_as_a_prerequisite(self):
        goal = self.plan(title="先前已完成的材料")
        self.finish(goal)
        ctx = self.context()
        self.assertIn(goal, [item["goal_id"] for item in ctx["learning"]])
        raw = self.proposal()
        raw["stages"][0]["after"] = [{"goal_id": goal, "criteria_id": self.listing(goal)["criteria"]["id"]}]
        result = self.apply(raw, ctx=ctx)
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(goal_dependencies.readiness(self.pack, result["goal_ids"]["prepare"])["ready"])

    def test_external_fallback_missing_and_nonexistent_evidence_do_not_create_projects(self):
        before = self.contents()
        for ctx, generation in (({**self.context(), "_audience_id": "qq-group:123"}, self.generation),
                                (self.context(), {**self.generation, "fallback": True}),
                                (self.context(), {"runner": "stub"}),
                                ({**self.context(), "current_evidence": []}, self.generation),
                                ({**self.context(), "current_evidence": [{**self.ref, "id": "x_missing"}]}, self.generation)):
            self.assertEqual(self.apply(ctx=ctx, generation=generation)["status"], "rejected")
            self.assertEqual(self.contents(), before)

    def test_model_cannot_redefine_a_saved_stage(self):
        result = self.apply()
        goal = self.listing(result["goal_ids"]["write"])
        with self.assertRaises(SeedError):
            learning.define(self.pack, goal["goal"], goal["criteria"]["data"]["items"], skill="表达",
                evidence=goal["criteria"]["evidence"], source=goal["criteria"]["source"], origin="model", prerequisites=[])

    def test_user_revision_keeps_project_history_and_requires_explicit_child_rebinding(self):
        result = self.apply()
        first, second = result["goal_ids"]["prepare"], result["goal_ids"]["write"]
        state = self.listing(first)
        self.plan(title=state["goal"]["title"], goal_id=first, expected=state["goal"]["event_id"], skill="表达",
                  items=[{"text": "新条件", "check": "feedback"}])
        latest = self.listing(first)
        self.assertEqual(latest["criteria"]["format"], "seedbank/learning@4")
        self.assertEqual(latest["project"]["title"], self.proposal()["title"])
        self.assertEqual(goal_dependencies.readiness(self.pack, second)["requirements"][0]["state"], "changed")

    def test_forgotten_project_source_is_not_resurrected_by_repetition(self):
        result = self.apply()
        event = next(row for row in experience.read(self.pack) if row["id"] == result["project_id"])
        append_memories(self.pack, [{"id": "m_project", "day": self.day["dayNo"], "kind": "thought", "text": "这份安排的来源",
                                    "source": experience.source_of(event), "event_ids": [event["id"]]}])
        cognition.forget_memory(self.pack, "m_project")
        self.assertEqual(development.current_state(self.pack)["goals"], {})
        self.assertEqual(self.apply()["status"], "rejected")

    def test_changed_project_source_is_withheld_without_repairing_history(self):
        result = self.apply()
        events = experience.read(self.pack)
        event = next(row for row in events if row["id"] == result["project_id"])
        payload = json.loads(event["text"])
        payload["proposal"]["title"] = "外部改写"
        event["text"] = canonical_json(payload)
        write_file_atomic(experience.path(self.pack), "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in events))
        before = self.contents()
        with self.assertRaises(SeedError):
            learning.read(self.pack)
        self.assertEqual(self.contents(), before)

    def test_stage_standard_cannot_depart_from_its_original_proposal(self):
        self.apply()
        rows = learning.read(self.pack)
        rows[-1]["data"]["items"][0]["text"] = "没有提议过的替代条件"
        write_file_atomic(learning.path(self.pack), "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        before = self.contents()
        with self.assertRaises(SeedError):
            learning.read(self.pack)
        self.assertEqual(self.contents(), before)

    def test_backup_preserves_project_sources_conditions_and_order(self):
        result = self.apply()
        saved = backup.create(self.pack)
        restored = self.pack.parent / "project-restored.life"
        backup.restore(saved["file"], restored)
        goal = result["goal_ids"]["write"]
        self.assertEqual(learning.listing(restored, goal)["project"], self.listing(goal)["project"])
        self.assertEqual(goal_dependencies.readiness(restored, goal), goal_dependencies.readiness(self.pack, goal))

    def test_chat_returns_runtime_confirmation_and_request_replay_creates_no_duplicates(self):
        raw = self.proposal()
        generation = self.generation

        class ProjectBrain:
            name = "project-fixture"

            def chat(self, ctx):
                return {"reply": "我想分两步做。", "development": {"project": deepcopy(raw)}, "_generation": generation}

        result = cognition.chat_turn(self.pack, "请安排一下这项工作。", ProjectBrain(), request_id="project-chat")
        self.assertEqual(result["goalProject"]["status"], "accepted")
        self.assertIn("分阶段安排已记录", result["reply"])
        self.assertEqual(result["actions"], 0)
        before = self.contents()
        repeated = cognition.chat_turn(self.pack, "请安排一下这项工作。", ProjectBrain(), request_id="project-chat")
        self.assertEqual(repeated["goalProject"], result["goalProject"])
        self.assertEqual(self.contents(), before)

    def test_project_protocol_is_offered_only_in_private_context(self):
        self.assertIn("development.project", _development_contract({"_audience_id": "owner"}))
        self.assertNotIn("development.project", _development_contract({"_audience_id": "qq-group:123"}))

    def test_optional_project_protocol_can_yield_to_a_small_context_budget(self):
        ctx = {"_cfg": {"input_budget": 2048}}
        _, selected, report = context_window.fit(ctx, lambda value: {
            "user": "required message" + ("optional protocol" * 200 if value.get("goal_project_protocol", True) else "")})
        self.assertTrue(report["limited"])
        self.assertFalse(selected["goal_project_protocol"])
        self.assertNotIn("goal_project_protocol", ctx)
        self.assertNotIn("development.project", _development_contract({"goal_project_protocol": False}))


if __name__ == "__main__":
    unittest.main()
