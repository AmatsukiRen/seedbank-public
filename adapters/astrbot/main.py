"""Explicit /seed routing; no AstrBot LLM or private persona copy."""
import asyncio
import json
import os
import urllib.request

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register("seedbank_bridge", "AmatsukiRen", "Route explicit messages to the local SeedBank individual", "0.0.1")
class SeedBankBridge(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.lock = asyncio.Lock()

    @filter.command("seedid")
    async def identity(self, event: AstrMessageEvent):
        event.stop_event()
        owner = str(event.get_platform_id()) + "/" + str(event.get_sender_id())
        yield event.plain_result("SeedBank 主人账号 ID: " + owner + "\n群/会话 ID: " + event.unified_msg_origin)

    @filter.command("seed")
    async def send_to_seed(self, event: AstrMessageEvent):
        event.stop_event()  # Prevent this input also triggering AstrBot's LLM.
        raw = event.get_message_str().strip()
        # The framework already matched the command; preserve all remaining text.
        parts = raw.split(maxsplit=1)
        text = parts[1].strip() if len(parts) > 1 else ""
        if not text or len(text) > 2000:
            yield event.plain_result("用法：/seed 想说的话（最多 2000 字）")
            return
        sender = str(event.get_platform_id()) + "/" + str(event.get_sender_id())
        if not event.get_sender_id() or event.get_sender_id() == event.get_self_id():
            return
        direct = event.is_private_chat()
        event_id = str(getattr(event.message_obj, "message_id", "") or "")
        if not event_id:
            yield event.plain_result("平台未提供消息 ID；此消息未转交。")
            return
        payload = {"event_id": event_id, "account": str(event.get_platform_id()) + "/" + str(event.get_self_id()),
                   "sender": sender, "chat": event.unified_msg_origin, "text": text,
                   "direct": direct, "mentioned": True, "bot": False}
        # A command is the explicit invocation for AstrBot groups. The host still
        # enforces owner and exact session allowlists before touching the model.
        def request():
            token = os.environ.get(str(self.config.get("token_env", "SEEDBANK_ASTRBOT_TOKEN")), "")
            if not token:
                raise ValueError("Missing local relay token")
            port = int(self.config.get("port", 8791))
            if not 1024 <= port <= 65535:
                raise ValueError("Invalid local relay port")
            req = urllib.request.Request("http://127.0.0.1:" + str(port) + "/v1/message",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")
            with urllib.request.urlopen(req, timeout=600) as response:
                return json.loads(response.read(128 * 1024).decode("utf-8")).get("reply", "")
        try:
            async with self.lock:
                reply = await asyncio.to_thread(request)
            if reply:
                yield event.plain_result(reply)
        except Exception:
            # Timeout may follow a committed turn; do not retry or leak diagnostics.
            yield event.plain_result("SeedBank 转交未确认，请在桌面查看连接状态与未完成请求；不会自动重试。")
