"""User-run daily-choice regressions. Authored only; all packs/models are fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import actions, agency, backup, cognition, deliberation, development, experience, planning, requests
from seedbank.brain import _validate_chat_result, _validate_diary_result, _validate_initiate_result
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.util import append_memories, read_json

ROOT = Path(__file__).resolve().parents[2]


class Brain:
    name = "daily-choice-fixture"

    def __init__(self, result=None):
        self.result = result or {"reply": "我再想想。"}
        self.compositions = 0
        self.contexts = []

    def chat(self, ctx):
        self.contexts.append(deepcopy(ctx))
        return deepcopy(self.result)

    def compose(self, ctx):
        self.compositions += 1
        return {"title": "一次尝试", "text": "谢谢你陪我整理资料。"}

    def diary(self, ctx):
        return {"diary": "今天我选择留些空白，想清楚下一步。", "memories": [], **deepcopy(self.result)}


class DailyChoicesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="seedbank-daily-choices-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        for guard in (
            patch.dict(os.environ, {"HOME": str(self.folder / "home"),
                "USERPROFILE": str(self.folder / "home"), "SEEDBANK_LANG": "zh_CN"}),
            patch("seedbank.semantic._request", side_effect=AssertionError("No real service")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.pack = self.folder / "isolated.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="daily-choices",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = cognition.start_day(self.pack)
        self.input = experience.record(self.pack, kind="conversation", text="今天可以自己安排。",
            day=self.day["dayNo"], source=self.day["file"], actor="owner")
        self.ref = {"id": self.input["id"], "source": experience.source_of(self.input), "kind": "conversation"}
        self.first = self.goal("写一封感谢信")["data"]["id"]
        self.second = self.goal("整理一次自己的想法")["data"]["id"]
        agency.plan_for_day(self.pack, self.day["dayNo"])

    def goal(self, title, *, identifier="", status="active", next_step="完成一份初稿"):
        return development.apply_proposals(self.pack, {"goals": [{"id": identifier, "title": title,
            "next_step": next_step, "status": status, "reason": "练习把想法表达清楚", "evidence": ["current"]}]},
            day=self.day["dayNo"], source=self.day["file"], runner="fixture", current_evidence=[self.ref])[0]

    def context(self):
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        ctx["current_evidence"] = [self.ref]
        return ctx

    def proposal(self, mode="focus", goal=None, **extra):
        return {"mode": mode, "goal_id": (goal or self.second) if mode == "focus" else "",
                "next_step": "先安静整理想法" if mode == "focus" else "先留出一段空白",
                "reason": "今天想按自己的节奏来", "evidence": [], **extra}

    def choose(self, raw=None, *, ctx=None, generation=None):
        return deliberation.apply(self.pack, raw if raw is not None else self.proposal(),
            ctx=ctx or self.context(), day=self.day, generation=generation or {"runner": Brain.name, "fallback": False})

    def execute(self, brain, goal=""):
        return actions.execute(self.pack, [{"type": "compose", "kind": "letter", "goal_id": goal,
            "reason": "尝试写一封信"}], day=self.day, source=self.day["file"], brain=brain,
            memories=[], evidence=[self.ref])[0]

    def test_choice_selects_a_different_goal_and_survives_background_refresh(self):
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["goal_id"], self.first)
        selected = self.choose()["plan"]
        self.assertEqual(selected["goal_id"], self.second)
        self.assertTrue(deliberation.valid(self.pack, selected))
        self.goal("写一封感谢信", identifier=self.first, next_step="先列具体事例")
        refreshed = agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertEqual(refreshed["plan_id"], selected["plan_id"])
        self.assertEqual(read_json(agency.agency_path(self.pack))["plan_store"], planning.DECISION_FORMAT)
        self.assertEqual(planning.read(self.pack)[-1]["kind"], "decision")
        self.assertNotEqual(agency.plan_for_day(self.pack, self.day["dayNo"] + 1).get("origin"), "model")

    def test_rest_blocks_automatic_work_but_not_explicit_compose(self):
        selected = self.choose(self.proposal("rest"))["plan"]
        before = self.pack.joinpath("mind/body.json").read_bytes() if self.pack.joinpath("mind/body.json").exists() else None
        brain = Brain()
        receipt = self.execute(brain, self.first)
        self.assertEqual(receipt["data"]["status"], "blocked")
        self.assertEqual(brain.compositions, 0)
        self.assertEqual(development.current_state(self.pack)["skills"].get("compose", {}).get("attempts", 0), 0)
        after = self.pack.joinpath("mind/body.json").read_bytes() if self.pack.joinpath("mind/body.json").exists() else None
        self.assertEqual(after, before)
        self.assertIn(selected["decision_id"], {r["id"] for r in receipt["data"]["evidence"]})
        result = cognition.compose_work(self.pack, "letter", brain, day=self.day, goal_id=self.first)
        self.assertEqual(result["receipt"]["data"]["status"], "succeeded")
        self.assertEqual(brain.compositions, 1)
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["mode"], "rest")

    def test_focus_requires_selected_goal_and_open_allows_unbound_attempt(self):
        self.choose()
        brain = Brain()
        self.assertEqual(self.execute(brain, self.first)["data"]["status"], "blocked")
        self.assertEqual(self.execute(brain, self.second)["data"]["status"], "succeeded")
        self.choose(self.proposal("open"))
        self.assertEqual(self.execute(brain)["data"]["status"], "succeeded")
        self.assertFalse(agency.current_plan(self.pack, self.day["dayNo"])["done"])

    def test_noop_does_not_add_decision_and_runtime_refresh_preserves_rest(self):
        raw = self.proposal("rest")
        self.choose(raw)
        before = planning.path(self.pack).read_bytes()
        self.assertEqual(self.choose(raw)["status"], "unchanged")
        agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertEqual(planning.path(self.pack).read_bytes(), before)

    def test_changed_goal_requires_new_choice_and_ended_goal_is_not_replaced_by_another(self):
        original = self.choose()["plan"]
        self.goal("整理一次自己的想法", identifier=self.second, next_step="先区分事实和解释")
        self.assertEqual(agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)["plan_id"], original["plan_id"])
        self.assertEqual(self.execute(Brain(), self.second)["data"]["status"], "blocked")
        self.assertEqual(self.choose()["status"], "accepted")
        self.goal("整理一次自己的想法", identifier=self.second, status="paused")
        reconsider = agency.plan_for_day(self.pack, self.day["dayNo"], refresh=True)
        self.assertEqual(reconsider["goal_id"], "")
        self.assertNotEqual(reconsider.get("origin"), "model")

    def test_invalid_unshown_stale_fallback_and_guest_choices_do_not_change_schedule(self):
        before = planning.path(self.pack).read_bytes()
        cases = [[], {}, self.proposal(next_step=""), self.proposal(reason=""), self.proposal(evidence=["missing"]),
                 self.proposal("rest", goal_id=self.first), self.proposal(mode="unknown")]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.choose(raw)["status"], "rejected")
        hidden = self.context()
        hidden["development"]["goals"] = []
        self.assertEqual(self.choose(ctx=hidden)["status"], "rejected")
        guest = self.context()
        guest["_audience_id"] = "person:visitor"
        self.assertEqual(self.choose(ctx=guest)["status"], "rejected")
        self.assertEqual(self.choose(generation={"runner": "stub-v1", "fallback": True})["status"], "rejected")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        stale = self.context()
        self.goal("整理一次自己的想法", identifier=self.second, next_step="先停一停")
        self.assertEqual(self.choose(ctx=stale)["status"], "rejected")

    def test_trimmed_goal_list_is_used_by_chat_and_rejected_choice_blocks_actions(self):
        brain = Brain({"reply": "我想先安排今天。", "daily_plan": self.proposal(),
                       "_used_development": {"goals": []},
                       "actions": [{"type": "compose", "goal_id": self.second, "reason": "尝试"}]})
        result = cognition.chat_turn(self.pack, "今天做什么？", brain)
        self.assertEqual(result["planDecision"]["status"], "rejected")
        self.assertEqual(result["actionResults"][0]["data"]["status"], "blocked")
        self.assertEqual(brain.compositions, 0)

    def test_choice_can_follow_its_own_goal_revision_in_same_response(self):
        brain = Brain({"reply": "我会先修改下一步。", "daily_plan": self.proposal(), "development": {"goals": [{
            "id": self.second, "next_step": "先整理两个例子", "reason": "需要更具体", "evidence": ["current"]}]}})
        result = cognition.chat_turn(self.pack, "先具体一点。", brain)
        self.assertEqual(result["planDecision"]["status"], "accepted")
        self.assertEqual(result["planDecision"]["plan"]["goal_event_id"],
                         development.current_state(self.pack)["goals"][self.second]["event_id"])

    def test_silent_initiation_and_diary_can_record_choices(self):
        brain = Brain({"reply": "", "daily_plan": self.proposal("rest")})
        result = cognition.maybe_initiate(self.pack, brain, force=True)
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["planDecision"]["status"], "accepted")
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["mode"], "rest")
        cognition.run_days(self.pack, 1, Brain({"daily_plan": self.proposal("open")}))
        self.assertEqual(agency.current_plan(self.pack, self.day["dayNo"])["mode"], "open")

    def test_forgotten_choice_basis_is_hidden_and_not_reintroduced_by_initiative(self):
        memory = {"id": "m_choice_basis", "day": self.day["dayNo"], "kind": "thought", "text": "今天可以自己安排。",
                  "source": experience.source_of(self.input), "event_ids": [self.input["id"]]}
        append_memories(self.pack, [memory])
        selected = self.choose(self.proposal("rest", evidence=["current"]))["plan"]
        cognition.forget_memory(self.pack, memory["id"])
        self.assertFalse(deliberation.valid(self.pack, selected))
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertEqual(ctx["plan"], "")
        self.assertEqual(ctx["daily_choice"], {})
        brain = Brain({"reply": ""})
        cognition.maybe_initiate(self.pack, brain, force=True)
        self.assertEqual(brain.contexts[-1]["initiative"]["plan"], "")
        self.assertEqual(self.execute(Brain(), self.first)["data"]["status"], "blocked")

    def test_guest_context_never_receives_private_choice(self):
        self.choose(self.proposal("rest"))
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False,
                                      person_id="visitor", audience_id="person:visitor")
        self.assertEqual(ctx["plan"], "")
        self.assertNotIn("daily_choice", ctx)

    def test_altered_decision_event_is_not_treated_as_valid_choice(self):
        selected = self.choose(self.proposal("rest"))["plan"]
        rows = experience.read(self.pack)
        target = next(row for row in rows if row["id"] == selected["decision_id"])
        target["text"] = "被外部改写的说明"
        experience.path(self.pack).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        self.assertFalse(deliberation.valid(self.pack, selected))
        ctx = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        self.assertEqual(ctx["daily_choice"], {})
        self.assertEqual(self.execute(Brain(), self.first)["data"]["status"], "blocked")

    def test_choice_write_failure_rolls_back_chat_and_retry_keeps_one_decision(self):
        brain = Brain({"reply": "今天先留白。", "daily_plan": self.proposal("open")})
        before = planning.path(self.pack).read_bytes()
        config = agency.agency_path(self.pack).read_bytes()
        original = planning.choose

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("fixture after choice write")

        with patch("seedbank.deliberation.planning.choose", side_effect=fail):
            with self.assertRaises(OSError):
                cognition.chat_turn(self.pack, "怎样安排？", brain, request_id="daily-choice-retry")
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(agency.agency_path(self.pack).read_bytes(), config)
        self.assertTrue(requests.pending(self.pack))
        result = cognition.chat_turn(self.pack, "怎样安排？", brain, request_id="daily-choice-retry")
        self.assertEqual(result["planDecision"]["status"], "accepted")
        before = planning.path(self.pack).read_bytes()
        replay = cognition.chat_turn(self.pack, "怎样安排？", brain, request_id="daily-choice-retry")
        self.assertTrue(replay["replayed"])
        self.assertEqual(planning.path(self.pack).read_bytes(), before)
        self.assertEqual(sum(r["kind"] == "decision" for r in planning.read(self.pack)), 1)

    def test_model_decision_survives_backup_and_marker_is_not_downgraded(self):
        selected = self.choose()["plan"]
        agency.save_agency(self.pack, {"plans": []})
        self.assertEqual(read_json(agency.agency_path(self.pack))["plan_store"], planning.DECISION_FORMAT)
        archive = backup.create(self.pack)
        restored = self.folder / "restored.life"
        backup.restore(archive["file"], restored)
        self.assertTrue(deliberation.valid(restored, agency.current_plan(restored, self.day["dayNo"])))
        self.assertEqual(agency.current_plan(restored, self.day["dayNo"])["decision_id"], selected["decision_id"])

    def test_result_adapters_preserve_daily_choice(self):
        raw = self.proposal("rest")
        for validator, result in ((_validate_chat_result, {"reply": "稍后再做"}),
                                  (_validate_initiate_result, {"reply": ""}),
                                  (_validate_diary_result, {"diary": "今天先休息。", "mood": "平静"})):
            with self.subTest(validator=validator.__name__):
                self.assertEqual(validator({**result, "daily_plan": raw})["daily_plan"], raw)


if __name__ == "__main__":
    unittest.main()
