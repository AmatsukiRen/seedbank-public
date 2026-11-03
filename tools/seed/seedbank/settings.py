"""她的设置 —— 脑、记忆卫生、窗口偏好。都写在生命包里，跟着她走。

分两处存：
  mind/brain.json    脑（适配器、模型、地址、密钥环境变量名、温度）
  mind/memory.json   记忆卫生（严格去重、每轮最多提炼几条）

窗口自己的偏好（置顶、开机自启）是「这台机器」的事，不跟着生命包走，
存在 ~/.seedbank/ui.json。窗口的 geometry（大小位置）也写在这个文件里，
所以读写时必须保留不认识的键。

窗口的设置面板、命令行 `seed brain` 和这些函数共用同一份读写逻辑。

生命包只存环境变量名或本机加密凭据引用，API Key 本身不进入生命包。
"""

from __future__ import annotations

from .i18n import t
import os
import re
import subprocess
import sys
from pathlib import Path
from .pack_lock import durable

from .brain import (
    ADAPTERS,
    BrainConfigError,
    anthropic_transport,
    codex_transport,
    workbuddy_transport,
    describe_brain,
    load_brain_config,
    openai_transport,
    save_brain_config,
)
from .util import read_json, write_json_atomic

MEMORY_FORMAT = "seedbank/memory@1"

DEFAULT_MEMORY = {
    "format": MEMORY_FORMAT,
    "strict": True,
    "daily_max": 8,
}

# 设置面板里的预设。hint 会原样显示给用户。
PRESETS = [
    {
        "label": "不联网（桩 · 测试用）",
        "adapter": "stub",
        "model": None,
        "base_url": None,
        "api_key_env": "SEEDBANK_API_KEY",
        "hint": "不联网、确定性。她的第一批日子、示例和 CI 都用它。",
    },
    {
        "label": "DeepSeek V4.1 Flash（便宜、快）",
        "adapter": "anthropic",
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key_env": "DEEPSEEK_API_KEY",
        "hint": "DeepSeek 的 Messages 兼容端点；使用你自己的 API Key。",
    },
    {
        "label": "DeepSeek V4 Pro（更聪明、更贵）",
        "adapter": "anthropic",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key_env": "DEEPSEEK_API_KEY",
        "hint": "同一端点，换模型名即可。",
    },
    {
        "label": "Claude（官方）",
        "adapter": "anthropic",
        "model": "claude-sonnet-4-5",
        "base_url": None,
        "api_key_env": "ANTHROPIC_API_KEY",
        "hint": "Anthropic 官方 Messages API。",
    },
    {
        "label": "OpenAI 兼容（自定义云端）",
        "adapter": "openai-compatible",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "SEEDBANK_API_KEY",
        "hint": "任何 Chat Completions 兼容服务（OpenAI / DeepSeek / vLLM …）。",
    },
    {
        "label": "Ollama（本地、离线）",
        "adapter": "openai-compatible",
        "model": "qwen2.5:7b",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "hint": "本地模型不需要 key。常见地址 http://localhost:11434/v1（Ollama）、http://localhost:1234/v1（LM Studio）。",
    },
    {
        "label": "LM Studio（本地、离线）",
        "adapter": "openai-compatible",
        "model": "local-model",
        "base_url": "http://localhost:1234/v1",
        "api_key_env": "",
        "hint": "先在 LM Studio 里启动本地服务器，再点「测试连接」。",
    },
    {
        "label": "vLLM / 其他本地服务",
        "adapter": "openai-compatible",
        "model": "",
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key_env": "",
        "hint": "任何本地 OpenAI 兼容端点都可以；模型名填服务里的模型 id。",
    },
]

PRESETS.append({
    "label": "GPT（当前 Codex 账号）", "adapter": "codex", "model": "gpt-6-astra",
    "base_url": None, "api_key_env": "",
    "hint": "使用本机 Codex 的 ChatGPT 登录与账号额度；无需填写密钥。当前支持文字，图片仅归档。",
})

PRESETS.append({
    "label": "OpenAI（API Key）", "adapter": "openai-compatible", "model": "gpt-4.1-mini",
    "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
    "hint": "使用自己的 OpenAI API Key；与 Codex 登录通道分开。模型名称可自行修改。",
})

from .providers import ADDITIONAL_PRESETS, COMPATIBILITY_DEFAULTS

# Preserve existing preset indices used by older UI/CLI callers.
for _preset, _provider in zip(PRESETS, ("", "deepseek", "deepseek", "anthropic", "",
                                     "", "", "", "codex", "openai")):
    _preset.update(provider=_provider, response_format_mode="prompt", temperature_mode="default")
PRESETS.extend(ADDITIONAL_PRESETS)
from .workbuddy_transport import LABEL as WORKBUDDY_LABEL, HINT as WORKBUDDY_HINT
PRESETS.append({"label": WORKBUDDY_LABEL, "adapter": "workbuddy", "provider": "workbuddy",
                "model": "", "base_url": "", "api_key_env": "", "hint": WORKBUDDY_HINT,
                "response_format_mode": "prompt", "temperature_mode": "default"})

_BRAIN_KEYS = ("adapter", "model", "base_url", "api_key_env", "api_key_source", "api_key_ref", "temperature", "max_tokens", "fallback", "input_budget", "codex_max_calls", "workbuddy_max_calls", "provider", "response_format_mode", "temperature_mode")
_MEMORY_KEYS = ("strict", "daily_max")

# 视觉模型配置。接收流程先归档原件，再按调用方式尝试视觉解释；
# 原件保留由 media_intake/media_archive 管理，不由这里的兼容 enabled 字段决定。
VISION_FORMAT = "seedbank/vision@1"
DEFAULT_VISION = {
    "format": VISION_FORMAT,
    "enabled": False,
    "model": "",
    "max_side": 1024,
}
_VISION_KEYS = ("enabled", "model", "max_side")

# 窗口偏好（这台机器上），存在 ~/.seedbank/ui.json
DEFAULT_UI = {
    "always_on_top": False,
    "autostart": False,
}
_UI_KEYS = ("always_on_top", "autostart")

# Windows 开机自启：HKCU\...\Run 下的一个值
_AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_VALUE_NAME = "Seedbank"


# ---------------------------------------------------------------------------
# 读
# ---------------------------------------------------------------------------

def memory_settings(pack_dir) -> dict:
    """记忆卫生设置；老生命包没有这个文件时用默认值。"""
    saved = read_json(Path(pack_dir) / "mind" / "memory.json", None)
    cfg = dict(DEFAULT_MEMORY)
    if isinstance(saved, dict):
        if "strict" in saved:
            cfg["strict"] = bool(saved.get("strict"))
        for key in ("daily_max",):
            try:
                value = int(saved.get(key, cfg[key]))
            except (TypeError, ValueError):
                value = cfg[key]
            cfg[key] = max(1, min(50, value))
    return cfg


def vision_settings(pack_dir) -> dict:
    """视觉翻译设置；老生命包没有 mind/vision.json 时默认关闭。"""
    saved = read_json(Path(pack_dir) / "mind" / "vision.json", None)
    cfg = dict(DEFAULT_VISION)
    if isinstance(saved, dict):
        cfg["enabled"] = bool(saved.get("enabled", cfg["enabled"]))
        cfg["model"] = str(saved.get("model") or "").strip()
        try:
            cfg["max_side"] = max(256, min(2048, int(saved.get("max_side", cfg["max_side"]))))
        except (TypeError, ValueError):
            cfg["max_side"] = DEFAULT_VISION["max_side"]
    return cfg


def load_settings(pack_dir) -> dict:
    """给设置面板用的扁平字典：脑字段 + 记忆字段 + 感官字段 + 一句描述。"""
    brain = load_brain_config(pack_dir)
    memory = memory_settings(pack_dir)
    vision = vision_settings(pack_dir)
    from .semantic import configuration as semantic_configuration, DEFAULTS as SEMANTIC_DEFAULTS
    semantic = semantic_configuration(pack_dir)
    flat = {key: brain.get(key) for key in _BRAIN_KEYS}
    flat["api_key_source"] = brain.get("api_key_source") or "env"
    flat["api_key_ref"] = brain.get("api_key_ref") or ""
    for key, default in COMPATIBILITY_DEFAULTS.items():
        flat[key] = brain.get(key) or default
    flat.update({"strict": memory["strict"], "daily_max": memory["daily_max"]})
    flat.update({
        "vision_enabled": vision["enabled"],
        "vision_model": vision["model"],
        "vision_max_side": vision["max_side"],
    })
    flat["describe"] = describe_brain(brain)
    flat.update({"semantic_" + key: semantic[key] for key in SEMANTIC_DEFAULTS if key != "format"})
    return flat


# ---------------------------------------------------------------------------
# 写
# ---------------------------------------------------------------------------

def _clean_brain_patch(patch: dict) -> dict:
    out: dict = {}
    for key in _BRAIN_KEYS:
        if key not in patch:
            continue
        value = patch[key]
        if key == "adapter":
            value = str(value or "stub").strip()
            if value not in ADAPTERS:
                raise ValueError(t("不认识的脑适配器：{value}（可选：{join}）", value=value, join=' / '.join(ADAPTERS)))
        if key == "temperature":
            try:
                value = max(0.0, min(2.0, float(value)))
            except (TypeError, ValueError):
                value = 0.8
        if key == "input_budget":
            try:
                value = max(2048, min(1000000, int(value)))
            except (TypeError, ValueError):
                raise ValueError("input_budget 必须是 2048–1000000 的整数。") from None
        if key in ("codex_max_calls", "workbuddy_max_calls"):
            try:
                value = int(value)
                if not 1 <= value <= 3:
                    raise ValueError()
            except (TypeError, ValueError, OverflowError):
                raise ValueError(t("每轮活动的账号模型调用上限必须为 1–3。")) from None
        if key == "api_key_source":
            value = str(value or "env")
            if value not in ("env", "local"):
                raise ValueError(t("不认识的密钥保存方式。"))
        if key in ("response_format_mode", "temperature_mode"):
            value = str(value or COMPATIBILITY_DEFAULTS[key])
            allowed = ("json_object", "prompt") if key == "response_format_mode" else ("custom", "default")
            if value not in allowed:
                raise ValueError(t("不认识的模型兼容选项。"))
        if key in ("model", "base_url", "api_key_env", "api_key_ref", "fallback", "provider"):
            value = "" if value is None else str(value).strip()
        out[key] = value
    return out


def _clean_memory_patch(patch: dict) -> dict:
    out: dict = {}
    if "strict" in patch:
        out["strict"] = bool(patch["strict"])
    if "daily_max" in patch:
        try:
            out["daily_max"] = max(1, min(50, int(patch["daily_max"])))
        except (TypeError, ValueError):
            out["daily_max"] = DEFAULT_MEMORY["daily_max"]
    return out


def _clean_vision_patch(patch: dict) -> dict:
    out: dict = {}
    if "vision_enabled" in patch:
        out["enabled"] = bool(patch["vision_enabled"])
    if "vision_model" in patch:
        out["model"] = "" if patch["vision_model"] is None else str(patch["vision_model"]).strip()
    if "vision_max_side" in patch:
        try:
            out["max_side"] = max(256, min(2048, int(patch["vision_max_side"])))
        except (TypeError, ValueError):
            out["max_side"] = DEFAULT_VISION["max_side"]
    return out


@durable
def save_settings(pack_dir, patch: dict, *, api_key: str = "") -> dict:
    """保存设置，返回保存后的扁平设置。只写变化的那部分。"""
    brain_patch = _clean_brain_patch(patch or {})
    if api_key:
        from .credentials import store
        config = {**load_brain_config(pack_dir), **brain_patch}
        if config.get("api_key_source") != "local":
            raise ValueError(t("API Key 只能保存到本机密钥存储。"))
        brain_patch["api_key_ref"] = store(api_key, config)
    memory_patch = _clean_memory_patch(patch or {})
    vision_patch = _clean_vision_patch(patch or {})
    from .semantic import configure as semantic_configure, DEFAULTS as SEMANTIC_DEFAULTS
    semantic_patch = {key: patch["semantic_" + key] for key in SEMANTIC_DEFAULTS
                      if key != "format" and "semantic_" + key in (patch or {})}
    if semantic_patch:
        semantic_configure(pack_dir, semantic_patch)
    if brain_patch:
        save_brain_config(pack_dir, brain_patch)
    if memory_patch:
        current = memory_settings(pack_dir)
        current.update(memory_patch)
        current["format"] = MEMORY_FORMAT
        write_json_atomic(Path(pack_dir) / "mind" / "memory.json", current)
    if vision_patch:
        current = vision_settings(pack_dir)
        current.update(vision_patch)
        current["format"] = VISION_FORMAT
        write_json_atomic(Path(pack_dir) / "mind" / "vision.json", current)
    return load_settings(pack_dir)


# ---------------------------------------------------------------------------
# 窗口偏好（置顶 / 开机自启）
# ---------------------------------------------------------------------------

def ui_settings_path() -> Path:
    """窗口偏好存在用户目录：换生命包、删生命包，这些偏好都还在。"""
    return Path.home() / ".seedbank" / "ui.json"


def _read_ui_file() -> dict:
    """原始 ui.json；窗口的 geometry 等不认识的键也要保留，所以返回整份。"""
    saved = read_json(ui_settings_path(), None)
    return dict(saved) if isinstance(saved, dict) else {}


def load_ui_settings() -> dict:
    """窗口偏好；文件缺失或坏了就用默认值（跟默认合并，不抛异常）。"""
    cfg = dict(DEFAULT_UI)
    saved = _read_ui_file()
    for key in _UI_KEYS:
        if key in saved:
            cfg[key] = bool(saved[key])
    return cfg


def save_ui_settings(patch: dict) -> dict:
    """只认 always_on_top / autostart 两个键，其余原样保留，返回最新偏好。"""
    data = _read_ui_file()
    if isinstance(patch, dict):
        for key in _UI_KEYS:
            if key in patch:
                data[key] = bool(patch[key])
    write_json_atomic(ui_settings_path(), data)
    return load_ui_settings()


def desktop_executable() -> str:
    """Keep user-created startup entries on the stable launcher across updates."""
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False) and re.fullmatch(r"seedbank-runtime-[0-9a-f]{32}\.exe", executable.name):
        launcher = executable.with_name("seedbank.exe")
        if launcher.is_file():
            return str(launcher)
    return str(executable)


def autostart_command() -> list[str]:
    """开机时跑什么：`<pythonw> <repo>/tools/seed/seed.py window`。"""
    if getattr(sys, "frozen", False):
        return [desktop_executable()]
    executable = str(sys.executable or "python")
    if sys.platform.startswith("win") and executable.lower().endswith("python.exe"):
        # 用 pythonw 就不会开机时闪一个黑框。
        pythonw = Path(executable).with_name("pythonw.exe")
        if pythonw.exists():
            executable = str(pythonw)
    seed_py = Path(__file__).resolve().parent.parent / "seed.py"
    return [executable, str(seed_py), "window"]


def _command_line(command: list[str]) -> str:
    """把命令拼成注册表里能用的命令行（带空格的路径自动加引号）。"""
    return subprocess.list2cmdline([str(part) for part in command])


def _autostart_command_or_default(command: list[str] | None) -> list[str]:
    if command is None:
        return autostart_command()
    if isinstance(command, str):
        return [command]
    return [str(part) for part in command]


def set_autostart(enabled: bool, command: list[str] | None = None) -> dict:
    """开 / 关 Windows 开机自启，并把结果记进 ui.json。

    返回 {"ok": bool, "message": 给用户看的一句话}；失败不抛异常。
    command 参数只给单测用（不碰真注册表也能验命令拼接）。
    """
    enabled = bool(enabled)
    if not sys.platform.startswith("win"):
        return {"ok": False, "message": t("当前系统不支持开机自启")}
    cmdline = _command_line(_autostart_command_or_default(command))
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _AUTOSTART_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            if enabled:
                winreg.SetValueEx(key, _AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, cmdline)
            else:
                try:
                    winreg.DeleteValue(key, _AUTOSTART_VALUE_NAME)
                except FileNotFoundError:
                    pass  # 本来就没开，取消也算成功
        finally:
            winreg.CloseKey(key)
    except Exception as error:  # noqa: BLE001 —— 注册表问题要让用户看见，不是崩
        return {"ok": False, "message": t("设置失败：{error}", error=error)}
    try:
        save_ui_settings({"autostart": enabled})
    except Exception:  # noqa: BLE001 —— 注册表已经改了，不能因为 ui.json 写不了就回滚
        pass
    return {"ok": True, "message": t("已设置开机自启" if enabled else "已取消开机自启")}


def is_autostart_enabled() -> bool:
    """注册表里有没有开机自启；非 Windows 永远 False。"""
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _AUTOSTART_RUN_KEY,
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, _AUTOSTART_VALUE_NAME)
        finally:
            winreg.CloseKey(key)
        return True
    except (OSError, ImportError):
        return False


# ---------------------------------------------------------------------------
# 测试连接 / 打开文件夹
# ---------------------------------------------------------------------------

def _merged_brain_config(pack_dir, patch: dict | None) -> dict:
    cfg = load_brain_config(pack_dir)
    for key, value in (patch or {}).items():
        if key in _BRAIN_KEYS and value is not None:
            cfg[key] = "" if value == "" else value
    return cfg


def test_brain(pack_dir, patch: dict | None = None) -> tuple[bool, str]:
    """真的跟脑说一句话（不写生命包）。返回 (成功?, 给用户看的一句话)。

    只在用户点「测试连接」时调用；其他任何地方都不该自动联网。
    """
    try:
        cfg = _merged_brain_config(pack_dir, patch)
        from .providers import validate_connection
        validate_connection(cfg)
        adapter = str(cfg.get("adapter") or "stub")
        if adapter == "stub":
            return True, t("桩不需要联网：她会说话（离线、确定性）。")
        system = '连接检查。请只输出 JSON 对象：{"message":"好"}。'
        user = "你好吗？"
        if adapter == "openai-compatible":
            raw = openai_transport(cfg, system, user)
        elif adapter == "anthropic":
            raw = anthropic_transport(cfg, system, user)
        elif adapter == "codex":
            raw = codex_transport(cfg, system, user)
        elif adapter == "workbuddy":
            raw = workbuddy_transport(cfg, system, user)
            from .brain import parse_json_loose
            if parse_json_loose(raw).get("message") != "好":
                raise BrainConfigError(t("账号模型回复格式不符合要求，本轮未采用，也未自动重试。"))
        else:
            return False, t("不认识的适配器：{adapter}", adapter=adapter)
    except BrainConfigError as error:
        return False, str(error)
    except Exception as error:  # noqa: BLE001 —— 网络问题要给用户看，不是崩
        return False, t("连不上：{error}", error=error)
    text = " ".join(str(raw or "").split())[:40]
    return True, t("通了：{value}", value=text or '（空回复）')


def open_pack_folder(pack_dir) -> None:
    """在系统文件管理器里打开生命包（她的一生就是一个文件夹）。"""
    path = str(Path(pack_dir).resolve())
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return
        subprocess.Popen(["xdg-open", path])
    except Exception as error:  # noqa: BLE001 —— 打开失败不影响窗口
        raise OSError(t("打不开文件夹：{error}", error=error)) from error
