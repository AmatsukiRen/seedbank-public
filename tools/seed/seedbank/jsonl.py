"""Strict JSONL reading, bounded parse caching and transaction-aware append.

Recent append deltas are an optimization hint, never a source of truth. A file
replacement, rollback, external edit or missing hint falls back to source read.
"""
from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
import threading

from . import file_state
from .durability import append_bytes
from .pack_lock import durable
from .util import SeedError

_guard = threading.RLock()
_cache = OrderedDict()
_checks = OrderedDict()
_deltas = OrderedDict()
CACHE_BYTES = 16 * 1024 * 1024
DELTA_BYTES = 1024 * 1024


def _load(path):
    name = file_state.key(path)
    stamp = file_state.stamp(path)
    cached = _cache.get(name)
    if cached is not None and cached["stamp"] == stamp:
        _cache.move_to_end(name)
        return cached
    rows = []
    if stamp:
        try:
            with Path(path).open("r", encoding="utf-8-sig") as source:
                for number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError as error:
                        raise SeedError(f"{Path(path).name} 第 {number} 行不是完整 JSON；原文件已保留。") from error
                    if not isinstance(row, dict):
                        raise SeedError(f"{Path(path).name} 第 {number} 行不是记录对象；原文件已保留。")
                    rows.append(row)
        except UnicodeError as error:
            raise SeedError(f"{Path(path).name} 的文本编码无法读取；原文件已保留。") from error
    if file_state.stamp(path) != stamp:
        raise SeedError("读取档案期间内容发生变化，请在写入结束后继续。")
    result = {"stamp": stamp, "bytes": Path(path).stat().st_size if stamp else 0, "rows": rows}
    _cache.pop(name, None)
    if result["bytes"] <= CACHE_BYTES:
        _cache[name] = result
        while len(_cache) > 8 or sum(value["bytes"] for value in _cache.values()) > CACHE_BYTES:
            _cache.popitem(last=False)
    return result


def _validate(path, validator, entry=None):
    key = (file_state.key(path), validator)
    stamp = file_state.stamp(path)
    prior = _checks.get(key)
    if prior and prior[0] == stamp:
        return prior[1]
    entry = entry or _load(path)
    if validator is not None:
        for number, row in enumerate(entry["rows"], 1):
            validator(row, number)
    _checks[key] = (entry["stamp"], len(entry["rows"]))
    _checks.move_to_end(key)
    while len(_checks) > 64:
        _checks.popitem(last=False)
    return len(entry["rows"])


def read(path, validator=None):
    with _guard:
        entry = _load(path)
        _validate(path, validator, entry)
        return deepcopy(entry["rows"])


def find(path, identifier, validator=None):
    with _guard:
        entry = _load(path)
        _validate(path, validator, entry)
        return next((deepcopy(row) for row in entry["rows"] if row.get("id") == identifier), None)


@durable
def append(pack, path, rows, validator=None):
    rows = list(rows)
    if not rows:
        return
    path = Path(path)
    with _guard:
        count = _validate(path, validator)
        for offset, row in enumerate(rows, count + 1):
            if not isinstance(row, dict):
                raise SeedError("追加档案必须使用记录对象。")
            if validator:
                validator(row, offset)
        before = file_state.stamp(path)
        if _checks[(file_state.key(path), validator)][0] != before:
            raise SeedError("校验后档案发生变化，未追加内容。")
        content = ("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode("utf-8")
        if path.exists() and path.stat().st_size:
            with path.open("rb") as source:
                source.seek(-1, 2)
                if source.read(1) != b"\n":
                    content = b"\n" + content
        append_bytes(path, content)
        after = file_state.stamp(path)
        name = file_state.key(path)
        cached = _cache.get(name)
        if cached and cached["stamp"] == before:
            cached["rows"].extend(deepcopy(rows))
            cached["stamp"], cached["bytes"] = after, path.stat().st_size
            if cached["bytes"] > CACHE_BYTES:
                _cache.pop(name, None)
            else:
                _cache.move_to_end(name)
        while sum(value["bytes"] for value in _cache.values()) > CACHE_BYTES:
            _cache.popitem(last=False)
        for key, value in list(_checks.items()):
            if key[0] == name:
                _checks.pop(key, None)
        _checks[(name, validator)] = (after, count + len(rows))
        while len(_checks) > 64:
            _checks.popitem(last=False)
        chain = _deltas.setdefault(name, [])
        if chain and chain[-1][1] != before:
            chain.clear()
        chain.append((before, after, deepcopy(rows), len(content)))
        while len(chain) > 128 or sum(item[3] for item in chain) > DELTA_BYTES:
            chain.pop(0)
        _deltas.move_to_end(name)
        while len(_deltas) > 8:
            _deltas.popitem(last=False)


def changes_since(path, previous_stamp):
    with _guard:
        current = file_state.stamp(path)
        if previous_stamp == current:
            return []
        chain = _deltas.get(file_state.key(path), [])
        if not chain or chain[-1][1] != current:
            return None
        for index, item in enumerate(chain):
            if item[0] == previous_stamp:
                return deepcopy([row for change in chain[index:] for row in change[2]])
        return None
