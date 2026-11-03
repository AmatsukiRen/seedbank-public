"""QQ 载体（OneBot v11）—— 让 QQ 成为她的一扇窗。

这是「内置版」：不需要 `seed bridge` 子进程，直接在当前进程里用 `Bridge`
和生命包说话。既可以被 `seed qq` 命令启动，也可以被设置页（窗口）调起。

设计规则（见 docs/03-extending.md、spec/channel.md）：
- 适配器不直接写生命包，只通过 Bridge 说「她说了什么」；
- 图片通过桥先保存原件与接收请求，再解释；临时下载文件可在桥返回后清理；
- 默认「主人」私聊才说话；群聊必须 @ 她，且群要在白名单里；
- token 只从环境变量或设置里读，不写进生命包。

它不登录 QQ：QQ 那一侧由第三方 OneBot 实现（SnowLuma / NapCat /
LLOneBot / Lagrange …）负责，我们只对接 OneBot v11 的 HTTP API 与 HTTP 上报。
"""
from __future__ import annotations

import json
import hmac
import os
import queue
import re
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .i18n import t
from .util import SeedError, canonical_json, expand_home, sha256

MAX_TEXT = 2000
MAX_EVENT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 40 * 1024 * 1024
DEFAULT_ONEBOT_HTTP = "http://127.0.0.1:3001"
DEFAULT_QQ_PORT = 8790
DEFAULT_SECRET_ENV = "SEEDBANK_ONEBOT_SECRET"


def secret_env(config) -> str:
    name = str(config.get("secret_env") or DEFAULT_SECRET_ENV).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", name):
        raise ValueError(t("请填写上报签名密钥的环境变量名，不要填写密钥本身。"))
    return name


def inbound_secret(config) -> str:
    value = os.environ.get(secret_env(config), "")
    if not value:
        raise ValueError(t("未设置 QQ 上报签名密钥。请设置对应环境变量，并在 OneBot HTTP 上报中填写相同的 secret。"))
    return value


# —— 消息解析（纯函数，方便测试） ——

_CQ = re.compile(r"\[CQ:([A-Za-z0-9_.-]+)((?:,[^\[\]]*)?)\]")


def _cq_unescape(value, *, parameter=False):
    if parameter:
        value = value.replace("&#44;", ",")
    # Decode ampersands last and never reparse decoded text as CQ markup.
    return value.replace("&#91;", "[").replace("&#93;", "]").replace("&amp;", "&")


def message_segments(message):
    """Normalize both OneBot v11 message formats; arrays already hold raw text."""
    if isinstance(message, list):
        return [{"type": row["type"], "data": row.get("data") or {}} for row in message
                if isinstance(row, dict) and isinstance(row.get("type"), str)
                and (row.get("data") is None or isinstance(row.get("data"), dict))]
    if not isinstance(message, str):
        return []
    rows, offset = [], 0

    def text(value):
        if value:
            rows.append({"type": "text", "data": {"text": _cq_unescape(value)}})

    for match in _CQ.finditer(message):
        text(message[offset:match.start()])
        params, valid = {}, True
        for part in match[2][1:].split(",") if match[2] else []:
            key, separator, value = part.partition("=")
            if not separator or not re.fullmatch(r"[A-Za-z0-9_.-]+", key) or key in params:
                valid = False
                break
            params[key] = _cq_unescape(value, parameter=True)
        if valid:
            rows.append({"type": match[1], "data": params})
        else:
            text(match[0])
        offset = match.end()
    text(message[offset:])
    return rows

def extract_text(segments) -> str:
    """把 OneBot 消息段里的纯文字拼起来（忽略 @、图片、表情）。"""
    parts = []
    for segment in message_segments(segments):
        if not isinstance(segment, dict):
            continue
        if segment.get("type") == "text":
            data = segment.get("data") or {}
            parts.append(data.get("text") if isinstance(data.get("text"), str) else "")
    return "".join(parts).strip()


def find_images(segments) -> list[dict]:
    images = []
    for segment in message_segments(segments):
        if isinstance(segment, dict) and segment.get("type") == "image":
            data = segment.get("data") or {}
            url = data.get("url") or data.get("file") or ""
            if url:
                images.append({"url": str(url)})
    return images


def mentioned(segments, self_id) -> bool:
    self_id = str(self_id or "")
    if not self_id:
        return False
    for segment in message_segments(segments):
        if not isinstance(segment, dict) or segment.get("type") != "at":
            continue
        data = segment.get("data") or {}
        if str(data.get("qq") or "") == self_id:
            return True
    return False


def decide(event: dict, *, owner: str, groups=None, self_id: str = "") -> dict:
    """决定这条事件该怎么处理。返回值是可测试的纯数据。"""
    groups = [str(g) for g in (groups or [])]
    if event.get("post_type") != "message":
        return {"action": "ignore", "reason": t("不是消息事件")}

    message_type = event.get("message_type")
    user_id = str(event.get("user_id") or "")
    segments = message_segments(event.get("message"))
    text = extract_text(segments)[:MAX_TEXT]
    images = find_images(segments)

    if message_type == "private":
        if not owner or user_id != str(owner):
            return {"action": "ignore", "reason": t("不是主人")}
        if not text and not images:
            return {"action": "ignore", "reason": t("空消息")}
        return {
            "action": "sense" if images else "chat",
            "speaker": "主人",
            "text": text,
            "images": [item["url"] for item in images],
            "target": "private",
            "user_id": user_id,
        }

    if message_type == "group":
        group_id = str(event.get("group_id") or "")
        if group_id not in groups:
            # 白名单为空 = 不回应任何群（和设置页「不填 = 不回应群聊」一致）
            return {"action": "ignore", "reason": t("群不在白名单里"), "reason_code": "group_not_allowed"}
        if not mentioned(segments, self_id or event.get("self_id")):
            return {"action": "ignore", "reason": t("没有 @ 她"), "reason_code": "not_mentioned"}
        if not text and not images:
            text = t("（对方在群里 @ 了你，没有附带文字。）")
        return {
            "action": "sense" if images else "chat",
            "speaker": "访客",
            "text": text,
            "images": [item["url"] for item in images],
            "target": "group",
            "user_id": user_id,
            "group_id": group_id,
        }

    return {"action": "ignore", "reason": t("不处理的消息类型：{kind}", kind=message_type)}


# —— 进程内载体桥 ——

class BridgeClient:
    """在当前进程里和生命包说话（不启子进程）。"""

    def __init__(self, pack_dir, brain_override: str = ""):
        from .bridge import Bridge  # 延迟导入，避免循环

        self._bridge = Bridge(str(pack_dir), brain_override)
        self._lock = threading.Lock()
        self._seq = 0

    @property
    def name(self) -> str:
        return self._bridge.name

    def call(self, op: str, **fields) -> dict:
        with self._lock:
            self._seq += 1
            request = {"id": self._seq, "op": op}
            request.update(fields)
            response = self._bridge.handle(request)
            if not response.get("ok"):
                raise RuntimeError(str(response.get("error") or t("载体桥返回错误")))
            return response

    def close(self) -> None:
        return None


class SubprocessBridge:
    """兼容旧适配器：用 stdin/stdout 上的 JSONL 和 `seed bridge` 说话。"""

    def __init__(self, pack_dir, seed_py: Path | None = None, python: str = ""):
        import subprocess

        seed_py = Path(seed_py or default_seed_py())
        if not seed_py.is_file():
            raise RuntimeError(t("找不到 tools/seed/seed.py：{path}", path=seed_py))
        self._lock = threading.Lock()
        self._seq = 0
        command = [python or sys.executable, str(seed_py), "bridge", str(pack_dir)]
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(seed_py.parents[2]),
        )

    def call(self, op: str, **fields) -> dict:
        with self._lock:
            self._seq += 1
            request = {"id": self._seq, "op": op}
            request.update(fields)
            if self._proc.poll() is not None:
                raise RuntimeError(t("载体桥已经退出了"))
            self._proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(t("载体桥没有回应"))
            response = json.loads(line)
            if not response.get("ok"):
                raise RuntimeError(str(response.get("error") or t("载体桥返回错误")))
            return response

    def close(self) -> None:
        with self._lock:
            if self._proc.poll() is None:
                try:
                    self._proc.stdin.write('{"id":0,"op":"stop"}\n')
                    self._proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    self._proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    pass
            for stream in (self._proc.stdin, self._proc.stdout):
                try:
                    stream.close()
                except (AttributeError, OSError):
                    pass


def default_seed_py() -> Path:
    # tools/seed/seedbank/qq.py → tools/seed/seed.py
    return Path(__file__).resolve().parents[1] / "seed.py"


# —— OneBot HTTP 发送端 ——

class OneBotSender:
    """通过 OneBot v11 的 HTTP API 发消息。"""

    def __init__(self, base_url: str = DEFAULT_ONEBOT_HTTP, token: str = "", timeout: float = 20.0):
        self.base_url = (base_url or DEFAULT_ONEBOT_HTTP).rstrip("/")
        self.token = str(token or "")
        self.timeout = timeout

    def action(self, action: str, params: dict) -> dict:
        data = json.dumps(params, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.base_url + "/" + action, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def send_private(self, user_id: str, text: str) -> dict:
        return self.action("send_private_msg", {
            "user_id": int(user_id),
            "message": [{"type": "text", "data": {"text": text}}],
        })

    def send_group(self, group_id: str, text: str, at_user: str = "") -> dict:
        message = []
        if at_user:
            message.append({"type": "at", "data": {"qq": str(at_user)}})
            message.append({"type": "text", "data": {"text": " "}})
        message.append({"type": "text", "data": {"text": text}})
        return self.action("send_group_msg", {"group_id": int(group_id), "message": message})


class ConsoleSender:
    """`--once` 模式用：不连真的 QQ，直接把回复打到终端。"""

    def send_private(self, user_id: str, text: str) -> dict:
        print(f"[qq→{user_id}] {text}", flush=True)
        return {"ok": True}

    def send_group(self, group_id: str, text: str, at_user: str = "") -> dict:
        print(f"[qq→{t('群')}{group_id} @{at_user}] {text}", flush=True)
        return {"ok": True}


# —— 连接测试 ——

def test_connection(base_url: str = "", token: str = "", timeout: float = 4.0) -> dict:
    """问 OneBot 实现「你是谁」。返回 {ok, user_id, nickname, error}。"""
    url = (base_url or DEFAULT_ONEBOT_HTTP).rstrip("/")
    sender = OneBotSender(url, token, timeout=timeout)
    try:
        result = sender.action("get_login_info", {})
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "base_url": url}
    data = result.get("data") if isinstance(result, dict) else None
    if (isinstance(result, dict) and result.get("status") == "ok" and result.get("retcode") == 0
            and isinstance(data, dict) and str(data.get("user_id") or "").isdigit()):
        return {
            "ok": True,
            "base_url": url,
            "user_id": str(data.get("user_id") or ""),
            "nickname": str(data.get("nickname") or ""),
        }
    if isinstance(result, dict) and result.get("retcode") not in (0, None):
        return {"ok": False, "error": str(result.get("message") or result), "base_url": url}
    return {"ok": False, "base_url": url, "error": t("OneBot 未返回有效登录信息，不能确认 QQ 已连接。")}


# —— 适配器本体 ——

class QQAdapter:
    def __init__(self, pack_dir, owner: str, groups=None, *, bridge=None, sender=None,
                 self_id: str = "", log=None):
        self.pack_dir = str(expand_home(pack_dir))
        self.owner = str(owner or "")
        self.groups = [str(g) for g in (groups or [])]
        self.self_id = str(self_id or "")
        self.bridge = bridge
        self.sender = sender
        self.log = log or (lambda message: print(f"[qq] {message}", flush=True))
        self._owns_bridge = bridge is None
        self._stopped = threading.Event()
        self._delivery_lock = threading.RLock()
        self._received = self._sent = self._failed = 0
        self._last_stage, self._last_code = "waiting", None

    def runtime_status(self):
        return {"state": "stopped" if self._stopped.is_set() else "listening",
                "received": self._received, "sent": self._sent, "failed": self._failed}

    def diagnostics(self):
        return {**self.runtime_status(), "stage": self._last_stage, "code": self._last_code}

    def _stage(self, value, code=None):
        self._last_stage = value
        self._last_code = code if type(code) is int else None

    def _get_bridge(self):
        if self.bridge is None:
            self.bridge = BridgeClient(self.pack_dir)
        return self.bridge

    def _get_sender(self):
        if self.sender is None:
            self.sender = OneBotSender(
                os.environ.get("SEEDBANK_ONEBOT_HTTP", DEFAULT_ONEBOT_HTTP),
                os.environ.get("SEEDBANK_ONEBOT_TOKEN", ""),
            )
        return self.sender

    def _download(self, url: str) -> Path:
        request = urllib.request.Request(url)
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise RuntimeError(t("照片太大了"))
        suffix = _image_suffix(data)
        temp_dir = Path(tempfile.mkdtemp(prefix="seedbank-qq-"))
        path = temp_dir / f"image{suffix}"
        path.write_bytes(data)
        return path

    def handle(self, event: dict) -> dict:
        from .runtime_self import incoming
        with incoming(self.pack_dir, "qq", self.runtime_status):
            return self._handle(event)

    def _handle(self, event: dict) -> dict:
        from .lifecycle import active
        if self._stopped.is_set() or not active(self.pack_dir):
            return {"ok": True, "action": "ignore", "reason": "dormant"}
        if self.self_id and str(event.get("self_id") or "") != self.self_id:
            self._stage("wrong_account")
            return {"ok": True, "action": "ignore", "reason": "different_account"}
        decision = decide(event, owner=self.owner, groups=self.groups,
                          self_id=self.self_id or str(event.get("self_id") or ""))
        if decision["action"] == "ignore":
            if decision.get("reason_code"):
                self._stage(decision["reason_code"])
            self.log(t("忽略：{reason}", reason=decision.get("reason")))
            return {"ok": True, **decision}
        message_id = event.get("message_id")
        account = self.self_id or str(event.get("self_id") or "")
        if (not account or not isinstance(message_id, (int, str)) or
                isinstance(message_id, bool) or not str(message_id).strip()):
            return {"ok": True, "action": "ignore", "reason": "missing_message_id"}
        identity = sha256(canonical_json({
            "account": account, "target": decision["target"],
            "group": decision.get("group_id", ""), "user": decision["user_id"], "message": str(message_id)}))
        request_id = "qq_event_" + identity
        from .channels import Journal
        journal = Journal(self.pack_dir)
        if not journal.claim(request_id):
            return {"ok": True, "action": "ignore", "reason": "duplicate"}
        self._received += 1
        self._stage("generating")
        sending = False
        try:
            bridge = self._get_bridge()
            sender = self._get_sender()
            delivery = {"person_id": "owner" if decision["target"] == "private" else "",
                        "audience_id": "owner" if decision["target"] == "private" else "qq-group:" + decision["group_id"]}
            if decision["images"]:
                # Preserve pre-upgrade media receipt identifiers.
                media_id = "qq_media_" + identity
                result = bridge.call("media", action="probe_intake", request_id=media_id,
                    expected={"slots": ["image"], "note": decision["text"] or "", "vision": None, **delivery})
                if not result.get("found"):
                    image_url = decision["images"][0]
                    path = self._download(image_url)
                    try:
                        result = bridge.call("image", path=str(path), note=decision["text"] or None, request_id=media_id, **delivery)
                    finally:
                        for leftover in path.parent.glob("*"):
                            leftover.unlink(missing_ok=True)
                        path.parent.rmdir()
                reply = "；".join(result.get("lines") or []) or t("（她感觉到了什么，但说不出来）")
            else:
                result = bridge.call("message", text=decision["text"], speaker=decision["speaker"], request_id=request_id, **delivery)
                reply = str(result.get("reply") or "")
            from .pack_lock import writer
            with self._delivery_lock, writer(self.pack_dir):
                # A pause may have been confirmed while an earlier reply was
                # being prepared. Do not send that reply after dormancy begins.
                if self._stopped.is_set() or not active(self.pack_dir):
                    self._stage("cancelled")
                    journal.finish(request_id, "cancelled")
                    return {"ok": True, "action": "ignore", "reason": "dormant"}
                journal.finish(request_id, "sending")
                sending = True
                self._stage("sending")
                if decision["target"] == "private":
                    receipt = sender.send_private(decision["user_id"], reply)
                else:
                    receipt = sender.send_group(decision["group_id"], reply, at_user=decision["user_id"])
                if not isinstance(receipt, dict) or receipt.get("retcode") != 0 or receipt.get("status") != "ok":
                    self._failed += 1
                    self._stage("send_failed", receipt.get("retcode") if isinstance(receipt, dict) else None)
                    journal.finish(request_id, "delivery_failed")
                    return {"ok": False, "action": decision["action"], "error": t("QQ 回复发送失败；未自动重试。")}
                journal.finish(request_id, "delivered")
                self._sent += 1
                self._stage("sent")
            self.log(t("回复 {target} {who}：{reply}", target=decision["target"],
                       who=decision.get("group_id") or decision["user_id"], reply=reply[:40]))
            return {"ok": True, "action": decision["action"], "reply": reply}
        except (RuntimeError, OSError, ValueError, KeyError, SeedError) as exc:
            self._failed += 1
            self._stage("send_unknown" if sending else "generation_failed", getattr(exc, "code", None))
            journal.finish(request_id, "delivery_unknown" if sending else "failed")
            self.log(t("这一条没能处理：{error}", error=exc))
            return {"ok": False, "action": decision["action"], "error": str(exc)}

    def close(self) -> None:
        # A confirmed stop waits for an already-started send, and prevents any
        # new send after it returns. Generation does not hold this lock.
        with self._delivery_lock:
            self._stopped.set()
        if self._owns_bridge and self.bridge is not None and hasattr(self.bridge, "close"):
            self.bridge.close()


def diagnostic_text(row):
    labels = {
        "waiting": "本机接收服务已启动；等待消息，尚不能据此确认 QQ 在线。",
        "group_not_allowed": "收到群消息，但该群不在白名单；检查后保存并重新启动连接。",
        "not_mentioned": "收到群消息，但没有识别到对本账号的 @。",
        "wrong_account": "上报账号与设置中的 QQ 号不一致。",
        "generating": "消息已交给当前个体，正在生成回复。",
        "sending": "回复已生成，正在发送到 QQ。",
        "sent": "OneBot 已确认本次回复发送成功。",
        "send_failed": "QQ 拒绝发送回复；请检查群禁言、权限和 OneBot 服务。未自动重发。",
        "send_unknown": "QQ 发送结果未确认；请检查 OneBot 地址、令牌和网络。未自动重发。",
        "generation_failed": "消息处理未完成；请检查模型设置与未完成请求。尚未发送回复。",
        "cancelled": "回复已取消：个体已休眠或连接已停止。",
    }
    text = t(labels.get(row.get("stage"), labels["waiting"]))
    if type(row.get("code")) is int:
        text += " " + t("错误码：{code}", code=row["code"])
    return t("交给个体 {received} 条 · 回复成功 {sent} 条 · 失败 {failed} 条",
             received=row.get("received", 0), sent=row.get("sent", 0), failed=row.get("failed", 0)) + "\n" + text


def _image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data.startswith(b"BM"):
        return ".bmp"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


# —— 接收 OneBot 上行事件的 HTTP 服务 ——

class _EventDispatcher:
    """One ordered daemon worker and a bounded queue; no thread per event."""
    def __init__(self, adapter, capacity=32):
        self.adapter = adapter
        self.pending = queue.Queue(maxsize=capacity)
        self.stopped = threading.Event()
        self.worker = threading.Thread(target=self._run, name="seedbank-qq-events", daemon=True)
        self.worker.start()

    def submit(self, event):
        if self.stopped.is_set():
            return False
        try:
            self.pending.put_nowait(event)
            return True
        except queue.Full:
            return False

    def _run(self):
        while not self.stopped.is_set():
            try:
                event = self.pending.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                if not self.stopped.is_set():
                    self.adapter.handle(event)
            except Exception:
                self.adapter.log(t("QQ 消息处理失败；未自动重试。"))
            finally:
                self.pending.task_done()

    def close(self):
        self.stopped.set()
        self.adapter.close()
        while True:
            try:
                self.pending.get_nowait()
                self.pending.task_done()
            except queue.Empty:
                break


class _IMServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 的 SO_REUSEADDR 允许同端口二次 bind（会静默起两个写者），
    # 所以这里在 Windows 上关掉，让端口占用真的报错。
    allow_reuse_address = os.name != "nt"

    def __init__(self, address, adapter: QQAdapter, *, secret=None):
        value = inbound_secret({}) if secret is None else secret
        if not value:
            raise ValueError(t("QQ 上报签名密钥不能为空。"))
        self.secret = str(value).encode("utf-8")
        self.adapter = adapter
        self.dispatcher = None
        self._http_slots = threading.BoundedSemaphore(8)
        super().__init__(address, _IMHandler)
        try:
            self.dispatcher = _EventDispatcher(adapter)
        except Exception:
            self.server_close()
            raise

    def submit_event(self, event):
        return self.dispatcher.submit(event)

    def process_request(self, request, client_address):
        if not self._http_slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._http_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._http_slots.release()

    def server_close(self):
        if self.dispatcher is not None:
            self.dispatcher.close()
        super().server_close()


class _IMHandler(BaseHTTPRequestHandler):
    server_version = "SeedbankQQ"
    timeout = 15  # 慢客户端别一直占着线程

    def _ok(self, status=204, body: bytes = b""):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/health"):
            self._ok(200, json.dumps({
                "ok": True,
                "adapter": "qq-onebot",
                "protocol": "onebot/v11",
            }).encode("utf-8"))
        else:
            self._ok(404)

    def do_POST(self):
        signature = self.headers.get("X-Signature", "")
        if not signature:
            self._ok(401)
            self.close_connection = True
            return
        if self.headers.get("Transfer-Encoding"):
            self._ok(400)
            self.close_connection = True
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            self._ok(400)
            return
        if length < 0 or length > MAX_EVENT_BYTES:
            self._ok(413)
            self.close_connection = True
            return
        try:
            raw = self.rfile.read(length) if length else b""
            expected = "sha1=" + hmac.new(self.server.secret, raw, "sha1").hexdigest()
            if len(raw) != length or not hmac.compare_digest(signature.encode("utf-8"), expected.encode("ascii")):
                self._ok(403)
                self.close_connection = True
                return
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (OSError, ValueError, UnicodeDecodeError):
            self._ok(400)
            self.close_connection = True
            return
        event = payload.get("event") if isinstance(payload, dict) and "event" in payload else payload
        if not isinstance(event, dict):
            self._ok(400)
            return
        if not self.server.submit_event(event):
            self._ok(503)
            return
        self._ok(204)

    def log_message(self, fmt, *args):
        return


def serve(adapter: QQAdapter, host: str = "127.0.0.1", port: int = DEFAULT_QQ_PORT, *, secret=None) -> int:
    server = _IMServer((host, port), adapter, secret=secret)
    print(t("[qq] 她的 QQ 窗口起来了：{host}:{port}", host=host, port=port))
    print(t("[qq] 在 OneBot 实现（SnowLuma / NapCat / LLOneBot / Lagrange 等）里配置「HTTP 上报」到：http://{host}:{port}/", host=host, port=port))
    print(t("[qq] 只有主人在私聊里说话；群聊必须 @ 她，且要在白名单里。"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        adapter.close()
    print(t("\n[qq] QQ 窗口关上了。她还在她的文件夹里。"))
    return 0


def parse_groups(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").replace("，", ",").split(",") if item.strip()]


def config_defaults() -> dict:
    """从 ~/.seedbank/config.json 的 qq 段读默认配置（缺失返回空）。"""
    try:
        from .onboarding import load_config

        qq = load_config().get("qq")
        return {k: v for k, v in qq.items() if k not in ("token", "secret")} if isinstance(qq, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_config(patch: dict) -> dict:
    """把 QQ 配置并存进 ~/.seedbank/config.json（凭据永不落盘）。

    token 是凭据，只能来自 `--token` 或环境变量 `SEEDBANK_ONEBOT_TOKEN`；
    上报密钥来自配置指定的环境变量。这里只保存允许的设置与变量名。
    """
    from .onboarding import load_config, save_config as _save

    current = load_config().get("qq")
    merged = dict(current) if isinstance(current, dict) else {}
    for key, value in (patch or {}).items():
        if key not in {"pack", "owner", "groups", "self_id", "onebot_http", "port", "secret_env"}:
            continue
        if value in (None, ""):
            merged.pop(key, None)
        else:
            merged[key] = value
    merged.pop("token", None)
    merged.pop("secret", None)
    merged["secret_env"] = secret_env(merged)
    _save({"qq": merged})
    return merged


def run_from_args(args) -> int:
    """给 cli.py 的 `seed qq` 用。"""
    defaults = config_defaults()
    pack = args.pack or defaults.get("pack") or ""
    owner = str(args.owner or defaults.get("owner") or "")
    groups = parse_groups(args.groups if args.groups is not None else defaults.get("groups"))
    onebot_http = args.onebot_http or defaults.get("onebot_http") or DEFAULT_ONEBOT_HTTP
    token = args.token or os.environ.get("SEEDBANK_ONEBOT_TOKEN", "")
    port = int(args.port if args.port is not None else (defaults.get("port") or DEFAULT_QQ_PORT))
    self_id = str(args.self_id or defaults.get("self_id") or "")
    signing_config = {"secret_env": getattr(args, "secret_env", "") or defaults.get("secret_env")}

    if args.test:
        result = test_connection(onebot_http, token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if not pack:
        raise SeedError(t("需要 --pack <生命包目录>（或在配置里设置 qq.pack）"))
    if not Path(expand_home(pack)).is_dir():
        raise SeedError(t("生命包不存在：{path}", path=pack))
    if not owner:
        raise SeedError(t("需要 --owner <主人QQ号>（私聊只回主人）"))

    os.environ["SEEDBANK_ONEBOT_HTTP"] = onebot_http
    os.environ["SEEDBANK_ONEBOT_TOKEN"] = token
    adapter = QQAdapter(
        expand_home(pack), owner, groups, self_id=self_id,
        sender=ConsoleSender() if args.once else None,
    )
    if args.once:
        result = adapter.handle({
            "post_type": "message",
            "message_type": "private",
            "user_id": int(owner) if owner.isdigit() else 0,
            "self_id": self_id or "offline",
            "message_id": __import__("uuid").uuid4().hex,
            "message": [{"type": "text", "data": {"text": args.once}}],
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        adapter.close()
        return 0 if result.get("ok") else 1
    try:
        return serve(adapter, args.host, port, secret=inbound_secret(signing_config))
    finally:
        adapter.close()

# —— 独立入口（兼容旧的 adapters/qq-onebot/qq_onebot.py） ——

def main(argv: list[str] | None = None) -> int:
    """命令行入口：python qq_onebot.py --pack ... --owner ...

    真正的参数解析在 adapters 兼容层；这里只做最小实现，
    方便 `python tools/seed/seedbank/qq.py` 直接跑。
    """
    import argparse

    parser = argparse.ArgumentParser(description=t("Seedbank QQ 载体适配器（OneBot v11）"))
    parser.add_argument("--pack", default=os.environ.get("SEEDBANK_PACK", ""))
    parser.add_argument("--owner", default=os.environ.get("SEEDBANK_OWNER", ""))
    parser.add_argument("--groups", default=os.environ.get("SEEDBANK_GROUPS", ""))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SEEDBANK_QQ_PORT", str(DEFAULT_QQ_PORT))))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--onebot-http", default=os.environ.get("SEEDBANK_ONEBOT_HTTP", DEFAULT_ONEBOT_HTTP))
    parser.add_argument("--token", default=os.environ.get("SEEDBANK_ONEBOT_TOKEN", ""))
    parser.add_argument("--secret-env", default="", help=t("上报签名密钥的环境变量名（默认 SEEDBANK_ONEBOT_SECRET）"))
    parser.add_argument("--self-id", default=os.environ.get("SEEDBANK_QQ_SELF_ID", ""))
    parser.add_argument("--once", default="", help=t("只处理一句话就退出（用于测试）"))
    parser.add_argument("--test", action="store_true", help=t("只测试 OneBot 连接"))
    args = parser.parse_args(argv)

    # 用同一套默认值逻辑
    args.groups = _split_groups_arg(args.groups)
    return run_from_args(args)


def _split_groups_arg(value: str) -> list[str]:
    return parse_groups(value)


if __name__ == "__main__":
    raise SystemExit(main())
