"""他者：别的鱼来串门、礼物、以及失去（1.18）。

她的一生里，除了主人和事件，还可以有别的鱼。
朋友不是联系人列表，是「来过、说过话、记得」的记录。
失联的朋友会被标记为 lost，并写进有限性里的告别。
"""

from __future__ import annotations

from .i18n import t
from pathlib import Path
from .pack_lock import durable

from .util import SeedError, now_iso, read_json, write_json_atomic

FRIENDS_FORMAT = "seedbank/friends@1"
MAX_FRIENDS = 32
MAX_NOTE_CHARS = 120


def friends_path(pack_dir) -> Path:
    return Path(pack_dir) / "mind" / "friends.json"


def load_friends(pack_dir) -> dict:
    """朋友记录只在第一次有鱼来访时创建。"""
    path = friends_path(pack_dir)
    if not path.is_file():
        return {"format": FRIENDS_FORMAT, "friends": [], "updated_at": None}
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("friends"), list):
        raise SeedError("来访记录格式不完整；原文件已保留。")
    if any(not isinstance(r, dict) or not isinstance(r.get("name"), str) or not r["name"].strip()
           or r.get("status", "alive") not in ("alive", "lost") for r in data["friends"]):
        raise SeedError("来访记录格式不完整；原文件已保留。")
    data["format"] = FRIENDS_FORMAT
    data.setdefault("updated_at", None)
    return data


@durable
def save_friends(pack_dir, data: dict) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("friends"), list):
        raise SeedError(t("friends.json 的结构不对（不是对象或 friends 不是列表）"))
    data["format"] = FRIENDS_FORMAT
    data["updated_at"] = now_iso()
    for item in data["friends"]:
        if not isinstance(item, dict) or not item.get("name"):
            raise SeedError(t("friends.json 里有一个朋友缺名字"))
    write_json_atomic(friends_path(pack_dir), data)


def _clean_text(text: str, limit: int = MAX_NOTE_CHARS) -> str:
    return " ".join(str(text or "").split())[:limit]


def _find(data: dict, name: str) -> dict | None:
    by_id = [item for item in data["friends"] if item.get("id") == name or item.get("person_id") == name]
    matches = by_id or [item for item in data["friends"] if item.get("name") == name]
    if len(matches) > 1:
        raise SeedError("有多位同名来访者，请使用来访记录编号。")
    return matches[0] if matches else None


@durable
def record_visit(
    pack_dir,
    *,
    name: str,
    species_path: str = "",
    day: int,
    note: str = "",
    gift: str = "",
    identity_key: str = "", person_id: str = "",
) -> dict:
    """别的鱼来看她：记下名字、来自哪里、说过什么、送过什么。"""
    name = _clean_text(name, 40)
    if not name:
        raise SeedError(t("来访的鱼得有个名字"))
    path = Path(species_path) if species_path else None
    data = load_friends(pack_dir)
    matches = [r for r in data["friends"] if r.get("identity_key") == identity_key] if identity_key else []
    if len(matches) > 1:
        raise SeedError("来访身份重复，请先核对原记录。")
    friend = matches[0] if matches else None
    if not identity_key:
        # Historical direct callers have no birth identity; do not merge their
        # names into a newly identified individual.
        friend = _find({"friends": [r for r in data["friends"] if not r.get("identity_key")]}, name)
    if friend is None:
        friend = {
            "id": f"f_{len(data['friends']) + 1:04d}",
            "name": name,
            "species_path": str(path) if path else "",
            "visit_count": 0,
            "gift_count": 0,
            "last_visit_day": None,
            "status": "alive",
            "lost_day": None,
            "first_day": int(day),
            "identity_key": identity_key, "person_id": person_id,
        }
        data["friends"].append(friend)
    friend["visit_count"] = int(friend.get("visit_count") or 0) + 1
    friend["last_visit_day"] = int(day)
    if path:
        friend["species_path"] = str(path)
    if note:
        friend["last_note"] = _clean_text(note)
    if gift:
        friend["gift_count"] = int(friend.get("gift_count") or 0) + 1
        friend["last_gift"] = _clean_text(gift)
    friend["status"] = "alive"
    friend["lost_day"] = None
    save_friends(pack_dir, data)
    return friend


@durable
def mourn_friend(pack_dir, name: str, *, day: int) -> dict:
    """一条鱼不见了：她记下这一天，并且送别一次。"""
    name = _clean_text(name, 100)
    data = load_friends(pack_dir)
    friend = _find(data, name)
    if friend is None:
        raise SeedError(t("她的朋友里没有谁叫「{value}」", value=name))
    if friend.get("status") == "lost":
        raise SeedError("这位来访者已经记录为失联。")
    friend["status"] = "lost"
    friend["lost_day"] = int(day)
    save_friends(pack_dir, data)
    return friend


def list_friends(pack_dir) -> list:
    return list(load_friends(pack_dir)["friends"])


def friends_summary(pack_dir) -> dict:
    friends = list_friends(pack_dir)
    return {
        "total": len(friends),
        "alive": len([f for f in friends if f.get("status") != "lost"]),
        "lost": len([f for f in friends if f.get("status") == "lost"]),
        "recent": [
            {
                "name": f.get("name"),
                "id": f.get("id"), "person_id": f.get("person_id", ""),
                "visits": int(f.get("visit_count") or 0),
                "last_visit_day": f.get("last_visit_day"),
                "lost_day": f.get("lost_day"),
                "status": f.get("status") or "alive",
            }
            for f in friends[-3:]
        ],
    }


def describe_friends(pack_dir) -> str:
    friends = list_friends(pack_dir)
    lines = [t("她认识的鱼：")]
    if not friends:
        lines.append(t("  还没有别的鱼来过。"))
        return "\n".join(lines)
    for friend in friends:
        label = t("失联") if friend.get("status") == "lost" else t("还在")
        lines.append(
            t(
                "  {name} · {label} · 来过 {visits} 次（最近第 {day} 天）",
                name=f"[{friend.get('id', '')}] {friend.get('name', '')}",
                label=label,
                visits=friend.get("visit_count") or 0,
                day=friend.get("last_visit_day"),
            )
        )
    return "\n".join(lines)
