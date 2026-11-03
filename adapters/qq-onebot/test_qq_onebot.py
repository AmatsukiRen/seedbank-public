"""QQ 载体适配器的测试（纯函数 + 假桥 + 假发送端，不需要真的 QQ）。"""

from __future__ import annotations

import sys
import itertools
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qq_onebot as adapter  # noqa: E402
EVENT_IDS = itertools.count(1)


class FakeBridge:
    def __init__(self):
        self.calls = []

    def call(self, op, **fields):
        self.calls.append((op, fields))
        if op == "message":
            return {"ok": True, "reply": "我在。刚才在看光。"}
        return {"ok": True, "lines": ["光很亮，是暖的。"]}


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_private(self, user_id, text):
        self.sent.append(("private", str(user_id), text))
        return {"status": "ok", "retcode": 0}

    def send_group(self, group_id, text, at_user=""):
        self.sent.append(("group", str(group_id), text, str(at_user)))
        return {"status": "ok", "retcode": 0}


def private_event(user_id=123, text="你好呀"):
    return {
        "message_id": next(EVENT_IDS),
        "post_type": "message",
        "message_type": "private",
        "user_id": user_id,
        "self_id": 999,
        "message": [{"type": "text", "data": {"text": text}}],
    }


def group_event(group_id=456, user_id=123, mentioned=True, text="在吗"):
    segments = []
    if mentioned:
        segments.append({"type": "at", "data": {"qq": "999"}})
    segments.append({"type": "text", "data": {"text": " " + text}})
    return {
        "message_id": next(EVENT_IDS),
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": 999,
        "message": segments,
    }


class ParseTest(unittest.TestCase):
    def test_extract_text(self):
        segments = [
            {"type": "at", "data": {"qq": "999"}},
            {"type": "text", "data": {"text": "你好"}},
            {"type": "image", "data": {"url": "http://x/y.png"}},
            {"type": "text", "data": {"text": " 呀"}},
        ]
        self.assertEqual(adapter.extract_text(segments), "你好 呀")

    def test_find_images(self):
        segments = [{"type": "image", "data": {"url": "http://x/y.png"}}]
        self.assertEqual(len(adapter.find_images(segments)), 1)

    def test_mentioned(self):
        segments = [{"type": "at", "data": {"qq": "999"}}]
        self.assertTrue(adapter.mentioned(segments, "999"))
        self.assertFalse(adapter.mentioned(segments, "123"))
        self.assertFalse(adapter.mentioned([], "999"))


class DecideTest(unittest.TestCase):
    def test_private_owner_chats(self):
        decision = adapter.decide(private_event(123), owner="123")
        self.assertEqual(decision["action"], "chat")
        self.assertEqual(decision["speaker"], "主人")
        self.assertEqual(decision["target"], "private")

    def test_private_stranger_ignored(self):
        decision = adapter.decide(private_event(777), owner="123")
        self.assertEqual(decision["action"], "ignore")

    def test_group_requires_mention(self):
        self.assertEqual(adapter.decide(group_event(mentioned=False), owner="123", groups=["456"])["action"], "ignore")
        self.assertEqual(adapter.decide(group_event(mentioned=True), owner="123", groups=["456"])["action"], "chat")

    def test_group_whitelist(self):
        decision = adapter.decide(group_event(group_id=888, mentioned=True), owner="123", groups=["456"])
        self.assertEqual(decision["action"], "ignore")
        self.assertIn("白名单", decision["reason"])

    def test_group_is_guest(self):
        decision = adapter.decide(group_event(mentioned=True), owner="123", groups=["456"])
        self.assertEqual(decision["speaker"], "访客")

    def test_image_becomes_sense(self):
        event = private_event()
        event["message"].append({"type": "image", "data": {"url": "http://x/1.png"}})
        decision = adapter.decide(event, owner="123")
        self.assertEqual(decision["action"], "sense")
        self.assertEqual(decision["images"], ["http://x/1.png"])


class HandleTest(unittest.TestCase):
    def setUp(self):
        from seedbank.pack import hatch
        temporary = tempfile.TemporaryDirectory(prefix="seedbank-adapter-test-")
        self.addCleanup(temporary.cleanup)
        self.pack = Path(temporary.name) / "test.life"
        hatch(self.pack, Path(__file__).resolve().parents[2] / "eggs/open.egg", "适配器测试")

    def _adapter(self, **kwargs):
        bridge = FakeBridge()
        sender = FakeSender()
        instance = adapter.QQAdapter(str(self.pack), owner="123",
                                     groups=["456"], bridge=bridge, sender=sender,
                                     log=lambda message: None, **kwargs)
        return instance, bridge, sender

    def test_private_roundtrip(self):
        instance, bridge, sender = self._adapter()
        result = instance.handle(private_event())
        self.assertTrue(result["ok"])
        self.assertEqual(bridge.calls[0][0], "message")
        self.assertEqual(sender.sent[0][:2], ("private", "123"))
        self.assertIn("我在", sender.sent[0][2])

    def test_group_reply_has_at(self):
        instance, bridge, sender = self._adapter()
        instance.handle(group_event(mentioned=True))
        self.assertEqual(sender.sent[0][0], "group")
        self.assertEqual(sender.sent[0][3], "123")

    def test_stranger_never_touches_bridge(self):
        instance, bridge, sender = self._adapter()
        result = instance.handle(private_event(777))
        self.assertEqual(result["action"], "ignore")
        self.assertEqual(bridge.calls, [])
        self.assertEqual(sender.sent, [])

    def test_image_calls_sense(self):
        instance, bridge, sender = self._adapter()
        temp = Path(tempfile.mkdtemp(prefix="qq-test-"))
        image = temp / "x.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 8)
        instance._download = lambda url: image  # 不真的下载

        event = private_event()
        event["message"].append({"type": "image", "data": {"url": "http://x/1.png"}})
        result = instance.handle(event)
        self.assertTrue(result["ok"])
        self.assertEqual(bridge.calls[0][0], "media")
        image_calls = [fields for op, fields in bridge.calls if op == "image"]
        self.assertEqual(len(image_calls), 1)
        self.assertTrue(image_calls[0]["path"].endswith(".png"))


if __name__ == "__main__":
    unittest.main()
