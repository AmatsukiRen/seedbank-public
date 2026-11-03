"""Network-only carrier subprocess. It never opens a life pack or model key."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import re
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit


def post(url, payload, *, timeout=30, headers=None):
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                    headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))


class Bus:
    def __init__(self, source, output):
        self.source, self.output = source, output
        self.lock = threading.Lock()
        self.jobs = queue.Queue(maxsize=32)
        threading.Thread(target=self._consume, daemon=True).start()

    def emit(self, value):
        self.output.write(json.dumps(value, ensure_ascii=False) + "\n")
        self.output.flush()

    def forward(self, event, send):
        with self.lock:
            self.emit({"type": "event", "event": event})
            line = self.source.readline()
            if not line:
                os._exit(0)
            reply = json.loads(line).get("reply", "")
            ok = True
            if reply:
                try:
                    send(reply)
                except Exception:
                    ok = False
            self.emit({"type": "delivery", "ok": ok})

    def enqueue(self, event, send):
        try:
            self.jobs.put_nowait((event, send))
        except queue.Full:
            # No unbounded queue of potentially billable work.
            pass

    def _consume(self):
        while True:
            event, send = self.jobs.get()
            self.forward(event, send)


def telegram_event(update, bot):
    message = update.get("message") or {}
    sender, chat = message.get("from") or {}, message.get("chat") or {}
    text = message.get("text")
    if not isinstance(text, str) or sender.get("is_bot") is not False or chat.get("type") not in ("private", "group", "supergroup"):
        return None
    username = "@" + str(bot.get("username") or "")
    # Telegram entity offsets use UTF-16 code units, not Python character indices.
    mentioned = False
    for entity in message.get("entities", []):
        start, length = entity.get("offset", 0), entity.get("length", 0)
        part = text.encode("utf-16-le")[start * 2:(start + length) * 2].decode("utf-16-le", errors="replace")
        if entity.get("type") == "mention" and part.casefold() == username.casefold():
            mentioned = True
        if entity.get("type") == "text_mention" and str((entity.get("user") or {}).get("id")) == str(bot["id"]):
            mentioned = True
    return {"event_id": str(message.get("message_id") or ""), "account": str(bot["id"]),
            "sender": str(sender.get("id") or ""), "chat": str(chat.get("id") or ""),
            "text": re.sub(re.escape(username) + r"(?![A-Za-z0-9_])", "", text, flags=re.I).strip(),
            "direct": chat["type"] == "private", "mentioned": mentioned, "bot": False}


def run_telegram(config, secret, bus):
    base = "https://api.telegram.org/bot" + secret + "/"
    def api(method, payload, timeout=30):
        data = post(base + method, payload, timeout=timeout)
        if data.get("ok") is not True:
            raise RuntimeError("Telegram API rejected request")
        return data.get("result")
    bot = api("getMe", {})
    if api("getWebhookInfo", {}).get("url"):
        raise RuntimeError("Existing webhook: not changed automatically")
    # Discard old pending updates at explicit startup rather than answer a backlog.
    initial = api("getUpdates", {"offset": -1, "limit": 1, "timeout": 0, "allowed_updates": ["message"]})
    offset = initial[-1]["update_id"] + 1 if initial else 0
    while True:
        updates = api("getUpdates", {"offset": offset, "timeout": 20, "allowed_updates": ["message"]}, timeout=30)
        for update in updates:
            offset = update["update_id"] + 1
            event = telegram_event(update, bot)
            if not event:
                continue
            topic = (update.get("message") or {}).get("message_thread_id")
            def send(reply, event=event, topic=topic):
                for start in range(0, len(reply), 1800):
                    payload = {"chat_id": event["chat"], "text": reply[start:start + 1800],
                               "link_preview_options": {"is_disabled": True}}
                    if topic:
                        payload["message_thread_id"] = topic
                    api("sendMessage", payload)
            bus.forward(event, send)


def run_discord(config, secret, bus):
    import discord
    intents = discord.Intents.none()
    intents.guilds = intents.guild_messages = intents.dm_messages = intents.message_content = True
    client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())
    @client.event
    async def on_message(message):
        if message.author.bot or message.webhook_id or not message.content:
            return
        direct = isinstance(message.channel, discord.DMChannel)
        if message.guild is None and not direct:
            return  # A group DM must never get owner-private context.
        identifier = str(client.user.id)
        event = {"event_id": str(message.id), "account": identifier,
                 "sender": str(message.author.id), "chat": str(message.channel.id),
                 "direct": direct, "mentioned": client.user in message.mentions, "bot": False,
                 "text": re.sub(r"<@!?" + identifier + r">", "", message.content).strip()}
        loop = asyncio.get_running_loop()
        async def reply_chunks(reply):
            for start in range(0, len(reply), 1800):
                await message.channel.send(reply[start:start + 1800], allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)
        def send(reply):
            asyncio.run_coroutine_threadsafe(reply_chunks(reply), loop).result(timeout=35)
        bus.enqueue(event, send)
    client.run(secret, log_handler=None)


def feishu_event(data, config):
    event = data.get("event") or {}
    sender, message = event.get("sender") or {}, event.get("message") or {}
    if sender.get("sender_type") != "user" or message.get("message_type") != "text" or message.get("chat_type") not in ("p2p", "group"):
        return None
    text = json.loads(message.get("content") or "{}").get("text", "")
    mentioned = False
    for mention in message.get("mentions") or []:
        if (mention.get("id") or {}).get("open_id") == config["self_id"]:
            mentioned = True
            text = text.replace(mention.get("key") or "@_invalid_", "")
    return {"event_id": str(message.get("message_id") or ""), "account": config["app_id"],
            "sender": str((sender.get("sender_id") or {}).get("open_id") or ""), "chat": str(message.get("chat_id") or ""),
            "text": text.strip(), "direct": message["chat_type"] == "p2p", "mentioned": mentioned, "bot": False}


def run_feishu(config, secret, bus):
    import lark_oapi as lark
    def receive(data):
        event = feishu_event(json.loads(lark.JSON.marshal(data)), config)
        if event is None:
            return
        def send(reply):
            token = post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                         {"app_id": config["app_id"], "app_secret": secret})
            if token.get("code") != 0 or not token.get("tenant_access_token"):
                raise RuntimeError("Feishu authentication rejected")
            for start in range(0, len(reply), 3000):
                data = post("https://open.feishu.cn/open-apis/im/v1/messages/" + event["event_id"] + "/reply",
                    {"msg_type": "text", "content": json.dumps({"text": reply[start:start + 3000]}, ensure_ascii=False)},
                    headers={"Authorization": "Bearer " + token["tenant_access_token"]})
                if data.get("code") != 0:
                    raise RuntimeError("Feishu delivery rejected")
        bus.enqueue(event, send)  # Return immediately so the SDK can acknowledge.
    handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(receive).build()
    lark.ws.Client(config["app_id"], secret, event_handler=handler, log_level=lark.LogLevel.ERROR).start()


def dingtalk_event(data, config):
    if data.get("msgtype") != "text" or not data.get("senderStaffId") or str(data.get("conversationType")) not in ("1", "2"):
        return None
    return {"event_id": str(data.get("msgId") or ""), "account": config["app_id"],
            "sender": str(data["senderStaffId"]), "chat": str(data.get("conversationId") or ""),
            "text": str((data.get("text") or {}).get("content") or "").strip(),
            "direct": str(data["conversationType"]) == "1", "mentioned": data.get("isInAtList") is True, "bot": False}


def run_dingtalk(config, secret, bus):
    import dingtalk_stream
    class Handler(dingtalk_stream.ChatbotHandler):
        async def process(self, callback):
            event = dingtalk_event(callback.data, config)
            address = str(callback.data.get("sessionWebhook") or "")
            url = urlsplit(address)
            if event and url.scheme == "https" and url.hostname == "oapi.dingtalk.com" and not url.username and url.path == "/robot/send":
                def send(reply):
                    for start in range(0, len(reply), 1200):
                        data = post(address, {"msgtype": "text", "text": {"content": reply[start:start + 1200]}})
                        if data.get("errcode") != 0:
                            raise RuntimeError("DingTalk delivery rejected")
                bus.enqueue(event, send)
            return dingtalk_stream.AckMessage.STATUS_OK, "OK"
    client = dingtalk_stream.DingTalkStreamClient(dingtalk_stream.Credential(config["app_id"], secret))
    client.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC, Handler())
    client.start_forever()


def main():
    source, output = sys.stdin, sys.stdout
    for stream in (source, output):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = json.loads(source.readline())
    # SDK diagnostics must not mix with the protocol or expose bot credentials.
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    logging.disable(logging.CRITICAL)
    bus = Bus(source, output)
    try:
        secret = os.environ.get(config["token_env"], "").strip()
        {"telegram": run_telegram, "discord": run_discord, "feishu": run_feishu,
         "dingtalk": run_dingtalk}[config["id"]](config, secret, bus)
    except Exception:
        with bus.lock:
            bus.emit({"type": "error"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
