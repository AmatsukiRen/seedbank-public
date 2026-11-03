"""Offline recall of previous goal versions without restoring old intentions."""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import test_action_outcomes as fixtures
from seedbank import cognition, development, disclosure, experience, goal_projects, learning, life_story, retrieval, semantic
from seedbank.memory_state import MemoryPolicy, describe
from seedbank.util import append_memories


class GoalHistoryTest(unittest.TestCase):
    setUp = fixtures.ActionOutcomesTest.setUp

    def revise(self, reason="OLD_GOAL_REASON_秋声驿站", *, goal_id="", status="active", title="整理驿站的声音", generation=None):
        return development.apply_proposals(self.pack, {"goals": [{
            "id": goal_id, "title": title, "status": status, "next_step": "整理构想",
            "reason": reason, "evidence": [self.memory["id"]]}]},
            day=self.day["dayNo"], source=experience.source_of(self.input), runner="goal-history-fixture",
            memories=[self.memory], generation=generation if generation is not None else {
                "runner": "goal-history-fixture", "proposal_activity": "initiative", **disclosure.stamp("owner")})[0]

    def search(self, query="OLD_GOAL_REASON_秋声驿站", **kwargs):
        return retrieval.search(self.pack, query, 20, use_semantic=False, **kwargs)

    def test_old_goal_and_change_reasons_survive_beyond_the_current_summary(self):
        first = self.revise()
        target = first["data"]["id"]
        self.revise("MIDDLE_REASON_换一种表达", goal_id=target, status="paused")
        self.revise("LATEST_REASON_明确放下", goal_id=target, status="abandoned")
        for index in range(12):
            later = self.revise("后来构想 " + str(index), title="新构想 " + str(index))
            self.revise("已放下其他构想", goal_id=later["data"]["id"], status="abandoned", title=later["data"]["title"])
        before = (self.pack / "mind/development.jsonl").read_bytes()
        self.assertNotIn(target, [goal["id"] for goal in development.summary(self.pack)["goals"]])
        recalled = next((row["memory"] for row in self.search() if row["memory"]["id"] == first["id"]), None)
        self.assertIsNotNone(recalled)
        self.assertIn("OLD_GOAL_REASON_秋声驿站", recalled["text"])
        self.assertEqual(recalled["source"], "mind/development.jsonl#" + first["id"])
        self.assertFalse(recalled["goal_version"]["is_latest"])
        self.assertEqual(recalled["goal_version"]["status"], "abandoned")
        self.assertIn("LATEST_REASON_明确放下", describe(recalled))
        self.assertTrue(self.search("MIDDLE_REASON_换一种表达"))
        self.assertEqual(development.current_state(self.pack)["goals"][target]["status"], "abandoned")
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), before)

    def new_basis(self):
        self.input = experience.record(self.pack, kind="conversation", text="另一条独立的人工依据",
            day=self.day["dayNo"], source=self.day["file"], actor="owner")
        self.memory = {"id": "m_later_goal_basis", "day": self.day["dayNo"], "at": self.input["recorded_at"],
            "kind": "thought", "text": self.input["text"], "source": experience.source_of(self.input),
            "event_ids": [self.input["id"]]}
        append_memories(self.pack, [self.memory])

    def test_hidden_latest_does_not_restore_or_expose_its_old_intention(self):
        first = self.revise()
        self.new_basis()
        latest = self.revise("WITHDRAWN_LATEST_PRIVATE_REASON", goal_id=first["data"]["id"], status="paused")
        self.assertEqual(self.search()[0]["memory"]["goal_version"]["status"], "paused")
        cognition.forget_memory(self.pack, self.memory["id"])
        found = next(row["memory"] for row in self.search() if row["memory"]["id"] == first["id"])
        self.assertFalse(found["goal_version"]["current_available"])
        self.assertNotIn("WITHDRAWN_LATEST_PRIVATE_REASON", describe(found))
        self.assertNotIn(latest["id"], json.dumps(found))
        self.assertNotIn(first["data"]["id"], development.current_state(self.pack)["goals"])

    def test_withdrawal_follows_version_only_derivatives_without_erasing_independent_revision(self):
        first = self.revise()
        original_memory = self.memory["id"]
        derived = experience.record(self.pack, kind="thought", text="DERIVED_OLD_GOAL_ID_ONLY",
            day=self.day["dayNo"], source="art/future.md", depends_on=[first["id"]])
        self.new_basis()
        self.revise("INDEPENDENT_LATER_GOAL_REASON", goal_id=first["data"]["id"], status="paused")
        self.assertTrue(self.search())
        cognition.forget_memory(self.pack, original_memory)
        for found in (self.search(), self.search(historical=True)):
            self.assertNotIn(first["id"], [r["memory"]["id"] for r in found])
            self.assertNotIn("OLD_GOAL_REASON_秋声驿站", json.dumps(found, ensure_ascii=False))
        self.assertFalse(MemoryPolicy.load(self.pack).allows(derived))
        self.assertTrue(self.search("INDEPENDENT_LATER_GOAL_REASON"))

    def test_scope_is_private_and_semantic_catalog_obeys_withdrawal(self):
        first = self.revise()
        self.assertEqual(self.search(policy=disclosure.policy_for(self.pack, "qq-group:123")), [])
        semantic.configure(self.pack, {"enabled": True, "model": "goal-fixture", "min_similarity": .9})
        sent = []
        def fake(cfg, texts):
            sent.extend(texts)
            return {"model": "goal-fixture", "data": [{"index": i,
                "embedding": [1., 0.] if "OLD_GOAL_REASON_秋声驿站" in text or text == "旧愿望的缘由" else [0., 1.]}
                for i, text in enumerate(texts)]}
        with patch("seedbank.semantic._request", side_effect=fake):
            semantic.manage(self.pack, "index", limit=64)
            rows = retrieval.search(self.pack, "旧愿望的缘由", 20)
        self.assertIn(first["id"], [r["memory"]["id"] for r in rows])
        cognition.forget_memory(self.pack, self.memory["id"])
        sent.clear()
        with patch("seedbank.semantic._request", side_effect=fake):
            semantic.manage(self.pack, "index", limit=64)
            rows = retrieval.search(self.pack, "旧愿望的缘由", 20)
        self.assertNotIn(first["id"], [r["memory"]["id"] for r in rows])
        self.assertNotIn("OLD_GOAL_REASON_秋声驿站", "\n".join(sent))

    def test_reopen_bad_index_and_date_filters_preserve_original_version(self):
        first = self.revise()
        self.assertTrue(self.search())
        code = "import json,sys; from seedbank.retrieval import search; print(json.dumps(search(sys.argv[1],'OLD_GOAL_REASON_秋声驿站',20,use_semantic=False),ensure_ascii=False))"
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(self.pack)],
            capture_output=True, encoding="utf-8", timeout=30, check=True)
        self.assertIn(first["id"], [r["memory"]["id"] for r in json.loads(result.stdout)])
        (self.pack / "mind/search.sqlite3").write_bytes(b"invalid synthetic cache")
        self.assertIn(first["id"], [r["memory"]["id"] for r in self.search()])
        self.assertEqual(self.search(date_to="2020-01-01"), [])

    def test_cache_cannot_forge_goal_status_or_original_reason(self):
        first = self.revise()
        self.assertTrue(self.search())
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            payload = json.loads(db.execute("SELECT payload FROM entries WHERE id=?", (first["id"],)).fetchone()[0])
            payload["goal_version"] = {"current_available": True, "status": "completed", "reason": "FAKED_GOAL_COMPLETION"}
            db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(payload), first["id"]))
            db.commit()
        self.assertNotIn("FAKED_GOAL_COMPLETION", json.dumps(self.search()))
        with closing(sqlite3.connect(self.pack / "mind/search.sqlite3")) as db:
            payload["text"] += " FAKED_GOAL_TEXT"
            payload["origin"] = "experience"
            db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(payload), first["id"]))
            db.commit()
        self.assertNotIn("FAKED_GOAL_TEXT", json.dumps(self.search()))

    def test_external_revision_and_return_value_mutation_are_seen_without_rewriting_history(self):
        first = self.revise()
        policy = MemoryPolicy.load(self.pack)
        policy.goal_rows[first["id"]]["text"] = "caller mutation"
        self.assertIn("OLD_GOAL_REASON_秋声驿站", self.search()[0]["memory"]["text"])
        ledger = self.pack / "mind/development.jsonl"
        content = ledger.read_text(encoding="utf-8")
        ledger.write_text(content.replace("OLD_GOAL_REASON_秋声驿站", "EXTERNAL_GOAL_REASON_海风"), encoding="utf-8")
        self.assertNotIn("OLD_GOAL_REASON_秋声驿站", json.dumps(self.search(), ensure_ascii=False))
        self.assertTrue(self.search("EXTERNAL_GOAL_REASON_海风"))

    def test_actual_prompt_and_dependencies_distinguish_old_and_latest_and_disallow_memory_correction(self):
        from seedbank.brain import RemoteBrain, _CfgBrain
        first = self.revise()
        self.new_basis()
        latest = self.revise("LATEST_GOAL_PAUSE_REASON", goal_id=first["data"]["id"], status="paused")
        old = next(r for r in self.search() if r["memory"]["id"] == first["id"])
        self.assertEqual(old["memory"]["goal_version"]["day"], latest["day"])
        self.assertEqual(old["memory"]["goal_version"]["at"], latest["at"])
        self.assertIn(latest["id"], cognition._context_dependencies({"recalled": [old]}))
        self.assertEqual(cognition._context_dependencies({"recalled": []}), [])
        transport = Mock(return_value=json.dumps({"reply": "人工回顾说明", "memory_writes": [],
            "corrections": [{"target_id": first["id"], "new": "已实际完成", "reason": "不应覆写目标历史"}]}, ensure_ascii=False))
        brain = _CfgBrain({"adapter": "codex", "model": "fixture", "input_budget": 16000, "codex_max_calls": 1}, RemoteBrain("codex", transport))
        result = cognition.chat_turn(self.pack, "回查 OLD_GOAL_REASON_秋声驿站 的当时理由。", brain)
        self.assertEqual(result["corrections"], 0)
        prompt = "\n".join(transport.call_args.args[1:])
        self.assertIn("OLD_GOAL_REASON_秋声驿站", prompt)
        self.assertIn("LATEST_GOAL_PAUSE_REASON", prompt)
        self.assertIn("paused", prompt)
        reply = next(row for row in reversed(experience.read(self.pack)) if row["text"] == "人工回顾说明")
        self.assertIn(latest["id"], reply["depends_on"])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertFalse(MemoryPolicy.load(self.pack).allows(reply))

    def test_life_review_anchors_a_past_goal_and_keeps_that_time_after_later_revision(self):
        first = self.revise()
        original = MemoryPolicy.load(self.pack).goal_rows[first["id"]]
        saved = life_story.perform(self.pack, "save", {"kind": "chapter", "title": "回看一个旧愿望",
            "interpretation": "我曾记录过整理驿站声音的愿望。", "change": "", "question": "", "status": "open",
            "reason": "依据当时的目标记录", "target": "", "expected": "",
            "anchors": [{"id": first["id"], "quote": "OLD_GOAL_REASON_秋声驿站", "hash": life_story._digest(original)}]})["record"]
        self.revise("后来决定放下", goal_id=first["data"]["id"], status="abandoned")
        self.assertIn(saved["id"], [row["id"] for row in life_story.context(self.pack)["chapters"]])
        cognition.forget_memory(self.pack, self.memory["id"])
        self.assertEqual(life_story.context(self.pack)["chapters"], [])

    def test_each_prompt_channel_keeps_latest_note_until_whole_history_is_trimmed(self):
        from seedbank.brain import build_chat_prompt
        from seedbank.context_window import fit
        first = self.revise()
        latest = self.revise("LATEST_GOAL_FOR_FIT_" + "界" * 180,
            goal_id=first["data"]["id"], status="abandoned")
        old = next(r for r in self.search() if r["memory"]["id"] == first["id"])
        ledger = (self.pack / "mind/development.jsonl").read_bytes()
        base = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        for key in ("development", "facts", "practice", "relationships", "life_story", "inner", "daily_choice"):
            base[key] = {}
        for key in ("transcript", "evidence", "recalled", "learning", "disclosed", "senses", "news", "works", "friends"):
            base[key] = []
        for key in ("beliefs", "selfMd", "recentDays", "plan"):
            base[key] = ""
        base.update(message="回看当时为何改变想法", _compact_protocol=True)
        empty_prompt = build_chat_prompt({**base, "context_limited": True})
        budget = sum(len(value.encode("utf-8")) for value in empty_prompt.values()) + 512 + 32
        for channel in ("evidence", "recalled"):
            with self.subTest(channel=channel):
                ctx = {**base, channel: [old["memory"]] if channel == "evidence" else [old],
                    "_cfg": {"input_budget": budget}}
                before = json.dumps(ctx, ensure_ascii=False)
                full = "\n".join(build_chat_prompt(ctx).values())
                self.assertIn("LATEST_GOAL_FOR_FIT_", full)
                self.assertIn(latest["id"], full)
                self.assertIn(latest["id"], cognition._context_dependencies(ctx))
                prompt, used, measured = fit(ctx, build_chat_prompt)
                self.assertTrue(measured["limited"])
                self.assertNotIn("OLD_GOAL_REASON_", "\n".join(prompt.values()))
                self.assertNotIn("LATEST_GOAL_FOR_FIT_", "\n".join(prompt.values()))
                self.assertNotIn(first["id"], cognition._context_dependencies(used))
                self.assertNotIn(latest["id"], cognition._context_dependencies(used))
                self.assertEqual(json.dumps(ctx, ensure_ascii=False), before)
        self.assertEqual((self.pack / "mind/development.jsonl").read_bytes(), ledger)

    def test_explicit_excerpt_does_not_disclose_later_private_goal_versions(self):
        first = self.revise()
        original = MemoryPolicy.load(self.pack).goal_rows[first["id"]]
        share = disclosure.perform(self.pack, "excerpt", {"scope": "qq-group:123", "text": "OLD_GOAL_REASON_秋声驿站",
            "source_id": first["id"], "source_hash": disclosure._hash(original), "reason": "人工分享这段旧说明"})["record"]
        self.revise("LATER_PRIVATE_GOAL_REASON", goal_id=first["data"]["id"], status="paused")
        found = self.search(policy=disclosure.policy_for(self.pack, "qq-group:123"))
        self.assertIn(share["event_id"], [r["memory"]["id"] for r in found])
        self.assertNotIn(first["id"], [r["memory"]["id"] for r in found])
        self.assertNotIn("LATER_PRIVATE_GOAL_REASON", json.dumps(found))
        self.assertEqual(self.search(policy=disclosure.policy_for(self.pack, "qq-group:456")), [])
        disclosure.perform(self.pack, "revoke", {"target": share["key"], "expected": share["id"], "reason": "结束人工分享"})
        self.assertEqual(self.search(policy=disclosure.policy_for(self.pack, "qq-group:123")), [])

    def test_user_fixed_and_missing_activity_have_distinct_recorded_sources(self):
        user_goal = learning.perform(self.pack, "plan", {"title": "USER_GOAL_SOURCE_记下一段见闻", "skill": "表达",
            "reason": "人工明确设置", "next_step": "先整理材料",
            "criteria": [{"text": "记录具体", "group": "材料", "check": "feedback"}]})["goal_id"]
        user_row = next(r["memory"] for r in self.search("记下一段见闻") if r["memory"].get("goal_id") == user_goal)
        self.assertIn("用户设置", user_row["text"])
        fixed = self.revise("FIXED_GOAL_REASON", title="固定夹具目标", generation={"runner": "stub", "proposal_activity": "initiative"})
        fixed_row = next(r["memory"] for r in self.search("FIXED_GOAL_REASON") if r["memory"]["id"] == fixed["id"])
        self.assertTrue(fixed_row["template_generated"])
        self.assertIn("固定或回退响应", fixed_row["text"])
        legacy = self.revise("LEGACY_GOAL_REASON", title="旧版本夹具目标", generation={})
        legacy_row = next(r["memory"] for r in self.search("LEGACY_GOAL_REASON") if r["memory"]["id"] == legacy["id"])
        self.assertIn("当时未记录形成场景", legacy_row["text"])
        first = self.revise("FIRST_ACTIVITY_REASON")
        self.revise("LATER_FIXED_REASON", goal_id=first["data"]["id"], status="paused", generation={"runner": "stub"})
        old = next(r["memory"] for r in self.search("FIRST_ACTIVITY_REASON") if r["memory"]["id"] == first["id"])
        self.assertEqual(old["goal_version"]["activity"], "fixed")
        self.assertIn("来源：固定或回退响应", describe(old))

    def test_staged_goals_require_unchanged_original_project(self):
        context = cognition.build_context(self.pack, self.day["dayNo"], self.day["date"], use_semantic=False)
        context["current_evidence"] = [{"id": self.input["id"], "source": experience.source_of(self.input), "kind": "conversation"}]
        proposal = {"title": "整理并表达", "reason": "STAGED_GOAL_HISTORY_REASON", "evidence": ["current"], "stages": [
            {"key": "a", "title": "分阶段整理材料", "next_step": "列出材料", "skill": "表达",
             "criteria": [{"text": "具体材料", "group": "材料", "check": "feedback"}], "after": []},
            {"key": "b", "title": "分阶段表达", "next_step": "写出内容", "skill": "表达",
             "criteria": [{"text": "表达具体", "group": "作品", "check": "feedback"}], "after": [{"stage": "a"}]}]}
        result = goal_projects.apply(self.pack, proposal, ctx=context, day=self.day,
            generation={"runner": "project-fixture", "model": "fixture", "fallback": False})
        self.assertEqual(result["status"], "accepted")
        ids = set(result["goal_ids"].values())
        self.assertEqual(ids, {r["memory"].get("goal_id") for r in self.search("STAGED_GOAL_HISTORY_REASON") if r["memory"]["kind"] == "goal_history"})
        file = self.pack / "mind/development.jsonl"
        rows = development.events(self.pack)
        for row in rows:
            if row["kind"] == "goal" and row["data"]["id"] in ids:
                row["data"]["project"]["sha256"] = "0" * 64
        file.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        self.assertFalse(any(r["memory"].get("goal_id") in ids for r in self.search("STAGED_GOAL_HISTORY_REASON")))


if __name__ == "__main__":
    unittest.main()
