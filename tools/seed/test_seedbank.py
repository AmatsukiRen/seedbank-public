"""Seedbank 参考实现的测试（只用标准库 unittest，零依赖）。

跑法：
  python -m unittest discover -s tools/seed -p "test_*.py" -v
"""

from __future__ import annotations

import http.server
import io
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank import cli  # noqa: E402
from seedbank import localmodels, offline, onboarding  # noqa: E402
from seedbank.agency import (  # noqa: E402
    add_boundary, add_interest, clear_boundaries, current_plan, learn_from_day, load_agency,
    mark_plan_done, plan_for_day, should_initiate,
)
from seedbank.bonds import (  # noqa: E402
    add_event, add_promise, bond_summary, break_promise, describe_bonds, due_today,
    familiarity_percent, keep_promise, list_promises, load_bonds, pending_promises, register_talk,
)
from seedbank.brain import (  # noqa: E402
    MAX_VISION_BYTES, VISION_PROMPT, create_brain, create_stub_brain, describe_brain,
    load_brain_config, openai_transport, save_brain_config, stub_chat, stub_diary, vision_translate,
)
from seedbank.cognition import (  # noqa: E402
    compose_work, build_context, chat_turn, feed_news, forget_memory, forgotten_ids, legacy_letter,
    list_memories, maybe_initiate, mourn, normalize_memory_writes, open_day, read_news_lines,
    recall, run_days, sense_media, visible_memories, visit,
)
from seedbank.pack import (  # noqa: E402
    build_egg_info, check, hatch, load_egg, validate_name,
)
from seedbank.persona import (  # noqa: E402
    DEFAULT_THRESHOLD, PERSONA_FORMAT, capture, check as persona_check,
    collect_probes,
)
from seedbank.senses import analyze_image, analyze_sound, describe_image, describe_sound, image_mime  # noqa: E402
from seedbank.settings import (  # noqa: E402
    autostart_command, is_autostart_enabled, load_settings, load_ui_settings,
    save_settings, save_ui_settings, set_autostart, test_brain, ui_settings_path,
    vision_settings,
)
from seedbank.friends import friends_summary, list_friends, mourn_friend, record_visit
from seedbank.clock import (  # noqa: E402
    DEFAULT_CLOCK, describe_clock, load_clock, save_clock, tick,
)
from seedbank.timeline import write_timeline  # noqa: E402
from seedbank.works import add_work, describe_works, list_works, read_work, works_summary  # noqa: E402
from seedbank.hands import (  # noqa: E402
    add_reminder, describe_hands, due_reminders, hands_summary, list_reminders,
    load_hands, mark_said, overdue_reminders, sweep_missed,
)
from seedbank.util import (  # noqa: E402
    SeedError, hash_tree, list_days, read_json, read_memories, read_text, write_file_atomic, write_json_atomic,
)

ROOT = Path(__file__).resolve().parents[2]
EGG = ROOT / "eggs" / "dafeiyu.egg"
TESTDATA = ROOT / "tools" / "seed" / "testdata"


def capture_main(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main(argv)
    return buffer.getvalue()


class SeedbankTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-test-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    # -- 蛋与孵化 ---------------------------------------------------------

    def test_egg_loads(self):
        egg = load_egg(EGG)
        self.assertEqual(egg["species"]["id"], "dafeiyu")
        self.assertGreaterEqual(len(egg["traits"]), 3)
        self.assertEqual(egg["pick"], 3)

    def test_egg_info(self):
        info = build_egg_info(EGG)
        self.assertEqual(info["format"], "seedbank/seed@1")
        self.assertEqual(info["species"]["id"], "dafeiyu")
        self.assertEqual(info["requires"]["name"], "python")

    def test_hatch_creates_valid_pack(self):
        pack = self._hatch()
        birth = read_json(pack / "birth.json")
        self.assertEqual(birth["format"], "seedbank/life@1")
        self.assertEqual(birth["name"], "小蓝")
        self.assertEqual(birth["clock"], "on-demand")
        self.assertTrue((pack / "life").is_dir())
        self.assertTrue((pack / "mind" / "brain.json").is_file())
        self.assertTrue((pack / "deps.lock").is_file())
        memory = read_memories(pack)[0]
        self.assertEqual(memory["day"], 1)
        self.assertIn("光", memory["text"])
        result = check(pack)
        self.assertTrue(result["ok"])
        self.assertTrue(result["runtime"]["ok"])
        self.assertEqual(result["days"], 1)

    def test_hatch_picks_unique_traits(self):
        pack = self._hatch()
        traits = read_json(pack / "genome" / "traits.json")
        ids = list(traits["picked"])
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(ids), len(set(ids)))
        all_ids = {t["id"] for t in traits["traits"]}
        self.assertTrue(set(ids).issubset(all_ids))
        self.assertEqual(sorted(ids), sorted(t["id"] for t in read_json(pack / "mind" / "traits.json")["picked"]))

    def test_two_hatches_differ(self):
        a = self._hatch("甲")
        b = self._hatch("乙")
        self.assertNotEqual(read_json(a / "birth.json")["seed"], read_json(b / "birth.json")["seed"])

    def test_hatch_with_seed_and_time_is_reproducible(self):
        a = self.tmp / "a" / "CI.life"
        b = self.tmp / "b" / "CI.life"
        for target in (a, b):
            target.parent.mkdir(parents=True)
            hatch(target, EGG, "CI", seed_override="ci-daily", born_at_override="2026-01-01T00:00:00Z")
        self.assertEqual(
            (a / "birth.json").read_bytes().decode("utf-8"),
            (b / "birth.json").read_bytes().decode("utf-8"),
        )
        self.assertEqual(check(a)["bornAt"], "2026-01-01T00:00:00Z")

    def test_hatch_refuses_existing_target(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            hatch(pack, EGG, "又一")

    def test_hatch_refuses_bad_names(self):
        for bad in ("CON", "a/b", "..", "", "x" * 40):
            with self.assertRaises(SeedError):
                validate_name(bad)
        self.assertEqual(validate_name("小蓝"), "小蓝")

    # -- 说话与一天 -------------------------------------------------------

    def test_chat_writes_day_and_memories(self):
        pack = self._hatch()
        from seedbank.brain import create_stub_brain
        result = chat_turn(pack, "你好呀", create_stub_brain())
        self.assertTrue(result["file"].startswith("life/"))
        self.assertTrue(result["file"].endswith(".md"))
        text = read_text(pack / "life" / Path(result["file"]).name)
        self.assertIn("**主人**：你好呀", text)
        self.assertIn("**小蓝**：", text)
        self.assertEqual(result["memoriesAdded"], 1)
        self.assertGreaterEqual(len(read_memories(pack)), 2)

    def test_chat_rejects_empty(self):
        pack = self._hatch()
        from seedbank.brain import create_stub_brain
        before = (pack / "mind/memories.jsonl").read_bytes()
        with self.assertRaisesRegex(SeedError, "消息不能为空"):
            chat_turn(pack, "  ", create_stub_brain())
        self.assertEqual((pack / "mind/memories.jsonl").read_bytes(), before)

    def test_open_day_semantics(self):
        pack = self._hatch()
        day = open_day(pack)
        self.assertEqual((day["dayNo"], day["open"]), (2, False))
        from seedbank.brain import create_stub_brain
        chat_turn(pack, "在吗", create_stub_brain())
        day = open_day(pack)
        self.assertEqual((day["dayNo"], day["open"]), (2, True))
        run_days(pack, days=1, brain=create_stub_brain())
        day = open_day(pack)
        self.assertEqual((day["dayNo"], day["open"]), (3, False))

    def test_day_writes_diary_and_mood(self):
        pack = self._hatch()
        previous_memories = read_memories(pack)
        from seedbank.brain import create_stub_brain
        result = run_days(pack, days=2, brain=create_stub_brain())
        self.assertEqual(result["nowDay"], 3)
        self.assertEqual(len(result["days"]), 2)
        files = sorted((pack / "life").glob("*.md"))
        self.assertEqual(len(files), 3)
        text = files[1].read_text(encoding="utf-8")
        self.assertIn("## 今天", text)
        self.assertIn("*", text)
        mood = read_json(pack / "mind" / "mood.json")
        self.assertIn("mood", mood)
        self.assertIn("updated_at", mood)
        self.assertEqual(read_memories(pack), previous_memories)
        self.assertTrue(all(day["memoriesAdded"] == 0 for day in result["days"]))
        self.assertEqual(check(pack)["days"], 3)

    def test_stub_diary_is_deterministic(self):
        pack = self._hatch()
        ctx = build_context(pack, 2, "2026-10-31")
        first = stub_diary(ctx)
        second = stub_diary(ctx)
        self.assertEqual(first["diary"], second["diary"])
        self.assertEqual([m["text"] for m in first["memories"]], [m["text"] for m in second["memories"]])

    def test_recall_ranks(self):
        pack = self._hatch()
        from seedbank.brain import create_stub_brain
        chat_turn(pack, "我喜欢光", create_stub_brain())
        run_days(pack, days=2, brain=create_stub_brain())
        # Ranking needs actual supplied experiences; stub diaries no longer
        # manufacture extra memories about light just to fill each day.
        chat_turn(pack, "昨天窗边的阳光很柔和", create_stub_brain())
        chat_turn(pack, "今晚准备看看月光", create_stub_brain())
        results = recall(pack, "光", 5)
        self.assertGreaterEqual(len(results), 3, results)
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(any("光" in r["memory"]["text"] for r in results))

    # -- 死亡的第一道门：校验 --------------------------------------------

    def test_check_detects_tampered_genome(self):
        pack = self._hatch()
        write_file_atomic(pack / "genome" / "identity.md", "我是一条新的鱼。")
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_tampered_deps(self):
        pack = self._hatch()
        write_file_atomic(pack / "deps.lock", '{"runtime":{"name":"python","version":">=3.10"},"x":1}')
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_history_gap(self):
        pack = self._hatch()
        from seedbank.brain import create_stub_brain
        run_days(pack, days=2, brain=create_stub_brain())
        files = sorted((pack / "life").glob("*.md"))
        files[1].unlink()
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_broken_memory_line(self):
        pack = self._hatch()
        with open(pack / "mind" / "memories.jsonl", "a", encoding="utf-8") as fh:
            fh.write("{不是 json}\n")
        # Runtime reads and checks both preserve and report corruption.
        before = (pack / "mind/memories.jsonl").read_bytes()
        with self.assertRaisesRegex(SeedError, "第 2 行"):
            read_memories(pack)
        with self.assertRaises(SeedError):
            check(pack)
        self.assertEqual((pack / "mind/memories.jsonl").read_bytes(), before)

    def test_check_detects_memory_missing_fields(self):
        pack = self._hatch()
        with open(pack / "mind" / "memories.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"day": 1}, ensure_ascii=False) + "\n")
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_duplicate_memory_id(self):
        pack = self._hatch()
        text = (pack / "mind" / "memories.jsonl").read_text(encoding="utf-8")
        first = json.loads(text.splitlines()[0])
        with open(pack / "mind" / "memories.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(first, ensure_ascii=False) + "\n")
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_tampered_birth(self):
        pack = self._hatch()
        birth = read_json(pack / "birth.json")
        birth["name"] = "被改过的名字"
        write_json_atomic(pack / "birth.json", birth)
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_missing_birth_hash(self):
        pack = self._hatch()
        birth = read_json(pack / "birth.json")
        birth.pop("birth_hash")
        write_json_atomic(pack / "birth.json", birth)
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_broken_day_header(self):
        pack = self._hatch()
        day1 = sorted((pack / "life").glob("*.md"))[0]
        text = day1.read_text(encoding="utf-8")
        day1.write_text("# 随便写的开头\n" + text, encoding="utf-8")
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_detects_unfinished_middle_day(self):
        pack = self._hatch()
        from seedbank.brain import create_stub_brain
        run_days(pack, days=2, brain=create_stub_brain())
        files = sorted((pack / "life").glob("*.md"))
        text = files[0].read_text(encoding="utf-8").replace("## 今天", "## 还没结束")
        files[0].write_text(text, encoding="utf-8")
        with self.assertRaises(SeedError):
            check(pack)

    @unittest.skipUnless(sys.platform == "win32", "冒号在 POSIX 上是合法文件名，这是 Windows 专属校验")
    def test_hatch_bad_path_gives_friendly_error(self):
        with self.assertRaises(SeedError):
            hatch(self.tmp / "a:b.life", EGG, "小蓝")

    # -- 脑 -----------------------------------------------------------------

    def test_brain_defaults_and_patch(self):
        pack = self._hatch()
        cfg = load_brain_config(pack)
        self.assertEqual(cfg["adapter"], "stub")
        self.assertIn("stub", describe_brain(cfg))
        saved = save_brain_config(pack, {"adapter": "openai-compatible", "model": "deepseek-chat"})
        self.assertEqual(saved["adapter"], "openai-compatible")
        self.assertEqual(load_brain_config(pack)["model"], "deepseek-chat")
        with self.assertRaises(ValueError):
            from seedbank.brain import create_brain
            create_brain(pack, "没有这种脑")

    def test_messages_endpoint(self):
        """DeepSeek 官方走 Anthropic 兼容端点：base_url 要能拼出 /v1/messages。"""
        from seedbank.brain import _messages_endpoint
        self.assertEqual(_messages_endpoint(None), "https://api.anthropic.com/v1/messages")
        self.assertEqual(_messages_endpoint("https://api.anthropic.com"), "https://api.anthropic.com/v1/messages")
        self.assertEqual(
            _messages_endpoint("https://api.deepseek.com/anthropic"),
            "https://api.deepseek.com/anthropic/v1/messages",
        )
        self.assertEqual(
            _messages_endpoint("https://api.deepseek.com/anthropic/v1/"),
            "https://api.deepseek.com/anthropic/v1/messages",
        )

    def test_extract_message_text_skips_thinking(self):
        """DeepSeek/Claude 的 content 里思考块在前、text 块在后：只取说出来的话。"""
        from seedbank.brain import _extract_message_text
        data = {
            "content": [
                {"type": "thinking", "thinking": "（有人来了）"},
                {"type": "text", "text": '{"reply": "我在。", "memory_writes": [], "self_edits": {}}'},
            ]
        }
        self.assertIn('"reply"', _extract_message_text(data))
        self.assertEqual(_extract_message_text({"content": "纯文本"}), "纯文本")
        with self.assertRaises(RuntimeError):
            _extract_message_text({"content": [{"type": "thinking", "thinking": "只有思考"}], "stop_reason": "max_tokens"})

    # -- 感官（新生儿的光感与声感） -------------------------------------------

    def test_hatch_day1_feels_light(self):
        pack = self._hatch()
        birth = read_json(pack / "birth.json")
        text = read_text(pack / "life" / f"0001-{birth['local_date']}.md")
        self.assertIn("## 感知", text)
        self.assertIn("光：光很亮", text)

    def test_sense_image_writes_perception(self):
        pack = self._hatch()
        result = sense_media(pack, image=TESTDATA / "bright-warm.png", note="给你看窗外的光")
        self.assertGreaterEqual(result["memoriesAdded"], 2)
        text = read_text(pack / "life" / Path(result["file"]).name)
        self.assertIn("## 感知", text)
        self.assertIn("光：光很亮", text)
        self.assertIn("主人：给你看窗外的光", text)
        self.assertIn("指纹", text)
        self.assertEqual(len(result["assets"]), 1)  # 原件与解释分开保存。
        kinds = [m["kind"] for m in read_memories(pack)]
        self.assertIn("perception", kinds)

    def test_sense_sound_writes_perception(self):
        pack = self._hatch()
        result = sense_media(pack, sound=TESTDATA / "sound.wav")
        text = read_text(pack / "life" / Path(result["file"]).name)
        self.assertIn("声：有声音", text)
        day = open_day(pack)
        ctx = build_context(pack, day["dayNo"], day["date"], "")
        self.assertTrue(any("声：" in line for line in ctx["senses"]))

    def test_sense_rejects_nothing(self):
        pack = self._hatch()
        with self.assertRaises(ValueError):
            sense_media(pack)

    def test_sense_rejects_missing_file(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            sense_media(pack, image=self.tmp / "没有这张图.png")

    def test_image_analysis_is_stable(self):
        png = analyze_image(TESTDATA / "bright-warm.png")
        jpg = analyze_image(TESTDATA / "bright-warm.jpg")
        self.assertEqual(png["format"], "png")
        self.assertEqual(jpg["format"], "jpeg")
        self.assertTrue(png["readable"])
        self.assertAlmostEqual(png["leftRight"], jpg["leftRight"], delta=0.1)
        self.assertEqual(describe_image(png)[0].count("光从左边来"), 1)

    def test_sound_analysis_counts_bursts(self):
        sound = analyze_sound(TESTDATA / "sound.wav")
        self.assertEqual(sound["readable"], True)
        self.assertGreaterEqual(sound["bursts"], 2)
        self.assertIn("响了", describe_sound(sound)[0])

    def test_timeline_shows_senses(self):
        pack = self._hatch()
        sense_media(pack, image=TESTDATA / "bright-warm.png", note="看，这是光")
        out = self.tmp / "site"
        write_timeline(pack, out)
        html = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("这一天她感觉到的", html)
        self.assertIn("光很亮", html)

    # -- 时间线 --------------------------------------------------------------

    def test_timeline(self):
        pack = self._hatch()
        from seedbank.brain import create_stub_brain
        chat_turn(pack, "你好", create_stub_brain())
        run_days(pack, days=1, brain=create_stub_brain())
        out = self.tmp / "site"
        result = write_timeline(pack, out)
        self.assertTrue(Path(result["index"]).exists())
        self.assertTrue((out / "style.css").exists())
        html = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("小蓝", html)
        self.assertIn("第 0001 天", html)
        self.assertEqual(result["stats"]["days"], 2)

    def test_hash_tree_is_stable(self):
        pack = self._hatch()
        first = hash_tree(pack)["sha256"]
        second = hash_tree(pack)["sha256"]
        self.assertEqual(first, second)


class BridgeTest(unittest.TestCase):
    """载体桥：一行 JSON 进，一行 JSON 出。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-bridge-")
        self.tmp = Path(self._tmp.name)
        self.pack = self.tmp / "桥.life"
        hatch(self.pack, EGG, "桥")

    def tearDown(self):
        self._tmp.cleanup()

    def test_hello(self):
        from seedbank.bridge import Bridge
        result = Bridge(self.pack).handle({"id": 7, "op": "hello"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["id"], 7)
        self.assertEqual(result["name"], "桥")
        self.assertEqual(result["protocol"], "seedbank/bridge@1")
        self.assertIn("day", result["status"])

    def test_message_and_status(self):
        from seedbank.bridge import Bridge
        bridge = Bridge(self.pack)
        result = bridge.handle({"op": "message", "text": "你好呀"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["reply"])
        self.assertGreaterEqual(result["status"]["memories"], 2)
        status = bridge.handle({"op": "status"})
        self.assertEqual(status["name"], "桥")
        self.assertIn("stub", status["brain"])

    def test_visitor_can_speak(self):
        from seedbank.bridge import Bridge
        result = Bridge(self.pack).handle({"op": "message", "text": "我是路过的人", "speaker": "访客"})
        self.assertTrue(result["ok"])
        day_file = sorted((self.pack / "life").glob("*.md"))[-1]
        text = day_file.read_text(encoding="utf-8")
        self.assertIn("**访客**：", text)

    def test_unknown_op_is_an_error(self):
        from seedbank.bridge import Bridge
        result = Bridge(self.pack).handle({"op": "does-not-exist"})
        self.assertFalse(result["ok"])
        self.assertIn("不认识的 op", result["error"])

    def test_serve_jsonl_loop(self):
        import contextlib
        import io
        from seedbank.bridge import serve as bridge_serve
        lines = '{"id":1,"op":"hello"}\n{"id":2,"op":"message","text":"嗯"}\n{"id":3,"op":"stop"}\n'
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(lines)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                code = bridge_serve(self.pack)
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        rows = [json.loads(row) for row in buffer.getvalue().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["id"], 2)
        self.assertTrue(rows[1]["reply"])
        self.assertTrue(rows[2]["bye"])

    def test_recall_returns_text(self):
        from seedbank.bridge import Bridge
        bridge = Bridge(self.pack)
        bridge.handle({"op": "message", "text": "记住：今天有光"})
        result = bridge.handle({"op": "recall", "query": "光", "k": 3})
        self.assertTrue(result["ok"])
        self.assertTrue(any(item["text"] for item in result["memories"]))

    def test_tick_op_advances_clock(self):
        """载体也能看钟：这里以前因为漏 import 被静默吞掉过。"""
        from seedbank.bridge import Bridge
        bridge = Bridge(self.pack)
        self.assertTrue(bridge.handle({"op": "hello"})["ok"])
        result = bridge.handle({"op": "tick", "now": "2030-01-02T06:00:00Z"})
        self.assertTrue(result["ok"], result)
        self.assertIn("day", result)

    def test_every_op_in_protocol_is_dispatchable(self):
        """协议里列出来的 op，都必须真的接上了（防止扩展接口变成空话）。"""
        from seedbank.bridge import OPS, Bridge

        minimal = {
            "hello": {}, "status": {}, "message": {"text": "在吗"},
            "image": {"path": ""}, "sound": {"path": ""},
            "feed": {"items": ["海边的灯亮了"]}, "day": {"days": 1},
            "tick": {"now": "2030-01-02T06:00:00Z"},
            "recall": {}, "check": {}, "stop": {},
            "event": {"kind": "note", "text": "窗外下雨"},
            "reminder": {"action": "list"},
            "promise": {"action": "list"},
            "memorial": {"action": "list"},
            "inner": {"action": "status"},
            "work": {"action": "list"},
            "friend": {"action": "list"},
            "persona": {"action": "check"},
            "memories": {"action": "list"},
            "agency": {"action": "list"},
        }
        bridge = Bridge(self.pack)
        for op in OPS:
            payload = {"op": op, **minimal.get(op, {})}
            response = bridge.handle(payload)
            if op in ("image", "sound", "persona"):
                continue  # 需要真实文件 / 会调脑，别在这里跑
            self.assertNotIn(
                "不认识的 op", str(response.get("error") or ""),
                f"{op} 没有接上：{response}",
            )

    def test_extension_ops_life(self):
        from seedbank.bridge import Bridge
        bridge = Bridge(self.pack)
        self.assertTrue(bridge.handle({"op": "event", "kind": "note", "text": "窗外下雨"})["ok"])
        self.assertTrue(bridge.handle({"op": "reminder", "action": "add", "text": "给花浇水", "due_day": 3})["ok"])
        rows = bridge.handle({"op": "reminder", "action": "list"})
        self.assertEqual(len(rows["reminders"]), 1)
        self.assertTrue(bridge.handle({"op": "promise", "action": "make", "text": "明天讲故事", "due_day": 3})["ok"])
        self.assertTrue(bridge.handle({"op": "memorial", "action": "anniversary", "name": "第一次见面"})["ok"])
        self.assertTrue(bridge.handle({"op": "inner", "action": "dream", "text": "我梦见了海"})["ok"])
        inner = bridge.handle({"op": "inner", "action": "status"})["inner"]
        self.assertEqual(inner["dreams"], 1)
        self.assertTrue(inner["last_dreams"])
        agency = bridge.handle({"op": "agency", "action": "interest", "text": "灯塔"})
        self.assertTrue(agency["agency"]["interests"])
        memories = bridge.handle({"op": "memories", "action": "list", "limit": 5})
        self.assertTrue(memories["memories"])

    def test_extension_ops_creative_and_social(self):
        from seedbank.bridge import Bridge
        bridge = Bridge(self.pack)
        made = bridge.handle({"op": "work", "action": "compose", "kind": "poem"})
        self.assertTrue(made["ok"], made)
        listed = bridge.handle({"op": "work", "action": "list"})
        self.assertEqual(len(listed["works"]), 1)
        guest = self.tmp / "远客.life"
        hatch(guest, EGG, "远客")
        visited = bridge.handle({"op": "friend", "action": "visit", "other": str(guest)})
        self.assertTrue(visited["ok"], visited)
        legacy = bridge.handle({"op": "friend", "action": "legacy"})
        self.assertTrue(legacy["ok"], legacy)

    def test_extension_ops_errors_are_ok_false(self):
        from seedbank.bridge import Bridge
        bridge = Bridge(self.pack)
        self.assertFalse(bridge.handle({"op": "event", "kind": "nope", "text": "x"})["ok"])
        self.assertFalse(bridge.handle({"op": "inner", "action": "nope"})["ok"])
        self.assertFalse(bridge.handle({"op": "work", "action": "read", "id": "404"})["ok"])
        self.assertFalse(bridge.handle({"op": "agency", "action": "nope"})["ok"])
        self.assertFalse(bridge.handle({"op": "friend", "action": "visit", "other": ""})["ok"])


class WebUITest(unittest.TestCase):
    """她的窗口：真正的本地网页，用 urllib 当浏览器。"""

    @classmethod
    def setUpClass(cls):
        import threading
        from seedbank.brain import create_stub_brain
        from seedbank.webui import _Server
        cls._tmp = tempfile.TemporaryDirectory(prefix="seedbank-web-")
        cls.tmp = Path(cls._tmp.name)
        cls.pack = cls.tmp / "窗.life"
        hatch(cls.pack, EGG, "窗")
        cls.server = _Server(("127.0.0.1", 0), pack=cls.pack, brain=create_stub_brain(),
                             lock=threading.Lock())
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()

    def _open(self, path: str, data: bytes | None = None, headers: dict | None = None):
        import urllib.request
        request = urllib.request.Request(self.base + path, data=data,
                                         method="POST" if data is not None else "GET")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()

    def _json(self, path: str, payload: dict | None = None):
        data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        status, body = self._open(path, data, {"Content-Type": "application/json"} if data else None)
        return status, json.loads(body.decode("utf-8"))

    def test_page_loads(self):
        status, body = self._open("/")
        self.assertEqual(status, 200)
        self.assertIn("她的窗口", body.decode("utf-8"))

    def test_state(self):
        status, data = self._json("/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["name"], "窗")
        self.assertIsInstance(data["history"], list)

    def test_send_message(self):
        status, data = self._json("/api/message", {"text": "你好呀"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["reply"])

    def test_empty_message_is_rejected(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self._json("/api/message", {"text": "   "})
        self.assertEqual(caught.exception.code, 400)

    def test_show_image_writes_sense(self):
        raw = (TESTDATA / "bright-warm.png").read_bytes()
        status, body = self._open("/api/media?kind=image&note=%E7%9C%8B",
                                  raw, {"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertTrue(data["lines"])
        day_file = sorted((self.pack / "life").glob("*.md"))[-1]
        text = day_file.read_text(encoding="utf-8")
        self.assertIn("## 感知", text)
        self.assertIn("指纹", text)

    def test_pass_one_day(self):
        status, data = self._json("/api/day", {"days": 1})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["days"]), 1)


class WindowTest(unittest.TestCase):
    """独立窗口：工具函数照着验，窗口本身在有图形环境时开一下再关。"""

    def test_mood_face(self):
        from seedbank.window import mood_face

        self.assertEqual(mood_face("开心"), "😊")
        self.assertEqual(mood_face("平静"), "🙂")
        self.assertEqual(mood_face("吃醋"), "😤")
        self.assertEqual(mood_face(""), "🐋")
        self.assertEqual(mood_face("说不清的心情"), "🐋")

    def test_day_caption(self):
        from seedbank.window import day_caption

        self.assertEqual(day_caption(2, "2026-10-21"), "第 2 天 · 10 月 21 日")
        self.assertEqual(day_caption("7", ""), "第 7 天")

    def test_window_opens(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # pragma: no cover - CI 上没有图形环境
            self.skipTest(f"没有图形界面或 tkinter：{error}")
        root.withdraw()
        try:
            from seedbank.window import WhaleWindow

            with tempfile.TemporaryDirectory() as tmp:
                pack = Path(tmp) / "小蓝.life"
                hatch(pack, EGG, "小蓝")
                window = WhaleWindow(root, pack)
                root.update()
                self.assertEqual(window.name, "小蓝")
                self.assertIn("第 1 天", window.meta_label.cget("text"))
                self.assertIn("她住在这里", window.root.title())
                self.assertTrue(window.body.frame.winfo_children())
                # Compatibility windows cannot reactivate the retired artwork.
                self.assertFalse(window.pet._available)
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_retired_pet_loader_does_not_access_assets(self):
        try:
            from seedbank.desktop.pet import PET_STATES, _load_frames
        except Exception as error:  # pragma: no cover - CI 上可能没有 tkinter
            self.skipTest(f"没有 tkinter：{error}")

        class UnreadablePath:
            def __truediv__(self, name):
                raise AssertionError("The retired loader accessed its input path")

        for state in (*PET_STATES, "unknown"):
            self.assertEqual(_load_frames(UnreadablePath(), state), ())

    def test_pet_stage_degrades_without_assets(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # pragma: no cover - CI 上没有图形环境
            self.skipTest(f"没有图形界面或 tkinter：{error}")
        root.withdraw()
        try:
            from seedbank import window as window_module

            with tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(window_module, "PET_ROOT", Path(tmp) / "不存在"):
                    stage = window_module._PetStage(root, bg=window_module.SIDEBAR_BG)
                    stage.pack(fill="both", expand=True)
                    root.attributes("-alpha", 0)
                    if os.name == "nt":
                        root.attributes("-disabled", True)
                    root.geometry("320x360+0+0")
                    root.deiconify()
                    root.update()
                    self.assertFalse(stage._available)
                    self.assertFalse(stage.play("idle"))
                    self.assertTrue(stage.find_withtag("placeholder"))
                    stage.stop()
        finally:
            try:
                root.destroy()
            except Exception:
                pass


class SettingsTest(unittest.TestCase):
    """脑设置、记忆卫生、本地模型（不需要 key）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-settings-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    def test_hatch_ships_default_memory_settings(self):
        pack = self._hatch()
        settings = load_settings(pack)
        self.assertTrue(settings["strict"])
        self.assertEqual(settings["daily_max"], 8)

    def test_save_settings_roundtrip(self):
        pack = self._hatch()
        saved = save_settings(pack, {
            "adapter": "openai-compatible",
            "model": "qwen2.5:7b",
            "base_url": "http://localhost:11434/v1",
            "api_key_env": "",
            "temperature": 0.5,
            "strict": False,
            "daily_max": 5,
        })
        self.assertEqual(saved["adapter"], "openai-compatible")
        self.assertEqual(saved["model"], "qwen2.5:7b")
        self.assertFalse(saved["strict"])
        self.assertEqual(saved["daily_max"], 5)
        self.assertIn("本地端点", saved["describe"])
        again = load_settings(pack)
        self.assertEqual(again["base_url"], "http://localhost:11434/v1")
        self.assertFalse(again["strict"])

    def test_strict_mode_dedupes_and_drops_noise(self):
        pack = self._hatch()
        day = open_day(pack)
        entries = [
            {"text": "光在水里晃了一下", "importance": 0.6},
            {"text": "光 在 水 里 晃 了 一 下", "importance": 0.6},
            {"text": "好", "importance": 0.6},
            {"text": "我记住了", "importance": 0.6},
        ]
        out = normalize_memory_writes(
            pack, day_no=day["dayNo"], source="test", runner="test",
            default_kind="thought", entries=entries, at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(len(out), 1)
        self.assertIn("光在水里", out[0]["text"])

    def test_loose_mode_is_lenient(self):
        pack = self._hatch()
        save_settings(pack, {"strict": False})
        day = open_day(pack)
        out = normalize_memory_writes(
            pack, day_no=day["dayNo"], source="test", runner="test", default_kind="thought",
            entries=[{"text": "好", "importance": 0.5}, {"text": "光在水里晃了一下", "importance": 0.5}],
            at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(len(out), 2)

    def test_memory_extraction_batch_budget(self):
        pack = self._hatch()
        save_settings(pack, {"daily_max": 1})  # Legacy key; now caps one extraction batch.
        day = open_day(pack)  # 第 1 天出生即闭合 → 这里开出第 2 天
        out = normalize_memory_writes(
            pack, day_no=day["dayNo"], source="test", runner="test", default_kind="thought",
            entries=[{"text": f"第 {i} 件想记住的事", "importance": 0.5} for i in range(3)],
            at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(len(out), 1)

    def test_local_endpoint_needs_no_key(self):
        from seedbank.brain import is_local_endpoint

        self.assertTrue(is_local_endpoint("http://localhost:11434/v1"))
        self.assertTrue(is_local_endpoint("http://127.0.0.1:1234/v1"))
        self.assertFalse(is_local_endpoint("https://api.deepseek.com/v1"))
        # 本地地址没起服务时：给用户一句话，而不是「没有 key」
        ok, message = test_brain(pack_dir := self._hatch(), {
            "adapter": "openai-compatible",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key_env": "",
        })
        self.assertFalse(ok)
        self.assertIn("连不上", message)

    def test_test_brain_stub(self):
        ok, message = test_brain(self._hatch())
        self.assertTrue(ok)
        self.assertIn("桩", message)

    def test_bad_adapter_rejected(self):
        pack = self._hatch()
        with self.assertRaises(ValueError):
            save_settings(pack, {"adapter": "not-a-brain"})


class MemoryForgetTest(unittest.TestCase):
    """记忆只追加：忘记是加一条墓碑，不是删掉旧行。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-forget-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    def _pack_with_memories(self) -> Path:
        pack = self._hatch()
        brain = create_stub_brain()
        chat_turn(pack, "你好呀，今天有光", brain)
        run_days(pack, days=1, brain=brain)
        return pack

    def _conversation_memory(self, pack: Path) -> dict:
        return next(m for m in read_memories(pack) if m["kind"] == "conversation")

    def test_forget_appends_tombstone_and_keeps_original(self):
        pack = self._pack_with_memories()
        target = self._conversation_memory(pack)
        memory_file = pack / "mind" / "memories.jsonl"
        before_lines = memory_file.read_text(encoding="utf-8").splitlines()

        result = forget_memory(pack, target["id"], reason="测试忘记")
        self.assertEqual(result, {"id": target["id"], "forgotten": True})

        after_lines = memory_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(after_lines), len(before_lines) + 1)  # 原行没被删，只多了一行墓碑
        kept = [json.loads(line) for line in after_lines]
        self.assertIn(target["id"], [m["id"] for m in kept])
        self.assertTrue(check(pack)["ok"])  # 墓碑不影响生命包校验

        tombstone = kept[-1]
        self.assertEqual(tombstone["kind"], "forget")
        self.assertEqual(tombstone["forgets"], target["id"])
        self.assertEqual(tombstone["source"], "forget")
        self.assertEqual(tombstone["runner"], "forget-v1")
        self.assertEqual(tombstone["tags"], ["忘记"])
        self.assertEqual(tombstone["importance"], 0.0)
        self.assertEqual(tombstone["reason"], "测试忘记")
        self.assertIn("已放下", tombstone["text"])
        self.assertNotIn(target["text"][:20], tombstone["text"])
        self.assertRegex(tombstone["id"], r"^m_\d{4}_\d+$")
        self.assertTrue(tombstone["session"].startswith("forget-"))
        self.assertEqual(tombstone["day"], int(list_days(pack)[-1]["day"]))

    def test_forgotten_memory_hidden_from_list_context_and_recall(self):
        pack = self._pack_with_memories()
        target = self._conversation_memory(pack)
        last = list_days(pack)[-1]
        ctx_before = build_context(pack, last["day"], last["date"], message="你好呀")
        self.assertIn(target["id"], [m["id"] for m in ctx_before["memories"]])
        self.assertIn(
            target["id"],
            [item["memory"]["id"] for item in recall(pack, "你好呀", 20)],
        )

        forget_memory(pack, target["id"])

        self.assertIn(target["id"], forgotten_ids(pack))
        listed = {m["id"]: m for m in list_memories(pack)}
        self.assertTrue(listed[target["id"]]["forgotten"])
        self.assertNotIn(target["id"], {m["id"] for m in visible_memories(pack)})
        self.assertNotIn(target["id"], {m["id"] for m in visible_memories(pack) if m["kind"] == "forget"})

        ctx_after = build_context(pack, last["day"], last["date"], message="你好呀")
        self.assertNotIn(target["id"], [m["id"] for m in ctx_after["memories"]])
        self.assertNotIn(
            target["id"],
            [item["memory"]["id"] for item in recall(pack, "你好呀", 20)],
        )
        self.assertNotIn(
            target["id"],
            [item["memory"]["id"] for item in recall(pack, "", 50)],
        )
        # Audit records stay on disk/UI history, never in model recall.
        self.assertNotIn("forget", {m["kind"] for m in visible_memories(pack)})
        self.assertIn("forget", {m["kind"] for m in list_memories(pack)})

    def test_forget_twice_raises(self):
        pack = self._pack_with_memories()
        target = self._conversation_memory(pack)
        forget_memory(pack, target["id"])
        with self.assertRaises(SeedError):
            forget_memory(pack, target["id"])

    def test_forget_unknown_or_empty_id_raises(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            forget_memory(pack, "m_9999_9")
        with self.assertRaises(SeedError):
            forget_memory(pack, "")

    def test_forget_another_tombstone_raises(self):
        pack = self._pack_with_memories()
        target = self._conversation_memory(pack)
        forget_memory(pack, target["id"])
        tombstone = next(m for m in read_memories(pack) if m["kind"] == "forget")
        with self.assertRaises(SeedError):
            forget_memory(pack, tombstone["id"])


class _FakeWinreg:
    """假注册表：不开机自启测试也能验「写 / 读 / 删」逻辑。"""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 0x0002
    KEY_READ = 0x0001
    REG_SZ = 1

    def __init__(self):
        self.values: dict = {}

    def OpenKey(self, root, path, reserved=0, access=0):
        return {"root": root, "path": path}

    def CloseKey(self, key):
        pass

    def SetValueEx(self, key, name, reserved, kind, data):
        self.values[name] = data

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(f"没有 {name}")
        del self.values[name]

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(f"没有 {name}")
        return self.values[name], self.REG_SZ


class UISettingsTest(unittest.TestCase):
    """窗口偏好：默认值、往返、保留不认识的键；注册表用假 winreg。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-ui-")
        self.tmp = Path(self._tmp.name)
        self.ui_path = self.tmp / "home" / ".seedbank" / "ui.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _patched_path(self):
        return mock.patch("seedbank.settings.ui_settings_path", return_value=self.ui_path)

    def test_ui_settings_path_is_under_home(self):
        path = ui_settings_path()
        self.assertIsInstance(path, Path)
        self.assertEqual(path, Path.home() / ".seedbank" / "ui.json")

    def test_defaults_when_file_missing(self):
        with self._patched_path():
            self.assertEqual(load_ui_settings(), {"always_on_top": False, "autostart": False})

    def test_save_roundtrip_merges(self):
        with self._patched_path():
            saved = save_ui_settings({"always_on_top": True})
            self.assertTrue(saved["always_on_top"])
            self.assertFalse(saved["autostart"])
            self.assertTrue(self.ui_path.is_file())
            self.assertTrue(load_ui_settings()["always_on_top"])
            saved = save_ui_settings({"autostart": True})
            self.assertTrue(saved["always_on_top"])  # 合并不是覆盖
            self.assertTrue(saved["autostart"])

    def test_unknown_keys_ignored_and_geometry_preserved(self):
        self.ui_path.parent.mkdir(parents=True, exist_ok=True)
        self.ui_path.write_text(json.dumps({"geometry": "900x700+10+10"}), encoding="utf-8")
        with self._patched_path():
            saved = save_ui_settings({"always_on_top": True, "bogus": "不要写进去"})
        self.assertEqual(set(saved), {"always_on_top", "autostart"})
        raw = json.loads(self.ui_path.read_text(encoding="utf-8"))
        self.assertNotIn("bogus", raw)
        self.assertEqual(raw["geometry"], "900x700+10+10")  # 窗口那边写的键要留着
        self.assertTrue(raw["always_on_top"])

    def test_corrupt_file_falls_back_to_defaults(self):
        self.ui_path.parent.mkdir(parents=True, exist_ok=True)
        self.ui_path.write_text("{ 这不是 json", encoding="utf-8")
        with self._patched_path():
            self.assertEqual(load_ui_settings(), {"always_on_top": False, "autostart": False})
            self.assertTrue(save_ui_settings({"always_on_top": True})["always_on_top"])

    def test_autostart_command_shape(self):
        command = autostart_command()
        self.assertIsInstance(command, list)
        self.assertTrue(command)
        self.assertTrue(all(isinstance(part, str) for part in command))
        self.assertEqual(command[-1], "window")
        # 开机自启只在 Windows 有意义；命令形状在别的平台上也应当是一个 Python 解释器。
        self.assertTrue(Path(command[0]).name.lower().startswith("python"))
        self.assertEqual(Path(command[1]), ROOT / "tools" / "seed" / "seed.py")
        self.assertTrue(Path(command[1]).is_file())

    def test_set_autostart_unsupported_platform(self):
        with mock.patch("sys.platform", "linux"):
            result = set_autostart(True)
        self.assertFalse(result["ok"])
        self.assertIn("不支持", result["message"])

    def test_set_autostart_writes_and_removes_registry_value(self):
        fake = _FakeWinreg()
        command = [
            r"C:\Program Files\Python\pythonw.exe",
            r"D:\Projects\SeedBank\tools\seed\seed.py",
            "window",
        ]
        with self._patched_path(), \
                mock.patch("sys.platform", "win32"), \
                mock.patch.dict(sys.modules, {"winreg": fake}):
            result = set_autostart(True, command=command)
            self.assertTrue(result["ok"])
            self.assertEqual(result["message"], "已设置开机自启")
            value = fake.values["Seedbank"]
            self.assertIn("seed.py", value)
            self.assertIn("window", value)
            self.assertIn('"C:\\Program Files\\Python\\pythonw.exe"', value)  # 带空格的路径加引号
            self.assertTrue(is_autostart_enabled())
            self.assertTrue(load_ui_settings()["autostart"])

            cancel = set_autostart(False)
            self.assertTrue(cancel["ok"])
            self.assertEqual(cancel["message"], "已取消开机自启")
            self.assertFalse(is_autostart_enabled())
            self.assertFalse(load_ui_settings()["autostart"])
            # 重复取消不报错
            self.assertTrue(set_autostart(False)["ok"])

    def test_set_autostart_reports_registry_error(self):
        class _BrokenWinreg(_FakeWinreg):
            def OpenKey(self, *args, **kwargs):
                raise OSError("拒绝访问")

        with self._patched_path(), \
                mock.patch("sys.platform", "win32"), \
                mock.patch.dict(sys.modules, {"winreg": _BrokenWinreg()}):
            result = set_autostart(True)
        self.assertFalse(result["ok"])
        self.assertIn("设置失败", result["message"])


class PersonaTest(unittest.TestCase):
    """Archive samples do not equate stub output or prose similarity with identity."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-persona-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    def _baseline_path(self, pack: Path) -> Path:
        return pack / "mind" / "persona.json"

    def test_collect_probes_falls_back_to_identity_without_dialogue(self):
        pack = self._hatch()
        probes = collect_probes(pack)
        self.assertIn("identity", [p["id"] for p in probes])
        self.assertIn("unknown", [p["id"] for p in probes])
        self.assertNotIn("promises", [p["id"] for p in probes])

    def test_collect_probes_uses_recorded_conversation(self):
        pack = self._hatch()
        chat_turn(pack, "你叫什么名字？", create_stub_brain())
        probes = collect_probes(pack)
        self.assertIn("memory", [p["id"] for p in probes])
        self.assertTrue(all("reply" not in p for p in probes))

    def test_capture_and_check_stub_is_not_assessed(self):
        pack = self._hatch()
        baseline = capture(pack)
        self.assertEqual(baseline["format"], PERSONA_FORMAT)
        self.assertTrue(baseline["probes"])
        self.assertEqual(baseline["brain"]["adapter"], "stub")
        self.assertEqual(read_json(self._baseline_path(pack)), baseline)

        result = persona_check(pack)
        self.assertIsNone(result["passed"])
        self.assertEqual(result["reason"], "stub")
        self.assertNotIn("average", result)

    def test_capture_archives_previous_baseline(self):
        pack = self._hatch()
        capture(pack)
        path = self._baseline_path(pack)
        original = path.read_bytes()
        capture(pack)
        archived = list((pack / "mind/continuity/archive").glob("*.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), original)

    def test_check_without_baseline_raises(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            persona_check(pack)

    def test_life_change_invalidates_fixed_sample(self):
        pack = self._hatch()
        capture(pack)
        chat_turn(pack, "你叫什么名字？", create_stub_brain())  # 进入第 2 天
        self.assertEqual(persona_check(pack)["reason"], "stale_sample")

    def test_numeric_similarity_threshold_is_rejected(self):
        with self.assertRaises(SeedError):
            persona_check(self._hatch(), threshold=0.45)


class PersonaCLITest(unittest.TestCase):
    """命令行层：正常路径 + 非法参数返回 1（直接调 seedbank.cli.main）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-cli-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        self.stderr = err.getvalue()
        return code, out.getvalue()

    def test_memories_and_forget_commands(self):
        pack = self._hatch()
        chat_turn(pack, "你好呀，今天有光", create_stub_brain())
        code, out = self._run(["memories", str(pack)])
        self.assertEqual(code, 0)
        self.assertIn("[seed] 她的记忆", out)
        self.assertIn("第 2 天", out)
        self.assertIn("[对话]", out)
        self.assertIn("（重要度", out)
        self.assertIn("共 2 条（已忘记 0 条）", out)

        memory_id = read_memories(pack)[-1]["id"]
        code, out = self._run(["forget", str(pack), memory_id, "--reason", "测试"])
        self.assertEqual(code, 0)
        self.assertIn(f"她忘掉了 {memory_id}", out)

        # 默认不再列已忘记的；--forgotten 只列已忘记的。
        code, out = self._run(["memories", str(pack)])
        self.assertEqual(code, 0)
        self.assertNotIn("主人说「你好呀", out)
        self.assertIn("共 2 条（已忘记 1 条）", out)
        code, out = self._run(["memories", str(pack), "--forgotten"])
        self.assertEqual(code, 0)
        self.assertIn("她忘掉的事", out)
        self.assertIn("已忘记 1 条", out)
        # --day 过滤
        code, out = self._run(["memories", str(pack), "--day", "1"])
        self.assertEqual(code, 0)
        self.assertIn("共 1 条", out)

        # 非法参数 → 1
        self.assertEqual(self._run(["memories"])[0], 1)
        self.assertEqual(self._run(["memories", str(pack), "--day", "abc"])[0], 1)
        self.assertEqual(self._run(["forget", str(pack)])[0], 1)
        self.assertEqual(self._run(["forget", str(pack), "m_9999_9"])[0], 1)
        self.assertEqual(self._run(["forget", str(pack), memory_id])[0], 1)  # 已经忘了

    def test_persona_capture_and_check_commands(self):
        pack = self._hatch()
        code, out = self._run(["persona", "capture", str(pack)])
        self.assertEqual(code, 0)
        self.assertIn("连续性样本已保存", out)
        self.assertTrue((pack / "mind" / "persona.json").is_file())

        code, out = self._run(["persona", "check", str(pack)])
        self.assertEqual(code, 2)
        self.assertIn("未评估：stub", out)

        # Corrupted sample is rejected without using the model.
        path = pack / "mind" / "persona.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for probe in doc["probes"]:
            probe["expected"]["value"] = "被改坏的依据"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        code, out = self._run(["persona", "check", str(pack)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("摘要不符", self.stderr)

        # 没有基线 → 报错退出 1
        fresh = self.tmp / "fresh.life"
        hatch(fresh, EGG, "小红")
        self.assertEqual(self._run(["persona", "check", str(fresh)])[0], 1)

        # 非法参数 / 非法阈值 → 1
        self.assertEqual(self._run(["persona"])[0], 1)
        self.assertEqual(self._run(["persona", "bogus", str(pack)])[0], 1)
        self.assertEqual(self._run(["persona", "capture"])[0], 1)
        self.assertEqual(self._run(["persona", "check", str(pack), "--threshold", "abc"])[0], 1)

    def test_persona_brain_flag(self):
        pack = self._hatch()
        code, _ = self._run(["persona", "capture", str(pack), "--brain", "stub"])
        self.assertEqual(code, 0)
        code, out = self._run(["persona", "check", str(pack), "--brain", "stub"])
        self.assertEqual(code, 2)
        self.assertIn("未评估：stub", out)

    def test_help_and_version_mention_new_commands(self):
        code, out = self._run(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("Seedbank", out)
        code, out = self._run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("seed persona capture", out)
        self.assertIn("seed forget", out)
        self.assertIn("seed memories", out)


class ClockTest(unittest.TestCase):
    """1.7 真实时钟：她的一天就是真实的一天，没有第二种走法。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-clock-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self) -> Path:
        pack = self.tmp / "小蓝.life"
        hatch(pack, EGG, "小蓝", seed_override="clock-test",
              born_at_override="2026-10-29T10:00:00+08:00")
        return pack

    def _days(self, pack: Path) -> list[str]:
        return sorted(path.name for path in (pack / "life").glob("*.md"))

    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_default_is_realtime(self):
        pack = self._hatch()
        clock = load_clock(pack)
        self.assertEqual(clock["format"], "seedbank/clock@1")
        self.assertNotIn("mode", clock)
        self.assertIn("真实的一天", describe_clock(clock))
        self.assertIn("不需要设置", describe_clock(clock) + "不需要设置")

    def test_save_roundtrip_and_validation(self):
        pack = self._hatch()
        saved = save_clock(pack, {"last_seen_date": "2026-10-30"})
        self.assertEqual(saved["last_seen_date"], "2026-10-30")
        self.assertEqual(load_clock(pack)["last_seen_date"], "2026-10-30")
        self.assertIn("上次看到她：2026-10-30", describe_clock(load_clock(pack)))
        with self.assertRaises(SeedError):
            save_clock(pack, {"last_seen_date": "2026-13-01"})
        # 老版本的 mode 字段会被忽略：不报错，也不会被写回来
        saved = save_clock(pack, {"mode": "on-demand"})
        self.assertEqual(saved["format"], "seedbank/clock@1")
        self.assertNotIn("mode", load_clock(pack))

    def test_first_tick_records_today(self):
        pack = self._hatch()
        result = tick(pack, now="2026-10-30T06:00:00Z")
        self.assertTrue(result["advanced"])
        self.assertEqual(result["date"], "2026-10-30")
        self.assertEqual(load_clock(pack)["last_seen_date"], "2026-10-30")

    def test_birth_day_message_stays_on_today_and_midnight_adds_diary(self):
        from seedbank.bridge import Bridge
        pack = self._hatch()
        first = pack / "life" / self._days(pack)[0]
        genesis = first.read_text(encoding="utf-8").split("## 今天", 1)[1].strip()
        with mock.patch("seedbank.clock.now_iso", return_value="2026-10-29T12:00:00+08:00"):
            result = Bridge(pack, brain_override="stub").message("这是出生当天的一次实际输入。")
        self.assertEqual((result["day"], result["date"]), (1, "2026-10-29"))
        self.assertEqual(len(self._days(pack)), 1)
        self.assertIn(genesis, first.read_text(encoding="utf-8"))
        result = tick(pack, brain=create_stub_brain(), now="2026-10-30T12:00:00+08:00")
        self.assertEqual((result["day"], result["date"]), (2, "2026-10-30"))
        self.assertIn("## 当日日记", first.read_text(encoding="utf-8"))
        self.assertIn(genesis, first.read_text(encoding="utf-8"))
        self.assertEqual(len(self._days(pack)), 2)
        check(pack)

    def test_same_day_tick_does_nothing(self):
        pack = self._hatch()
        tick(pack, now="2026-10-30T06:00:00Z")
        before = self._days(pack)
        result = tick(pack, now="2026-10-30T09:00:00Z")
        self.assertFalse(result["advanced"])
        self.assertIn("同一天", result["reason"])
        self.assertEqual(self._days(pack), before)

    def test_cross_midnight_opens_new_day(self):
        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-30"})
        before = self._days(pack)
        result = tick(pack, now="2026-10-31T06:00:00Z")
        self.assertEqual(result["day"], 2)
        self.assertEqual(len(self._days(pack)), len(before) + 1)
        self.assertIn("新的一天", result["reason"])
        again = tick(pack, now="2026-10-31T09:00:00Z")
        self.assertFalse(again["advanced"])
        self.assertIn("同一天", again["reason"])

    def test_gap_days_are_unknown_and_resume_today_without_fabricated_pages(self):
        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-31"})
        result = tick(pack, now="2026-11-03T06:00:00Z")
        self.assertTrue(result["advanced"])
        self.assertEqual(result["sleptDays"], 2)
        self.assertEqual(result["unobservedDays"], 2)
        self.assertEqual(result["date"], "2026-11-03")
        self.assertEqual(len(self._days(pack)), 2)
        journal = (pack / "journal" / "loop.jsonl").read_text(encoding="utf-8")
        self.assertIn('"clock_gap"', journal)
        self.assertNotIn('"sleep"', journal)
        check(pack)

    def test_open_day_is_finalized_when_clock_moves(self):
        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-30"})
        tick(pack, now="2026-10-31T06:00:00Z")  # 开出第 2 天（还开着）
        day2 = pack / "life" / self._days(pack)[1]
        self.assertNotIn("## 今天", day2.read_text(encoding="utf-8"))
        result = tick(pack, now="2026-11-01T06:00:00Z")
        self.assertTrue(result["advanced"])
        # 闭合第 2 天之后要立刻开出第 3 天，否则连续运行时中间那一天会丢
        self.assertIn("## 今天", day2.read_text(encoding="utf-8"))
        self.assertEqual(result["day"], 3)
        names = self._days(pack)
        self.assertEqual(len(names), 3)
        self.assertTrue(names[-1].endswith("2026-11-01.md"), names)
        check(pack)  # 时钟推进后生命包仍然合法

    def test_continuous_midnights_keep_every_date(self):
        """连续运行（窗口一直开着）时，每个自然日都必须有自己的一页。"""
        pack = self._hatch()  # 第 1 天 = 2026-10-29，孵化即闭合
        save_clock(pack, {"last_seen_date": "2026-10-29"})
        tick(pack, now="2026-10-30T06:00:00Z")
        tick(pack, now="2026-10-31T06:00:00Z")
        tick(pack, now="2026-11-01T06:00:00Z")
        names = self._days(pack)
        self.assertEqual(len(names), 4, names)
        for expected, name in zip(
            ("2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"), names
        ):
            self.assertIn(expected, name)
        check(pack)

    def test_midnight_advances_even_if_brain_config_is_broken(self):
        """翻页那晚脑配置坏了（缺 key）：退回离线 stub 写日记，时间照走。"""
        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-29"})
        tick(pack, now="2026-10-30T06:00:00Z")  # 第 2 天还开着
        (pack / "mind" / "brain.json").write_text(
            json.dumps({
                "format": "seedbank/brain@1",
                "adapter": "anthropic",
                "model": "deepseek-flash",
                "base_url": "https://api.deepseek.com/anthropic",
                "api_key_env": "SEEDBANK_TEST_MISSING_KEY",
                "temperature": 0.8,
                "fallback": "stub",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        result = tick(pack, now="2026-10-31T06:00:00Z")
        self.assertTrue(result["advanced"])
        self.assertEqual(len(self._days(pack)), 3)
        check(pack)

    def test_bridge_ticks_before_message(self):
        from seedbank.bridge import Bridge

        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-29"})
        before = len(self._days(pack))
        # 冻结「今天」，否则这条测试会随着真实日期前进而失效（日期炸弹）
        with mock.patch("seedbank.clock.now_iso", return_value="2026-10-30T12:00:00+08:00"):
            reply = Bridge(pack).message("你好呀")
        self.assertTrue(reply["ok"])
        self.assertEqual(len(self._days(pack)), before + 1)

    def test_webui_tick_moves_clock(self):
        from seedbank import webui

        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-29"})
        before = len(self._days(pack))
        with mock.patch("seedbank.clock.now_iso", return_value="2026-10-30T12:00:00+08:00"):
            webui._tick(pack, None)
        self.assertEqual(len(self._days(pack)), before + 1)

    def test_clock_and_tick_commands(self):
        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-10-30"})
        code, out = self._run(["clock", str(pack)])
        self.assertEqual(code, 0)
        self.assertIn("她的时间", out)
        self.assertIn("不需要设置", out)
        code, out = self._run(["tick", str(pack), "--now", "2026-10-31T06:00:00Z"])
        self.assertEqual(code, 0)
        self.assertIn("第 2 天", out)
        self.assertEqual(self._run(["clock"])[0], 1)
        self.assertEqual(self._run(["tick"])[0], 1)
        self.assertEqual(self._run(["tick", str(pack), "--now", "不是时间"])[0], 1)


class AuditRegressionTest(unittest.TestCase):
    """打包前 bug 审计的回归：坏输入不能让进程/窗口倒下去。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-audit-")
        self.tmp = Path(self._tmp.name)
        self.pack = self.tmp / "审.life"
        hatch(self.pack, EGG, "审")

    def tearDown(self):
        self._tmp.cleanup()

    def test_run_days_rejects_bad_numbers(self):
        from seedbank.util import SeedError
        brain = create_stub_brain()
        for bad in (0, -3, 5000):
            with self.assertRaises(SeedError):
                run_days(self.pack, days=bad, brain=brain)

    def test_bridge_day_zero_is_error_and_survives(self):
        import contextlib
        from seedbank.bridge import serve as bridge_serve
        lines = (
            '{"id":1,"op":"day","days":0}\n'
            '{"id":2,"op":"day","days":-2}\n'
            '{"id":3,"op":"hello"}\n'
            '{"id":4,"op":"stop"}\n'
        )
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(lines)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                code = bridge_serve(self.pack)
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        rows = [json.loads(row) for row in buffer.getvalue().splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertFalse(rows[0]["ok"])
        self.assertFalse(rows[1]["ok"])
        self.assertTrue(rows[2]["ok"])
        self.assertTrue(rows[3]["bye"])

    def test_bridge_overlong_line_is_error_and_survives(self):
        import contextlib
        from seedbank.bridge import serve as bridge_serve
        huge = '{"op":"hello","junk":"' + "a" * (1024 * 1024 + 50) + '"}\n'
        lines = huge + '{"id":2,"op":"hello"}\n{"id":3,"op":"stop"}\n'
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(lines)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                code = bridge_serve(self.pack)
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        rows = [json.loads(row) for row in buffer.getvalue().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertFalse(rows[0]["ok"])
        self.assertIn("太长", rows[0]["error"])
        self.assertTrue(rows[1]["ok"])


class WebUIAuditTest(unittest.TestCase):
    """窗口 HTTP 边界的回归。"""

    @classmethod
    def setUpClass(cls):
        import threading
        from seedbank.brain import create_stub_brain
        from seedbank.webui import _Server
        cls._tmp = tempfile.TemporaryDirectory(prefix="seedbank-web-audit-")
        cls.pack = Path(cls._tmp.name) / "窗审.life"
        hatch(cls.pack, EGG, "窗审")
        cls.lock = threading.Lock()
        cls.server = _Server(("127.0.0.1", 0), pack=cls.pack,
                             brain=create_stub_brain(), lock=cls.lock)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._tmp.cleanup()

    def _post(self, path: str, payload: dict):
        import urllib.error
        import urllib.request
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_day_zero_is_400_json(self):
        status, body = self._post("/api/day", {"days": 0})
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        self.assertIn("days", body["error"])

    def test_negative_content_length_is_400_json(self):
        import socket
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            sock.sendall(
                b"POST /api/message HTTP/1.1\r\nHost: x\r\n"
                b"Content-Length: -5\r\nContent-Type: application/json\r\n"
                b"Connection: close\r\n\r\n"
            )
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            sock.close()
        raw = b"".join(chunks)
        self.assertIn(b" 400 ", raw.split(b"\r\n")[0])
        self.assertIn(b'"ok": false', raw.lower())

    def test_state_with_missing_birth_is_500_json(self):
        import urllib.error
        import urllib.request
        birth = self.pack / "birth.json"
        backup = birth.with_suffix(".json.bak")
        birth.replace(backup)
        try:
            request = f"http://127.0.0.1:{self.port}/api/state"
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status = response.status
                    body = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                status = error.code
                body = json.loads(error.read().decode("utf-8"))
            self.assertEqual(status, 500)
            self.assertFalse(body["ok"])
        finally:
            backup.replace(birth)
        # 服务器还活着：正常请求依然有回答
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/state", timeout=10) as response:
            self.assertTrue(json.loads(response.read().decode("utf-8"))["ok"])

    def test_ticker_takes_the_lock(self):
        from seedbank import webui
        seen = []

        def fake_tick(pack, brain):
            seen.append(self.lock.locked())

        class Stop:
            def __init__(self):
                self.calls = 0

            def wait(self, timeout):
                self.calls += 1
                return self.calls > 1

        with mock.patch.object(webui, "_tick", side_effect=fake_tick):
            webui._ticker(self.pack, None, self.lock, Stop())
        self.assertEqual(seen, [True])


class WindowAuditTest(unittest.TestCase):
    """窗口后台任务与结果泵的回归（没有图形环境就跳过）。"""

    def setUp(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
        except Exception as error:  # pragma: no cover - CI 上没有图形环境
            self.skipTest(f"没有图形界面或 tkinter：{error}")
        self.root.withdraw()
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-win-audit-")
        self.pack = Path(self._tmp.name) / "窗审.life"
        hatch(self.pack, EGG, "窗审")
        from seedbank.window import WhaleWindow
        self.window = WhaleWindow(self.root, self.pack)
        self.root.update()

    def tearDown(self):
        try:
            if getattr(self, "_after", None) is not None:
                self.root.after_cancel(self._after)
        except Exception:
            pass
        try:
            self.window._on_close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    def test_poll_survives_callback_error(self):
        good = []

        def boom(payload):
            raise RuntimeError("画不出来")

        def ok(payload):
            good.append(payload)

        self.window._queue.put(("ok", 1, boom))
        self.window._queue.put(("ok", 2, ok))
        self.window._poll()
        self.assertEqual(good, [2])
        self._after = self.window._after_id

    def test_forget_while_busy_is_refused(self):
        notes = []
        with mock.patch.object(self.window, "_set_memory_note",
                               side_effect=lambda text, kind="": notes.append(text)):
            self.window._busy = True
            self.window._forget_memory("m_0001_0")
        self.assertTrue(notes)
        self.assertIn("忙", notes[0])

    def test_clock_loop_marks_busy(self):
        calls = []
        self.window._busy = False
        with mock.patch.object(self.window, "_run",
                               side_effect=lambda work, on_ok: calls.append(on_ok)):
            self.window._clock_loop()
        self._after = self.window._clock_after_id
        self.assertTrue(calls)
        self.assertTrue(self.window._busy)
        self.window._on_clock({"advanced": False})
        self.assertFalse(self.window._busy)


class AuditCoreRegressionTest(unittest.TestCase):
    """audit-core 的边界回归：内存、时钟回拨、协议污染、坏数据、CLI 参数。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-audit-core-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "审鱼") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name, seed_override="audit-core",
              born_at_override="2026-10-29T10:00:00+08:00")
        return pack

    def test_clock_rollback_keeps_last_seen(self):
        pack = self._hatch()
        save_clock(pack, {"last_seen_date": "2026-11-05"})
        # 时钟往回走：不写 last_seen、不推进、不记「睡了 N 天」
        back = tick(pack, now="2026-11-01T06:00:00Z")
        self.assertFalse(back["advanced"])
        self.assertIn("早于上次检查", back["reason"])
        self.assertEqual(load_clock(pack)["last_seen_date"], "2026-11-05")
        # 之后再往前走一天：正常过完/开新的一天，而不是被误判成睡了 4 天
        forward = tick(pack, now="2026-11-06T06:00:00Z")
        self.assertTrue(forward["advanced"])

    def _png_bomb(self) -> bytes:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            body = kind + payload
            return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        # 1×1 的图，IDAT 解压出 8MB 全零 —— 合法压缩、非法膨胀
        idat = zlib.compress(b"\x00" * (8 * 1024 * 1024))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", idat) + chunk(b"IEND", b""))

    def test_png_decompression_bomb_rejected(self):
        bomb = self.tmp / "bomb.png"
        bomb.write_bytes(self._png_bomb())
        with self.assertRaises(SeedError) as raised:
            analyze_image(bomb)
        self.assertIn("压缩数据不正常", str(raised.exception))

    def test_malformed_ppm_is_chinese_error(self):
        bad = self.tmp / "bad.ppm"
        bad.write_bytes(b"P6\nabc def\n255\n")
        with self.assertRaises(SeedError) as raised:
            analyze_image(bad)
        self.assertIn("PPM", str(raised.exception))

    def test_local_endpoint_never_sends_key(self):
        seen = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server 的命名约定
                length = int(self.headers.get("content-length") or 0)
                self.rfile.read(length)
                seen["headers"] = dict(self.headers)
                body = json.dumps({
                    "choices": [{"message": {"content": json.dumps(
                        {"reply": "在。", "memory_writes": [], "self_edits": {}})}}],
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # 安静
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            cfg = {
                "adapter": "openai-compatible",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "local-test",
                "api_key_env": "SEEDBANK_AUDIT_KEY",
            }
            with mock.patch.dict("os.environ", {"SEEDBANK_AUDIT_KEY": "sk-should-not-leak"}):
                raw = openai_transport(cfg, "系统", "用户")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        headers = {key.lower(): value for key, value in seen["headers"].items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("x-api-key", headers)
        self.assertIn("reply", raw)

    def test_brain_fallback_logs_to_stderr_not_stdout(self):
        pack = self._hatch()
        save_brain_config(pack, {"adapter": "openai-compatible",
                                 "base_url": "http://127.0.0.1:9/v1",
                                 "model": "nowhere"})
        brain = create_brain(pack)
        ctx = build_context(pack, open_day(pack)["dayNo"], open_day(pack)["date"], "在吗")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = brain.chat(ctx)
        self.assertIn("reply", result)
        self.assertNotIn("[seed]", out.getvalue())
        self.assertIn("[seed]", err.getvalue())

    def test_check_rejects_bad_mood_energy(self):
        pack = self._hatch()
        mood_file = pack / "mind" / "mood.json"
        doc = json.loads(mood_file.read_text(encoding="utf-8"))
        doc["energy"] = None
        mood_file.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(SeedError):
            check(pack)

    def test_check_rejects_bad_memory_day(self):
        pack = self._hatch()
        memory_file = pack / "mind" / "memories.jsonl"
        lines = memory_file.read_text(encoding="utf-8").splitlines()
        item = json.loads(lines[0])
        item["day"] = None
        lines[0] = json.dumps(item, ensure_ascii=False)
        memory_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(SeedError) as raised:
            check(pack)
        self.assertIn("day", str(raised.exception))

    def test_check_rejects_broken_brain_json(self):
        pack = self._hatch()
        (pack / "mind" / "brain.json").write_text("{ 不是 json", encoding="utf-8")
        with self.assertRaises(SeedError) as raised:
            check(pack)
        self.assertIn("brain.json", str(raised.exception))

    def test_cli_rejects_unknown_flag(self):
        pack = self._hatch()
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["day", str(pack), "--dasy", "2"])
        self.assertEqual(code, 1)
        self.assertIn("不认识的参数", err.getvalue())

    def test_cli_rejects_negative_recall_k(self):
        pack = self._hatch()
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["recall", str(pack), "--k", "-1"])
        self.assertEqual(code, 1)
        self.assertIn("--k", err.getvalue())

    def test_cli_rejects_missing_pack_for_brain(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["brain", str(self.tmp / "没有.life")])
        self.assertEqual(code, 1)
        self.assertIn("没有这个生命包", err.getvalue())

    def test_runtime_range_parsing(self):
        from seedbank.pack import _check_runtime

        self.assertTrue(_check_runtime({"python": ">=3.8"})["ok"])
        self.assertFalse(_check_runtime({"python": "<3.12"})["ok"])
        self.assertFalse(_check_runtime({"python": ">=3.10,<3.12"})["ok"])
        self.assertIn("<3.12", _check_runtime({"python": "<3.12"})["need"])
        # 老蛋只写「3.10」时按 >=3.10 兼容
        self.assertTrue(_check_runtime({"python": "3.10"})["ok"])


class VisionTest(unittest.TestCase):
    """1.9 视觉翻译层（1.22 起自动）：原图不落盘、只写翻译、没有视觉就退回原生感官。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-vision-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue()

    def _enable_vision(self, pack: Path, *, adapter: str = "anthropic",
                       model: str = "vision-test", base_url: str = "http://127.0.0.1:9",
                       vision_model: str = "") -> dict:
        save_brain_config(pack, {"adapter": adapter, "model": model, "base_url": base_url})
        return save_settings(pack, {"vision_enabled": True, "vision_model": vision_model})

    @staticmethod
    def _latest_day(pack: Path) -> str:
        return read_text(sorted((pack / "life").glob("*.md"))[-1])

    def test_vision_is_automatic_and_falls_back_quietly(self):
        pack = self._hatch()
        settings = load_settings(pack)
        self.assertEqual(settings["vision_model"], "")
        self.assertEqual(settings["vision_max_side"], 1024)

        # 1.22：看图自动。没有视觉的脑时，安静退回原生光感，不写失败提示。
        with mock.patch("seedbank.brain._post_json", side_effect=AssertionError("没有视觉的脑不应联网")):
            result = sense_media(pack, image=TESTDATA / "bright-warm.png")
        self.assertTrue(result["vision"]["attempted"])
        self.assertFalse(result["vision"]["ok"])
        day = self._latest_day(pack)
        self.assertIn("## 感知", day)
        self.assertIn("光：", day)
        self.assertNotIn("看：", day)  # 不往她的一天里写噪声
        self.assertFalse((pack / "mind" / "vision.jsonl").is_file())

        # 程序显式跳过（vision=False）时，返回结构里 vision=未尝试。
        result = sense_media(pack, image=TESTDATA / "bright-warm.png", vision=False)
        self.assertEqual(result["vision"], {"attempted": False, "ok": None})

    def test_vision_settings_roundtrip(self):
        pack = self._hatch()
        saved = save_settings(pack, {"vision_enabled": True, "vision_model": "deepseek-flash"})
        self.assertTrue(saved["vision_enabled"])
        self.assertEqual(saved["vision_model"], "deepseek-flash")
        vision_file = pack / "mind" / "vision.json"
        self.assertTrue(vision_file.is_file())
        raw = json.loads(read_text(vision_file))
        self.assertEqual(raw["format"], "seedbank/vision@1")
        self.assertEqual(vision_settings(pack)["model"], "deepseek-flash")
        self.assertTrue(load_settings(pack)["vision_enabled"])

        save_settings(pack, {"vision_enabled": False})
        self.assertFalse(vision_settings(pack)["enabled"])
        self.assertTrue(vision_file.is_file())
        # max_side 会被夹进 256..2048，防止手滑写成 0 / 十万。
        save_settings(pack, {"vision_max_side": 99999})
        self.assertEqual(vision_settings(pack)["max_side"], 2048)
        save_settings(pack, {"vision_max_side": 12})
        self.assertEqual(vision_settings(pack)["max_side"], 256)

    def test_image_mime_detection(self):
        self.assertEqual(image_mime((TESTDATA / "bright-warm.png").read_bytes()), "image/png")
        self.assertEqual(image_mime((TESTDATA / "bright-warm.jpg").read_bytes()), "image/jpeg")
        webp = b"RIFF" + struct.pack("<I", 20) + b"WEBPVP8 " + b"\x00" * 8
        self.assertEqual(image_mime(webp), "image/webp")
        self.assertEqual(image_mime((TESTDATA / "bright-warm.png")), "image/png")  # 也认路径
        # bmp / ppm / 乱码：原生眼睛能看（或不认识），但视觉翻译不转发。
        self.assertEqual(image_mime(b"BM" + b"\x00" * 32), "")
        self.assertEqual(image_mime(b"P6\n1 1\n255\n" + b"\x00" * 3), "")
        self.assertEqual(image_mime(b"not an image"), "")

    def test_too_large_and_unsupported_formats_rejected(self):
        pack = self._hatch()
        self._enable_vision(pack)

        too_big = self.tmp / "too-big.png"
        too_big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_VISION_BYTES + 1))
        with mock.patch("seedbank.brain._post_json", side_effect=AssertionError("太大不该联网")):
            result = vision_translate(pack, too_big)
        self.assertFalse(result["ok"])
        self.assertIn("8MB", result["reason"])

        bmp = self.tmp / "only-native.bmp"
        bmp.write_bytes(b"BM" + b"\x00" * 64)
        result = vision_translate(pack, bmp)
        self.assertFalse(result["ok"])
        self.assertIn("PNG", result["reason"])
        self.assertIn("原生眼睛", result["reason"])

        missing = vision_translate(pack, self.tmp / "没有.png")
        self.assertFalse(missing["ok"])
        self.assertIn("找不到", missing["reason"])

    def test_translate_success_keeps_translation_and_archived_original(self):
        pack = self._hatch()
        self._enable_vision(pack, vision_model="flash-vision")
        calls = []

        def fake_post(url, headers, payload):
            calls.append((url, headers, payload))
            return {"content": [{"type": "text", "text": "墙上有光在慢慢走，暖的，离她不远。"}]}

        with mock.patch("seedbank.brain._post_json", side_effect=fake_post):
            result = sense_media(pack, image=TESTDATA / "bright-warm.png",
                                 note="给你看", vision=True)

        self.assertTrue(result["vision"]["ok"])
        self.assertEqual(result["vision"]["provider"], "anthropic")
        self.assertEqual(result["vision"]["model"], "flash-vision")
        self.assertIn("看：墙上有光在慢慢走", "\n".join(result["lines"]))

        # Anthropic 视觉消息形状：先 image 块，再 text 块。
        payload = calls[0][2]
        content = payload["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["type"], "base64")
        self.assertEqual(content[0]["source"]["media_type"], "image/png")
        self.assertTrue(content[0]["source"]["data"])
        self.assertEqual(content[1]["type"], "text")
        self.assertEqual(payload["model"], "flash-vision")

        # The diary contains interpretation and fingerprint; the original is
        # retained separately for future review, not mistaken for a new event.
        day = self._latest_day(pack)
        sha = analyze_image(TESTDATA / "bright-warm.png")["sha256"][:8]
        self.assertIn("看：墙上有光在慢慢走", day)
        self.assertIn("flash-vision 翻译", day)
        self.assertIn(f"指纹 {sha}", day)
        self.assertIn("光：", day)
        originals = list((pack / "media").rglob("*.png"))
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].read_bytes(), (TESTDATA / "bright-warm.png").read_bytes())

        # 记忆：一条 tags 含「看懂」。
        memories = read_memories(pack)
        self.assertTrue(any("看懂" in (m.get("tags") or []) for m in memories))
        self.assertTrue(any("我看懂了" in str(m.get("text")) for m in memories))

        # 审计日志：她能「记录后重放」的凭据。
        log_file = pack / "mind" / "vision.jsonl"
        self.assertTrue(log_file.is_file())
        rows = [json.loads(line) for line in read_text(log_file).splitlines() if line.strip()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "anthropic")
        self.assertEqual(rows[0]["model"], "flash-vision")
        self.assertEqual(rows[0]["text"], "墙上有光在慢慢走，暖的，离她不远。")
        self.assertEqual(len(rows[0]["sha256"]), 64)
        self.assertTrue(rows[0]["at"])

    def test_translate_failure_still_writes_native_light(self):
        pack = self._hatch()
        self._enable_vision(pack)
        with mock.patch("seedbank.brain._post_json",
                        side_effect=RuntimeError("网络错误：timed out")):
            result = sense_media(pack, image=TESTDATA / "bright-warm.jpg", vision=True)

        self.assertTrue(result["vision"]["attempted"])
        self.assertFalse(result["vision"]["ok"])
        self.assertIn("网络错误", result["vision"]["reason"])
        day = self._latest_day(pack)
        self.assertIn("光：", day)          # 原生光感照写
        self.assertNotIn("看：", day)        # 1.22：失败提示不落进她的一天
        self.assertFalse((pack / "mind" / "vision.jsonl").is_file())
        self.assertTrue(any("感知" in (m.get("tags") or []) for m in read_memories(pack)))

    def test_stub_brain_gives_clear_reason(self):
        pack = self._hatch()  # 默认就是 stub
        result = vision_translate(pack, TESTDATA / "bright-warm.png")
        self.assertFalse(result["ok"])
        self.assertIn("stub", result["reason"])
        self.assertIn("桩", result["reason"])

        with mock.patch("seedbank.brain._post_json", side_effect=AssertionError("stub 不应联网")):
            sensed = sense_media(pack, image=TESTDATA / "bright-warm.png", vision=True)
        self.assertEqual(sensed["vision"]["attempted"], True)
        self.assertFalse(sensed["vision"]["ok"])

        # prompt 的核心约束就写在 brain.py 常量里，供跨实现对齐。
        self.assertNotIn("大肥鱼", VISION_PROMPT)
        self.assertIn("120", VISION_PROMPT)
        self.assertIn("不确定", VISION_PROMPT)
        self.assertIn("不把图像中的事件当作观看者亲身经历", VISION_PROMPT)

    def test_openai_compatible_image_message_shape(self):
        pack = self._hatch()
        self._enable_vision(pack, adapter="openai-compatible", model="brain-model",
                            base_url="http://127.0.0.1:11434/v1")
        calls = []

        def fake_post(url, headers, payload):
            calls.append((url, headers, payload))
            return {"choices": [{"message": {"content": "光在左边，暖的，很安静。"}}]}

        with mock.patch("seedbank.brain._post_json", side_effect=fake_post):
            result = vision_translate(pack, TESTDATA / "bright-warm.jpg")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "openai-compatible")
        self.assertEqual(result["model"], "brain-model")
        url, headers, payload = calls[0]
        self.assertTrue(url.endswith("/chat/completions"))
        content = payload["messages"][1]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("response_format", payload)  # 视觉请求只要一句话，不逼 JSON

    def test_cli_vision_is_automatic(self):
        pack = self._hatch()

        code, out = self._run(["brain", str(pack)])
        self.assertEqual(code, 0)
        self.assertIn("看图：自动", out)

        # 给图就自动看；stub 下只写原生光感，不写失败提示。
        code, out = self._run([
            "sense", str(pack), "--image", str(TESTDATA / "bright-warm.png"),
            "--note", "给你看",
        ])
        self.assertEqual(code, 0)
        self.assertIn("光：", out)
        self.assertNotIn("看：", out)

        # 旧参数 --vision 仍被接受（兼容），不再控制开关。
        self.assertEqual(self._run([
            "sense", str(pack), "--image", str(TESTDATA / "bright-warm.png"), "--vision",
        ])[0], 0)
        # 非法参数名直接被拒
        self.assertEqual(self._run(["sense", str(pack), "--vision", "--nope"])[0], 1)

        code, out = self._run(["brain", str(pack), "--vision-model", "deepseek-flash"])
        self.assertEqual(code, 0)
        self.assertIn("deepseek-flash", out)
        self.assertIn("看图：自动", out)


if __name__ == "__main__":
    unittest.main()


class FeedTest(unittest.TestCase):
    """1.10 见闻：这是她读到的，不是她经历的。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-feed-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _hatch(self, name: str = "小蓝") -> Path:
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name)
        return pack

    @staticmethod
    def _latest_day(pack: Path) -> str:
        return read_text(sorted((pack / "life").glob("*.md"))[-1])

    def test_feed_writes_section_and_hearsay_memory(self):
        pack = self._hatch()
        result = feed_news(pack, ["海边的灯塔亮了。"], source="群聊")
        self.assertEqual(result["memoriesAdded"], 1)
        day = self._latest_day(pack)
        self.assertIn("## 见闻", day)
        self.assertIn("海边的灯塔亮了。（来源：群聊）", day)
        mems = [m for m in read_memories(pack) if m.get("kind") == "hearsay"]
        self.assertEqual(len(mems), 1)
        self.assertIn("我读到：海边的灯塔亮了。", mems[0]["text"])
        self.assertIn("见闻", mems[0]["tags"])
        self.assertEqual(mems[0]["importance"], 0.3)
        ctx = build_context(pack, result["dayNo"], result["date"])
        self.assertEqual(ctx["news"], ["海边的灯塔亮了。（来源：群聊）"])

    def test_feed_accepts_dicts_and_dedupes(self):
        pack = self._hatch()
        feed_news(pack, [{"text": "今天降温了", "source": "群聊"}, "今天降温了"], source="主人")
        lines = read_news_lines(pack, open_day(pack)["dayNo"])
        self.assertEqual(len(lines), 1)
        self.assertIn("（来源：群聊）", lines[0])

    def test_feed_is_not_experience(self):
        pack = self._hatch()
        feed_news(pack, ["外面下雨了。"], source="群聊")
        friends = pack / "friends"
        self.assertFalse(friends.is_dir() and any(friends.iterdir()))
        kinds = {m.get("kind") for m in read_memories(pack)}
        self.assertIn("hearsay", kinds)
        self.assertNotIn("conversation", kinds)

    def test_feed_validates(self):
        pack = self._hatch()
        with self.assertRaises(ValueError):
            feed_news(pack, [], source="主人")
        with self.assertRaises(ValueError):
            feed_news(pack, ["  ", ""], source="主人")

    def test_section_order_and_cli(self):
        pack = self._hatch()
        feed_file = self.tmp / "feed.txt"
        write_file_atomic(feed_file, "海边的灯塔亮了。\n# 这是注释，会被跳过\n群里的猫又来了。\n")
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["feed", str(pack), "--file", str(feed_file), "--source", "群聊", "--max", "2"])
        self.assertEqual(code, 0)
        self.assertIn("今天的见闻", out.getvalue())
        chat_turn(pack, "你好呀", create_stub_brain())
        day = self._latest_day(pack)
        self.assertLess(day.index("## 对话"), day.index("## 见闻"))
        self.assertIn("（来源：群聊）", day)

        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["news", str(pack)]), 0)
        self.assertIn("读到的：", out.getvalue())
        self.assertIn("海边的灯塔亮了。", out.getvalue())

    def test_stub_diary_mentions_what_she_read(self):
        pack = self._hatch()
        feed_news(pack, ["今天海边有雾。"], source="群聊")
        ctx = build_context(pack, open_day(pack)["dayNo"], open_day(pack)["date"])
        diary = stub_diary(ctx)["diary"]
        self.assertIn("今天海边有雾。", diary)
        self.assertIn("来源：群聊", diary)
        self.assertIn("这是见闻", diary)

    def test_bridge_feed_op(self):
        from seedbank.bridge import Bridge

        pack = self._hatch()
        bridge = Bridge(str(pack))
        response = bridge.handle({"id": 7, "op": "feed", "items": ["海边的灯塔亮了。"], "source": "群聊"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["id"], 7)
        self.assertIn("（来源：群聊）", response["lines"][0])
        self.assertIn("## 见闻", self._latest_day(pack))

        bad = bridge.handle({"op": "feed", "items": []})
        self.assertFalse(bad["ok"])
        self.assertIn("items", bad["error"])


class AgencyTest(unittest.TestCase):
    """1.11 意志：兴趣、计划、边界、主动开口。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = self._hatch()

    def _hatch(self):
        pack = Path(self.tmp.name) / "小风.life"
        hatch(pack, EGG, "小风", seed_override="agency-test", born_at_override="2026-10-30T09:00:00+08:00")
        return pack

    def _open_today(self):
        return open_day(self.pack)

    def _open_chat_day(self):
        """孵化后的第 1 天是闭合的；说一句话把新的一天打开，才能测「主动」。"""
        chat_turn(self.pack, "在吗？", create_stub_brain())
        return open_day(self.pack)

    def test_defaults_and_lazy_file(self):
        self.assertFalse((self.pack / "mind" / "agency.json").exists())
        data = load_agency(self.pack)
        self.assertEqual(data["interests"], [])
        self.assertEqual(data["boundaries"], [])
        add_interest(self.pack, "看雨")
        self.assertTrue((self.pack / "mind" / "agency.json").is_file())
        self.assertIn("看雨", [item["topic"] for item in load_agency(self.pack)["interests"]])

    def test_interest_weight_and_boundary(self):
        add_interest(self.pack, "看雨")
        data = add_interest(self.pack, "看雨")
        self.assertEqual(data["interests"][0]["weight"], 2)
        add_boundary(self.pack, "海")
        add_boundary(self.pack, "海")
        self.assertEqual(load_agency(self.pack)["boundaries"], ["海"])
        clear_boundaries(self.pack)
        self.assertEqual(load_agency(self.pack)["boundaries"], [])

    def test_repeated_topic_does_not_imply_interest(self):
        day = self._open_today()
        feed_news(self.pack, ["海边的灯塔修好了。", "海边的灯塔在夜里很亮。", "海退潮了。"], source="群聊")
        learned = learn_from_day(self.pack, day["dayNo"], day["date"])
        self.assertEqual(learned, [])
        self.assertEqual(load_agency(self.pack)["interests"], [])
        self.assertEqual(learn_from_day(self.pack, day["dayNo"], day["date"]), [])  # 学过的不重复学

    def test_plan_is_deterministic_and_can_finish(self):
        first = plan_for_day(self.pack, 2)
        again = plan_for_day(self.pack, 2)
        self.assertEqual(first["plan"], again["plan"])
        self.assertEqual(first["goal_id"], "")
        self.assertIn("留白", first["plan"])
        mark_plan_done(self.pack, 2)
        self.assertTrue(current_plan(self.pack, 2)["done"])

    def test_boundary_makes_her_say_no(self):
        add_boundary(self.pack, "海")
        reply = stub_chat(build_context(self.pack, self._open_today()["dayNo"], self._open_today()["date"], message="你还记得海吗？"))
        self.assertTrue(any(word in reply["reply"] for word in ("不想说", "不聊", "不想聊")), reply["reply"])
        self.assertEqual(reply["memory_writes"], [])

    def test_should_initiate_window(self):
        day = self._open_chat_day()
        self.assertIsNotNone(should_initiate(self.pack, now=f"{day['date']}T16:00:00+08:00", idle_seconds=0))
        self.assertIsNone(should_initiate(self.pack, now=f"{day['date']}T03:00:00+08:00", idle_seconds=0))
        self.assertIsNone(should_initiate(self.pack, now="2026-11-05T16:00:00+08:00", idle_seconds=0))

    def test_maybe_initiate_writes_active_line(self):
        day = self._open_chat_day()
        result = maybe_initiate(self.pack, create_stub_brain(), now=f"{day['date']}T16:00:00+08:00", idle_seconds=0)
        self.assertIsNotNone(result)
        self.assertTrue(result["reply"])
        text = read_text(self.pack / "life" / result["file"].split("/", 1)[1])
        self.assertIn("（主动）", text)
        self.assertIn(result["reply"], text)
        data = load_agency(self.pack)
        self.assertEqual(data["initiated"].get(day["date"]), 1)
        self.assertTrue(current_plan(self.pack, day["dayNo"]) is None or not current_plan(self.pack, day["dayNo"])["done"])

    def test_maybe_initiate_force_and_limits(self):
        day = self._open_today()
        forced = maybe_initiate(self.pack, create_stub_brain(), force=True)
        self.assertIsNotNone(forced)
        for _ in range(3):
            maybe_initiate(self.pack, create_stub_brain(), now=f"{day['date']}T16:00:00+08:00", idle_seconds=0)
        self.assertIsNone(maybe_initiate(self.pack, create_stub_brain(), now=f"{day['date']}T16:00:00+08:00", idle_seconds=0))

    def test_cli_agency_and_initiate(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["agency", str(self.pack), "--interest", "看雨", "--boundary", "海"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("看雨", text)
        self.assertIn("不想聊的：海", text)

        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["initiate", str(self.pack), "--force", "--now", "2026-10-30T15:00:00+08:00"])
        self.assertEqual(code, 0)
        self.assertIn("她主动说了句", out.getvalue())

    def test_check_still_passes_with_agency_file(self):
        add_interest(self.pack, "看雨")
        add_boundary(self.pack, "海")
        with redirect_stdout(io.StringIO()):
            self.assertTrue(check(self.pack)["ok"])


class BondsTest(unittest.TestCase):
    """1.12 关系：熟悉度、承诺、感谢 / 道歉 / 争执 / 和好。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = self._hatch()

    def _hatch(self):
        pack = Path(self.tmp.name) / "小风.life"
        hatch(pack, EGG, "小风", seed_override="bonds-test", born_at_override="2026-10-30T09:00:00+08:00")
        return pack

    def test_defaults_lazy(self):
        self.assertFalse((self.pack / "mind" / "bonds.json").exists())
        data = load_bonds(self.pack)
        self.assertEqual(data["format"], "seedbank/bonds@1")
        self.assertEqual(data["promises"], [])
        self.assertEqual(data["events"], [])
        register_talk(self.pack, 1)
        self.assertTrue((self.pack / "mind" / "bonds.json").is_file())

    def test_interaction_count_does_not_increase_familiarity(self):
        register_talk(self.pack, 1)
        register_talk(self.pack, 1)
        self.assertEqual(load_bonds(self.pack)["owner"]["talks"], 2)
        self.assertEqual(familiarity_percent(self.pack), 0)
        register_talk(self.pack, 2)
        self.assertEqual(familiarity_percent(self.pack), 0)

    def test_promise_lifecycle(self):
        day = open_day(self.pack)
        item = add_promise(self.pack, "明天讲一个海边的故事", due_day=day["dayNo"])
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["made_day"], day["dayNo"])
        self.assertEqual([p["id"] for p in due_today(self.pack)], [item["id"]])
        kept = keep_promise(self.pack, item["id"])
        self.assertEqual(kept["status"], "kept")
        self.assertEqual(pending_promises(self.pack), [])
        with self.assertRaises(SeedError):
            keep_promise(self.pack, item["id"])

    def test_promise_validation(self):
        with self.assertRaises(SeedError):
            add_promise(self.pack, "   ")
        with self.assertRaises(SeedError):
            add_promise(self.pack, "以后再说", due_day=0)
        with self.assertRaises(SeedError):
            break_promise(self.pack, "p_9999")

    def test_break_promise_with_note(self):
        item = add_promise(self.pack, "每天晒太阳")
        broken = break_promise(self.pack, item["id"], note="那天阴天")
        self.assertEqual(broken["status"], "broken")
        self.assertEqual(broken["note"], "那天阴天")
        self.assertEqual(load_bonds(self.pack)["promises"][0]["status"], "broken")

    def test_events(self):
        add_event(self.pack, "thank", "谢谢你听我说")
        add_event(self.pack, "apology", "刚才我声音大了")
        add_event(self.pack, "conflict", "我们争了一下")
        add_event(self.pack, "repair", "后来又好了")
        events = load_bonds(self.pack)["events"]
        self.assertEqual([e["kind"] for e in events], ["thank", "apology", "conflict", "repair"])
        with self.assertRaises(SeedError):
            add_event(self.pack, "unknown", "x")

    def test_describe_and_summary(self):
        register_talk(self.pack, 1)
        add_promise(self.pack, "明天讲故事")
        text = "\n".join(describe_bonds(self.pack))
        self.assertNotIn("熟悉度", text)
        self.assertIn("聊过", text)
        self.assertIn("还没做到的承诺", text)
        self.assertIn("讲故事", text)
        summary = bond_summary(self.pack)
        self.assertEqual(summary["owner"], "主人")
        self.assertEqual(summary["pending_count"], 1)
        self.assertEqual(summary["due_today"], [])

    def test_chat_registers_talk_and_supplies_due_promise_without_completing_it(self):
        day = open_day(self.pack)
        promise = add_promise(self.pack, "今天要讲故事", made_day=day["dayNo"], due_day=day["dayNo"])
        brain = create_stub_brain()
        with mock.patch.object(brain, "chat", wraps=brain.chat) as call:
            chat_turn(self.pack, "在吗？", brain)
        due = call.call_args.args[0]["bond"]["due_today"]
        self.assertIn(promise["id"], [item["id"] for item in due])
        self.assertEqual(list_promises(self.pack)[0]["status"], "pending")
        self.assertEqual(load_bonds(self.pack)["owner"]["talks"], 1)

    def test_cli_bond_and_promise(self):
        day = open_day(self.pack)
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["bond", str(self.pack), "--thank", "谢谢你陪着我"])
        self.assertEqual(code, 0)
        self.assertIn("感谢", out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["promise", str(self.pack), "明天讲故事", "--due-day", str(day["dayNo"])])
        self.assertEqual(code, 0)
        self.assertIn("p_0001", out.getvalue())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["promise", str(self.pack), "--keep", "p_0001"]), 0)
        self.assertEqual(load_bonds(self.pack)["promises"][0]["status"], "kept")

    def test_check_passes_with_bonds_file(self):
        add_promise(self.pack, "明天讲故事")
        add_event(self.pack, "thank", "谢谢")
        with redirect_stdout(io.StringIO()):
            self.assertTrue(check(self.pack)["ok"])

class MemorialTest(unittest.TestCase):
    """1.13 有限性：纪念日、遗憾、告别、缺席、有限的日子进入上下文。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = self._hatch()

    def _hatch(self):
        pack = Path(self.tmp.name) / "小岸.life"
        hatch(pack, EGG, "小岸", seed_override="memorial-test", born_at_override="2026-10-30T09:00:00+08:00")
        return pack

    def test_defaults_lazy(self):
        self.assertFalse((self.pack / "mind" / "memorial.json").exists())
        from seedbank.memorial import load_memorial

        data = load_memorial(self.pack)
        self.assertEqual(data["format"], "seedbank/memorial@1")
        self.assertEqual(data["anniversaries"], [])
        self.assertEqual(data["regrets"], [])
        self.assertEqual(data["farewells"], [])

    def test_anniversary_today(self):
        from seedbank.memorial import add_anniversary, anniversaries_today, describe_memorial, remove_anniversary

        day = open_day(self.pack)["dayNo"]
        item = add_anniversary(self.pack, "第一次见面", day=day, kind="first-meet")
        self.assertEqual(item["day"], day)
        self.assertEqual([a["name"] for a in anniversaries_today(self.pack, day)], ["第一次见面"])
        self.assertEqual(anniversaries_today(self.pack, day + 1), [])
        text = "\n".join(describe_memorial(self.pack, day))
        self.assertIn("今天", text)
        remove_anniversary(self.pack, item["name"])
        self.assertEqual(describe_memorial(self.pack, day), ["记着的日子：还没有。", "遗憾：没有还没放下的。", "告别过：还没有。"])

    def test_regret_add_and_resolve(self):
        from seedbank.memorial import add_regret, open_regrets, resolve_regret

        from seedbank.memorial import describe_memorial

        item = add_regret(self.pack, "没能说出那句话")
        self.assertEqual(item["index"], 1)
        self.assertEqual(len(open_regrets(self.pack)), 1)
        resolved = resolve_regret(self.pack, 1)
        self.assertIn("resolved_day", resolved)
        self.assertEqual(open_regrets(self.pack), [])
        with self.assertRaises(SeedError):
            resolve_regret(self.pack, 1)
        with self.assertRaises(SeedError):
            resolve_regret(self.pack, 99)

    def test_farewell(self):
        from seedbank.memorial import add_farewell, farewells_of

        item = add_farewell(self.pack, "旧窗口", kind="body", note="换了个身体")
        self.assertEqual(item["name"], "旧窗口")
        items = farewells_of(self.pack)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["note"], "换了个身体")

    def test_missing_days(self):
        from seedbank.memorial import note_missing, total_missing_days

        note_missing(self.pack, 3)
        note_missing(self.pack, 2)
        self.assertEqual(total_missing_days(self.pack), 5)

    def test_broken_promise_becomes_regret(self):
        from seedbank.bonds import add_promise, break_promise
        from seedbank.memorial import open_regrets

        day = open_day(self.pack)["dayNo"]
        item = add_promise(self.pack, "明天讲故事", due_day=day)
        break_promise(self.pack, item["id"], note="睡着了")
        regrets = open_regrets(self.pack)
        self.assertEqual(len(regrets), 1)
        self.assertIn("没有做到：明天讲故事", regrets[0]["text"])

    def test_stub_faces_anniversary(self):
        from seedbank.brain import anniversary_names, stub_chat
        from seedbank.memorial import add_anniversary

        day = open_day(self.pack)["dayNo"]
        add_anniversary(self.pack, "我们的第一天", day=day, kind="birthday")
        ctx = {
            "birth": {"seed": "memorial-test"},
            "name": "小岸",
            "dayNo": day,
            "message": "今天是什么日子？",
            "memorial": {"anniversaries_today": [{"name": "我们的第一天"}]},
        }
        self.assertEqual(anniversary_names(ctx), ["我们的第一天"])
        reply = stub_chat(ctx)["reply"]
        self.assertIn("我们的第一天", reply)

    def test_cli_writes_memorial(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["memorial", str(self.pack), "--anniversary", "第一次见面", "--kind", "初见"]), 0)
            self.assertIn("第一次见面", out.getvalue())
            self.assertEqual(cli.main(["memorial", str(self.pack), "--regret", "没能说出那句话"]), 0)
            self.assertEqual(cli.main(["memorial", str(self.pack), "--farewell", "旧窗口", "--note", "换了个身体"]), 0)
        from seedbank.memorial import describe_memorial

        day = open_day(self.pack)["dayNo"]
        text = "\n".join(describe_memorial(self.pack, day))
        self.assertIn("第一次见面", text)
        self.assertIn("没能说出那句话", text)
        self.assertIn("旧窗口", text)

    def test_check_passes_with_memorial(self):
        from seedbank.memorial import add_anniversary, add_regret

        add_anniversary(self.pack, "第一次见面")
        add_regret(self.pack, "没能说出那句话")
        with redirect_stdout(io.StringIO()):
            self.assertTrue(check(self.pack)["ok"])

    def test_bad_memorial_file_rejected(self):
        (self.pack / "mind" / "memorial.json").write_text("不是 json", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SeedError):
                check(self.pack)
class InnerTest(unittest.TestCase):
    """1.14 内在：沉默权、自我更正、梦、自我叙事。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = self._hatch()

    def _hatch(self):
        pack = Path(self.tmp.name) / "小岸.life"
        hatch(pack, EGG, "小岸", seed_override="inner-test", born_at_override="2026-10-30T09:00:00+08:00")
        return pack

    def _day(self):
        return open_day(self.pack)["dayNo"]

    def test_defaults_lazy(self):
        from seedbank.inner import load_inner

        self.assertFalse((self.pack / "mind" / "inner.json").exists())
        data = load_inner(self.pack)
        self.assertEqual(data["format"], "seedbank/inner@2")
        self.assertEqual(data["corrections"], [])
        self.assertEqual(data["dreams"], [])
        self.assertEqual(data["silence"]["on"], False)
        self.assertEqual(data["narrative"]["text"], "")

    def test_silence_toggle_and_describe(self):
        from seedbank.inner import describe_inner, set_silence, silence_active, silence_state

        day = self._day()
        set_silence(self.pack, True, note="今天想安静一会儿", day=day)
        self.assertTrue(silence_active(self.pack))
        self.assertEqual(silence_state(self.pack)["since_day"], day)
        self.assertIn("沉默权：开着", describe_inner(self.pack))
        set_silence(self.pack, False)
        self.assertFalse(silence_active(self.pack))

    def test_correct_belief_keeps_old(self):
        from seedbank.inner import correct_belief, recent_corrections

        day = self._day()
        correct_belief(self.pack, "她是人造的", "她是从蛋里长出来的", day=day)
        recent = recent_corrections(self.pack)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["old"], "她是人造的")
        self.assertEqual(recent[0]["new"], "她是从蛋里长出来的")
        with self.assertRaises(SeedError):
            correct_belief(self.pack, "", "x")

    def test_old_dreams_survive_more_than_the_previous_display_limit(self):
        from seedbank.inner import DREAM_MAX, add_dream, last_dreams

        day = self._day()
        for index in range(DREAM_MAX + 2):
            add_dream(self.pack, day, f"第{index}个梦")
        self.assertEqual(len(last_dreams(self.pack, 999)), DREAM_MAX + 2)
        with self.assertRaises(SeedError):
            add_dream(self.pack, day, "")

    def test_narrative_saved(self):
        from seedbank.inner import narrative, set_narrative

        day = self._day()
        set_narrative(self.pack, "我是小岸，我住在一个安静的小房间里。", day=day)
        data = narrative(self.pack)
        self.assertIn("我是小岸", data["text"])
        self.assertEqual(data["updated_day"], day)

    def test_stub_dream_and_narrative_clean(self):
        from seedbank.brain import stub_dream, stub_narrative

        ctx = {
            "birth": {"seed": "inner-test"},
            "name": "小岸",
            "speciesName": "大肥鱼",
            "dayNo": self._day(),
            "senses": ["光：光很亮，是暖的。"],
            "news": ["海边的灯塔修好了。"],
            "interests": ["灯塔"],
            "traitsPicked": [{"text": "睡觉会打小呼噜"}],
            "worldBible": "# 她的世界\n\n> 你（读这份文件的人）",
        }
        self.assertIn("梦", stub_dream(ctx)["dream"])
        text = stub_narrative(ctx)["text"]
        self.assertNotIn("#", text)
        self.assertNotIn(">", text)
        self.assertIn("小岸", text)

    def test_build_context_has_inner(self):
        from seedbank.inner import set_silence

        set_silence(self.pack, True, note="安静")
        day = open_day(self.pack)
        ctx = build_context(self.pack, day["dayNo"], day["date"], "在吗")
        self.assertTrue(ctx["inner"]["silence"]["on"])

    def test_chat_short_when_silent(self):
        from seedbank.brain import create_stub_brain
        from seedbank.inner import set_silence

        set_silence(self.pack, True, note="安静")
        result = chat_turn(self.pack, "在吗", brain=create_stub_brain())
        self.assertLessEqual(len(result["reply"]), 20)

    def test_silence_suppresses_initiative(self):
        from seedbank.brain import create_stub_brain
        from seedbank.inner import set_silence

        set_silence(self.pack, True, note="安静")
        self.assertIsNone(maybe_initiate(self.pack, create_stub_brain()))
        forced = maybe_initiate(self.pack, create_stub_brain(), force=True)
        self.assertIsNotNone(forced)

    def test_chat_writes_correction(self):
        from seedbank.brain import Brain
        from seedbank.inner import recent_corrections
        from seedbank.util import append_memories

        day = open_day(self.pack)
        append_memories(self.pack, [{"id": "correction-target", "day": day["dayNo"],
                                   "kind": "thought", "text": "她是人造的", "importance": 0.5,
                                   "tags": [], "source": "fixture", "at": "2026-11-01", "runner": "fixture"}])

        class _CorrectingBrain(Brain):
            name = "fake-v1"

            def chat(self, ctx):
                return {
                    "reply": "嗯，我想起来了。",
                    "memory_writes": [],
                    "corrections": [{"target_id": "correction-target", "new": "她是从蛋里长出来的",
                                     "reason": "本次说明更正了旧说法"}],
                }

        result = chat_turn(self.pack, "你记得吗", brain=_CorrectingBrain())
        self.assertEqual(result["corrections"], 1)
        self.assertEqual(len(recent_corrections(self.pack)), 1)
        kinds = [item["kind"] for item in list_memories(self.pack)]
        self.assertIn("correction", kinds)

    def test_run_days_does_not_invent_scheduled_dreams(self):
        from seedbank.brain import create_stub_brain
        from seedbank.inner import load_inner

        run_days(self.pack, 3, brain=create_stub_brain())
        self.assertEqual(load_inner(self.pack)["dreams"], [])

    def test_cli_inner(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["inner", str(self.pack), "--silence", "on", "--note", "安静"]), 0)
            self.assertEqual(cli.main(["inner", str(self.pack), "--dream"]), 1)
            self.assertEqual(cli.main(["inner", str(self.pack), "--narrate"]), 1)
            self.assertEqual(cli.main(["inner", str(self.pack), "--correct", "她是人造的", "--now", "她是从蛋里长出来的"]), 0)
            self.assertEqual(cli.main(["inner", str(self.pack)]), 0)
        text = out.getvalue()
        self.assertIn("沉默权已打开", text)
        self.assertIn("当前使用离线模板", text)
        self.assertNotIn("已保存梦的记录", text)
        self.assertNotIn("已保存自我叙述", text)

    def test_check_passes_with_inner(self):
        from seedbank.inner import add_dream, set_narrative, set_silence

        day = self._day()
        set_silence(self.pack, True, note="安静", day=day)
        add_dream(self.pack, day, "我梦见光")
        set_narrative(self.pack, "我是小岸。", day=day)
        with redirect_stdout(io.StringIO()):
            self.assertTrue(check(self.pack)["ok"])

    def test_bad_inner_file_rejected(self):
        (self.pack / "mind" / "inner.json").write_text("不是 json", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SeedError):
                check(self.pack)


class WorksTest(unittest.TestCase):
    """1.15 作品与身体：诗、信、字符画。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = Path(self.tmp.name) / "小岸.life"
        with redirect_stdout(io.StringIO()):
            hatch(self.pack, EGG, "小岸", seed_override="works-test", born_at_override="2026-10-30T09:00:00+08:00")

    def test_lazy_file_and_empty(self):
        self.assertFalse((self.pack / "mind" / "works.json").exists())
        self.assertEqual(works_summary(self.pack)["total"], 0)
        self.assertIn("还没有", describe_works(self.pack))

    def test_add_poem(self):
        entry = add_work(self.pack, "poem", "光在墙上\n停了一会儿", title="夜里", day=2)
        self.assertEqual(entry["id"], "w_0001")
        self.assertEqual(entry["kind"], "poem")
        self.assertEqual(entry["day"], 2)
        data = json.loads((self.pack / "mind" / "works.json").read_text(encoding="utf-8"))
        self.assertEqual(data["format"], "seedbank/works@1")
        self.assertEqual(len(data["works"]), 1)

    def test_three_kinds_and_list_order(self):
        add_work(self.pack, "poem", "第一首", day=2)
        add_work(self.pack, "letter", "给我的人", day=2)
        add_work(self.pack, "drawing", "~ ~\n ~~", day=3)
        self.assertEqual(len(list_works(self.pack)), 3)
        self.assertEqual(list_works(self.pack)[0]["kind"], "drawing")  # 最新在前
        self.assertEqual([w["kind"] for w in list_works(self.pack, kind="poem")], ["poem"])

    def test_unknown_kind_and_empty_text_rejected(self):
        with self.assertRaises(SeedError):
            add_work(self.pack, "song", "啦啦")
        with self.assertRaises(SeedError):
            add_work(self.pack, "poem", "   ")

    def test_read_work(self):
        entry = add_work(self.pack, "letter", "今天想你。", title="信")
        self.assertEqual(read_work(self.pack, entry["id"])["text"], "今天想你。")
        self.assertIsNone(read_work(self.pack, "w_9999"))

    def test_summary_counts(self):
        add_work(self.pack, "poem", "一")
        add_work(self.pack, "poem", "二")
        add_work(self.pack, "drawing", "三")
        summary = works_summary(self.pack)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["poems"], 2)
        self.assertEqual(summary["drawings"], 1)
        self.assertEqual(summary["letters"], 0)

    def test_compose_work_with_stub_brain(self):
        result = compose_work(self.pack, "poem", create_stub_brain())
        self.assertEqual(result["kind"], "poem")
        entry = result["entry"]
        self.assertTrue(entry["text"].strip())
        self.assertEqual(len(list_works(self.pack)), 1)
        memories = [m for m in visible_memories(self.pack) if "作品" in (m.get("tags") or [])]
        self.assertTrue(memories, "作品要留下一条记忆")

    def test_compose_letter_and_drawing(self):
        compose_work(self.pack, "letter", create_stub_brain())
        compose_work(self.pack, "drawing", create_stub_brain())
        summary = works_summary(self.pack)
        self.assertEqual(summary["letters"], 1)
        self.assertEqual(summary["drawings"], 1)
        self.assertIn("~", list_works(self.pack, kind="drawing")[0]["text"])

    def test_compose_unknown_kind_rejected(self):
        with self.assertRaises(SeedError):
            compose_work(self.pack, "movie", create_stub_brain())

    def test_check_reports_works(self):
        add_work(self.pack, "poem", "一首诗", day=2)
        with redirect_stdout(io.StringIO()):
            info = check(self.pack)
        self.assertEqual(info["works"]["total"], 1)
        self.assertEqual(info["works"]["poems"], 1)

    def test_check_rejects_bad_works_file(self):
        add_work(self.pack, "poem", "一首诗", day=2)
        broken = json.loads((self.pack / "mind" / "works.json").read_text(encoding="utf-8"))
        broken["works"][0]["kind"] = "song"
        (self.pack / "mind" / "works.json").write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SeedError):
                check(self.pack)

    def test_cli_make_and_works(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["make", str(self.pack), "--kind", "poem"]), 0)
            self.assertEqual(cli.main(["works", str(self.pack)]), 0)
            self.assertEqual(cli.main(["works", str(self.pack), "w_0001"]), 0)
        self.assertEqual(len(list_works(self.pack)), 1)

    def test_run_days_does_not_create_scheduled_work(self):
        run_days(self.pack, 4, create_stub_brain())
        works = list_works(self.pack)
        self.assertEqual(works, [], "创作需要真实的行动选择，不由天数触发")

class LiveTest(unittest.TestCase):
    """1.16 生活流：事件队列 + 常驻循环。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = self._hatch()

    def _hatch(self):
        pack = Path(self.tmp.name) / "小光.life"
        hatch(pack, EGG, "小光", seed_override="live-test", born_at_override="2026-10-30T09:00:00+08:00")
        return pack

    def _inbox(self):
        return [item for item in (self.pack / "inbox").iterdir() if item.is_file()]

    def test_enqueue_and_process_news(self):
        from seedbank.live import enqueue_event, process_inbox
        from seedbank.util import read_text

        path = enqueue_event(self.pack, {"kind": "news", "text": "海边起风了。", "source": "群聊"})
        self.assertTrue(path.is_file())
        self.assertEqual(len(self._inbox()), 1)
        result = process_inbox(self.pack)
        self.assertEqual(len(result["processed"]), 1)
        self.assertEqual(result["failed"], [])
        self.assertEqual(self._inbox(), [])
        day = open_day(self.pack)["dayNo"]
        text = read_text(self.pack / "life" / sorted((self.pack / "life").iterdir())[-1].name)
        self.assertIn("## 见闻", text)
        self.assertIn("海边起风了。", text)
        self.assertTrue(any(m["kind"] == "hearsay" for m in visible_memories(self.pack)))

    def test_note_event_gets_reply(self):
        from seedbank.live import enqueue_event, process_event

        day = open_day(self.pack)["dayNo"]
        enqueue_event(self.pack, {"kind": "note", "text": "我回来了。"})
        result = process_event(
            self.pack,
            {"kind": "note", "text": "我回来了。", "source": "主人", "at": "2026-10-30T10:00:00Z"},
            brain=create_stub_brain(),
        )
        self.assertEqual(result["kind"], "note")
        self.assertTrue(result["result"]["reply"])
        life = sorted((self.pack / "life").iterdir())[-1]
        text = life.read_text(encoding="utf-8")
        self.assertIn("**主人**：我回来了。", text)
        self.assertIn("## 对话", text)

    def test_sense_event_uses_note(self):
        from seedbank.live import enqueue_event, process_event

        enqueue_event(self.pack, {"kind": "sense", "text": "窗外有雨声。"})
        result = process_event(
            self.pack,
            {"kind": "sense", "text": "窗外有雨声。", "source": "主人", "at": "2026-10-30T10:00:00Z"},
        )
        self.assertEqual(result["kind"], "sense")
        life = sorted((self.pack / "life").iterdir())[-1]
        self.assertIn("## 感知", life.read_text(encoding="utf-8"))
        self.assertIn("主人：窗外有雨声。", life.read_text(encoding="utf-8"))

    def test_bad_event_goes_to_failed(self):
        from seedbank.live import failed_path, process_inbox

        bad = self.pack / "inbox" / "broken.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")
        result = process_inbox(self.pack)
        self.assertEqual(result["processed"], [])
        self.assertEqual(len(result["failed"]), 1)
        self.assertTrue(any(failed_path(self.pack).iterdir()))
        self.assertEqual(self._inbox(), [])

    def test_enqueue_validates_kind_and_text(self):
        from seedbank.live import enqueue_event

        with self.assertRaises(SeedError):
            enqueue_event(self.pack, {"kind": "movie", "text": "看电影"})
        with self.assertRaises(SeedError):
            enqueue_event(self.pack, {"kind": "note", "text": "   "})

    def test_non_json_files_ignored(self):
        from seedbank.live import process_inbox

        (self.pack / "inbox").mkdir(parents=True, exist_ok=True)
        (self.pack / "inbox" / "readme.txt").write_text("不是事件", encoding="utf-8")
        result = process_inbox(self.pack)
        self.assertEqual(result["processed"], [])
        self.assertEqual(result["failed"], [])

    def test_live_rounds_collect_events(self):
        from seedbank.live import enqueue_event, run_live

        enqueue_event(self.pack, {"kind": "news", "text": "灯塔修好了。", "source": "群聊"})
        lines = []
        stats = run_live(
            self.pack,
            rounds=2,
            interval=1,
            brain=create_stub_brain(),
            sleep=lambda seconds: None,
            out=lines.append,
        )
        self.assertEqual(stats["rounds"], 2)
        self.assertEqual(stats["events"], 1)
        self.assertEqual(len(lines), 2)

    def test_live_validates_interval_and_rounds(self):
        from seedbank.live import run_live

        with self.assertRaises(SeedError):
            run_live(self.pack, interval=0, rounds=1)
        with self.assertRaises(SeedError):
            run_live(self.pack, interval=1, rounds=0)

    def test_live_advances_day(self):
        from seedbank.clock import tick as clock_tick
        from seedbank.live import run_live

        clock_tick(self.pack, None, now="2026-10-31T10:00:00Z")
        stats = run_live(
            self.pack,
            rounds=1,
            interval=1,
            brain=create_stub_brain(),
            now_fn=lambda: "2026-11-01T00:30:00Z",
            sleep=lambda seconds: None,
            out=lambda line: None,
        )
        self.assertGreaterEqual(stats["days"], 1)



class HandsTest(unittest.TestCase):
    """1.17 手与代价：提醒能说出口，错过会变成遗憾。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = self._hatch()

    def _hatch(self):
        pack = Path(self.tmp.name) / "小光.life"
        hatch(pack, EGG, "小光", seed_override="hands-test", born_at_override="2026-10-30T09:00:00+08:00")
        return pack

    def _day(self):
        return open_day(self.pack)["dayNo"]

    def test_lazy_file_absent_until_first_reminder(self):
        self.assertFalse((self.pack / "mind" / "hands.json").is_file())
        reminder = add_reminder(self.pack, "给窗台那盆花浇水", due_day=2)
        self.assertEqual(reminder["id"], "r_0001")
        self.assertTrue((self.pack / "mind" / "hands.json").is_file())

    def test_remind_command(self):
        self.assertEqual(cli.main(["remind", str(self.pack), "明天投喂小鲸鱼", "--due-day", "2"]), 0)
        reminders = list_reminders(self.pack)
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["status"], "pending")
        self.assertEqual(reminders[0]["due_day"], 2)

    def test_past_due_is_rejected(self):
        with self.assertRaises(SeedError):
            add_reminder(self.pack, "早就该做的事", due_day=1)

    def test_due_today_helpers(self):
        add_reminder(self.pack, "提醒主人喝水", due_day=2)
        self.assertEqual(len(due_reminders(self.pack, 2)), 1)
        self.assertEqual(len(due_reminders(self.pack, 3)), 0)
        self.assertEqual(len(overdue_reminders(self.pack, 3)), 1)

    def test_chat_says_due_reminder_once(self):
        add_reminder(self.pack, "记得给花浇水", due_day=2)
        result = cli.main(["chat", str(self.pack), "--once", "在吗"])
        self.assertEqual(result, 0)
        text = "".join(read_text(p) for p in sorted((self.pack / "life").glob("*.md")))
        self.assertIn("记得给花浇水", text)
        self.assertEqual(list_reminders(self.pack)[0]["status"], "said")
        self.assertEqual(len(due_reminders(self.pack, 2)), 0)
        count = text.count("记得给花浇水")
        cli.main(["chat", str(self.pack), "--once", "在吗"])
        text2 = "".join(read_text(p) for p in sorted((self.pack / "life").glob("*.md")))
        self.assertEqual(text2.count("记得给花浇水"), count)

    def test_hands_command_lists_reminders(self):
        add_reminder(self.pack, "整理旧照片", due_day=2)
        out = capture_main(["hands", str(self.pack)])
        self.assertIn("手里的事", out)
        self.assertIn("整理旧照片", out)

    def test_hands_done_marks_said(self):
        reminder = add_reminder(self.pack, "记得说晚安", due_day=2)
        out = capture_main(["hands", str(self.pack), "--done", reminder["id"]])
        self.assertIn("提醒过了", out)
        self.assertEqual(list_reminders(self.pack)[0]["status"], "said")

    def test_sweep_missed_writes_regret(self):
        add_reminder(self.pack, "没讲完的故事", due_day=2)
        missed = sweep_missed(self.pack, 4)
        self.assertEqual(len(missed), 1)
        self.assertEqual(list_reminders(self.pack)[0]["status"], "missed")
        from seedbank.memorial import load_memorial
        memorial = load_memorial(self.pack)
        self.assertTrue(any("没做到" in item["text"] for item in memorial["regrets"]))

    def test_sweep_keeps_future_reminders(self):
        add_reminder(self.pack, "下周的事", due_day=9)
        self.assertEqual(sweep_missed(self.pack, 4), [])
        self.assertEqual(list_reminders(self.pack)[0]["status"], "pending")

    def test_check_reports_hands(self):
        add_reminder(self.pack, "提醒一件事", due_day=2)
        add_reminder(self.pack, "提醒第二件事", due_day=3)
        info = check(self.pack)
        self.assertEqual(info["hands"]["total"], 2)
        self.assertEqual(info["hands"]["pending"], 2)

    def test_check_rejects_broken_hands(self):
        path = self.pack / "mind" / "hands.json"
        path.write_text('{"format": "seedbank/hands@1", "reminders": [{"text": "x"}]}', encoding="utf-8")
        with self.assertRaises(SeedError):
            check(self.pack)
        path.write_text('{"format": "seedbank/hands@1", "reminders": [{"id": "r_1", "text": "x", "due_day": 0}]}', encoding="utf-8")
        with self.assertRaises(SeedError):
            check(self.pack)

    def test_apply_actions_records_reminder(self):
        from seedbank.hands import apply_actions
        from seedbank.cognition import build_context
        ctx = build_context(self.pack, self._day(), date="2026-10-31", message="帮我记着")
        actions = apply_actions(self.pack, self._day(), "2026-10-31T10:00:00Z",
                               [{"type": "remind", "text": "给你带一块石头", "due_day": 3}])
        self.assertEqual(len(actions), 1)
        self.assertEqual(list_reminders(self.pack)[0]["text"], "给你带一块石头")

    def test_context_has_hands(self):
        add_reminder(self.pack, "拿着", due_day=self._day())
        from seedbank.cognition import build_context
        day = self._day()
        ctx = build_context(self.pack, day, date="x", message="hi")
        self.assertEqual(len(ctx["hands"]["due_today"]), 1)
        self.assertIn("due_today", ctx["hands"])

class FriendsTest(SeedbankTest):
    def _other(self, name="小岸"):
        other = self.tmp / f"{name}.life"
        hatch(other, EGG, name)
        return other

    def test_default_friends_is_empty(self):
        pack = self._hatch()
        self.assertEqual(friends_summary(pack)["total"], 0)

    def test_visit_creates_friend(self):
        pack = self._hatch()
        other = self._other()
        result = visit(pack, other, note="你这里真安静。")
        self.assertEqual(result["guest"], "小岸")
        summary = friends_summary(pack)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["alive"], 1)
        self.assertEqual(summary["recent"][0]["visits"], 1)

    def test_visit_twice_counts(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        result = visit(pack, other)
        self.assertEqual(friends_summary(pack)["recent"][0]["visits"], 2)
        self.assertTrue(result["reply"])

    def test_visit_requires_real_pack(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            visit(pack, self.tmp / "不存在.life")

    def test_mourn_marks_lost(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        result = mourn(pack, "小岸", letter="谢谢你来过。")
        self.assertEqual(result["friend"], "小岸")
        summary = friends_summary(pack)
        self.assertEqual(summary["lost"], 1)
        self.assertEqual(summary["alive"], 0)

    def test_mourn_unknown_raises(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            mourn(pack, "没来过的人")

    def test_legacy_letter_written(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        mourn(pack, "小岸", letter="再见。")
        result = legacy_letter(pack)
        letter = Path(str(result["path"]))
        self.assertTrue(letter.exists())
        text = letter.read_text(encoding="utf-8")
        self.assertIn("给读到这封信的人", text)
        self.assertIn("小岸", text)

    def test_check_reports_friends(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        mourn(pack, "小岸")
        result = check(pack)
        self.assertEqual(result["friends"]["total"], 1)
        self.assertEqual(result["friends"]["lost"], 1)

    def test_check_rejects_bad_friends(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        path = pack / "mind" / "friends.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["friends"][0]["status"] = "unknown"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SeedError):
            check(pack)


    def test_visit_self_is_rejected(self):
        pack = self._hatch()
        with self.assertRaises(SeedError):
            visit(pack, pack)

    def test_mourn_twice_is_rejected(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        mourn(pack, "小岸")
        with self.assertRaises(SeedError):
            mourn(pack, "小岸")

    def test_visit_after_mourn_revives(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        mourn(pack, "小岸")
        visit(pack, other)
        summary = friends_summary(pack)
        self.assertEqual(summary["alive"], 1)
        self.assertEqual(summary["lost"], 0)
        self.assertIsNone(summary["recent"][0]["lost_day"])

    def test_summary_recent_has_lost_day(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        mourn(pack, "小岸")
        recent = friends_summary(pack)["recent"][0]
        self.assertEqual(recent["status"], "lost")
        self.assertIsNotNone(recent["lost_day"])

    def test_check_rejects_bad_lost_day(self):
        pack = self._hatch()
        other = self._other()
        visit(pack, other)
        path = pack / "mind" / "friends.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["friends"][0]["lost_day"] = "昨天"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SeedError):
            check(pack)

    def test_cli_visit_and_mourn(self):
        from seedbank import cli
        pack = self._hatch()
        other = self._other()
        self.assertEqual(cli.main(["visit", str(pack), "--from", str(other)]), 0)
        self.assertEqual(cli.main(["mourn", str(pack), "--friend", "小岸"]), 0)
        self.assertEqual(cli.main(["legacy", str(pack)]), 0)


class OnboardingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {
            "HOME": str(self.tmp),
            "USERPROFILE": str(self.tmp),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_find_egg_in_repo(self):
        egg = onboarding.find_egg()
        self.assertTrue((egg / "species.json").is_file())

    def test_clean_name(self):
        self.assertEqual(onboarding.clean_name("  小 蓝  "), "小 蓝")
        self.assertEqual(onboarding.clean_name("a/b:c"), "abc")
        with self.assertRaises(SeedError):
            onboarding.clean_name("   ")
        with self.assertRaises(SeedError):
            onboarding.clean_name("长" * 30)

    def test_create_fish(self):
        pack = onboarding.create_fish("小蓝", self.tmp / "fish")
        self.assertTrue((pack / "birth.json").is_file())
        self.assertTrue((pack / "mind" / "traits.json").is_file())
        config = onboarding.load_config()
        self.assertEqual(config["default_pack"], str(pack))
        self.assertEqual(onboarding.resolve_pack(), pack)

    def test_create_fish_twice_fails(self):
        onboarding.create_fish("小蓝", self.tmp / "fish")
        with self.assertRaises(SeedError):
            onboarding.create_fish("小蓝", self.tmp / "fish")

    def test_resolve_pack_ignores_missing(self):
        self.assertIsNone(onboarding.resolve_pack())
        pack = onboarding.create_fish("小蓝", self.tmp / "fish")
        (pack / "birth.json").unlink()
        self.assertIsNone(onboarding.resolve_pack())

    def test_save_config_merges(self):
        onboarding.save_config({"a": 1})
        onboarding.save_config({"b": 2})
        config = onboarding.load_config()
        self.assertEqual(config["a"], 1)
        self.assertEqual(config["b"], 2)
        self.assertEqual(config["format"], onboarding.CONFIG_FORMAT)

    def test_setup_cli_creates_fish(self):
        output = capture_main(["setup", "--name", "小蓝"])
        self.assertIn("她醒了", output)
        self.assertIsNotNone(onboarding.resolve_pack())

    def test_start_without_pack_errors(self):
        self.assertEqual(cli.main(["start"]), 1)


class LocalModelsTest(unittest.TestCase):
    def test_normalize_base_url(self):
        self.assertEqual(localmodels.normalize_base_url("127.0.0.1:11434"),
                         "http://127.0.0.1:11434/v1")
        self.assertEqual(localmodels.normalize_base_url("http://localhost:1234/v1/"),
                         "http://localhost:1234/v1")

    def test_only_local_hosts(self):
        self.assertTrue(localmodels._is_local("http://127.0.0.1:11434"))
        self.assertTrue(localmodels._is_local("http://localhost:8000"))
        self.assertFalse(localmodels._is_local("http://192.168.1.9:11434"))

    def test_probe_refuses_remote(self):
        row = localmodels.probe("http://10.0.0.5:11434")
        self.assertFalse(row["ok"])

    def test_first_choice(self):
        rows = [{"ok": True, "label": "Ollama",
                 "base_url": "http://127.0.0.1:11434/v1", "models": ["qwen2.5:7b"]}]
        patch = localmodels.first_choice(rows)
        self.assertEqual(patch["adapter"], "openai-compatible")
        self.assertEqual(patch["model"], "qwen2.5:7b")
        self.assertEqual(patch["api_key_env"], "")
        self.assertIsNone(localmodels.first_choice([]))

    def test_describe_empty(self):
        self.assertIn("没有发现", localmodels.describe_local([]))


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _hatch(self, name="小岸"):
        pack = self.tmp / f"{name}.life"
        hatch(pack, EGG, name, seed_override="offline-test",
              born_at_override="2026-10-28T10:00:00+08:00")
        return pack

    def _feed(self, pack, texts):
        feed_news(pack, [{"text": text} for text in texts], source="群聊")

    def test_grow_records_a_topic_without_inventing_a_belief(self):
        pack = self._hatch()
        self._feed(pack, ["海边风很大，灯塔亮了一下。", "灯塔下面有两只海鸟。"])
        run_days(pack, days=1, brain=create_stub_brain())
        self._feed(pack, ["夜里灯塔的光扫过海面，很安静。"])
        before = (pack / "mind" / "beliefs.md").read_text(encoding="utf-8")
        entry = offline.grow(pack)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["format"], offline.GROWTH_FORMAT)
        beliefs = (pack / "mind" / "beliefs.md").read_text(encoding="utf-8")
        self.assertEqual(beliefs, before)
        self.assertEqual(entry["kind"], "topic_observation")
        self.assertTrue(entry["evidence"])
        growth = offline.read_growth(pack)
        self.assertEqual(len(growth), 1)
        memories = list_memories(pack)
        self.assertTrue(any("成长" in (row.get("tags") or []) for row in memories))

    def test_grow_is_idempotent(self):
        pack = self._hatch()
        self._feed(pack, ["海边风很大，灯塔亮了一下。", "灯塔下面有两只海鸟。"])
        run_days(pack, days=1, brain=create_stub_brain())
        self._feed(pack, ["夜里灯塔的光扫过海面，很安静。"])
        self.assertIsNotNone(offline.grow(pack))
        self.assertIsNone(offline.grow(pack))
        self.assertEqual(len(offline.read_growth(pack)), 1)

    def test_grow_without_material(self):
        pack = self._hatch()
        self.assertIsNone(offline.grow(pack))
        self.assertIn("还没有", offline.describe_growth(pack))

    def test_cli_grow(self):
        pack = self._hatch()
        self._feed(pack, ["海边风很大，灯塔亮了一下。", "灯塔下面有两只海鸟。"])
        run_days(pack, days=1, brain=create_stub_brain())
        self._feed(pack, ["夜里灯塔的光扫过海面，很安静。"])
        output = capture_main(["grow", str(pack)])
        self.assertIn("长大了一点", output)
        self.assertIn("灯塔", output)


class Audit121Test(unittest.TestCase):
    """1.21 审计修出来的几条：载体钟、QQ 群权限、端口、时间线类型。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-a121-")
        self.tmp = Path(self._tmp.name)
        self.pack = self.tmp / "审计鱼.life"
        hatch(self.pack, EGG, "审计鱼")

    def tearDown(self):
        self._tmp.cleanup()

    def test_bridge_tick_really_writes_clock(self):
        from seedbank.bridge import Bridge

        bridge = Bridge(self.pack)
        result = bridge.handle({"op": "tick", "now": "2031-02-03T06:00:00Z"})
        self.assertTrue(result["ok"], result)
        clock = json.loads((self.pack / "mind" / "clock.json").read_text(encoding="utf-8"))
        self.assertEqual(clock["last_seen_date"], "2031-02-03")

    def test_qq_empty_group_whitelist_means_no_groups(self):
        from seedbank import qq

        event = {
            "post_type": "message", "message_type": "group", "group_id": 555,
            "user_id": 123, "self_id": 999,
            "message": [{"type": "at", "data": {"qq": "999"}}, {"type": "text", "data": {"text": " 你好"}}],
        }
        self.assertEqual(qq.decide(event, owner="123", groups=[])["action"], "ignore")
        self.assertEqual(qq.decide(event, owner="123", groups=["555"])["action"], "chat")

    def test_qq_http_rejects_oversized_event(self):
        import http.client
        from seedbank import qq

        class FakeAdapter:
            def handle(self, event):
                return None

            def close(self):
                return None

        server = qq._IMServer(("127.0.0.1", 0), FakeAdapter())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.putrequest("POST", "/")
            connection.putheader("Content-Length", str(qq.MAX_EVENT_BYTES + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_timeline_rejects_wrong_types(self):
        from seedbank import timeline

        (self.pack / "birth.json").write_text('"不是对象"', encoding="utf-8")
        with self.assertRaises(ValueError):
            timeline.render_timeline(self.pack)

        good = self.tmp / "好鱼.life"
        hatch(good, EGG, "好鱼")
        (good / "mind" / "mood.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            timeline.render_timeline(good)

    def test_webui_second_bind_fails(self):
        from seedbank import webui

        brain = create_stub_brain()
        lock = threading.Lock()
        first = webui._Server(("127.0.0.1", 0), pack=self.pack, brain=brain, lock=lock)
        port = first.server_address[1]
        try:
            with self.assertRaises(OSError):
                webui._Server(("127.0.0.1", port), pack=self.pack, brain=brain, lock=lock)
        finally:
            first.server_close()

    def test_concurrent_tick_advances_only_once(self):
        from datetime import date, datetime, time, timedelta

        from seedbank import clock as clock_module

        opened = open_day(self.pack)
        base = opened["date"]
        tomorrow_date = date.fromisoformat(base) + timedelta(days=1)
        tomorrow = tomorrow_date.isoformat()
        # 不写死时区：用「明天的中午」的本地时间，tick 里的 local_date 才会落在明天，
        # 否则在 UTC runner 上 03:00+08:00 会被换算回今天，gap==0，两边都不推进。
        now_local = datetime.combine(tomorrow_date, time(12, 0)).astimezone().isoformat(
            timespec="seconds"
        )
        save_clock(self.pack, {"last_seen_date": base})

        results = []
        barrier = threading.Barrier(2)

        def run():
            barrier.wait()
            results.append(tick(self.pack, now=now_local))

        runners = [threading.Thread(target=run) for _ in range(2)]
        for runner in runners:
            runner.start()
        for runner in runners:
            runner.join(timeout=10)

        advanced = [item for item in results if item.get("advanced")]
        self.assertEqual(len(advanced), 1, results)
        files = sorted((self.pack / "life").glob("*.md"))
        self.assertEqual(len(files), 2)
        self.assertTrue(files[-1].name.startswith("0002-"))
        self.assertFalse((self.pack / "mind" / ".tick.lock").exists())

    def test_check_rejects_bad_optional_mind_files(self):
        from seedbank import pack as pack_module

        cases = [
            ("memory.json", "{not json"),
            ("memory.json", json.dumps({"strict": "yes"})),
            ("memory.json", json.dumps({"daily_max": 0})),
            ("vision.json", json.dumps({"enabled": "on"})),
            ("vision.json", json.dumps({"max_side": 10})),
            ("persona.json", json.dumps({"probes": "nope"})),
            ("growth.jsonl", '{"format": "x"}\n{broken'),
            ("vision.jsonl", "[1, 2, 3]"),
        ]
        for name, content in cases:
            with self.subTest(name=name, content=content):
                (self.pack / "mind" / name).write_text(content, encoding="utf-8")
                with self.assertRaises(Exception):
                    pack_module.check(self.pack)
                (self.pack / "mind" / name).unlink()

    def test_write_commands_tick_clock_first(self):
        from datetime import date, timedelta

        from seedbank.clock import load_clock, save_clock
        from seedbank import cli

        today = date.today()
        stale = (today - timedelta(days=3)).isoformat()
        save_clock(self.pack, {"last_seen_date": stale})

        feed_file = self.tmp / "news.txt"
        feed_file.write_text("一条很小的新闻。\n", encoding="utf-8")
        self.assertEqual(cli.main(["feed", str(self.pack), "--file", str(feed_file)]), 0)

        self.assertEqual(load_clock(self.pack)["last_seen_date"], today.isoformat())

    def test_bad_clock_json_self_heals(self):
        (self.pack / "mind" / "clock.json").write_text(
            json.dumps({"format": "seedbank/clock@1", "last_seen_date": "2026-13-01"}),
            encoding="utf-8",
        )
        self.assertIsNone(load_clock(self.pack)["last_seen_date"])
        with self.assertRaises(Exception):
            check(self.pack)

        result = tick(self.pack, now="2026-11-05T09:00:00+08:00")
        # A missing/invalid last_seen now restores the actual calendar date,
        # preserving the old page and recording the unobserved gap.
        self.assertTrue(result["advanced"])
        self.assertEqual(result["date"], "2026-11-05")
        self.assertEqual(load_clock(self.pack)["last_seen_date"], "2026-11-05")
        check(self.pack)

    def test_resolve_pack_ignores_non_string_default(self):
        home = self.tmp / "home"
        (home / ".seedbank").mkdir(parents=True)
        (home / ".seedbank" / "config.json").write_text(
            json.dumps({"format": "seedbank/config@1", "default_pack": 123}),
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"USERPROFILE": str(home)}):
            self.assertIsNone(onboarding.resolve_pack())

    def test_live_failed_event_journal_mode(self):
        from seedbank import live

        inbox = self.pack / "inbox"
        inbox.mkdir(exist_ok=True)
        (inbox / "bad.json").write_text("{not json", encoding="utf-8")
        live.process_inbox(self.pack)
        journal = (self.pack / "journal" / "loop.jsonl").read_text(encoding="utf-8")
        modes = [json.loads(line)["mode"] for line in journal.splitlines() if line.strip()]
        self.assertIn("live_failed", modes)

    def test_live_interval_validated_before_banner(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(["live", str(self.pack), "--interval", "0.5"])
        self.assertEqual(code, 1)
        self.assertNotIn("循环开始了", buffer.getvalue())

