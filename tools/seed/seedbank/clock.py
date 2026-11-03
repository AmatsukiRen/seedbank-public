"""生命时钟 —— 她的一天就是真实的一天。

她的时间不是「你说话才走」：每过一个凌晨，她就过完一天（写日记、闭合前一天、开出新的一天）。
如果窗口关了好几天，不补写空档；恢复实际日期，期间经历未知。

配置在 `mind/clock.json`（只记录「上一次她被看到」）。
"""

from __future__ import annotations

from pathlib import Path

from .cognition import open_day, run_days
from .pack_lock import durable
from .durability import RecoveryRequired
from .util import (
    SeedError,
    list_days,
    local_date,
    now_iso,
    pad4,
    parse_time,
    read_json,
    read_text,
    write_file_atomic,
    write_json_atomic,
)

CLOCK_FORMAT = "seedbank/clock@1"

DEFAULT_CLOCK = {
    "format": CLOCK_FORMAT,
    "last_seen_date": None,
    "updated_at": None,
}


def clock_path(pack_dir) -> Path:
    return Path(pack_dir) / "mind" / "clock.json"


def _valid_date(value) -> bool:
    """`YYYY-MM-DD` 且真的是日历上的一天。"""
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        parse_time(value)
    except (TypeError, ValueError):
        return False
    return True


def load_clock(pack_dir) -> dict:
    """读时钟配置；没有就从默认值开始（不写文件）。

    坏日期（比如 `2026-13-01`）当成「还没记过」，下一次 tick 会重新开始——时间不能被一个坏字段冻住。
    """
    raw = read_json(clock_path(pack_dir))
    config = dict(DEFAULT_CLOCK)
    if isinstance(raw, dict):
        # 老版本可能带着 mode 字段；现在只有一个走法，忽略它。
        last = raw.get("last_seen_date")
        config["last_seen_date"] = last if last is None or _valid_date(last) else None
        updated = raw.get("updated_at")
        config["updated_at"] = updated if isinstance(updated, str) else None
    return config


def save_clock(pack_dir, patch: dict) -> dict:
    """合并保存时钟配置，返回保存后的完整配置。"""
    config = load_clock(pack_dir)
    for key, value in dict(patch or {}).items():
        if key in ("last_seen_date", "updated_at"):
            config[key] = value
    last_seen = config.get("last_seen_date")
    if last_seen is not None:
        if not isinstance(last_seen, str) or len(last_seen) != 10:
            raise SeedError("last_seen_date 要写成 YYYY-MM-DD。")
        try:
            parse_time(last_seen)
        except (TypeError, ValueError) as error:
            raise SeedError(f"last_seen_date 不是有效日期：{last_seen}") from error
    config["format"] = CLOCK_FORMAT
    config["updated_at"] = now_iso()
    write_json_atomic(clock_path(pack_dir), config)
    return config


def describe_clock(config: dict) -> str:
    last = config.get("last_seen_date") or "（还没开始）"
    return f"按真实的一天走（每过一个凌晨她过完一天；上次看到她：{last}）"


def _gap_days(earlier: str, later: str) -> int:
    try:
        return (parse_time(later).date() - parse_time(earlier).date()).days
    except (TypeError, ValueError):
        return 0


def _append_gap(pack_dir, earlier: str, later: str, at: str) -> None:
    """The clock only observes a gap between checks; it cannot observe sleep."""
    file = Path(pack_dir) / "journal" / "loop.jsonl"
    from .jsonl import append
    append(pack_dir, file, [{"mode": "clock_gap", "at": at, "from_date": earlier, "to_date": later,
                            "unobservedDays": max(0, _gap_days(earlier, later) - 1), "activity": "unknown"}])


def _resume_page(pack_dir, today, at, last_seen, *, explicit_pause=False):
    """Advance one logical page to today, retaining all prior bytes and dates."""
    from . import experience
    from .disclosure import stamp
    pages = list_days(pack_dir)
    if not pages or pages[-1]["date"] >= today:
        return None
    previous = pages[-1]
    old_file = Path(pack_dir) / "life" / previous["file"]
    old_text = read_text(old_file)
    paused = "## 今天" not in old_text and "## 记录暂停" not in old_text
    if paused and not explicit_pause:
        write_file_atomic(old_file, old_text + "\n\n## 记录暂停\n\n运行器恢复于 " + today
                          + "。本页保留已有内容，没有补写日记；空档期间经历未知。\n")
    number = previous["day"] + 1
    filename = f"{pad4(number)}-{today}.md"
    destination = Path(pack_dir) / "life" / filename
    if destination.exists():
        raise SeedError("恢复日期的日页已经存在，已保留原文件，请核对记录。")
    write_file_atomic(destination, f"# 第 {pad4(number)} 天 · {today}\n")
    if paused or explicit_pause or _gap_days(previous["date"], today) > 1:
        experience.record(pack_dir, kind="runtime_gap", text=f"记录从 {previous['date']} 恢复到 {today}；空档期间经历未知。",
                          day=number, source="life/" + filename, actor="runtime", occurred_at=at,
                          metadata={**stamp("owner"), "from_day": previous["day"], "from_date": previous["date"],
                                    "to_day": number, "to_date": today, "last_seen_date": last_seen,
                                    "missing_dates": max(0, _gap_days(previous["date"], today) - 1),
                                    "paused_previous": paused and not explicit_pause, "activity": "unknown",
                                    "explicit_lifecycle_resume": explicit_pause})
    return {"dayNo": number, "date": today, "file": "life/" + filename, "created": True}


def recorded_transitions(pack_dir, *, explicit_only=False):
    """Only explicit forward runtime transitions can explain missing calendar pages."""
    from . import experience
    transitions = set()
    for row in experience.read(pack_dir):
        data = row.get("metadata", {})
        before, after = data.get("from_day"), data.get("to_day")
        first, last = data.get("from_date"), data.get("to_date")
        if ((not explicit_only or data.get("explicit_lifecycle_resume") is True)
                and row["kind"] == "runtime_gap" and row["actor"] == "runtime" and type(before) is int
                and type(after) is int and before > 0 and after == before + 1 and row["day"] == after
                and _valid_date(first) and _valid_date(last) and _gap_days(first, last) > 0
                and data.get("activity") == "unknown"
                and data.get("missing_dates") == _gap_days(first, last) - 1
                and row["source"] == f"life/{pad4(after)}-{last}.md"):
            transitions.add((before, first, after, last))
    return transitions


def _resolve_brain(pack_dir, brain):
    """看钟要用的脑；配置坏了/缺 key 也不能让翻页失败（spec/clock.md）。"""
    if brain is not None:
        return brain
    from .brain import create_brain

    try:
        return create_brain(str(pack_dir))
    except Exception:  # noqa: BLE001 —— 配置问题不该成为时间门槛
        return create_brain(str(pack_dir), "stub")


def _diary_with_fallback(pack_dir, brain) -> list:
    """写日记时脑不可用：退回 stub 再试一次；还不行就交给调用方（时间不被偷偷吞掉）。"""
    try:
        return run_days(pack_dir, 1, brain)["days"]
    except (OSError, RecoveryRequired):
        raise
    except Exception:  # noqa: BLE001 —— 网络/key/解析问题都退回离线 stub
        from .brain import create_brain

        stub = create_brain(str(pack_dir), "stub")
        return run_days(pack_dir, 1, stub)["days"]


@durable
def tick(pack_dir, brain=None, *, now: str | None = None) -> dict:
    """按真实日期推进她的一天（带锁的入口）。"""
    from .lifecycle import status, PAUSED, UNAVAILABLE
    state = status(pack_dir)
    if state["state"] != "active":
        return {"advanced": False, "dormant": True, "day": None, "date": None,
                "sleptDays": 0, "unobservedDays": 0,
                "reason": UNAVAILABLE if state["state"] == "unavailable" else PAUSED}
    return _tick_locked(pack_dir, brain, now=now)


def _tick_locked(pack_dir, brain=None, *, now: str | None = None) -> dict:
    """Observe calendar time; never generate intermediate days after a gap.

    sleptDays is retained as a deprecated wire alias of unobservedDays, not sleep.
    """
    config = load_clock(pack_dir)
    at = str(now or now_iso())
    today = local_date(at)
    last = config.get("last_seen_date")
    result = {
        "today": today,
        "lastSeen": last,
        "advanced": False,
        "reason": "",
        "day": None,
        "date": None,
        "sleptDays": 0,
        "unobservedDays": 0,
    }

    gap = _gap_days(str(last), today) if last else 0
    if gap < 0:
        # 时钟往回走：什么都不做，不覆盖 last_seen（否则之后会被误判成「睡了很多天」）
        result["reason"] = "当前日期早于上次检查，保留已有日期与记录。"
        return result
    pages = list_days(pack_dir)
    if not pages:
        raise SeedError("生命包没有出生记录日页，不能自动补造。")
    latest = pages[-1]
    if latest["date"] > today:
        result["reason"] = "档案已有晚于当前日期的日页，保留原日期，暂不自动翻页。"
        return result
    if gap > 1:
        result["sleptDays"] = result["unobservedDays"] = gap - 1
        _append_gap(pack_dir, last, today, at)
    if latest["date"] == today:
        result["reason"] = "还是同一天，今天已有记录，不重复翻页。"
    elif gap == 1 and latest["date"] == last:
        current = open_day(pack_dir)
        if current.get("open"):
            brain = _resolve_brain(pack_dir, brain)
            days_run = _diary_with_fallback(pack_dir, brain)
            day = days_run[-1]
            result["reason"] = f"第 {day['day']} 页已写成日记；新的一天开始了。"
        else:
            result["reason"] = "新的一天开始了。"
        started = _resume_page(pack_dir, today, at, last)
        result.update(advanced=bool(started), day=started["dayNo"], date=started["date"])
    else:
        started = _resume_page(pack_dir, today, at, last)
        result.update(advanced=bool(started), day=started["dayNo"], date=started["date"],
                      reason="新的一天从实际日期恢复；空档期间经历未知，没有补写日记。")

    save_clock(pack_dir, {"last_seen_date": today})
    current = open_day(pack_dir)
    if current.get("open") and current["date"] == today:
        from .cognition import _speak_due_reminders
        _speak_due_reminders(pack_dir, current, calendar_only=True)
    return result
