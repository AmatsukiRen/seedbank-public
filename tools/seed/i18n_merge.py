"""把窗口/后端代理交上来的中文 key 清单合并进 locales/_keys.json。

用法:
  python tools/seed/i18n_merge.py            # 合并 %TEMP%\\i18n_*keys.json + locales/_keys.json
  python tools/seed/i18n_merge.py --check    # 检查四种语言各自缺哪些 key
  python tools/seed/i18n_merge.py --stub     # 给缺的 key 写英文兜底（=原文，便于先跑起来）

清单格式：JSON 数组（字符串），或 {"keys": [...]}，或对象（取键名）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "tools" / "seed" / "seedbank" / "locales"
TEMP = Path.home() / "AppData" / "Local" / "Temp"
SOURCES = [
    TEMP / "i18n_window_keys.json",
    TEMP / "i18n_backend_keys.json",
]
ALL = ("zh_CN", "en_US", "ja_JP", "ko_KR")


def _load_keys(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("keys") if isinstance(data.get("keys"), list) else list(data.keys())
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str) and item.strip()]


def collect() -> list[str]:
    keys: set[str] = set()
    for source in SOURCES:
        keys.update(_load_keys(source))
    keys.update(_load_keys(LOCALES / "_keys.json"))
    return sorted(keys)


def _read(locale: str) -> dict[str, str]:
    path = LOCALES / f"{locale}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _write(locale: str, mapping: dict[str, str]) -> None:
    path = LOCALES / f"{locale}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def merge(stub: bool = False) -> dict:
    keys = collect()
    merged: dict = {}
    if keys:
        (LOCALES / "_keys.json").write_text(
            json.dumps(keys, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        merged["keys"] = len(keys)
    for locale in ALL:
        existing = _read(locale) if locale != "zh_CN" else {k: k for k in keys}
        if locale != "zh_CN" and stub:
            for key in keys:
                existing.setdefault(key, key)
        _write(locale, existing)
        merged[locale] = len(existing)
    return merged


def check() -> dict:
    keys = set(collect())
    report = {}
    for locale in ALL:
        mapping = _read(locale)
        missing = sorted(keys - set(mapping))
        report[locale] = {"total": len(mapping), "missing": len(missing), "examples": missing[:10]}
    return report


def main(argv: list[str]) -> int:
    stub = "--stub" in argv
    report = check() if "--check" in argv else merge(stub=stub)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
