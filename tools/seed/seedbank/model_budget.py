"""Per-activity model-call allowance, shared by nested cognitive work.

This bounds application dispatches, not HTTP retries or billed tokens. The
context is ephemeral: independent requests/threads get independent allowances.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import uuid

from .i18n import t
from .util import SeedError

_current = ContextVar("seedbank_model_budget", default=None)
BLOCKED = "本轮模型调用额度已用完，后续生成尚未开始；这不代表能力不足。"


class Exhausted(SeedError):
    pass


@contextmanager
def scope():
    if _current.get() is not None:
        yield
        return
    token = _current.set({"id": uuid.uuid4().hex, "limit": None, "reserved_calls": 0})
    try:
        yield
    finally:
        _current.reset(token)


def operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with scope():
            return function(*args, **kwargs)
    return wrapped


def exhausted():
    state = _current.get()
    return bool(state and state["limit"] is not None and state["reserved_calls"] >= state["limit"])


def reserve(limit):
    state = _current.get()
    if state is None:
        raise RuntimeError("A model dispatch requires an activity scope")
    if state["limit"] is None:
        state["limit"] = limit
    else:
        # A nested caller may narrow the allowance, never reset or enlarge it.
        state["limit"] = min(state["limit"], limit)
    if exhausted():
        raise Exhausted(t(BLOCKED))
    state["reserved_calls"] += 1


def snapshot():
    state = _current.get()
    return dict(state) if state and state["limit"] is not None else {}
