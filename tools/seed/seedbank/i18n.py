"""轻量多语言：中文原文即 key，缺翻译时自动回落中文。

设计原则：
- 不引入 gettext / babel 等依赖，只用标准库；
- 代码里写 `t("查一段记忆…")`，中文原文就是 key，翻译表在 `locales/<locale>.json`；
- 缺翻译时返回原文，绝不因为缺翻译而报错；
- 语言只影响界面/CLI/文档，不翻译她的日记、记忆、承诺——那是她自己的话。
"""
from __future__ import annotations
import sys

import json
import os
from pathlib import Path
from typing import Dict

LOCALES = ("zh_CN", "en_US", "ja_JP", "ko_KR")
DEFAULT_LOCALE = "zh_CN"
LOCALE_LABELS: Dict[str, str] = {
    "zh_CN": "简体中文",
    "en_US": "English",
    "ja_JP": "日本語",
    "ko_KR": "한국어",
}

_LOCALE_DIR = Path(__file__).resolve().parent / "locales"
_current: str = DEFAULT_LOCALE
_cache: Dict[str, dict] = {}


def _locale_dirs() -> list[Path]:
    """源码 / PyInstaller 冻结后可能的 locales 位置（按优先级）。"""
    here = Path(__file__).resolve().parent
    dirs = [here / "locales"]
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", here))
        dirs += [
            base / "seedbank" / "locales",
            base / "tools" / "seed" / "seedbank" / "locales",
        ]
    # 源码仓库：tools/seed/seedbank/locales
    try:
        dirs.append(here / "locales")
    except Exception:
        pass
    out: list[Path] = []
    seen = set()
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def normalize_locale(code: str | None) -> str:
    """把各种写法（zh、zh-CN、zh_Hans、en-US、ja、ko）归一成受支持的语言代码。"""
    if not code:
        return DEFAULT_LOCALE
    raw = str(code).strip().replace("-", "_")
    if not raw:
        return DEFAULT_LOCALE
    head = raw.split("_")[0].lower()
    for loc in LOCALES:
        if raw.lower() == loc.lower():
            return loc
    for loc in LOCALES:
        if loc.split("_")[0].lower() == head:
            return loc
    return DEFAULT_LOCALE


def detect_locale() -> str:
    """按 环境变量 → 系统 locale 的顺序猜一个语言。"""
    for env in ("SEEDBANK_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(env)
        if value:
            return normalize_locale(value)
    try:
        import locale as _locale

        code = _locale.getlocale()[0] or _locale.getdefaultlocale()[0]
        if code:
            return normalize_locale(code)
    except Exception:
        pass
    return DEFAULT_LOCALE


def available_locales() -> tuple[str, ...]:
    return LOCALES


def locale_label(code: str) -> str:
    return LOCALE_LABELS.get(normalize_locale(code), code)


def _load(code: str) -> dict:
    if code in _cache:
        return _cache[code]
    data: dict = {}
    for folder in _locale_dirs():
        path = folder / f"{code}.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                data = {}
    _cache[code] = data
    return data


def set_locale(code: str) -> str:
    global _current
    _current = normalize_locale(code)
    return _current


def get_locale() -> str:
    return _current


def t(text: str, /, **kwargs) -> str:
    """翻译一段界面文本。text 是中文原文；缺翻译/翻译损坏都返回原文。"""
    translated = _load(_current).get(text)
    if not isinstance(translated, str) or not translated:
        translated = text
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return translated
    return translated


def all_keys() -> list[str]:
    """中文原文 key 的集合（用于翻译进度检查）。"""
    return sorted(_load(DEFAULT_LOCALE))
