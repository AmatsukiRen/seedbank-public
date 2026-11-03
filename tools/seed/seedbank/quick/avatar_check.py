"""Explicit native-render acceptance entry; never runs during normal startup.

Uses a temporary offline life and settings, a transparent noninteractive window,
and read-only local model assets. Captures only this process's rendered scene.
Run in a fresh process so graphics selection and network isolation are reliable.
"""
from __future__ import annotations

from contextlib import contextmanager
import gc
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time


@contextmanager
def isolated_profile(output, report):
    # Windows graphics drivers may hold their shader cache until process exit.
    # Best-effort cleanup must not turn a completed rendering check into failure;
    # retain its location in the report instead of touching any external process.
    directory = tempfile.TemporaryDirectory(prefix="seedbank-native-avatar-", ignore_cleanup_errors=True)
    report["temporary_directory"] = directory.name
    try:
        with directory as temporary:
            yield temporary
    finally:
        report["temporary_cleanup"] = "retained_locked_files" if Path(directory.name).exists() else "removed"
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def asset_hashes(model):
    from ..live2d_model import descriptor
    document, _registry = descriptor(model)
    paths = {Path(model).resolve()}

    def collect(value):
        if isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, str) and Path(value).is_absolute() and Path(value).is_file():
            paths.add(Path(value))

    collect(json.loads(document)["FileReferences"])
    result = {}
    for path in sorted(paths):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        result[str(path)] = digest.hexdigest()
    return result


def run(output, model, *, cycle_seconds=60):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Use a new report path; existing reports are preserved.")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "scope": "native Live2D / isolated offline life; no desktop input",
              "model": str(Path(model).resolve()), "phases": [], "captures": [], "cycles": []}

    def record(phase, **fields):
        report["phases"].append({"phase": phase, "elapsed": round(time.monotonic() - started, 3), **fields})
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(phase, flush=True)

    def block_network(event, _args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("Native avatar check must stay offline")

    started = time.monotonic()
    sys.addaudithook(block_network)
    before = asset_hashes(model)
    record("assets.read", files=len(before))
    with isolated_profile(output, report) as temporary:
        os.environ.update(HOME=temporary, USERPROFILE=temporary,
                          APPDATA=str(Path(temporary) / "Roaming"), LOCALAPPDATA=str(Path(temporary) / "Local"),
                          SEEDBANK_LANG="zh_CN", QT_QPA_PLATFORM="windows", QT_QPA_FONTDIR=temporary)
        os.environ.pop("QT_QUICK_BACKEND", None)
        from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, qInstallMessageHandler
        from PySide6.QtGui import QFontDatabase, QImage
        from PySide6.QtQml import QQmlEngine, QQmlExpression
        from ..onboarding import find_egg
        from ..pack import hatch
        from .app import application, create_engine
        from .bridge import Bridge
        from .live2d_item import Live2DItem
        from .window_geometry import WindowPlacement

        messages = []
        diagnostic = output.with_suffix(".native.log").open("w", encoding="utf-8", buffering=1)
        faulthandler.enable(file=diagnostic)

        def qt_message(kind, _context, message):
            messages.append(message)
            diagnostic.write(f"{kind}: {message}\n")

        old_handler = qInstallMessageHandler(qt_message)
        app = application()
        app.setQuitOnLastWindowClosed(False)
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
        pack = Path(temporary) / "Native-check.life"
        hatch(pack, find_egg(), "原生渲染隔离测试")
        bridge = engine = root = avatar = None

        def settle(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                # Dump only if an event dispatch is stuck, not during an
                # otherwise healthy minute-long animation observation.
                faulthandler.dump_traceback_later(25, file=diagnostic)
                app.processEvents()
                faulthandler.cancel_dump_traceback_later()
                if avatar is not None and avatar.status == "error":
                    raise RuntimeError(avatar.detail)
                time.sleep(0.002)

        def wait_for(condition, label, seconds=15):
            until = time.monotonic() + seconds
            while not condition() and time.monotonic() < until:
                settle(0.01)
            if not condition():
                raise RuntimeError("Timed out: " + label)

        def pixels(label, save=True):
            # Synchronous QQuickWindow.grabWindow can wait for a render thread
            # whose Python renderer needs the caller's GIL. Let Qt finish its
            # asynchronous item grab while the main thread yields normally.
            capture = root.contentItem().grabToImage()
            if capture is None:
                raise RuntimeError("Could not request native scene capture")
            ready = []
            capture.ready.connect(lambda: ready.append(True))
            wait_for(lambda: bool(ready), "asynchronous native capture")
            picture = capture.image()
            if picture.isNull():
                raise RuntimeError("No native window pixels")
            if save:
                path = output.parent / (output.stem + "-" + label + ".png")
                if not picture.save(str(path)):
                    raise RuntimeError("Could not save native capture")
                report["captures"].append(str(path))
            corner = avatar.mapToScene(QPointF(0, 0))
            scale = picture.width() / root.width()
            region = picture.copy(round(corner.x() * scale), round(corner.y() * scale),
                                  round(avatar.width() * scale), round(avatar.height() * scale))
            region = region.convertToFormat(QImage.Format.Format_RGBA8888)
            return hashlib.sha256(region.constBits()).hexdigest()

        def close_cycle():
            nonlocal bridge, engine, root, avatar
            if bridge is not None:
                bridge.shutdown()
            if engine is not None:
                avatar = None
                root.setProperty("mayClose", True)
                root.close()
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            bridge = engine = root = None
            gc.collect()

        try:
            for cycle in range(2):
                record("cycle.open.begin", cycle=cycle)
                bridge = Bridge(brain_override="stub", timers=False)
                bridge.preference("live2d_model", str(Path(model).resolve()))
                bridge.openPack(str(pack))
                wait_for(lambda: bridge.ready and not bridge._pending, "temporary life open")
                record("cycle.engine.begin", cycle=cycle)
                engine = create_engine(bridge, test_mode=True)
                root = engine.rootObjects()[0]
                # Retain the same placement cycle as normal startup, without
                # placing a visible window or changing the user's saved geometry.
                root._placement = WindowPlacement(root, [])
                expression = QQmlExpression(QQmlEngine.contextForObject(root), root,
                    "flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput")
                expression.evaluate()
                if expression.hasError():
                    raise RuntimeError(expression.error().toString())
                root.setOpacity(0)
                engine.rootContext().setContextProperty("testMode", False)
                root.show()
                wait_for(lambda: root.findChild(Live2DItem, "live2dView") is not None, "avatar item")
                avatar = root.findChild(Live2DItem, "live2dView")
                wait_for(lambda: avatar.status == "ready", "first native model frame")
                stamps = []
                root.frameSwapped.connect(lambda: stamps.append(time.monotonic()))
                record("cycle.ready", cycle=cycle, graphics=str(root.rendererInterface().graphicsApi()))
                cycle_started = time.monotonic()
                settle(2)
                idle = pixels(f"{cycle}-idle")
                bridge.petAction.emit("wave")
                settle(2)
                wave = pixels(f"{cycle}-wave")
                if idle == wave:
                    raise RuntimeError("Native avatar pixels did not change during motion")
                settle(10)
                pixels(f"{cycle}-returned")
                record("motion.returned", cycle=cycle)
                for motion in ("think", "happy", "idle"):
                    bridge.petAction.emit(motion)
                    settle(2)
                root.setWidth(860)
                root.setHeight(640)
                settle(2)
                pixels(f"{cycle}-small")
                root.setWidth(1280)
                root.setHeight(840)
                gc.collect()
                bridge.reloadAvatar()
                wait_for(lambda: avatar.status == "ready", "explicit model reload")
                settle(2)
                pixels(f"{cycle}-reloaded")
                record("reload.ready", cycle=cycle)
                bridge.changeLifecycle("pause", "隔离检查：明确暂停。", bridge.lifecycle["revision"])
                wait_for(lambda: not bridge._pending, "pause")
                if bridge.lifeActive or avatar.animating or avatar._timer.isActive():
                    raise RuntimeError("Dormancy did not stop native animation scheduling")
                settle(1)
                paused = pixels(f"{cycle}-paused")
                settle(2)
                if pixels("paused-again", save=False) != paused:
                    raise RuntimeError("Native avatar changed while dormant")
                bridge.changeLifecycle("resume", "隔离检查：明确恢复。", bridge.lifecycle["revision"])
                wait_for(lambda: not bridge._pending, "resume")
                if not bridge.lifeActive or not avatar.animating or not avatar._timer.isActive():
                    raise RuntimeError("Explicit resume did not restart native animation")
                settle(2)
                if pixels(f"{cycle}-resumed") == paused:
                    raise RuntimeError("Native avatar pixels did not resume")
                record("dormancy.resume", cycle=cycle)
                while time.monotonic() - cycle_started < cycle_seconds:
                    settle(1)
                    gc.collect()
                deltas = [b - a for a, b in zip(stamps, stamps[1:]) if 0 < b - a < .1]
                report["cycles"].append({"seconds": round(time.monotonic() - cycle_started, 3),
                    "frame_swaps": len(stamps), "sampled_interval_median_ms": round(statistics.median(deltas) * 1000, 3) if deltas else None,
                    "note": "Transparent test window; excludes pauses/long gaps, not interactive FPS acceptance"})
                close_cycle()
                record("cycle.closed", cycle=cycle)
            after = asset_hashes(model)
            if before != after:
                raise RuntimeError("Original model assets changed during check")
            failures = [message for message in messages if any(word in message for word in
                ("Error", "Cannot", "Unable", "failed", "Binding loop", "recursive rearrange", "not found", "is not defined"))]
            if failures:
                raise RuntimeError("\n".join(failures))
            report.update(ok=True, original_assets_unchanged=True, asset_files=len(before), qt_messages=messages)
            record("complete")
            return 0
        except Exception as error:
            report["error"] = str(error)
            record("failed")
            raise
        finally:
            close_cycle()
            qInstallMessageHandler(old_handler)
            faulthandler.cancel_dump_traceback_later()
            faulthandler.disable()
            diagnostic.close()


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1], sys.argv[2]))
