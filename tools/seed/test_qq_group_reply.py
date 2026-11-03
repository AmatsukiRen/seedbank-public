"""Group mention intake and outgoing requests, entirely mocked and offline."""
import json
import unittest
from unittest.mock import Mock, patch

from seedbank import qq
import test_runtime_self as fixtures
from test_qq import group_event


class GroupReplyTest(unittest.TestCase):
    setUp = fixtures.RuntimeSelfTest.setUp
    start_qq = fixtures.RuntimeSelfTest.start_qq

    def test_cq_string_mention_reaches_model_and_posts_reply_to_same_group(self):
        adapter = self.start_qq()
        event = group_event(456, 888)
        event["message"] = "[CQ:at,qq=999] 你好，我来打招呼。"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"status":"ok","retcode":0,"data":{"message_id":23}}'
        with patch("seedbank.qq.urllib.request.urlopen", return_value=response) as send:
            result = adapter.handle(event)
        self.assertEqual(result.get("action"), "chat")
        self.assertTrue(result["ok"])
        send.assert_called_once()
        request = send.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/send_group_msg"))
        payload = json.loads(request.data)
        self.assertEqual(payload["group_id"], 456)
        self.assertEqual(payload["message"][0], {"type": "at", "data": {"qq": "888"}})
        self.assertEqual(payload["message"][-1]["data"]["text"], "人工测试回答。")
        self.assertEqual(self.brain.context["_audience_id"], "qq-group:456")

    def test_bare_mention_is_a_greeting_event_not_silently_dropped(self):
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_group.return_value = {"status": "ok", "retcode": 0}
        for index, message in enumerate(("[CQ:at,qq=999]", [{"type": "at", "data": {"qq": "999"}}])):
            event = group_event(456, 888)
            event.update(message=message, message_id=800 + index)
            self.assertEqual(adapter.handle(event).get("action"), "chat")
            self.assertIn("没有附带文字", self.brain.context["message"])
        self.assertEqual(adapter.sender.send_group.call_count, 2)

    def test_cq_escapes_are_decoded_once_and_literal_mentions_do_not_trigger(self):
        for text in ("&#91;CQ:at,qq=999&#93; 你好", "&amp;#91;CQ:at,qq=999&amp;#93; 你好",
                     "[CQ:at,qq=all] 你好", "[CQ:at,qq=998] 你好", "[CQ:at,qq=999,qq=998] 你好"):
            event = group_event(456, 888)
            event["message"] = text
            self.assertEqual(qq.decide(event, owner="123", groups=["456"])["action"], "ignore")
        self.assertEqual(qq.extract_text("&#91;x&#93; &amp; &amp;#91;"), "[x] & &#91;")

    def test_cq_parameters_keep_commas_equals_and_array_text_is_not_reparsed(self):
        images = qq.find_images("[CQ:image,file=test&#44;a.jpg,url=https://example.invalid/a?x=1&amp;y=2]")
        self.assertEqual(images, [{"url": "https://example.invalid/a?x=1&y=2"}])
        raw = [{"type": "text", "data": {"text": "[CQ:at,qq=999] &#91;"}}]
        self.assertFalse(qq.mentioned(raw, 999))
        self.assertEqual(qq.extract_text(raw), "[CQ:at,qq=999] &#91;")

    def test_string_format_still_requires_whitelisted_group(self):
        event = group_event(987, 888)
        event["message"] = "[CQ:at,qq=999] 你好"
        self.assertEqual(qq.decide(event, owner="123", groups=["456"])["action"], "ignore")

    def test_malformed_message_segments_are_ignored_without_crashing_receiver(self):
        for raw in (None, 17, {}, [1, None], [{"type": "at", "data": "broken"}], [{"type": [], "data": {}}]):
            event = group_event(456, 888)
            event["message"] = raw
            self.assertEqual(qq.decide(event, owner="123", groups=["456"])["action"], "ignore")

    def test_group_memory_and_raw_conversation_survive_reopen_and_desktop_recall(self):
        from seedbank import cognition, disclosure, experience
        from seedbank.desktop.session import Session
        from seedbank.retrieval import search
        from seedbank.util import read_memories
        from test_memory_evolution import FixedBrain
        marker = "群里的青禾刚修好了紫色风铃。"
        self.session.bridge._brain = FixedBrain({"reply": "我听到了。", "memory_writes": [
            {"text": marker, "importance": .6, "kind": "conversation", "tags": ["QQ"]}]})
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_group.return_value = {"retcode": 0, "status": "ok"}
        event = group_event(456, 888)
        event["message"] = "[CQ:at,qq=999] " + marker
        self.assertTrue(adapter.handle(event)["ok"])
        self.assertTrue(any(row["text"] == marker for row in read_memories(self.pack)))
        original = next(row for row in experience.read(self.pack) if row["text"] == marker)
        self.assertEqual(original["metadata"]["audience_id"], "qq-group:456")
        reopened = Session(self.pack, brain_override="stub")
        try:
            reopened.bridge._brain = self.brain
            reopened.call("message", text="群里谁修好了紫色风铃？")
            self.assertIn(marker, json.dumps(self.brain.context, ensure_ascii=False))
            self.assertIn(marker, json.dumps(reopened.snapshot()["memories"], ensure_ascii=False))
        finally:
            reopened.close()
        same = disclosure.policy_for(self.pack, "qq-group:456", "")
        other = disclosure.policy_for(self.pack, "qq-group:789", "")
        self.assertTrue(search(self.pack, "紫色风铃", policy=same, use_semantic=False))
        self.assertFalse(search(self.pack, "紫色风铃", policy=other, use_semantic=False))

    def test_raw_group_input_remains_recallable_when_model_omits_memory_summary(self):
        from seedbank.retrieval import search
        from seedbank.util import read_memories
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_group.return_value = {"retcode": 0, "status": "ok"}
        marker = "小组约定的测试代号是澄空纸鸢。"
        before = read_memories(self.pack)
        self.assertTrue(adapter.handle(group_event(456, 888, text=marker))["ok"])
        self.assertEqual(read_memories(self.pack), before)
        found = search(self.pack, "澄空纸鸢", use_semantic=False)
        self.assertTrue(any(marker in row["memory"]["text"] for row in found))

    def test_failed_send_is_visible_locally_without_response_body_or_retry(self):
        adapter = self.start_qq()
        adapter.sender = Mock()
        adapter.sender.send_group.return_value = {"status": "failed", "retcode": 100,
                                                  "message": "PRIVATE_SERVER_DETAIL"}
        event = group_event(456, 888)
        self.assertFalse(adapter.handle(event)["ok"])
        self.assertEqual(adapter.diagnostics()["stage"], "send_failed")
        self.assertEqual(adapter.diagnostics()["code"], 100)
        self.assertNotIn("PRIVATE_SERVER_DETAIL", json.dumps(adapter.diagnostics()))
        adapter.handle(event)
        adapter.sender.send_group.assert_called_once()

    def test_ignored_group_and_unrecognized_mentions_have_distinct_local_diagnostics(self):
        adapter = self.start_qq()
        adapter.handle(group_event(789, 888))
        self.assertEqual(adapter.diagnostics()["stage"], "group_not_allowed")
        adapter.handle(group_event(456, 888, at=False))
        self.assertEqual(adapter.diagnostics()["stage"], "not_mentioned")

    def test_connection_check_requires_real_login_receipt_not_empty_or_failed_data(self):
        for receipt in ({}, {"status": "ok", "retcode": 0, "data": {}},
                        {"status": "failed", "retcode": 100, "data": {"user_id": 999}}):
            with patch.object(qq.OneBotSender, "action", return_value=receipt):
                self.assertFalse(qq.test_connection()["ok"])
        with patch.object(qq.OneBotSender, "action", return_value={
                "status": "ok", "retcode": 0, "data": {"user_id": 999, "nickname": "fixture"}}):
            self.assertTrue(qq.test_connection()["ok"])
