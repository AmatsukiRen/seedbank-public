"""Authenticated HTTP intake and durable delivery, with no sockets or services."""
import hashlib
import hmac
import io
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from seedbank import qq
from seedbank.pack import hatch


def event(**patch):
    return {"post_type": "message", "message_type": "private", "self_id": 999,
            "user_id": 123, "message_id": 501,
            "message": [{"type": "text", "data": {"text": "人工消息"}}], **patch}


class IntakeTest(unittest.TestCase):
    def post(self, body, signature=None, *, accepted=True, **headers):
        handler = object.__new__(qq._IMHandler)
        handler.rfile = io.BytesIO(body)
        handler.headers = {"Content-Length": str(len(body)), **headers}
        if signature is not None:
            handler.headers["X-Signature"] = signature
        handler.path = "/"
        handler._ok = mock.Mock()
        adapter = mock.Mock()
        handler.server = SimpleNamespace(adapter=adapter, secret=b"artificial-secret",
            submit_event=lambda value: (adapter.handle(value) or True) if accepted else False)
        # Exercise the old dispatch too: starting a thread runs the fake adapter inline.
        with mock.patch.object(qq.threading, "Thread", side_effect=lambda target, args, **kw:
                               SimpleNamespace(start=lambda: target(*args))):
            handler.do_POST()
        return handler, adapter

    def sign(self, body):
        return "sha1=" + hmac.new(b"artificial-secret", body, hashlib.sha1).hexdigest()

    def test_unsigned_owner_event_is_rejected_before_dispatch(self):
        handler, adapter = self.post(json.dumps(event()).encode())
        self.assertEqual(handler._ok.call_args.args[0], 401)
        adapter.handle.assert_not_called()

    def test_wrong_signature_and_changed_body_are_rejected(self):
        body = json.dumps(event()).encode()
        for signature, value in (("sha1=bad", body), (self.sign(body), body + b" ")):
            with self.subTest(signature=signature):
                handler, adapter = self.post(value, signature)
                self.assertEqual(handler._ok.call_args.args[0], 403)
                adapter.handle.assert_not_called()

    def test_valid_raw_body_signature_accepts_event(self):
        body = json.dumps(event(), ensure_ascii=False).encode()
        handler, adapter = self.post(body, self.sign(body))
        self.assertEqual(handler._ok.call_args.args[0], 204)
        adapter.handle.assert_called_once_with(event())

    def test_full_queue_returns_retryable_503_without_dispatch(self):
        body = json.dumps(event()).encode()
        handler, adapter = self.post(body, self.sign(body), accepted=False)
        self.assertEqual(handler._ok.call_args.args[0], 503)
        adapter.handle.assert_not_called()

    def test_malformed_json_and_event_are_not_dispatched(self):
        for body in (b"{", b"[]", b'{"event":null}'):
            handler, adapter = self.post(body, self.sign(body))
            self.assertEqual(handler._ok.call_args.args[0], 400)
            adapter.handle.assert_not_called()

    def test_oversize_and_chunked_requests_are_rejected(self):
        body = b"{}"
        for headers, expected in (({"Content-Length": str(qq.MAX_EVENT_BYTES + 1)}, 413),
                                  ({"Transfer-Encoding": "chunked"}, 400)):
            handler, adapter = self.post(body, self.sign(body), **headers)
            self.assertEqual(handler._ok.call_args.args[0], expected)
            adapter.handle.assert_not_called()


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="seedbank-qq-security-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        patch = mock.patch.dict(os.environ, {"HOME": tmp.name, "USERPROFILE": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.pack = self.home / "artificial.life"
        hatch(self.pack, Path(__file__).resolve().parents[2] / "eggs/open.egg", "人工个体")
        self.bridge = mock.Mock()
        self.bridge.call.return_value = {"reply": "人工回答"}
        self.sender = mock.Mock()
        self.sender.send_private.return_value = {"status": "ok", "retcode": 0}

    def adapter(self, **kwargs):
        return qq.QQAdapter(self.pack, "123", bridge=self.bridge, sender=self.sender,
                            log=lambda _: None, **kwargs)

    def test_repost_after_reopen_neither_generates_nor_sends_twice(self):
        first = self.adapter().handle(event())
        second = self.adapter().handle(event())
        self.assertTrue(first["ok"])
        self.assertEqual(second.get("reason"), "duplicate")
        self.bridge.call.assert_called_once()
        self.sender.send_private.assert_called_once()
        self.assertTrue(self.bridge.call.call_args.kwargs.get("request_id"))

    def test_missing_message_id_and_wrong_bot_do_not_generate(self):
        self.adapter().handle(event(message_id=None))
        self.adapter(self_id="888").handle(event())
        self.bridge.call.assert_not_called()
        self.sender.send_private.assert_not_called()

    def test_unknown_send_result_is_not_automatically_retried(self):
        self.sender.send_private.side_effect = TimeoutError("artificial timeout")
        self.assertFalse(self.adapter().handle(event())["ok"])
        self.assertEqual(self.adapter().handle(event()).get("reason"), "duplicate")
        self.bridge.call.assert_called_once()
        self.sender.send_private.assert_called_once()

    def test_distinct_accounts_can_share_message_number(self):
        self.adapter().handle(event())
        self.adapter().handle(event(self_id=888))
        self.assertEqual(self.bridge.call.call_count, 2)
        identifiers = {call.kwargs.get("request_id") for call in self.bridge.call.call_args_list}
        self.assertEqual(len(identifiers), 2)

    def test_concurrent_adapters_claim_same_event_only_once(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.adapter().handle(event()), range(12)))
        self.assertEqual(sum(r.get("reason") == "duplicate" for r in results), 11)
        self.bridge.call.assert_called_once()
        self.sender.send_private.assert_called_once()

    def test_explicit_onebot_send_failure_is_not_reported_as_success(self):
        self.sender.send_private.return_value = {"status": "failed", "retcode": 100}
        self.assertFalse(self.adapter().handle(event())["ok"])
        self.assertEqual(self.adapter().handle(event()).get("reason"), "duplicate")
        self.sender.send_private.assert_called_once()

    def test_incomplete_onebot_receipt_is_not_reported_as_success(self):
        for number, receipt in enumerate(({}, {"retcode": 0}, {"status": "ok"}), start=600):
            with self.subTest(receipt=receipt):
                self.sender.send_private.return_value = receipt
                incoming = event(message_id=number)
                self.assertFalse(self.adapter().handle(incoming)["ok"])
                self.assertEqual(self.adapter().handle(incoming).get("reason"), "duplicate")

    def test_stopping_during_generation_prevents_send(self):
        adapter = self.adapter()
        self.bridge.call.side_effect = lambda *a, **kw: (adapter.close() or {"reply": "人工回答"})
        self.assertEqual(adapter.handle(event())["reason"], "dormant")
        self.sender.send_private.assert_not_called()

    def test_config_stores_only_secret_variable_name(self):
        with mock.patch("seedbank.onboarding.config_dir", return_value=self.home / "config"):
            qq.save_config({"owner": "123", "secret": "never-store-this", "token": "never-store-that",
                            "secret_env": "TEST_ONEBOT_SECRET"})
            stored = (self.home / "config/config.json").read_text(encoding="utf-8")
            self.assertNotIn("never-store", stored)
            self.assertIn("TEST_ONEBOT_SECRET", stored)


class ServerBoundsTest(unittest.TestCase):
    def test_empty_secret_cannot_open_a_socket(self):
        with mock.patch.object(qq.ThreadingHTTPServer, "__init__") as bind:
            with self.assertRaises(ValueError):
                qq._IMServer(("127.0.0.1", 0), mock.Mock(), secret="")
            bind.assert_not_called()

    def test_missing_env_secret_cannot_open_a_socket(self):
        with mock.patch.dict(os.environ, {qq.DEFAULT_SECRET_ENV: ""}), \
             mock.patch.object(qq.ThreadingHTTPServer, "__init__") as bind:
            with self.assertRaises(ValueError):
                qq._IMServer(("127.0.0.1", 0), mock.Mock())
            bind.assert_not_called()

    def test_http_worker_limit_rejects_excess_and_releases_on_error(self):
        server = object.__new__(qq._IMServer)
        server._http_slots = threading.BoundedSemaphore(1)
        server.shutdown_request = mock.Mock()
        first, excess = mock.Mock(), mock.Mock()
        with mock.patch.object(qq.ThreadingHTTPServer, "process_request") as start:
            server.process_request(first, ("127.0.0.1", 1))
            server.process_request(excess, ("127.0.0.1", 2))
            start.assert_called_once()
            self.assertIn(b"503", excess.sendall.call_args.args[0])
        with mock.patch.object(qq.ThreadingHTTPServer, "process_request_thread", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                server.process_request_thread(first, ("127.0.0.1", 1))
        self.assertTrue(server._http_slots.acquire(blocking=False))

    def test_queue_is_bounded_and_shutdown_discards_waiting_events(self):
        entered, release = threading.Event(), threading.Event()
        adapter = mock.Mock()
        def blocked(_event):
            entered.set()
            release.wait(3)
        adapter.handle.side_effect = blocked
        dispatcher = qq._EventDispatcher(adapter, capacity=1)
        try:
            self.assertTrue(dispatcher.submit({"id": 1}))
            self.assertTrue(entered.wait(2))
            self.assertTrue(dispatcher.submit({"id": 2}))
            self.assertFalse(dispatcher.submit({"id": 3}))
            dispatcher.close()
            self.assertFalse(dispatcher.submit({"id": 4}))
        finally:
            release.set()
            dispatcher.close()
            dispatcher.worker.join(3)
        self.assertFalse(dispatcher.worker.is_alive())
        adapter.handle.assert_called_once_with({"id": 1})


if __name__ == "__main__":
    unittest.main()
