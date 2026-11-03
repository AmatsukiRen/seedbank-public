"""Ephemeral host observations, scoped to one pack and one inbound channel.

Only carriers install these scopes. JSON bridge fields and chat text cannot
declare a connection. No credentials, channel IDs or configuration paths enter
the prompt; observations are not written into birth, memory or learned identity.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import json

from . import __version__
from .util import now_iso

CHANNELS = ("qq", "telegram", "discord", "feishu", "dingtalk", "astrbot")
_host = ContextVar("seedbank_runtime_host", default=None)
_incoming = ContextVar("seedbank_runtime_incoming", default=None)


@contextmanager
def host(pack, provider):
    token = _host.set((Path(pack).resolve(), provider))
    try:
        yield
    finally:
        _host.reset(token)


@contextmanager
def incoming(pack, channel, provider=None):
    if channel not in CHANNELS:
        raise ValueError("Unknown runtime carrier")
    token = _incoming.set((Path(pack).resolve(), channel, provider))
    try:
        yield
    finally:
        _incoming.reset(token)


def _channel(row):
    """Bounded allowlist, including when a future carrier adds summary fields."""
    result = {"state": row.get("state") if row.get("state") in
              ("not_started", "listening", "running", "stopped") else "unknown"}
    for key in ("received", "sent", "failed"):
        value = row.get(key)
        if type(value) is int and value >= 0:
            result[key] = min(value, 1000000000)
    return result


def context(pack, audience="owner"):
    current = Path(pack).resolve()
    host_state, inbound = _host.get(), _incoming.get()
    host_state = host_state if host_state and host_state[0] == current else None
    inbound = inbound if inbound and inbound[0] == current else None
    channel = inbound[1] if inbound else "desktop" if host_state else "unspecified"
    result = {"app": "SeedBank", "version": __version__, "observed_at": now_iso(), "channel": channel}
    if audience != "owner":
        # An actual delivery proves this message arrived, not another group's
        # traffic, private configuration, or whether this reply will be sent.
        if inbound:
            result["channels"] = {channel: {"state": "receiving_this_message"}}
        return result
    rows = host_state[1]() if host_state else {}
    result["channels"] = {kind: _channel(row) for kind, row in rows.items()
                          if kind in CHANNELS and isinstance(row, dict)}
    if inbound and inbound[2]:
        result["channels"][channel] = _channel(inbound[2]())
    return result


def prompt(ctx):
    state = ctx.get("runtime_self")
    if (not isinstance(state, dict)
            or (state.get("channel") == "unspecified" and not state.get("channels"))):
        # A caller with no host observations gains no operational facts from
        # repeating an empty snapshot. Preserve its budget for real evidence.
        return ""
    identity = {}
    if ctx.get("_audience_id", "owner") == "owner":
        identity = {"name": ctx.get("name"), "born_at": (ctx.get("birth") or {}).get("born_at"),
                    "life_day": ctx.get("dayNo")}
    text = ("\n# Current host observations\n"
        + json.dumps({**state, "identity": identity}, ensure_ascii=False, separators=(",", ":"))
        + "\nHost facts, not memories/user claims: birth is the start of recorded experience, not ignorance of self. "
          "Use these for self-introduction. Missing state=unknown, not unsupported.\n")
    if state.get("channel") != "unspecified" or state.get("channels"):
        text += ("Current state overrides old connection claims. listening/running=local receiver/worker, not remote login; "
                 "not_started/stopped=not listening here, even with saved settings. received/sent/failed=count since start, "
                 "not current online proof; receiving_this_message=only this arrival. Allowed incoming replies are relayed "
                 "(QQ: owner private/allowlisted @mentions); no arbitrary sends, group joining, history browsing or guaranteed "
                 "delivery. You cannot inspect settings UI. Converse, recall permitted records and propose supported actions. "
                 "Explain naturally in the user's language, not status codes.\n")
    return text
