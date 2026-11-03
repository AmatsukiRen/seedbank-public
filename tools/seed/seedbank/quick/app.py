from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl, Qt
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QSurfaceFormat
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtQuickControls2 import QQuickStyle

from ..onboarding import resolve_pack
from .. import startup_log, __version__
from .bridge import Bridge
from .live2d_item import AvatarRuntime, register_type
from .window_geometry import WindowPlacement


_dll_directory = os.add_dll_directory(str(Path(PySide6.__file__).parent)) if sys.platform == "win32" else None


def application():
    startup_log.mark("qt.application.begin")
    app = QGuiApplication.instance()
    if app is None:
        # Live2D uses the same OpenGL scene as the rest of the Qt Quick UI.
        # Respect explicit software/offscreen choices for user-run headless tests.
        if os.environ.get("QT_QUICK_BACKEND") != "software" and os.environ.get("QT_QPA_PLATFORM") not in ("offscreen", "minimal"):
            QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
            form = QSurfaceFormat()
            form.setVersion(3, 3)
            form.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
            form.setAlphaBufferSize(8)
            form.setDepthBufferSize(24)
            form.setStencilBufferSize(8)
            QSurfaceFormat.setDefaultFormat(form)
        QQuickStyle.setStyle("Basic")
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QGuiApplication([sys.argv[0]])
        app.setApplicationName("Seedbank")
        # Preserve the internal name used by existing local settings.
        app.setApplicationDisplayName("SeedBank")
        app.setApplicationVersion(__version__)
        app.setWindowIcon(QIcon(str(Path(__file__).parent / "qml" / "brand" / "seedbank-logo.png")))
        app.setFont(QFont("Microsoft YaHei UI", 11))
    startup_log.mark("qt.application.ready")
    return app


def create_engine(bridge, *, test_mode=False):
    startup_log.mark("qml.engine.begin")
    register_type()
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    context = engine.rootContext()
    context.setContextProperty("bridge", bridge)
    context.setContextProperty("testMode", test_mode)
    context.setContextProperty("avatarGraphicsEnabled", os.environ.get("QT_QUICK_BACKEND") != "software" and os.environ.get("QT_QPA_PLATFORM") not in ("offscreen", "minimal"))
    for name, model in (("chatModel", bridge.chat), ("daysModel", bridge.days),
                        ("memoryModel", bridge.memories), ("lifeModel", bridge.life)):
        context.setContextProperty(name, model)
    startup_log.mark("qml.load.begin")
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("The Qt Quick interface could not be loaded.\n" + "\n".join(warnings))
    root = engine.rootObjects()[0]
    # QML owns the C++ window, but that does not root its Python reference
    # cycle (window -> placement -> window) for cyclic GC. Keep the wrapper
    # and its Python-only runtime state alive until the engine is torn down.
    engine._root_window = root
    startup_log.mark("qml.load.ready")
    engine._startup_error = ""

    def graphics_error(_code, message):
        # Qt otherwise may terminate without passing through Python's catch.
        # This signal is delivered on the GUI thread. Exit on its next turn,
        # even if initialization failed before app.exec() was entered.
        if not engine._startup_error:
            engine._startup_error = str(message) or "Graphics context unavailable"
            startup_log.mark("qt.scene_graph.error")
            QTimer.singleShot(0, lambda: QCoreApplication.exit(1))

    root.sceneGraphError.connect(graphics_error)
    root.sceneGraphInitialized.connect(lambda: startup_log.mark("qt.scene_graph.ready"), Qt.ConnectionType.DirectConnection)
    first_frame = [False]

    def frame_ready():
        if not first_frame[0]:
            first_frame[0] = True
            startup_log.mark("qt.first_frame")

    root.frameSwapped.connect(frame_ready)
    root._avatar_runtime = AvatarRuntime(root)
    root.setProperty("_avatarRuntime", root._avatar_runtime)
    if not test_mode:
        screens = QGuiApplication.screens()
        saved = bridge.preferences.get("quick_geometry")
        if not saved:
            old = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", str(bridge.preferences.get("desktop_geometry", "")))
            saved = [int(value) for value in old.groups()] if old else None
        root._placement = WindowPlacement(root, screens, saved)
        startup_log.mark("window.show.begin")
        root.show()
        startup_log.mark("window.show.returned")
        root._placement.schedule()
    return engine


def run(pack=None, brain_override="", *, acquire_lock=None):
    app = application()
    startup_log.mark("bridge.create.begin")
    bridge = Bridge(pack or resolve_pack(), brain_override, acquire_lock=acquire_lock)
    startup_log.mark("bridge.create.ready")
    engine = None
    try:
        engine = create_engine(bridge)
        startup_log.mark("qt.event_loop.begin")
        result = app.exec()
        startup_log.mark("qt.event_loop.returned")
        if engine._startup_error:
            raise RuntimeError("无法初始化图形界面，请使用同目录的 Safe-Graphics.cmd。\n" + engine._startup_error)
    finally:
        try:
            bridge.shutdown()
        finally:
            if engine is not None:
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return result


def window(pack_dir, brain_override=""):
    return run(pack_dir, brain_override)
