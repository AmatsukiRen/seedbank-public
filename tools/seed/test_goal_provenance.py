"""User-run checks for goal provenance; temporary packs, offline brains only."""
from copy import deepcopy
import unittest

import test_learning as fixtures
from seedbank import cognition, development, experience, goal_provenance, learning
from seedbank.memory_state import MemoryPolicy


class GoalBrain:
    name = "provenance-fixture"

    def __init__(self, proposal, *, quiet=False, generation=None):
        self.proposal = proposal
        self.quiet = quiet
        self.generation = generation or {}

    def chat(self, ctx):
        return {"reply": "" if self.quiet else "我想把这件事记作一个目标。",
                "development": {"goals": [deepcopy(self.proposal)]},
                "_generation": dict(self.generation)}

    def diary(self, ctx):
        return {"diary": "今天我重新考虑了自己的打算。",
                "development": {"goals": [deepcopy(self.proposal)]},
                "_generation": dict(self.generation)}


class GoalProvenanceTest(unittest.TestCase):
    setUp = fixtures.LearningTest.setUp
    plan = fixtures.LearningTest.plan
    listing = fixtures.LearningTest.listing

    def proposal(self, **patch):
        return {"title": "整理纸船的故事", "next_step": "先记下构想", "reason": "我对这个构想感兴趣",
                "evidence": ["current"], **patch}

    def goals(self):
        return development.current_state(self.pack)["goals"]

    def test_conversation_cannot_claim_an_initiative_trigger(self):
        cognition.chat_turn(self.pack, "可以想想纸船的故事。", GoalBrain(
            self.proposal(), generation={"proposal_activity": "initiative"}))
        goal = next(iter(self.goals().values()))
        self.assertEqual(goal["provenance"]["first"]["kind"], "conversation")
        self.assertEqual(goal["provenance"]["first"], goal["provenance"]["latest"])
        self.assertEqual(development.events(self.pack)[0]["data"]["origin"], "model")

    def test_quiet_scheduled_goal_keeps_actual_formation_event(self):
        event = experience.record(self.pack, kind="conversation", text="纸船让我想到一些故事。",
                                  source=self.day["file"], actor="owner", day=self.day["dayNo"])
        # The ordinary builder may return dialogue in transcript instead of
        # evidence. Use a real sourced memory so the proposal is actually shown.
        from seedbank.util import append_memories
        memory = {"id": "m_goal_source", "day": self.day["dayNo"], "at": event["recorded_at"],
                  "kind": "conversation", "text": event["text"], "importance": 0.8, "tags": [],
                  "source": experience.source_of(event), "event_ids": [event["id"]], "runner": "user"}
        append_memories(self.pack, [memory])
        result = cognition.maybe_initiate(self.pack,
            GoalBrain(self.proposal(evidence=[memory["id"]]), quiet=True),
            now=f"{self.day['date']}T16:00:00+08:00")
        self.assertEqual(result["reply"], "")
        goal = next(iter(self.goals().values()))
        self.assertEqual(goal["provenance"]["first"]["kind"], "initiative")
        self.assertIn(memory["id"], goal["provenance"]["first"]["dependencies"])

    def test_forced_initiative_is_not_labelled_as_normal_scheduling(self):
        cognition.maybe_initiate(self.pack, GoalBrain(self.proposal()), force=True)
        goal = next(iter(self.goals().values()))
        self.assertEqual(goal["provenance"]["first"]["kind"], "forced_initiative")

    def test_diary_records_its_own_trigger(self):
        cognition.run_days(self.pack, 1, GoalBrain(self.proposal()))
        goal = next(iter(self.goals().values()))
        self.assertEqual(goal["provenance"]["first"]["kind"], "diary")

    def test_staged_goal_proposal_uses_the_actual_conversation_trigger(self):
        class ProjectBrain(GoalBrain):
            def chat(self, ctx):
                result = super().chat(ctx)
                result["development"] = {"project": {"title": "整理再表达", "reason": "先弄清材料",
                    "evidence": ["current"], "stages": [
                        {"key": "notes", "title": "整理材料", "next_step": "列出具体事情", "skill": "表达",
                         "criteria": [{"text": "材料明确", "group": "材料", "check": "feedback"}], "after": []},
                        {"key": "letter", "title": "写一封信", "next_step": "根据材料写信", "skill": "表达",
                         "criteria": [{"text": "感谢明确", "group": "信", "check": "feedback"}], "after": [{"stage": "notes"}]}]}}
                return result

        result = cognition.chat_turn(self.pack, "可以先整理材料，再写信。", ProjectBrain(
            self.proposal(), generation={"model": "test-only", "fallback": False}))
        self.assertEqual(result["goalProject"]["status"], "accepted", result["goalProject"])
        self.assertEqual(len(self.goals()), 2)
        for goal in self.goals().values():
            self.assertEqual(goal["provenance"]["first"]["kind"], "conversation")

    def test_user_created_goal_stays_user_created_after_model_revision(self):
        identifier = self.plan()
        before = (self.pack / "mind/development.jsonl").read_bytes()
        first = self.goals()[identifier]["provenance"]["first"]
        cognition.chat_turn(self.pack, "先整理今天的帮助。", GoalBrain(self.proposal(
            id=identifier, title=self.goals()[identifier]["title"], next_step="先整理今天的帮助")))
        goal = self.goals()[identifier]
        self.assertEqual(goal["provenance"]["first"], first)
        self.assertEqual(first["kind"], "user")
        self.assertEqual(goal["provenance"]["latest"]["kind"], "conversation")
        self.assertTrue((self.pack / "mind/development.jsonl").read_bytes().startswith(before))

    def test_manual_revision_keeps_model_formation_and_does_not_persist_projection(self):
        cognition.chat_turn(self.pack, "想想纸船的故事。", GoalBrain(self.proposal()))
        goal = next(iter(self.goals().values()))
        original = deepcopy(goal["provenance"]["first"])
        self.plan(goal_id=goal["id"], expected=goal["event_id"], title=goal["title"], next_step="写下故事概要")
        changed = self.goals()[goal["id"]]
        self.assertEqual(changed["provenance"]["first"], original)
        self.assertEqual(changed["provenance"]["latest"]["kind"], "user")
        self.assertNotIn("provenance", development.events(self.pack)[-1]["data"])
        self.assertNotEqual(original["event_id"], changed["provenance"]["latest"]["event_id"])

    def test_legacy_model_origin_is_not_evidence_of_activity(self):
        development.apply_proposals(self.pack, {"goals": [self.proposal()]},
            day=self.day["dayNo"], source=self.day["file"], runner="legacy-model")
        goal = next(iter(self.goals().values()))
        self.assertEqual(goal["provenance"]["first"]["kind"], "unrecorded")

    def test_fallback_is_not_reported_as_a_model_goal_decision(self):
        cognition.chat_turn(self.pack, "想想纸船。", GoalBrain(self.proposal(), generation={"fallback": True}))
        goal = next(iter(self.goals().values()))
        self.assertEqual(goal["provenance"]["first"]["kind"], "fixed")

    def test_unavailable_formation_hides_its_metadata_and_dependencies(self):
        identifier = self.plan()
        row = development.events(self.pack)[0]
        policy = MemoryPolicy.load(self.pack)
        policy.blocked.update(ref["id"] for ref in row["data"]["evidence"])
        projected = goal_provenance.describe(row, policy)
        self.assertEqual(projected, {"kind": "unavailable"})
        self.assertNotIn(identifier, str(projected))

    def test_prompt_records_activity_without_claiming_independent_motivation(self):
        identifier = self.plan()
        cognition.chat_turn(self.pack, "先整理帮助。", GoalBrain(self.proposal(
            id=identifier, title=self.goals()[identifier]["title"])))
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        first = self.goals()[identifier]["provenance"]["first"]
        self.assertTrue(set(first["dependencies"]) <= set(cognition._context_dependencies(ctx)))
        prompt = development.prompt_lines(ctx["development"], compact=True)
        self.assertIn("first=user", prompt)
        self.assertIn("latest=conversation", prompt)
        self.assertIn("not proof of independent motivation", prompt)


if __name__ == "__main__":
    unittest.main()
