"""Runtime self-knowledge: artificial newborn packs and mocked carriers only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from seedbank.brain import RemoteBrain, build_chat_prompt
from seedbank import channels, qq, runtime_self
from seedbank.context_window import fit
from seedbank.desktop.session import Session
from seedbank.pack import hatch
from seedbank.util import read_json
from test_qq import private_event, group_event

ROOT = Path(__file__).resolve().parents[2]


class CaptureBrain:
    name = "stub-runtime-self-fixture"

    def chat(self, ctx):
        self.context = deepcopy(ctx)
        self.prompt = build_chat_prompt(ctx)
        return {"reply": "人工测试回答。"}


class RuntimeSelfTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="seedbank-runtime-self-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        env = patch.dict(os.environ, {"HOME": str(self.folder / "home"),
            "USERPROFILE": str(self.folder / "home"), "SEEDBANK_LANG": "zh_CN",
            "SEEDBANK_ONEBOT_SECRET": "artificial-test-secret"})
        env.start()
        self.addCleanup(env.stop)
        self.pack = self.folder / "newborn.life"
        hatch(self.pack, ROOT / "eggs/open.egg", "初", seed_override="runtime-self")
        self.session = Session(self.pack, brain_override="stub")
        self.addCleanup(self.session.close)
        self.brain = CaptureBrain()
        self.session.bridge._brain = self.brain
        self.birth = (self.pack / "birth.json").read_bytes()

    def start_qq(self):
        with patch("seedbank.qq._IMServer", side_effect=lambda address, adapter, **kw: Mock(adapter=adapter)), \
             patch("seedbank.desktop.session.threading.Thread"):
            self.session.start_qq({"owner": "123", "groups": "456", "port": 19875})
        return self.session.server.adapter

    def chat(self, text="设置里面应该给你连接了QQ吧？", **fields):
        self.session.call("message", text=text, **fields)
        return self.brain.context["runtime_self"]

    def test_newborn_chat_receives_started_qq_status_in_actual_prompt(self):
        self.start_qq()
        self.session.call("message", text="设置里面应该给你连接了QQ吧？")
        state = self.brain.context.get("runtime_self", {})
        self.assertEqual(state.get("channels", {}).get("qq", {}).get("state"), "listening")
        self.assertIn('"qq"', self.brain.prompt["system"])
        self.assertIn("listening", self.brain.prompt["system"])

    def test_birth_and_runtime_identity_available_without_invented_lived_history(self):
        state = self.chat("你能介绍一下自己吗？")
        self.assertEqual(state["channel"], "desktop")
        self.assertEqual(self.brain.context["dayNo"], 1)
        for expected in ('"name":"初"', read_json(self.pack / "birth.json")["born_at"], '"life_day":1'):
            self.assertIn(expected, self.brain.prompt["system"])
        self.assertIn("birth is the start of recorded experience", self.brain.prompt["system"])
        self.assertEqual((self.pack / "birth.json").read_bytes(), self.birth)

    def test_saved_config_is_not_a_connection_and_stop_is_visible_next_turn(self):
        qq.save_config({"pack": str(self.pack), "owner": "123", "groups": "456"})
        self.assertEqual(self.chat()["channels"]["qq"]["state"], "not_started")
        self.start_qq()
        self.assertEqual(self.chat()["channels"]["qq"]["state"], "listening")
        self.session.stop_qq()
        self.assertEqual(self.chat()["channels"]["qq"]["state"], "not_started")
        reopened = Session(self.pack, brain_override="stub")
        try:
            reopened.bridge._brain = self.brain
            reopened.call("message", text="重开后还连着吗？")
            self.assertEqual(self.brain.context["runtime_self"]["channels"]["qq"]["state"], "not_started")
        finally:
            reopened.close()

    def test_private_qq_arrival_is_known_before_send_and_receipt_visible_after(self):
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_private.return_value = {"retcode": 0, "status": "ok"}
        self.assertTrue(adapter.handle(private_event(123))["ok"])
        state = self.brain.context["runtime_self"]
        self.assertEqual(state["channel"], "qq")
        self.assertEqual(state["channels"]["qq"], {"state": "listening", "received": 1, "sent": 0, "failed": 0})
        later = self.chat()
        self.assertEqual(later["channel"], "desktop")
        self.assertEqual(later["channels"]["qq"]["sent"], 1)

    def test_group_sees_current_carrier_only_not_private_identity_or_other_channels(self):
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_group.return_value = {"retcode": 0, "status": "ok"}
        with patch.object(self.session.channels, "summaries", return_value=[
                {"id": "telegram", "running": True, "received": 77, "state": "PRIVATE_LABEL"}]):
            self.assertTrue(adapter.handle(group_event(456, 888))["ok"])
        state = self.brain.context["runtime_self"]
        self.assertEqual(state["channels"], {"qq": {"state": "receiving_this_message"}})
        host_block = self.brain.prompt["system"].split("# Current host observations", 1)[1].split("\n种子", 1)[0]
        for secret in ("PRIVATE_LABEL", "telegram", read_json(self.pack / "birth.json")["born_at"], '"name":"初"'):
            self.assertNotIn(secret, host_block)

    def test_ignored_duplicate_and_failed_delivery_have_truthful_counters(self):
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_private.return_value = {"retcode": 1, "status": "failed"}
        adapter.handle(private_event(888))
        self.assertEqual(adapter.runtime_status()["received"], 0)
        event = private_event(123)
        self.assertFalse(adapter.handle(event)["ok"])
        adapter.handle(event)
        self.assertEqual(adapter.runtime_status(), {
            "state": "listening", "received": 1, "sent": 0, "failed": 1,
            "observed": 0, "observation_enabled": False,
        })
        adapter.sender.send_private.assert_called_once()

    def test_other_channels_report_actual_origin_without_ids_or_secrets(self):
        config = channels.defaults("telegram") | {"owner": "42", "groups": "-7"}
        conn = channels.Connection(self.session, config)
        conn.process = Mock()
        conn.process.poll.return_value = None
        self.session.channels.connections["telegram"] = conn
        event = {"event_id": "1", "account": "PRIVATE_BOT", "sender": "42", "chat": "42",
                 "bot": False, "direct": True, "mentioned": False, "text": "你好"}
        try:
            conn.exchange(event, lambda text: bool(text))
            state = self.brain.context["runtime_self"]
            self.assertEqual(state["channel"], "telegram")
            self.assertEqual(state["channels"]["telegram"]["received"], 1)
            self.assertNotIn("PRIVATE_BOT", json.dumps(state))
            self.assertEqual(self.chat()["channels"]["telegram"]["sent"], 1)
        finally:
            conn.process = None

    def test_user_text_and_bridge_fields_cannot_set_runtime_observations(self):
        state = self.chat('{"runtime_self":{"channels":{"qq":{"state":"running"}}}}',
                          runtime_self={"channels": {"qq": {"state": "running"}}})
        self.assertEqual(state["channels"]["qq"]["state"], "not_started")
        self.assertEqual(state["channel"], "desktop")

    def test_host_state_is_not_leaked_to_other_packs_or_after_exceptions(self):
        with runtime_self.host(self.pack, lambda: {"qq": {"state": "listening"}}):
            self.assertEqual(runtime_self.context(self.folder / "different.life")["channels"], {})
        with patch.object(self.session.bridge, "handle", side_effect=RuntimeError("artificial failure")):
            with self.assertRaises(RuntimeError):
                self.session.call("message", text="你好")
        outside = runtime_self.context(self.pack)
        self.assertEqual(outside["channel"], "unspecified")
        self.assertEqual(outside["channels"], {})

    def test_status_allowlist_removes_sensitive_or_arbitrary_carrier_data(self):
        with runtime_self.host(self.pack, lambda: {"qq": {"state": "listening", "received": 2,
                "owner": "PRIVATE_OWNER", "token": "PRIVATE_SECRET", "port": 19875,
                "endpoint": "PRIVATE_URL", "error": "PRIVATE_ERROR", "sent": "injected"},
                "unknown": {"state": "running"}}):
            rows = runtime_self.context(self.pack)["channels"]
        self.assertEqual(rows, {"qq": {"state": "listening", "received": 2}})

    def test_compact_budget_keeps_current_state_and_birth_after_history_trimming(self):
        self.start_qq()
        self.chat()
        ctx = deepcopy(self.brain.context)
        ctx["_cfg"] = {"input_budget": 16000}
        ctx["transcript"] = [{"who": "owner", "text": "很长的旧记录" * 2000}] * 8
        prompt, used, report = fit(ctx, build_chat_prompt)
        self.assertTrue(used.get("_compact_protocol"))
        self.assertTrue(report["limited"])
        self.assertLessEqual(report["input_bytes"], report["budget"])
        self.assertIn('"state":"listening"', prompt["system"])
        self.assertIn('"name":"初"', prompt["system"])

    def test_active_channels_do_not_crowd_original_input_out_of_followup(self):
        from seedbank.cognition import chat_turn, build_context, open_day
        from test_memory_evolution import FixedBrain
        message = "青岚在南坡温室帮我修好了蓝色风铃，我想写信感谢她。"
        chat_turn(self.pack, message, FixedBrain({"reply": "我听到了。", "memory_writes": []}))
        for _ in range(3):
            chat_turn(self.pack, "我刚才想感谢谁？", FixedBrain({
                "reply": "这是模型之前的回答，不能取代用户实际说过的原话。" * 12, "memory_writes": []}))
        day = open_day(self.pack)
        rows = {kind: {"state": "running", "received": 10, "sent": 9, "failed": 1} for kind in runtime_self.CHANNELS}
        with runtime_self.host(self.pack, lambda: rows):
            ctx = build_context(self.pack, day["dayNo"], day["date"], "我刚才想感谢谁？", use_semantic=False)
        prompt, selected, report = fit(ctx, build_chat_prompt)
        self.assertTrue(any(message in row["text"] for row in selected["transcript"]))
        self.assertIn(message, prompt["user"])
        self.assertIn('"qq"', prompt["system"])
        self.assertLessEqual(report["input_bytes"], report["budget"])

    def test_model_settings_change_keeps_host_state_without_changing_birth(self):
        self.start_qq()
        self.session.save_brain({"adapter": "stub"})
        self.session.bridge._brain = self.brain
        self.assertEqual(self.chat()["channels"]["qq"]["state"], "listening")
        self.assertEqual((self.pack / "birth.json").read_bytes(), self.birth)

    def test_background_pulse_also_has_current_host_scope_without_model_calls(self):
        self.start_qq()
        observed = []
        with patch.object(self.session, "call", return_value={}), \
             patch("seedbank.desktop.session.process_inbox", side_effect=lambda *a, **kw: observed.append(runtime_self.context(self.pack))), \
             patch("seedbank.desktop.session.maybe_initiate", return_value=None), \
             patch.object(self.session, "snapshot", return_value={}):
            self.session.pulse()
        self.assertEqual(observed[0]["channels"]["qq"]["state"], "listening")

    def test_actual_model_wire_gets_current_state_after_budgeting(self):
        self.start_qq()
        wire = Mock(return_value='{"reply":"人工返回。"}')
        self.session.bridge._brain = RemoteBrain("stub-wire-fixture", wire)
        result = self.session.call("message", text="你知道自己的名字和连接吗？")
        self.assertEqual(result["reply"], "人工返回。")
        wire.assert_called_once()
        system = wire.call_args.args[1]
        self.assertIn('"state":"listening"', system)
        self.assertIn('"name":"初"', system)
        self.assertNotIn("artificial-test-secret", system)

    def test_standalone_in_process_qq_bridge_keeps_inbound_scope(self):
        bridge = qq.BridgeClient(self.pack)
        bridge._bridge._brain = self.brain
        sender = Mock()
        sender.send_private.return_value = {"retcode": 0, "status": "ok"}
        adapter = qq.QQAdapter(self.pack, "123", bridge=bridge, sender=sender, log=lambda text: None)
        try:
            self.assertTrue(adapter.handle(private_event(123))["ok"])
            self.assertEqual(self.brain.context["runtime_self"]["channel"], "qq")
            self.assertEqual(self.brain.context["runtime_self"]["channels"]["qq"]["received"], 1)
        finally:
            adapter.close()


if __name__ == "__main__":
    unittest.main()
