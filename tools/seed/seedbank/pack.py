"""蛋与生命包 —— 孵化、校验、读取。

这里只有「格式」和「检查」，没有「说话」。
一只鱼会不会说话，取决于脑（brain.py）；她的一生怎么被记录，取决于这里。
"""

from __future__ import annotations

from .i18n import t
import json
import re
import secrets
import shutil
import sys
import time
import uuid
from datetime import timezone
from pathlib import Path

from .brain import ADAPTERS, birth_brain_config, describe_brain, load_brain_config
from .settings import DEFAULT_MEMORY as DEFAULT_MEMORY_SETTINGS, memory_settings
from .util import (
    BRAIN_FORMAT, LIFE_FORMAT, SeedError, add_days, canonical_json, expand_home,
    hash_tree, list_days, local_date, now_iso, pad4, parse_time, pick, read_json,
    read_text, round2, rng_from, sha256, write_file_atomic,
    write_json_atomic,
)
EGG_FORMAT = "seedbank/seed@1"

# Windows 不让用的文件名（她可能会被拷到任何机器上）。名字是文件夹名的一部分，
# 允许中间有空格（首尾空格会被 strip 掉），但不允许控制字符和 Windows 非法字符。
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)
_BAD_CHARS = re.compile(r'[\u0000-\u001f<>:"/\\|?*]')

REQUIRED_EGG_FILES = [
    "species.json",
    "deps.lock",
    "genesis.md",
    "world/bible.md",
    "genome/identity.md",
    "genome/values.md",
    "genome/quirks.md",
    "genome/traits.json",
]

REQUIRED_PACK_FILES = [
    "birth.json",
    "deps.lock",
    "genome/identity.md",
    "genome/values.md",
    "genome/quirks.md",
    "genome/traits.json",
    "world/bible.md",
    "mind/traits.json",
    "mind/mood.json",
    "mind/self.md",
    "mind/beliefs.md",
    "mind/brain.json",
    "mind/memories.jsonl",
]


# ---------------------------------------------------------------------------
# 名字
# ---------------------------------------------------------------------------

def validate_name(name) -> str:
    text = str(name or "").strip()
    if not text:
        raise SeedError(t("名字不能为空。"))
    if len(text) > 24:
        raise SeedError(t("名字最多 24 个字。"))
    if text in (".", ".."):
        raise SeedError(t("这个名字不能用。"))
    if _BAD_CHARS.search(text):
        raise SeedError(t('名字里不能有 < > : " / \\ | ? * 或控制字符。'))
    if text.endswith((" ", ".")):
        raise SeedError(t("名字不能以空格或句号结尾。"))
    if _RESERVED.match(text):
        raise SeedError(t("「{value}」是 Windows 保留设备名，换一个吧。", value=text))
    return text


# ---------------------------------------------------------------------------
# 读蛋
# ---------------------------------------------------------------------------

def load_egg(egg_dir) -> dict:
    """读入一颗蛋，做完整性检查，返回内存中的蛋。"""
    egg = expand_home(egg_dir)
    if not egg.exists():
        raise SeedError(t("找不到蛋目录：{egg}", egg=egg))
    for rel in REQUIRED_EGG_FILES:
        if not (egg / rel).is_file():
            raise SeedError(t("蛋不完整，缺少 {rel}（路径：{egg}）", rel=rel, egg=egg))

    species = read_json(egg / "species.json")
    if not isinstance(species, dict):
        raise SeedError(t("species.json 不是合法 JSON：{value}", value=egg / 'species.json'))
    if species.get("format") != EGG_FORMAT:
        raise SeedError(t("不认识的蛋格式：{format!r}（需要 {EGG_FORMAT}）", format=species.get('format'), EGG_FORMAT=EGG_FORMAT))

    deps = read_json(egg / "deps.lock", {})
    if not isinstance(deps, dict):
        raise SeedError(t("deps.lock 不是合法 JSON。"))

    traits_doc = read_json(egg / "genome" / "traits.json", {})
    traits = traits_doc.get("traits") if isinstance(traits_doc.get("traits"), list) else []
    if not traits:
        raise SeedError(t("genome/traits.json 里没有 traits。"))

    moods = species.get("moods") or traits_doc.get("moods") or ["安静"]
    if not isinstance(moods, list) or not moods:
        moods = ["安静"]
    try:
        pick_count = max(0, min(len(traits), int(traits_doc.get("pick") or 3)))
    except (TypeError, ValueError):
        pick_count = min(3, len(traits))

    return {
        "dir": egg,
        "species": species,
        "deps": deps,
        "requires": deps.get("runtime") or {},
        "traits": traits,
        "pick": pick_count,
        "moods": [str(m) for m in moods],
        "identity": read_text(egg / "genome" / "identity.md"),
        "values": read_text(egg / "genome" / "values.md"),
        "quirks": read_text(egg / "genome" / "quirks.md"),
        "bible": read_text(egg / "world" / "bible.md"),
        "genesis": read_text(egg / "genesis.md"),
        "deps_text": read_text(egg / "deps.lock"),
        "hash": hash_tree(egg),
    }


def build_egg_info(egg_dir) -> dict:
    """蛋的公开说明书（不含任何秘密，适合贴到 registry/）。"""
    egg = load_egg(egg_dir)
    species = egg["species"]
    return {
        "format": EGG_FORMAT,
        "species": {
            "id": species.get("id"),
            "name": species.get("name"),
            "version": species.get("version"),
            "author": species.get("author"),
            "description": species.get("description"),
        },
        "genome": {
            "traits": len(egg["traits"]),
            "moods": egg["moods"],
        },
        "requires": egg["requires"],
        "license": egg["deps"].get("license"),
        "sha256": egg["hash"]["sha256"],
        "files": len(egg["hash"]["files"]),
    }


# ---------------------------------------------------------------------------
# 孵化
# ---------------------------------------------------------------------------

def hatch(pack_dir, egg_dir, name, seed_override: str | None = None,
          born_at_override: str | None = None) -> dict:
    """把一颗蛋孵成一个生命包。一次孵化 = 一条新生命。

    seed_override / born_at_override 只用于复现与示例：给定后同一颗蛋会孵出
    同一个个体（出生证逐字节一致）。正常孵化不传，熵与时间决定她是哪一条。
    """
    name = validate_name(name)
    egg = load_egg(egg_dir)
    try:
        pack = expand_home(pack_dir)
        if pack.exists():
            raise SeedError(t("目标已存在，不覆盖：{pack}（孵化只发生一次）", pack=pack))
        if not pack.parent.exists():
            pack.parent.mkdir(parents=True, exist_ok=True)
    except SeedError:
        raise
    except OSError as error:
        raise SeedError(t("这个路径不能用：{error}", error=error)) from error

    deps_text = egg["deps_text"]
    deps = egg["deps"]
    requires = dict(egg["requires"])
    requires.setdefault("python", ">=3.10")

    if seed_override:
        seed = sha256(f"seedbank/v1:{seed_override}")
    else:
        entropy = f"{uuid.uuid4().hex}-{time.time_ns()}"
        seed = sha256(f"seedbank/v1:{entropy}")
    rng = rng_from(seed)

    pool = list(egg["traits"])
    picked: list[dict] = []
    for _ in range(egg["pick"]):
        picked.append(pool.pop(min(len(pool) - 1, int(rng() * len(pool)))))
    moods = egg["moods"]
    mood = pick(rng, moods)
    energy = round2(0.4 + rng() * 0.6)

    born_at = now_iso() if not born_at_override else parse_time(born_at_override).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    born_date = local_date(parse_time(born_at))
    day1 = f"{pad4(1)}-{born_date}.md"
    species = egg["species"]
    species_brief = {
        "id": species.get("id"),
        "name": species.get("name"),
        "version": species.get("version"),
    }

    tmp = pack.parent / f".{pack.name}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        _write_tree(tmp, egg=egg, name=name, species=species_brief, deps_text=deps_text,
                    day1=day1, born_date=born_date, born_at=born_at, seed=seed,
                    mood=mood, energy=energy, picked=picked, moods=moods)

        genome_hash = hash_tree(tmp / "genome")["sha256"]
        pack_hash = hash_tree(tmp)["sha256"]
        birth = {
            "format": LIFE_FORMAT,
            "name": name,
            "born_at": born_at,
            "local_date": born_date,
            "seed": seed,
            "species": species_brief,
            "egg": {
                "id": species.get("id"),
                "version": species.get("version"),
                "sha256": egg["hash"]["sha256"],
            },
            "deps": deps,
            "requires": requires,
            "genome": {
                "identity": "genome/identity.md",
                "values": "genome/values.md",
                "quirks": "genome/quirks.md",
                "traits": "genome/traits.json",
            },
            "genesis": {"file": f"life/{day1}", "day": 1},
            "clock": species.get("clock") or "on-demand",
            "hashes": {
                "pack": pack_hash,
                "genome": genome_hash,
                "deps": sha256(deps_text.encode("utf-8")),
            },
        }
        birth["birth_hash"] = sha256(canonical_json(birth))
        write_json_atomic(tmp / "birth.json", birth)
        if pack.exists():
            _fail(t("目标已存在，不覆盖：{pack}", pack=pack))
        tmp.rename(pack)
    except SeedError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SeedError(t("孵化失败：{error}", error=error)) from error

    return {
        "packDir": str(pack),
        "name": name,
        "bornAt": born_at,
        "localDate": born_date,
        "seed": seed,
        "species": species_brief,
        "picked": picked,
        "clock": "realtime",
        "path": str(pack),
    }


def _fail(message: str):
    raise SeedError(message)


def _write_tree(directory: Path, *, egg, name, species, deps_text, day1, born_date,
                born_at, seed, mood, energy, picked, moods) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "genome").mkdir()
    (directory / "world").mkdir()
    (directory / "life").mkdir()
    (directory / "mind").mkdir()

    for rel in ("identity.md", "values.md", "quirks.md"):
        write_file_atomic(directory / "genome" / rel, read_text(egg["dir"] / "genome" / rel))
    traits_doc = read_json(egg["dir"] / "genome" / "traits.json", {})
    write_json_atomic(directory / "genome" / "traits.json", {
        "format": traits_doc.get("format", "seedbank/traits@1"),
        "traits": egg["traits"],
        "moods": moods,
        "picked": [t.get("id") for t in picked],
    })
    write_file_atomic(directory / "world" / "bible.md", egg["bible"])
    write_file_atomic(directory / "deps.lock", deps_text)

    profile_file = egg["dir"] / "genome" / "profile.json"
    profile = read_json(profile_file, {}) if profile_file.is_file() else {}
    if not isinstance(profile, dict) or (profile and profile.get("format") != "seedbank/profile@1"):
        raise SeedError("genome/profile.json 必须是 seedbank/profile@1 对象。")
    if any(key in profile and not isinstance(profile[key], str) for key in (
            "identity_mode", "avatar", "initial_self", "initial_belief", "birth_memory", "initial_perception")):
        raise SeedError("genome/profile.json 的身份与出生文本必须是字符串。")
    if profile:
        write_file_atomic(directory / "genome" / "profile.json", read_text(profile_file))
    def initial(key, fallback):
        return str(profile.get(key, fallback)).replace("{name}", name)
    legacy_whale = species.get("id") == "dafeiyu"
    perception = initial("initial_perception", "光：光很亮，有点暖。" if legacy_whale else "")
    no_talk = "（今天还没有人跟她说话。）" if legacy_whale else "（今天还没有对话记录。）"

    genesis = str(egg["genesis"]).strip()
    write_file_atomic(directory / "life" / day1,
                      f"# 第 0001 天 · {born_date}\n\n## 对话\n\n{no_talk}\n\n"
                      f"## 感知\n\n{('- ' + perception) if perception else '（尚未接收到感知输入。）'}\n\n"
                      f"## 今天\n\n{genesis}\n\n---\n\n*{mood}。*\n")

    write_json_atomic(directory / "mind" / "traits.json", {"picked": picked})
    write_json_atomic(directory / "mind" / "mood.json",
                      {"mood": mood, "energy": energy, "updated_at": born_at})
    write_json_atomic(directory / "mind" / "brain.json", birth_brain_config())
    write_json_atomic(directory / "mind" / "memory.json", dict(DEFAULT_MEMORY_SETTINGS))
    default_self = (f"我是{name}，一只{species.get('name') or '小东西'}。\n\n我刚醒来。世界很小，只有光和水的影子。"
                    if legacy_whale else f"我叫{name}。我的个人经历从今天开始。")
    initial_self = initial("initial_self", default_self)
    write_file_atomic(directory / "mind" / "self.md", f"# 我是谁\n\n{initial_self}\n")
    initial_belief = initial("initial_belief", "光会回来。" if legacy_whale else "我对自己的认识可以随经历改变。")
    write_file_atomic(directory / "mind" / "beliefs.md", f"# 我相信的事\n\n- {initial_belief}\n")
    birth_memory = {
        "id": "m_0001_1",
        "day": 1,
        "at": born_at,
        "kind": "feeling",
        "text": initial("birth_memory", "我醒过来了。第一眼看见的是光。" if legacy_whale else "今天是我的出生记录。此前没有个人经历。"),
        "importance": 0.6,
        "tags": ["出生"],
        "source": "genesis",
        "runner": "hatch",
    }
    write_file_atomic(directory / "mind" / "memories.jsonl",
                      json.dumps(birth_memory, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

_RUNTIME = re.compile(r"(\d+)\.(\d+)")
_VERSION_CLAUSE = re.compile(r"^(>=|<=|==|!=|>|<)\s*(\d+)\.(\d+)(?:\.(\d+))?$")


def _check_runtime(requires: dict) -> dict:
    """她还能被运行吗？——这是死亡的第一道门。"""
    spec = str(requires.get("python") or ">=3.10")
    have = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    clauses = [part for part in spec.split(",") if part.strip()]
    if clauses and all(_VERSION_CLAUSE.match(part.strip()) for part in clauses):
        ok = all(_satisfies_version(have, part.strip()) for part in clauses)
        need_text = f"python {spec.strip()}"
    else:
        # 不认识的写法：老蛋只写了「3.10」这种，按 >=3.10 兼容处理
        loose = _RUNTIME.search(spec)
        need = (int(loose.group(1)), int(loose.group(2))) if loose else (3, 10)
        ok = have[:2] >= need
        need_text = f"python >={need[0]}.{need[1]}"
    return {
        "ok": ok,
        "need": need_text,
        "have": f"python {have[0]}.{have[1]}.{have[2]}",
        "spec": spec,
    }


def _satisfies_version(have: tuple[int, int, int], clause: str) -> bool:
    match = _VERSION_CLAUSE.match(clause)
    if not match:
        return False
    op = match.group(1)
    target = (int(match.group(2)), int(match.group(3)), int(match.group(4) or 0))
    full = match.group(4) is not None
    left = have if full else have[:2]
    right = target if full else target[:2]
    if op == ">=":
        return left >= right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    if op == "<":
        return left < right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return False


_DAY_HEADER = re.compile(r"^# 第 (\d{4,}) 天 · (\d{4}-\d{2}-\d{2})")


def _birth_fingerprint(birth: dict) -> str:
    """出生证的指纹：对除 birth_hash 之外的全部字段做规范 JSON 哈希。"""
    body = {key: value for key, value in birth.items() if key != "birth_hash"}
    return sha256(canonical_json(body))


def _read_memories_strict(pack: Path) -> list[dict]:
    """生命包完整性检查：坏行就是坏数据，保留原文件并报告位置。"""
    file = pack / "mind" / "memories.jsonl"
    if not file.is_file():
        raise SeedError(t("生命包里没有 mind/memories.jsonl。"))
    items = []
    for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except ValueError as error:
            raise SeedError(t("memories.jsonl 第 {line_no} 行不是合法 JSON：{error}", line_no=line_no, error=error)) from None
        if not isinstance(item, dict):
            raise SeedError(t("memories.jsonl 第 {line_no} 行不是一条记忆。", line_no=line_no))
        items.append(item)
    return items


def _optional_json_object(pack: Path, name: str):
    """读一个可选的 mind/*.json；坏 JSON 或不是对象一律当「坏了」报错（体检口径统一）。"""
    file = pack / "mind" / name
    if not file.is_file():
        return None
    try:
        raw = json.loads(file.read_text(encoding="utf-8-sig"))
    except ValueError as error:
        raise SeedError(t("mind/{name} 不是合法 JSON：{error}", name=name, error=error)) from None
    if not isinstance(raw, dict):
        raise SeedError(t("mind/{name} 坏了（不是对象）。", name=name))
    return raw


def _optional_jsonl_objects(pack: Path, name: str) -> int:
    """检查一个可选的 mind/*.jsonl：每行都必须是 JSON 对象；返回行数。"""
    file = pack / "mind" / name
    if not file.is_file():
        return 0
    rows = 0
    for number, line in enumerate(file.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as error:
            raise SeedError(
                t("mind/{name} 第 {line} 行不是合法 JSON：{error}", name=name, line=number, error=error)
            ) from None
        if not isinstance(row, dict):
            raise SeedError(t("mind/{name} 第 {line} 行不是对象。", name=name, line=number))
        rows += 1
    return rows


def check(pack_dir) -> dict:
    """校验一个生命包：格式、依赖、历史连续、记忆完整。"""
    pack = expand_home(pack_dir)
    if not pack.exists():
        raise SeedError(t("找不到生命包：{pack}", pack=pack))
    birth = read_json(pack / "birth.json")
    if not isinstance(birth, dict):
        raise SeedError(t("不是生命包（birth.json 缺失或损坏）：{pack}", pack=pack))

    if birth.get("format") != LIFE_FORMAT:
        raise SeedError(t("不认识的格式：{format!r}（需要 {LIFE_FORMAT}）", format=birth.get('format'), LIFE_FORMAT=LIFE_FORMAT))
    name = str(birth.get("name") or "")
    if not name:
        raise SeedError(t("birth.json 里没有名字。"))

    stored_fingerprint = birth.get("birth_hash")
    if not isinstance(stored_fingerprint, str) or not stored_fingerprint:
        raise SeedError(t("出生证没有指纹（birth_hash 缺失）——这份文件不完整。"))
    if stored_fingerprint != _birth_fingerprint(birth):
        raise SeedError(t("出生证被改过（birth_hash 不符）——名字、种子或出生时间可能被改过。"))

    for rel in REQUIRED_PACK_FILES:
        if not (pack / rel).is_file():
            raise SeedError(t("生命包缺少 {rel}（{pack}）", rel=rel, pack=pack))

    hashes = birth.get("hashes") or {}
    deps_hash = sha256((pack / "deps.lock").read_bytes())
    if hashes.get("deps") and hashes["deps"] != deps_hash:
        raise SeedError(t("依赖清单被改过（deps.lock 哈希不符）——这张出生证可能是伪造的。"))

    genome_hash = hash_tree(pack / "genome")["sha256"]
    if hashes.get("genome") and hashes["genome"] != genome_hash:
        raise SeedError(t("基因组被改过（genome/ 哈希不符）。基因不能手改。"))

    requires = birth.get("requires") or read_json(pack / "deps.lock", {}).get("runtime") or {}
    runtime = _check_runtime(requires)

    days = list_days(pack)
    if not days:
        raise SeedError(t("life/ 里一天都没有。"))
    from .clock import recorded_transitions
    transitions = recorded_transitions(pack)
    explicit_pauses = recorded_transitions(pack, explicit_only=True)
    for index, day in enumerate(days):
        if day["day"] != index + 1:
            raise SeedError(t("历史断了：第 {value} 天应该在，实际是第 {day} 天（{file}）。", value=index + 1, day=day['day'], file=day['file']))
        previous = days[index - 1] if index else None
        if previous and add_days(previous["date"], 1) != day["date"] and (
                previous["day"], previous["date"], day["day"], day["date"]) not in transitions:
            raise SeedError(t("日期不连续：{date} 之后是 {date_1}。", date=days[index - 1]['date'], date_1=day['date']))

    genesis = birth.get("genesis") or {}
    genesis_file = str(genesis.get("file") or "")
    if genesis_file and not (pack / genesis_file).is_file():
        raise SeedError(t("出生证指向的创世日不见了：{genesis_file}", genesis_file=genesis_file))

    for index, day in enumerate(days):
        text = (pack / "life" / day["file"]).read_text(encoding="utf-8")
        header = _DAY_HEADER.match(text)
        if not header:
            raise SeedError(t("第 {day} 天文件没有正确的开头（life/{file}）。", day=day['day'], file=day['file']))
        if int(header.group(1)) != day["day"] or header.group(2) != day["date"]:
            raise SeedError(t("第 {day} 天文件开头和文件名对不上（life/{file}）。", day=day['day'], file=day['file']))
        following = days[index + 1] if index + 1 < len(days) else None
        paused = following and "## 记录暂停" in text and (
            day["day"], day["date"], following["day"], following["date"]) in transitions
        if following and (day["day"], day["date"], following["day"], following["date"]) in explicit_pauses:
            paused = True
        if following and "## 今天" not in text and not paused:
            raise SeedError(t("第 {day} 天还没结束，就有了下一天（life/{file}）。", day=day['day'], file=day['file']))

    memories = _read_memories_strict(pack)
    seen_ids: set[str] = set()
    for memory in memories:
        if not all(key in memory for key in ("id", "day", "text")):
            raise SeedError(t("memories.jsonl 里有一条记忆缺字段。"))
        if not isinstance(memory["id"], str) or not memory["id"].strip():
            raise SeedError(t("memories.jsonl 里有一条记忆的 id 不是字符串。"))
        try:
            day_no = int(memory["day"])
        except (TypeError, ValueError):
            raise SeedError(t("memories.jsonl 里的记忆 {id} 的 day 不是整数。", id=memory['id'])) from None
        if day_no < 1:
            raise SeedError(t("memories.jsonl 里的记忆 {id} 的 day 小于 1。", id=memory['id']))
        if not isinstance(memory["text"], str) or not memory["text"].strip():
            raise SeedError(t("memories.jsonl 里的记忆 {id} 没有正文。", id=memory['id']))
        if "importance" in memory:
            try:
                importance = float(memory["importance"])
            except (TypeError, ValueError):
                raise SeedError(t("memories.jsonl 里的记忆 {id} 的 importance 不是数字。", id=memory['id'])) from None
            if not (0.0 <= importance <= 1.0):
                raise SeedError(t("memories.jsonl 里的记忆 {id} 的 importance 超出 0..1。", id=memory['id']))
        memory_id = str(memory["id"])
        if memory_id in seen_ids:
            raise SeedError(t("memories.jsonl 里有重复的记忆 id：{memory_id}", memory_id=memory_id))
        seen_ids.add(memory_id)

    mood_doc = read_json(pack / "mind" / "mood.json")
    if not isinstance(mood_doc, dict) or not isinstance(mood_doc.get("mood"), str):
        raise SeedError(t("mind/mood.json 坏了。"))
    if "energy" in mood_doc:
        try:
            energy_value = float(mood_doc["energy"])
        except (TypeError, ValueError):
            raise SeedError(t("mind/mood.json 里的 energy 不是数字。")) from None
        if not (0.0 <= energy_value <= 1.0) or energy_value != energy_value:
            raise SeedError(t("mind/mood.json 里的 energy 超出 0..1。"))

    brain_file = pack / "mind" / "brain.json"
    if brain_file.is_file():
        try:
            raw_brain = json.loads(brain_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/brain.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_brain, dict):
            raise SeedError(t("mind/brain.json 坏了（不是对象）。"))
    brain_cfg = load_brain_config(pack)
    if brain_cfg.get("adapter") not in ADAPTERS:
        raise SeedError(t("mind/brain.json 里的 adapter 不认识：{adapter!r}", adapter=brain_cfg.get('adapter')))
    memory_cfg = memory_settings(pack)

    agency_file = pack / "mind" / "agency.json"
    if agency_file.is_file():
        from .agency import load_agency
        load_agency(pack)
    from .planning import read as read_plans
    read_plans(pack)

    bonds_file = pack / "mind" / "bonds.json"
    bonds_info = None
    if bonds_file.is_file():
        try:
            raw_bonds = json.loads(bonds_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/bonds.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_bonds, dict):
            raise SeedError(t("mind/bonds.json 坏了（不是对象）。"))
        promises = raw_bonds.get("promises") or []
        if not isinstance(promises, list):
            raise SeedError(t("mind/bonds.json 里的 promises 不是列表。"))
        for promise in promises:
            if not isinstance(promise, dict) or not promise.get("id") or not promise.get("text"):
                raise SeedError(t("mind/bonds.json 里有一条承诺缺 id 或正文。"))
        bonds_info = {
            "promises": len(promises),
            "pending": len([item for item in promises if item.get("status") == "pending"]),
        }

    memorial_file = pack / "mind" / "memorial.json"
    if memorial_file.is_file():
        from .memorial import load_memorial
        load_memorial(pack)

    inner_file = pack / "mind" / "inner.json"
    if inner_file.is_file():
        try:
            raw_inner = json.loads(inner_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/inner.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_inner, dict):
            raise SeedError(t("mind/inner.json 坏了（不是对象）。"))
        for key in ("corrections", "dreams", "narrative_history"):
            if raw_inner.get(key) is not None and not isinstance(raw_inner.get(key), list):
                raise SeedError(t("mind/inner.json 里的 {key} 不是列表。", key=key))
        narrative = raw_inner.get("narrative")
        if narrative is not None and not isinstance(narrative, dict):
            raise SeedError(t("mind/inner.json 里的 narrative 不是对象。"))
        silence = raw_inner.get("silence")
        if silence is not None and not isinstance(silence, dict):
            raise SeedError(t("mind/inner.json 里的 silence 不是对象。"))
        from .inner import load_inner
        load_inner(pack)

    works_file = pack / "mind" / "works.json"
    works_info = None
    if works_file.is_file():
        try:
            raw_works = json.loads(works_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/works.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_works, dict):
            raise SeedError(t("mind/works.json 坏了（不是对象）。"))
        items = raw_works.get("works")
        if not isinstance(items, list):
            raise SeedError(t("mind/works.json 里的 works 不是列表。"))
        for item in items:
            if not isinstance(item, dict) or not item.get("id") or not item.get("text"):
                raise SeedError(t("mind/works.json 里有一件作品缺 id 或正文。"))
            if str(item.get("kind")) not in ("poem", "letter", "drawing"):
                raise SeedError(t("mind/works.json 里有不认识的作种类别：{kind!r}", kind=item.get('kind')))
        works_info = {
            "total": len(items),
            "poems": len([w for w in items if w.get("kind") == "poem"]),
            "letters": len([w for w in items if w.get("kind") == "letter"]),
            "drawings": len([w for w in items if w.get("kind") == "drawing"]),
        }

    hands_file = pack / "mind" / "hands.json"
    hands_info = None
    if hands_file.is_file():
        try:
            raw_hands = json.loads(hands_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/hands.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_hands, dict):
            raise SeedError(t("mind/hands.json 坏了（不是对象）。"))
        from .hands import HANDS_FORMAT, CALENDAR_FORMAT, REVISION_FORMAT, validate_calendar, load_hands
        load_hands(pack)
        if raw_hands.get("format", HANDS_FORMAT) not in (HANDS_FORMAT, CALENDAR_FORMAT, REVISION_FORMAT):
            raise SeedError("提醒文件版本不受支持；原文件已保留。")
        reminders = raw_hands.get("reminders")
        if not isinstance(reminders, list):
            raise SeedError(t("mind/hands.json 里的 reminders 不是列表。"))
        for item in reminders:
            if not isinstance(item, dict) or not item.get("text"):
                raise SeedError(t("mind/hands.json 里有一条提醒缺正文。"))
            if any(key in item for key in ("due_on", "created_on", "said_on", "said_via")):
                validate_calendar(item, raw_hands.get("format"))
            elif isinstance(item.get("due_day"), bool):
                raise SeedError(t("mind/hands.json 里有一条提醒的 due_day 不是天数。"))
            try:
                due_day = 1 if item.get("due_on") is not None else int(item.get("due_day"))
            except (TypeError, ValueError):
                raise SeedError(t("mind/hands.json 里有一条提醒的 due_day 不是天数。")) from None
            if due_day < 1:
                raise SeedError(t("mind/hands.json 里有一条提醒的 due_day 小于 1。"))
            if str(item.get("status") or "pending") not in ("pending", "said", "missed", "cancelled"):
                raise SeedError(t("mind/hands.json 里有不认识的状态：{status!r}", status=item.get('status')))
        hands_info = {
            "total": len(reminders),
            "pending": len([r for r in reminders if str(r.get("status") or "pending") == "pending"]),
            "said": len([r for r in reminders if r.get("status") == "said"]),
            "missed": len([r for r in reminders if r.get("status") == "missed"]),
            "cancelled": len([r for r in reminders if r.get("status") == "cancelled"]),
        }

    friends_file = pack / "mind" / "friends.json"
    friends_info = None
    if friends_file.is_file():
        try:
            raw_friends = json.loads(friends_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/friends.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_friends, dict):
            raise SeedError(t("mind/friends.json 坏了（不是对象）。"))
        items = raw_friends.get("friends")
        if not isinstance(items, list):
            raise SeedError(t("mind/friends.json 里的 friends 不是列表。"))
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                raise SeedError(t("mind/friends.json 里有一位朋友缺名字。"))
            if str(item.get("status") or "alive") not in ("alive", "lost"):
                raise SeedError(t("mind/friends.json 里有不认识的状态：{status!r}", status=item.get('status')))
            lost_day = item.get("lost_day")
            if lost_day is not None and (isinstance(lost_day, bool) or not isinstance(lost_day, int)):
                raise SeedError(t("mind/friends.json 里的 lost_day 必须是整数或 null。"))
        friends_info = {
            "total": len(items),
            "alive": len([f for f in items if (f.get("status") or "alive") == "alive"]),
            "lost": len([f for f in items if f.get("status") == "lost"]),
        }

    clock_file = pack / "mind" / "clock.json"
    if clock_file.is_file():
        try:
            raw_clock = json.loads(clock_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise SeedError(t("mind/clock.json 不是合法 JSON：{error}", error=error)) from None
        if not isinstance(raw_clock, dict):
            raise SeedError(t("mind/clock.json 坏了（不是对象）。"))
        last_seen = raw_clock.get("last_seen_date")
        if last_seen is not None:
            if not isinstance(last_seen, str) or len(last_seen) != 10:
                raise SeedError(t("mind/clock.json 里的 last_seen_date 要写成 YYYY-MM-DD。"))
            try:
                parse_time(last_seen)
            except (TypeError, ValueError):
                raise SeedError(
                    t("mind/clock.json 里的 last_seen_date 不是有效日期：{value}", value=last_seen)
                ) from None

    memory_settings_raw = _optional_json_object(pack, "memory.json")
    if memory_settings_raw is not None:
        strict_value = memory_settings_raw.get("strict")
        if strict_value is not None and not isinstance(strict_value, bool):
            raise SeedError(t("mind/memory.json 里的 strict 必须是 true/false。"))
        daily_max = memory_settings_raw.get("daily_max")
        if daily_max is not None:
            if isinstance(daily_max, bool) or not isinstance(daily_max, int) or daily_max < 1:
                raise SeedError(t("mind/memory.json 里的 daily_max 必须是至少 1 的整数。"))

    vision_settings_raw = _optional_json_object(pack, "vision.json")
    if vision_settings_raw is not None:
        enabled = vision_settings_raw.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise SeedError(t("mind/vision.json 里的 enabled 必须是 true/false。"))
        max_side = vision_settings_raw.get("max_side")
        if max_side is not None:
            if isinstance(max_side, bool) or not isinstance(max_side, int) or max_side < 256:
                raise SeedError(t("mind/vision.json 里的 max_side 必须是至少 256 的整数。"))

    from .facts import read as read_facts
    read_facts(pack)
    from .learning import read as read_learning
    read_learning(pack)
    from .relationships import read as read_relationships
    read_relationships(pack)
    from .disclosure import read as read_disclosure
    read_disclosure(pack)
    from .life_story import read as read_life_story
    read_life_story(pack)
    from .media_archive import read as read_media
    read_media(pack)
    semantic_raw = _optional_json_object(pack, "semantic.json")
    if semantic_raw is not None:
        from .semantic import configuration as semantic_configuration
        semantic_configuration(pack)

    persona_raw = _optional_json_object(pack, "persona.json")
    if persona_raw is not None:
        probes = persona_raw.get("probes")
        if not isinstance(probes, list):
            raise SeedError(t("mind/persona.json 里的 probes 不是列表（重新 capture 一次）。"))
        if persona_raw.get("format") == "seedbank/persona@2":
            from .persona import load_persona
            load_persona(pack)

    _optional_jsonl_objects(pack, "growth.jsonl")
    _optional_jsonl_objects(pack, "vision.jsonl")
    from .development import events as development_events
    development_rows = development_events(pack)
    body_raw = _optional_json_object(pack, "body.json")
    if body_raw is not None:
        energy = body_raw.get("energy")
        if (body_raw.get("format") != "seedbank/body@1"
                or isinstance(energy, bool) or not isinstance(energy, (int, float))
                or not 0 <= energy <= 1):
            raise SeedError("mind/body.json 的格式或精力值无效。")

    return {
        "ok": True,
        "name": name,
        "species": (birth.get("species") or {}).get("name", ""),
        "bornAt": birth.get("born_at"),
        "days": len(days),
        "memories": len(memories),
        "runtime": runtime,
        "depsHash": deps_hash,
        "genomeHash": genome_hash,
        "brain": describe_brain(brain_cfg),
        "memory": memory_cfg,
        "bonds": bonds_info,
        "works": works_info,
        "hands": hands_info,
        "friends": friends_info,
        "developmentEvents": len(development_rows),
        "clock": "realtime",  # 出生证里的旧字段只作历史记录，运行时固定按真实的一天走
    }


def print_hatch(result: dict) -> None:
    print(t("[seed] 从蛋孵化「{value}」", value=result['name']))
    print(t("      物种：{value} v{version}", value=result['species'].get('name'), version=result['species'].get('version')))
    born = parse_time(result["bornAt"])
    local = result["localDate"]
    print(t("      出生：{bornAt}（本机 {YmdHM}，{local}）", bornAt=result['bornAt'], YmdHM=born.astimezone().strftime('%Y-%m-%d %H:%M'), local=local))
    print(t("      种子：{value}…（熵 + 时间决定；不可重算，只会重现）", value=result['seed'][:16]))
    picked_names = "、".join(str(t.get("text", t.get("id", ""))) for t in result["picked"])
    print(t("      天赋：{value}", value=picked_names or t('（没有特别的）')))
    print(t("      时钟：按真实的一天走（每过一个凌晨，她过完一天）"))
    print(t("      生命包：{value}", value=result['path']))
    print(t("      下一步："))
    print(t("        python tools/seed/seed.py sense \"{value}\" --image 一张图.png --note 给你看样东西", value=result['path']))
    print(f"        python tools/seed/seed.py day \"{result['path']}\"")
    print(f"        python tools/seed/seed.py chat \"{result['path']}\"")


def print_check(result: dict) -> None:
    runtime = result["runtime"]
    print(t("[seed] 生命包：{value}", value=result['name']))
    print(t("      物种：{species} · 出生：{bornAt}（第 {days} 天）", species=result['species'], bornAt=result['bornAt'], days=result['days']))
    print(t("      依赖：{need} · 当前 {have}", need=runtime['need'], have=runtime['have']))
    print(t("      脑：{brain}", brain=result['brain']))
    memory_cfg = result.get("memory") or {}
    strict_word = t("严格") if memory_cfg.get("strict", True) else t("宽松")
    print(t("      记忆：{memories} 条 · 天：{days} 天 · {strict_word}模式（每轮 ≤{daily_max} 条）", memories=result['memories'], days=result['days'], strict_word=strict_word, daily_max=memory_cfg.get('daily_max', 8)))
    bonds = result.get("bonds")
    if bonds:
        print(t("      关系：承诺 {promises} 条（未做到 {pending} 条）", promises=bonds['promises'], pending=bonds['pending']))
    works = result.get("works")
    if works:
        print(t("      作品：诗 {poems} 首 / 信 {letters} 封 / 画 {drawings} 张（共 {total} 件）", poems=works['poems'], letters=works['letters'], drawings=works['drawings'], total=works['total']))
    friends = result.get("friends")
    if friends:
        print(t("      他者：朋友 {total} 位（还在 {alive} / 失联 {lost}）", total=friends['total'], alive=friends['alive'], lost=friends['lost']))
    hands = result.get("hands")
    if hands:
        print(t("      手：提醒 {total} 条（还没说 {pending} / 说过了 {said} / 错过 {missed}）", total=hands['total'], pending=hands['pending'], said=hands['said'], missed=hands['missed']))
        if hands.get("cancelled"):
            print(t("      已取消提醒：{count} 条（历史保留）", count=hands["cancelled"]))
    print(t("      依赖清单：{value}… ✓", value=result['depsHash'][:8]))
    print(t("      基因组：{value}… ✓", value=result['genomeHash'][:8]))
    if not runtime["ok"]:
        print(t("      ✗ 依赖不可得：需要 {need}，当前 {have}——她今天不能被运行。", need=runtime['need'], have=runtime['have']))
        return
    print(t("      校验：全部通过"))
