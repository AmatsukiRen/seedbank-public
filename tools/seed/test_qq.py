"""QQ 载体（OneBot v11）的测试。

这些测试不需要真的 QQ / OneBot 实现：纯函数直接测，
BridgeClient 用临时孵化的生命包，连接测试用一个假 OneBot HTTP 服务。
"""
from __future__ import annotations

import json
import itertools
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "seed"))

from seedbank import qq  # noqa: E402
from seedbank.pack import hatch  # noqa: E402

EGG = ROOT / "eggs" / "dafeiyu.egg"
EVENT_IDS = itertools.count(1)


def private_event(user_id, text="你好呀", self_id=999):
    return {
        "message_id": next(EVENT_IDS),
        "post_type": "message",
        "message_type": "private",
        "user_id": int(user_id),
        "self_id": int(self_id),
        "message": [{"type": "text", "data": {"text": text}}],
    }


def group_event(group_id, user_id, text="你好呀", self_id=999, at=True):
    message = []
    if at:
        message.append({"type": "at", "data": {"qq": str(self_id)}})
        message.append({"type": "text", "data": {"text": " "}})
    message.append({"type": "text", "data": {"text": text}})
    return {
        "message_id": next(EVENT_IDS),
        "post_type": "message",
        "message_type": "group",
        "group_id": int(group_id),
        "user_id": int(user_id),
        "self_id": int(self_id),
        "message": message,
    }


class PureTest(unittest.TestCase):
    def test_extract_text_joins_text_segments(self):
        segments = [
            {"type": "at", "data": {"qq": "999"}},
            {"type": "text", "data": {"text": "早上"}},
            {"type": "image", "data": {"url": "http://x/1.png"}},
            {"type": "text", "data": {"text": "好呀"}},
        ]
        self.assertEqual(qq.extract_text(segments), "早上好呀")

    def test_find_images(self):
        segments = [
            {"type": "image", "data": {"url": "http://x/a.png"}},
            {"type": "text", "data": {"text": "看"}},
            {"type": "image", "data": {"file": "b.jpg"}},
        ]
        self.assertEqual(
            qq.find_images(segments),
            [{"url": "http://x/a.png"}, {"url": "b.jpg"}],
        )

    def test_mentioned(self):
        segments = [{"type": "at", "data": {"qq": "999"}}]
        self.assertTrue(qq.mentioned(segments, 999))
        self.assertFalse(qq.mentioned(segments, 1000))
        self.assertFalse(qq.mentioned(segments, ""))


class DecideTest(unittest.TestCase):
    def test_private_owner_is_chat(self):
        decision = qq.decide(private_event(123), owner="123")
        self.assertEqual(decision["action"], "chat")
        self.assertEqual(decision["speaker"], "主人")
        self.assertEqual(decision["text"], "你好呀")

    def test_private_stranger_is_ignored(self):
        decision = qq.decide(private_event(456), owner="123")
        self.assertEqual(decision["action"], "ignore")

    def test_private_empty_is_ignored(self):
        event = private_event(123)
        event["message"] = [{"type": "face", "data": {"id": "1"}}]
        self.assertEqual(qq.decide(event, owner="123")["action"], "ignore")

    def test_group_needs_mention(self):
        decision = qq.decide(group_event(555, 123, at=False), owner="123")
        self.assertEqual(decision["action"], "ignore")

    def test_group_needs_whitelist(self):
        decision = qq.decide(group_event(555, 123), owner="123", groups=["666"])
        self.assertEqual(decision["action"], "ignore")
        decision = qq.decide(group_event(555, 123), owner="123", groups=["555"])
        self.assertEqual(decision["action"], "chat")
        self.assertEqual(decision["speaker"], "访客")

    def test_image_is_sense(self):
        event = private_event(123)
        event["message"] = [
            {"type": "text", "data": {"text": "看这个"}},
            {"type": "image", "data": {"url": "http://x/a.png"}},
        ]
        decision = qq.decide(event, owner="123")
        self.assertEqual(decision["action"], "sense")
        self.assertEqual(decision["images"], ["http://x/a.png"])

    def test_non_message_is_ignored(self):
        self.assertEqual(qq.decide({"post_type": "notice"}, owner="123")["action"], "ignore")


class BridgeClientTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="seedbank-qq-test-")
        self.addCleanup(self._tmp.cleanup)
        self.pack = Path(self._tmp.name) / "qq鱼.life"
        hatch(self.pack, EGG, "qq鱼", seed_override="qq-test")

    def test_hello_and_status(self):
        client = qq.BridgeClient(self.pack)
        self.addCleanup(client.close)
        hello = client.call("hello")
        self.assertEqual(hello.get("name"), "qq鱼")
        status = client.call("status")
        self.assertGreaterEqual(int(status.get("days") or 0), 1)

    def test_message_roundtrip(self):
        client = qq.BridgeClient(self.pack)
        self.addCleanup(client.close)
        result = client.call("message", text="你好呀", speaker="访客")
        self.assertTrue(str(result.get("reply") or "").strip())


class FakeOneBot(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) or b"{}"
        FakeOneBot.calls.append((self.path, json.loads(raw.decode("utf-8"))))
        auth = self.headers.get("Authorization") or ""
        body = json.dumps({
            "status": "ok",
            "retcode": 0,
            "data": {"user_id": 10001, "nickname": "桥上的小号", "auth": auth},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        return


class ConnectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeOneBot.calls = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOneBot)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_connection_ok(self):
        result = qq.test_connection(self.base_url, token="tok")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["user_id"], "10001")
        self.assertEqual(result["nickname"], "桥上的小号")
        path, payload = FakeOneBot.calls[-1]
        self.assertEqual(path, "/get_login_info")

    def test_connection_refused(self):
        result = qq.test_connection("http://127.0.0.1:9", timeout=0.5)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


class ConfigTest(unittest.TestCase):
    def test_parse_groups(self):
        self.assertEqual(qq.parse_groups("1，2, 3"), ["1", "2", "3"])
        self.assertEqual(qq.parse_groups(["4", " 5 "]), ["4", "5"])
        self.assertEqual(qq.parse_groups(""), [])

    def test_save_config_keeps_token_out(self):
        with tempfile.TemporaryDirectory(prefix="seedbank-qq-conf-") as tmp:
            tmp_path = Path(tmp)
            with mock.patch("seedbank.onboarding.config_dir", return_value=tmp_path):
                saved = qq.save_config({
                    "owner": "123",
                    "groups": ["555"],
                    "onebot_http": "http://127.0.0.1:3001",
                })
                self.assertEqual(saved["owner"], "123")
                self.assertEqual(saved["groups"], ["555"])
                data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(data["qq"]["owner"], "123")
                self.assertNotIn("token", json.dumps(data))

    def test_config_defaults_missing(self):
        with tempfile.TemporaryDirectory(prefix="seedbank-qq-conf2-") as tmp:
            tmp_path = Path(tmp)
            with mock.patch("seedbank.onboarding.config_dir", return_value=tmp_path):
                self.assertEqual(qq.config_defaults(), {})


if __name__ == "__main__":
    unittest.main()

