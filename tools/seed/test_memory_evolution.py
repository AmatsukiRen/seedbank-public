"""User-run regressions for sourced recall; isolated packs, no real API/UI."""
import json
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import development
from seedbank.brain import RemoteBrain, build_chat_prompt, build_diary_prompt, build_initiate_prompt
from seedbank.bonds import add_promise, bond_summary, break_promise, keep_promise
from seedbank.cognition import (build_context, chat_turn, forget_memory, normalize_memory_writes,
                                recall, start_day, visible_memories)
from seedbank.context_window import ContextBudgetError, fit
from seedbank.hands import add_reminder, mark_said
from seedbank.memory_state import describe, revise_memory
from seedbank.retrieval import search
from seedbank.pack import hatch
from seedbank.settings import save_settings
from seedbank.util import append_memories, now_iso, read_memories, read_text, write_json_atomic

ROOT = Path(__file__).resolve().parents[2]


class FixedBrain:
    name = "fixture"

    def __init__(self, result):
        self.result = result

    def chat(self, ctx):
        return dict(self.result)


class MemoryEvolutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-memory-")
        self.addCleanup(temporary.cleanup)
        self.pack = Path(temporary.name) / "初.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="memory-evolution",
              born_at_override="2026-11-01T00:00:00Z")
        self.day = start_day(self.pack)

    def context(self, message=""):
        return build_context(self.pack, self.day["dayNo"], self.day["date"], message)

    def remember(self, text, **extra):
        chat_turn(self.pack, text, FixedBrain({"reply": "我听到了。", "memory_writes": [
            {"text": text, "importance": 0.7}], **extra}))
        return next(row for row in reversed(read_memories(self.pack)) if row["text"] == text)

    def test_forgetting_removes_content_from_all_prompt_modes_and_raw_recall(self):
        marker = "只用于隔离验收的紫色灯塔暗号"
        target = self.remember(marker, development={"beliefs": [
            {"text": marker, "reason": "本次对话", "evidence": ["current"]}]})
        before = (self.pack / "mind/memories.jsonl").read_bytes()
        forget_memory(self.pack, target["id"])
        self.assertTrue((self.pack / "mind/memories.jsonl").read_bytes().startswith(before))
        self.assertNotIn(marker, read_memories(self.pack)[-1]["text"])
        context = self.context("我们换个话题")
        for builder in (build_chat_prompt, build_diary_prompt, build_initiate_prompt):
            self.assertNotIn(marker, json.dumps(builder(context), ensure_ascii=False))
        self.assertEqual(recall(self.pack, "紫色灯塔暗号", 50), [])
        self.assertEqual(context["development"]["beliefs"], [])

    def test_correction_is_linked_and_not_limited_by_earlier_memory_writes(self):
        save_settings(self.pack, {"daily_max": 1})
        target = self.remember("我现在住在杭州。")
        result = chat_turn(self.pack, "我搬到成都了。", FixedBrain({
            "reply": "我会区分过去和现在。", "memory_writes": [], "corrections": [
                {"target_id": target["id"], "new": "现在住在成都，以前住在杭州。",
                 "reason": "用户刚刚明确说明搬家", "change_type": "change"}]}))
        self.assertEqual(result["corrections"], 1)
        visible = visible_memories(self.pack)
        self.assertNotIn(target["id"], {row["id"] for row in visible})
        revised = next(row for row in visible if row.get("supersedes") == target["id"])
        self.assertEqual(revised["change_type"], "change")
        self.assertIn(target["id"], {row["id"] for row in read_memories(self.pack)})
        current_ids = {row["memory"]["id"] for row in recall(self.pack, "杭州", 50)}
        self.assertFalse(set(target["event_ids"]) & current_ids)
        self.assertNotIn(target["id"], current_ids)
        historical = search(self.pack, "杭州", 50, historical=True)
        old = next(row["memory"] for row in historical if row["memory"]["id"] == target["id"])
        self.assertIn("旧版本", describe(old))

    def test_raw_event_can_be_corrected_without_an_extracted_memory(self):
        chat_turn(self.pack, "现在的住处是杭州。", FixedBrain({"reply": "收到。", "memory_writes": []}))
        target = next(row["memory"] for row in recall(self.pack, "住处 杭州", 8)
                      if row["memory"].get("origin") == "experience")
        chat_turn(self.pack, "更正住处，现在是成都。", FixedBrain({"reply": "我记录这个变化。", "memory_writes": [],
            "corrections": [{"target_id": target["id"], "new": "现在的住处是成都。",
                             "reason": "本人明确更正", "change_type": "change"}]}))
        self.assertNotIn(target["id"], {r["memory"]["id"] for r in recall(self.pack, "住处", 50)})
        self.assertTrue(any(m.get("supersedes") == target["id"] for m in visible_memories(self.pack)))

    def test_new_turn_still_learns_when_batch_limit_was_reached(self):
        save_settings(self.pack, {"daily_max": 1})
        self.remember("今天先聊一件普通的事情。")
        target = self.remember("这是一条稍后才告诉你的重要变化。")
        self.assertIn(target["id"], {row["id"] for row in visible_memories(self.pack)})

    def test_desktop_message_reports_saved_correction_and_replay(self):
        from seedbank.desktop.session import Session

        chat_turn(self.pack, "主角洛川在青石图书馆整理旧地图。",
                  FixedBrain({"reply": "收到。", "memory_writes": []}))
        target = next(row["memory"] for row in recall(self.pack, "洛川 旧地图", 8)
                      if row["memory"].get("origin") == "experience")
        session = Session(self.pack)
        session.bridge._brain = FixedBrain({"reply": "已更正名字。", "memory_writes": [],
            "corrections": [{"target_id": target["id"], "new": "主角洛杉在青石图书馆整理旧地图。",
                             "reason": "用户明确说明原名写错", "change_type": "correction"}]})
        for replayed in (False, True):
            result = session.call("message", text="更正：主角叫洛杉，原来写错了，不是后来改名。",
                                  request_id="desktop-source-correction")
            self.assertTrue(result["ok"])
            self.assertEqual(result["corrections"], 1)
            self.assertEqual(result["replayed"], replayed)
            revisions = [row for row in read_memories(self.pack) if row.get("supersedes") == target["id"]]
            self.assertEqual(len(revisions), 1)
            self.assertEqual(revisions[0]["change_type"], "correction")
            self.assertTrue(revisions[0]["evidence"])

    def test_correcting_raw_event_also_retires_its_extracted_memory(self):
        extracted = self.remember("原来约定周三见面。")
        event = next(r["memory"] for r in recall(self.pack, "周三见面", 50)
                     if r["memory"]["id"] == extracted["event_ids"][0])
        revise_memory(self.pack, event["id"], "见面时间改为周五。", reason="明确改期",
                      day=self.day["dayNo"], source=self.day["file"], runner="fixture", target_record=event)
        self.assertNotIn(extracted["id"], {m["id"] for m in visible_memories(self.pack)})

    def test_raw_archive_is_searchable_without_extracted_memory(self):
        chat_turn(self.pack, "北坡有两只丹顶鹤。", FixedBrain({"reply": "我收到了你的见闻。", "memory_writes": []}))
        rows = recall(self.pack, "你之前说的丹顶鹤", 8)
        self.assertTrue(any("两只丹顶鹤" in row["memory"]["text"] for row in rows))
        self.assertEqual(recall(self.pack, "quantumunknown987654", 8), [])

    def _check_legacy_index_rebuild(self, version):
        from seedbank import retrieval
        append_memories(self.pack, [{"id": "index-migration-memory", "day": self.day["dayNo"],
            "text": "人工夹具：银杏树旁的风铃编号为 G-491。", "kind": "hearsay", "importance": .7,
            "source": self.day["file"], "tags": ["人工夹具"], "at": now_iso()}])
        sources = [self.pack / "birth.json", self.pack / "mind/memories.jsonl", *self.pack.glob("life/*.md")]
        original = {path: path.read_bytes() for path in sources}
        index = self.pack / "mind/search.sqlite3"
        with closing(sqlite3.connect(index)) as db:
            db.executescript("""
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE entries (id TEXT PRIMARY KEY, source_key TEXT, source_ref TEXT, payload TEXT);
                CREATE TABLE terms (token TEXT, entry_id TEXT, PRIMARY KEY(token, entry_id));
                CREATE INDEX terms_entry ON terms(entry_id);
                CREATE TABLE sources (key TEXT PRIMARY KEY, stamp TEXT);
            """)
            if version is not None:
                db.execute("INSERT INTO metadata VALUES ('version', ?)", (version,))
            ghost = {"id": "cache-only", "text": "cacheonlymarker", "source": self.day["file"],
                     "importance": .9, "padding": "x" * 262144}
            db.execute("INSERT INTO entries VALUES (?, ?, ?, ?)",
                       ("cache-only", "memories", self.day["file"], json.dumps(ghost)))
            db.execute("INSERT INTO terms VALUES ('cacheonlymarker', 'cache-only')")
            db.commit()
        old_size = index.stat().st_size
        rows = search(self.pack, "银杏 风铃", 10, use_semantic=False)
        self.assertIn("index-migration-memory", {row["memory"]["id"] for row in rows})
        self.assertEqual(search(self.pack, "cacheonlymarker", 10, use_semantic=False), [])
        self.assertEqual({path: path.read_bytes() for path in sources}, original)
        self.assertLess(index.stat().st_size, old_size // 2,
                        "Rebuilding a disposable index must release obsolete cache pages")
        with closing(sqlite3.connect(index)) as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0], retrieval.VERSION)
            self.assertEqual([row[2] for row in db.execute("PRAGMA index_info('terms')")], ["token", "entry_id"],
                             "A legacy cache must rebuild into the compact composite-key table")
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_version_eight_index_rebuild_preserves_raw_sources_and_recall(self):
        self._check_legacy_index_rebuild("8")

    def test_version_nine_index_rebuild_preserves_raw_sources_and_recall(self):
        self._check_legacy_index_rebuild("9")

    def test_version_ten_index_rebuild_preserves_raw_sources_and_recall(self):
        self._check_legacy_index_rebuild("10")

    def test_unversioned_index_rebuild_preserves_raw_sources_and_recall(self):
        self._check_legacy_index_rebuild(None)

    def test_dream_keeps_its_type_in_final_prompt(self):
        row = {"id": "dream-fixture", "day": self.day["dayNo"], "kind": "thought", "text": "梦里去过月球。",
               "tags": ["梦"], "importance": 0.5, "source": self.day["file"], "at": now_iso(), "runner": "fixture"}
        append_memories(self.pack, [row])
        context = self.context("月球")
        self.assertIn("梦境，不是亲历", build_chat_prompt(context)["user"])
        self.assertNotIn(row["id"], {m["id"] for m in context["evidence"]})

    def test_corrupt_disposable_index_falls_back_to_original_archive(self):
        self.remember("窗外有一只戴胜。")
        index = self.pack / "mind/search.sqlite3"
        index.write_bytes(b"broken disposable search index")
        rows = recall(self.pack, "戴胜", 8)
        self.assertTrue(any("戴胜" in row["memory"]["text"] for row in rows))
        self.assertEqual(index.read_bytes(), b"broken disposable search index")

    def test_legacy_self_edits_cannot_bypass_evidence(self):
        before = read_text(self.pack / "mind/self.md")
        chat_turn(self.pack, "请先听完", FixedBrain({"reply": "好。", "self_edits": {
            "self_append": "没有任何依据的永久身份", "beliefs_append": "未经证实的结论"}}))
        self.assertEqual(read_text(self.pack / "mind/self.md"), before)
        self.assertNotIn("未经证实的结论", read_text(self.pack / "mind/beliefs.md"))

    def test_updated_old_belief_remains_in_current_summary(self):
        identifiers = []
        for index in range(24):
            rows = development.apply_proposals(self.pack, {"beliefs": [
                {"text": f"观察编号 {index}", "reason": "夹具依据", "evidence": ["current"]}]},
                day=self.day["dayNo"], source=self.day["file"], runner="fixture")
            identifiers.append(rows[0]["data"]["id"])
        development.apply_proposals(self.pack, {"beliefs": [
            {"id": identifiers[0], "text": "最早的观察已修正", "reason": "新依据", "evidence": ["current"]}]},
            day=self.day["dayNo"], source=self.day["file"], runner="fixture")
        self.assertIn(identifiers[0], {r["id"] for r in development.summary(self.pack)["beliefs"]})

    def test_model_can_rephrase_search_and_records_actual_fallback(self):
        self.remember("最近入睡很困难。")
        prompts = []

        def transport(cfg, system, user):
            prompts.append(user)
            if len(prompts) == 1:
                return json.dumps({"memory_search": {"query": "入睡 困难"}})
            return json.dumps({"reply": "你提到过入睡困难。", "memory_writes": []})

        brain = RemoteBrain("openai-compatible", transport)
        result = brain.chat({**self.context("之前的睡眠困扰是什么"), "_cfg": {"model": "fixture"}})
        self.assertEqual(result["_generation"]["memory_searches"], 1)
        self.assertIn("入睡很困难", prompts[-1])

        def failed(*args):
            raise OSError("fixture failure")

        failed_brain = RemoteBrain("openai-compatible", failed)
        fallback = failed_brain.chat(self.context("你好"))
        self.assertTrue(fallback["_generation"]["fallback"])
        self.assertEqual(fallback["_generation"]["runner"], failed_brain._stub.name)

    def test_context_budget_keeps_request_and_does_not_modify_history(self):
        context = self.context("请保留这一条当前请求")
        context["transcript"] = [{"who": "owner", "text": "很久以前的普通交流" * 80} for _ in range(100)]
        prompt, selected, report = fit(context, build_chat_prompt)
        self.assertTrue(report["limited"])
        self.assertLessEqual(sum(len(v.encode("utf-8")) for v in prompt.values()), report["budget"])
        self.assertIn(context["message"], prompt["user"])
        self.assertEqual(len(context["transcript"]), 100)

    def test_default_budget_allows_minimal_turns_and_preserves_optional_choices(self):
        context = self.context("今天先聊聊")
        for builder in (build_chat_prompt, build_diary_prompt, build_initiate_prompt):
            with self.subTest(builder=builder.__name__):
                prompt, selected, report = fit(context, builder)
                self.assertLessEqual(report["input_bytes"], report["budget"])
                self.assertIn("daily_plan", prompt["user"])
                self.assertIn("development.project", prompt["user"])
                self.assertTrue(selected.get("goal_project_protocol", True))
        context["message"] = "当前输入不可被静默截断" * 2000
        with self.assertRaises(ContextBudgetError):
            fit(context, build_chat_prompt)

    def test_default_budget_keeps_recent_owner_input_for_followup_recall(self):
        message = "青岚在南坡温室帮我修好了蓝色风铃，我想写信感谢她。"
        chat_turn(self.pack, message, FixedBrain({
            "reply": "我会根据你告诉我的事写感谢信，不添加未经确认的经历。" * 8,
            "memory_writes": []}))
        context = self.context("刚才我想感谢谁，因为什么？")
        before = json.dumps(context["transcript"], ensure_ascii=False)
        prompt, selected, report = fit(context, build_chat_prompt)
        self.assertTrue(any(message in row["text"] for row in selected["transcript"]),
                        "Budget fitting discarded the previous speaker's actual input")
        self.assertIn(message, prompt["user"])
        self.assertLessEqual(report["input_bytes"], report["budget"])
        self.assertIn("daily_plan", prompt["user"])
        self.assertIn("development.project", prompt["user"])
        self.assertEqual(json.dumps(context["transcript"], ensure_ascii=False), before)

    def test_followup_retains_original_input_despite_repeated_long_model_replies(self):
        message = "青岚在南坡温室帮我修好了蓝色风铃，我想写信感谢她。"
        chat_turn(self.pack, message, FixedBrain({"reply": "我听到了。", "memory_writes": []}))
        for _ in range(3):
            chat_turn(self.pack, "我刚才想感谢谁？", FixedBrain({
                "reply": "这是模型之前的回答，不能取代用户实际说过的原话。" * 12,
                "memory_writes": []}))
        prompt, selected, report = fit(self.context("我刚才想感谢谁？"), build_chat_prompt)
        self.assertIn(message, prompt["user"])
        self.assertTrue(any(message in row["text"] for row in selected["transcript"]))
        self.assertLessEqual(report["input_bytes"], report["budget"])

    def test_visible_transcript_is_still_citable_when_recall_evidence_was_trimmed(self):
        original = "我给的创作素材是青岚在南坡温室修好了蓝色风铃。"
        chat_turn(self.pack, original, FixedBrain({"reply": "我收到了这份素材。", "memory_writes": [],
                                                 "_generation": {"runner": "stub-fixture"}}))
        context = self.context("更正素材里的名字，是青禾，不是青岚。")
        target = next(row for row in context["transcript"] if row["text"] == original)
        # The visible dialogue can survive after duplicated recall/evidence
        # entries were removed by fitting. It must still offer a usable ID.
        context.update(evidence=[], recalled=[])
        prompts = []
        def transport(cfg, system, user):
            prompts.append(user)
            return json.dumps({"reply": "素材中的名字更正为青禾。", "memory_writes": [],
                "corrections": [{"target_id": target["event_id"], "new": "素材中的青禾在南坡温室修好蓝色风铃。",
                                 "reason": "用户明确更正名字", "change_type": "correction"}]}, ensure_ascii=False)
        result = RemoteBrain("openai-compatible", transport).chat(context)
        self.assertIn(target["event_id"], prompts[-1])
        self.assertIn(target["source"], prompts[-1])
        self.assertIn('"id": "' + target["event_id"] + '"', prompts[-1],
                      "Dialogue IDs must also appear in the citation menu")
        available = {row["id"]: row for row in result["_used_evidence"]}
        self.assertIn(target["event_id"], available)
        self.assertEqual(available[target["event_id"]]["source"], target["source"])
        self.assertNotIn(context["transcript"][1]["event_id"], available,
                         "Offline fixture replies must not become independent evidence")
        saved = chat_turn(self.pack, context["message"], FixedBrain(result))
        self.assertEqual(saved["corrections"], 1)
        revision = next(row for row in read_memories(self.pack) if row.get("supersedes") == target["event_id"])
        self.assertEqual(revision["change_type"], "correction")
        self.assertTrue(revision["evidence"])

    def test_long_latest_model_reply_cannot_evict_the_original_statement(self):
        original = "独立创作设定：洛川在青石图书馆整理旧地图。"
        chat_turn(self.pack, original, FixedBrain({
            "reply": "这只是先前的模型回答，不是用户给出的新素材。" * 400,
            "memory_writes": []}))
        message = "请正式更正素材：主角是洛杉，原来名字写错了，不是后来改名。"
        context = self.context(message)
        target = next(row for row in context["transcript"] if row["text"] == original)
        before = json.dumps(context, ensure_ascii=False, default=str)
        prompt, selected, report = fit(context, build_chat_prompt)
        self.assertLessEqual(report["input_bytes"], report["budget"])
        self.assertIn(original, prompt["user"])
        self.assertIn(target["source"], prompt["user"])
        self.assertIn('"id": "' + target["event_id"] + '"', prompt["user"])
        self.assertTrue(prompt["user"].rstrip().endswith(message))
        self.assertIn(target, selected["transcript"])
        self.assertEqual(json.dumps(context, ensure_ascii=False, default=str), before)

    def test_current_request_is_last_after_history_and_protocol_on_model_wire(self):
        chat_turn(self.pack, "收信人是谁？", FixedBrain({"reply": "你尚未提供收信人。", "memory_writes": []}))
        message = "更正刚才的短篇设定：主角叫洛杉，不是洛川。"
        captured = []
        def transport(cfg, system, user):
            captured.append(user)
            return json.dumps({"reply": "收到这次更正。", "memory_writes": []})
        RemoteBrain("openai-compatible", transport).chat(self.context(message))
        self.assertTrue(captured[-1].rstrip().endswith(message),
                        "Current request must remain distinct after historical questions and protocol")

    def test_finished_promises_and_reminders_do_not_exhaust_lifetime(self):
        for index in range(41):
            promise = add_promise(self.pack, f"承诺 {index}", made_day=self.day["dayNo"])
            if index == 0:
                break_promise(self.pack, promise["id"])
            else:
                keep_promise(self.pack, promise["id"])
        self.assertEqual(bond_summary(self.pack)["broken_count"], 1)
        prompt = build_chat_prompt(self.context("以前的约定呢"))["system"]
        self.assertIn("未履行 1 次", prompt)
        self.assertIn("未经当前条件核对", prompt)
        self.assertNotIn("你答应过的事都做到了", prompt)
        for index in range(65):
            reminder = add_reminder(self.pack, f"提醒 {index}", self.day["dayNo"])
            mark_said(self.pack, reminder["id"], self.day["dayNo"])
        self.assertEqual(add_reminder(self.pack, "很久以后的事情", 3651)["due_day"], 3651)


if __name__ == "__main__":
    unittest.main()
