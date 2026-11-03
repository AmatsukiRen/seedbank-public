"""Opt-in local startup diagnostics; no settings, pack data or exception values.

The frozen GUI enables this before PyInstaller's dependency runtime hooks.
Keep the fault-handler file open for the lifetime of the process. Importing this
module alone does not create files or install handlers.
"""
from __future__ import annotations

import atexit
import faulthandler
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback

_stream = None
_path = None
_lock = threading.RLock()
_MAX_BYTES = 256 * 1024


def mark(stage: str) -> None:
    """Call with fixed stage labels only, never user content or model paths."""
    if _stream is None:
        return
    try:
        with _lock:
            if _stream.tell() < _MAX_BYTES:
                _stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {stage}\n")
                _stream.flush()
    except (OSError, ValueError):
        pass  # Diagnostics must not prevent startup or shutdown.


def exception(error: BaseException) -> None:
    # Traceback frames identify code locations; omit messages, locals and source
    # expressions, any of which could contain life data or service credentials.
    mark("exception " + type(error).__name__)
    for frame in traceback.extract_tb(error.__traceback__):
        mark(f"  {frame.filename}:{frame.lineno} in {frame.name}")


def path() -> str:
    return str(_path) if _path is not None else ""


def enable() -> str:
    """Best effort, idempotent; a separate file per launch preserves failures."""
    global _stream, _path
    if _stream is not None:
        return path()
    filename = f"seedbank-startup-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.log"
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent)
    try:
        candidates.append(Path(tempfile.gettempdir()))
    except OSError:
        pass
    for directory in candidates:
        try:
            candidate = directory / filename
            _stream = candidate.open("a", encoding="utf-8", buffering=1)
            _path = candidate
            break
        except OSError:
            continue
    if _stream is None:
        return ""
    mark("startup.logging.ready")
    try:
        faulthandler.enable(file=_stream, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        mark("startup.native_trace.unavailable")
    previous = sys.excepthook

    def unhandled(kind, value, tb):
        exception(value)
        previous(kind, value, tb)

    sys.excepthook = unhandled
    atexit.register(mark, "process.python_shutdown")
    return path()
