"""User-invoked five-page capture from the packaged UI, using an artificial life.

No desktop input or screen scraping. Never called by normal startup or packaging.
This produces documentation material, not a regression pass certificate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from datetime import datetime


def run(output, model=""):
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    model_path = Path(model).resolve() if model else None
    if model_path is not None and not model_path.is_file():
        raise ValueError("The explicitly selected model file does not exist.")
    report = {"completed": False, "purpose": "documentation captures, not regression acceptance",
              "scenario": "artificial life / offline stub / explicitly advanced one day",
              "started": datetime.now().astimezone().isoformat(), "captures": [],
              "runtime": Path(sys.executable).name,
              "runtime_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
              "model_selected": bool(model_path), "messages": []}

    def save_report():
        (destination / "capture.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def no_network(event, _args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("Showcase capture is offline")

    sys.addaudithook(no_network)
    save_report()
    # Fresh process only: isolate both home-based app preferences and Qt paths.
    with tempfile.TemporaryDirectory(prefix="seedbank-showcase-", ignore_cleanup_errors=True) as temporary:
        os.environ.update(HOME=temporary, USERPROFILE=temporary,
                          APPDATA=str(Path(temporary) / "Roaming"),
                          LOCALAPPDATA=str(Path(temporary) / "Local"),
                          SEEDBANK_LANG="zh_CN", QT_QPA_PLATFORM="windows")
        os.environ.pop("SEEDBANK_EGG", None)
        os.environ.pop("QT_QUICK_BACKEND", None)
        from PySide6.QtCore import QCoreApplication, QEvent, QObject, qInstallMessageHandler
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtQml import QQmlEngine, QQmlExpression
        from ..bridge import Bridge as CoreBridge
        from ..onboarding import find_egg
        from ..pack import hatch
        from .app import application, create_engine
        from .bridge import Bridge
        from .live2d_item import Live2DItem

        previous_handler = qInstallMessageHandler(
            lambda kind, context, message: report["messages"].append(str(message)))
        app = application()
        app.setQuitOnLastWindowClosed(False)
        bridge = engine = root = None
        try:
            pack = Path(temporary) / "Showcase.life"
            hatch(pack, find_egg(), "澄 · 界面演示")
            core = CoreBridge(pack, brain_override="stub")
            for request in (
                {"op": "message", "text": "这是人工界面展示。今天聊起北街书店，想做一张雨天出门前的便签。", "request_id": "showcase-message-1"},
                {"op": "message", "text": "便签想写得短一点：带伞、钥匙，出门前看一眼天气。", "request_id": "showcase-message-2"},
                {"op": "day", "days": 1},
                {"op": "message", "text": "这份档案只用于展示日记、记忆和生活页面，没有连接真实模型。", "request_id": "showcase-message-3"},
            ):
                result = core.handle(request)
                if result.get("ok") is not True:
                    raise RuntimeError(result.get("error", "Could not prepare artificial scenario"))
            del core
            bridge = Bridge(brain_override="stub", timers=False)
            if model_path:
                bridge.preference("live2d_model", str(model_path))

            def settle(seconds):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    app.processEvents()
                    time.sleep(.003)

            def wait_for(condition, label, seconds=30):
                until = time.monotonic() + seconds
                while not condition() and time.monotonic() < until:
                    settle(.02)
                if not condition():
                    raise RuntimeError("Capture timed out: " + label)

            bridge.openPack(str(pack))
            wait_for(lambda: bridge.ready and not bridge._pending, "open artificial life")
            engine = create_engine(bridge, test_mode=True)
            root = engine.rootObjects()[0]
            expression = QQmlExpression(QQmlEngine.contextForObject(root), root,
                "flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput")
            expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            root.setWidth(1280)
            root.setHeight(840)
            root.setOpacity(0)
            if model_path:
                engine.rootContext().setContextProperty("testMode", False)
            root.show()
            if model_path:
                wait_for(lambda: root.findChild(Live2DItem, "live2dView") is not None, "model item")
                avatar = root.findChild(Live2DItem, "live2dView")
                wait_for(lambda: avatar.status in ("ready", "error"), "model load")
                if avatar.status != "ready":
                    raise RuntimeError(avatar.detail)
            settle(1)
            for index, name in enumerate(("companion", "diary", "memories", "life", "settings")):
                root.setProperty("page", index)
                if index == 1:
                    # Select the first, completed artificial day, not an empty date.
                    if not bridge.selectDay(1):
                        raise RuntimeError("Could not select the demonstration diary")
                    wait_for(lambda: bridge._diary_status in ("ready", "empty", "error"), "diary text")
                    if bridge._diary_status != "ready":
                        raise RuntimeError("The demonstration diary has no readable body")
                elif index == 3:
                    bridge.lifeSection("growth")
                wait_for(lambda: not bridge._pending, name)
                settle(.6)
                # Async item capture avoids holding the GIL across a native render.
                capture = root.contentItem().grabToImage()
                if capture is None:
                    raise RuntimeError("Could not request " + name + " capture")
                ready = []
                capture.ready.connect(lambda: ready.append(True))
                wait_for(lambda: bool(ready), name + " pixels")
                scene = capture.image()
                if scene.isNull():
                    raise RuntimeError("No scene pixels: " + name)
                # contentItem excludes QQuickWindow's clear color. Reproduce that
                # actual color in an opaque image so GitHub themes cannot alter it.
                picture = QImage(scene.size(), QImage.Format.Format_RGB32)
                picture.fill(root.color())
                painter = QPainter(picture)
                painter.drawImage(0, 0, scene)
                painter.end()
                path = destination / (name + ".png")
                if not picture.save(str(path)):
                    raise RuntimeError("Could not write " + name)
                report["captures"].append({"page": name, "file": path.name,
                    "width": picture.width(), "height": picture.height(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "background": root.color().name(), "captured": datetime.now().astimezone().isoformat()})
                save_report()
            report["completed"] = True
            return 0
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            if bridge is not None:
                bridge.shutdown()
            if root is not None:
                root.setProperty("mayClose", True)
                root.close()
            if engine is not None:
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qInstallMessageHandler(previous_handler)
            report["finished"] = datetime.now().astimezone().isoformat()
            save_report()
