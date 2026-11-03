"""User-run regressions only: temporary packs, fixed brains and mocked transport."""
from copy import deepcopy
import json
from unittest.mock import Mock, patch
import unittest

import test_daily_choices as fixtures
from seedbank import actions, agency, body, cognition, development, disclosure, experience, planning, relationships, requests
from seedbank.durability import RecoveryRequired
from seedbank.brain import _speaker
from seedbank.qq import QQAdapter
from seedbank.util import SeedError, append_memories
from test_qq import group_event, private_event


class GuestBrain(fixtures.Brain):
    name = "stub-cross-channel-fixture"

    def compose(self, ctx):
        self.contexts.append(deepcopy(ctx))
        return super().compose(ctx)


class CrossChannelActionsTest(unittest.TestCase):
    goal = fixtures.DailyChoicesTest.goal
    context = fixtures.DailyChoicesTest.context
    proposal = fixtures.DailyChoicesTest.proposal
    choose = fixtures.DailyChoicesTest.choose

    def setUp(self):
        fixtures.DailyChoicesTest.setUp(self)
        self.visitor = relationships.perform(self.pack, "person", {"label": "访客甲"})["person_id"]

    def action(self, kind="compose", **extra):
        return {"type": kind, "kind": "letter", "reason": "尝试写一段文字", **extra}

    def brain(self, action=None):
        return GuestBrain({"reply": "我准备尝试。", "actions": [action or self.action()]})

    def chat(self, brain=None, *, person="", audience="qq-group:123", request=""):
        return cognition.chat_turn(self.pack, "尝试整理一下。", brain or self.brain(), "访客",
            person_id=person, audience_id=audience, request_id=request)

    def test_group_transcript_preserves_channel_ids_and_runtime_receipt_role(self):
        other = relationships.perform(self.pack, "person", {"label": "另一个同名访客"})["person_id"]
        for person, text in ((self.visitor, "甲的输入"), (other, "乙的输入")):
            cognition.chat_turn(self.pack, text, self.brain(), "同名", person_id=person, audience_id="qq-group:123")
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"],
            use_semantic=False, person_id=self.visitor, audience_id="qq-group:123")
        for person, text in ((self.visitor, "甲的输入"), (other, "乙的输入")):
            row = next(r for r in ctx["transcript"] if r["text"] == text)
            self.assertEqual(row.get("person_id"), person)
            self.assertEqual(row["interaction_kind"], "direct")
            self.assertIn(person, _speaker(ctx, row))
        reports = [r for r in ctx["transcript"] if r.get("metadata", {}).get("runner") == "runtime"]
        self.assertTrue(reports)
        self.assertTrue(all(r["who"] == "runtime" for r in reports))
        replies = [r for r in ctx["transcript"] if r["text"] == "我准备尝试。"]
        self.assertEqual(len(replies), 2)
        self.assertTrue(all(r["who"] == "fish" and "person_id" not in r for r in replies))

    def assert_private_plan_absent(self, value, selected):
        raw = json.dumps(value, ensure_ascii=False)
        for secret in (selected["plan"], selected["reason"], selected["decision_id"], selected["plan_id"]):
            self.assertNotIn(secret, raw)

    def external_goal(self, title="小组交流中的写作目标"):
        event = experience.record(self.pack, kind="conversation", text=title, day=self.day["dayNo"],
            source=self.day["file"], actor="访客", metadata=disclosure.stamp("qq-group:123"))
        return development.apply_proposals(self.pack, {"goals": [{"title": title, "next_step": "写一个例子",
            "reason": "整理交流中的想法", "evidence": ["current"]}]}, day=self.day["dayNo"],
            source=experience.source_of(event), runner="fixture", generation=disclosure.stamp("qq-group:123"),
            current_evidence=[{"id": event["id"], "source": experience.source_of(event), "kind": "conversation"}])[0]["data"]["id"]

    def test_rest_applies_to_person_group_and_owner_group_without_private_details(self):
        selected = self.choose(self.proposal("rest", next_step="PRIVATE_REST_PLAN", reason="PRIVATE_REST_REASON"))["plan"]
        for person, audience in ((self.visitor, "person:" + self.visitor), ("", "qq-group:123"), ("owner", "qq-group:123")):
            with self.subTest(person=person, audience=audience):
                brain = self.brain()
                with patch("seedbank.actions.body.spend", wraps=body.spend) as spend:
                    result = self.chat(brain, person=person, audience=audience)
                self.assertEqual(brain.compositions, 0)
                self.assertEqual([call.args[1] for call in spend.call_args_list], ["chat"])
                receipt = result["actionResults"][0]
                self.assertEqual(receipt["data"]["status"], "blocked")
                self.assertNotIn("plan_reference", receipt["data"])
                self.assertIn("未执行", result["reply"])
                self.assertTrue(result["actionReportEventIds"])
                self.assert_private_plan_absent(result, selected)
                self.assert_private_plan_absent(brain.contexts, selected)
                policy = disclosure.policy_for(self.pack, audience, person)
                self.assertTrue(all(policy.allows(policy.nodes[ref]) for ref in result["actionReportEventIds"]))
        self.assertEqual(development.current_state(self.pack)["skills"], {})

    def test_reflection_is_blocked_before_creating_a_file(self):
        self.choose(self.proposal("rest"))
        brain = self.brain(self.action("reflect", memory_ids=[], text="不应保存的解释"))
        result = self.chat(brain)
        self.assertEqual(result["actionResults"][0]["data"]["status"], "blocked")
        self.assertEqual(list(self.pack.glob("art/reflections/*.md")), [])

    def test_focus_allows_visible_matching_goal_but_blocks_other_visible_goal(self):
        goal = self.external_goal()
        self.choose(self.proposal(goal=goal))
        brain = self.brain(self.action(goal_id=goal))
        result = self.chat(brain)
        self.assertEqual(brain.compositions, 1)
        self.assertEqual(result["actionResults"][0]["data"]["status"], "succeeded")
        self.assertIn("已保存作品", result["reply"])
        self.assertNotIn("plan_reference", result["actionResults"][0]["data"])
        self.choose(self.proposal(goal=self.first))
        other = self.chat(self.brain(self.action(goal_id=goal)))
        self.assertEqual(other["actionResults"][0]["data"]["status"], "blocked")

    def test_runtime_schedule_and_open_choice_allow_external_work(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                if explicit:
                    self.choose(self.proposal("open"))
                result = self.chat()
                self.assertEqual(result["actionResults"][0]["data"]["status"], "succeeded")
                self.assertNotIn("plan_reference", result["actionResults"][0]["data"])

    def test_unknown_goal_is_checked_before_private_schedule(self):
        self.choose(self.proposal(goal=self.first))
        for goal in (self.first, "g_unrelated_guess"):
            with self.subTest(goal=goal), patch("seedbank.deliberation.blocked_reason", side_effect=AssertionError("private schedule probe")):
                result = self.chat(self.brain(self.action(goal_id=goal)))
            self.assertEqual(result["actionResults"][0]["data"]["status"], "blocked")
            self.assertEqual(result["actionResults"][0]["data"]["detail"], "本次未执行这项操作。")

    def test_explicit_user_work_still_works_while_resting(self):
        self.choose(self.proposal("rest"))
        result = cognition.compose_work(self.pack, "letter", fixtures.Brain(), day=self.day)
        self.assertEqual(result["receipt"]["data"]["status"], "succeeded")
        self.assertEqual(result["receipt"]["data"]["plan_reference"]["execution"], "requested")
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["mode"], "rest")

    def test_external_proposal_cannot_replace_private_choice(self):
        selected = self.choose(self.proposal("rest"))["plan"]
        brain = self.brain()
        brain.result["daily_plan"] = self.proposal("open")
        result = self.chat(brain)
        self.assertEqual(result["planDecision"]["status"], "rejected")
        self.assertEqual(result["actionResults"][0]["data"]["status"], "blocked")
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["plan_id"], selected["plan_id"])

    def test_pending_choice_survives_refresh_and_requires_new_choice(self):
        self.choose(self.proposal(goal=self.second))
        self.goal("整理一次自己的想法", identifier=self.second, status="paused")
        waiting = agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertTrue(waiting["awaiting_choice"])
        self.goal("写一封感谢信", identifier=self.first, next_step="先列两个例子")
        self.assertEqual(agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)["plan_id"], waiting["plan_id"])
        self.assertTrue(self.context()["choice_pending"])
        self.assertEqual(self.chat()["actionResults"][0]["data"]["status"], "blocked")
        own = actions.execute(self.pack, [self.action()], day=self.day, source=self.day["file"], brain=fixtures.Brain(), memories=[])
        self.assertEqual(own[0]["data"]["status"], "blocked")
        self.choose(self.proposal("open"))
        self.assertFalse(self.context()["choice_pending"])
        self.assertEqual(self.chat()["actionResults"][0]["data"]["status"], "succeeded")

    def test_earlier_waiting_record_is_honored_without_migration(self):
        waiting = planning.choose(self.pack, {"day": self.day["dayNo"], "plan": "等待重新选择",
            "reason": "旧目标已经变化", "goal_id": "", "done": False},
            legacy=agency.load_agency(self.pack)["plans"], trigger="decision_basis_changed")
        before = planning.path(self.pack).read_bytes()
        self.assertTrue(planning.awaiting_choice(self.pack, waiting))
        self.assertEqual(agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)["plan_id"], waiting["plan_id"])
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(self.chat()["actionResults"][0]["data"]["status"], "blocked")
        self.assertFalse(planning.awaiting_choice(self.pack, agency.plan_for_day(self.pack, self.day["dayNo"] + 1)))

    def test_forgetting_basis_does_not_disclose_it_or_release_the_hold(self):
        append_memories(self.pack, [{"id": "m_private_choice", "day": self.day["dayNo"], "kind": "thought",
            "text": "PRIVATE_BASIS", "source": experience.source_of(self.input), "event_ids": [self.input["id"]]}])
        selected = self.choose(self.proposal("rest", next_step="PRIVATE_REST", evidence=["current"]))["plan"]
        cognition.forget_memory(self.pack, "m_private_choice")
        self.assertEqual(self.chat()["actionResults"][0]["data"]["status"], "blocked")
        agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertTrue(self.context()["choice_pending"])
        result = self.chat()
        self.assertEqual(result["actionResults"][0]["data"]["status"], "blocked")
        self.assert_private_plan_absent(result, selected)

    def test_failure_diagnostics_never_enter_external_receipt_or_report(self):
        self.choose(self.proposal("open"))
        brain = self.brain()
        with patch.object(brain, "compose", side_effect=OSError("PRIVATE_DISK_PATH_AND_DETAIL")):
            result = self.chat(brain)
        self.assertEqual(result["actionResults"][0]["data"]["status"], "failed")
        self.assertNotIn("PRIVATE_DISK_PATH_AND_DETAIL", json.dumps(result))
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], person_id="", audience_id="qq-group:123", use_semantic=False)
        self.assertNotIn("PRIVATE_DISK_PATH_AND_DETAIL", json.dumps(ctx))

    def test_replay_rechecks_report_sources_even_when_original_reply_still_allowed(self):
        self.choose(self.proposal("open"))
        brain = self.brain()
        first = self.chat(brain, request="external-report-replay")
        replay = self.chat(brain, request="external-report-replay")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["reply"], first["reply"])
        self.assertEqual(brain.compositions, 1)
        created = next(r for r in first["actionResults"][0]["data"]["evidence"] if r["kind"] == "creation")
        append_memories(self.pack, [{"id": "m_result_to_forget", "day": self.day["dayNo"], "kind": "thought",
            "text": "the saved creation", "source": created["source"], "event_ids": [created["id"]]}])
        cognition.forget_memory(self.pack, "m_result_to_forget")
        policy = disclosure.policy_for(self.pack, "qq-group:123", "")
        self.assertTrue(policy.allows(policy.nodes[first["responseEventId"]]))
        self.assertFalse(policy.allows(policy.nodes[first["actionReportEventIds"][0]]))
        with self.assertRaises(SeedError):
            self.chat(brain, request="external-report-replay")
        self.assertEqual(brain.compositions, 1)

    def test_report_write_failure_rolls_back_action_and_retry_keeps_one_receipt(self):
        self.choose(self.proposal("open"))
        brain = self.brain()
        before = development.events(self.pack)
        original = cognition.append_transcript

        def fail(pack, day, entries, **kwargs):
            result = original(pack, day, entries, **kwargs)
            if any(row.get("metadata", {}).get("action_outcome_id") for row in entries):
                raise OSError("fixture after report write")
            return result

        with patch("seedbank.cognition.append_transcript", side_effect=fail), self.assertRaises(OSError):
            self.chat(brain, request="report-write-retry")
        self.assertEqual(development.events(self.pack), before)
        self.assertTrue(requests.pending(self.pack))
        result = self.chat(brain, request="report-write-retry")
        replay = self.chat(brain, request="report-write-retry")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["actionReportEventIds"], result["actionReportEventIds"])
        self.assertEqual(len(development.load_development(self.pack)["outcomes"]), 1)

    def test_recovery_required_stops_request_instead_of_becoming_a_public_failure(self):
        self.choose(self.proposal("rest"))
        with patch("seedbank.deliberation._private_blocked_reason", side_effect=RecoveryRequired("fixture recovery")):
            with self.assertRaises(RecoveryRequired):
                self.chat(request="gate-recovery")
        self.assertEqual(development.load_development(self.pack)["outcomes"], [])

    def test_qq_receives_the_report_with_mocked_sender_only(self):
        selected = self.choose(self.proposal("rest", next_step="PRIVATE_QQ_PLAN"))["plan"]
        brain, sender, bridge = self.brain(), Mock(), Mock()
        sender.send_group.return_value = sender.send_private.return_value = {"status": "ok", "retcode": 0}
        bridge.call.side_effect = lambda op, **kw: cognition.chat_turn(self.pack, kw["text"], brain, kw["speaker"],
            person_id=kw["person_id"], audience_id=kw["audience_id"])
        adapter = QQAdapter(str(self.pack), "7", ["123"], bridge=bridge, sender=sender, log=lambda value: None)
        result = adapter.handle(group_event(123, 7))
        self.assertTrue(result["ok"])
        self.assertIn("[运行器回执]", result["reply"])
        self.assertIn("未执行", result["reply"])
        self.assertEqual(sender.send_group.call_args.args[1], result["reply"])
        self.assert_private_plan_absent(result, selected)
        own = adapter.handle(private_event(7))
        self.assertTrue(own["ok"])
        self.assertIn("[运行器回执]", own["reply"])
        self.assertIn("暂不自动", own["reply"])
        self.assertEqual(sender.send_private.call_args.args[1], own["reply"])


if __name__ == "__main__":
    unittest.main()
