"""User-run offline channel policy, normalization and delivery regressions."""
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from seedbank import channels, disclosure
from seedbank.channel_worker import telegram_event, feishu_event, dingtalk_event


def event(**overrides):
    return {"event_id": "e1", "account": "bot1", "sender": "42", "chat": "chat1", "text": "人工输入",
            "bot": False, "direct": True, "mentioned": False, **overrides}


class ChannelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patch = mock.patch.dict(os.environ, {"HOME": self.temp.name, "USERPROFILE": self.temp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.config = channels.defaults("telegram") | {"owner": "42", "groups": "group1"}
        self.session = SimpleNamespace(pack=Path(self.temp.name) / "artificial.life", closed=False,
            lock=threading.RLock(), call=mock.Mock(return_value={"reply": "人工回答"}))

    def test_only_explicit_owner_can_use_private_context(self):
        self.assertEqual(channels.route(self.config, event())["audience_id"], "owner")
        self.assertIsNone(channels.route(self.config, event(sender="43")))
        self.assertIsNone(channels.route(self.config, event(bot=True)))
        self.assertIsNone(channels.route(self.config, event(direct="true")))

    def test_groups_require_exact_allowlist_and_mention(self):
        self.assertIsNone(channels.route(self.config, event(direct=False, chat="group1")))
        self.assertIsNone(channels.route(self.config, event(direct=False, chat="group2", mentioned=True)))
        routed = channels.route(self.config, event(direct=False, chat="group1", mentioned=True))
        self.assertNotEqual(routed["audience_id"], "owner")
        self.assertEqual(disclosure.scope(routed["audience_id"]), routed["audience_id"])
        guest = channels.route(self.config, event(sender="43", direct=False, chat="group1", mentioned=True))
        self.assertEqual(guest["person_id"], "")

    def test_arbitrary_operations_and_sender_identity_are_not_forwarded(self):
        routed = channels.route(self.config, event(op="lifecycle", action="resume", person_id="self", audience_id="public"))
        self.assertEqual(routed["person_id"], "owner")
        self.assertNotIn("op", routed)
        self.assertIsNone(channels.route(self.config, event(event_id="")))
        self.assertIsNone(channels.route(self.config, event(text="x" * 2001)))

    def test_channel_and_account_namespace_is_part_of_dedup_and_scope(self):
        a = channels.route(self.config, event())
        b = channels.route(self.config, event(account="bot2"))
        c = channels.route({**self.config, "id": "discord"}, event())
        self.assertEqual(len({v["request_id"] for v in (a, b, c)}), 3)

    def test_local_config_saves_names_and_never_starts_a_worker(self):
        with mock.patch.dict(os.environ, {"SEEDBANK_TELEGRAM_TOKEN": "artificial-secret"}), mock.patch.object(channels.subprocess, "Popen") as proc:
            channels.save_config(self.session.pack, {**self.config, "token": "discard-me"})
            loaded = channels.load_config(self.session.pack, "telegram")
            self.assertEqual(loaded["owner"], "42")
            contents = channels.config_path(self.session.pack).read_text(encoding="utf-8")
            self.assertNotIn("artificial-secret", contents)
            self.assertNotIn("discard-me", contents)
            proc.assert_not_called()

    def test_missing_token_never_spawns_a_process(self):
        connection = channels.Connection(self.session, self.config)
        with mock.patch.dict(os.environ, {"SEEDBANK_TELEGRAM_TOKEN": ""}), mock.patch.object(channels.subprocess, "Popen") as proc:
            with self.assertRaises(ValueError):
                connection.start()
            proc.assert_not_called()

    def test_malformed_saved_channel_does_not_crash_or_replace_its_identity(self):
        path = channels.config_path(self.session.pack)
        path.parent.mkdir(parents=True)
        for content in ('{"telegram":null}', '{"telegram":[]}', '{"telegram":"broken"}', 'invalid json'):
            path.write_text(content, encoding="utf-8")
            self.assertEqual(channels.load_config(self.session.pack, "telegram"), channels.defaults("telegram"))
        path.write_text('{"telegram":{"id":"discord","owner":[],"token_env":null,"port":true}}', encoding="utf-8")
        self.assertEqual(channels.load_config(self.session.pack, "telegram"), channels.defaults("telegram"))
        self.assertIn('"discord"', path.read_text(encoding="utf-8"))  # Reading does not rewrite the file.

    def test_partial_worker_start_failure_releases_owned_process(self):
        manager = channels.Manager(self.session)
        process = mock.Mock()
        process.poll.return_value = None
        process.stdin.write.side_effect = BrokenPipeError("artificial child exit")
        with mock.patch.dict(os.environ, {self.config["token_env"]: "artificial-token"}), \
             mock.patch.object(channels.subprocess, "Popen", return_value=process):
            with self.assertRaises(BrokenPipeError):
                manager.start(self.config)
        process.terminate.assert_called_once()
        self.assertFalse(manager.summaries()[0]["running"])
        self.assertTrue(manager.connections["telegram"].stopped.is_set())

    def test_closed_manager_refuses_to_start_a_worker(self):
        manager = channels.Manager(self.session)
        manager.close()
        with mock.patch.object(channels.subprocess, "Popen") as proc, self.assertRaises(ValueError):
            manager.start(self.config)
        proc.assert_not_called()

    def test_relay_thread_start_failure_closes_socket_without_waiting_for_server(self):
        manager = channels.Manager(self.session)
        config = channels.defaults("astrbot") | {"owner": "42"}
        with mock.patch.dict(os.environ, {config["token_env"]: "artificial-token"}), \
             mock.patch.object(channels.ThreadingHTTPServer, "__init__", return_value=None), \
             mock.patch.object(channels.ThreadingHTTPServer, "server_close") as close, \
             mock.patch.object(channels.ThreadingHTTPServer, "shutdown") as shutdown, \
             mock.patch.object(channels.threading.Thread, "start", side_effect=RuntimeError("thread unavailable")):
            with self.assertRaises(RuntimeError):
                manager.start(config)
            close.assert_called_once()
            shutdown.assert_not_called()
        self.assertFalse(manager.summaries()[0]["running"])

    def test_duplicate_after_reopening_does_not_generate_or_send_again(self):
        connection = channels.Connection(self.session, self.config)
        deliver = mock.Mock(return_value=True)
        with mock.patch("seedbank.lifecycle.active", return_value=True):
            connection.exchange(event(), deliver)
            channels.Connection(self.session, self.config).exchange(event(), deliver)
        self.session.call.assert_called_once()
        self.assertEqual([c.args[0] for c in deliver.call_args_list], ["人工回答", ""])

    def test_journal_commits_and_releases_connections_on_success_and_error(self):
        real_connect = sqlite3.connect
        opened = []

        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            # Retain references so garbage collection cannot hide a leaked handle.
            opened.append(connection)
            self.addCleanup(connection.close)
            return connection

        with mock.patch.object(channels.sqlite3, "connect", side_effect=connect):
            journal = channels.Journal(self.session.pack)
            self.assertTrue(journal.claim("e1"))
            journal.finish("e1", "delivered")
            self.assertFalse(journal.claim("e1"))
            with self.assertRaises(sqlite3.IntegrityError):
                journal.finish("e1", None)

        for connection in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")
        with closing(real_connect(journal.path)) as db:
            self.assertEqual(db.execute("SELECT id, state FROM delivery").fetchall(), [("e1", "delivered")])

    def test_dormancy_and_stop_block_generation(self):
        connection = channels.Connection(self.session, self.config)
        deliver = mock.Mock(return_value=True)
        with mock.patch("seedbank.lifecycle.active", return_value=False):
            connection.exchange(event(), deliver)
        connection.stop()
        with mock.patch("seedbank.lifecycle.active", return_value=True):
            connection.exchange(event(), deliver)
        self.session.call.assert_not_called()

    def test_model_failure_does_not_send_exception_or_retry(self):
        self.session.call.side_effect = RuntimeError("PRIVATE artificial-key")
        connection = channels.Connection(self.session, self.config)
        deliver = mock.Mock(return_value=True)
        with mock.patch("seedbank.lifecycle.active", return_value=True):
            connection.exchange(event(), deliver)
            connection.exchange(event(), deliver)
        self.session.call.assert_called_once()
        self.assertTrue(all(c.args == ("",) for c in deliver.call_args_list))

    def test_uncertain_delivery_is_not_attempted_twice(self):
        connection = channels.Connection(self.session, self.config)
        deliver = mock.Mock(side_effect=TimeoutError("receipt lost"))
        with mock.patch("seedbank.lifecycle.active", return_value=True), self.assertRaises(TimeoutError):
            connection.exchange(event(), deliver)
        deliver.assert_called_once()
        with closing(sqlite3.connect(connection.journal.path)) as db:
            self.assertEqual(db.execute("SELECT state FROM delivery").fetchone()[0], "failed")

    def test_telegram_utf16_mention_and_private_detection(self):
        update = {"message": {"message_id": 1, "from": {"id": 42, "is_bot": False},
            "chat": {"id": -5, "type": "supergroup"}, "text": "😀 @seedbot hello",
            "entities": [{"type": "mention", "offset": 3, "length": 8}]}}
        normalized = telegram_event(update, {"id": 99, "username": "seedbot"})
        self.assertTrue(normalized["mentioned"])
        self.assertFalse(normalized["direct"])
        self.assertEqual(normalized["text"], "😀  hello")
        update["message"]["chat"]["type"] = "channel"
        self.assertIsNone(telegram_event(update, {"id": 99, "username": "seedbot"}))

    def test_feishu_checks_exact_bot_mention_and_open_id(self):
        data = {"event": {"sender": {"sender_type": "user", "sender_id": {"open_id": "ou_owner"}},
            "message": {"message_id": "om_1", "chat_id": "oc_1", "chat_type": "group", "message_type": "text",
                "content": '{"text":"@_user_1 hello"}', "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}]}}}
        cfg = channels.defaults("feishu") | {"app_id": "cli_demo", "self_id": "ou_bot"}
        normalized = feishu_event(data, cfg)
        self.assertEqual(normalized["text"], "hello")
        self.assertTrue(normalized["mentioned"])
        self.assertFalse(feishu_event(data, {**cfg, "self_id": "another"})["mentioned"])

    def test_dingtalk_requires_staff_identity_and_known_conversation_type(self):
        cfg = channels.defaults("dingtalk") | {"app_id": "app_demo"}
        data = {"msgtype": "text", "msgId": "1", "senderStaffId": "staff1", "conversationId": "cid1",
                "conversationType": "2", "isInAtList": True, "text": {"content": "hello"}}
        self.assertTrue(dingtalk_event(data, cfg)["mentioned"])
        self.assertFalse(dingtalk_event(data, cfg)["direct"])
        self.assertIsNone(dingtalk_event({**data, "senderStaffId": ""}, cfg))


if __name__ == "__main__":
    unittest.main()
