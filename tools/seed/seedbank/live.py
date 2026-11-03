"""常驻循环与事件队列（1.16）：让她的一天不等按键也会继续。

设计原则（见 `docs/04-gap-to-human.md` 与 `spec/live.md`）：

- 只搬运真实事件：时间自己走、外部程序投递的事件、主人留下的便条；
- 不伪造现实：`live` 不会凭空生成「发生在她房间里」的事；
- 坏事件只进 `inbox/failed/`，不阻塞循环；
- 生命包里只追加：所有结果都落在当天的 `life/` 里，消费记录落在 `journal/loop.jsonl`。
"""

from __future__ import annotations

from .i18n import t
import json
import shutil
import time
from pathlib import Path
import uuid
from .pack_lock import serialized
from .durability import RecoveryRequired

from .clock import tick as clock_tick
from .cognition import (
    _append_journal,
    chat_turn,
    feed_news,
    maybe_initiate,
    open_day,
    sense_media,
)
from .util import (
    SeedError,
    now_iso,
    parse_time,
    read_json,
    sha256,
    write_json_atomic,
)

LIVE_FORMAT = "seedbank/live@1"
EVENT_KINDS = ("news", "sense", "note")
EVENT_TEXT_CHARS = 2000
EVENT_SOURCE_CHARS = 80
INBOX_DIR = "inbox"
FAILED_DIR = "inbox/failed"
DONE_LOG = "journal/loop.jsonl"


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

def inbox_path(pack_dir) -> Path:
    return Path(pack_dir) / INBOX_DIR


def failed_path(pack_dir) -> Path:
    return Path(pack_dir) / FAILED_DIR


# ---------------------------------------------------------------------------
# 投递：只写队列，不做任何解释
# ---------------------------------------------------------------------------

def _clean_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise SeedError(t("事件必须是一个 JSON 对象"))
    kind = str(raw.get("kind") or "").strip()
    if kind not in EVENT_KINDS:
        raise SeedError(t("事件类型只能是 {join}（收到 {value}）", join=' / '.join(EVENT_KINDS), value=kind or '空'))
    text = str(raw.get("text") or "").strip()
    if not text:
        raise SeedError(t("事件必须有 text"))
    if len(text) > EVENT_TEXT_CHARS:
        text = text[:EVENT_TEXT_CHARS]
    source = str(raw.get("source") or "外界").strip() or "外界"
    if len(source) > EVENT_SOURCE_CHARS:
        source = source[:EVENT_SOURCE_CHARS]
    at = str(raw.get("at") or now_iso())
    try:
        parse_time(at)
    except SeedError:
        raise SeedError(t("事件时间不是合法 ISO 时间：{at}", at=at))
    return {"kind": kind, "text": text, "source": source, "at": at}


def _stamp(at: str) -> str:
    dt = parse_time(at)
    return dt.strftime("%Y%m%dT%H%M%S")


@serialized
def enqueue_event(pack_dir, event: dict) -> Path:
    """把一条事件写进 `inbox/`，返回文件路径。"""
    clean = _clean_event(event)
    folder = inbox_path(pack_dir)
    folder.mkdir(parents=True, exist_ok=True)
    digest = sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True).encode("utf-8"))[:8]
    name = f"{_stamp(clean['at'])}-{clean['kind']}-{digest}.json"
    path = folder / name
    write_json_atomic(path, {"format": LIVE_FORMAT, **clean})
    return path


def list_events(pack_dir) -> list[Path]:
    folder = inbox_path(pack_dir)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.json") if p.is_file())


# ---------------------------------------------------------------------------
# 消费：把事件变成她的一天
# ---------------------------------------------------------------------------

@serialized
def process_event(pack_dir, event: dict, *, brain=None, request_id="") -> dict:
    from .lifecycle import require_active
    require_active(pack_dir)
    from .requests import run
    clean = _clean_event(event)
    payload = {"kind": "event", "event": {**clean, "at": str(event.get("at") or "")}}
    return run(pack_dir, payload, lambda: _process_event(pack_dir, clean, brain=brain), request_id=request_id)


def _process_event(pack_dir, clean, *, brain=None):
    day = open_day(pack_dir)
    if clean["kind"] == "news":
        res = feed_news(
            pack_dir,
            [{"text": clean["text"], "source": clean["source"]}],
            source=clean["source"],
            at=clean["at"],
        )
        return {"kind": "news", "dayNo": day["dayNo"], "result": res}
    if clean["kind"] == "sense":
        res = sense_media(pack_dir, note=clean["text"])
        return {"kind": "sense", "dayNo": day["dayNo"], "result": res}
    res = chat_turn(pack_dir, clean["text"], brain)
    return {
        "kind": "note",
        "dayNo": day["dayNo"],
        "reply": res.get("reply"),
        "result": res,
    }


@serialized
def process_inbox(pack_dir, *, brain=None) -> dict:
    """消费 `inbox/` 里所有事件；坏的移进 `inbox/failed/`，不抛异常。"""
    from .lifecycle import active
    if not active(pack_dir):
        return {"processed": [], "failed": [], "dormant": True}
    processed: list[dict] = []
    failed: list[dict] = []
    for path in list_events(pack_dir):
        try:
            raw = read_json(path)
            if raw is None:
                raise SeedError(t("事件文件不是合法 JSON"))
            key = "inbox_" + sha256(path.name + json.dumps(raw, ensure_ascii=False, sort_keys=True))
            result = process_event(pack_dir, raw, brain=brain, request_id=key)
            path.unlink(missing_ok=True)
            entry = {
                "mode": "event",
                "at": now_iso(),
                "kind": result["kind"],
                "dayNo": result["dayNo"],
            }
            _append_journal(pack_dir, entry)
            processed.append({"file": path.name, **result})
        except RecoveryRequired:
            raise
        except Exception as exc:  # noqa: BLE001 — 坏事件不能拖垮循环
            dest = failed_path(pack_dir)
            dest.mkdir(parents=True, exist_ok=True)
            try:
                target = dest / path.name
                if target.exists():
                    target = dest / (path.stem + "-" + uuid.uuid4().hex + path.suffix)
                shutil.move(str(path), str(target))
            except OSError:
                pass  # Keep the original input if archiving fails.
            _append_journal(
                pack_dir,
                {"mode": "live_failed", "at": now_iso(), "file": path.name, "error": str(exc)},
            )
            failed.append({"file": path.name, "error": str(exc)})
    return {"processed": processed, "failed": failed}


# ---------------------------------------------------------------------------
# 常驻循环
# ---------------------------------------------------------------------------

def run_live(
    pack_dir,
    *,
    interval: float = 60.0,
    rounds: int | None = None,
    brain=None,
    now_fn=None,
    initiate_every: int = 5,
    sleep=time.sleep,
    out=print,
) -> dict:
    """前台常驻循环：看钟 → 消费事件 → 偶尔主动开口 → 睡一会。

    `rounds` 为 None 时一直跑（Ctrl+C 停）；测试用 `rounds=1` + `now_fn`。
    """
    if interval < 1:
        raise SeedError(t("interval 至少 1 秒"))
    if rounds is not None and rounds < 1:
        raise SeedError(t("rounds 至少 1"))
    now_fn = now_fn or now_iso
    stats = {"rounds": 0, "days": 0, "events": 0, "failed": 0, "initiated": 0, "stopped": "rounds"}

    count = 0
    try:
        while rounds is None or count < rounds:
            count += 1
            at = now_fn()
            # 时钟是辅助，不是门槛：看钟失败也不能让生活流停下（spec/clock.md）。
            try:
                clock = clock_tick(pack_dir, brain, now=at)
            except Exception:  # noqa: BLE001 —— 翻页失败只影响时间，不影响这一轮
                clock = {}
            if clock.get("advanced"):
                stats["days"] += 1
            inbox = process_inbox(pack_dir, brain=brain)
            stats["events"] += len(inbox["processed"])
            stats["failed"] += len(inbox["failed"])
            if initiate_every and count % initiate_every == 0:
                try:
                    init = maybe_initiate(pack_dir, brain)
                except Exception:  # pragma: no cover — 主动开口失败不该停循环
                    init = None
                if init:
                    stats["initiated"] += 1
            stats["rounds"] = count
            day_no = clock.get("dayNo") or clock.get("day")
            if day_no is None:
                try:
                    day_no = open_day(pack_dir)["dayNo"]
                except Exception:  # pragma: no cover — 显示用，失败不该停循环
                    day_no = None
            out(
                t(
                    "[live] {at} · 第 {day} 天 · 事件 {events} 条",
                    at=at,
                    day=day_no if day_no is not None else "?",
                    events=len(inbox["processed"]),
                )
                + (t("（{value} 条坏事件）", value=len(inbox["failed"])) if inbox["failed"] else "")
            )
            if rounds is None or count < rounds:
                sleep(interval)
    except KeyboardInterrupt:
        stats["stopped"] = "interrupted"
        out(t("[live] 停了。她的文件都还在。"))
    return stats
