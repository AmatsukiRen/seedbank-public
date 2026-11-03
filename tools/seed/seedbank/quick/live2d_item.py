"""A single local Live2D stage composited inside the Qt Quick scene.

Model/GL operations, including destruction, belong to the render thread.
The SDK framework stays initialized until process exit, after window cleanup.
The GUI thread only sends snapshots through synchronize() and receives queued
status signals. Importing this module does not initialize Live2D or open files.
"""
from __future__ import annotations

import atexit
import logging
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QOpenGLContext
from PySide6.QtOpenGL import QOpenGLFramebufferObject
from PySide6.QtQml import qmlRegisterType
from PySide6.QtQuick import QQuickFramebufferObject, QQuickOpenGLUtils
from shiboken6 import Shiboken

from ..live2d_model import descriptor
from .. import startup_log
from .live2d_motion import MotionPlayback
from .avatar_expression import ExpressionPlayback
from .avatar_view import normalized_view

_log = logging.getLogger(__name__)


class Framework:
    """Process lifetime for Cubism's shared IDs and allocator.

    live2d-py 1.0.0 crashes loading a second model after dispose()/init(), even
    without GL. A scene graph invalidation must release graphics, not Cubism.
    This app has one native avatar window; acquire runs on its render thread.
    """
    def __init__(self):
        self.sdk = None

    def acquire(self):
        if self.sdk is None:
            startup_log.mark("live2d.import.begin")
            import live2d
            startup_log.mark("live2d.init.begin")
            live2d.init()
            self.sdk = live2d
        return self.sdk

    def dispose(self):
        sdk, self.sdk = self.sdk, None
        if sdk is not None:
            try:
                sdk.dispose()
            except Exception:
                _log.exception("Live2D SDK cleanup failed")


_framework = Framework()
atexit.register(_framework.dispose)


class AvatarRuntime(QObject):
    """One owner for the single window's native resources."""
    def __init__(self, window):
        super().__init__(window)
        self.sdk = None
        self.renderers = []
        window.sceneGraphInvalidated.connect(self.release, Qt.ConnectionType.DirectConnection)

    def acquire(self, renderer):
        if renderer not in self.renderers:
            self.renderers.append(renderer)
        if self.sdk is None:
            sdk = _framework.acquire()
            startup_log.mark("live2d.gl_init.begin")
            sdk.glInit()
            self.sdk = sdk
            startup_log.mark("live2d.sdk.ready")
        return self.sdk

    @Slot()
    def release(self):
        # Detach first: a failed native destructor must not leave half-released
        # objects registered for another teardown, or skip the remaining ones.
        renderers, self.renderers = self.renderers, []
        sdk, self.sdk = self.sdk, None
        for renderer in renderers:
            try:
                renderer.release_model()
            except Exception:
                _log.exception("Live2D model cleanup failed")
            finally:
                renderer.loaded_key = None
                renderer.last_report = None
        if sdk is not None:
            try:
                sdk.glRelease()
            except Exception:
                _log.exception("Live2D graphics cleanup failed")


class Live2DItem(QQuickFramebufferObject):
    sourceChanged = Signal()
    animatingChanged = Signal()
    motionChanged = Signal()
    expressionChanged = Signal()
    zoomChanged = Signal()
    offsetChanged = Signal()
    statusChanged = Signal()
    rendered = Signal(str, int, int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = ""
        self._animating = False
        self._motion = "idle"
        self._expression = "idle"
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._status = "loading"
        self._detail = ""
        self._pointer = (0.5, 0.5)
        self._revision = 0
        self._renderer_epoch = 0
        self._renderer = None
        self.setMirrorVertically(True)
        self._timer = QTimer(self)
        # Request frames near a 60 Hz display cadence. The scene graph still
        # controls presentation; this interval is not a measured frame rate.
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self.visibleChanged.connect(self._schedule)
        self.rendered.connect(self._receive, Qt.ConnectionType.QueuedConnection)

    @Property(str, notify=sourceChanged)
    def source(self):
        return self._source

    @source.setter
    def source(self, value):
        if value != self._source:
            self._source = value
            self._revision += 1
            self._pointer = (0.5, 0.5)
            self._status, self._detail = "loading", ""
            self.sourceChanged.emit()
            self.statusChanged.emit()
            self._schedule()
            self.update()

    @Property(bool, notify=animatingChanged)
    def animating(self):
        return self._animating

    @animating.setter
    def animating(self, value):
        if bool(value) != self._animating:
            self._animating = bool(value)
            self.animatingChanged.emit()
            self._schedule()
            self.update()

    @Property(str, notify=motionChanged)
    def motion(self):
        return self._motion

    @motion.setter
    def motion(self, value):
        if value != self._motion:
            self._motion = value
            self.motionChanged.emit()
            self.update()

    @Property(str, notify=expressionChanged)
    def expression(self):
        return self._expression

    @expression.setter
    def expression(self, value):
        if value != self._expression:
            self._expression = value
            self.expressionChanged.emit()
            self.update()

    @Property(float, notify=zoomChanged)
    def zoom(self):
        return self._zoom

    @zoom.setter
    def zoom(self, value):
        value = normalized_view({"live2d_zoom": value})["live2d_zoom"]
        if value != self._zoom:
            self._zoom = value
            self.zoomChanged.emit()
            self.update()

    @Property(float, notify=offsetChanged)
    def offsetX(self):
        return self._offset_x

    @offsetX.setter
    def offsetX(self, value):
        value = normalized_view({"live2d_offset_x": value})["live2d_offset_x"]
        if value != self._offset_x:
            self._offset_x = value
            self.offsetChanged.emit()
            self.update()

    @Property(float, notify=offsetChanged)
    def offsetY(self):
        return self._offset_y

    @offsetY.setter
    def offsetY(self, value):
        value = normalized_view({"live2d_offset_y": value})["live2d_offset_y"]
        if value != self._offset_y:
            self._offset_y = value
            self.offsetChanged.emit()
            self.update()

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def detail(self):
        return self._detail

    @Slot(float, float)
    def lookAt(self, x, y):
        if self._animating:
            self._pointer = (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))

    @Slot()
    def reload(self):
        self._revision += 1
        self._status, self._detail = "loading", ""
        self.statusChanged.emit()
        self._schedule()
        self.update()

    @Slot(str, int, int, str, str)
    def _receive(self, source, revision, renderer_epoch, status, detail):
        if (source, revision, renderer_epoch) != (self._source, self._revision, self._renderer_epoch):
            return
        if (status, detail) != (self._status, self._detail):
            self._status, self._detail = status, detail
            self.statusChanged.emit()
            self._schedule()

    @Slot()
    def _schedule(self):
        if self._animating and self.isVisible() and self._status != "error":
            self._timer.start()
        else:
            self._timer.stop()

    def createRenderer(self):
        # Qt creates the renderer during synchronization while the GUI is
        # blocked. A new scene graph must not accept an old renderer's report.
        startup_log.mark("live2d.renderer.create.begin")
        self._renderer_epoch += 1
        self._renderer = AvatarRenderer(self.window().property("_avatarRuntime"), self.rendered, self._renderer_epoch)
        startup_log.mark("live2d.renderer.create.ready")
        return self._renderer


class AvatarRenderer(QQuickFramebufferObject.Renderer):
    def __init__(self, runtime, report, epoch):
        super().__init__()
        self.runtime = runtime
        self.report = report
        self.epoch = epoch
        self.model = None
        self.loaded_key = None
        self.source_key = ("", 0)
        self.animating = False
        self.motion = "idle"
        self.expression = "idle"
        self.previous_motion = None
        self.playback = MotionPlayback()
        self.expressions = ExpressionPlayback()
        self.zoom = 1.0
        self.offset = (0.0, 0.0)
        self.pointer = (0.5, 0.5)
        self.registry = {}
        self.last_frame = None
        self.failure = False
        self.last_report = None

    def synchronize(self, item):
        self.source_key = (item._source, item._revision)
        self.animating = item._animating
        self.motion = item._motion
        self.expression = item._expression
        self.zoom = item._zoom
        self.offset = (item._offset_x, item._offset_y)
        self.pointer = item._pointer

    def createFramebufferObject(self, size):
        startup_log.mark("live2d.framebuffer.create.begin")
        # PySide 6.12 transfers createRenderer() to C++, but its typesystem
        # does not transfer createFramebufferObject(). A Python-constructed
        # temporary can therefore be freed as this override returns, leaving
        # Qt's scene graph with a dangling FBO. Keeping a Python reference is
        # insufficient: Qt also deletes/recreates FBOs on resize and teardown.
        # The native factory returns a borrowed wrapper. Qt alone owns the
        # allocation, including replacements after a size/DPI change.
        frame = super().createFramebufferObject(size)
        startup_log.mark("live2d.framebuffer.python_owned" if Shiboken.ownedByPython(frame)
                         else "live2d.framebuffer.cpp_owned")
        frame.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        startup_log.mark("live2d.framebuffer.create.ready")
        return frame

    def release_model(self):
        model, self.model = self.model, None
        self.last_frame = None
        self.previous_motion = None
        self.playback = MotionPlayback()
        self.expressions = ExpressionPlayback()
        self.registry = {}
        if model is not None:
            model.DestroyRenderer()

    def publish(self, status, detail=""):
        result = (*self.source_key, self.epoch, status, detail)
        if result != self.last_report:
            if status == "ready":
                startup_log.mark("live2d.first_frame")
            self.last_report = result
            self.report.emit(*result)

    def fail(self, error):
        self.failure = True
        startup_log.exception(error)
        detail = str(error)
        try:
            self.release_model()
        except Exception as cleanup_error:
            _log.exception("Live2D cleanup after rendering failure")
            detail += "\n" + str(cleanup_error)
        self.publish("error", detail)

    def render(self):
        # Qt and Cubism share the context. Neither may inherit the other's GL
        # bindings, blend functions, stencil masks or scissor state.
        try:
            QQuickOpenGLUtils.resetOpenGLState()
            from OpenGL import GL
            # resetOpenGLState() binds the default framebuffer. Restore the
            # avatar target BEFORE clearing, or old translucent frames pile up
            # inside its texture while the clear mistakenly affects the window.
            frame = self.framebufferObject()
            if not frame.bind():
                raise RuntimeError("Could not bind the Live2D framebuffer")
            size = frame.size()
            GL.glViewport(0, 0, size.width(), size.height())
            GL.glDisable(GL.GL_SCISSOR_TEST)
            GL.glColorMask(True, True, True, True)
            GL.glDepthMask(True)
            GL.glStencilMask(0xFF)
            GL.glClearColor(0.0, 0.0, 0.0, 0.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT | GL.GL_STENCIL_BUFFER_BIT)
            if self.source_key != self.loaded_key:
                self.release_model()
                self.loaded_key = self.source_key
                self.last_report = None
                self.failure = False
                self.publish("loading")
                startup_log.mark("live2d.descriptor.begin")
                content, self.registry = descriptor(self.source_key[0])
                if self.runtime is None or QOpenGLContext.currentContext() is None:
                    raise RuntimeError("OpenGL context unavailable")
                sdk = self.runtime.acquire(self)
                startup_log.mark("live2d.model.begin")
                self.model = sdk.Model()
                # The SDK's automatic renderer uses one mask texture (only
                # 36 distinct clipping groups). Load first, then allocate a
                # conservative capacity from the number of drawable meshes:
                # each mesh can introduce at most one drawable clipping group.
                # Multiple textures hold 32 groups each. The Python SDK does
                # not expose the deduplicated clipping-group count.
                self.model.LoadFromJsonString(content, False)
                startup_log.mark("live2d.model.loaded")
                if self.model.GetParamCount() <= 0:
                    raise RuntimeError("Model contains no parameters")
                drawable_count = len(self.model.GetDrawableIds())
                if drawable_count <= 0:
                    raise RuntimeError("Model contains no drawable meshes")
                mask_buffers = 1 if drawable_count <= 36 else (drawable_count + 31) // 32
                self.model.Resize(size.width(), size.height())
                startup_log.mark("live2d.renderer.masks.single" if mask_buffers == 1
                                 else "live2d.renderer.masks.multiple")
                self.model.CreateRenderer(mask_buffers)
                startup_log.mark("live2d.renderer.masks.ready")
                self.model.SetAutoBlink(True)
                self.model.SetAutoBreath(True)
            if self.failure or self.model is None:
                return
            # Texture/mask allocation may change the framebuffer on first load.
            # Explicitly restore Qt's offscreen target before drawing the model.
            if not frame.bind():
                raise RuntimeError("Could not restore the Live2D framebuffer")
            GL.glViewport(0, 0, size.width(), size.height())
            self.model.Resize(size.width(), size.height())
            self.model.SetScale(self.zoom)
            # UI stores fractions of the viewport, right/down positive.
            # Cubism wrapper offset is clip-space translation, right/up positive.
            # Translate the model before drawing, not the already-clipped FBO.
            self.model.SetOffset(2.0 * self.offset[0], -2.0 * self.offset[1])
            now = time.monotonic()
            delta = min(0.05, max(0.0, now - self.last_frame)) if self.last_frame is not None else 0.0
            self.last_frame = now
            if self.animating:
                self.model.Drag(self.pointer[0] * size.width(), self.pointer[1] * size.height())
                self.expressions.update(self.model, self.expression, self.registry["expressions"])
                self.playback.update(self.model, self.motion, self.registry["motions"])
                self.model.Update(delta)
                self.previous_motion = self.motion
            elif self.previous_motion is None:
                self.model.Update(0.0)
            self.model.Draw()
            self.publish("ready")
        except Exception as error:
            self.fail(error)
        finally:
            try:
                QQuickOpenGLUtils.resetOpenGLState()
            except Exception as error:
                self.fail(error)


_registered = False


def register_type():
    global _registered
    if not _registered:
        qmlRegisterType(Live2DItem, "Seedbank.Avatar", 1, 0, "Live2DView")
        _registered = True
