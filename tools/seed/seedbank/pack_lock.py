"""Reentrant single-writer ownership shared by desktop, CLI and bridge.

OS locks are released when a process exits. The persistent lock file is not
used as evidence that a writer is still alive.
"""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path
import threading

from .util import SeedError

_guard = threading.Lock()
_locks = {}
_local = threading.local()


@contextmanager
def writer(pack):
    root = Path(pack).expanduser().resolve()
    if not (root / "birth.json").is_file():
        raise SeedError(f"不是生命包（缺 birth.json）：{root}")
    key = os.path.normcase(str(root))
    with _guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        owned = getattr(_local, "owned", None)
        if owned is None:
            owned = _local.owned = set()
        if key in owned:
            yield
            return
        path = root / "mind" / ".writer.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        locked = False
        try:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as error:
                raise SeedError("这个生命包正在由另一个进程写入，请在原窗口继续。") from error
            owned.add(key)
            from .durability import recover_locked
            recovered = recover_locked(root)
            yield recovered
        finally:
            owned.discard(key)
            try:
                if locked:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def serialized(function):
    @wraps(function)
    def call(*args, **kwargs):
        pack = args[0] if args else kwargs.get("pack_dir", kwargs.get("pack"))
        with writer(pack):
            return function(*args, **kwargs)
    return call


def durable(function):
    """One recoverable operation, joining an outer operation when nested."""
    @wraps(function)
    def call(*args, **kwargs):
        from .durability import operation
        pack = args[0] if args else kwargs.get("pack_dir", kwargs.get("pack"))
        with writer(pack):
            with operation(pack, function.__name__):
                return function(*args, **kwargs)
    return call
