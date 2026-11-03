"""离线整理重复话题。线索不是偏好、信念或模型训练成果。

历史 growth.jsonl 原样保留；新记录只表达有来源的 topic_observation。
有意义的信念、偏好与目标更新由 development 协议记录。
"""

from __future__ import annotations

import re
from pathlib import Path
from .pack_lock import durable
from . import jsonl

from .cognition import normalize_memory_writes, open_day, visible_memories
from .util import append_memories, list_days, now_iso, read_memories, read_text_safe, write_file_atomic

GROWTH_FORMAT = "seedbank/growth@1"
RECENT_DAYS = 14
MIN_MEMORY_HITS = 3
MIN_TOPIC_DAYS = 2

# 这些标签是「发生的类型」，不是「她在意的事」，不往里长。
META_TAGS = {
    "对话", "感知", "见闻", "主人", "日子", "出生", "边界", "成长",
    "梦", "更正", "作品", "手", "关系", "遗憾", "纪念日", "告别",
    # 来源/载体标签：它们说明「从哪来」，不是「她在意什么」。
    "群聊", "群里", "群", "新闻", "报纸", "网络", "论坛", "社区",
    "载体", "访客", "朋友", "聊天记录", "窗外",
}

# 高频但没信息量的词，不当作「在意的事」。
STOPWORDS = {
    "今天", "明天", "昨天", "现在", "时候", "自己", "一个", "什么", "没有",
    "这样", "那样", "知道", "觉得", "时候", "一点", "有点", "一直", "已经",
    "还是", "就是", "这个", "那个", "不是", "可是", "然后", "因为", "所以",
    "主人", "房间", "只有", "可以", "如果", "真的", "好像", "只是", "这里",
    "那里", "不会", "没有", "我会", "我看", "我想", "她说", "我说", "到了",
    "一点", "出来", "下来", "起来", "不住", "不说",
    # 来源/载体词：它们出现在记忆正文里（「（来源：群聊）」），不是她在意的事。
    "群聊", "群里", "来源", "新闻", "报纸", "网络", "论坛", "社区",
    "载体", "访客", "朋友", "聊天记录", "窗外",
    "来源", "读到", "听到", "看见", "说过", "写下", "记下", "有人",
}

_CJK = re.compile(r"[\u4e00-\u9fff]")
_SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n\r]+")


def growth_path(pack_dir: Path) -> Path:
    return Path(pack_dir) / "mind" / "growth.jsonl"


def read_growth(pack_dir: Path) -> list[dict]:
    return jsonl.read(growth_path(pack_dir))


def _read_memories(pack_dir: Path) -> list[dict]:
    return read_memories(pack_dir)


def _recent(pack_dir: Path, day: int, days: int = RECENT_DAYS) -> list[dict]:
    rows = []
    for row in visible_memories(pack_dir):
        if row.get("kind") == "forget" or "梦" in (row.get("tags") or []) or row.get("runner") == "grow-offline-v1":
            continue
        row_day = row.get("day")
        if isinstance(row_day, int) and row_day < day - days:
            continue
        rows.append(row)
    return rows


def _diary_text(pack_dir: Path, day: int, days: int = RECENT_DAYS) -> str:
    parts = []
    for item in list_days(pack_dir):
        if item["day"] > day or item["day"] < day - days:
            continue
        text = read_text_safe(Path(pack_dir) / "life" / item["file"])
        if text:
            parts.append(text)
    return "\n".join(parts)


def _beliefs_text(pack_dir: Path) -> str:
    return read_text_safe(Path(pack_dir) / "mind" / "beliefs.md")


@durable
def _append_belief(pack_dir: Path, line: str) -> None:
    path = Path(pack_dir) / "mind" / "beliefs.md"
    text = _beliefs_text(pack_dir)
    if not text:
        text = "# 我相信的事\n\n"
    if not text.endswith("\n"):
        text += "\n"
    write_file_atomic(path, text + line + "\n")


def _append_growth(pack_dir: Path, entries: list[dict]) -> None:
    jsonl.append(pack_dir, growth_path(pack_dir), entries)


_SOURCE_TAIL = re.compile(r"（\s*来源：[^）]*）")
_HEARSAY_HEAD = re.compile(r"^我(?:读|听)到[：:，,]?")


def _clean_material(text: str) -> str:
    """去掉「我读到：」这类壳和「（来源：…）」这类尾巴，只留内容。"""
    text = _HEARSAY_HEAD.sub("", (text or "").strip())
    text = _SOURCE_TAIL.sub("", text)
    return text.strip()


def _cjk_grams(text: str, size: int) -> set[str]:
    grams = set()
    for sentence in _SENTENCE_SPLIT.split(_clean_material(text)):
        for chunk in re.findall(r"[\u4e00-\u9fff]+", sentence):
            if len(chunk) < size:
                continue
            for index in range(0, len(chunk) - size + 1):
                gram = chunk[index:index + size]
                if gram in STOPWORDS:
                    continue
                if not _CJK.match(gram[0]) or not _CJK.match(gram[-1]):
                    continue
                grams.add(gram)
    return grams


def tag_counts(pack_dir: Path, *, day: int | None = None,
               days: int = RECENT_DAYS) -> dict[str, int]:
    """最近一段时间里，她记忆里出现最多的话题标签。"""
    counts: dict[str, int] = {}
    for row in _recent(pack_dir, day if day is not None else 1, days):
        for tag in row.get("tags") or []:
            if not isinstance(tag, str):
                continue
            tag = tag.strip()
            if not tag or tag in META_TAGS or len(tag) > 12:
                continue
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def topic_counts(pack_dir: Path, *, day: int) -> dict[str, int]:
    """把「记忆里反复出现」和「日记里也写过」的词放在一起数。

    入选条件（都为真才算她真的在意）：
    * 在最近的记忆里至少出现 MIN_MEMORY_HITS 次；
    * 至少跨 MIN_TOPIC_DAYS 个不同的日子（一次性的热闹不算）；
    * 不是高频虚词（STOPWORDS）。
    日记里出现过的词额外加分——她在自己写下的东西里也想到过它。
    """
    memories = _recent(pack_dir, day)
    memory_days: dict[str, set] = {}
    memory_hits: dict[str, int] = {}
    for row in memories:
        text = row.get("text")
        if not isinstance(text, str):
            continue
        row_day = row.get("day")
        seen = set()
        for size in (2, 3):
            for gram in _cjk_grams(text, size):
                if gram in seen:
                    continue
                seen.add(gram)
                memory_hits[gram] = memory_hits.get(gram, 0) + 1
                if isinstance(row_day, int):
                    memory_days.setdefault(gram, set()).add(row_day)

    diary = _diary_text(pack_dir, day)
    diary_hits: dict[str, int] = {}
    for size in (2, 3):
        for gram in _cjk_grams(diary, size):
            diary_hits[gram] = diary_hits.get(gram, 0) + 1

    counts: dict[str, int] = {}
    for gram, hits in memory_hits.items():
        if hits < MIN_MEMORY_HITS:
            continue
        if len(memory_days.get(gram, set())) < MIN_TOPIC_DAYS:
            continue
        if gram in STOPWORDS:
            continue
        counts[gram] = hits * 2 + diary_hits.get(gram, 0)
    return counts


@durable
def grow(pack_dir: Path, *, day: int | None = None) -> dict | None:
    """跑一次本地成长；有变化返回那条成长记录，没有就返回 None。"""
    from .lifecycle import active
    if not active(pack_dir):
        return None
    pack = Path(pack_dir)
    if not (pack / "birth.json").is_file():
        return None
    if day is None:
        day = int(open_day(pack)["dayNo"])

    # 一天只长大一次：同一天重复调用不再写新东西。
    growth = read_growth(pack)
    if growth and growth[-1].get("day") == day:
        return None

    # 重复出现只说明有过接触，不推断喜欢、相信或重要程度。
    candidates = {}
    for topic, hits in topic_counts(pack, day=day).items():
        candidates[topic] = hits * 2
    ranked = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
    for topic, hits in ranked:
        if any(row.get("topic") == topic for row in growth):
            continue
        if len(topic) < 2:
            continue
        evidence = [row["id"] for row in _recent(pack, day)
                    if topic in str(row.get("text", "")) and row.get("id")][:6]
        at = now_iso()
        entry = {
            "format": GROWTH_FORMAT,
            "day": day,
            "kind": "topic_observation",
            "topic": topic,
            "evidence": evidence,
            "text": f"最近的记录反复提到「{topic}」；我对它的态度还没有确定。",
            "at": at,
        }
        _append_growth(pack, [entry])
        writes = normalize_memory_writes(
            pack,
            day_no=day,
            source="mind/growth.jsonl",
            runner="grow-offline-v1",
            default_kind="thought",
            entries=[{
                "text": entry["text"],
                "importance": 0.35,
                "tags": ["成长", topic],
            }],
            at=at,
        )
        append_memories(pack, writes)
        return entry
    return None


def describe_growth(pack_dir: Path) -> str:
    entries = read_growth(pack_dir)
    if not entries:
        return "她还没有靠自己长大过（`seed grow` 会让本机帮她整理一次记忆）。"
    lines = [f"她自己长大的次数：{len(entries)} 次"]
    for row in entries[-5:]:
        day = row.get("day")
        text = row.get("text", "")
        lines.append(f"  · 第 {day} 天 · {text}")
    return "\n".join(lines)


def growth_summary(pack_dir: Path) -> dict:
    entries = read_growth(pack_dir)
    return {
        "count": len(entries),
        "last": entries[-1] if entries else None,
        "growth_path": str(growth_path(pack_dir)),
    }
