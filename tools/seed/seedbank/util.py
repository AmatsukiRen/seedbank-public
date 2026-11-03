"""Seedbank 运行时工具：哈希、时间、文件、记忆。

零依赖，只用 Python 标准库。被 CLI、认知循环、脑适配器、时间线共用。

确定性约定（协议的一部分，跨实现必须一致）：
- 所有文本一律 UTF-8，写入不做换行符转换。
- 哈希输入都是字节；字符串一律先 UTF-8 编码。
- 目录哈希：文件按相对路径排序，依次喂入 `相对路径\\0字节\\0`。
- 随机只来自 `sha256(熵)` 与出生时间；其余全部确定。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIFE_FORMAT = "seedbank/life@1"
BRAIN_FORMAT = "seedbank/brain@1"

DAY_FILE = re.compile(r"^(\d{4,})-(\d{4})-(\d{2})-(\d{2})\.md$")

MILLISECOND = 1000


class SeedError(Exception):
    """用户能看懂的错误：CLI 只打印消息，不打印堆栈。"""


# ---------------------------------------------------------------------------
# 时间
# ---------------------------------------------------------------------------

def now_iso() -> str:
    """UTC ISO 时间，毫秒精度，以 Z 结尾（与 JS toISOString 一致）。"""
    return _iso(datetime.now(timezone.utc))


def _iso(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // MILLISECOND:03d}Z"


def parse_time(value: str) -> datetime:
    """解析出生时间：ISO 字符串；带时区按给定时区，不带时按本机时区。"""
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def local_date(dt) -> str:
    """本机时区的日期字符串。日期 = 她在哪一天醒来，所以跟机器时区走。"""
    if isinstance(dt, Date) and not isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        dt = parse_time(dt)
    return dt.astimezone().strftime("%Y-%m-%d")


def add_days(date_str: str, n: int) -> str:
    return (Date.fromisoformat(date_str) + timedelta(days=int(n))).isoformat()


# ---------------------------------------------------------------------------
# 哈希
# ---------------------------------------------------------------------------

def sha256(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(value) -> str:
    """键排序、无空白的 JSON，用于让出生证哈希与书写顺序无关。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def list_files(directory) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    out: list[Path] = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if entry.is_dir():
            out.extend(list_files(entry))
        else:
            out.append(entry)
    return out


def hash_tree(directory) -> dict:
    """对目录内容做确定性哈希。返回 {sha256, files}。"""
    directory = Path(directory)
    h = hashlib.sha256()
    files = list_files(directory)
    for path in files:
        h.update(path.relative_to(directory).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return {
        "sha256": h.hexdigest(),
        "files": [p.relative_to(directory).as_posix() for p in files],
    }


# ---------------------------------------------------------------------------
# 文本与 JSON 文件
# ---------------------------------------------------------------------------

def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_text_safe(path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write_file_atomic(file, text: str) -> None:
    """UTF-8 atomic replacement, participating in a local operation if active."""
    from .durability import before_write, replace_bytes
    content = text.encode("utf-8")
    before_write(file, content)
    replace_bytes(file, content)


def write_json_atomic(file, value) -> None:
    write_file_atomic(file, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def delete_file_atomic(file) -> None:
    """Delete one known file, retaining its before-image in an active operation."""
    from .durability import before_write
    before_write(file, None)
    Path(file).unlink(missing_ok=True)


def expand_home(value) -> Path:
    return Path(str(value)).expanduser()


# ---------------------------------------------------------------------------
# 确定性随机（mulberry32，逐位可移植）
# ---------------------------------------------------------------------------

def mulberry32(seed: int):
    """32 位确定性 PRNG。与 JS 实现逐位一致，跨语言可复现。"""
    state = seed & 0xFFFFFFFF

    def next_float() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t + ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return next_float


def rng_from(key: str):
    digest = hashlib.sha256(str(key).encode("utf-8")).digest()
    return mulberry32(int.from_bytes(digest[:4], "big"))


def pick(rng, items):
    return items[min(len(items) - 1, math.floor(rng() * len(items)))]


def round2(value) -> float:
    """与 JS Math.round(x*100)/100 一致（只用于非负数场景）。"""
    return math.floor(float(value) * 100 + 0.5) / 100


# ---------------------------------------------------------------------------
# 生命包里的天与记忆
# ---------------------------------------------------------------------------

def list_days(pack_dir) -> list[dict]:
    """返回 life/ 里的天：[{file, day, date}]，按天数排序。"""
    directory = Path(pack_dir) / "life"
    if not directory.exists():
        return []
    days = []
    for entry in directory.iterdir():
        m = DAY_FILE.match(entry.name)
        if m:
            days.append({"file": entry.name, "day": int(m.group(1)), "date": f"{m.group(2)}-{m.group(3)}-{m.group(4)}"})
    return sorted(days, key=lambda d: d["day"])


def read_memories(pack_dir) -> list[dict]:
    from .jsonl import read
    return read(Path(pack_dir) / "mind" / "memories.jsonl")


def append_memories(pack_dir, entries: list[dict]) -> None:
    if not entries:
        return
    from .jsonl import append
    append(pack_dir, Path(pack_dir) / "mind" / "memories.jsonl", entries)


def pad4(n) -> str:
    return f"{int(n):04d}"
