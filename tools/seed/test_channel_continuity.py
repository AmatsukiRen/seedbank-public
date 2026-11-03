"""User-run regression cases; artificial packs, no platform or model requests."""
from contextlib import closing
import io
import json
import sqlite3
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from seedbank import channels, disclosure
from seedbank.channel_worker import Bus, telegram_event, discord_event, feishu_event, dingtalk_event, run_telegram
from seedbank.desktop.session import Session
from seedbank.retrieval import search
from seedbank.util import read_memories
from test_channels import event
from test_memory_evolution import FixedBrain
from test_runtime_self import RuntimeSelfTest


def config(kind):
    return channels.defaults(kind) | {"owner": "42", "groups": "group1", "app_id": "app1", "self_id": "99"}


def telegram(text="@seedbot", entities=None):
    return {"message": {"message_id": 1, "from": {"id": 42, "is_bot": False},
            "chat": {"id": "group1", "type": "supergroup"}, "text": text,
            "entities": entities if entities is not None else [{"type": "mention", "offset": 0, "length": 8}]}}


def discord(text="<@99>", mentions=True):
    return SimpleNamespace(author=SimpleNamespace(bot=False, id=42), webhook_id=None, content=text,
        id=1, channel=SimpleNamespace(id="group1"), mentions=[SimpleNamespace(id=99)] if mentions else [])


def feishu():
    return {"event": {"sender": {"sender_type": "user", "sender_id": {"open_id": "42"}},
            "message": {"message_id": "1", "chat_id": "group1", "chat_type": "group", "message_type": "text",
            "content": '{"text":"@_user_1"}', "mentions": [{"key": "@_user_1", "id": {"open_id": "99"}}]}}}


class NormalizationTest(unittest.TestCase):
    def test_bare_mentions_from_each_direct_platform_reach_shared_route(self):
        rows = {"telegram": telegram_event(telegram(), {"id": 99, "username": "seedbot"}),
                "discord": discord_event(discord(), 99, direct=False),
                "feishu": feishu_event(feishu(), config("feishu")),
                "dingtalk": dingtalk_event({"msgtype": "text", "msgId": "1", "senderStaffId": "42",
                    "conversationId": "group1", "conversationType": "2", "isInAtList": True,
                    "text": {"content": " "}}, config("dingtalk"))}
        for kind, row in rows.items():
            with self.subTest(kind=kind):
                self.assertTrue(row["mentioned"])
                self.assertEqual(row["text"], "")
                request = channels.route(config(kind), row)
                self.assertTrue(request["text"])
                self.assertNotEqual(request["audience_id"], "owner")

    def test_empty_input_does_not_bypass_scope_or_astrbot_command_contract(self):
        for kind in ("telegram", "discord", "feishu", "dingtalk", "astrbot"):
            with self.subTest(kind=kind):
                cfg = config(kind)
                self.assertIsNone(channels.route(cfg, event(text="")))
                self.assertIsNone(channels.route(cfg, event(text="", direct=False, chat="other", mentioned=True)))
                self.assertIsNone(channels.route(cfg, event(text="", direct=False, chat="group1", mentioned=False)))
                self.assertIsNone(channels.route(cfg, event(text=None, direct=False, chat="group1", mentioned=True)))
        self.assertIsNone(channels.route(config("astrbot"), event(text="", direct=False, chat="group1", mentioned=True)))

    def test_telegram_preserves_literal_username_and_removes_named_utf16_mention(self):
        bot = {"id": 99, "username": "seedbot"}
        literal = telegram_event(telegram("这是字面 @seedbot", []), bot)
        self.assertEqual(literal["text"], "这是字面 @seedbot")
        self.assertFalse(literal["mentioned"])
        row = telegram_event(telegram("😀 小种子 你好", [
            {"type": "text_mention", "offset": 3, "length": 3, "user": {"id": 99}}]), bot)
        self.assertTrue(row["mentioned"])
        self.assertEqual(row["text"], "😀  你好")
        row = telegram_event(telegram("@seedbot 文本 @seedbot"), bot)
        self.assertEqual(row["text"], "文本 @seedbot")

    def test_discord_requires_platform_mention_evidence(self):
        row = discord_event(discord("<@99> 字面文本", mentions=False), 99, direct=False)
        self.assertFalse(row["mentioned"])
        self.assertEqual(row["text"], "<@99> 字面文本")
        self.assertIsNone(channels.route(config("discord"), row))

    def test_malformed_event_fields_are_rejected_without_killing_parser(self):
        for bad in (None, [], "bad"):
            self.assertIsNone(telegram_event(bad, {"id": 99}))
            self.assertIsNone(feishu_event(bad, config("feishu")))
            self.assertIsNone(dingtalk_event(bad, config("dingtalk")))
        for bad in ("{", "[]", '{"text":null}', '{"text":{}}'):
            data = feishu()
            data["event"]["message"]["content"] = bad
            self.assertIsNone(feishu_event(data, config("feishu")))
        data = telegram()
        data["message"]["entities"] = [None, {"offset": "bad", "length": 8}, {"offset": -1, "length": 8}]
        self.assertFalse(telegram_event(data, {"id": 99, "username": "seedbot"})["mentioned"])

    def test_worker_reports_explicit_send_rejection(self):
        bus = Bus.__new__(Bus)
        bus.source, bus.output, bus.lock = io.StringIO('{"reply":"人工回复"}\n'), io.StringIO(), threading.Lock()
        send = Mock(return_value=False)
        bus.forward(event(), send)
        receipt = json.loads(bus.output.getvalue().splitlines()[-1])
        self.assertEqual(receipt, {"type": "delivery", "ok": False})
        send.assert_called_once_with("人工回复")
        bus.source, bus.output = io.StringIO('{"reply":"人工回复"}\n'), io.StringIO()
        bus.forward(event(), Mock(side_effect=TimeoutError("PRIVATE_FIXTURE")))
        receipt = json.loads(bus.output.getvalue().splitlines()[-1])
        self.assertEqual(receipt, {"type": "delivery", "ok": False, "uncertain": True})
        self.assertNotIn("PRIVATE_FIXTURE", bus.output.getvalue())

    def test_telegram_empty_send_receipt_is_not_reported_as_delivered(self):
        bus = Mock()
        captured = []
        bus.forward.side_effect = lambda row, send: captured.append(send)
        update = telegram("@seedbot 你好") | {"update_id": 10}
        responses = [{"ok": True, "result": {"id": 99, "username": "seedbot"}},
                     {"ok": True, "result": {"url": ""}}, {"ok": True, "result": []},
                     {"ok": True, "result": [update]}, RuntimeError("end artificial polling")]
        with patch("seedbank.channel_worker.post", side_effect=responses), self.assertRaises(RuntimeError):
            run_telegram(config("telegram"), "artificial-token", bus)
        self.assertEqual(len(captured), 1)
        with patch("seedbank.channel_worker.post", return_value={"ok": True, "result": {}}), self.assertRaises(RuntimeError):
            captured[0]("人工回复")


class ContinuityTest(unittest.TestCase):
    setUp = RuntimeSelfTest.setUp

    def connection(self, kind):
        connection = channels.Connection(self.session, config(kind))
        self.session.channels.connections[kind] = connection
        return connection

    def test_each_channel_saves_group_memory_and_reopens_in_desktop_without_other_group_access(self):
        for kind in ("telegram", "discord", "feishu", "dingtalk", "astrbot"):
            with self.subTest(kind=kind):
                marker = kind + " 群里约定的人工代号是琉璃纸鹤。"
                self.session.bridge._brain = FixedBrain({"reply": "记下了。", "memory_writes": [
                    {"text": marker, "importance": .6, "kind": "conversation", "tags": [kind]}]})
                row = event(event_id=kind, direct=False, mentioned=True, chat="group1", sender="43", text=marker)
                conn = self.connection(kind)
                self.assertTrue(conn.exchange(row, lambda reply: bool(reply)))
                self.assertTrue(any(memory["text"] == marker for memory in read_memories(self.pack)))
                reopened = Session(self.pack, brain_override="stub")
                try:
                    reopened.bridge._brain = self.brain
                    reopened.call("message", text=kind + " 群里的人工代号是什么？")
                    self.assertIn(marker, json.dumps(self.brain.context, ensure_ascii=False))
                    self.assertIn(marker, json.dumps(reopened.snapshot()["memories"], ensure_ascii=False))
                finally:
                    reopened.close()
                scope = channels.route(config(kind), row)["audience_id"]
                other = channels.route(config(kind) | {"groups": "group2"}, row | {"chat": "group2"})["audience_id"]
                self.assertTrue(search(self.pack, "琉璃纸鹤", policy=disclosure.policy_for(self.pack, scope, ""), use_semantic=False))
                self.assertFalse(search(self.pack, "琉璃纸鹤", policy=disclosure.policy_for(self.pack, other, ""), use_semantic=False))

    def test_each_channel_raw_input_is_recallable_without_a_memory_card(self):
        before = read_memories(self.pack)
        for kind in ("telegram", "discord", "feishu", "dingtalk", "astrbot"):
            with self.subTest(kind=kind):
                marker = kind + " 的人工测试作品叫银色帆船。"
                self.assertTrue(self.connection(kind).exchange(event(event_id=kind, text=marker), lambda reply: bool(reply)))
                self.assertEqual(self.brain.context["runtime_self"]["channel"], kind)
                self.assertTrue(any(marker in row["memory"]["text"] for row in search(self.pack, "银色帆船", use_semantic=False)))
        self.assertEqual(read_memories(self.pack), before)

    def test_astrbot_handoff_is_not_a_platform_send_receipt_or_repeated_after_reopen(self):
        conn = self.connection("astrbot")
        deliver = Mock(return_value=True)
        conn.exchange(event(), deliver)
        self.assertEqual((conn.sent, conn.relayed, conn.failed), (0, 1, 0))
        self.assertEqual(conn.summary()["stage"], "relayed")
        with closing(sqlite3.connect(conn.journal.path)) as db:
            self.assertEqual(db.execute("SELECT state FROM delivery").fetchone()[0], "relayed")
        self.session.call("message", text="AstrBot 回复送到哪里了？")
        self.assertEqual(self.brain.context["runtime_self"]["channels"]["astrbot"]["relayed"], 1)
        self.assertEqual(self.brain.context["runtime_self"]["channels"]["astrbot"]["sent"], 0)
        channels.Connection(self.session, config("astrbot")).exchange(event(), deliver)
        self.assertEqual([call.args[0] for call in deliver.call_args_list], ["人工测试回答。", ""])

    def test_processing_and_send_stages_are_visible_without_payload(self):
        conn = self.connection("telegram")
        original = self.brain.chat
        observed = []
        def chat(ctx):
            observed.append(conn.summary()["stage"])
            return original(ctx)
        def send(reply):
            observed.append(conn.summary()["stage"])
            return True
        with patch.object(self.brain, "chat", side_effect=chat):
            conn.exchange(event(text="PRIVATE_FIXTURE"), send)
        self.assertEqual(observed, ["generating", "sending"])
        self.assertEqual(conn.summary()["stage"], "delivered")
        self.assertNotIn("PRIVATE_FIXTURE", json.dumps(conn.summary()))

    def test_empty_reply_is_not_marked_delivered(self):
        conn = self.connection("discord")
        self.session.bridge._brain = FixedBrain({"reply": ""})
        with patch.object(self.session, "call", return_value={"reply": ""}):
            deliver = Mock(return_value=True)
            conn.exchange(event(), deliver)
        deliver.assert_called_once_with("")
        self.assertEqual(conn.summary()["stage"], "no_reply")
        self.assertEqual(conn.sent, 0)

    def test_unconfirmed_send_retains_failure_scope_and_is_not_retried(self):
        conn = self.connection("feishu")
        deliver = Mock(side_effect=TimeoutError("PRIVATE_FIXTURE"))
        with self.assertRaises(TimeoutError):
            conn.exchange(event(), deliver)
        self.assertEqual(conn.summary()["stage"], "delivery_unknown")
        self.assertEqual(conn.failed, 1)
        self.assertNotIn("PRIVATE_FIXTURE", json.dumps(conn.summary()))
        second = Mock(return_value=True)
        conn.exchange(event(), second)
        second.assert_called_once_with("")

    def test_local_rejection_reasons_never_reach_model_or_override_identity(self):
        conn = self.connection("dingtalk")
        with patch.object(self.session, "call") as call:
            for changes, stage in (({"sender": "43"}, "not_owner"),
                    ({"direct": False, "chat": "other", "mentioned": True}, "group_not_allowed"),
                    ({"direct": False, "chat": "group1"}, "not_mentioned")):
                conn.exchange(event(**changes), lambda reply: not reply)
                self.assertEqual(conn.summary()["stage"], stage)
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
