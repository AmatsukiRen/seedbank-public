"""首次启动：从开放种子开始一段人生。

这个模块只做「准备数据」这几件事，界面在 `window.py` 的 SetupWizard 里：

1. 找到种子（默认 `eggs/open.egg/`，可用 SEEDBANK_EGG 指定其他种子）；
2. 在用户选的位置孵出 `<名字>.life/`；
3. 把选好的脑写进 `mind/brain.json`；
4. 记住「上次打开的那条鱼」，以后双击就能直接进她的房间。

所有函数都不依赖 tkinter，方便测试与命令行使用。配置文件在
`~/.seedbank/config.json`，和生命包本身无关——删掉它不会弄丢任何鱼。
"""

from __future__ import annotations

from .i18n import t
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from .pack import hatch
from .settings import save_settings
from .util import SeedError, now_iso

CONFIG_FORMAT = "seedbank/config@1"
CONFIG_VERSION = 1


# ---------------------------------------------------------------------------
# 配置文件
# ---------------------------------------------------------------------------

def config_dir() -> Path:
    return Path.home() / ".seedbank"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    """读配置；坏文件当作空配置（不因为一个 json 坏了就开不了窗）。"""
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(patch: dict) -> dict:
    """合并写入配置；未知键保留（窗口尺寸等也放在这里）。"""
    current = load_config()
    current.update(patch or {})
    current["format"] = CONFIG_FORMAT
    current["version"] = CONFIG_VERSION
    current["updated_at"] = now_iso()
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return current


# ---------------------------------------------------------------------------
# 蛋在哪
# ---------------------------------------------------------------------------

def find_egg() -> Path:
    """找蛋：环境变量 → 冻结后的 exe → 仓库布局。找不到就报错。"""
    env = os.environ.get("SEEDBANK_EGG", "").strip()
    if env:
        path = Path(env).expanduser()
        if (path / "species.json").is_file():
            return path
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for rel in (Path("eggs") / "open.egg",
                    Path("tools") / "seed" / ".." / ".." / "eggs" / "open.egg"):
            candidate = (base / rel).resolve()
            if (candidate / "species.json").is_file():
                return candidate
    repo = Path(__file__).resolve().parents[3]  # seedbank/ → seed/ → tools/ → 仓库根
    candidate = repo / "eggs" / "open.egg"
    if (candidate / "species.json").is_file():
        return candidate
    raise SeedError(t("找不到种子：请保留 eggs/open.egg，或用 SEEDBANK_EGG 指定。"))


# ---------------------------------------------------------------------------
# 领养
# ---------------------------------------------------------------------------

_FISH_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_name(name: str) -> str:
    """名字清理：去掉首尾空白与非法字符，最长 24 字。空名字报错。"""
    text = (name or "").strip()
    if not text:
        raise SeedError(t("她的名字不能是空的。"))
    text = _FISH_BAD_CHARS.sub("", text).strip()
    if not text:
        raise SeedError(t("这个名字里没有能用的字。"))
    if len(text) > 24:
        raise SeedError(t("名字太长了：最多 24 个字。"))
    return text


def default_pack_parent() -> Path:
    return Path.home() / "Seedbank"


def suggest_pack_path(name: str) -> Path:
    return default_pack_parent() / f"{clean_name(name)}.life"


def create_fish(name: str, parent_dir: str | Path, brain: dict | None = None) -> Path:
    """创建个体并记住生命包路径；保留 create_fish 名称兼容已有调用。

    返回生命包目录；已存在同名目录会报错（不覆盖别人的鱼）。
    """
    clean = clean_name(name)
    parent = Path(parent_dir).expanduser()
    parent.mkdir(parents=True, exist_ok=True)
    egg = find_egg()
    target = parent / f"{clean}.life"
    if target.exists():
        raise SeedError(t("这里已经有名为「{clean}」的生命包：{target}", clean=clean, target=target))
    hatch(target, egg, clean)
    if brain:
        save_settings(target, brain)
    save_config({"default_pack": str(target)})
    return target


# ---------------------------------------------------------------------------
# 上次打开的那条鱼
# ---------------------------------------------------------------------------

def resolve_pack() -> Path | None:
    """配置里记住的生命包还在的话返回它；否则 None（需要重新领养/选择）。"""
    config = load_config()
    raw = config.get("default_pack")
    if not raw or not isinstance(raw, str):
        return None
    try:
        path = Path(raw).expanduser()
    except (OSError, ValueError):
        return None
    if (path / "birth.json").is_file():
        return path
    return None


def remember_pack(pack_dir: str | Path) -> dict:
    return save_config({"default_pack": str(Path(pack_dir).expanduser())})


def describe_setup() -> dict:
    """给命令行/界面看的首次使用状态。"""
    pack = resolve_pack()
    return {
        "has_config": config_path().is_file(),
        "config_path": str(config_path()),
        "default_pack": str(pack) if pack else None,
        "egg": str(find_egg()) if _egg_exists() else None,
    }


def _egg_exists() -> bool:
    try:
        find_egg()
    except SeedError:
        return False
    return True
