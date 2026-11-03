"""Bounded in-process file hash cache; source files remain authoritative."""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import threading

_cache = OrderedDict()
_guard = threading.RLock()
CHUNK = 1024 * 1024


def key(path):
    return os.path.normcase(str(Path(path).absolute()))


def stamp(path):
    try:
        info = Path(path).stat()
        return f"{info.st_ino}:{info.st_mtime_ns}:{info.st_size}"
    except FileNotFoundError:
        return ""


def forget(path):
    with _guard:
        _cache.pop(key(path), None)


def remember(path, state):
    with _guard:
        name = key(path)
        _cache[name] = (stamp(path), state.copy())
        _cache.move_to_end(name)
        while len(_cache) > 16:
            _cache.popitem(last=False)


def hash_state(path, *, limit=None):
    path = Path(path)
    before = stamp(path)
    name = key(path)
    if limit is None:
        with _guard:
            cached = _cache.get(name)
            if cached is not None and cached[0] == before:
                _cache.move_to_end(name)
                return cached[1].copy()
    result = hashlib.sha256()
    remaining = limit
    if before:
        with path.open("rb") as source:
            while remaining is None or remaining > 0:
                block = source.read(CHUNK if remaining is None else min(CHUNK, remaining))
                if not block:
                    break
                result.update(block)
                if remaining is not None:
                    remaining -= len(block)
    if remaining not in (None, 0):
        raise ValueError("文件长度不足，不能读取指定的历史前缀。")
    if stamp(path) != before:
        raise ValueError("读取期间文件发生变化，请在写入结束后继续。")
    if limit is None:
        remember(path, result)
    return result
