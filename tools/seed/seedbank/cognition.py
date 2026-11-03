"""认知循环 —— 对话回合、过一天、记忆召回。

文件格式、检索公式、遗忘规则在这里；「她说什么」由脑适配器（brain.py）决定。
运行器只负责：组装上下文 → 问脑 → 校验 → 落笔。
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import body, development, experience, facts, learning, relationships, model_budget
from .memory_state import MemoryPolicy, revise_memory, provenance as memory_provenance, is_template
from .pack_lock import serialized, durable
from .lifecycle import active as life_active, require_active
from .durability import RecoveryRequired
from .identity import profile as identity_profile

from .agency import boundaries_match, current_plan, learn_from_day, load_agency, plan_for_day, plan_status, record_initiation, should_initiate
from .bonds import bond_summary, register_talk
from .brain import create_brain, vision_translate
from .inner import add_dream, correct_belief, inner_summary, set_narrative, silence_active
from .hands import apply_actions, due_reminders, hands_summary, mark_said, sweep_missed
from .friends import friends_summary, list_friends, mourn_friend, record_visit
from .memorial import farewells_of, memorial_summary
from .senses import analyze_image, analyze_sound, describe_image, describe_sound
from .settings import memory_settings
from .works import add_work, list_works, works_summary
from .util import (
    SeedError, add_days, append_memories, expand_home, list_days, local_date,
    now_iso, pad4, read_json, read_memories, read_text, read_text_safe, round2,
    rng_from, write_file_atomic, write_json_atomic, canonical_json, sha256,
)

# 给脑的上下文里最多带几条记忆。
RECALL_K = 8
# 每张记忆最多多少字。
MEMORY_MAX_CHARS = 200
# 每轮最多提炼几条记忆；保留旧常量名与设置键。
MEMORY_DAILY_BUDGET = 8
# 一条见闻最多多少字（避免把整篇文章灌进她的一天）。
NEWS_MAX_CHARS = 200
# 一次最多读进多少条见闻。
NEWS_MAX_ITEMS = 12

ALLOWED_KINDS = {"conversation", "diary", "thought", "feeling", "correction", "forget", "perception", "hearsay"}

_TRANSCRIPT_LINE = re.compile(r"^\*\*(.+?)\*\*[：:](.*)$")
_QUERY_SPLIT = re.compile(r"[\s，。、！？：；,.!?:;\"'「」（）()]+")


def _memory_filename(day_no: int, date: str) -> str:
    return f"{pad4(day_no)}-{date}.md"


def _day_file_of(pack_dir, day_no):
    for day in list_days(pack_dir):
        if day["day"] == int(day_no):
            return day
    return None


def _day_excerpt(pack_dir, day: dict, *, policy=None) -> str:
    """取「## 今天」段落的开头做摘要。"""
    try:
        text = read_text(Path(pack_dir) / "life" / day["file"])
    except OSError:
        return ""
    heading = "当日日记" if "\n## 当日日记" in text else "今天"
    if "\n## " + heading not in text:
        return ""
    after = text.split("\n## " + heading, 1)[1].split("\n---")[0]
    excerpt = " ".join(after.split())[:200]
    known_template = policy is not None and policy.template_diary_fragment("life/" + day["file"], excerpt)
    prefix = "[离线或回退模板日记，不是亲历依据] " if known_template else ""
    return prefix + excerpt


def read_transcript(pack_dir, day_no) -> list[dict]:
    """读出某一天已经说过的话：`**主人**：…` / `**名字**：…`"""
    day = _day_file_of(pack_dir, day_no)
    if not day:
        return []
    text = read_text(Path(pack_dir) / "life" / day["file"])
    start = text.find("## 对话")
    if start < 0:
        return []
    block = text[start + len("## 对话"):].split("\n## ")[0]
    messages = []
    for line in block.splitlines():
        m = _TRANSCRIPT_LINE.match(line.strip())
        if m:
            messages.append({"who": m.group(1).strip(), "text": m.group(2).strip()})
    return messages


def _text_block(text: str, heading: str) -> str:
    """取某个二级标题下的内容（直到下一个 `## `）。"""
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    body = text[start + len(marker):]
    end = body.find("\n## ")
    return body if end < 0 else body[:end]


def read_sense_lines(pack_dir, day_no) -> list[str]:
    """读出某一天她「感觉到」的原始记录（`## 感知` 下的 bullet）。"""
    day = _day_file_of(pack_dir, day_no)
    if not day:
        return []
    text = read_text(Path(pack_dir) / "life" / day["file"])
    lines = []
    for line in _text_block(text, "感知").splitlines():
        line = line.strip()
        if line.startswith("- "):
            lines.append(line[2:].strip())
    return lines


def read_news_lines(pack_dir, day_no) -> list[str]:
    """读出某一天她「读到的」见闻（`## 见闻` 下的 bullet）。"""
    day = _day_file_of(pack_dir, day_no)
    if not day:
        return []
    text = read_text(Path(pack_dir) / "life" / day["file"])
    lines = []
    for line in _text_block(text, "见闻").splitlines():
        line = line.strip().lstrip("\ufeff")
        if line.startswith("- "):
            lines.append(line[2:].strip())
    return lines


def _append_to_section(text: str, heading: str, lines: list[str]) -> str:
    """把若干 bullet 追加到 `## heading` 段；没有这一段就在末尾新建。"""
    bullets = "\n".join(f"- {line}" for line in lines)
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return text.rstrip() + f"\n\n{marker}\n\n{bullets}\n"
    rest = text[start + len(marker):]
    nxt = re.search(r"(?m)^## ", rest)
    if nxt is None:
        return text.rstrip() + "\n" + bullets + "\n"
    insert_at = start + len(marker) + nxt.start()
    before = text[:insert_at].rstrip()
    after = text[insert_at:]
    return before + "\n" + bullets + "\n\n" + after


def _later_headings(heading: str) -> tuple[str, ...]:
    """一天里各段的固定顺序：对话 → 感知 → 见闻 → 今天。"""
    order = ("对话", "感知", "见闻")
    try:
        index = order.index(heading)
    except ValueError:
        return ()
    return order[index + 1:]


def _ensure_bullet_section(text: str, heading: str, lines: list[str]) -> str:
    """写一段 bullet 列表：有这一段就追加，没有就按固定顺序插到该在的位置。"""
    marker = f"## {heading}"
    if marker in text:
        return _append_to_section(text, heading, lines)
    bullets = "\n".join(f"- {line}" for line in lines)
    block = marker + "\n\n" + bullets
    return _insert_before_sections(text, block, _later_headings(heading) + ("今天",))


def _append_news(text: str, lines: list[str]) -> str:
    """把见闻写进 `## 见闻`；顺序上在「今天」之前（说话与感知之后）。"""
    return _ensure_bullet_section(text, "见闻", lines)


def open_day(pack_dir) -> dict:
    """现在轮到哪一天？

    - 最后一天还没写「## 今天」→ 这一天还没结束，就写在这一天
    - 否则 → 新的一天
    """
    birth = read_json(Path(pack_dir) / "birth.json")
    if not birth:
        raise ValueError(f"不是生命包（缺 birth.json）：{pack_dir}")
    days = list_days(pack_dir)
    if not days:
        return {"dayNo": 1, "date": local_date(birth.get("born_at") or now_iso()), "open": False}
    last = days[-1]
    text = read_text(Path(pack_dir) / "life" / last["file"])
    # The genesis narrative is not the end of the actual birth day. Once the
    # real-time clock has observed that date, interaction continues on page 1.
    # Packs used for explicit logical-day simulation (no clock) keep their ABI.
    clock = read_json(Path(pack_dir) / "mind/clock.json", {})
    if (last["day"] == 1 and isinstance(clock, dict)
            and clock.get("last_seen_date") == last["date"]
            and "## 当日日记" not in text and "## 记录暂停" not in text):
        return {"dayNo": 1, "date": last["date"], "open": True}
    if "## 今天" not in text and "## 记录暂停" not in text:
        return {"dayNo": last["day"], "date": last["date"], "open": True}
    return {"dayNo": last["day"] + 1, "date": add_days(last["date"], 1), "open": False}


@durable
def start_day(pack_dir) -> dict:
    """确保她现在这一天在 life/ 里有一页。

    真实时钟在凌晨翻页时用：没人说话的日子也要有一页，否则一天没有地方发生。
    已经开着的天不会重复创建。
    """
    require_active(pack_dir)
    day = open_day(pack_dir)
    file = Path(pack_dir) / "life" / _memory_filename(day["dayNo"], day["date"])
    if not file.exists():
        write_file_atomic(file, f"# 第 {pad4(day['dayNo'])} 天 · {day['date']}\n")
    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": f"life/{_memory_filename(day['dayNo'], day['date'])}",
        "created": True,
    }


def _insert_before_sections(text: str, block: str, headings: tuple[str, ...]) -> str:
    """把一段内容插到指定二级标题之前；都不存在就追加到末尾。"""
    for heading in headings:
        marker = f"## {heading}"
        index = text.find(marker)
        if index >= 0:
            return text[:index].rstrip() + "\n\n" + block + "\n\n" + text[index:]
    return text + "\n\n" + block


def _append_section_text(text: str, heading: str, block: str) -> str:
    """把一段自由文本（不是 bullet）追加到 `## heading` 段末尾；没有就按顺序新建。"""
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return _insert_before_sections(
            text, marker + "\n\n" + block, _later_headings(heading) + ("今天",)
        )
    rest_start = start + len(marker)
    rest = text[rest_start:]
    nxt = re.search(r"(?m)^## ", rest)
    if nxt is None:
        return text.rstrip() + "\n\n" + block + "\n"
    insert_at = rest_start + nxt.start()
    return text[:insert_at].rstrip() + "\n" + block + "\n\n" + text[insert_at:]


def append_transcript(pack_dir, day: dict, entries: list[dict], *, recorded=None) -> str:
    """把一轮对话追加进当天的文件。返回相对路径。"""
    birth = read_json(Path(pack_dir) / "birth.json", {})
    fish_name = str(birth.get("name") or "她")
    file = Path(pack_dir) / "life" / _memory_filename(day["dayNo"], day["date"])
    text = read_text_safe(file).rstrip()
    if not text:
        text = f"# 第 {pad4(day['dayNo'])} 天 · {day['date']}"
    block_lines = []
    batch_ids = []
    for e in entries:
        who = str(e.get("who") or "owner")
        if who == "fish":
            who = f"{fish_name}（主动）" if e.get("initiated") else fish_name
        elif who in ("owner", "主人"):
            who = "主人"
        else:
            who = who.replace("**", "").replace("\n", " ").strip()[:20] or "访客"
        line = str(e["text"]).replace("\r", " ").replace("\n", " ")
        event = experience.record(pack_dir, kind="conversation", text=line, actor=who,
                                  day=day["dayNo"], source=f"life/{file.name}",
                                  depends_on=list(e.get("depends_on", [])) + (batch_ids if e.get("who") == "fish" else []),
                                  metadata=e.get("metadata"))
        batch_ids.append(event["id"])
        if recorded is not None:
            recorded.append(event)
        block_lines.append(f"**{who}**：{line}")
    text = _append_section_text(text, "对话", "\n\n".join(block_lines))
    write_file_atomic(file, text)
    return f"life/{_memory_filename(day['dayNo'], day['date'])}"


def _finalize_day(pack_dir, day: dict, diary: str, mood: str) -> str:
    """写出这一天的日记段（若当天文件已存在则追加，不覆盖对话）。"""
    file = Path(pack_dir) / "life" / _memory_filename(day["dayNo"], day["date"])
    text = read_text_safe(file).rstrip()
    if not text:
        text = f"# 第 {pad4(day['dayNo'])} 天 · {day['date']}"
    if "## 今天" not in text:
        text += f"\n\n## 今天\n\n{diary}\n\n---\n\n*{mood}。*\n"
    elif day["dayNo"] == 1 and "## 当日日记" not in text:
        # Retain the original genesis text; the first real diary is separate.
        text += f"\n\n## 当日日记\n\n{diary}\n\n---\n\n*{mood}。*\n"
    write_file_atomic(file, text.rstrip() + "\n")
    return f"life/{_memory_filename(day['dayNo'], day['date'])}"


def _append_journal(pack_dir, entry: dict) -> None:
    from .jsonl import append
    file = Path(pack_dir) / "journal" / "loop.jsonl"
    append(pack_dir, file, [entry])


# ---------------------------------------------------------------------------
# 记忆的可见与忘记
#
# 记忆只追加，不改旧行：忘记一个人或一件事，不是把那一行删掉，而是给未来的
# 自己留一句「我忘了」。墓碑（kind="forget"）的 forgets 字段指向被忘记的 id；
# 召回、上下文、UI 列表都跳过被指向的那些 —— 但历史仍然可查。
# ---------------------------------------------------------------------------

TOMBSTONE_KIND = "forget"
TOMBSTONE_TEXT_PREFIX = "我忘了："
TOMBSTONE_TEXT_CHARS = 40


def forgotten_ids(pack_dir) -> set[str]:
    """已经被墓碑指向的记忆 id。"""
    forgotten: set[str] = set()
    for memory in read_memories(pack_dir):
        if memory.get("kind") != TOMBSTONE_KIND:
            continue
        target = memory.get("forgets")
        if isinstance(target, str) and target:
            forgotten.add(target)
    return forgotten


def list_memories(pack_dir, *, _policy=None) -> list[dict]:
    """按文件顺序读记忆，每条附带 forgotten：是否已被某条墓碑指向。"""
    policy = _policy if _policy is not None else MemoryPolicy.load(pack_dir)
    listing = []
    for memory in policy.records:
        item = policy.annotate(memory)
        item["forgotten"] = str(memory.get("id") or "") in policy.blocked
        item["superseded"] = str(memory.get("id") or "") in policy.superseded
        item["recallable"] = policy.allows(memory)
        item["can_revise"] = item["recallable"] and memory.get("kind") != TOMBSTONE_KIND
        item["provenance"] = memory_provenance(memory)
        listing.append(item)
    return listing


def visible_memories(pack_dir) -> list[dict]:
    """Current, supported recollections. Audit tombstones never enter prompts."""
    return MemoryPolicy.load(pack_dir).visible()


def _latest_day(pack_dir) -> dict:
    """最后一天的 day/date；一个还没过完的新生命包就当作第 1 天。"""
    days = list_days(pack_dir)
    if days:
        return {"day": int(days[-1]["day"]), "date": str(days[-1]["date"])}
    birth = read_json(Path(pack_dir) / "birth.json", {})
    if not birth:
        raise ValueError(f"不是生命包（缺 birth.json）：{pack_dir}")
    return {"day": 1, "date": local_date(birth.get("born_at") or now_iso())}


@durable
def forget_memory(pack_dir, memory_id, *, reason: str = "") -> dict:
    """忘记一条记忆：追加一条墓碑，旧记忆原样保留（历史不能被改写）。"""
    target = str(memory_id or "").strip()
    if not target:
        raise SeedError("要她忘记哪一条记忆？给一个记忆 id（例如 m_0002_1）。")
    memories = read_memories(pack_dir)
    found = next((m for m in memories if str(m.get("id") or "") == target), None)
    if found is None:
        raise SeedError(f"她的记忆里没有这一条：{target}")
    if found.get("kind") == TOMBSTONE_KIND:
        raise SeedError(f"「{target}」是一条忘记记录，本身不能再被忘记。")
    if target in forgotten_ids(pack_dir):
        raise SeedError(f"「{target}」她已经忘掉了。")

    day = _latest_day(pack_dir)
    day_no = day["day"]
    at = now_iso()
    same_day = len([m for m in memories if _memory_day(m) == day_no])
    tombstone = {
        "id": f"m_{pad4(day_no)}_{same_day + 1}",
        "day": day_no,
        "date": day["date"],
        "kind": TOMBSTONE_KIND,
        "text": "已放下一条记忆；正文仅保留在历史档案中。",
        "tags": ["忘记"],
        "importance": 0.0,
        "source": "forget",
        "runner": "forget-v1",
        "session": f"forget-{at}",
        "at": at,
        "forgets": target,
        "reason": str(reason or ""),
    }
    append_memories(pack_dir, [tombstone])
    learn_from_day(pack_dir, day_no, day["date"])
    return {"id": target, "forgotten": True}


def build_context(pack_dir, day_no: int, date: str, message: str = "", *, use_semantic=True, person_id="owner", audience_id=None,
                  interaction_kind="direct") -> dict:
    """组装给脑的上下文。这是她「此刻知道的一切」。"""
    birth = read_json(Path(pack_dir) / "birth.json")
    if not birth:
        raise ValueError(f"不是生命包（缺 birth.json）：{pack_dir}")
    from . import disclosure
    audience_id = disclosure.audience(person_id, audience_id, interaction_kind=interaction_kind)
    from .runtime_self import context as runtime_context
    runtime = runtime_context(pack_dir, audience_id)
    if audience_id != "owner":
        return {**disclosure.context(pack_dir, day_no, date, message, person_id=person_id,
                                    policy=disclosure.policy_for(pack_dir, audience_id, person_id), use_semantic=use_semantic),
                "runtime_self": runtime}
    species = read_json(Path(pack_dir) / "species.json", {})
    traits_doc = read_json(Path(pack_dir) / "genome" / "traits.json", {})
    picked = read_json(Path(pack_dir) / "mind" / "traits.json", {"traits": []})
    mood_doc = read_json(Path(pack_dir) / "mind" / "mood.json", {})
    from .memory_sources import PolicySources
    sources = PolicySources(pack_dir)
    policy = MemoryPolicy.load(pack_dir, _sources=sources)
    growth = development.current_state(pack_dir, policy=policy, _events=sources.development_events)
    current_source = f"life/{_memory_filename(day_no, date)}"
    outdated_sources = policy.affected_sources | policy.revised_sources
    restricted_legacy = bool(policy.forgotten or policy.superseded)

    moods = traits_doc.get("moods") if isinstance(traits_doc.get("moods"), list) and traits_doc["moods"] else ["安静"]
    transcript = []
    entries = experience.transcript_events(pack_dir, current_source, read_transcript(pack_dir, day_no))
    for m in entries:
        if not policy.allows(m) or (not m.get("event_id") and current_source in policy.revised_sources):
            continue
        provenance = {"source": m["source"], "event_id": m["event_id"], "depends_on": m["depends_on"],
                      "template_generated": is_template(m)}
        metadata = m.get("metadata", {})
        if "person_id" in metadata and not metadata.get("runner"):
            transcript.append({"who": "owner" if metadata["person_id"] == "owner" else m["who"],
                               "text": m["text"], "person_id": metadata["person_id"],
                               "interaction_kind": metadata.get("interaction_kind", "direct"), **provenance})
        elif m["who"] in (birth.get("name"), f"{birth.get('name')}（主动）"):
            transcript.append({"who": "fish", "text": m["text"], **provenance})
        elif m["who"] == "运行器":
            transcript.append({"who": "runtime", "text": m["text"], **provenance})
        elif m["who"] == "主人":
            transcript.append({"who": "owner", "text": m["text"], **provenance})
        else:
            transcript.append({"who": m["who"], "text": m["text"], **provenance})

    transcript = facts.annotate_records(pack_dir, transcript, policy)
    from .story_lineage import Lineage
    story_links = Lineage(pack_dir, policy)
    transcript = story_links.annotate_many(transcript)
    days = list_days(pack_dir)
    try:
        energy_value = round2(body.state(pack_dir)["energy"])
    except (TypeError, ValueError):
        energy_value = 0.6
    if not math.isfinite(energy_value):
        energy_value = 0.6
    energy_value = min(1.0, max(0.0, energy_value))
    _agency = load_agency(pack_dir)
    _today_plan = current_plan(pack_dir, day_no) or {}
    from .planning import awaiting_choice
    choice_pending = awaiting_choice(pack_dir, _today_plan)
    current_development = development.summary(pack_dir, policy=policy, day=day_no, _lineage=story_links, _state=growth)
    if _today_plan.get("origin") != "model" and current_development.get("prior_choices"):
        choice_pending = True
    from . import life_story
    recalled = recall(pack_dir, message, RECALL_K, policy=policy, use_semantic=use_semantic) if message else []
    from .semantic import last_status as retrieval_status
    visible_goals = {item["id"] for item in current_development["goals"]}
    if _today_plan.get("goal_id") and _today_plan["goal_id"] not in visible_goals:
        _today_plan = {}
    plan_refs = _today_plan.get("evidence", [])
    if plan_refs and len(policy.supports(plan_refs)) != len(plan_refs):
        _today_plan = {}
        plan_refs = []
    if _today_plan.get("origin") == "model":
        from .deliberation import valid
        if not valid(pack_dir, _today_plan, policy=policy):
            _today_plan, plan_refs = {}, []
    if _today_plan.get("goal_event_id") and any(g["id"] == _today_plan.get("goal_id")
            and g["event_id"] != _today_plan["goal_event_id"] for g in current_development["goals"]):
        _today_plan = {**_today_plan, "basis_changed": True}
    from .plan_checkpoints import for_plan as plan_checkpoint
    checkpoint = plan_checkpoint(pack_dir, _today_plan, policy=policy, _state=growth)
    choice_pending = choice_pending or checkpoint.get("passed", False) or checkpoint.get("state") in ("unavailable", "criteria_changed", "prerequisites")
    recent_days = [d for d in days if d["day"] < int(day_no)
                   and f"life/{d['file']}" not in outdated_sources][-2:]
    context = {
        "runtime_self": runtime,
        "packDir": str(pack_dir),
        "_audience_id": audience_id, "_person_id": person_id,
        "birth": birth,
        "name": str(birth.get("name")),
        "speciesId": (birth.get("species") or {}).get("id", species.get("id", "")),
        "speciesName": (birth.get("species") or {}).get("name", species.get("name", "")),
        "dayNo": day_no,
        "date": date,
        "message": message,
        "mood": str(mood_doc.get("mood", moods[0])),
        "energy": energy_value,
        "moods": moods,
        "traitsPicked": picked.get("picked", picked.get("traits", [])),
        "profile": identity_profile(pack_dir),
        "development": current_development,
        "life_story": life_story.context(pack_dir, message, policy=policy),
        "learning": learning.context(pack_dir, policy=policy, state=growth),
        "evidence": _evidence_memories(pack_dir, message, policy=policy, recalled=recalled, _lineage=story_links),
        "identity": read_text_safe(Path(pack_dir) / "genome" / "identity.md"),
        "values": read_text_safe(Path(pack_dir) / "genome" / "values.md"),
        "worldBible": read_text_safe(Path(pack_dir) / "world" / "bible.md"),
        "selfMd": read_text_safe(Path(pack_dir) / "mind" / "self.md") if not restricted_legacy else "",
        "beliefs": read_text_safe(Path(pack_dir) / "mind" / "beliefs.md") if not restricted_legacy else "",
        "memories": policy.visible(),
        "recalled": recalled,
        "retrieval_status": retrieval_status(pack_dir) if message else {"state": "not_used"},
        "facts": facts.context(pack_dir, message, policy=policy, references=[
            ref for item in recalled for ref in [item["memory"].get("id"), *item["memory"].get("event_ids", [])]]),
        "transcript": transcript,
        "current_evidence": [{"id": row["event_id"], "source": row["source"], "kind": "conversation"}
                             for row in transcript if row.get("event_id") and not is_template(row)][-6:],
        "senses": read_sense_lines(pack_dir, day_no) if current_source not in outdated_sources else [],
        "news": read_news_lines(pack_dir, day_no) if current_source not in outdated_sources else [],
        "interests": [item["topic"] for item in (_agency.get("interests") or [])[:5]],
        "boundaries": list(_agency.get("boundaries") or []),
        "plan": (str(_today_plan["plan"]) + "（" + plan_status(_today_plan,
                    outcomes=current_development["outcomes"], checkpoint=checkpoint) + "）") if _today_plan else "",
        "_plan_evidence": plan_refs,
        "_plan_checkpoint_dependencies": checkpoint.get("dependencies", []),
        "choice_pending": choice_pending,
        "daily_choice": {k: _today_plan.get(k, "") for k in ("mode", "goal_id", "plan_id")}
                        if _today_plan.get("origin") == "model" else {},
        "bond": bond_summary(pack_dir) if person_id == "owner" else {},
        "relationships": relationships.context(pack_dir, person_id, policy=policy, day=day_no),
        "works": works_summary(pack_dir),
        "memorial": memorial_summary(pack_dir, day_no),
        "inner": inner_summary(pack_dir, policy=policy, _lineage=story_links, for_context=True),
        "hands": hands_summary(pack_dir, day_no),
        "friends": friends_summary(pack_dir),
        "recentDays": [
            {"day": d["day"], "date": d["date"], "excerpt": _day_excerpt(pack_dir, d, policy=policy)}
            for d in recent_days
        ],
    }
    if person_id and person_id in facts.entities(pack_dir) and person_id not in {r["id"] for r in context["facts"]["entities"]}:
        context["facts"]["entities"].append({"id": person_id, "label": facts.entities(pack_dir)[person_id]})
    if restricted_legacy:
        # Legacy summaries have no source links. Preserve their files/UI, but do
        # not let these opaque summaries bypass recall suppression.
        context["interests"] = [p["topic"] for p in current_development["preferences"] if p["stance"] == "like"][:5]
        context["works"] = {}
        context["friends"] = {}
        context["memorial"] = {}
        if not _today_plan.get("goal_id") and _today_plan.get("origin") != "model":
            context["plan"] = ""
            context["daily_choice"] = {}
        affected_days = {int(match[1]) for source in outdated_sources
                         if (match := re.search(r"life/(\d+)-", source))}
        for group in ("bond", "hands"):
            for key, value in list(context[group].items()):
                if isinstance(value, list):
                    context[group][key] = [row for row in value if isinstance(row, dict)
                                          and row.get("made_day", row.get("created_day", row.get("day"))) not in affected_days]
    return context


def _memory_day(memory: dict) -> int:
    """坏数据兜底：day 被改成 null/字符串时不让她整个崩掉（check 会报出来）。"""
    try:
        return int(memory.get("day", 0))
    except (TypeError, ValueError):
        return 0


def _memory_key(text: str) -> str:
    """记忆去重用的归一化：忽略空白、标点、大小写。"""
    return re.sub(r"[\s\W_]+", "", str(text or "").lower())


# 弱模型爱写的废话，严格模式下不收。
_MEMORY_NOISE = re.compile(
    r"^(好|嗯|哦|收到|明白了|知道了|我记住了|我明白了|好的|ok|okay|谢谢)[。.!！？?…]*$",
    re.IGNORECASE,
)


def normalize_memory_writes(pack_dir, *, day_no, source, runner, default_kind, entries, at,
                            depends_on=(), event_ids=(), generation=None, trusted_kinds=False) -> list[dict]:
    """校验并规范化脑给出的记忆提案。运行器说了算。

    记忆卫生（mind/memory.json）：
    - strict=true：去重（忽略空白/标点）、丢弃太短的、丢弃「好/嗯/知道了」这类空话
    - daily_max：兼容旧设置名，每轮提炼最多写几条（默认 8）
    """
    if not isinstance(entries, list):
        return []
    policy = memory_settings(pack_dir)
    strict = bool(policy.get("strict", True))
    try:
        daily_max = int(policy.get("daily_max") or MEMORY_DAILY_BUDGET)
    except (TypeError, ValueError):
        daily_max = MEMORY_DAILY_BUDGET
    existing_all = read_memories(pack_dir)
    existing = len([m for m in existing_all if _memory_day(m) == int(day_no)])
    # The legacy setting now bounds a single extraction batch. Ordinary
    # earlier messages must not consume the whole day's ability to learn.
    budget = max(1, min(50, daily_max))
    # 只在「同一天内」去重：同一天别重复记同一句话，但隔天又想起同一件事是自然的。
    seen = {_memory_key(str(m.get("text") or "")) for m in existing_all if _memory_day(m) == int(day_no)} if strict else set()
    out: list[dict] = []
    for raw in entries:
        if len(out) >= budget:
            break
        if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
            continue
        text = raw["text"].strip()[:MEMORY_MAX_CHARS]
        if not text:
            continue
        # A model cannot promote an interpretation to a perception or create
        # recall-control events. Provenance belongs to the calling runtime.
        allowed = ALLOWED_KINDS - {"forget", "correction"} if trusted_kinds else ("thought", "feeling")
        kind = raw.get("kind") if raw.get("kind") in allowed else default_kind
        if kind == "forget":
            continue
        try:
            importance = float(raw.get("importance", 0.4))
            if not math.isfinite(importance):
                importance = 0.4
        except (TypeError, ValueError):
            importance = 0.4
        if importance < 0.3:
            continue
        if strict:
            key = _memory_key(text)
            if len(text) < 4 or not key:
                continue
            if key in seen:
                continue
            if _MEMORY_NOISE.match(text):
                continue
            seen.add(key)
        tags = []
        if isinstance(raw.get("tags"), list):
            tags = [str(t).strip()[:20] for t in raw["tags"] if str(t).strip()][:6]
        out.append({
            "id": f"m_{pad4(day_no)}_{existing + len(out) + 1}",
            "day": int(day_no),
            "at": at,
            "kind": kind,
            "text": text,
            "importance": round2(min(1.0, max(0.3, importance))),
            "tags": tags,
            "source": source,
            "runner": runner,
            "depends_on": sorted(set(str(ref) for ref in depends_on if ref)),
            "event_ids": list(event_ids),
            "generation": dict(generation or {}),
        })
    return out


def _apply_self_edits(pack_dir, edits) -> None:
    """Legacy ABI only. New self interpretations require development evidence."""
    return None


def _evidence_memories(pack_dir, message="", *, policy=None, recalled=None, _lineage=None):
    policy = policy if policy is not None else MemoryPolicy.load(pack_dir)
    if recalled is None:
        recalled = recall(pack_dir, message, RECALL_K, policy=policy)
    candidates = [row["memory"] for row in recalled] + policy.visible()[-8:]
    unique = {}
    for item in candidates:
        if (item.get("kind") not in ("forget", "dream", "creation") and "梦" not in (item.get("tags") or [])
                and not is_template(item)):
            unique[str(item.get("id"))] = item
    # Recent-memory fallback can replace a retrieved copy during deduplication.
    # Annotate after that merge so its fact corrections are not lost.
    from .story_lineage import Lineage
    lineage = _lineage if _lineage is not None else Lineage(pack_dir, policy)
    return lineage.annotate_many(facts.annotate_records(pack_dir, list(unique.values())[-16:], policy))


def _apply_learning(pack_dir, result, ctx, day, source, brain):
    from .disclosure import policy_for
    audience_id = ctx.get("_audience_id", "owner")
    policy = policy_for(pack_dir, audience_id, ctx.get("_person_id", ""))
    permitted = {r["id"] for bucket in ("beliefs", "preferences", "goals")
                 for r in ctx.get("development", {}).get(bucket, [])} if audience_id != "owner" else None
    actual_runner = generation_info(result, brain)["runner"]
    from . import life_story
    narrative_generation = {**generation_info(result, brain), "audience_id": audience_id, "disclosure_version": 1,
                            "context_dependencies": sorted(set(_context_dependencies(ctx))
                                | set(generation_info(result, brain).get("context_dependencies", []))
                                | {r["id"] for r in ctx.get("current_evidence", [])})}
    ctx["story_changes"] = life_story.apply_proposals(pack_dir, result.get("life_story"), ctx=ctx, generation=narrative_generation)
    changes = development.apply_proposals(
        pack_dir, result.get("development"), day=day["dayNo"], source=source,
        runner=actual_runner, memories=ctx.get("evidence", []),
        current_evidence=ctx.get("current_evidence"), generation=generation_info(result, brain),
        policy=policy, permitted_ids=permitted)
    shown_learning = result.get("_used_learning", ctx.get("learning", []))
    if not isinstance(shown_learning, list):
        shown_learning = []
    corrections = _apply_corrections(pack_dir, result, ctx, day, source, actual_runner)
    ctx["corrections_applied"] = corrections
    policy = policy_for(pack_dir, audience_id, ctx.get("_person_id", ""))
    from .goal_projects import apply as apply_project
    proposal = result.get("development")
    project = apply_project(pack_dir, proposal.get("project") if isinstance(proposal, dict) else None,
        ctx={**ctx, "learning": shown_learning}, day=day, generation=narrative_generation)
    changes.extend(project.pop("changes", []))
    ctx["project_decision"] = project
    if any(change["kind"] == "goal" for change in changes):
        plan_for_day(pack_dir, day["dayNo"], refresh=True)
    if any(change["kind"] == "preference" for change in changes):
        learn_from_day(pack_dir, day["dayNo"], day["date"])
    ctx["learning_changes"] = learning.apply_adjustments(pack_dir, result.get("learning_updates"),
                               available=[r["id"] for item in shown_learning for r in item.get("feedback", [])],
                               source=source, runner=actual_runner, day=day["dayNo"], generation=generation_info(result, brain), policy=policy)
    from .deliberation import apply as apply_daily_choice
    ctx["plan_decision"] = apply_daily_choice(pack_dir, result.get("daily_plan"), ctx={**ctx, "learning": shown_learning}, day=day,
        generation=generation_info(result, brain), goal_changes=changes)
    decision = ctx["plan_decision"]
    rejection = "本轮计划选择未采纳，相关行动未执行。" if decision.get("status") == "rejected" else ""
    from .actions import execute
    receipts = execute(pack_dir, result.get("actions"), day=day, source=source,
                       brain=brain, memories=ctx.get("evidence", []), evidence=ctx.get("current_evidence", []),
                       generation=generation_info(result, brain), person_id=ctx.get("_person_id", "owner"), audience_id=audience_id,
                       interaction_kind=ctx.get("interaction_kind", "direct"), blocked_reason=rejection)
    reports = []
    if project:
        project_text = ("分阶段安排已记录：" + project["title"] + "；各阶段仍需自己的成果与反馈。") if project["status"] == "accepted" else (
            "这份分阶段安排已经记录，未重复建立目标。" if project["status"] == "unchanged" else "分阶段安排未保存：" + project["reason"])
        reports.append({"who": "运行器", "text": project_text,
            "metadata": {**generation_info(result, brain), "runner": "runtime", "goal_project_status": project["status"]},
            "depends_on": [project["project_id"]] if project.get("project_id") else [r["id"] for r in ctx.get("current_evidence", [])]})
    if decision.get("status") in ("accepted", "rejected"):
        plan = decision.get("plan", {})
        reports.append({"who": "运行器", "text": ("今日选择已记录：" + plan["plan"] + "；安排不代表已经完成。")
                        if plan else "今日选择未采纳：" + decision["reason"],
                        "metadata": {**generation_info(result, brain), "runner": "runtime",
                                     "plan_decision_id": plan.get("decision_id", "")},
                        "depends_on": [r["id"] for r in plan.get("evidence", []) if r["id"] != "current"]})
    if receipts:
        reports.extend([{"who": "运行器", "text": "行动结果：" + row["data"]["detail"],
                                         "metadata": {**generation_info(result, brain), "runner": "runtime",
                                                      "action_outcome_id": row["id"]},
                                         "depends_on": development.outcome_dependencies({**row["data"], "source": row["source"]})}
                                          for row in receipts])
    report_events = []
    if reports:
        append_transcript(pack_dir, day, reports, recorded=report_events)
    ctx["_action_report_events"] = [row for row in report_events if row.get("metadata", {}).get("action_outcome_id")
                                   or row.get("metadata", {}).get("goal_project_status")]
    return changes, receipts


def generation_info(result, brain):
    metadata = dict((result or {}).get("_generation") or {})
    metadata.setdefault("runner", brain.name)
    return metadata


def _use_supplied_context(ctx, result):
    """Keep every source-bearing projection aligned with the fitted prompt."""
    result = result or {}
    for field, expected in (("evidence", list), ("learning", list), ("transcript", list), ("recalled", list), ("disclosed", list),
                            ("development", dict), ("facts", dict), ("practice", dict),
                            ("relationships", dict), ("life_story", dict), ("inner", dict)):
        value = result.get("_used_" + field)
        if isinstance(value, expected):
            ctx[field] = value
    if isinstance(result.get("_used_transcript"), list):
        shown = {row.get("event_id") for row in ctx["transcript"] if row.get("event_id")}
        ctx["current_evidence"] = [ref for ref in ctx.get("current_evidence", []) if ref["id"] in shown]


def _context_dependencies(ctx):
    refs = {str(m["id"]) for m in ctx.get("evidence", []) if m.get("id")}
    from .goal_history import context_dependencies as goal_history_dependencies
    refs.update(goal_history_dependencies(ctx))
    from .judgment_history import context_dependencies as judgment_history_dependencies
    refs.update(judgment_history_dependencies(ctx))
    for item in ctx.get("recalled", []):
        row = item["memory"]
        if row.get("id"):
            refs.add(str(row["id"]))
        refs.update(str(identifier) for identifier in row.get("event_ids", []))
    from .story_lineage import context_dependencies as story_dependencies
    refs.update(story_dependencies(ctx))
    from .inner_sources import context_dependencies as inner_dependencies
    refs.update(inner_dependencies(ctx.get("inner", {})))
    refs.update(r["id"] for r in ctx.get("disclosed", []))
    refs.update(r["id"] for r in ctx.get("_plan_evidence", []) if r.get("id") not in (None, "", "current"))
    refs.update(ctx.get("_plan_checkpoint_dependencies", []))
    for row in ctx.get("life_story", {}).get("chapters", []) + ctx.get("life_story", {}).get("previous_versions", []):
        refs.add(row["event_id"])
    for row in ctx.get("evidence", []) + ctx.get("transcript", []):
        for note in row.get("fact_notes", []):
            refs.update(note.get("evidence_ids", []))
    refs.update(str(row["event_id"]) for row in ctx.get("transcript", []) if row.get("event_id"))
    for group in ctx.get("facts", {}).get("groups", []):
        refs.update(group.get("temporal", {}).get("dependency_ids", []))
        refs.update(group.get("retraction_dependencies", []))
        for claim in group.get("claims", []):
            refs.update(ref["id"] for ref in claim.get("evidence", []))
        for decision in group.get("decisions", []):
            refs.update(ref["id"] for ref in decision.get("evidence", []))
    for item in ctx.get("learning", []) + ([ctx["practice"]] if ctx.get("practice") else []):
        refs.update(item.get("readiness", {}).get("dependencies", []))
        records = [item.get("criteria", {})] + item.get("feedback", []) + item.get("adjustments", []) + item.get("lessons", [])
        for row in records:
            refs.update(ref["id"] for ref in row.get("evidence", []))
            refs.update(ref["id"] for ref in row.get("observation_evidence", []))
    for bucket in ("notes", "issues", "agreements"):
        for row in ctx.get("relationships", {}).get(bucket, []):
            refs.update(ref["id"] for ref in row.get("evidence", []))
    for bucket in ("beliefs", "preferences", "goals"):
        for item in ctx.get("development", {}).get(bucket, []):
            refs.update(str(ref["id"]) for ref in item.get("evidence", []) if ref.get("id") != "current")
            for origin in item.get("provenance", {}).values():
                refs.update(origin.get("dependencies", []))
    for outcome in ctx.get("development", {}).get("outcomes", []):
        refs.update(development.outcome_dependencies(outcome))
    if ctx.get("development", {}).get("skills"):
        refs.update(ctx["development"].get("skill_dependencies", []))
    for review in ctx.get("development", {}).get("plan_review", []) + ctx.get("development", {}).get("prior_choices", []):
        refs.update(review.get("dependencies", []))
    return sorted(refs)


def _apply_corrections(pack, result, ctx, day, source, runner):
    applied = []
    available = {m["id"]: m for m in ctx.get("evidence", [])}
    for item in (result.get("corrections") or [])[:3]:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target_id") or "")
        if target not in available:
            continue
        if available[target].get("origin") in ("action_archive", "goal_archive", "judgment_archive"):
            # A runtime receipt and a historical reported reason are not a
            # factual claim the model can replace through memory correction.
            continue
        if ctx.get("_audience_id", "owner") != "owner":
            # An approved excerpt cannot be rewritten into a larger disclosure.
            from .disclosure import policy_for
            scoped = policy_for(pack, ctx["_audience_id"], ctx.get("_person_id", ""))
            if target in scoped.approved or not scoped.allows(available[target]):
                continue
        if facts.protects_source(pack, available[target]):
            # Structured disagreements require an explicit user decision;
            # replacing their entire source must not silently remove a side.
            continue
        try:
            row = revise_memory(pack, target, item.get("new"), reason=item.get("reason"),
                                day=day["dayNo"], source=source, runner=runner,
                                evidence=ctx.get("current_evidence", []),
                                change_type=item.get("change_type", "correction"), target_record=available[target],
                                generation=result.get("_generation") or {"runner": runner})
        except SeedError:
            continue
        if ctx.get("_audience_id", "owner") == "owner":
            correct_belief(pack, available[target]["text"], row["text"], day=day["dayNo"],
                           generation=row["generation"], depends_on=[row["id"]], source=source)
        applied.append(row)
    return applied


def sense_media(pack_dir, *, image=None, sound=None, note=None, vision=None, person_id="owner", audience_id=None, review_asset="", request_id="", before_process=None) -> dict:
    """Accept media independently before attempting its interpretation."""
    if not review_asset and (image is not None or sound is not None):
        from .media_intake import submit
        return submit(pack_dir, image=image, sound=sound, note=note, vision=vision, person_id=person_id,
                      audience_id=audience_id, request_id=request_id, before_process=before_process)
    if before_process is not None:
        before_process()
    return _sense_media(pack_dir, image=image, sound=sound, note=note, vision=vision, person_id=person_id,
                        audience_id=audience_id, review_asset=review_asset)


@durable
def _sense_media(pack_dir, *, image=None, sound=None, note=None, vision=None, person_id="owner", audience_id=None, review_asset="", intake=None) -> dict:
    """让她看一张图 / 听一段声音 / 听主人说一句话。

    感官是新生儿就有的：她感到光和声音，但还认不出图里有什么。
    原始文件保存在生命包里；收到材料与解释材料分开记录。

    1.22 起看图是自动的：给了图就试着让脑「看懂」；脑没有视觉能力时安静退回
    原生光感，不写多余的提示。（vision=False 仅供程序显式跳过。）
    """
    require_active(pack_dir)
    if not image and not sound and not note and not review_asset and not intake:
        raise ValueError("至少要给她看一张图、听一段声音，或留一句话。")
    pack = Path(expand_home(pack_dir))
    from .disclosure import audience, stamp
    from . import media_archive
    from .durability import _safe_path
    if intake:
        if image or sound or review_asset:
            raise SeedError("已接收材料不能同时混入新文件或重新理解请求。")
        image = _safe_path(pack.resolve(), intake["assets"]["image"]["blob"]) if "image" in intake["assets"] else None
        sound = _safe_path(pack.resolve(), intake["assets"]["sound"]["blob"]) if "sound" in intake["assets"] else None
    reviewed = None
    if review_asset:
        if image or sound:
            raise SeedError("重新查看已有材料时不能同时接收新文件。")
        reviewed = media_archive.detail(pack, review_asset)
        if reviewed["state"] != "available" or reviewed["media_kind"] != "image":
            raise SeedError("这份材料当前不可用于重新理解。")
        image = _safe_path(pack.resolve(), reviewed["blob"])
        # Archive review is a local owner's action. An originally shared image
        # does not make a new private note or interpretation visible to its group.
        person_id, audience_id = "owner", "owner"
    audience_id = audience(person_id, audience_id)
    if person_id:
        relationships.person(pack, person_id)
    birth = read_json(pack / "birth.json")
    if not birth:
        raise ValueError(f"不是生命包（缺 birth.json）：{pack}")
    day = open_day(pack)
    file = pack / "life" / _memory_filename(day["dayNo"], day["date"])
    text = read_text_safe(file).rstrip()
    if not text:
        text = f"# 第 {pad4(day['dayNo'])} 天 · {day['date']}"

    lines: list[str] = []
    entries: list[dict] = []
    assets = []
    source = f"life/{_memory_filename(day['dayNo'], day['date'])}"
    generation = {"runner": "sense-v2", **stamp(audience_id), "person_id": person_id}
    if intake:
        generation["intake_id"] = intake["id"]
        generation["received_at"] = intake["payload"]["received_at"]
    notes = str(note or "").strip()
    note_event = None
    if intake and intake["payload"]["note_event_id"]:
        note_event = next(e for e in experience.read(pack) if e["id"] == intake["payload"]["note_event_id"])
    elif notes:
        note_event = experience.record(pack, kind="conversation", text=f"{'主人' if person_id == 'owner' else '当前交流对象'}说：{notes}",
                                       day=day["dayNo"], source=source, actor="user", metadata=generation)
    image_refs = []
    image_metadata = {}
    if image:
        if reviewed:
            asset = reviewed
            review_event = experience.record(pack, kind="media_review", text=f"重新查看收到于 {asset['at']} 的图片：{asset['name']}。这不是一次新拍摄。",
                day=day["dayNo"], source=source, actor="user", depends_on=[asset["event_id"]],
                metadata={**generation, "asset_id": asset["id"], "received_at": asset["at"],
                          "received_audience_id": asset["audience_id"]})
            image_refs = [asset["event_id"], review_event["id"]]
            lines.append(review_event["text"])
        elif intake:
            asset = intake["assets"]["image"]
            image_refs = [asset["event_id"]]
        else:
            asset, image, _ = media_archive.capture(pack, image, kind="image", day=day["dayNo"], source=source,
                                                  audience_id=audience_id, person_id=person_id)
            image_refs = [asset["event_id"]]
        assets.append(asset["id"])
        image_metadata = {"asset_id": asset["id"], "received_at": asset["at"], "review": bool(reviewed),
                          "received_audience_id": asset["audience_id"]}
    vision_result = {"attempted": False, "ok": None}
    legacy_whale = audience_id == "owner" and (birth.get("species") or {}).get("id") == "dafeiyu"
    if image:
        analysis = analyze_image(image)
        if analysis.get("sha256") != asset["sha256"]:
            raise SeedError("图片分析期间原件发生变化，未保存解释。")
        if analysis.get("readable", True):
            desc = describe_image(analysis)
            if not legacy_whale:
                desc = [f"图像平均亮度 {analysis['brightness']:.2f}，明暗差异 {analysis['contrast']:.2f}（0～1）。这只是像素分析，尚未识别画面内容。"]
            meta = f"{analysis['width']}×{analysis['height']} 的图，指纹 {analysis['sha256'][:8]}"
            lines.append(f"光：{desc[0]}（{meta}）")
            entries.append({
                "kind": "perception",
                "text": f"我看见了光：{desc[0]}" if legacy_whale else f"收到图像分析：{desc[0]}",
                "importance": 0.5,
                "tags": ["感知", "光"],
                "depends_on": image_refs, "metadata": {**image_metadata, "interpretation": "pixel_analysis"},
            })
        else:
            lines.append(f"光：{describe_image(analysis)[0]}（指纹 {analysis['sha256'][:8]}）")
            entries.append({
                "kind": "perception",
                "text": "我想看清一张图，但只看见一片模糊。" if legacy_whale else "收到一张图片，当前图像分析器未能解析。",
                "importance": 0.35,
                "tags": ["感知", "光"],
                "depends_on": image_refs, "metadata": {**image_metadata, "interpretation": "pixel_analysis"},
            })
        if vision is not False:
            # 原生分析先做完（保底），再试可选的视觉翻译；翻译成功才落一行字。
            translated = vision_translate(pack, image, note=note or "")
            if translated.get("ok"):
                if translated.get("sha256") and translated["sha256"] != asset["sha256"]:
                    raise SeedError("视觉模型读取的图片与原件不同，未保存解释。")
                seen = translated["text"]
                provider = translated.get("provider") or "?"
                model = translated.get("model") or "?"
                fingerprint = str(analysis.get("sha256") or "")[:8]
                lines.append(f"看：{seen}（{provider}·{model} 翻译，指纹 {fingerprint}）")
                entries.append({
                    "kind": "perception",
                    "text": f"我看懂了：{seen}" if legacy_whale else f"视觉模型对图片的解释（可能有误）：{seen}",
                    "importance": 0.6,
                    "tags": ["感知", "看懂"],
                    "depends_on": image_refs + ([note_event["id"]] if note_event else []),
                    "metadata": {**image_metadata, "interpretation": "vision_model", "provider": provider, "model": model},
                })
                vision_result = {
                    "attempted": True,
                    "ok": True,
                    "text": seen,
                    "provider": provider,
                    "model": model,
                    "ms": translated.get("ms", 0),
                }
            else:
                # 1.22：没有视觉能力时安静退回原生光感，不往她的一天里写噪声。
                reason = str(translated.get("reason") or "翻译没成")
                vision_result = {"attempted": True, "ok": False, "reason": reason}
    if sound:
        if intake:
            sound_asset = intake["assets"]["sound"]
        else:
            sound_asset, sound, _ = media_archive.capture(pack, sound, kind="sound", day=day["dayNo"], source=source,
                                                         audience_id=audience_id, person_id=person_id)
        assets.append(sound_asset["id"])
        analysis = analyze_sound(sound)
        if analysis.get("sha256") != sound_asset["sha256"]:
            raise SeedError("声音分析期间原件发生变化，未保存解释。")
        desc = describe_sound(analysis)
        meta = f"指纹 {analysis['sha256'][:8]}"
        lines.append(f"声：{desc[0]}（{meta}）")
        entries.append({
            "kind": "perception",
            "text": f"我听见了：{desc[0]}",
            "importance": 0.45,
            "tags": ["感知", "声"],
            "depends_on": [sound_asset["event_id"]],
            "metadata": {"asset_id": sound_asset["id"], "received_at": sound_asset["at"], "interpretation": "sound_analysis"},
        })
    if note_event:
        lines.append(f"{'主人' if person_id == 'owner' else '当前交流对象'}：{notes}")
        entries.append({"kind": "conversation", "text": f"{'主人' if person_id == 'owner' else '当前交流对象'}说：{notes}", "importance": 0.45,
                        "tags": ["感知"], "event": note_event, "depends_on": []})
    if reviewed:
        lines = [f"旧图（收到于 {reviewed['at']}）的本次回看：{line}" for line in lines]
        for entry in entries:
            if entry["kind"] == "perception":
                entry["text"] = f"重新理解收到于 {reviewed['at']} 的旧图：" + entry["text"]
    if intake and intake["payload"]["date"] != day["date"]:
        received = intake["payload"]["received_at"]
        lines = [f"材料（收到于 {received}）的本次处理：{line}" for line in lines]
        for entry in entries:
            if entry["kind"] == "perception":
                entry["text"] = f"对收到于 {received} 的材料进行分析：" + entry["text"]
            else:
                entry["text"] = f"收到于 {received} 的随附说明：" + entry["text"]

    text = _ensure_bullet_section(text, "感知", lines)
    write_file_atomic(file, text.rstrip() + "\n")
    at = now_iso()
    writes = []
    event_ids = []
    try:
        maximum = max(1, min(50, int(memory_settings(pack).get("daily_max") or MEMORY_DAILY_BUDGET)))
    except (ValueError, TypeError):
        maximum = MEMORY_DAILY_BUDGET
    for entry in entries:
        metadata = {**generation, **entry.get("metadata", {}), "context_dependencies": entry.get("depends_on", [])}
        event = entry.get("event") or experience.record(pack, kind=entry["kind"], text=entry["text"], day=day["dayNo"],
            source=source, actor="perception", depends_on=entry.get("depends_on", []), metadata=metadata)
        event_ids.append(event["id"])
        if len(writes) < maximum:
            extracted = normalize_memory_writes(pack, day_no=day["dayNo"], source=experience.source_of(event), runner="sense-v2",
                default_kind="perception", entries=[entry], at=at, trusted_kinds=True,
                event_ids=[event["id"]], depends_on=[event["id"]], generation=metadata)
            append_memories(pack, extracted)
            writes.extend(extracted)
    _append_journal(pack, {"day": day["dayNo"], "at": at, "mode": "sense", "brain": "sense-v2", "memories": len(writes)})
    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": source,
        "lines": lines,
        "memoriesAdded": len(writes),
        "vision": vision_result,
        "assets": assets,
        "event_ids": event_ids,
    }


def _clean_feed_items(items, source: str) -> list[dict]:
    """把载体送来的见闻整理成 [{text, source}]：去空、去重、截断、限量。

    见闻是「她读到的」东西，不是她亲历的。载体只该送来筛选过的摘要，
    不该送来整页群聊或全文文章——这里也会再截一次。
    """
    if isinstance(items, (str, dict)):
        items = [items]
    if not isinstance(items, list):
        raise SeedError("见闻要是一行行文字，或者 [{text, source}] 的列表。")
    out: list[dict] = []
    seen: set[str] = set()
    for raw in items:
        if isinstance(raw, str):
            text, raw_source = raw, source
        elif isinstance(raw, dict):
            text = raw.get("text") or raw.get("title") or ""
            raw_source = raw.get("source") if raw.get("source") is not None else source
        else:
            continue
        text = " ".join(str(text).split()).strip()[:NEWS_MAX_CHARS]
        if not text:
            continue
        src = " ".join(str(raw_source).split()).strip()[:40] or "某个地方"
        key = _memory_key(text)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "source": src})
        if len(out) >= NEWS_MAX_ITEMS:
            break
    return out


@durable
def feed_news(pack_dir, items, *, source: str = "主人", at: str | None = None) -> dict:
    """让她读一段见闻（新闻、群聊摘要、主人讲外面的事）。

    只写「她读到的」：当天 life/ 的 `## 见闻` 段 + 一条 kind=hearsay 的记忆。
    原文不落盘，只留摘要和来源；之后照常会遗忘、会被加权重估。
    """
    require_active(pack_dir)
    pack = Path(expand_home(pack_dir))
    birth = read_json(pack / "birth.json")
    if not birth:
        raise ValueError(f"不是生命包（缺 birth.json）：{pack}")
    cleaned = _clean_feed_items(items, source)
    if not cleaned:
        raise ValueError("没有可读的见闻：一行字都没有。")

    day = open_day(pack)
    file = pack / "life" / _memory_filename(day["dayNo"], day["date"])
    text = read_text_safe(file).rstrip()
    if not text:
        text = f"# 第 {pad4(day['dayNo'])} 天 · {day['date']}"
    lines = [f"{item['text']}（来源：{item['source']}）" for item in cleaned]
    text = _append_news(text, lines)
    write_file_atomic(file, text.rstrip() + "\n")

    source_file = f"life/{_memory_filename(day['dayNo'], day['date'])}"
    at = at or now_iso()
    writes = normalize_memory_writes(
        pack,
        day_no=day["dayNo"],
        source=source_file,
        runner="feed-v1",
        default_kind="hearsay",
        entries=[
            {
                "kind": "hearsay",
                "text": f"我读到：{item['text']}（来源：{item['source']}）",
                "importance": 0.3,
                "tags": ["见闻", item["source"]],
            }
            for item in cleaned
        ],
        at=at,
    )
    append_memories(pack, writes)
    _append_journal(pack, {"day": day["dayNo"], "at": at, "mode": "feed", "brain": "feed-v1", "memories": len(writes)})
    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": source_file,
        "lines": lines,
        "items": cleaned,
        "memoriesAdded": len(writes),
    }


@serialized
@model_budget.operation
def chat_turn(pack_dir, message: str, brain, speaker: str = "主人", *, request_id="", person_id=None, interaction_kind="direct", audience_id=None) -> dict:
    require_active(pack_dir)
    from .requests import run
    text = str(message or "").strip()
    if not text or len(text) > 2000:
        raise SeedError("消息不能为空，也不能超过 2000 字。")
    speaker = str(speaker or "主人").replace("**", "").replace("\n", " ").strip()[:20] or "主人"
    if speaker == "owner":
        speaker = "主人"
    if person_id is not None and not isinstance(person_id, str):
        raise SeedError("人物编号应为字符串，未知身份可留空。")
    resolved = person_id if person_id is not None else ("owner" if speaker == "主人" else "")
    if resolved:
        relationships.person(pack_dir, resolved)
    if interaction_kind not in ("direct", "reported"):
        raise SeedError("对话来源类型无效。")
    payload = {"kind": "chat", "text": text, "speaker": speaker}
    # Keep legacy/default request fingerprints stable for retries.
    if person_id is not None:
        payload["person_id"] = resolved
    if interaction_kind != "direct":
        payload["interaction_kind"] = interaction_kind
    from . import disclosure
    import uuid
    request_id = str(request_id or "chat_" + uuid.uuid4().hex)
    target = disclosure.audience(resolved, audience_id, request_id, interaction_kind=interaction_kind)
    if audience_id is not None:
        payload["audience_id"] = target
    result = run(pack_dir, payload, lambda: _chat_turn(pack_dir, text, brain, speaker,
                 person_id=resolved, interaction_kind=interaction_kind, audience_id=target), request_id=request_id)
    if target != "owner":
        policy = disclosure.policy_for(pack_dir, target, resolved)
        report_ids = result.get("actionReportEventIds", [])
        if not isinstance(report_ids, list) or any(not isinstance(ref, str) for ref in report_ids):
            raise SeedError("这条历史回复的行动回执信息不完整；请用新的请求重新交流。")
        events = [policy.nodes.get(ref) for ref in [result.get("responseEventId"), *report_ids]]
        if any(not event or not policy.allows(event) for event in events):
            raise SeedError("这条历史回复的分享依据已变化，不能再次向外提供；请用新的请求重新交流。")
    return result


def _chat_turn(pack_dir, message: str, brain, speaker: str = "主人", *, person_id="owner", interaction_kind="direct", audience_id="owner") -> dict:
    """和她说话（一个回合）。

    流程：取上下文 → 问脑 → 校验 → 追加对话 → 写记忆 → 记日志。
    speaker 是说话的人：默认「主人」；经过载体的访客可以传自己的名字。
    """
    if brain is None:
        raise ValueError("chat_turn 需要一个脑")
    text = str(message or "").strip()
    if not text:
        raise ValueError("想对她说的话不能为空")
    if len(text) > 2000:
        raise ValueError("一条消息最多 2000 字")
    speaker = str(speaker or "主人").replace("**", "").replace("\n", " ").strip()[:20] or "主人"

    day = open_day(pack_dir)
    ctx = build_context(pack_dir, day["dayNo"], day["date"], message=text,
                        use_semantic=not str(getattr(brain, "name", "")).startswith("stub"), person_id=person_id,
                        audience_id=audience_id, interaction_kind=interaction_kind)
    ctx["speaker"] = speaker
    ctx["interaction_kind"] = interaction_kind
    result = brain.chat(ctx)
    _use_supplied_context(ctx, result)
    reply = str((result or {}).get("reply", "")).strip()
    if not reply:
        raise ValueError("脑没有给出回复")

    from .presentation import normalize as normalize_presentation
    presentation = normalize_presentation(result.get("presentation"))

    generation = generation_info(result, brain)
    from .disclosure import stamp
    generation.update(stamp(audience_id))
    generation["proposal_activity"] = "conversation"
    generation["context_dependencies"] = _context_dependencies(ctx)
    result["_generation"] = generation
    recorded = []
    source = append_transcript(pack_dir, day, [
        {"who": speaker, "text": text, "metadata": {"person_id": person_id, "interaction_kind": interaction_kind,
                                                     "identity_basis": "channel_assignment", **stamp(audience_id)}},
        {"who": "fish", "text": reply, "depends_on": _context_dependencies(ctx),
         "metadata": {**generation, "presentation": presentation}},
    ], recorded=recorded)
    current = recorded[0]
    generation["context_dependencies"] = sorted(set(generation["context_dependencies"]) | {recorded[1]["id"]})
    ctx["current_evidence"] = [{"id": current["id"], "source": experience.source_of(current),
                                "kind": "conversation"}]
    memory_source = experience.source_of(current)
    at = now_iso()
    writes = normalize_memory_writes(
        pack_dir,
        day_no=day["dayNo"],
        source=memory_source,
        runner=generation["runner"],
        default_kind="conversation",
        entries=(result or {}).get("memory_writes"),
        at=at,
        depends_on=_context_dependencies(ctx), event_ids=[event["id"] for event in recorded], generation=generation,
    )
    append_memories(pack_dir, writes)
    if person_id == "owner" and interaction_kind == "direct" and audience_id == "owner":
        register_talk(pack_dir, day["dayNo"], name="主人")

    fact_changes = facts.apply_proposals(
        pack_dir, (result or {}).get("fact_claims"), event=current,
        allowed_entities=[row["id"] for row in ctx.get("facts", {}).get("entities", [])] if person_id else [],
        runner=generation["runner"], generation=generation)
    relationships.apply_observations(pack_dir, (result or {}).get("relationship_notes"), event=current,
                                    person_id=person_id, runner=generation["runner"], generation=generation)

    # 1.17 手：今天到期的提醒，这次对话里她会说出来（标记为说过，不再重复）
    for reminder in (due_reminders(pack_dir, day["dayNo"]) if audience_id == "owner" else []):
        # Calendar reminders require an explicit local reminder record or manual
        # acknowledgement. Merely quoting the text is not such a record.
        if reminder.get("due_on"):
            continue
        if str(reminder.get("text") or "").strip() not in reply:
            continue
        try:
            mark_said(pack_dir, reminder["id"], day["dayNo"], via="local_transcript")
        except SeedError:
            break

    # 1.17 手：她答应替你记着的事（只收「记着」动作）
    body.spend(pack_dir, "chat")
    changes, actions = _apply_learning(pack_dir, result or {}, ctx, day,
                                      experience.source_of(recorded[1]) if audience_id != "owner" else source, brain)
    corrections = ctx.get("corrections_applied", [])

    _append_journal(pack_dir, {"day": day["dayNo"], "at": at, "mode": "chat", "brain": generation["runner"],
                               "generation": generation, "memories": len(writes),
                               "activity_budget": model_budget.snapshot()})

    action_reports = ctx.get("_action_report_events", [])
    delivered_reply = reply
    if action_reports:
        # Carriers such as QQ (including private chats) deliver only `reply`.
        # Include runtime results so
        # a proposed action cannot silently appear to have been carried out.
        delivered_reply += "\n\n" + "\n".join("[运行器回执] " + row["text"] for row in action_reports)

    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": source,
        "reply": delivered_reply,
        "presentation": presentation,
        "responseEventId": recorded[1]["id"],
        "actionReportEventIds": [row["id"] for row in action_reports],
        "memoriesAdded": len(writes),
        "corrections": len(corrections),
        "actions": len(actions),
        "developmentChanges": len(changes),
        "factsAdded": len(fact_changes["added"]),
        "factProposalsRejected": fact_changes["rejected"],
        "actionResults": actions,
        "lifeStoryChanges": len(ctx.get("story_changes", [])),
        "planDecision": ctx.get("plan_decision", {}),
        "goalProject": ctx.get("project_decision", {}),
        "modelBudget": model_budget.snapshot(),
    }


@durable
@model_budget.operation
def maybe_initiate(pack_dir, brain=None, *, now=None, idle_seconds: int = 2 * 60 * 60, max_per_day: int = 3, force: bool = False) -> dict | None:
    """一次自主机会：可以安静整理、行动、说话，也可以不作变化。

    只有非空 reply 写入带主动落款的对话；私人提案仍需正常来源校验。
    返回 None 表示没有受支持的提案或发言。`force=True` 仅用于测试/演示。
    """
    if not life_active(pack_dir):
        return None
    if not relationships.may_initiate(pack_dir, "owner"):
        return None
    if silence_active(pack_dir) and not force:
        return None
    if force:
        day = open_day(pack_dir)
        decision = {"day": day["dayNo"], "date": day["date"], "plan": "", "interest": ""}
    else:
        decision = should_initiate(pack_dir, now=now, idle_seconds=idle_seconds, max_per_day=max_per_day)
        if not decision:
            return None
        day = {"dayNo": decision["day"], "date": decision["date"], "open": True}
    ctx = build_context(pack_dir, day["dayNo"], day["date"])
    decision = {**decision, "plan": ctx.get("plan", ""),
                "interest": decision.get("interest", "") if decision.get("interest") in ctx.get("interests", []) else ""}
    ctx["initiative"] = decision
    brain = brain or create_brain(pack_dir)
    result = brain.chat(ctx) or {}
    _use_supplied_context(ctx, result)
    generation = generation_info(result, brain)
    from .disclosure import stamp
    generation.update(stamp(ctx.get("_audience_id", "owner")))
    generation["proposal_activity"] = "forced_initiative" if force else "initiative"
    generation["context_dependencies"] = _context_dependencies(ctx)
    result["_generation"] = generation
    reply = str(result.get("reply", "")).strip()
    # Silence is a communication choice. Sourced private learning, recollection
    # and interpretation proposals still use the normal validation/write path.
    pending = any(result.get(field) for field in (
        "actions", "development", "memory_writes", "learning_updates", "life_story", "corrections"))
    if not reply and not pending and result.get("daily_plan") is None:
        record_initiation(pack_dir, now=now, day_no=day["dayNo"])
        return None
    if reply:
        recorded = []
        source = append_transcript(pack_dir, day, [{"who": "fish", "initiated": True, "text": reply,
                                                   "depends_on": _context_dependencies(ctx), "metadata": generation}], recorded=recorded)
        ctx["current_evidence"] = [{"id": event["id"], "source": experience.source_of(event), "kind": "conversation"} for event in recorded]
        generation["context_dependencies"] = sorted(set(generation["context_dependencies"]) | {r["id"] for r in recorded})
    else:
        ctx["current_evidence"] = []
        start_day(pack_dir)
        source = f"life/{_memory_filename(day['dayNo'], day['date'])}"
    at = now_iso()
    writes = normalize_memory_writes(
        pack_dir,
        day_no=day["dayNo"],
        source=source,
        runner=generation["runner"],
        default_kind="thought",
        entries=result.get("memory_writes"),
        at=at,
        depends_on=_context_dependencies(ctx), generation=generation,
    )
    append_memories(pack_dir, writes)
    body.spend(pack_dir, "initiate")
    changes, actions = _apply_learning(pack_dir, result, ctx, day, source, brain)
    record_initiation(pack_dir, now=now, day_no=day["dayNo"])
    _append_journal(pack_dir, {
        "day": day["dayNo"],
        "at": at,
        "mode": "initiate",
        "brain": generation["runner"],
        "generation": generation,
        "plan": decision.get("plan") or "",
        "memories": len(writes),
        "learning_changes": len(ctx.get("learning_changes", [])),
        "life_story_changes": len(ctx.get("story_changes", [])),
        "corrections": len(ctx.get("corrections_applied", [])),
        "activity_budget": model_budget.snapshot(),
    })
    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": source,
        "reply": reply,
        "plan": str(decision.get("plan") or ctx.get("plan") or ""),
        "interest": decision.get("interest") or "",
        "memoriesAdded": len(writes),
        "developmentChanges": len(changes),
        "learningChanges": len(ctx.get("learning_changes", [])),
        "lifeStoryChanges": len(ctx.get("story_changes", [])),
        "corrections": len(ctx.get("corrections_applied", [])),
        "actionResults": actions,
        "planDecision": ctx.get("plan_decision", {}),
        "modelBudget": model_budget.snapshot(),
    }


class _ComposeFailure(SeedError):
    """An unsuccessful adapter invocation, without persisting provider diagnostics."""

    def __init__(self, kind, detail):
        super().__init__(detail)
        self.kind = kind


@durable
def _compose_response(pack_dir, brain, ctx):
    # A failed adapter must not leave partial local writes. Storage failures
    # after a valid response are deliberately outside this handler.
    from .brain import BrainConfigError
    from .context_window import ContextBudgetError
    try:
        result = brain.compose(ctx)
    except (RecoveryRequired, BrainConfigError, ContextBudgetError):
        raise
    except (RuntimeError, ValueError, OSError):
        raise _ComposeFailure("adapter_error", "创作适配器未返回可用作品；这不代表创作能力不足。") from None
    if not isinstance(result, dict) or not isinstance(result.get("_generation", {}), dict):
        raise _ComposeFailure("invalid_output", "创作返回的格式无法使用，本次没有保存作品。")
    generation = result.get("_generation", {})
    if generation.get("fallback"):
        raise _ComposeFailure("fallback", "创作服务退回了模板内容，本次没有把模板保存为作品。")
    if generation.get("runtime_guard"):
        raise _ComposeFailure("runtime_guard", "创作由运行器中止，本次没有保存作品。")
    if not isinstance(result.get("text"), str) or not result["text"].strip():
        raise _ComposeFailure("empty_output", "本次创作没有返回作品正文，无法判断具体原因。")
    return result


def _record_compose_failure(pack_dir, failure, *, ctx, day, kind, goal_id, plan_reference):
    from .disclosure import stamp
    # These are the references available before dispatch, not a claim about
    # the fitted prompt or the model's use of any feedback or strategy.
    generation = {"runner": "runtime", "operation": "compose", "failure_kind": failure.kind,
                  "context_scope": "available_at_execution", "context_dependencies": _context_dependencies(ctx),
                  **stamp(ctx["_audience_id"])}
    source = f"life/{_memory_filename(day['dayNo'], day['date'])}"
    event = experience.record(pack_dir, kind="action_attempt", text=str(failure), day=day["dayNo"],
                              source=source, actor="runtime", depends_on=_context_dependencies(ctx), metadata=generation)
    practice = {"criteria_id": ctx.get("practice", {}).get("criteria", {}).get("id", ""),
                "task": dict(ctx["compose"]), "scope": "available_at_execution"}
    receipt = development.record_outcome(pack_dir, action="compose", status="failed", attempt_state="started",
        detail=str(failure), day=day["dayNo"], source=experience.source_of(event), goal_id=goal_id,
        evidence=[{"id": event["id"], "source": experience.source_of(event), "kind": event["kind"]}],
        generation=generation, practice=practice, plan_reference=plan_reference)
    return {"succeeded": False, "dayNo": day["dayNo"], "date": day["date"], "file": source,
            "kind": kind, "entry": None, "receipt": receipt, "error": str(failure)}


@durable
@model_budget.operation
def compose_work(pack_dir, kind: str = "poem", brain=None, *, title: str = "", day: dict | None = None,
                 topic: str = "", goal_id: str = "", person_id="owner", audience_id=None, interaction_kind="direct",
                 _plan_reference=None, _action_proposal=None) -> dict:
    """Save a work and receipt, or a terminal failed attempt for a direct request.

    Automatic actions own their failure receipt. Preparation/storage failures
    still raise, leaving an enclosing durable request pending for explicit recovery.
    """
    require_active(pack_dir)
    if day is None:
        day = start_day(pack_dir)
    from .works import _clean_kind
    kind = _clean_kind(kind)
    if body.state(pack_dir)["energy"] < 0.15:
        raise SeedError("当前精力不足，先休息后再创作。")
    ctx = build_context(pack_dir, day["dayNo"], day["date"], person_id=person_id, audience_id=audience_id, interaction_kind=interaction_kind)
    ctx["interaction_kind"] = interaction_kind
    from .disclosure import policy_for, stamp
    policy = policy_for(pack_dir, ctx["_audience_id"], person_id)
    from .plan_links import capture
    plan_reference = capture(pack_dir, day["dayNo"], execution="requested", audience_id=ctx["_audience_id"]) \
        if _plan_reference is None else _plan_reference
    ctx["compose"] = {"kind": str(kind or "poem"), "topic": topic}
    # Cross-task candidates belong to this task's practice block. General goal
    # context must not duplicate candidates from unrelated active goals.
    ctx["learning"] = [{k: v for k, v in item.items() if k != "lessons"} for item in ctx.get("learning", [])]
    prerequisite_check, prerequisite_evidence = {}, []
    if goal_id:
        goal = development.current_state(pack_dir, policy=policy)["goals"].get(goal_id)
        if not goal or goal["status"] != "active":
            raise SeedError("这个目标不存在、已暂停或依据不可用。")
        from .goal_dependencies import readiness, BLOCKED, EXTERNAL_BLOCKED
        private = learning.view(pack_dir) if ctx["_audience_id"] != "owner" else learning.view(pack_dir, policy=policy)
        if not readiness(pack_dir, goal_id, loaded=private)["ready"]:
            raise SeedError(BLOCKED if ctx["_audience_id"] == "owner" else EXTERNAL_BLOCKED)
        from .goal_dependencies import execution_reference
        prerequisite_check, prerequisite_evidence = execution_reference(pack_dir, goal_id, loaded=private)
        ctx["practice"] = learning.for_goal(pack_dir, goal_id, loaded=learning.view(pack_dir, policy=policy), task=ctx["compose"])
        # This goal's full standards/feedback are already in the task block.
        # Duplicating them in the general summary exhausted the default budget
        # and discarded the very feedback requested for the next attempt.
        ctx["learning"] = [item for item in ctx["learning"] if item.get("goal_id") != goal_id]
    if brain is None:
        brain = create_brain(pack_dir)
    try:
        result = _compose_response(pack_dir, brain, ctx)
    except _ComposeFailure as failure:
        if _plan_reference is not None:
            raise
        return _record_compose_failure(pack_dir, failure, ctx=ctx, day=day, kind=kind,
                                       goal_id=goal_id, plan_reference=plan_reference)
    _use_supplied_context(ctx, result)
    text = str(result.get("text", "")).strip()
    final_title = str(title or result.get("title") or "无题").strip() or "无题"
    entry = add_work(pack_dir, kind, text, title=final_title, day=day["dayNo"])
    generation = generation_info(result, brain)
    from .learning_choices import collect as collect_choices
    practice = learning.practice_reference(ctx.get("practice", {}), "provided_to_creator", task=ctx["compose"],
                                           additional=ctx.get("learning", []))
    if practice:
        practice["strategy_choices"] = collect_choices(result.get("strategy_choices"), ctx.get("practice", {}), generation)
        generation["strategy_choices"] = practice["strategy_choices"]
    generation.update(stamp(ctx["_audience_id"]))
    generation["context_dependencies"] = _context_dependencies(ctx)
    created = experience.record(pack_dir, kind="creation", text=entry["title"] + "\n" + entry["text"],
                                day=day["dayNo"], source=f"life/{_memory_filename(day['dayNo'], day['date'])}",
                                actor=ctx["name"], depends_on=_context_dependencies(ctx) + [ref["id"] for ref in prerequisite_evidence],
                                metadata={**generation, **({"prerequisite_check": prerequisite_check} if prerequisite_check else {})})
    body.spend(pack_dir, "compose")
    receipt = development.record_outcome(
        pack_dir, action="compose", status="succeeded", detail=f"已保存作品：{entry['title']}。",
        day=day["dayNo"], source=experience.source_of(created),
        goal_id=goal_id, artifact="mind/works.json#" + entry["id"], generation=generation,
        evidence=[{"id": created["id"], "source": experience.source_of(created), "kind": "creation"}],
        practice=practice, plan_reference=plan_reference, proposal=_action_proposal)
    label = {"poem": "诗", "letter": "信", "drawing": "画"}.get(str(kind).lower(), "作品")
    measure = {"poem": "首诗", "letter": "封信", "drawing": "幅画"}.get(str(kind).lower(), "件作品")
    try:
        writes = normalize_memory_writes(
            pack_dir,
            day_no=day["dayNo"],
            source=f"life/{_memory_filename(day['dayNo'], day['date'])}",
            runner=generation["runner"],
            default_kind="thought",
            entries=[{
                "text": f"我写了一{measure}：{entry['title']}",
                "importance": 0.55,
                "tags": ["作品", label],
            }],
            at=now_iso(),
            depends_on=_context_dependencies(ctx), event_ids=[created["id"]], generation=generation,
        )
        append_memories(pack_dir, writes)
    except RecoveryRequired:
        raise
    except SeedError:
        pass
    _append_journal(pack_dir, {"day": day["dayNo"], "at": now_iso(), "mode": "work", "kind": kind,
                               "brain": generation["runner"], "generation": generation})
    return {
        "succeeded": True,
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": f"life/{_memory_filename(day['dayNo'], day['date'])}",
        "kind": str(kind or "poem"),
        "label": label,
        "entry": entry,
        "receipt": receipt,
    }


@durable
def _inner_receipt(pack_dir, ctx, day, activity, *, reason="", entry=None, generation=None,
                   attempt_state="started", trigger="requested", scope="available_at_execution", at=None):
    from .disclosure import stamp
    from .inner_attempts import detail, generation_snapshot
    dependencies = _context_dependencies(ctx)
    at = at or now_iso()
    source = f"life/{_memory_filename(day['dayNo'], day['date'])}"
    metadata = {"runner": "runtime", "operation": "inner", "failure_kind": reason,
                "trigger": trigger, "context_scope": scope, "context_dependencies": dependencies,
                "producer": generation_snapshot(generation), **stamp("owner")}
    message = detail(activity, reason)
    if entry:
        reference = {"id": entry["event_id"], "source": source + "#" + entry["event_id"],
                     "kind": "dream" if activity == "dream" else "thought"}
    else:
        event = experience.record(pack_dir, kind="action_attempt", text=message, day=day["dayNo"],
            source=source, actor="runtime", depends_on=dependencies, occurred_at=at,
            metadata={**metadata, "activity": activity, "attempt_state": attempt_state})
        reference = {"id": event["id"], "source": experience.source_of(event), "kind": "action_attempt"}
    status = "succeeded" if entry else "blocked" if attempt_state == "not_started" else "failed"
    receipt = development.record_outcome(pack_dir, action=activity, status=status, detail=message,
        day=day["dayNo"], source=reference["source"], evidence=[reference], generation=metadata, attempt_state=attempt_state,
        artifact="mind/inner.json#" + entry["event_id"] if entry else "")
    _append_journal(pack_dir, {"day": day["dayNo"], "at": at, "mode": "inner_attempt", "activity": activity,
        "status": status, "reason": reason, "attempt_state": attempt_state, "receipt_id": receipt["id"]})
    return {**(entry or {}), "succeeded": bool(entry), "reason": reason, "receipt": receipt}


@durable
def save_inner_result(pack_dir, ctx, result, brain, day, activity, *, at=None, trigger="requested"):
    """Save the generated entry, source and derived memory as one operation."""
    at = at or now_iso()
    if activity not in ("dream", "narrative") or ctx.get("_audience_id", "owner") != "owner":
        raise SeedError("内心生成需要明确的私人活动。")
    used = dict(ctx)
    from .inner_attempts import failure_kind
    reason = failure_kind(result, brain, activity)
    shaped = isinstance(result, dict) and isinstance(result.get("_generation", {}), dict)
    if shaped:
        _use_supplied_context(used, result)
    day_no = day["dayNo"]
    value = result.get("dream" if activity == "dream" else "text", "") if shaped else ""
    generation = generation_info(result, brain) if shaped else {}
    supplied = shaped and all(isinstance(result.get("_used_" + key), expected)
                              for key, expected in (("evidence", list), ("transcript", list), ("inner", dict)))
    scope = "supplied_to_adapter" if supplied else "available_at_execution"
    if reason:
        return _inner_receipt(pack_dir, used, day, activity, reason=reason, generation=generation,
                              trigger=trigger, scope=scope, at=at)
    text = value.strip()
    source = f"life/{_memory_filename(day_no, day['date'])}"
    dependencies = _context_dependencies(used)
    if activity == "dream":
        entry = add_dream(pack_dir, day_no, text, at=at, generation=generation, depends_on=dependencies, source=source)
        writes = normalize_memory_writes(pack_dir, day_no=day_no, source=source, runner=generation["runner"],
            default_kind="thought", entries=[{"text": text[:100], "importance": 0.35, "tags": ["梦"]}], at=at,
            depends_on=dependencies, event_ids=[entry["event_id"]], generation=generation)
        append_memories(pack_dir, writes)
    else:
        entry = set_narrative(pack_dir, text, day=day_no, at=at, generation=generation,
                              depends_on=dependencies, source=source)["narrative"]
    _append_journal(pack_dir, {"day": day_no, "at": at, "mode": activity,
                              "brain": generation["runner"], "generation": generation, "event_id": entry["event_id"]})
    return _inner_receipt(pack_dir, used, day, activity, entry=entry, generation=generation,
                          trigger=trigger, scope=scope, at=at)


class _InnerResponseFailure(Exception):
    def __init__(self, result):
        super().__init__("Inner generation did not return usable model content")
        self.result = result


@durable
def _inner_response(pack_dir, ctx, brain, activity):
    # Join the caller's transaction with a savepoint; a faulty adapter cannot
    # retain partial local writes when its invocation fails.
    from copy import deepcopy
    from .inner_attempts import failure_kind
    result = getattr(brain, activity)(deepcopy(ctx))
    if failure_kind(result, brain, activity):
        raise _InnerResponseFailure(result)
    return result


@durable
@model_budget.operation
def perform_inner(pack_dir, ctx, brain, day, activity, *, trigger="requested", at=None):
    require_active(pack_dir)
    from .brain import BrainConfigError
    from .context_window import ContextBudgetError
    if activity not in ("dream", "narrative") or ctx.get("_audience_id", "owner") != "owner":
        raise SeedError("内心生成需要明确的私人活动。")
    used = dict(ctx)
    if activity == "dream":
        used["dreamDay"] = day["dayNo"]
    if str(getattr(brain, "name", "")).strip().startswith("stub"):
        return _inner_receipt(pack_dir, used, day, activity, reason="offline", attempt_state="not_started", trigger=trigger, at=at)
    if not callable(getattr(brain, activity, None)):
        return _inner_receipt(pack_dir, used, day, activity, reason="unsupported", attempt_state="not_started", trigger=trigger, at=at)
    if model_budget.exhausted():
        return _inner_receipt(pack_dir, used, day, activity, reason="model_budget", attempt_state="not_started", trigger=trigger, at=at)
    reason = ""
    try:
        result = _inner_response(pack_dir, used, brain, activity)
    except _InnerResponseFailure as failure:
        result = failure.result
    except RecoveryRequired:
        raise
    except model_budget.Exhausted:
        reason, started = "model_budget", "not_started"
    except BrainConfigError:
        reason, started = "configuration", "not_started"
    except ContextBudgetError:
        reason, started = "context_budget", "not_started"
    except (RuntimeError, ValueError, OSError, TypeError):
        reason, started = "adapter_error", "started"
    if reason:
        return _inner_receipt(pack_dir, used, day, activity, reason=reason, attempt_state=started, trigger=trigger, at=at)
    # Storage errors from here propagate for recovery instead of being
    # mislabeled as a terminal model failure or erasing the day's pending work.
    return save_inner_result(pack_dir, used, result, brain, day, activity, at=at, trigger=trigger)


def _maybe_inner(pack_dir, ctx: dict, brain, day: dict, at: str):
    """根据当天选择做梦或重写自我叙事。

    服务失败保留回执和已有内容；存储/恢复失败向上交回事务处理。
    """
    selected = ctx.get("inner_activity")
    activity = {"dream": "dream", "narrate": "narrative"}.get(selected) if isinstance(selected, str) else None
    if activity:
        return perform_inner(pack_dir, ctx, brain, day, activity, trigger="daily", at=at)
    return None


@durable
def _speak_due_reminders(pack_dir, day, *, calendar_only=False) -> None:
    """到期的提醒：她会在这一天开头主动说出来。"""
    due = due_reminders(pack_dir, day["dayNo"])
    if calendar_only:
        due = [r for r in due if r.get("due_on")]
    if not due:
        return
    from .disclosure import stamp
    # Keep the transcript and reminder status in one local transaction. Failed
    # status writes must roll back the transcript so retries do not duplicate it.
    append_transcript(
        pack_dir,
        day,
        [{"who": "fish", "text": (f"原定 {reminder['due_on']} 的提醒现在补上：" if reminder.get("due_on") and reminder["due_on"] < day["date"]
                                   else "我记得你让我提醒你：") + reminder["text"],
          "metadata": {**stamp("owner"), "runner": "runtime", "mode": "reminder",
                       "reminder_id": reminder["id"], "due_on": reminder.get("due_on"),
                       "reminder_revision": len(reminder.get("history", [])),
                       "recorded_on": day["date"], "delivery_scope": "local_transcript"}} for reminder in due],
    )
    for reminder in due:
        mark_said(pack_dir, reminder["id"], day["dayNo"], via="local_transcript")


@durable
def run_days(pack_dir, days: int = 1, brain=None) -> dict:
    """过一天：让时间往前走 N 天。

    如果当天已经说过话，日记会接着对话写；否则写一段安静的一天。
    """
    require_active(pack_dir)
    if brain is None:
        raise ValueError("run_days 需要一个脑")
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise SeedError("天数必须是整数") from None
    if days < 1 or days > 3650:
        raise SeedError("天数要在 1..3650 之间")
    out = []
    for _ in range(int(days)):
        with model_budget.scope():
            day = open_day(pack_dir)
            # 1.17 手：过期的提醒变成遗憾；今天到期的她会在这一天里说出来
            try:
                sweep_missed(pack_dir, day["dayNo"])
                _speak_due_reminders(pack_dir, day)
            except Exception:  # noqa: BLE001 —— 提醒出问题也不能让她过不完这一天
                pass
            ctx = build_context(pack_dir, day["dayNo"], day["date"])
            result = brain.diary(ctx)
            _use_supplied_context(ctx, result)
            diary = str((result or {}).get("diary", "")).strip()
            if not diary:
                raise ValueError("脑没有写出日记")

            mood = str((result or {}).get("mood", ""))
            if mood not in ctx["moods"]:
                rng = rng_from(f"{ctx['birth'].get('seed')}|{ctx['name']}|{day['dayNo']}")
                mood = ctx["moods"][min(len(ctx["moods"]) - 1, int(rng() * len(ctx["moods"])))]
            source = f"life/{_memory_filename(day['dayNo'], day['date'])}"
            generation = generation_info(result, brain)
            from .disclosure import stamp
            generation.update(stamp("owner"))
            generation["proposal_activity"] = "diary"
            generation["context_dependencies"] = _context_dependencies(ctx)
            result["_generation"] = generation
            diary_event = experience.record(pack_dir, kind="diary", text=diary, day=day["dayNo"], source=source,
                                            actor=ctx["name"], depends_on=_context_dependencies(ctx), metadata=generation)
            ctx["current_evidence"] = [{"id": diary_event["id"], "source": experience.source_of(diary_event), "kind": "diary"}]
            generation["context_dependencies"] = sorted(set(generation["context_dependencies"]) | {diary_event["id"]})
            start_day(pack_dir)
            body.spend(pack_dir, "diary")
            _apply_learning(pack_dir, result or {}, ctx, day, source, brain)
            energy = body.state(pack_dir)["energy"]
            source = _finalize_day(pack_dir, day, diary[:2000], mood)
            at = now_iso()
            writes = normalize_memory_writes(
                pack_dir,
                day_no=day["dayNo"],
                source=source,
                runner=generation["runner"],
                default_kind="diary",
                entries=(result or {}).get("memories"),
                at=at,
                depends_on=_context_dependencies(ctx), event_ids=[diary_event["id"]], generation=generation,
            )
            append_memories(pack_dir, writes)
            write_json_atomic(Path(pack_dir) / "mind" / "mood.json", {"mood": mood, "energy": energy, "updated_at": at})
            _append_journal(pack_dir, {"day": day["dayNo"], "at": at, "mode": "day", "brain": generation["runner"],
                                       "generation": generation, "memories": len(writes)})
            # 1.11 意志：这一天结束 → 从这天学点兴趣、给明天定个计划
            learn_from_day(pack_dir, day["dayNo"], day["date"])
            plan_for_day(pack_dir, day["dayNo"] + 1)
            # 1.14 内在：做一个梦 / 偶尔重写自我叙事
            refreshed = build_context(pack_dir, day["dayNo"], day["date"])
            from .inner import generation_origin
            refreshed["inner_activity"] = (result or {}).get("inner_activity") if generation_origin(generation) == "model" else None
            inner_result = _maybe_inner(pack_dir, refreshed, brain, day, at)


            out.append({
                "day": day["dayNo"],
                "date": day["date"],
                "file": source,
                "memoriesAdded": len(writes),
                "totalMemories": len(read_memories(pack_dir)),
                "innerResult": inner_result,
                "modelBudget": model_budget.snapshot(),
                "mood": mood,
                "energy": energy,
            })
    return {"days": out, "nowDay": out[-1]["day"]}


def recall(pack_dir, query: str = "", k: int = 5, *, policy=None, use_semantic=True) -> list[dict]:
    """Recall current memories and original sources, using one visibility policy."""
    from .retrieval import search
    return search(pack_dir, query, k, policy=policy, use_semantic=use_semantic)


# ---------------------------------------------------------------------------
# 1.18 他者与传承：别的鱼来串门、失去、给后来的人留一封信
# ---------------------------------------------------------------------------

@durable
def visit(pack_dir, other_pack_dir, *, brain=None, note: str = "") -> dict:
    """别的鱼来看她：留下一条访客的话，她回一句；这次来访记进 friends.json。"""
    require_active(pack_dir)
    other = Path(other_pack_dir)
    if other.resolve() == Path(pack_dir).resolve():
        raise SeedError("不能让一条鱼来看她自己。")
    birth_path = other / "birth.json"
    if not birth_path.is_file():
        raise SeedError(f"这不是一个生命包：{other_pack_dir}")
    try:
        other_birth = read_json(birth_path)
    except Exception:  # noqa: BLE001
        raise SeedError(f"读不懂对方的存在证明：{birth_path}") from None
    if not isinstance(other_birth, dict) or not other_birth.get("seed") or not other_birth.get("born_at"):
        raise SeedError("对方的出生记录不完整，不能建立人物关联。")
    guest = str((other_birth or {}).get("name") or other.parent.name or "一条鱼")[:40]
    identity_key = "birth:" + sha256(canonical_json(other_birth))
    if identity_key == "birth:" + sha256(canonical_json(read_json(Path(pack_dir) / "birth.json"))):
        raise SeedError("这份出生记录属于当前个体；复制生命包不等于另一个来访者。")
    entity = facts.register_visitor(pack_dir, guest, identity_key)
    text = "用户记录了一次本地来访。" + ("用户转述的留言：" + str(note).strip() if str(note or "").strip() else "没有收到对方直接发来的话。")
    day = open_day(pack_dir)
    friend = record_visit(
        pack_dir,
        name=guest,
        species_path=str(other.resolve()),
        day=day["dayNo"],
        note=text,
        identity_key=identity_key, person_id=entity["id"],
    )
    result = chat_turn(pack_dir, text, brain or create_brain(pack_dir), speaker=guest,
                       person_id=entity["id"], interaction_kind="reported")
    at = now_iso()
    writes = normalize_memory_writes(
        pack_dir,
        day_no=day["dayNo"],
        source=result.get("file") or "",
        runner="visit-v1",
        default_kind="feeling",
        entries=[{
            "kind": "feeling",
            "text": f"用户记录了{guest}的本地来访；留言属于用户转述。",
            "importance": 0.6,
            "tags": ["来访", guest],
        }],
        at=at,
    )
    append_memories(pack_dir, writes)
    _append_journal(pack_dir, {
        "day": day["dayNo"], "at": at, "mode": "visit",
        "guest": guest, "visits": friend.get("visit_count"),
    })
    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "file": result.get("file"),
        "guest": guest,
        "reply": result.get("reply"),
        "visits": friend.get("visit_count"),
    }


@durable
def mourn(pack_dir, friend_name: str, *, brain=None, letter: str = "", day: dict | None = None) -> dict:
    """Record reported lost contact and its memories in one recoverable operation."""
    day = day or open_day(pack_dir)
    for item in list_friends(pack_dir):
        if str(item.get("name") or "") == str(friend_name or "").strip() and item.get("status") == "lost":
            raise SeedError(f"她已经送别过{friend_name}了。")
    friend = mourn_friend(pack_dir, friend_name, day=day["dayNo"])
    note = str(letter or "").strip() or "用户记录为失联，是否恢复联系尚不清楚。"
    from .memorial import add_farewell

    add_farewell(pack_dir, friend.get("name") or friend_name, kind="friend", note=note, day=day["dayNo"])
    at = now_iso()
    writes = normalize_memory_writes(
        pack_dir,
        day_no=day["dayNo"],
        source="",
        runner="mourn-v1",
        default_kind="feeling",
        entries=[{
            "kind": "feeling",
            "text": f"用户记录了与{friend.get('name') or friend_name}失联。是否会再联系尚不清楚。{note[:40]}",
            "importance": 0.7,
            "tags": ["哀悼", "告别"],
        }],
        at=at,
    )
    append_memories(pack_dir, writes)
    _append_journal(pack_dir, {
        "day": day["dayNo"], "at": at, "mode": "mourn",
        "friend": friend.get("name") or friend_name, "memories": len(writes),
    })
    return {
        "dayNo": day["dayNo"],
        "date": day["date"],
        "friend": friend.get("name") or friend_name,
        "memoriesAdded": len(writes),
    }


@serialized
def legacy_letter(pack_dir, *, out=None) -> dict:
    """Runtime-authored private archive summary, not an obituary or model letter."""
    pack = Path(pack_dir)
    birth = read_json(pack / "birth.json")
    if not isinstance(birth, dict):
        raise SeedError("出生登记无法读取，未生成档案摘要。")
    name = str(birth.get("name") or "这个个体")
    species = str((birth.get("species") or {}).get("name") or "未预设种族")
    born = str(birth.get("born_at") or "")
    days = list_days(pack)
    works = list_works(pack)
    memorial = memorial_summary(pack, days[-1]["day"] if days else None)
    farewells = farewells_of(pack)
    last_diary, diary_source = "", ""
    for page in reversed(days):
        raw = read_text(pack / "life" / page["file"])
        heading = "当日日记" if "\n## 当日日记" in raw else "今天"
        m = re.search(r"## " + heading + r"\n\n(.*?)(\n\n---\n|\Z)", raw, re.S)
        if m:
            last_diary = " ".join(m.group(1).split())[:200]
            if last_diary:
                diary_source = "life/" + page["file"]
                break
    lines = [
        f"# 给读到这封信的人",
        "",
        f"如果你读到了这里，说明{name}的一段时间被留了下来。",
        "",
        f"- 名字：{name}",
        f"- 出生登记：{species}；登记时间：{born}。",
        f"- 已保存 {len(days)} 个日页；日页数量不等于年龄或实际活动天数。",
        f"- 生命包指纹：{(birth.get('hashes') or {}).get('pack', '')[:16]}…",
        "",
        "这份私人档案摘要由 SEEDbank 运行器根据已有记录整理，不是个体另行写作的信。",
        "导出只保存当前片段，不表示生命已经结束；空档期间经历未知。",
        "",
    ]
    if works:
        lines.append("## 已保存的作品")
        lines.append("")
        for item in works[-3:]:
            lines.append(f"- {str(item.get('title') or item.get('kind'))}（第 {item.get('day')} 个日页）")
        lines.append("")
    if farewells:
        lines.append("## 记录过的告别")
        lines.append("")
        for item in farewells[-3:]:
            lines.append(f"- {item.get('name')}（第 {item.get('day')} 个日页）；告别记录不证明永久消失。")
        lines.append("")
    if memorial.get("regret_count"):
        lines.append("## 还未放下的遗憾记录")
        lines.append("")
        for item in memorial.get("regrets") or []:
            lines.append(f"- #{item['index']} {item['text']}")
        lines.append("")
    if last_diary:
        lines.append("## 最近保存的日记摘录")
        lines.append("")
        lines.append(f"来源：{diary_source}。原始历史摘录，不代表当前理解；其中可能有后来更正或放下的内容。")
        lines.append("")
        lines.append(f"> {last_diary}")
        lines.append("")
    lines.extend([
        "---",
        "",
        f"{name}的生命包可以继续读取与运行。保留档案、暂停运行和结束生命不是同一个状态。",
        "这份文件没有自动公开。是否分享、分享哪些内容，由档案持有人决定。",
    ])
    text = "\n".join(lines) + "\n"
    target = Path(out) if out else pack / "legacy" / "letter.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_file_atomic(target, text)
    return {"path": str(target), "text": text, "days": len(days), "name": name}


def _friends_lines(ctx: dict) -> str:
    friends = (ctx.get("friends") or {}).get("recent") or []
    if not friends:
        return "- （还没有别的鱼来过）"
    out = []
    for item in friends:
        status = "（失联）" if item.get("status") == "lost" else ""
        out.append(f"- {item.get('name')}{status}：来过 {item.get('visits')} 次，最近第 {item.get('last_visit_day')} 天")
    return "\n".join(out)
