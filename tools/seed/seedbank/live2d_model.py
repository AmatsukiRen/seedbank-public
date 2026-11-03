"""Local presentation assets, independent of life-pack identity and memory."""
from __future__ import annotations

import json
from pathlib import Path


# Third-party models are selected locally, never shipped or assumed.
DEFAULT_MODEL = ""
KNOWN_MODEL_FILENAME = "大肥鱼.model3.json"
MODEL_CREDIT = "DeepSeek-chan（大肥鱼） · 原画及拆分：神宫凉子 · Live2D 建模：霓虹猫_NeonNeko"


def descriptor(source: str | Path) -> tuple[str, dict]:
    """Read an in-memory descriptor; never rewrite, copy or download the model.

    Resolve references before handing them to the native SDK, which can fail
    without a useful exception on missing files. References stay inside the
    selected model directory. The supplied model omits its animation registry.
    """
    path = Path(source).expanduser().resolve()
    if not path.name.lower().endswith(".model3.json") or not path.is_file():
        raise ValueError("请选择完整模型目录中的 .model3.json 文件。")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("模型配置文件过大。")
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.get("Version") != 3:
        raise ValueError("需要 Cubism 3 或更新的模型配置。")
    refs = document.get("FileReferences")
    if not isinstance(refs, dict) or not refs.get("Moc") or not refs.get("Textures"):
        raise ValueError("模型配置缺少 Moc 或 Textures。")
    root = path.parent

    def local(value):
        if not isinstance(value, str) or not value or "://" in value:
            raise ValueError("模型只能引用同一目录中的本地文件。")
        target = (root / value).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("模型文件缺失或位于目录之外：" + value)
        return target.as_posix()

    for key in ("Moc", "Physics", "Pose", "DisplayInfo", "UserData"):
        if refs.get(key):
            refs[key] = local(refs[key])
    if not isinstance(refs["Textures"], list):
        raise ValueError("Textures 必须是文件列表。")
    refs["Textures"] = [local(value) for value in refs["Textures"]]
    motions = refs.setdefault("Motions", {})
    expressions = refs.setdefault("Expressions", [])
    if not isinstance(motions, dict) or not isinstance(expressions, list):
        raise ValueError("动作或表情配置格式不正确。")
    # Only this supplied model receives these known, reversible expressions.
    # Costume, body-shape and accessory toggles remain at the author's defaults.
    if path.name == KNOWN_MODEL_FILENAME:
        for group, filename in (("SeedIdle", "IDLE"), ("SeedWave", "默认手切举手"),
                                ("SeedReturn", "举手切默认手")):
            relative = f"Animation/{filename}.motion3.json"
            if (root / relative).is_file():
                entry = {"File": relative}
                if group in {"SeedWave", "SeedReturn"}:
                    # These short clips switch hand layers via Movement2.
                    # Cubism's default 1s fade-out can leave a partial layer
                    # in the SDK's saved pose; idle does not reset that value.
                    # Keep full end-of-clip weight so the authored final pose
                    # is saved. Only our injected entries get this override.
                    entry["FadeOutTime"] = 0.0
                motions.setdefault(group, [entry])
        names = {item.get("Name") for item in expressions if isinstance(item, dict)}
        for name, filename in (("SeedHappy", "＞＜"), ("SeedThink", "加载"), ("SeedWarm", "脸红"),
                               ("SeedSad", "流泪"), ("SeedNervous", "流冷汗"), ("SeedAngry", "黑脸")):
            relative = f"Exp3/{filename}.exp3.json"
            if name not in names and (root / relative).is_file():
                expressions.append({"Name": name, "File": relative})
    for rows in motions.values():
        if not isinstance(rows, list):
            raise ValueError("动作配置必须是列表。")
        for row in rows:
            if not isinstance(row, dict) or not row.get("File"):
                raise ValueError("动作配置缺少文件。")
            row["File"] = local(row["File"])
            if row.get("Sound"):
                row["Sound"] = local(row["Sound"])
    for row in expressions:
        if not isinstance(row, dict) or not row.get("Name") or not row.get("File"):
            raise ValueError("表情配置缺少名称或文件。")
        row["File"] = local(row["File"])
    # Cubism's JSON parser requires indented input. Absolute references allow
    # Unicode paths without creating a modified model file beside the original.
    return json.dumps(document, ensure_ascii=False, indent=2), {
        "motions": {group for group, rows in motions.items() if rows},
        "expressions": {row["Name"] for row in expressions},
    }
