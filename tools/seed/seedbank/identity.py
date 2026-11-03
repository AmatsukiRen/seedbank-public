"""Species-neutral runtime identity; seed-specific stories stay in the seed."""
from pathlib import Path

from .util import read_json


def profile(pack):
    value = read_json(Path(pack) / "genome" / "profile.json", {})
    if isinstance(value, dict) and value.get("format") == "seedbank/profile@1":
        return value
    birth = read_json(Path(pack) / "birth.json", {}) or {}
    species = (birth.get("species") or {}).get("id")
    # Compatibility is presentation only; it never rewrites an existing pack.
    return {"identity_mode": "seeded", "avatar": "dafeiyu" if species == "dafeiyu" else "seed"}
