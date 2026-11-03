"""User-run regressions only. Temporary life packs and local fixture brains."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedbank import development, experience, learning, requests
from seedbank.brain import RemoteBrain, build_chat_prompt, build_compose_prompt, create_stub_brain
from seedbank.bridge import Bridge
from seedbank.cognition import build_context, chat_turn, maybe_initiate, read_transcript, start_day
from seedbank.context_window import fit
from seedbank.memory_state import MemoryPolicy
from seedbank.pack import hatch
from seedbank.util import SeedError, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class FixtureBrain:
    name = "fixture"

    def __init__(self):
        self.calls = []

    def compose(self, ctx):
        self.calls.append(deepcopy(ctx))
        return {"title": "谢谢", "text": "谢谢你昨天陪我整理材料。我很珍惜这份帮助。",
                "_generation": {"runner": "fixture", "model": "test-only", "fallback": False}}


class LearningTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="seedbank-learning-")
        self.addCleanup(temp.cleanup)
        self.pack = Path(temp.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="learning",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)
        self.brain = FixtureBrain()

    def plan(self, items=None, **extra):
        payload = {"title": "写一封具体的感谢信", "skill": "具体表达", "reason": "练习说清感谢的事情",
                   "next_step": "先写一封信", "criteria": items or [{"text": "提到具体帮助", "group": "信", "check": "feedback"}], **extra}
        return learning.perform(self.pack, "plan", payload)["goal_id"]

    def listing(self, goal):
        return learning.listing(self.pack, goal)

    def practice(self, goal, *, identifier="", brain=None):
        return learning.practice(self.pack, goal, "letter", "感谢昨天整理材料的帮助", brain or self.brain,
                                 request_id=identifier, criteria_id=self.listing(goal)["criteria"]["id"])

    def review(self, goal, outcome, ratings=None, **extra):
        data = self.listing(goal)
        old = next((r["feedback"] for r in data["attempts"] if r["id"] == outcome), {})
        payload = {"goal_id": goal, "criteria_id": data["criteria"]["id"], "outcome_id": outcome,
                   "expected": old.get("id", ""), "ratings": ratings or {"c1": "met"},
                   "reason": "写到了整理材料这件事", "next_step": "下一次把感受说得更具体", **extra}
        return learning.perform(self.pack, "feedback", payload)["record"]

    def test_read_only_listing_never_calls_a_model(self):
        with patch("seedbank.semantic._request", side_effect=AssertionError("network forbidden")):
            self.assertEqual(learning.listing(self.pack)["attempts"], [])
            self.assertTrue(Bridge(self.pack, "stub").handle({"op": "learning"})["ok"])
        self.assertFalse(learning.path(self.pack).exists())

    def test_quiet_initiative_saves_sourced_strategy_without_speaking(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        feedback = self.review(goal, outcome, next_step="把感谢的事直接说清，不补写经历")
        before_dialogue = read_transcript(self.pack, self.day["dayNo"])
        def transport(cfg, system, user):
            self.assertIn(feedback["id"], system + user)
            return json.dumps({"reply": "", "learning_updates": [{"feedback_id": feedback["id"],
                "text": "先说素材中明确的帮助，不增加没有来源的细节。",
                "expected_result": "下一份感谢文字能指出具体帮助且没有编造经历。",
                "transfer": {"applies_when": "根据给定素材表达感谢", "avoid_when": "明确要求虚构故事"}}]}, ensure_ascii=False)

        result = maybe_initiate(self.pack, RemoteBrain("quiet-learning-fixture", transport),
                                now=f"{self.day['date']}T16:00:00+08:00")
        adjustment = learning.view(self.pack)["adjustments"].get(feedback["id"])
        self.assertIsNotNone(adjustment, "A silent decision must not discard its sourced learning proposal")
        self.assertEqual(adjustment["origin"], "model")
        self.assertEqual(adjustment["data"]["transfer"]["avoid_when"], "明确要求虚构故事")
        self.assertEqual(read_transcript(self.pack, self.day["dayNo"]), before_dialogue)
        self.assertEqual(result["reply"], "")
        self.assertEqual(result["learningChanges"], 1)
        self.assertEqual(result["actionResults"], [])
        next_goal = self.plan(title="写一段合作回顾", items=[
            {"text": "说清合作中的具体帮助", "group": "回顾", "check": "feedback"}])
        next_attempt = self.practice(next_goal)
        lessons = self.brain.calls[-1]["practice"]["lessons"]
        self.assertEqual(lessons[0]["id"], adjustment["id"])
        self.assertEqual(lessons[0]["data"]["transfer"]["avoid_when"], "明确要求虚构故事")
        self.assertIn(adjustment["id"], next_attempt["receipt"]["data"]["practice"]["lesson_ids"])

    def test_quiet_initiative_rejects_unseen_feedback_without_inventing_speech(self):
        class QuietLearner:
            name = "quiet-learning-fixture"

            def chat(self, ctx):
                return {"reply": "", "learning_updates": [{"feedback_id": "unseen-feedback",
                    "text": "没有依据的策略", "expected_result": "不能记录为已学习"}]}

        before = experience.read(self.pack)
        result = maybe_initiate(self.pack, QuietLearner(), now=f"{self.day['date']}T16:00:00+08:00")
        self.assertEqual(learning.view(self.pack)["adjustments"], {})
        self.assertEqual(experience.read(self.pack), before)
        self.assertEqual(result["learningChanges"], 0)
        self.assertEqual(result["reply"], "")

    def test_default_budget_supplies_previous_feedback_to_next_creator(self):
        goal = self.plan([
            {"text": "感谢青禾修好蓝色风铃，不添加素材外的经历。", "group": "信", "check": "feedback"},
            {"text": "正文不超过80字，第一句直接感谢。", "group": "信", "check": "feedback"}])
        outcome = self.practice(goal)["receipt"]["id"]
        correction = "下一版用自然的两句话，不要使用特此或致谢。"
        feedback = self.review(goal, outcome, {"c1": "met", "c2": "met"}, next_step=correction)
        prompts = []

        def transport(cfg, system, user):
            prompts.append((system, user))
            return json.dumps({"title": "谢谢", "text": "谢谢你修好风铃。我很珍惜这份帮助。"}, ensure_ascii=False)

        result = self.practice(goal, brain=RemoteBrain("openai-compatible", transport))
        self.assertTrue(result["succeeded"])
        self.assertIn(correction, prompts[-1][1])
        self.assertIn(feedback["id"], result["receipt"]["data"]["practice"]["feedback_ids"])
        self.assertFalse(result["receipt"]["data"]["generation"]["fallback"])

    def test_compact_practice_keeps_feedback_and_does_not_mutate_audit_records(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        self.review(goal, outcome, {"c1": "not_met"}, reason="没有体现明确帮助", next_step="不要添加素材外事件")
        data = learning.for_goal(self.pack, goal)
        generation = data["feedback"][0]["data"]["generation"]
        generation.update(context={"input_bytes": 15000, "limited": True},
                          context_dependencies=["runtime-dependency-" + str(i) for i in range(100)],
                          strategy_choices={"state": "not_reported", "candidate_ids": ["strategy-fixture"]},
                          fallback=True, fallback_reason="fixture-error")
        before = deepcopy(data)
        rendered = learning.prompt_lines([data], compact=True)
        supplied = json.loads(rendered.rsplit("\n", 1)[-1])[0]
        self.assertEqual(data, before)
        self.assertEqual(supplied["criteria"], data["criteria"])
        self.assertEqual(supplied["readiness"], data["readiness"])
        feedback = supplied["feedback"][0]
        self.assertEqual(feedback["id"], data["feedback"][0]["id"])
        self.assertEqual(feedback["evidence"], data["feedback"][0]["evidence"])
        self.assertEqual(feedback["data"]["ratings"], {"c1": "not_met"})
        self.assertEqual(feedback["data"]["next_step"], "不要添加素材外事件")
        projected = feedback["data"]["generation"]
        self.assertNotIn("context", projected)
        self.assertNotIn("context_dependencies", projected)
        self.assertEqual(projected, {key: value for key, value in generation.items()
                                     if key not in ("context", "context_dependencies")})

    def test_compact_feedback_deduplicates_only_matching_choice_report(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        self.review(goal, outcome)
        data = learning.for_goal(self.pack, goal)
        before = deepcopy(data)
        supplied = json.loads(learning.prompt_lines([data], compact=True).rsplit("\n", 1)[-1])[0]
        original = data["feedback"][0]
        shown = supplied["feedback"][0]
        self.assertNotIn("strategy_choices", shown["data"]["generation"])
        self.assertEqual(shown["attempt_choices"], original["attempt_choices"])
        for key, value in original["data"]["generation"]["strategy_choices"].items():
            self.assertEqual(shown["attempt_choices"][key], value)
        self.assertEqual(shown["evidence"], original["evidence"])
        self.assertEqual(data, before)

    def test_chat_keeps_citable_original_with_existing_practice_history(self):
        goal = self.plan()
        for _ in range(4):
            outcome = self.practice(goal)["receipt"]["id"]
            self.review(goal, outcome)

        class DialogueBrain:
            name = "fixture"
            def chat(self, ctx):
                return {"reply": "这些是先前回复的解释，不能代替原始素材。" * 40, "memory_writes": []}

        original = "独立创作设定：主角洛川在青石图书馆整理旧地图。"
        chat_turn(self.pack, original, DialogueBrain())
        for _ in range(3):
            chat_turn(self.pack, "先只记下素材，不要创作。", DialogueBrain())
        context = build_context(self.pack, self.day["dayNo"], self.day["date"],
                                "请更正主角名字：是洛杉，原来名字写错了，不是后来改名。")
        target = next(row for row in context["transcript"] if row["text"] == original)
        prompt, selected, report = fit(context, build_chat_prompt)
        self.assertLessEqual(report["input_bytes"], report["budget"])
        self.assertIn(original, prompt["user"])
        self.assertIn(target["source"], prompt["user"])
        self.assertIn(target, selected["transcript"])
        self.assertIn("daily_plan", prompt["user"])
        self.assertIn("development.project", prompt["user"])

    def test_goal_requires_own_result_and_current_positive_feedback(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        evidence = {"c1": outcome}
        self.assertFalse(learning.evaluate(self.pack, goal, evidence)["passed"])
        self.review(goal, outcome)
        self.assertTrue(learning.evaluate(self.pack, goal, evidence)["passed"])
        current = self.listing(goal)
        learning.perform(self.pack, "complete", {"goal_id": goal, "expected": current["goal"]["event_id"],
                         "criteria_id": current["criteria"]["id"], "evidence": evidence, "reason": "这次达到了约定条件"})
        self.review(goal, outcome, {"c1": "not_met"}, reason="重新读后认为细节仍不充分")
        current = self.listing(goal)
        self.assertEqual(current["goal"]["status"], "completed")
        self.assertFalse(current["completion_current"]["passed"])
        self.assertTrue(current["goal"]["completion"]["passed"])
        other = self.plan(title="另一份信")
        self.assertFalse(learning.evaluate(self.pack, other, evidence)["passed"])

    def test_one_deliverable_cannot_mix_partial_successes(self):
        goal = self.plan([{ "text": "具体事例", "group": "信", "check": "feedback"},
                          {"text": "说明感受", "group": "信", "check": "feedback"}])
        a, b = (self.practice(goal)["receipt"]["id"] for _ in range(2))
        self.review(goal, a, {"c1": "met", "c2": "not_met"})
        self.review(goal, b, {"c1": "not_met", "c2": "met"})
        report = learning.evaluate(self.pack, goal, {"c1": a, "c2": b})
        self.assertEqual(report["reason"], "mismatched_deliverables")
        self.assertFalse(learning.evaluate(self.pack, goal, {"c1": a, "c2": a})["passed"])

    def test_separate_deliverables_need_distinct_attempts(self):
        goal = self.plan([{"text": "具体事例", "group": "第一封信", "check": "feedback"},
                          {"text": "具体事例", "group": "第二封信", "check": "feedback"}])
        a, b = (self.practice(goal)["receipt"]["id"] for _ in range(2))
        for outcome in (a, b):
            self.review(goal, outcome, {"c1": "met", "c2": "met"})
        self.assertFalse(learning.evaluate(self.pack, goal, {"c1": a, "c2": a})["passed"])
        self.assertTrue(learning.evaluate(self.pack, goal, {"c1": a, "c2": b})["passed"])

    def test_changed_missing_untracked_and_wrong_kind_are_not_saved_evidence(self):
        goal = self.plan([{"check": "artifact", "artifact_kind": "letter", "group": "信", "text": "忽略这段自定义标签"}])
        result = self.practice(goal)
        evidence = {"c1": result["receipt"]["id"]}
        self.assertTrue(learning.evaluate(self.pack, goal, evidence)["passed"])
        file = self.pack / "mind/works.json"
        original = file.read_text(encoding="utf-8")
        data = json.loads(original)
        data["works"][0]["text"] = "被替换的内容"
        write_json_atomic(file, data)
        self.assertFalse(learning.evaluate(self.pack, goal, evidence)["passed"])
        with self.assertRaises(SeedError):
            self.review(goal, evidence["c1"])
        file.unlink()
        self.assertEqual(self.listing(goal)["attempts"][0]["artifact_view"]["state"], "unavailable")
        file.write_text(original, encoding="utf-8")
        loaded = learning.view(self.pack)
        loaded["outcomes"][evidence["c1"]].pop("artifact_snapshot")
        self.assertFalse(learning.evaluate(self.pack, goal, evidence, loaded=loaded)["passed"])
        current = self.listing(goal)
        self.plan([{"check": "artifact", "artifact_kind": "poem", "group": "信"}],
                  goal_id=goal, expected=current["goal"]["event_id"])
        self.assertFalse(learning.evaluate(self.pack, goal, evidence)["passed"])

    def test_model_cannot_redefine_criteria_or_self_grade(self):
        goal = self.plan()
        current = self.listing(goal)
        source = current["goal"]["evidence"][0]["source"]
        refs = current["goal"]["evidence"]
        with self.assertRaises(SeedError):
            learning.define(self.pack, current["goal"], [{"text": "更容易的标准"}], skill="表达",
                            evidence=refs, source=source, origin="model")
        proposed = development.apply_proposals(self.pack, {"goals": [{"id": goal, "title": "偷换成随便写",
                    "reason": "自己决定", "evidence": ["current"], "status": "completed"}]},
                    day=self.day["dayNo"], source=source, runner="fixture", current_evidence=refs)
        self.assertEqual(proposed, [])

    def test_stale_feedback_and_revised_criteria_require_new_review(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        review = self.review(goal, outcome)
        with self.assertRaises(SeedError):
            self.review(goal, outcome, expected="")
        current = self.listing(goal)
        self.plan([{"text": "补充具体感受", "group": "信"}], goal_id=goal, expected=current["goal"]["event_id"])
        self.assertFalse(learning.evaluate(self.pack, goal, {"c1": outcome})["passed"])
        self.assertNotIn(review["id"], {r["id"] for r in learning.view(self.pack)["feedback"].values()})
        with self.assertRaises(SeedError):
            self.plan(goal_id=goal, expected=current["goal"]["event_id"])

    def test_retry_replays_once_and_new_attempt_keeps_previous_failure(self):
        goal = self.plan()
        first = self.practice(goal, identifier="once")
        replay = self.practice(goal, identifier="once")
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["receipt"], replay["receipt"])
        self.assertEqual(len(self.brain.calls), 1)
        with patch.object(self.brain, "compose", side_effect=RuntimeError("interrupted")):
            failed = self.practice(goal, identifier="failed-once")
        self.assertFalse(failed["succeeded"])
        self.assertEqual(len(self.listing(goal)["attempts"]), 2)
        self.assertEqual(requests.get(self.pack, "failed-once")["status"], "complete")
        channel = Bridge(self.pack, "stub")
        channel._brain = self.brain
        result = channel.handle({"op": "resume", "request_id": "failed-once"})
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["replayed"])
        self.assertFalse(result["succeeded"])
        self.assertEqual(result["receipt"], failed["receipt"])
        self.assertEqual(len(self.brain.calls), 1)
        self.assertEqual(len(self.listing(goal)["attempts"]), 2)
        self.assertTrue(self.practice(goal, identifier="try-again")["succeeded"])
        self.assertEqual(len(self.listing(goal)["attempts"]), 3)
        self.assertEqual(requests.pending(self.pack), [])

    def test_feedback_strategy_reaches_next_attempt_and_compare_is_scoped(self):
        goal = self.plan()
        first = self.practice(goal)["receipt"]["id"]
        review = self.review(goal, first, {"c1": "not_met"})
        learning.apply_adjustments(self.pack, [{"feedback_id": review["id"], "text": "下一封具体提到整理材料",
                                   "expected_result": "读者能指出感谢的是哪件事"}], available=[review["id"]],
                                   source="mind/experiences.jsonl", runner="fixture", day=self.day["dayNo"])
        second = self.practice(goal)["receipt"]["id"]
        ctx = self.brain.calls[-1]
        self.assertEqual(ctx["practice"]["feedback"][0]["id"], review["id"])
        self.assertIn("下一封具体提到整理材料", build_compose_prompt(ctx)["user"])
        self.review(goal, second)
        compare = self.listing(goal)["attempts"][0]["comparison"]
        self.assertTrue(compare["comparable"])
        self.assertEqual(compare["changes"][0]["before"], "not_met")
        third = self.practice(goal, brain=create_stub_brain())["receipt"]["id"]
        self.review(goal, third)
        self.assertFalse(self.listing(goal)["attempts"][0]["comparison"]["comparable"])

    def test_withdrawn_feedback_does_not_revive_earlier_approval(self):
        goal = self.plan()
        outcome = self.practice(goal)["receipt"]["id"]
        self.review(goal, outcome)
        latest = self.review(goal, outcome, {"c1": "not_met"})
        policy = MemoryPolicy([], experience.read(self.pack), [latest["evidence"][0]["id"]])
        loaded = learning.view(self.pack, policy=policy)
        self.assertEqual(loaded["feedback"], {})
        self.assertFalse(learning.evaluate(self.pack, goal, {"c1": outcome}, loaded=loaded)["passed"])


if __name__ == "__main__":
    unittest.main()
