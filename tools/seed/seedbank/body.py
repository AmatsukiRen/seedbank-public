"""A small digital resource model: activity costs energy; elapsed rest restores it."""
from datetime import datetime
import math
from pathlib import Path

from .util import now_iso, parse_time, read_json, write_json_atomic
from .pack_lock import durable

COSTS = {"chat": 0.015, "initiate": 0.02, "compose": 0.08, "reflect": 0.04, "diary": 0.02}


def state(pack, *, now=None):
    when = parse_time(now) if isinstance(now, str) else (now or datetime.now().astimezone())
    saved = read_json(Path(pack) / "mind" / "body.json", {}) or {}
    mood = read_json(Path(pack) / "mind" / "mood.json", {}) or {}
    raw = saved if isinstance(saved, dict) and saved else mood
    if not isinstance(raw, dict):
        raw = {}
    try:
        energy = float(raw.get("energy", 0.6))
    except (ValueError, TypeError):
        energy = 0.6
    if not math.isfinite(energy):
        energy = 0.6
    try:
        previous = parse_time(raw.get("updated_at"))
        elapsed = max(0, (when - previous).total_seconds())
        when = max(when, previous)
    except (ValueError, TypeError, AttributeError):
        elapsed = 0
    energy = round(min(1.0, max(0.0, energy) + min(elapsed, 8 * 3600) / 3600 * 0.08), 3)
    return {"format": "seedbank/body@1", "energy": energy, "updated_at": when.isoformat(),
            "resting": bool(saved.get("resting", False)) if isinstance(saved, dict) else False}


@durable
def spend(pack, activity):
    value = state(pack)
    value["energy"] = round(max(0, value["energy"] - COSTS.get(activity, 0)), 3)
    value["resting"] = activity == "rest"
    value["last_activity"] = activity
    write_json_atomic(Path(pack) / "mind" / "body.json", value)
    mood = read_json(Path(pack) / "mind" / "mood.json", {}) or {}
    if not isinstance(mood, dict):
        mood = {}
    write_json_atomic(Path(pack) / "mind" / "mood.json", {
        **mood, "energy": value["energy"], "updated_at": now_iso()})
    return value
