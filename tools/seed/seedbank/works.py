"""作品（1.15）：她会写诗、写信、画点东西。

设计：
- 作品存在 `mind/works.json`，可选、懒创建（孵化器不写，避免破坏协议向量）。
- 三种作品：诗（poem）/ 信（letter）/ 画（drawing，字符画）。
- 每件作品都是一条不可改的记录：写了就写了，除非她自己撕掉（这里不提供删除）。
- 只写文字：画是字符画，仍然只是文本，谁都能读、能带走。

格式：
{
  "format": "seedbank/works@1",
  "works": [
    {"id": "w_0001", "kind": "poem", "title": "无题", "text": "…", "day": 3, "created_at": "…"}
  ]
}
"""

from __future__ import annotations

from .i18n import t
import json
from pathlib import Path
from .pack_lock import durable

from .util import (
    SeedError,
    now_iso,
    read_json,
    write_json_atomic,
)

WORKS_FORMAT = "seedbank/works@1"
WORK_KINDS = ("poem", "letter", "drawing")
WORK_LABELS = {"poem": "诗", "letter": "信", "drawing": "画"}
TITLE_CHARS = 40
TEXT_CHARS = 1200
MAX_WORKS = 120


def works_path(pack_dir) -> Path:
    return Path(pack_dir) / "mind" / "works.json"


def _empty() -> dict:
    return {"format": WORKS_FORMAT, "works": []}


def load_works(pack_dir) -> dict:
    path = works_path(pack_dir)
    if not path.is_file():
        return _empty()
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("works"), list):
        raise SeedError(t("作品文件坏了：{value}", value=path))
    return {"format": str(data.get("format") or WORKS_FORMAT), "works": list(data["works"])}


@durable
def save_works(pack_dir, works: dict) -> dict:
    path = works_path(pack_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "format": WORKS_FORMAT,
        "works": list(works.get("works") or []),
    }
    write_json_atomic(path, data)
    return data


def _clean_kind(kind) -> str:
    value = str(kind or "poem").strip().lower()
    if value not in WORK_KINDS:
        raise SeedError(t("不认识的作种类别：{kind}（可选：{join}）", kind=kind, join=' / '.join(WORK_KINDS)))
    return value


@durable
def add_work(pack_dir, kind: str, text: str, *, title: str = "", day: int | None = None, at: str | None = None) -> dict:
    """她写了一样东西。返回写入的作品条目。"""
    kind = _clean_kind(kind)
    body = str(text or "").strip()
    if not body:
        raise SeedError(t("作品是空的：她写了什么？"))
    works = load_works(pack_dir)
    numbers = [int(str(w.get("id", ""))[2:]) for w in works["works"]
               if str(w.get("id", "")).startswith("w_") and str(w.get("id", ""))[2:].isdigit()]
    number = max(numbers, default=0) + 1
    entry = {
        "id": f"w_{number:04d}",
        "kind": kind,
        "title": str(title or "无题").strip()[:TITLE_CHARS] or "无题",
        "text": body[:TEXT_CHARS],
        "day": int(day) if day is not None else None,
        "created_at": at or now_iso(),
    }
    works["works"].append(entry)
    save_works(pack_dir, works)
    return entry


def list_works(pack_dir, kind: str | None = None, limit: int | None = None) -> list[dict]:
    works = load_works(pack_dir)["works"]
    if kind:
        wanted = str(kind).strip().lower()
        if wanted in WORK_LABELS:
            wanted = {"诗": "poem", "信": "letter", "画": "drawing"}.get(wanted, wanted)
        works = [w for w in works if str(w.get("kind")) == wanted]
    works = list(reversed(works))
    if limit is not None:
        works = works[: max(0, int(limit))]
    return works


def works_summary(pack_dir) -> dict:
    works = load_works(pack_dir)["works"]
    counts = {kind: 0 for kind in WORK_KINDS}
    for item in works:
        kind = str(item.get("kind"))
        if kind in counts:
            counts[kind] += 1
    recent = list(reversed(works))[:3]
    return {
        "available": bool(works),
        "total": len(works),
        "poems": counts["poem"],
        "letters": counts["letter"],
        "drawings": counts["drawing"],
        "recent": [
            {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "label": t(WORK_LABELS.get(str(item.get("kind")), "作品")),
                "title": item.get("title"),
                "day": item.get("day"),
                "text": str(item.get("text") or "")[:200],
            }
            for item in recent
        ],
    }


def describe_works(pack_dir) -> str:
    data = works_summary(pack_dir)
    if not data["total"]:
        return t("她还没有留下过作品。")
    lines = [
        t("她留下的作品：诗 {poems} 首 / 信 {letters} 封 / 画 {drawings} 张", poems=data['poems'], letters=data['letters'], drawings=data['drawings']),
    ]
    for item in data["recent"]:
        day = t("第 {day} 天", day=item['day']) if item.get("day") else t("某一天")
        lines.append(f"- [{item['label']}] {item['title']}（{day}）")
    return "\n".join(lines)


def read_work(pack_dir, work_id: str) -> dict | None:
    wanted = str(work_id or "").strip()
    for item in load_works(pack_dir)["works"]:
        if str(item.get("id")) == wanted:
            return item
    return None
