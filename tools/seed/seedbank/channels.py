"""Opt-in chat carriers sharing the desktop Session; never auto-connect."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import queue
import re
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .i18n import t
from .util import read_json, write_json_atomic


PRESETS = [
    {"id": "telegram", "label": "Telegram", "token_env": "SEEDBANK_TELEGRAM_TOKEN", "app_id": "", "self_id": "", "hint": "BotFather Token；主人填写数字用户 ID；群聊仅响应白名单内 @机器人 的文字。"},
    {"id": "discord", "label": "Discord", "token_env": "SEEDBANK_DISCORD_TOKEN", "app_id": "", "self_id": "", "hint": "使用 Bot Token；开启 Message Content Intent；群白名单填写频道 ID。"},
    {"id": "feishu", "label": "飞书", "token_env": "SEEDBANK_FEISHU_SECRET", "app_id": "", "self_id": "", "hint": "企业自建应用，启用机器人与长连接；填写 App ID、机器人 open_id；主人使用 open_id。"},
    {"id": "dingtalk", "label": "钉钉", "token_env": "SEEDBANK_DINGTALK_SECRET", "app_id": "", "self_id": "", "hint": "企业机器人使用 Stream 模式；填写 Client ID；主人使用 senderStaffId，群使用 conversationId。"},
    {"id": "astrbot", "label": "AstrBot", "token_env": "SEEDBANK_ASTRBOT_TOKEN", "app_id": "", "self_id": "", "hint": "安装随包桥接插件，仅同机连接；用 /seedid 查看身份与会话 ID，用 /seed 发送文字。"},
]


def digest(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def config_path(pack):
    return Path.home() / ".seedbank" / "channels" / (digest(str(Path(pack).resolve()).casefold()) + ".json")


def defaults(kind):
    preset = next((p for p in PRESETS if p["id"] == kind), None)
    if preset is None:
        raise ValueError("Unknown chat channel")
    return {key: preset[key] for key in ("id", "token_env", "app_id", "self_id")} | {"owner": "", "groups": "", "port": 8791}


def load_config(pack, kind):
    stored = read_json(config_path(pack), {})
    values = stored.get(kind, {}) if isinstance(stored, dict) else {}
    result = defaults(kind)
    if isinstance(values, dict):
        for key, value in values.items():
            if key in result and key != "id" and (isinstance(value, str) or
                    (key == "port" and type(value) is int)):
                result[key] = value
    return result


def clean_config(config):
    kind = config.get("id")
    result = {k: str(config.get(k, v)).strip() for k, v in defaults(kind).items()}
    if not result["owner"] or len(result["owner"]) > 250:
        raise ValueError(t("请填写平台提供的主人账号 ID，不能使用昵称。"))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", result["token_env"]):
        raise ValueError(t("请填写令牌环境变量名，实际令牌放在该变量中。"))
    if kind in ("feishu", "dingtalk") and not result["app_id"]:
        raise ValueError(t("请填写应用 ID。"))
    if kind == "feishu" and not result["self_id"]:
        raise ValueError(t("请填写机器人的 open_id，用于准确判断群内提及。"))
    try:
        result["port"] = int(result["port"])
        if not 1024 <= result["port"] <= 65535:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(t("端口需要在 1024 到 65535 之间。")) from None
    return result


def save_config(pack, config):
    config = clean_config(config)
    path = config_path(pack)
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data[config["id"]] = config
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, data)
    return config


def route(config, event):
    """A channel event cannot request arbitrary bridge operations or identity."""
    return route_with_reason(config, event)[0]


def route_with_reason(config, event):
    """Return only fixed local reason codes, never private event contents."""
    if not isinstance(event, dict) or event.get("bot") is not False:
        return None, "invalid"
    fields = [event.get(k) for k in ("event_id", "account", "sender", "chat")]
    if not all(isinstance(v, str) and v.strip() for v in fields):
        return None, "invalid"
    text = event.get("text")
    if any(len(v) > 512 for v in fields) or not isinstance(text, str) or len(text) > 2000:
        return None, "invalid"
    direct = event.get("direct") is True
    if not direct and event.get("direct") is not False:
        return None, "invalid"
    owner = event["sender"] == config["owner"]
    groups = {v.strip() for v in str(config.get("groups", "")).split(",") if v.strip()}
    if direct and not owner:
        return None, "not_owner"
    if not direct and event["chat"] not in groups:
        return None, "group_not_allowed"
    if not direct and event.get("mentioned") is not True:
        return None, "not_mentioned"
    text = text.strip()
    if not text:
        if direct or config["id"] == "astrbot":
            return None, "empty"
        text = t("（对方在群里 @ 了你，没有附带文字。）")
    identity = json.dumps([config["id"], event["account"], event["chat"], event["event_id"]], ensure_ascii=False)
    request_id = "channel-" + digest(identity)
    audience = "owner" if direct else "channel:" + config["id"] + ":" + digest(event["account"] + "/" + event["chat"])
    return {"text": text, "speaker": "主人" if owner else config["id"] + ":" + event["sender"],
            "person_id": "owner" if owner else "", "audience_id": audience, "request_id": request_id}, "accepted"


class Journal:
    """Delivery identifiers only; no token, message text, or generated response."""
    def __init__(self, pack):
        self.path = config_path(pack).with_suffix(".sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Connection's context manager handles transactions, but does not close
        # the file handle. Close it after committing/rolling back each operation.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS delivery (id TEXT PRIMARY KEY, state TEXT NOT NULL)")

    def claim(self, identifier):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute("INSERT OR IGNORE INTO delivery VALUES (?, 'processing')", (identifier,)).rowcount == 1

    def finish(self, identifier, state):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE delivery SET state=? WHERE id=?", (state, identifier))


class Connection:
    def __init__(self, session, config):
        self.session, self.config = session, clean_config(config)
        self.journal = Journal(session.pack)
        self.stopped = threading.Event()
        self.process = self.server = None
        self.state = "尚未启动"
        self.stage = "not_started"
        self.received = self.sent = self.failed = self.relayed = 0

    def status(self, stage, text):
        self.stage, self.state = stage, text

    def summary(self):
        running = not self.stopped.is_set() and (self.server is not None or (self.process is not None and self.process.poll() is None))
        row = {"id": self.config["id"], "running": running, "state": t(self.state), "stage": self.stage,
               "received": self.received, "sent": self.sent, "failed": self.failed}
        if self.config["id"] == "astrbot":
            row["relayed"] = self.relayed
        return row

    def exchange(self, event, deliver):
        request, reason = route_with_reason(self.config, event)
        # One Session owns all carriers, including the GUI. The lock also covers
        # delivery so a confirmed pause cannot be followed by a new send.
        with self.session.lock:
            from .lifecycle import active
            if self.stopped.is_set() or self.session.closed or not active(self.session.pack):
                return deliver("")
            if request is None:
                labels = {"not_owner": "私聊账号未绑定为主人；消息未交给个体。",
                          "group_not_allowed": "该群或频道不在白名单；检查后保存并重新启动连接。",
                          "not_mentioned": "收到群消息，但没有识别到对本账号的 @。",
                          "empty": "收到空白文字；消息未交给个体。",
                          "invalid": "消息格式或身份字段不完整；消息未交给个体。"}
                self.status(reason, labels[reason])
                return deliver("")
            if not self.journal.claim(request["request_id"]):
                return deliver("")
            self.received += 1
            self.status("generating", "消息已交给当前个体，正在生成回复。")
            delivery_started = False
            try:
                from .runtime_self import incoming
                with incoming(self.session.pack, self.config["id"]):
                    result = self.session.call("message", **request)
                if self.stopped.is_set() or not active(self.session.pack):
                    self.status("cancelled", "回复已取消：个体已休眠或连接已停止。")
                    self.journal.finish(request["request_id"], "cancelled")
                    return deliver("")
                reply = str(result.get("reply") or "")
                if not reply.strip():
                    self.journal.finish(request["request_id"], "no_reply")
                    self.status("no_reply", "本次未生成可发送的文字；没有发送回复。")
                    return deliver("")
                self.journal.finish(request["request_id"], "sending")
                delivery_started = True
                self.status("sending", "回复已生成，正在提交到聊天渠道。")
                ok = deliver(reply)
                relay = self.config["id"] == "astrbot"
                self.journal.finish(request["request_id"], ("relayed" if relay else "delivered") if ok else "delivery_failed")
                self.sent += bool(ok and not relay)
                self.relayed += bool(ok and relay)
                self.failed += not ok
                if not ok:
                    self.status("delivery_failed", "回复发送失败；未自动重试")
                elif relay:
                    self.status("relayed", "回复已交给 AstrBot；最终平台送达尚未确认。")
                else:
                    self.status("delivered", "平台已确认本次回复发送成功。")
                return ok
            except Exception:
                self.failed += 1
                self.status("delivery_unknown" if delivery_started else "generation_failed",
                            "回复提交结果未确认；未自动重发。" if delivery_started else "消息处理失败；请查看未完成请求")
                self.journal.finish(request["request_id"], "delivery_unknown" if delivery_started else "failed")
                # Do not forward exception details or private context to a group.
                if delivery_started:
                    raise  # Never issue a second send after an uncertain receipt.
                return deliver("")

    def start(self):
        secret = os.environ.get(self.config["token_env"], "").strip()
        if not secret:
            raise ValueError(t("令牌环境变量为空；设置后请重新打开 SeedBank。"))
        self.status("starting", "连接进程已启动")
        if self.config["id"] == "astrbot":
            self._start_relay(secret)
        else:
            command = ([sys.executable, "--channel-worker"] if getattr(sys, "frozen", False)
                       else [sys.executable, "-u", "-m", "seedbank.channel_worker"])
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.process.stdin.write(json.dumps(self.config, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            threading.Thread(target=self._run, name="seedbank-channel-" + self.config["id"], daemon=True).start()

    def _run(self):
        messages = queue.Queue(maxsize=64)
        def reader():
            try:
                for line in self.process.stdout:
                    if len(line) > 32768:
                        break
                    messages.put(json.loads(line))
            except Exception:
                pass
            finally:
                messages.put({"type": "exit"})
        threading.Thread(target=reader, daemon=True).start()
        try:
            while not self.stopped.is_set():
                row = messages.get()
                if row.get("type") == "exit":
                    break
                if row.get("type") == "error":
                    self.status("connection_failed", "渠道连接失败；请核对令牌、权限与网络")
                    self.failed += 1
                    continue
                if row.get("type") != "event":
                    continue
                def deliver(reply):
                    if self.stopped.is_set():
                        return False
                    self.process.stdin.write(json.dumps({"reply": reply}, ensure_ascii=False) + "\n")
                    self.process.stdin.flush()
                    # Child sends exactly one delivery receipt per event, even
                    # for skipped/duplicate events. Missing receipts stop it.
                    result = messages.get(timeout=45)
                    if result.get("type") != "delivery":
                        raise RuntimeError("Missing delivery receipt")
                    if result.get("uncertain") is True:
                        raise RuntimeError("Unconfirmed platform delivery")
                    return result.get("ok") is True
                self.exchange(row.get("event"), deliver)
        except Exception:
            if self.stage != "delivery_unknown":
                self.failed += 1
                self.status("connection_failed", "渠道连接失败；请核对令牌、权限与网络")
        finally:
            if not self.stopped.is_set() and self.stage not in ("connection_failed", "delivery_unknown", "delivery_failed", "generation_failed"):
                self.status("disconnected", "渠道已断开；请检查配置后重新启动")
            self.stop(preserve_status=True)

    def _start_relay(self, secret):
        connection = self
        class Handler(BaseHTTPRequestHandler):
            timeout = 15
            def log_message(self, *_args):
                pass
            def do_POST(self):
                if self.path != "/v1/message" or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + secret):
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 16384:
                        raise ValueError()
                    payload = json.loads(self.rfile.read(size))
                    def deliver(reply):
                        body = json.dumps({"reply": reply}, ensure_ascii=False).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return True  # Relay receipt, not the platform's delivery receipt.
                    connection.exchange(payload, deliver)
                except (ValueError, TypeError):
                    self.send_error(400)
        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = False
        self.server = Server(("127.0.0.1", self.config["port"]), Handler)
        try:
            threading.Thread(target=self.server.serve_forever, name="seedbank-astrbot-relay", daemon=True).start()
        except Exception:
            # shutdown() waits for serve_forever(); do not call it when the
            # thread never started. Release the bound socket directly instead.
            self.server.server_close()
            self.server = None
            raise

    def stop(self, preserve_status=False):
        self.stopped.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.process and self.process.poll() is None:
            self.process.terminate()  # Only the child created by this Connection.
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if not preserve_status:
            self.status("stopped", "已停止连接")


class Manager:
    def __init__(self, session):
        self.session, self.connections = session, {}
        self.lock = threading.RLock()
        self.closed = False

    def start(self, config):
        with self.lock:
            if self.closed or self.session.closed:
                raise ValueError("The room is closed.")
            kind = config["id"]
            old = self.connections.get(kind)
            if old and old.summary()["running"]:
                raise ValueError(t("请先停止该渠道，再修改连接。"))
            connection = Connection(self.session, config)
            self.connections[kind] = connection
            try:
                connection.start()
            except Exception:
                connection.status("connection_failed", "渠道连接失败；请核对令牌、权限与网络")
                try:
                    connection.stop(preserve_status=True)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                raise
            return connection.summary()

    def stop(self, kind):
        with self.lock:
            connection = self.connections.get(kind)
        if connection:
            connection.stop()

    def close(self):
        with self.lock:
            self.closed = True
            connections = list(self.connections.values())
        for connection in connections:
            connection.stop()

    def summaries(self):
        with self.lock:
            connections = list(self.connections.values())
        return [connection.summary() for connection in connections]
