from __future__ import annotations

import os
import threading
from pathlib import Path

from .. import qq
from .. import body, development, runtime_self
from ..identity import profile as identity_profile
from ..agency import load_agency
from ..bonds import load_bonds
from ..brain import describe_brain, load_brain_config
from ..bridge import Bridge
from ..cognition import list_memories, maybe_initiate, read_news_lines, read_sense_lines, read_transcript
from ..live import process_inbox
from ..inner_sources import project as inner_projection
from ..memorial import load_memorial
from ..memory_state import MemoryPolicy
from ..memory_sources import PolicySources
from ..hands import load_hands
from ..settings import save_settings
from ..util import SeedError, list_days, read_json
from ..requests import pending
from ..pack_lock import writer


class Session:
    def __init__(self, pack_dir, brain_override=""):
        self.pack = Path(pack_dir).expanduser().resolve()
        self.bridge = Bridge(self.pack, brain_override)
        self.name = self.bridge.name
        self.lock = threading.RLock()
        self.server = None
        self.server_thread = None
        self.revision = 0
        self.closed = False
        from ..channels import Manager
        self.channels = Manager(self)

    def call(self, operation, **fields):
        with self.lock, runtime_self.host(self.pack, self.runtime_channels):
            if self.closed:
                raise RuntimeError("The room is closed.")
            result = self.bridge.handle({"op": operation, **fields})
            if not result.get("ok", False):
                raise SeedError(str(result.get("error") or result.get("message") or "Operation failed"))
            self.revision += 1
            return result

    def pulse(self):
        with self.lock, runtime_self.host(self.pack, self.runtime_channels):
            from ..lifecycle import active
            if not active(self.pack):
                return {"dormant": True, "snapshot": self.snapshot()}
            result = self.call("tick")
            inbox = process_inbox(self.pack, brain=self.bridge.brain)
            spoken = maybe_initiate(self.pack, self.bridge.brain)
            self.revision += 1
            return {**result, "inbox": inbox, "spoken": spoken, "snapshot": self.snapshot()}

    def save_brain(self, patch, *, api_key=""):
        with self.lock:
            result = save_settings(self.pack, patch, api_key=api_key)
            self.bridge = Bridge(self.pack)
            self.revision += 1
            return result

    def snapshot(self):
        with self.lock, writer(self.pack):
            # Share this read-time policy only within one locked snapshot.
            # The next snapshot reloads sources, including external edits/rollback.
            sources = PolicySources(self.pack)
            policy = MemoryPolicy.load(self.pack, _sources=sources)
            days = list_days(self.pack)
            current = days[-1] if days else {"day": 1, "date": ""}
            states = {}
            for name in ("mood", "agency", "bonds", "memorial", "inner", "hands", "friends", "works"):
                value = read_json(self.pack / "mind" / f"{name}.json", {})
                states[name] = value if isinstance(value, dict) else {}
            for name, loader in (("agency", load_agency), ("bonds", load_bonds), ("memorial", load_memorial), ("hands", load_hands)):
                states[name] = loader(self.pack)
            states["inner"] = inner_projection(self.pack, policy=policy)
            growth = development.current_state(self.pack, policy=policy, _events=sources.development_events)
            states["development"] = development.summary(self.pack, day=current["day"], policy=policy, _state=growth)
            from ..agency import plan_history
            states["plan_history"] = plan_history(self.pack, day=current["day"], limit=8)
            states["body"] = body.state(self.pack)
            from ..lifecycle import status
            states["lifecycle"] = status(self.pack)
            # Reading time is not a state change; retain only displayed resource values.
            states["body"].pop("updated_at", None)
            states["mood"]["energy"] = states["body"]["energy"]
            return {
                "profile": identity_profile(self.pack),
                "days": days, "day": current["day"], "date": current["date"],
                "transcript": read_transcript(self.pack, current["day"]) if days else [],
                "senses": read_sense_lines(self.pack, current["day"]) if days else [],
                "news": read_news_lines(self.pack, current["day"]) if days else [],
                "memories": list_memories(self.pack, _policy=policy), "states": states,
                "brain": describe_brain(load_brain_config(self.pack)),
                "revision": self.revision,
                "pendingRequests": pending(self.pack),
                "recoveredOperations": self.bridge.recovered_operations,
            }

    def diary(self, day):
        # A missing/unreadable file is different from an empty diary. Let the
        # page offer recovery instead of silently showing an empty document.
        with self.lock:
            rows = list_days(self.pack)
            row = next((item for item in rows if item["day"] == day), None)
            if row is None:
                raise SeedError("找不到这一天的日记文件。")
            return (self.pack / "life" / row["file"]).read_text(encoding="utf-8")

    def start_qq(self, config):
        if self.server is not None:
            return {"ok": True, "running": True}
        owner = str(config.get("owner") or "").strip()
        if not owner.isdigit():
            raise ValueError("QQ owner must contain digits.")
        port = int(config.get("port") or qq.DEFAULT_QQ_PORT)
        if not 1024 <= port <= 65535:
            raise ValueError("QQ port must be between 1024 and 65535.")
        sender = qq.OneBotSender(config.get("onebot_http") or qq.DEFAULT_ONEBOT_HTTP,
                                 os.environ.get("SEEDBANK_ONEBOT_TOKEN", ""))
        adapter = qq.QQAdapter(self.pack, owner, qq.parse_groups(config.get("groups")),
                               bridge=self, sender=sender, self_id=str(config.get("self_id") or ""),
                               log=lambda message: None)
        server = qq._IMServer(("127.0.0.1", port), adapter, secret=qq.inbound_secret(config))
        worker = threading.Thread(target=server.serve_forever, name="seedbank-desktop-qq", daemon=True)
        try:
            worker.start()
        except Exception:
            server.server_close()
            raise
        self.server, self.server_thread = server, worker
        return {"ok": True, "running": True, "port": port}

    def runtime_channels(self):
        # Only live in-process observations; saved forms do not imply a socket,
        # remote login, or receipt. No disk config or account IDs are exposed.
        server, worker = self.server, self.server_thread
        rows = {"qq": {"state": "not_started"}}
        if server is not None:
            rows["qq"] = {**server.adapter.runtime_status(),
                          "state": "listening" if worker and worker.is_alive() else "stopped"}
        for row in self.channels.summaries():
            rows[row["id"]] = {**row, "state": "running" if row["running"] else "stopped"}
        return rows

    def stop_qq(self):
        server, self.server = self.server, None
        if server is not None:
            server.shutdown()
            server.server_close()
            server.adapter.close()
        self.server_thread = None
        return {"ok": True, "running": False}

    def close(self):
        self.channels.close()
        self.stop_qq()
        with self.lock:
            self.closed = True
