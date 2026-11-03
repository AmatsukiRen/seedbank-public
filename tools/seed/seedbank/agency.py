"""意志 —— 她可以自己开始一件事（1.11）。

她不再只是「被叫醒才说话」：
- 兴趣（interests）：从日子里长出来的话题，影响她主动时说什么
- 计划（plans）：对明天有打算；做了会记下来
- 边界（boundaries）：她不想聊的话题，可以说不
- 主动（initiated）：在她醒着、安静了一段之后，她可以先开口

计划历史追加到 `mind/plans.jsonl`；兴趣、边界与主动计数保留在 `mind/agency.json`。
"""

from __future__ import annotations

from .i18n import t
from copy import deepcopy
import re
from datetime import datetime
from pathlib import Path
from .pack_lock import durable

from .util import (
    SeedError,
    expand_home,
    list_days,
    local_date,
    now_iso,
    parse_time,
    read_json,
    read_memories,
    read_text_safe,
    rng_from,
    write_json_atomic,
)

AGENCY_FORMAT = "seedbank/agency@1"

# 兴趣最多留几个；边界最多几条；每条多少字。
INTEREST_MAX = 8
BOUNDARY_MAX = 12
TEXT_CHARS = 40

# 她可以选来「过今天」的计划（不需要外部能力就能做到的那几件）。
PLAN_CHOICES = ("读点什么", "整理记忆", "发呆", "等主人来", "写点东西")

# 她醒着的小时区间（左闭右开）。半夜不主动说话。
AWAKE_HOURS = (7, 23)

DEFAULT_AGENCY = {
    "format": AGENCY_FORMAT,
    "interests": [],
    "plans": [],
    "boundaries": [],
    "last_initiated_at": None,
    "initiated": {},
}

# 学兴趣时忽略的词（太常见，学出来也没意义）。
_STOPWORDS = set("""
今天 明天 昨天 我们 你们 他们 自己 什么 这个 那个 没有 一个 时候 可以 已经 因为
所以 但是 如果 就是 还是 这样 那么 现在 知道 觉得 记得 东西 地方 主人 声音 房间
一直 一点 一下 一起 出来 起来 下来 过来 东西 觉得 好像 真的 不是 不会 不能 还有
然后 后来 开始 看到 听见 感觉 想起 时候 以后 以前 每天 一天 两天 今天 那些 这些
""".split())

# 候选话题里只要出现这些字，基本是「句子碎片」而不是「她在意的东西」。
_STOP_CHARS = set("的了是我你他她它它们在就有也很都说不把被让给和与这那又还再只但而着过吧呢啊呀吗一个什么自己在好来去上下的地得有事些点等使")

# 从中文里粗略切 2~4 个字当候选；英文单词 3 个字母以上。
_TOKEN = re.compile(r"[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,}")


def agency_path(pack_dir) -> Path:
    return Path(expand_home(pack_dir)) / "mind" / "agency.json"


def _clean_text(value, limit: int = TEXT_CHARS) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").replace("**", "")
    return text.strip()[:limit]


def _clean_interests(value) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        topic = _clean_text(item.get("topic"))
        if not topic or topic in seen:
            continue
        seen.add(topic)
        try:
            weight = int(item.get("weight") or 1)
        except (TypeError, ValueError):
            weight = 1
        out.append({
            "topic": topic,
            "weight": max(1, min(99, weight)),
            "from": _clean_text(item.get("from") or "day", 12) or "day",
            "day": int(item.get("day") or 0) if str(item.get("day") or "0").isdigit() else 0,
        })
    out.sort(key=lambda x: -x["weight"])
    return out[:INTEREST_MAX]


def _clean_plans(value) -> list[dict]:
    from .planning import clean_plans
    return clean_plans(value)


def _clean_boundaries(value) -> list[str]:
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        text = _clean_text(item)
        if text and text not in out:
            out.append(text)
    return out[:BOUNDARY_MAX]


def load_agency(pack_dir) -> dict:
    """Read current state without erasing malformed files or long plan history."""
    file = agency_path(pack_dir)
    raw = read_json(file, None) if file.exists() else {}
    if not isinstance(raw, dict) or raw.get("format", AGENCY_FORMAT) != AGENCY_FORMAT:
        raise SeedError("意志档案格式无法读取；原文件已保留。")
    from .planning import SUPPORTED_FORMATS, path as plans_path
    if "plan_store" in raw and (raw["plan_store"] not in SUPPORTED_FORMATS or not plans_path(pack_dir).is_file()):
        raise SeedError("计划历史文件缺失或版本不兼容；未使用旧快照覆盖历史。")
    data = {**deepcopy(DEFAULT_AGENCY), **deepcopy(raw)}
    if isinstance(raw, dict):
        data["interests"] = _clean_interests(raw.get("interests"))
        from .planning import project
        data["plans"] = project(pack_dir, _clean_plans(raw.get("plans", [])))
        data["boundaries"] = _clean_boundaries(raw.get("boundaries"))
        last = raw.get("last_initiated_at")
        data["last_initiated_at"] = str(last) if last else None
        initiated = raw.get("initiated")
        if "initiated" in raw and not isinstance(initiated, dict):
            raise SeedError("主动次数记录格式不完整；原档案已保留。")
        if isinstance(initiated, dict):
            data["initiated"] = {
                str(k): max(0, int(v or 0))
                for k, v in initiated.items()
                if str(k) and str(v or "0").isdigit()
            }
    return data


@durable
def save_agency(pack_dir, patch: dict) -> dict:
    data = load_agency(pack_dir)
    if "interests" in patch:
        data["interests"] = _clean_interests(patch["interests"])
    if "plans" in patch:
        from .planning import FORMAT, choose, path, project
        plans = _clean_plans(patch["plans"])
        for plan in plans:
            choose(pack_dir, plan, legacy=data["plans"], kind="import", trigger="save_agency")
        data["plans"] = project(pack_dir, data["plans"])
        if path(pack_dir).exists():
            data["plan_store"] = read_json(agency_path(pack_dir), {}).get("plan_store", FORMAT)
    if "boundaries" in patch:
        data["boundaries"] = _clean_boundaries(patch["boundaries"])
    if "last_initiated_at" in patch:
        data["last_initiated_at"] = patch["last_initiated_at"] or None
    if "initiated" in patch and isinstance(patch["initiated"], dict):
        data["initiated"] = {
            str(k): max(0, int(v or 0))
            for k, v in patch["initiated"].items()
            if str(k) and str(v or "0").isdigit()
        }
    data["format"] = AGENCY_FORMAT
    write_json_atomic(agency_path(pack_dir), data)
    return data


# —— 兴趣 ——

def _bump_interest(data: dict, topic: str, source: str, day: int) -> None:
    for item in data["interests"]:
        if item["topic"] == topic:
            item["weight"] = min(99, int(item["weight"]) + 1)
            item["from"] = source
            item["day"] = day
            data["interests"].sort(key=lambda x: -x["weight"])
            return
    data["interests"].append({"topic": topic, "weight": 1, "from": source, "day": day})
    data["interests"].sort(key=lambda x: -x["weight"])
    del data["interests"][INTEREST_MAX:]


@durable
def add_interest(pack_dir, topic: str, *, source: str = "主人", day: int = 0) -> dict:
    topic = _clean_text(topic)
    if not topic:
        raise SeedError(t("兴趣不能是空的"))
    data = load_agency(pack_dir)
    _bump_interest(data, topic, source, int(day or 0))
    data["format"] = AGENCY_FORMAT
    write_json_atomic(agency_path(pack_dir), data)
    return data


def _signal_passages(pack) -> list[str]:
    """可能的「在意来源」：她读到的见闻 + 主人/访客说过的话。日记不参与（模板词太多）。"""
    passages: list[str] = []
    for item in list_days(pack)[-7:]:
        text = read_text_safe(pack / "life" / str(item["file"]))
        section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                section = stripped[3:].strip()
                continue
            if section == "见闻" and stripped.startswith("- "):
                passages.append(re.sub(r"（[^）]*）", "", stripped[2:]))
            elif section == "对话" and stripped.startswith("**") and "：" in stripped:
                speaker, _, said = stripped.partition("：")
                if "（主动）" in speaker:
                    continue
                passages.append(said)
    return passages


def _topic_counts(passages: list[str]) -> dict[str, int]:
    """候选话题 = 中文二元组 / 英文单词；出现至少两次才算她惦记的事。"""
    counts: dict[str, int] = {}
    for passage in passages:
        clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", passage)
        for chunk in clean.split():
            if not chunk or chunk.isdigit():
                continue
            if chunk.isascii():
                if len(chunk) >= 3:
                    counts[chunk.lower()] = counts.get(chunk.lower(), 0) + 1
                continue
            for i in range(len(chunk) - 1):
                bigram = chunk[i:i + 2]
                if any(ch in _STOP_CHARS for ch in bigram):
                    continue
                if bigram in _STOPWORDS:
                    continue
                counts[bigram] = counts.get(bigram, 0) + 1
    return counts


@durable
def learn_from_day(pack_dir, day_no: int, date: str) -> list[str]:
    """把有来源的明确偏好同步到兴趣；词频不能判断喜欢或厌恶。"""
    from .development import load_development, current_state
    pack = Path(expand_home(pack_dir))
    data = load_agency(pack)
    learned: list[str] = []
    all_preferences = load_development(pack)["preferences"].values()
    preferences = list(current_state(pack)["preferences"].values())
    liked = {p["topic"] for p in preferences if p["stance"] == "like"}
    unliked = {p["topic"] for p in all_preferences if p["topic"] not in liked}
    data["interests"] = [i for i in data["interests"] if i["topic"] not in unliked
                         and (i.get("from") != "成长" or i["topic"] in liked)]
    known = {item["topic"] for item in data["interests"]}
    write_json_atomic(agency_path(pack), data)
    for preference in preferences:
        topic = preference["topic"]
        if preference["stance"] == "like" and topic not in known:
            add_interest(pack, topic, source="成长", day=int(day_no))
            learned.append(topic)
    return learned


# —— 计划 ——

def current_plan(pack_dir, day_no: int) -> dict | None:
    for item in load_agency(pack_dir)["plans"]:
        if int(item["day"]) == int(day_no):
            return item
    return None


def plan_status(plan, *, outcomes=(), checkpoint=None) -> str:
    """Describe only supplied, visible receipts; they do not prove a free-text plan."""
    if plan.get("awaiting_choice"):
        return t("等待重新选择")
    if plan.get("basis_changed"):
        return t("关联目标已更新，原计划待重新安排")
    if checkpoint:
        from .plan_checkpoints import label
        return label(checkpoint, waiting=True)
    if plan.get("goal_id") and any(row.get("goal_id") == plan["goal_id"]
                                   and row.get("day") == plan.get("day") for row in outcomes):
        return t("关联目标有行动回执，计划完成待核对")
    if plan.get("done"):
        return t("旧记录曾标为完成，依据待核对")
    return t("计划完成待核对")


@durable
def plan_for_day(pack_dir, day_no: int, *, refresh=False) -> dict:
    """Keep the current plan unless explicitly refreshed after a goal change."""
    if isinstance(day_no, str) and day_no.isascii() and day_no.isdigit():
        day_no = int(day_no)
    if type(day_no) is not int or day_no < 1:
        raise SeedError("计划日页应为正整数。")
    existing = current_plan(pack_dir, day_no)
    if existing and not refresh:
        return existing
    from .planning import awaiting_choice
    if awaiting_choice(pack_dir, existing):
        return existing
    if existing and existing.get("origin") == "model":
        from .deliberation import valid
        from .development import current_state
        state = current_state(pack_dir)
        goal = state["goals"].get(existing.get("goal_id"))
        if valid(pack_dir, existing) and (existing.get("mode") != "focus" or goal and goal["status"] == "active"):
            return existing
        from .planning import choose
        return choose(pack_dir, {"day": day_no, "plan": "原安排需要重新考虑，先留出选择的空间",
            "reason": "原选择的目标或依据已变化", "goal_id": "", "done": False, "awaiting_choice": True},
            legacy=load_agency(pack_dir)["plans"], trigger="decision_basis_changed")
    from .body import state as body_state
    from .development import choose_plan
    energy = body_state(pack_dir)["energy"]
    chosen = choose_plan(pack_dir, int(day_no), energy=energy)
    data = load_agency(pack_dir)
    if chosen is None:
        interests = data.get("interests") or []
        chosen = {"day": int(day_no), "plan": ("进一步了解" + interests[0]["topic"]) if interests else "暂时留白，等待值得投入的事情",
                  "done": False, "reason": "来自已记录的兴趣" if interests else "还没有形成长期目标", "goal_id": ""}
    from .planning import choose
    return choose(pack_dir, chosen, legacy=data["plans"], trigger="refresh" if refresh else "new_day",
                  context={"energy": energy})


@durable
def mark_plan_done(pack_dir, day_no: int) -> None:
    """Legacy compatibility flag only; current readers treat it as unverified.

    Runtime actions must not call this: there is no criterion for completing a
    free-text daily plan. Goal completion is separately checked by learning.
    """
    data = load_agency(pack_dir)
    current = next((item for item in data["plans"] if item["day"] == int(day_no)), None)
    if current and not current["done"]:
        from .planning import choose
        choose(pack_dir, {**current, "done": True}, legacy=data["plans"],
               kind="legacy_flag", trigger="mark_plan_done")


def plan_history(pack_dir, *, day=None, before="", limit=20):
    from .planning import history
    return history(pack_dir, load_agency(pack_dir)["plans"], day=day, before=before, limit=limit)


def history_line(row):
    plan = row["plan"]
    origin = {"selection": "运行器安排", "legacy": "旧计划快照", "import": "导入计划",
              "legacy_flag": "旧完成标记，未核实", "decision": "个体选择（模型生成）"}[row["kind"]]
    from .plan_continuity import link_line, valid_binding
    continuity = "\n" + link_line(plan["continuity"]) if row["kind"] != "legacy" and valid_binding(plan.get("continuity")) else ""
    return (str(row["at"] or t("原记录未注明选择时间")) + " · " + t(origin) + " · "
            + t("当前安排" if row["is_current"] else "历史安排") + "\n" + plan["plan"]
            + continuity
            + "\n" + t("理由：{text}", text=plan["reason"] or t("未记录理由")))


# —— 边界（她可以说不） ——

@durable
def add_boundary(pack_dir, topic: str) -> dict:
    topic = _clean_text(topic)
    if not topic:
        raise SeedError(t("不想聊的话题不能是空的"))
    data = load_agency(pack_dir)
    if topic not in data["boundaries"]:
        data["boundaries"].append(topic)
        data["boundaries"] = data["boundaries"][:BOUNDARY_MAX]
    data["format"] = AGENCY_FORMAT
    write_json_atomic(agency_path(pack_dir), data)
    return data


@durable
def clear_boundaries(pack_dir) -> dict:
    data = load_agency(pack_dir)
    data["boundaries"] = []
    data["format"] = AGENCY_FORMAT
    write_json_atomic(agency_path(pack_dir), data)
    return data


def boundaries_match(pack_dir, text: str) -> str | None:
    """这句话踩到哪条边界了吗？返回那条边界。"""
    haystack = str(text or "").casefold()
    for boundary in load_agency(pack_dir)["boundaries"]:
        if boundary.casefold() in haystack:
            return boundary
    return None


# —— 主动开口 ——

def should_initiate(
    pack_dir,
    *,
    now=None,
    idle_seconds: int = 2 * 60 * 60,
    max_per_day: int = 3,
) -> dict | None:
    """此刻是否有普通自主机会；获得机会不代表一定开口或行动。"""
    pack = Path(expand_home(pack_dir))
    when = parse_time(now) if isinstance(now, str) else (now or datetime.now().astimezone())
    if when.tzinfo is None:
        when = when.astimezone()
    if not (AWAKE_HOURS[0] <= when.hour < AWAKE_HOURS[1]):
        return None
    days = list_days(pack)
    if not days:
        return None
    last = days[-1]
    if last["date"] != local_date(when):
        return None
    # The genesis narrative uses the diary heading too. The real-time clock
    # can keep that birth day open; use the same calendar state as cognition
    # instead of interpreting a heading as a completed day here.
    from .cognition import open_day
    current = open_day(pack)
    if not current.get("open") or current["dayNo"] != last["day"] or current["date"] != last["date"]:
        return None
    data = load_agency(pack)
    today = last["date"]
    count = int((data.get("initiated") or {}).get(today, 0) or 0)
    if count >= int(max_per_day):
        return None
    last_at = data.get("last_initiated_at")
    if last_at:
        try:
            gap = (when - parse_time(last_at)).total_seconds()
        except (TypeError, ValueError):
            gap = idle_seconds
        if gap < int(idle_seconds):
            return None
    plan = current_plan(pack, last["day"]) or {}
    interests = data.get("interests") or []
    return {
        "day": int(last["day"]),
        "date": today,
        "plan": str(plan.get("plan") or ""),
        "interest": str(interests[0]["topic"]) if interests else "",
        "remaining": int(max_per_day) - count,
    }


@durable
def record_initiation(pack_dir, *, now=None, day_no=None) -> dict:
    """记下一次主动决策（包括选择不说话）；不代表计划完成。"""
    when = parse_time(now) if isinstance(now, str) else (now or datetime.now().astimezone())
    if when.tzinfo is None:
        when = when.astimezone()
    today = local_date(when)
    data = load_agency(pack_dir)
    data["initiated"][today] = int((data.get("initiated") or {}).get(today, 0) or 0) + 1
    data["last_initiated_at"] = when.isoformat(timespec="seconds")
    data["format"] = AGENCY_FORMAT
    write_json_atomic(agency_path(pack_dir), data)
    if day_no is None:
        days = list_days(pack_dir)
        day_no = days[-1]["day"] if days else 0
    return data


def _today_day(pack_dir) -> tuple[int, str]:
    """现在她处在哪一天：最后一天还开着就是它，已经闭合就是下一天。"""
    days = list_days(pack_dir)
    if not days:
        return 0, ""
    last = days[-1]
    path = Path(expand_home(pack_dir)) / "life" / str(last["file"])
    if "## 今天" in read_text_safe(path):
        return int(last["day"]) + 1, local_date(datetime.now().astimezone())
    return int(last["day"]), str(last["date"])


def describe_agency(pack_dir) -> list[str]:
    """给用户看的一小段话。"""
    data = load_agency(pack_dir)
    days = list_days(pack_dir)
    lines: list[str] = []
    interests = data.get("interests") or []
    if interests:
        lines.append(t("兴趣：") + "、".join(f"{item['topic']}（{item['weight']}）" for item in interests[:5]))
    else:
        lines.append(t("兴趣：还没有长出来（多过几天、读点东西就会有了）"))
    boundaries = data.get("boundaries") or []
    lines.append(t("不想聊的：") + ("、".join(boundaries) if boundaries else t("（没有，她目前什么都愿意说）")))
    if days:
        from .development import current_state
        from .plan_checkpoints import for_plan
        day_no, _ = _today_day(pack_dir)
        plan = current_plan(pack_dir, day_no) or {}
        if plan:
            plan_text = t(
                "{plan}（{status}）",
                plan=plan.get("plan"),
                status=plan_status(plan, outcomes=current_state(pack_dir)["outcomes"],
                                   checkpoint=for_plan(pack_dir, plan)),
            )
        else:
            plan_text = t("（今天没有计划）")
        lines.append(t("今天的计划：{plan_text}", plan_text=plan_text))
        today = days[-1]["date"]
        count = int((data.get("initiated") or {}).get(today, 0) or 0)
        lines.append(t("今天自主选择：{count} 次", count=count))
        if data.get("last_initiated_at"):
            lines.append(t("上次自主选择：{last_initiated_at}", last_initiated_at=data['last_initiated_at']))
    return lines


@durable
def new_day_hooks(pack_dir, day_no: int) -> dict:
    """新的一天：给今天定计划 + 从过去一天学兴趣（由认知循环调用）。"""
    plan = plan_for_day(pack_dir, day_no)
    learned: list[str] = []
    days = list_days(pack_dir)
    if days:
        previous = [d for d in days if int(d["day"]) < int(day_no)]
        if previous:
            learned = learn_from_day(pack_dir, previous[-1]["day"], previous[-1]["date"])
    return {"plan": plan, "learned": learned}
