"""Authored for user execution; isolated packs, local fixtures, no network."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import bonds, development, experience, facts, friends, learning, persona, relationships, requests
from seedbank.brain import _speaker, build_chat_prompt, create_stub_brain
from seedbank.bridge import Bridge
from seedbank.cognition import build_context, chat_turn, maybe_initiate, start_day, visit
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.util import SeedError, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class RelationshipsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="seedbank-relationships-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pack = self.root / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="relations",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        guard = patch("seedbank.semantic._request", side_effect=AssertionError("network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def edit(self, action, **data):
        payload = {"person_id": "owner", "reason": "用户记录具体情况", **data}
        return relationships.perform(self.pack, action, payload)["record"]

    def goal(self):
        return learning.perform(self.pack, "plan", {"title": "写一封具体的信", "skill": "表达",
                    "reason": "约定把事情说清", "next_step": "完成初稿",
                    "criteria": [{"text": "说明一件具体事情", "group": "信", "check": "feedback"}]})["goal_id"]

    def agreement(self, goal):
        return self.edit("agreement", goal_id=goal, criteria_id=learning.listing(self.pack, goal)["criteria"]["id"],
                         due_day=self.day["dayNo"])

    def result_with_feedback(self, goal):
        standard = learning.listing(self.pack, goal)["criteria"]
        result = learning.practice(self.pack, goal, "letter", "解释一件具体事情", create_stub_brain(), criteria_id=standard["id"])
        outcome = result["receipt"]["id"]
        learning.perform(self.pack, "feedback", {"goal_id": goal, "criteria_id": standard["id"], "outcome_id": outcome,
                         "expected": "", "ratings": {"c1": "met"}, "reason": "这次符合约定条件", "next_step": "以后继续尝试"})
        return outcome

    def test_read_only_and_model_notes_do_not_grant_consent(self):
        with patch("seedbank.bridge.create_brain", side_effect=AssertionError("no model")):
            self.assertTrue(Bridge(self.pack).handle({"op": "relationships"})["ok"])
        self.assertFalse(relationships.path(self.pack).exists())
        event = experience.record(self.pack, kind="conversation", text="昨天这件事让我不舒服", actor="用户",
                                  day=1, source="mind/experiences.jsonl", metadata={"person_id": "owner"})
        rows = relationships.apply_observations(self.pack, [{"person_id": "owner", "type": "tension",
                  "text": "我需要进一步了解对方的感受", "quote": "让我不舒服", "status": "resolved"}],
                  event=event, person_id="owner", runner="fixture")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin"], "model")
        self.assertNotIn("status", rows[0]["data"])
        self.assertEqual(relationships.context(self.pack)["issues"], [])
        self.assertIn("不能自动说对方失约", relationships.prompt_lines(relationships.context(self.pack)))
        self.assertEqual(relationships.apply_observations(self.pack, [{"person_id": "owner", "type": "tension",
                         "text": "虚构判断", "quote": "没有说过的话"}], event=event, person_id="owner", runner="fixture"), [])

    def test_unknown_speaker_does_not_inherit_owner_relationship(self):
        self.edit("note", type="reflection", text="用户希望解释具体一些")
        contexts = []

        class Brain:
            name = "stub-fixture"

            def chat(self, ctx):
                contexts.append(ctx)
                return {"reply": "我先了解一下你的意思。", "relationship_notes": [],
                        "fact_claims": [{"subject": "owner", "aspect": "居住地", "value": "杭州", "quote": "我住杭州"}]}

        result = chat_turn(self.pack, "我住杭州", Brain(), speaker="陌生访客")
        self.assertEqual(contexts[-1]["relationships"]["person_id"], "")
        self.assertEqual(contexts[-1]["relationships"]["notes"], [])
        self.assertEqual(contexts[-1]["bond"], {})
        self.assertEqual(result["factsAdded"], 0)
        self.assertEqual(relationships.context(self.pack)["interaction_count"], 0)

    def test_identified_speaker_and_same_name_remain_distinct_from_self(self):
        registered = relationships.perform(self.pack, "person", {"label": "初（朋友）"})["person_id"]
        chat_turn(self.pack, "这是朋友的发言", create_stub_brain(), speaker="初", person_id=registered)
        ctx = build_context(self.pack, self.day["dayNo"], self.day["date"], person_id=registered)
        entry = next(r for r in ctx["transcript"] if r["text"] == "这是朋友的发言")
        self.assertEqual(entry["person_id"], registered)
        self.assertIn(registered, _speaker(ctx, entry))
        self.assertEqual(ctx["relationships"]["interaction_count"], 1)
        self.assertEqual(relationships.context(self.pack)["interaction_count"], 0)
        self.assertEqual(bonds.familiarity_percent(self.pack), 0)

    def test_birth_identity_survives_move_and_same_names_do_not_merge(self):
        a, b = self.root / "甲.life", self.root / "乙.life"
        for file, seed in ((a, "one"), (b, "two")):
            hatch(file, ROOT / "eggs/open.egg", "同名", seed_override=seed, born_at_override="2026-11-01T00:00:00Z")
            visit(self.pack, file, brain=create_stub_brain(), note="用户转述的问候")
        visitors = friends.list_friends(self.pack)
        self.assertEqual(len(visitors), 2)
        self.assertNotEqual(visitors[0]["person_id"], visitors[1]["person_id"])
        moved = self.root / "搬家.life"
        shutil.copytree(a, moved)
        visit(self.pack, moved, brain=create_stub_brain())
        self.assertEqual(len(friends.list_friends(self.pack)), 2)
        self.assertEqual(friends.list_friends(self.pack)[0]["visit_count"], 2)
        ctx = relationships.context(self.pack, visitors[0]["person_id"])
        self.assertEqual(ctx["interaction_count"], 0)
        self.assertEqual(ctx["reported_inputs"], 2)
        with self.assertRaises(SeedError):
            friends.mourn_friend(self.pack, "同名", day=1)
        friends.mourn_friend(self.pack, visitors[0]["id"], day=1)
        self.assertEqual(friends.list_friends(self.pack)[1]["status"], "alive")

    def test_paused_spontaneous_messages_do_not_call_brain_even_when_forced(self):
        boundary = self.edit("boundary", proactive="paused")
        with patch("seedbank.cognition.create_brain", side_effect=AssertionError("no model")):
            self.assertIsNone(maybe_initiate(self.pack, force=True))
        self.assertFalse(relationships.may_initiate(self.pack))
        chat_turn(self.pack, "我主动来问一件事", create_stub_brain())
        self.assertFalse(relationships.may_initiate(self.pack))
        # A suppressed explanation must not silently re-enable contact.
        policy = MemoryPolicy([], experience.read(self.pack), [boundary["evidence"][0]["id"]])
        self.assertEqual(relationships.context(self.pack, policy=policy)["proactive"], "paused")
        with self.assertRaises(SeedError):
            self.edit("forget", target=boundary["key"], expected=boundary["id"])
        self.edit("boundary", proactive="allowed", expected=boundary["id"])
        self.assertTrue(relationships.may_initiate(self.pack))

    def test_overdue_is_unreviewed_and_fulfilment_needs_original_conditions(self):
        goal = self.goal()
        agreement = self.agreement(goal)
        self.assertEqual(relationships.assessment(self.pack, agreement, day=999)["state"], "due_for_review")
        with self.assertRaises(SeedError):
            self.edit("review", target=agreement["key"], expected=agreement["id"], status="fulfilled", completion_evidence={})
        outcome = self.result_with_feedback(goal)
        reviewed = self.edit("review", target=agreement["key"], expected=agreement["id"], status="fulfilled",
                             completion_evidence={"c1": outcome})
        self.assertTrue(relationships.assessment(self.pack, reviewed, day=999)["verified"])
        current = learning.listing(self.pack, goal)
        feedback = current["attempts"][0]["feedback"]
        learning.perform(self.pack, "feedback", {"goal_id": goal, "criteria_id": current["criteria"]["id"],
                         "outcome_id": outcome, "expected": feedback["id"], "ratings": {"c1": "not_met"},
                         "reason": "重新核对后认为尚未说清", "next_step": "补充具体说明"})
        self.assertEqual(relationships.assessment(self.pack, reviewed, day=999)["state"], "needs_review")
        self.assertEqual(relationships.view(self.pack)["visible"][reviewed["key"]]["data"]["status"], "fulfilled")

    def test_changed_conditions_do_not_reinterpret_old_commitment(self):
        goal = self.goal()
        agreement = self.agreement(goal)
        current = learning.listing(self.pack, goal)
        learning.perform(self.pack, "plan", {"goal_id": goal, "expected": current["goal"]["event_id"],
                         "title": "写一封具体的信", "skill": "表达", "reason": "协商新方向", "next_step": "重新写",
                         "criteria": [{"text": "解释另一件事"}]})
        self.assertEqual(relationships.assessment(self.pack, agreement, day=1)["state"], "conditions_changed")
        with self.assertRaises(SeedError):
            self.edit("review", target=agreement["key"], expected=agreement["id"], status="fulfilled", completion_evidence={})

    def test_issue_history_stale_edits_and_forgetting_dependencies(self):
        first = self.edit("issue", title="这次理解有分歧", status="open")
        revised = self.edit("issue", target=first["key"], expected=first["id"], title="这次理解有分歧",
                            status="trying", reason="重新说明并等待回应")
        prefix = relationships.path(self.pack).read_bytes()
        with self.assertRaises(SeedError):
            self.edit("issue", target=first["key"], expected=first["id"], title="改成已缓和", status="resolved")
        dependent = experience.record(self.pack, kind="thought", text="据此形成的解释", day=1,
                                      source="mind/experiences.jsonl", depends_on=[revised["evidence"][0]["id"]])
        self.edit("forget", target=revised["key"], expected=revised["id"])
        self.assertTrue(relationships.path(self.pack).read_bytes().startswith(prefix))
        self.assertEqual(relationships.context(self.pack)["issues"], [])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(dependent))
        self.assertEqual(len(relationships.listing(self.pack, history=True)["records"]), 3)

    def test_request_replay_and_interruption_resume_do_not_duplicate(self):
        payload = {"person_id": "owner", "type": "reflection", "text": "今天解释清楚了一件事", "reason": "用户记录"}
        first = relationships.perform(self.pack, "note", payload, request_id="once")
        replay = relationships.perform(self.pack, "note", payload, request_id="once")
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["record"], replay["record"])
        count = len(experience.read(self.pack))
        with patch("seedbank.relationships._append", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                relationships.perform(self.pack, "note", payload, request_id="resume")
        self.assertEqual(len(experience.read(self.pack)), count)
        self.assertEqual(requests.get(self.pack, "resume")["status"], "pending")
        response = Bridge(self.pack, "stub").handle({"op": "resume", "request_id": "resume"})
        self.assertTrue(response["ok"], response)
        self.assertEqual(len(relationships.read(self.pack)), 2)

    def test_corrupt_legacy_file_is_preserved(self):
        file = self.pack / "mind/friends.json"
        file.write_text('{"friends": "damaged"}', encoding="utf-8")
        original = file.read_bytes()
        with self.assertRaises(SeedError):
            friends.record_visit(self.pack, name="访客", day=1)
        self.assertEqual(file.read_bytes(), original)

    def test_relationship_edit_expires_continuity_and_eight_file_sample_is_legacy(self):
        baseline = persona.capture(self.pack)
        self.edit("note", type="reflection", text="新的相处理解")
        with patch("seedbank.persona.create_brain") as factory:
            report = persona.check(self.pack)
        factory.assert_not_called()
        self.assertIn("mind/relationships.jsonl", report["archive"]["changed"])
        baseline["sources"].pop("mind/relationships.jsonl")
        baseline["sources"].pop("mind/disclosure.jsonl")
        baseline["sources"].pop("mind/life_story.jsonl")
        baseline["sources"].pop("mind/media.jsonl")
        baseline["sample_digest"] = persona._sample_digest(baseline)
        write_json_atomic(self.pack / "mind/persona.json", baseline)
        self.assertEqual(persona.check(self.pack)["reason"], "legacy_baseline")


if __name__ == "__main__":
    unittest.main()
