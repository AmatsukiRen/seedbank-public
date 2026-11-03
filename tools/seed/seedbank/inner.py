"""Private inner records, with source-bound entries and narrative history.

Loading preserves legacy records without inventing their origin. New writes
bind to an experience event in the same recoverable operation. Prompt/UI
projections live in inner_sources; the stored history is never filtered away.
"""

from __future__ import annotations

from .i18n import t
import json
from pathlib import Path
from .pack_lock import durable

from .util import SeedError, list_days, now_iso, read_json, write_json_atomic

INNER_FORMAT = "seedbank/inner@2"
LEGACY_FORMAT = "seedbank/inner@1"
CORRECTION_MAX = 64
DREAM_MAX = 32
TEXT_CHARS = 200

DEFAULT_INNER: dict = {
    "format": INNER_FORMAT,
    "silence": {"on": False, "note": "", "since_day": None},
    "corrections": [],
    "dreams": [],
    "narrative": {"text": "", "updated_day": None},
    "narrative_history": [],
}


def inner_path(pack_dir) -> Path:
    return Path(pack_dir) / "mind" / "inner.json"


def _binding(item):
    # Keep malformed bindings visible as unavailable, never as legacy text.
    return {key: str(item.get(key) or "") for key in ("event_id", "event_hash") if key in item}


def _narrative(item):
    return {"text": str(item.get("text") or "")[:TEXT_CHARS * 2],
            "updated_day": item.get("updated_day") if isinstance(item.get("updated_day"), int) else None,
            **_binding(item)}


def _normalize(data: dict) -> dict:
    """把文件里的字段收拾整齐；坏字段用默认值兜底，不让她的心变成一坨异常。"""
    out = {
        "format": INNER_FORMAT,
        "silence": {"on": False, "note": "", "since_day": None},
        "corrections": [],
        "dreams": [],
        "narrative": {"text": "", "updated_day": None},
        "narrative_history": [],
    }
    silence = data.get("silence")
    if isinstance(silence, dict):
        out["silence"] = {
            "on": bool(silence.get("on")),
            "note": str(silence.get("note") or "")[:TEXT_CHARS],
            "since_day": silence.get("since_day") if isinstance(silence.get("since_day"), int) else None,
        }
    corrections = data.get("corrections")
    if isinstance(corrections, list):
        clean = []
        for item in corrections:
            if not isinstance(item, dict):
                continue
            entry = {
                "day": item.get("day"),
                "old": str(item.get("old") or "")[:TEXT_CHARS],
                "new": str(item.get("new") or "")[:TEXT_CHARS],
                "at": str(item.get("at") or ""),
                **_binding(item),
            }
            if not entry["old"] and not entry["new"]:
                continue
            clean.append(entry)
        out["corrections"] = clean
    dreams = data.get("dreams")
    if isinstance(dreams, list):
        clean = []
        for item in dreams:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()[:TEXT_CHARS]
            if not text:
                continue
            clean.append({"day": item.get("day"), "text": text, "at": str(item.get("at") or ""), **_binding(item)})
        out["dreams"] = clean
    narrative = data.get("narrative")
    if isinstance(narrative, dict):
        out["narrative"] = _narrative(narrative)
    history = data.get("narrative_history", [])
    if isinstance(history, list):
        out["narrative_history"] = [_narrative(row) for row in history if isinstance(row, dict) and row.get("text")]
    return out


def load_inner(pack_dir) -> dict:
    """读她的心。文件不存在就返回默认值（不创建文件）。"""
    file = inner_path(pack_dir)
    if not file.is_file():
        return _normalize({})
    try:
        data = read_json(file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SeedError(t("她的内心文件读不出来：{error}", error=error)) from None
    if not isinstance(data, dict):
        raise SeedError(t("她的内心文件格式不对（应该是一个对象）"))
    if data.get("format") not in (None, LEGACY_FORMAT, INNER_FORMAT):
        from .desktop.text import t as translate
        raise SeedError(translate("内心记录版本无法读取，原文件已保留。"))
    if data.get("format") == INNER_FORMAT:
        for key in ("dreams", "corrections", "narrative_history"):
            if not isinstance(data.get(key), list) or not all(isinstance(row, dict) for row in data[key]):
                raise SeedError(t("mind/inner.json 里的 {key} 不是列表。", key=key))
        if not isinstance(data.get("narrative"), dict):
            raise SeedError(t("mind/inner.json 里的 narrative 不是对象。"))
        for key, fields in (("dreams", ("text", "at")), ("corrections", ("old", "new", "at")),
                            ("narrative_history", ("text",)), ("narrative", ("text",))):
            rows = [data[key]] if key == "narrative" else data[key]
            if any(not all(isinstance(row.get(field), str) for field in fields) for row in rows):
                from .desktop.text import t as translate
                raise SeedError(translate("内心记录内容不完整，原文件已保留。"))
    return _normalize(data)


@durable
def save_inner(pack_dir, data: dict) -> dict:
    normalized = _normalize(data)
    normalized["format"] = INNER_FORMAT
    write_json_atomic(inner_path(pack_dir), normalized)
    return normalized


def _current_day(pack_dir) -> int:
    days = list_days(pack_dir)
    return days[-1]["day"] if days else 1


def generation_origin(generation):
    if generation is None:
        return "user"
    if not isinstance(generation, dict):
        return "template"
    runner, model = generation.get("runner"), generation.get("model")
    if (generation.get("fallback") or generation.get("runtime_guard")
            or not isinstance(runner, str) or not runner.strip() or runner.strip() == "runtime"
            or runner.strip().startswith("stub") or not isinstance(model, str) or not model.strip()):
        return "template"
    return "model"


def _record(pack, activity, value, *, generation=None, depends_on=(), source="", at=None):
    from . import experience
    from .disclosure import stamp
    from .inner_sources import digest
    metadata = dict(generation or {})
    origin = generation_origin(generation)
    if generation is None:
        metadata = {"runner": "user-inner-v2"}
    day = value.get("day", value.get("updated_day"))
    text = value.get("text", "") if activity != "correction" else value["old"] + " → " + value["new"]
    event = experience.record(pack, kind="dream" if activity == "dream" else "thought", text=text,
        day=day, source=source or "mind/inner.json", actor="user" if origin == "user" else "inner",
        depends_on=depends_on, occurred_at=at,
        metadata={**metadata, **stamp("owner"), "activity": activity, "inner_origin": origin, "inner_value": dict(value)})
    return {**value, "event_id": event["id"], "event_hash": digest(event)}


# ---------------------------------------------------------------------------
# 沉默权
# ---------------------------------------------------------------------------

SILENCE_NOTE_MAX = 80


@durable
def set_silence(pack_dir, on: bool, note: str = "", day: int | None = None) -> dict:
    """打开/关掉她的沉默权。打开后她可以少说、只说一两个字。"""
    data = load_inner(pack_dir)
    day = day if isinstance(day, int) else _current_day(pack_dir)
    data["silence"] = {
        "on": bool(on),
        "note": str(note or "")[:SILENCE_NOTE_MAX],
        "since_day": day if on else None,
    }
    return save_inner(pack_dir, data)


def silence_state(pack_dir) -> dict:
    return load_inner(pack_dir)["silence"]


def silence_active(pack_dir) -> bool:
    return bool(load_inner(pack_dir)["silence"].get("on"))


# ---------------------------------------------------------------------------
# 自我更正
# ---------------------------------------------------------------------------


@durable
def correct_belief(pack_dir, old: str, new: str, *, day: int | None = None, at: str | None = None,
                   generation=None, depends_on=(), source="") -> dict:
    """记下一次自我更正：以前她以为「old」，现在她知道「new」。旧说法保留。"""
    old = str(old or "").strip()[:TEXT_CHARS]
    new = str(new or "").strip()[:TEXT_CHARS]
    if not old or not new:
        raise SeedError(t("更正需要「以前的说法」和「现在的说法」两句话"))
    data = load_inner(pack_dir)
    entry = {
        "day": day if isinstance(day, int) else _current_day(pack_dir),
        "old": old,
        "new": new,
        "at": at or now_iso(),
    }
    entry = _record(pack_dir, "correction", entry, generation=generation, depends_on=depends_on, source=source, at=at)
    data["corrections"] = (data.get("corrections") or []) + [entry]
    save_inner(pack_dir, data)
    return entry


def recent_corrections(pack_dir, limit: int = 3) -> list[dict]:
    return (load_inner(pack_dir).get("corrections") or [])[-limit:]


# ---------------------------------------------------------------------------
# 梦
# ---------------------------------------------------------------------------


@durable
def add_dream(pack_dir, day: int, text: str, *, at: str | None = None,
              generation=None, depends_on=(), source="") -> dict:
    """记下她做的一个梦。梦里的话可以不是真的，但它是她做的梦。"""
    text = str(text or "").strip()[:TEXT_CHARS]
    if not text:
        raise SeedError(t("这个梦是空的"))
    data = load_inner(pack_dir)
    entry = {"day": day, "text": text, "at": at or now_iso()}
    entry = _record(pack_dir, "dream", entry, generation=generation, depends_on=depends_on, source=source, at=at)
    data["dreams"] = (data.get("dreams") or []) + [entry]
    save_inner(pack_dir, data)
    return entry


def last_dreams(pack_dir, limit: int = 3) -> list[dict]:
    return (load_inner(pack_dir).get("dreams") or [])[-limit:]


# ---------------------------------------------------------------------------
# 自我叙事
# ---------------------------------------------------------------------------


@durable
def set_narrative(pack_dir, text: str, *, day: int | None = None, at: str | None = None,
                   generation=None, depends_on=(), source="") -> dict:
    """她给自己写的一段「我是谁」。不是设定，是她读过的日子的总结。"""
    text = str(text or "").strip()[:TEXT_CHARS * 2]
    if not text:
        raise SeedError(t("自我叙事是空的"))
    data = load_inner(pack_dir)
    if data["narrative"].get("text"):
        data["narrative_history"].append(dict(data["narrative"]))
    data["narrative"] = _record(pack_dir, "narrative", {
        "text": text,
        "updated_day": day if isinstance(day, int) else _current_day(pack_dir),
    }, generation=generation, depends_on=depends_on, source=source, at=at)
    return save_inner(pack_dir, data)


def narrative(pack_dir) -> dict:
    return load_inner(pack_dir).get("narrative") or {"text": "", "updated_day": None}


# ---------------------------------------------------------------------------
# 汇总与描述
# ---------------------------------------------------------------------------


def inner_summary(pack_dir, *, policy=None, _lineage=None, for_context=False) -> dict:
    """给认知循环/窗口用的一份摘要（不会写文件）。"""
    from .inner_sources import project
    data = project(pack_dir, policy=policy, _lineage=_lineage, for_context=for_context)
    silence = data.get("silence") or {}
    return {
        "silence": {
            "on": bool(silence.get("on")),
            "note": str(silence.get("note") or ""),
            "since_day": silence.get("since_day"),
        },
        "corrections": len(data.get("corrections") or []),
        "recent_corrections": (data.get("corrections") or [])[-2:],
        "dreams": len(data.get("dreams") or []),
        "last_dreams": (data.get("dreams") or [])[-2:],
        "narrative": data.get("narrative") or {"text": "", "updated_day": None},
        "narrative_history": data.get("narrative_history", [])[-3:] if not for_context else [],
    }


def describe_inner(pack_dir) -> str:
    from .inner_sources import display_lines
    data = inner_summary(pack_dir)
    lines = []
    silence = data["silence"]
    if silence["on"]:
        note = f"（{silence['note']}）" if silence["note"] else ""
        lines.append(t("沉默权：开着{note}——今天她可以少说一点。", note=note))
    else:
        lines.append(t("沉默权：关着——她愿意说话。"))
    if data["narrative"].get("text") or data["narrative"].get("availability"):
        lines.extend(display_lines(data["narrative"]))
    else:
        lines.append(t("她还没有给自己写过叙事。"))
    dreams = data["last_dreams"]
    if dreams:
        lines.append(t("最近做过的梦（{dreams} 个）：", dreams=data['dreams']))
        for dream in dreams:
            lines.extend(display_lines(dream))
    else:
        lines.append(t("还没做过梦。"))
    corrections = data["recent_corrections"]
    if corrections:
        lines.append(t("记下的自我更正（{corrections} 次）：", corrections=data['corrections']))
        for item in corrections:
            lines.extend(display_lines(item))
    else:
        lines.append(t("还没有更正过什么。"))
    for item in data["narrative_history"]:
        lines.extend(display_lines(item, historical=True))
    return "\n".join(lines)
