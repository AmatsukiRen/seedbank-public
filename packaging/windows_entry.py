#!/usr/bin/env python3
"""Seedbank Windows 一键包入口（被打包成 seedbank.exe 的那个文件）。

打包之后，同一个 exe 有两种活法：

* **双击（没有参数）**：打开 Qt Quick 桌面——
  1. 读 `%USERPROFILE%\\.seedbank\\ui.json` 里的 `last_pack` 或默认生命包；
  2. 没有有效生命包时显示新建 / 打开欢迎页；
  3. 记住选定目录，进入陪伴、日记、记忆、生活与设置。

* **带参数**：原样交给 `seedbank.cli.main`，例如

      seedbank.exe --version
      seedbank.exe check D:\\fish\\小蓝.life
      seedbank.exe window D:\\fish\\小蓝.life

窗口是 `console=False` 的单文件 exe：双击时不该闪黑框。但这样一来，从终端里跑
`seedbank.exe --version` 时 PyInstaller 会把 stdout/stderr 置空，所以下面有一段
`_recover_stdio()`，把父进程的控制台/管道接回来（GUI 程序也能在终端里说话）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

# 和 tools/seed/seedbank/window.py 里的 WINDOW_TITLE 保持一致；只在找窗口时用。
_FALLBACK_WINDOW_TITLE = "她住在这里"

_IS_WINDOWS = sys.platform.startswith("win")

# 命名互斥体的句柄要活到进程退出，不能是局部变量（否则 GC 一收就释放了）。
_ROOM_MUTEXES: list = []

_DEVNULL_NAMES = {"", "nul", "nul:", os.devnull.lower()}


# ---------------------------------------------------------------------------
# 导入路径
# ---------------------------------------------------------------------------

def _bootstrap_import_path() -> None:
    """没冻结时（源码里直接跑）把 tools/seed 放进 sys.path。

    PyInstaller 构建时由 spec 的 pathex 负责；这里只是让
    `python packaging/windows_entry.py --version` 在仓库里也能跑。
    """
    if getattr(sys, "frozen", False):
        return
    tools = Path(__file__).resolve().parents[1] / "tools" / "seed"
    if tools.is_dir() and str(tools) not in sys.path:
        sys.path.insert(0, str(tools))


# ---------------------------------------------------------------------------
# stdout / stderr：windowed exe 也要能在终端里输出
# ---------------------------------------------------------------------------

def _looks_like_devnull(stream) -> bool:
    """PyInstaller 的 windowed 模式会把流换成 None 或一个假 writer。"""
    if stream is None:
        return True
    name = str(getattr(stream, "name", "") or "").lower()
    if name in _DEVNULL_NAMES:
        return True
    return type(stream).__name__ in ("NullWriter", "NullReader")


def _stream_ready(stream) -> bool:
    if _looks_like_devnull(stream):
        return False
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return False
    return isinstance(fd, int) and fd >= 0


def _console_writer(handle):
    """把 print 直接写进 Windows 控制台（WriteConsoleW），跟代码页无关。

    `cli._ensure_utf8_io()` 之后会调用 `stream.reconfigure(encoding="utf-8")`，
    这里把 reconfigure 做成空操作——WriteConsoleW 本来就不吃编码，中文不会乱。
    """
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WriteConsoleW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint),
        ctypes.c_void_p,
    )
    kernel32.WriteConsoleW.restype = ctypes.c_int

    class _ConsoleWriter:
        encoding = "utf-8"
        errors = "replace"
        name = "<console>"

        def write(self, text):
            text = text if isinstance(text, str) else str(text)
            if not text:
                return 0
            units = len(text.encode("utf-16-le", "replace")) // 2
            written = ctypes.c_uint(0)
            ok = kernel32.WriteConsoleW(
                ctypes.c_void_p(handle), text, units, ctypes.byref(written), None
            )
            return int(written.value) if ok else 0

        def flush(self):
            return None

        def writable(self):
            return True

        def isatty(self):
            # 让 tqdm / colorama 之类把它当终端（虽然这个包一个也没用）。
            return True

        def fileno(self):
            return -1

        def reconfigure(self, **kwargs):
            # 见上面的注释：不换编码，也不炸。
            return None

    return _ConsoleWriter()


def _is_console_handle(kernel32, handle) -> bool:
    import ctypes

    mode = ctypes.c_uint(0)
    return bool(kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))


def _attach_parent_console() -> None:
    """把父进程的控制台（或它给的管道/文件句柄）接回 sys.stdout / sys.stderr。"""
    try:
        import ctypes
        import io
        import msvcrt
    except ImportError:  # 不是 Windows / 精简解释器
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.argtypes = (ctypes.c_uint,)
        kernel32.GetStdHandle.restype = ctypes.c_void_p
    except OSError:
        return

    # ATTACH_PARENT_PROCESS = -1。父进程没有控制台时会失败，这是正常的。
    try:
        kernel32.AttachConsole(ctypes.c_uint(-1).value)
    except Exception:
        pass

    invalid = ctypes.c_void_p(-1).value
    for std_id, name in ((-10, "stdin"), (-11, "stdout"), (-12, "stderr")):
        if _stream_ready(getattr(sys, name, None)):
            continue
        handle = kernel32.GetStdHandle(std_id)
        if not handle or handle == invalid:
            continue
        try:
            if _is_console_handle(kernel32, handle):
                stream = open("CONIN$", "r", encoding="utf-8") if name == "stdin" else _console_writer(handle)
            else:
                # 重定向到管道/文件：直接写字节，保证 UTF-8 原样落盘。
                fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY if name == "stdin" else os.O_WRONLY)
                stream = io.open(
                    fd, "r" if name == "stdin" else "w", encoding="utf-8", errors="replace", closefd=True
                )
        except (OSError, ValueError):
            continue
        setattr(sys, name, stream)


def _recover_stdio() -> None:
    """保证 sys.stdin/stdout/stderr 永远不是 None，print 不会把 exe 弄崩。"""
    if _IS_WINDOWS and getattr(sys, "frozen", False):
        if not _stream_ready(sys.stdout) or not _stream_ready(sys.stderr):
            _attach_parent_console()
    for name, mode in (("stdout", "w"), ("stderr", "w"), ("stdin", "r")):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(os.devnull, mode, encoding="utf-8"))
            except OSError:  # pragma: no cover - 极端环境
                pass
        # Windowed executables may retain redirected streams with a system
        # codepage instead of setting them to None. Worker protocols require
        # UTF-8 independently of that locale or PYTHONUTF8 environment support.
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="strict")
            except (OSError, ValueError):
                pass


# ---------------------------------------------------------------------------
# ui.json：记住上一条鱼（只加一个 last_pack 键，其余原样保留）
# ---------------------------------------------------------------------------

def _ui_settings_path() -> Path:
    """和 seedbank.settings.ui_settings_path() 同一个文件：~/.seedbank/ui.json。"""
    try:
        from seedbank.settings import ui_settings_path

        return ui_settings_path()
    except Exception:
        return Path.home() / ".seedbank" / "ui.json"


def _read_ui_file() -> dict:
    try:
        data = json.loads(_ui_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return dict(data) if isinstance(data, dict) else {}


def _write_ui_file(data: dict) -> None:
    """原子写：窗口的 geometry、置顶、自启这些键都还在，格式也跟窗口写的一致。"""
    path = _ui_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from seedbank.util import write_json_atomic

        write_json_atomic(path, data)
        return
    except Exception:
        pass
    # settings/util 都不可用时的兜底（比如开发时没把 tools/seed 放进 sys.path）。
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _remember_pack(pack: Path) -> None:
    data = _read_ui_file()
    data["last_pack"] = str(pack)
    try:
        _write_ui_file(data)
    except OSError:
        # 记不住也要让她开门；下次再问一遍就是了。
        pass


# ---------------------------------------------------------------------------
# 找一条鱼
# ---------------------------------------------------------------------------

def _resolve_pack(value) -> Path:
    return Path(str(value)).expanduser().resolve()


def _is_life_pack(path) -> bool:
    try:
        return (Path(path).expanduser() / "birth.json").is_file()
    except OSError:
        return False


def _remembered_hint() -> Path | None:
    """ui.json 里记着的路径（哪怕已经失效），用来当选择框的起始目录。"""
    value = _read_ui_file().get("last_pack")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _resolve_pack(value)
    except (OSError, ValueError, RuntimeError):
        return None


def _remembered_pack() -> Path | None:
    hint = _remembered_hint()
    return hint if hint is not None and _is_life_pack(hint) else None


def _initial_dir(hint: Path | None) -> str:
    for candidate in (hint, Path.home() / "fish", Path.home()):
        if candidate is not None and candidate.is_dir():
            return str(candidate)
    return str(Path.home())


def _pick_pack(hint: Path | None) -> Path | None:
    """弹文件夹选择框；取消返回 None。选错不是生命包就重来。"""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as error:  # pragma: no cover - 没有 tkinter 的环境
        _message_box(f"这个包打不开文件夹选择框（tkinter 不可用）：{error}")
        return None

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        initial = _initial_dir(hint)
        while True:
            chosen = filedialog.askdirectory(
                parent=root,
                title="选一个生命包（.life 文件夹）",
                initialdir=initial,
                mustexist=True,
            )
            if not chosen:
                return None
            candidate = _resolve_pack(chosen)
            if _is_life_pack(candidate):
                return candidate
            messagebox.showerror(
                "这不是一个生命包",
                "这个文件夹里没有 birth.json。\n\n"
                "请选一个 .life 文件夹（她的一生就是那个文件夹）。",
                parent=root,
            )
            initial = str(candidate if candidate.is_dir() else Path(chosen).parent)
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 单实例：同一个生命包只开一扇窗
# ---------------------------------------------------------------------------

def _acquire_room_lock(pack: Path) -> bool:
    """拿到这把锁返回 True；同一条鱼已经开着返回 False（并把旧窗口叫到前面）。"""
    if not _IS_WINDOWS:
        return True
    try:
        import ctypes
        import hashlib
    except ImportError:
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_wchar_p,
        )
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_int
        digest = hashlib.sha256(str(pack).casefold().encode("utf-8")).hexdigest()[:16]
        handle = kernel32.CreateMutexW(None, False, f"Local\\SeedbankRoom-{digest}")
        if not handle:
            return True
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if already:
            kernel32.CloseHandle(handle)
            return False
        _ROOM_MUTEXES.append(handle)  # 活到进程退出
        return True
    except Exception:
        return True


def _window_title() -> str:
    try:
        from seedbank.window import WINDOW_TITLE

        return str(WINDOW_TITLE)
    except Exception:
        return _FALLBACK_WINDOW_TITLE


def _focus_existing_window() -> bool:
    """把已经开着的那扇窗叫到前面；找不到就返回 False。"""
    if not _IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        target = _window_title()
        found: list = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _collect(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if target in buffer.value:
                    found.append(hwnd)
            return True

        user32.EnumWindows(_collect, 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 对话框 / 崩溃日志
# ---------------------------------------------------------------------------

def _message_box(text: str, *, error: bool = True, title: str = "Seedbank") -> None:
    """双击启动时没有终端：错误必须弹出来。"""
    if _IS_WINDOWS:
        try:
            import ctypes

            flags = (0x10 if error else 0x40) | 0x40000 | 0x10000  # ICON | TOPMOST | SETFOREGROUND
            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), flags)
            return
        except Exception:
            pass
    try:
        print(f"[seedbank] {text}", file=sys.stderr)
    except Exception:
        pass


def _write_crash_log(detail: str) -> str:
    path = Path(tempfile.gettempdir()) / "seedbank-error.log"
    try:
        path.write_text(detail, encoding="utf-8")
        return str(path)
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# 冻结后的小补丁
# ---------------------------------------------------------------------------

def _patch_frozen_settings() -> None:
    """冻结后「开机自启」要注册成 `seedbank.exe`（无参数 = 回到上次的房间）。

    源码里设置模块拼的是 `python <repo>/tools/seed/seed.py window`；冻结以后
    seed.py 根本不存在，注册进去只会在开机时闪一下就没了。这里只换命令，
    不碰设置模块的其它逻辑（注册表读写、ui.json 都还是原来那套）。
    """
    if not getattr(sys, "frozen", False) or not _IS_WINDOWS:
        return
    try:
        from seedbank import settings as seed_settings

        def autostart_command() -> list[str]:
            return [seed_settings.desktop_executable()]

        seed_settings.autostart_command = autostart_command
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 两种入口
# ---------------------------------------------------------------------------

def _run_first_run(hint: Path | None) -> Path | None:
    """第一次启动：先走「初次见面」向导；向导不可用再退回选文件夹。"""
    try:
        from seedbank.onboarding import resolve_pack as configured_pack
    except Exception:
        configured_pack = None
    if configured_pack is not None:
        configured = configured_pack()
        if configured is not None:
            return configured

    try:
        import tkinter as tk

        from seedbank.window import SetupWizard
    except Exception:
        return _pick_pack(hint)

    result: dict = {}
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        def on_done(pack) -> None:
            result["pack"] = Path(pack)

        def on_cancel() -> None:
            result["cancel"] = True

        wizard = SetupWizard(root, on_done, on_cancel)
        root.wait_window(wizard)
    except Exception:  # noqa: BLE001 - 向导开不了就退回选文件夹
        return _pick_pack(hint)
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    if result.get("cancel"):
        return None
    return result.get("pack")


def _run_gui() -> int:
    """双击流程：上次的房间 → 没有就走初次见面 → 记住 → 开门。"""
    from seedbank import startup_log

    try:
        startup_log.mark("gui.resolve_previous.begin")
        hint = _remembered_hint()
        pack = hint if hint is not None and _is_life_pack(hint) else None
        startup_log.mark("gui.imports.begin")
        from seedbank.onboarding import resolve_pack
        from seedbank.quick.app import run

        startup_log.mark("gui.imports.ready")
        pack = pack or resolve_pack()
        if pack is not None and not _acquire_room_lock(pack):
            startup_log.mark("gui.existing_instance")
            if not _focus_existing_window():
                _message_box("她的房间已经开着了。", error=False)
            return 0

        def acquire(target):
            if pack is not None and Path(target).resolve() == Path(pack).resolve():
                return True
            locked = _acquire_room_lock(target)
            if not locked:
                _focus_existing_window()
            return locked

        startup_log.mark("gui.run.begin")
        result = int(run(pack, acquire_lock=acquire) or 0)
        startup_log.mark(f"gui.run.returned code={result}")
        return result
    except Exception as error:  # noqa: BLE001 - 双击时没有终端，必须让用户看见
        startup_log.exception(error)
        detail = traceback.format_exc()
        log = _write_crash_log(detail)
        message = f"打不开她的房间：{error}"
        if log:
            message += f"\n\n详细日志：{log}"
        if startup_log.path():
            message += f"\n启动日志：{startup_log.path()}"
        _message_box(message)
        return 1


def main(argv: list[str] | None = None) -> int:
    _bootstrap_import_path()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args == ["--safe-graphics"]:
        from seedbank import startup_log

        startup_log.enable()
        startup_log.mark("entry.main")
    _recover_stdio()
    _patch_frozen_settings()

    if args == ["--channel-worker"]:
        from seedbank.channel_worker import main as channel_main
        return channel_main()

    if len(args) == 2 and args[0] == "--plugin-worker":
        from seedbank.plugin_worker import main as plugin_main
        return plugin_main(args[1:])

    if args == ["--safe-graphics"]:
        # User-selected recovery entry. Set before importing/creating Qt; it
        # affects this process only and never edits UI preferences or life data.
        os.environ["QT_QUICK_BACKEND"] = "software"
        return _run_gui()

    if len(args) in (2, 3) and args[0] == "--capture-showcase":
        try:
            from seedbank.quick.showcase import run
            return run(args[1], args[2] if len(args) == 3 else "")
        except Exception:
            traceback.print_exc()
            return 1

    if len(args) == 2 and args[0] in ("--ui-self-test", "--ui-self-test-native"):
        try:
            from seedbank.quick.selfcheck import run
            return run(args[1], native=args[0] == "--ui-self-test-native")
        except Exception:
            traceback.print_exc()
            return 1

    if len(args) == 3 and args[0] == "--avatar-self-test":
        try:
            from seedbank.quick.avatar_check import run
            return run(args[1], args[2])
        except Exception:
            traceback.print_exc()
            return 1

    if args:
        # 带参数：就是命令行（--version / check / window / hatch …）。
        from seedbank.cli import main as cli_main

        return int(cli_main(args) or 0)
    return _run_gui()


if __name__ == "__main__":
    sys.exit(main())
