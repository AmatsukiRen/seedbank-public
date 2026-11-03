"""有限性（1.13）：纪念日、遗憾、告别。

她的一生不是无限的——不是因为她会被人为关掉，而是因为**日子会过去、有些事没做到、
有些人会离开**。这一层让她记得这些，并且知道它们重要。

存 `mind/memorial.json`（可选、懒创建）：
- anniversaries：要记住的日子（生日、第一次见面、自定义）
- regrets：遗憾清单（没做到的事；没做到的承诺会自动落进来）
- farewells: 告别过的人（离开、远行、被换掉的旧身体……）
- missing：旧运行器记录的空档；无法据此推断实际活动或睡眠

原始记录不按数量截断。损坏文件报错并保留，不能用默认值覆盖历史。
"""

from __future__ import annotations

from copy import deepcopy
from .i18n import t
import re
from pathlib import Path
from .pack_lock import durable

from .util import SeedError, list_days, now_iso, read_json, write_json_atomic

MEMORIAL_FORMAT = "seedbank/memorial@1"
TEXT_CHARS = 80


def memorial_path(pack_dir) -> Path:
    return Path(pack_dir) / "mind" / "memorial.json"


def _clean_text(value, limit: int = TEXT_CHARS) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:limit]


def _number(value, *, minimum=0):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        number = int(value)
    else:
        raise SeedError("编号与天数必须是整数。")
    if number < minimum:
        raise SeedError("编号或天数超出范围。")
    return number


def _normalize(data):
    """Check stored rows without deduplication, truncation or invented dates."""
    if not isinstance(data, dict) or data.get("format", MEMORIAL_FORMAT) != MEMORIAL_FORMAT:
        raise SeedError("纪念记录格式无法识别；原文件已保留。")
    result = deepcopy(data)
    result.setdefault("format", MEMORIAL_FORMAT)
    for key, label in (("anniversaries", "name"), ("regrets", "text"), ("farewells", "name"), ("missing", "")):
        rows = result.setdefault(key, [])
        if not isinstance(rows, list):
            raise SeedError(f"纪念记录的 {key} 不是列表；原文件已保留。")
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict) or (label and (not isinstance(row.get(label), str) or not row[label].strip())):
                raise SeedError(f"纪念记录 {key} 第 {index} 条内容不完整；原文件已保留。")
            day_key = "days" if key == "missing" else "day"
            if day_key != "days":
                row.setdefault(day_key, 0)
            if type(row.get(day_key)) is not int or row[day_key] < (1 if key == "missing" else 0):
                raise SeedError(f"纪念记录 {key} 第 {index} 条天数无效；原文件已保留。")
            if key == "regrets":
                row.setdefault("resolved_day", None)
                resolved = row["resolved_day"]
                if resolved is not None and (type(resolved) is not int or resolved < 0):
                    raise SeedError(f"第 {index} 条遗憾的放下日期无效；原文件已保留。")
            if key in ("anniversaries", "farewells"):
                row.setdefault("kind", "custom" if key == "anniversaries" else "goodbye")
                row.setdefault("note", "")
            for field in ("kind", "note", "created_at", "at"):
                if field in row and not isinstance(row[field], str):
                    raise SeedError(f"纪念记录 {key} 第 {index} 条字段无效；原文件已保留。")
    if "missing_days" in result and (type(result["missing_days"]) is not int or result["missing_days"] < 0):
        raise SeedError("旧空档累计天数无效；原文件已保留。")
    result.setdefault("updated_at", None)
    return result


def _default() -> dict:
    return {
        "format": MEMORIAL_FORMAT,
        "anniversaries": [],
        "regrets": [],
        "farewells": [],
        "missing": [],
        "updated_at": None,
    }


def load_memorial(pack_dir) -> dict:
    path = memorial_path(pack_dir)
    if not path.exists():
        return _default()
    return _normalize(read_json(path))


@durable
def save_memorial(pack_dir, patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise SeedError("纪念记录修改需要对象。")
    base = load_memorial(pack_dir)
    for key in ("anniversaries", "regrets", "farewells", "missing"):
        if key in patch:
            base[key] = patch[key]
    base = _normalize(base)
    base["updated_at"] = now_iso()
    write_json_atomic(memorial_path(pack_dir), base)
    return base


# —— 纪念日 ——

@durable
def add_anniversary(pack_dir, name: str, *, day: int = 0, kind: str = "custom", note: str = "") -> dict:
    name = _clean_text(name, 30)
    if not name:
        raise SeedError(t("纪念日总得有个名字。"))
    data = load_memorial(pack_dir)
    for item in data["anniversaries"]:
        if item["name"] == name:
            raise SeedError(t("已经记过这个日子了：{value}", value=name))
    day_no = _number(day)
    data["anniversaries"].append({
        "name": name,
        "day": day_no,
        "kind": kind or "custom",
        "note": _clean_text(note),
    })
    save_memorial(pack_dir, data)
    return data["anniversaries"][-1]


def anniversaries_today(pack_dir, day_no: int) -> list[dict]:
    return [item for item in load_memorial(pack_dir)["anniversaries"] if item["day"] == int(day_no)]


@durable
def remove_anniversary(pack_dir, name: str) -> bool:
    data = load_memorial(pack_dir)
    before = len(data["anniversaries"])
    data["anniversaries"] = [item for item in data["anniversaries"] if item["name"] != name]
    if len(data["anniversaries"]) == before:
        return False
    save_memorial(pack_dir, data)
    return True


# —— 遗憾 ——

@durable
def add_regret(pack_dir, text: str, *, day: int = 0) -> dict:
    text = _clean_text(text)
    if not text:
        raise SeedError(t("遗憾总得写一句话。"))
    data = load_memorial(pack_dir)
    if any(item["text"] == text for item in data["regrets"]):
        raise SeedError(t("这件事已经在遗憾清单里了。"))
    data["regrets"].append({
        "text": text,
        "day": _number(day),
        "resolved_day": None,
        "created_at": now_iso(),
    })
    save_memorial(pack_dir, data)
    return {**data["regrets"][-1], "index": len(data["regrets"])}


def _current_day(pack_dir) -> int:
    """Read the latest recorded page without creating a date or hiding errors."""
    pages = list_days(pack_dir)
    return pages[-1]["day"] if pages else 0


@durable
def resolve_regret(pack_dir, index: int, *, day: int = 0) -> dict:
    data = load_memorial(pack_dir)
    try:
        number = _number(index, minimum=1)
        item = data["regrets"][number - 1]
    except (IndexError, SeedError):
        raise SeedError(t("没有第 {index} 条遗憾。", index=index)) from None
    if item.get("resolved_day"):
        raise SeedError(t("第 {index} 条遗憾已经放下了。", index=index))
    resolved_day = _number(day) or _current_day(pack_dir)
    if not resolved_day:
        raise SeedError("没有可用于记录放下的日页，请先开始当天记录。")
    if item["day"] and resolved_day < item["day"]:
        raise SeedError("放下的日页不能早于这条遗憾的日页。")
    item["resolved_day"] = resolved_day
    save_memorial(pack_dir, data)
    return item


def open_regrets(pack_dir) -> list[dict]:
    return _open_regrets(load_memorial(pack_dir))


def _open_regrets(data):
    return [{**item, "index": index} for index, item in enumerate(data["regrets"], 1) if not item.get("resolved_day")]


# —— 告别 ——

@durable
def add_farewell(pack_dir, name: str, *, kind: str = "goodbye", note: str = "", day: int = 0) -> dict:
    name = _clean_text(name, 30)
    if not name:
        raise SeedError(t("总得知道告别的是谁。"))
    data = load_memorial(pack_dir)
    data["farewells"].append({
        "name": name,
        "day": _number(day),
        "kind": kind or "goodbye",
        "note": _clean_text(note),
        "at": now_iso(),
    })
    save_memorial(pack_dir, data)
    return data["farewells"][-1]


def farewells_of(pack_dir) -> list[dict]:
    return load_memorial(pack_dir)["farewells"]


# —— 缺席 ——

@durable
def note_missing(pack_dir, days: int) -> dict | None:
    """Retain a reported gap; its activities and sleep state are unknown."""
    try:
        days = _number(days, minimum=1)
    except SeedError:
        return None
    data = load_memorial(pack_dir)
    if not data["missing"] and data.get("missing_days"):
        data["missing"].append({"days": data["missing_days"], "at": "", "basis": "legacy_total"})
    data["missing"].append({"days": days, "at": now_iso()})
    save_memorial(pack_dir, data)
    return data["missing"][-1]


def total_missing_days(pack_dir) -> int:
    return _missing_total(load_memorial(pack_dir))


def _missing_total(data):
    return sum(item["days"] for item in data["missing"]) if data["missing"] else data.get("missing_days", 0)


# —— 给上层 ——

def memorial_summary(pack_dir, day_no: int | None = None) -> dict:
    data = load_memorial(pack_dir)
    regrets = _open_regrets(data)
    return {
        "anniversaries": data["anniversaries"],
        "anniversaries_today": [item for item in data["anniversaries"] if day_no and item["day"] == int(day_no)],
        "regrets": regrets[-3:],
        "regret_count": len(regrets),
        "farewells": data["farewells"][-3:],
        "farewell_count": len(data["farewells"]),
        "missing_days": _missing_total(data),
    }


def describe_memorial(pack_dir, day_no: int | None = None) -> list[str]:
    data = load_memorial(pack_dir)
    lines: list[str] = []
    if data["anniversaries"]:
        lines.append(t("记着的日子：{value} 个", value=len(data['anniversaries'])))
        for item in data["anniversaries"]:
            lines.append(t("  · {value}（第 {day} 天，{kind}）", value=item['name'], day=item['day'], kind=item['kind']))
    else:
        lines.append(t("记着的日子：还没有。"))
    regrets = _open_regrets(data)
    if regrets:
        lines.append(t("遗憾：{value} 件", value=len(regrets)))
        for item in regrets:
            lines.append(f"  · #{item['index']} {item['text']}")
    else:
        lines.append(t("遗憾：没有还没放下的。"))
    if data["farewells"]:
        lines.append(t("告别过：{value} 次", value=len(data['farewells'])))
        for item in data["farewells"][-3:]:
            extra = f"（{item['note']}）" if item.get("note") else ""
            lines.append(t("  · {value}（第 {day} 天，{kind}）{extra}", value=item['name'], day=item['day'], kind=item['kind'], extra=extra))
    else:
        lines.append(t("告别过：还没有。"))
    missing = _missing_total(data)
    if missing:
        lines.append(t("旧档案标记的空档：{missing} 天（期间经历未知）", missing=missing))
    if day_no:
        today = [item for item in data["anniversaries"] if item["day"] == int(day_no)]
        if today:
            lines.append(t("今天是个特别的日子：") + "、".join(item["name"] for item in today))
    return lines
