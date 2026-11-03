from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def run(output, *, native=False):
    def no_network(event, _args):
        if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
            raise RuntimeError("Packaged UI self-check is offline")
    sys.addaudithook(no_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-qt-package-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory, SEEDBANK_LANG="zh_CN", QT_QPA_PLATFORM="windows" if native else "offscreen", QT_QPA_FONTDIR=directory,
                          APPDATA=str(Path(directory) / "Roaming"), LOCALAPPDATA=str(Path(directory) / "Local"))
        os.environ.pop("SEEDBANK_EGG", None)
        if not native:
            os.environ["QT_QUICK_BACKEND"] = "software"
        from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, qInstallMessageHandler
        from PySide6.QtGui import QFontDatabase, QImage
        from PySide6.QtQml import QQmlEngine, QQmlExpression
        from ..onboarding import find_egg
        from ..pack import hatch
        from .app import application, create_engine
        from .bridge import Bridge

        messages = []
        old_handler = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
        app = application()
        app.setQuitOnLastWindowClosed(False)
        for filename in ("msyh.ttc", "segoeui.ttf", "malgun.ttf"):
            font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
        pack = Path(directory) / "Package.life"
        hatch(pack, find_egg(), "Package test")
        bridge = Bridge(brain_override="stub", timers=False)
        engine = None

        def settle(milliseconds=40):
            deadline = time.monotonic() + milliseconds / 1000
            while time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.002)

        try:
            engine = create_engine(bridge, test_mode=True)
            root = engine.rootObjects()[0]
            if native:
                # Replace the QML binding so later preference changes cannot re-enable window input.
                QQmlExpression(QQmlEngine.contextForObject(root), root,
                               "flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput").evaluate()
                root.setOpacity(0)
            root.show()
            settle(150)
            if root.grabWindow().isNull() or root.findChild(QObject, "pages").property("currentIndex") != 5:
                raise RuntimeError("The welcome page did not render")
            bridge.openPack(str(pack))
            deadline = time.monotonic() + 10
            while not bridge.ready and time.monotonic() < deadline:
                settle(20)
            if not bridge.ready:
                raise RuntimeError(bridge.notice)
            settle(150)
            rendered = []
            for page in range(5):
                root.setProperty("page", page)
                settle()
                picture = root.grabWindow()
                if picture.isNull():
                    raise RuntimeError(f"No pixels for page {page}")
                rendered.append([picture.width(), picture.height()])
            settings = root.findChild(QObject, "settingsPage")
            for section in range(6):
                settings.setProperty("section", section)
                settle()
            for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
                bridge.preference("language", language)
                settle()
                if language != "zh_CN" and bridge.translate("设置") == "设置":
                    raise RuntimeError(f"Missing translations for {language}")
            bridge.preference("language", "zh_CN")
            root.setProperty("page", 0)
            settle()
            avatar = root.findChild(QObject, "live2dStage")
            if avatar is None or not avatar.isVisible() or avatar.width() <= 0 or avatar.height() <= 0:
                raise RuntimeError("The avatar stage has no layout space")
            if avatar.property("loadStatus") != "disabled":
                raise RuntimeError("The isolated check must not load a local model")
            bridge.setDraft("你好，这是隔离包测试。")
            bridge.send()
            deadline = time.monotonic() + 10
            while bridge._pending and time.monotonic() < deadline:
                settle(20)
            root.setProperty("page", 1)
            diary_sizes = []
            for width, height in ((860, 640), (1180, 820), (1520, 780)):
                root.setWidth(width)
                root.setHeight(height)
                settle()
                dates = root.findChild(QObject, "dateList")
                for index, day in enumerate(bridge.days.rows):
                    button = QQmlExpression(QQmlEngine.contextForObject(dates), dates,
                                            f"itemAtIndex({index})").evaluate()[0]
                    if button is None:
                        raise RuntimeError("The diary date button is missing")
                    button.clicked.emit()
                    deadline = time.monotonic() + 5
                    while bridge._pending and time.monotonic() < deadline:
                        settle(20)
                    settle()
                    reader = root.findChild(QObject, "diaryReader")
                    if (bridge._pending or bridge.diaryDay != day["day"]
                            or f"第 {day['day']:04d} 天" not in reader.property("text")
                            or reader.width() < 300 or not reader.isVisible()):
                        raise RuntimeError("Selecting a diary date did not display its text")
                diary_sizes.append([width, height, reader.width()])
            failures = [message for message in messages if any(part in message for part in
                        ("Error", "Cannot", "Unable", "failed", "Binding loop", "recursive rearrange", "not found", "is not defined"))]
            if failures or not bridge.chat.rows or bridge._pending or bridge.error:
                raise RuntimeError("\n".join(failures) or bridge.notice)
            report = {"ok": True, "welcome_rendered": True, "avatar_stage_layout": True,
                      "live2d_rendering": "not_exercised", "diary_selection": True,
                      "diary_sizes": diary_sizes,
                      "pages_rendered": len(rendered), "settings_sections": 6, "languages": 4,
                      "sizes": rendered, "offline_chat": True, "qml_errors": failures,
                      "graphics_api": str(root.rendererInterface().graphicsApi()), "messages": messages}
            Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
            return 0
        finally:
            bridge.shutdown()
            if engine is not None:
                root.setProperty("mayClose", True)
                root.close()
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qInstallMessageHandler(old_handler)


if __name__ == "__main__":
    import sys
    raise SystemExit(run(sys.argv[1], native="--native" in sys.argv[2:]))
