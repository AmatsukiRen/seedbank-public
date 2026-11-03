"""汇总界面里的中文原文，生成待翻译 key 列表。

开发/翻译辅助脚本，不参与运行时。用法：
    python tools/seed/i18n_extract.py            # 扫描 tools/seed/seedbank/*.py
    python tools/seed/i18n_extract.py --write    # 同时写 locales/_keys.json
"""
from __future__ import annotations

import argparse
import io
import json
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "seedbank"
CJK = re.compile(r"[\u4e00-\u9fff]")
# 看起来像代码/路径/正则的串先排除
SKIP = re.compile(
    r"^(?:[\w./\\-]+|\.\.\.?|[\[\](){}<>|*+?^$]+)$|"
    r"(?:seed |python |\.py|\.json|\.life|\.egg|://|\\d|%[sd]|\\{|\\})"
)


def iter_strings(path: Path):
    try:
        with path.open("rb") as fh:
            tokens = tokenize.tokenize(fh.readline)
            for tok in tokens:
                if tok.type != tokenize.STRING:
                    continue
                text = tok.string
                if text.startswith(("'''", '"""', "r'''", 'r"""')):
                    continue
                value = _literal(text)
                if not value or not CJK.search(value):
                    continue
                if len(value) > 120:
                    continue
                if SKIP.search(value):
                    continue
                yield value.replace("\\n", "\n")
    except (OSError, tokenize.TokenError):
        return


def _literal(text: str) -> str:
    prefix = ""
    body = text
    for pre in ("fr", "rf", "f", "r", "u", "b"):
        if body.startswith(pre):
            prefix, body = pre, body[len(pre):]
            break
    if "b" in prefix:
        return ""
    try:
        value = eval(text, {"__builtins__": {}}, {"__builtins__": {}})  # noqa: S307
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def collect(directory: Path) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(directory.glob("*.py")):
        for value in iter_strings(path):
            found.setdefault(path.name, set()).add(value)
    return {name: sorted(values) for name, values in found.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = collect(PKG)
    total = sum(len(v) for v in data.values())
    for name, values in data.items():
        print(f"{name}: {len(values)}")
    print(f"合计 {total}")
    if args.write:
        out = PKG / "locales" / "_keys.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        flat = sorted({key for keys in data.values() for key in keys})
        out.write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out}（{len(flat)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
