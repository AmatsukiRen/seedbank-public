"""Isolated offscreen regressions with mocked SDK/GL and no real pack."""
import gc
from types import MethodType, ModuleType, SimpleNamespace
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from seedbank.quick import app as quick_app
from seedbank.quick import live2d_item as avatar


class Live2DLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        # No SDK import is allowed accidentally. Explicit acquire fixtures
        # override this with a fully local mock and never load _live2d.pyd.
        guard = patch.dict("sys.modules", {"live2d": None})
        guard.start()
        self.addCleanup(guard.stop)
        framework = patch.object(avatar, "_framework", avatar.Framework())
        framework.start()
        self.addCleanup(framework.stop)

    def item(self):
        item = avatar.Live2DItem()
        self.addCleanup(item.deleteLater)
        return item

    def test_engine_keeps_python_runtime_alive_after_factory_returns(self):
        engine = QQmlApplicationEngine()
        engine.loadData(b'import QtQuick; import QtQuick.Controls.Basic; ApplicationWindow { visible: false }')
        # Exercise create_engine with a QML-owned window, not a Python Mock.
        with patch.object(quick_app, "QQmlApplicationEngine", return_value=engine), \
             patch.object(engine, "load"), patch.object(QQuickWindow, "show"), \
             patch.object(QGuiApplication, "screens", return_value=[]):
            quick_app.create_engine(Mock(preferences={}), test_mode=False)
        try:
            gc.collect()
            window = engine.rootObjects()[0]
            self.assertIs(window._placement.window, window)
            self.assertIsNotNone(window._placement.timer)
            runtime = window.property("_avatarRuntime")
            sdk, renderer = Mock(), Mock()
            with patch.dict("sys.modules", {"live2d": sdk}):
                self.assertIs(runtime.acquire(renderer), sdk)
                runtime.release()
                self.assertIs(runtime.acquire(renderer), sdk)
                runtime.release()
            self.assertEqual(sdk.init.call_count, 1)
            self.assertEqual(sdk.glInit.call_count, 2)
            self.assertEqual(sdk.glRelease.call_count, 2)
            sdk.dispose.assert_not_called()
        finally:
            engine.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def renderer(self):
        model = Mock()
        size = SimpleNamespace(width=lambda: 640, height=lambda: 480)
        frame = Mock()
        frame.size.return_value = size
        renderer = SimpleNamespace(model=model, loaded_key=("fixture", 1), source_key=("fixture", 1),
            epoch=3, animating=False, motion="idle", previous_motion="idle", zoom=1.0, offset=(0.0, 0.0), pointer=(0.5, 0.5),
            registry={}, last_frame=None, failure=False, last_report=None, report=Mock(),
            framebufferObject=lambda: frame, runtime=None, playback=avatar.MotionPlayback(),
            expression="idle", expressions=avatar.ExpressionPlayback())
        for name in ("release_model", "publish", "fail"):
            setattr(renderer, name, MethodType(getattr(avatar.AvatarRenderer, name), renderer))
        return renderer, model

    def render(self, renderer, *, resets=None):
        module = ModuleType("OpenGL")
        module.GL = Mock(GL_SCISSOR_TEST=1, GL_COLOR_BUFFER_BIT=2, GL_DEPTH_BUFFER_BIT=4, GL_STENCIL_BUFFER_BIT=8)
        with patch.dict("sys.modules", {"OpenGL": module}), \
             patch.object(avatar.QQuickOpenGLUtils, "resetOpenGLState", side_effect=resets) as reset, \
             patch.object(avatar, "descriptor", side_effect=AssertionError("No real model")):
            avatar.AvatarRenderer.render(renderer)
        return reset

    def test_panning_redraws_a_paused_model_without_advancing_animation(self):
        renderer, model = self.renderer()
        renderer.offset = (.2, .15)
        self.render(renderer)
        model.SetOffset.assert_called_once_with(.4, -.3)
        model.Draw.assert_called_once()
        model.Update.assert_not_called()
        model.Drag.assert_not_called()
        self.assertFalse(renderer.failure)

    def test_expression_changes_leave_the_active_hand_motion_running(self):
        renderer, model = self.renderer()
        renderer.animating = True
        renderer.motion = "wave"
        renderer.registry = {"motions": {"SeedWave", "SeedReturn", "SeedIdle"},
                             "expressions": {"SeedHappy", "SeedSad"}}
        model.IsMotionFinished.return_value = False
        renderer.expression = "happy"
        self.render(renderer)
        renderer.expression = "sad"
        self.render(renderer)
        model.StartMotion.assert_called_once_with("SeedWave", 0, 3)
        self.assertEqual([row.args[0] for row in model.SetExpression.call_args_list], ["SeedHappy", "SeedSad"])
        self.assertFalse(renderer.failure)

    def test_paused_renderer_does_not_apply_queued_expression_changes(self):
        renderer, model = self.renderer()
        renderer.expression = "sad"
        self.render(renderer)
        model.SetExpression.assert_not_called()
        model.ResetExpressions.assert_not_called()
        model.Update.assert_not_called()

    def test_pan_preview_keeps_the_animation_timer_stopped(self):
        item = self.item()
        item.animating = False
        item.offsetX = .2
        item.offsetY = .15
        self.assertFalse(item._timer.isActive())
        self.assertEqual((item.offsetX, item.offsetY), (.2, .15))

    def test_invalid_view_coordinates_cannot_reach_the_native_renderer(self):
        item = self.item()
        item.zoom = float("nan")
        item.offsetX = float("inf")
        item.offsetY = -20
        self.assertEqual((item.zoom, item.offsetX, item.offsetY), (1.0, 0.0, -.45))

    def test_switching_away_and_back_rejects_the_first_load_result(self):
        item = self.item()
        item.source = "first.model3.json"
        old = (item.source, item._revision, item._renderer_epoch)
        item.source = "second.model3.json"
        item.source = "first.model3.json"
        item._receive(*old, "error", "obsolete failure")
        self.assertEqual(item.status, "loading")
        self.assertEqual(item.detail, "")
        item._receive(item.source, item._revision, item._renderer_epoch, "ready", "")
        self.assertEqual(item.status, "ready")

    def test_reload_rejects_queued_ready_for_same_path(self):
        item = self.item()
        item.source = "fixture.model3.json"
        old = (item.source, item._revision, item._renderer_epoch)
        item.reload()
        item._receive(*old, "ready", "")
        self.assertEqual(item.status, "loading")
        item._receive(item.source, item._revision, item._renderer_epoch, "error", "current failure")
        self.assertEqual(item.detail, "current failure")

    def test_recreated_renderer_rejects_previous_scene_reports(self):
        item = self.item()
        item.source = "fixture.model3.json"
        window = Mock()
        with patch.object(item, "window", return_value=window), patch.object(avatar, "AvatarRenderer") as factory:
            item.createRenderer()
            old = (item.source, item._revision, item._renderer_epoch)
            item.createRenderer()
            self.assertEqual(factory.call_count, 2)
        item._receive(*old, "error", "old scene failure")
        self.assertEqual(item.status, "loading")
        item._receive(item.source, item._revision, item._renderer_epoch, "ready", "")
        self.assertEqual(item.status, "ready")

    def test_framebuffer_uses_native_factory_and_preserves_depth_stencil(self):
        renderer = avatar.AvatarRenderer(None, Mock(), 1)
        frame = Mock()
        size = QSize(128, 96)
        with patch.object(avatar.QQuickFramebufferObject.Renderer, "createFramebufferObject", return_value=frame) as factory, \
             patch.object(avatar.Shiboken, "ownedByPython", return_value=False):
            self.assertIs(renderer.createFramebufferObject(size), frame)
        factory.assert_called_once_with(size)
        frame.setAttachment.assert_called_once_with(avatar.QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)

    def test_error_stops_refresh_and_reload_resumes_scheduling(self):
        item = self.item()
        item.setVisible(True)
        item.source = "fixture.model3.json"
        item.animating = True
        item._receive(item.source, item._revision, item._renderer_epoch, "error", "load failed")
        self.assertFalse(item._timer.isActive())
        item.reload()
        self.assertTrue(item._timer.isActive())
        item.animating = False
        self.assertFalse(item._timer.isActive())

    def test_model_cleanup_failure_does_not_skip_other_models_or_graphics_release(self):
        first, second, sdk = Mock(), Mock(), Mock()
        first.release_model.side_effect = RuntimeError("first cleanup")
        sdk.glRelease.side_effect = RuntimeError("graphics cleanup")
        runtime = SimpleNamespace(renderers=[first, second], sdk=sdk)
        with self.assertLogs(avatar._log, level="ERROR"):
            avatar.AvatarRuntime.release(runtime)
        first.release_model.assert_called_once()
        second.release_model.assert_called_once()
        sdk.glRelease.assert_called_once()
        sdk.dispose.assert_not_called()
        self.assertIsNone(runtime.sdk)
        self.assertEqual(runtime.renderers, [])
        self.assertIsNone(first.loaded_key)
        self.assertIsNone(second.loaded_key)
        avatar.AvatarRuntime.release(runtime)
        sdk.glRelease.assert_called_once()

    def test_model_owner_is_cleared_even_when_native_release_raises(self):
        renderer, model = self.renderer()
        model.DestroyRenderer.side_effect = RuntimeError("release failed")
        with self.assertRaisesRegex(RuntimeError, "release failed"):
            renderer.release_model()
        self.assertIsNone(renderer.model)
        self.assertIsNone(renderer.last_frame)
        self.assertIsNone(renderer.previous_motion)
        renderer.release_model()
        model.DestroyRenderer.assert_called_once()

    def test_draw_failure_still_reports_current_request_when_cleanup_also_fails(self):
        renderer, model = self.renderer()
        model.Draw.side_effect = RuntimeError("draw failed")
        model.DestroyRenderer.side_effect = RuntimeError("release failed")
        with self.assertLogs(avatar._log, level="ERROR"):
            reset = self.render(renderer)
        self.assertEqual(reset.call_count, 2)
        self.assertTrue(renderer.failure)
        self.assertIsNone(renderer.model)
        report = renderer.report.emit.call_args.args
        self.assertEqual(report[:4], ("fixture", 1, 3, "error"))
        self.assertIn("draw failed", report[4])
        self.assertIn("release failed", report[4])

    def test_each_frame_clears_avatar_target_after_qt_reset(self):
        renderer, model = self.renderer()
        state = {"bound": 0, "avatar": ["old frame"], "window": ["UI"]}
        module = ModuleType("OpenGL")
        module.GL = Mock(GL_SCISSOR_TEST=1, GL_COLOR_BUFFER_BIT=2, GL_DEPTH_BUFFER_BIT=4, GL_STENCIL_BUFFER_BIT=8)

        def reset():
            state["bound"] = 0  # QQuickOpenGLUtils binds the default FBO.

        def bind():
            state["bound"] = 42
            return True

        def clear(_bits):
            self.assertEqual(state["bound"], 42, "Must not clear the window/default target")
            state["avatar"].clear()

        renderer.framebufferObject().bind.side_effect = bind
        module.GL.glClear.side_effect = clear
        model.Draw.side_effect = lambda: state["avatar"].append("new frame")
        with patch.dict("sys.modules", {"OpenGL": module}), \
             patch.object(avatar.QQuickOpenGLUtils, "resetOpenGLState", side_effect=reset):
            for _ in range(3):
                avatar.AvatarRenderer.render(renderer)
                self.assertEqual(state["avatar"], ["new frame"])
                self.assertEqual(state["window"], ["UI"])
        self.assertFalse(renderer.failure)
        self.assertEqual(model.Draw.call_count, 3)

    def test_model_loading_cannot_redirect_the_draw_target(self):
        renderer, old_model = self.renderer()
        renderer.loaded_key = None
        renderer.runtime = Mock()
        model = renderer.runtime.acquire.return_value.Model.return_value
        model.GetParamCount.return_value = 1
        model.GetDrawableIds.return_value = ["mesh"] * 97
        state = {"bound": 0}
        module = ModuleType("OpenGL")
        module.GL = Mock(GL_SCISSOR_TEST=1, GL_COLOR_BUFFER_BIT=2, GL_DEPTH_BUFFER_BIT=4, GL_STENCIL_BUFFER_BIT=8)

        def bind():
            state["bound"] = 42
            return True

        renderer.framebufferObject().bind.side_effect = bind
        module.GL.glClear.side_effect = lambda _bits: self.assertEqual(state["bound"], 42)
        model.LoadFromJsonString.side_effect = lambda _content, _create: state.update(bound=99)
        model.CreateRenderer.side_effect = lambda _count: state.update(bound=100)
        model.Draw.side_effect = lambda: self.assertEqual(state["bound"], 42)
        with patch.dict("sys.modules", {"OpenGL": module}), \
             patch.object(avatar.QQuickOpenGLUtils, "resetOpenGLState", side_effect=lambda: state.update(bound=0)), \
             patch.object(avatar.QOpenGLContext, "currentContext", return_value=Mock()), \
             patch.object(avatar, "descriptor", return_value=("{}", {"motions": [], "expressions": []})):
            avatar.AvatarRenderer.render(renderer)
        model.Draw.assert_called_once()
        model.LoadFromJsonString.assert_called_once_with("{}", False)
        model.CreateRenderer.assert_called_once_with(4)
        calls = model.method_calls
        self.assertLess(next(i for i, call in enumerate(calls) if call[0] == "Resize"),
                        next(i for i, call in enumerate(calls) if call[0] == "CreateRenderer"))
        old_model.DestroyRenderer.assert_called_once()
        self.assertFalse(renderer.failure)

    def test_mask_capacity_covers_single_texture_boundary_and_complex_models(self):
        for drawable_count, expected_buffers in ((36, 1), (37, 2), (128, 4), (129, 5)):
            with self.subTest(drawables=drawable_count):
                renderer, _old_model = self.renderer()
                renderer.loaded_key = None
                renderer.runtime = Mock()
                model = renderer.runtime.acquire.return_value.Model.return_value
                model.GetParamCount.return_value = 1
                model.GetDrawableIds.return_value = ["mesh"] * drawable_count
                module = ModuleType("OpenGL")
                module.GL = Mock(GL_COLOR_BUFFER_BIT=2, GL_DEPTH_BUFFER_BIT=4, GL_STENCIL_BUFFER_BIT=8)
                with patch.dict("sys.modules", {"OpenGL": module}), \
                     patch.object(avatar.QQuickOpenGLUtils, "resetOpenGLState"), \
                     patch.object(avatar.QOpenGLContext, "currentContext", return_value=Mock()), \
                     patch.object(avatar, "descriptor", return_value=("{}", {"motions": [], "expressions": []})):
                    avatar.AvatarRenderer.render(renderer)
                model.LoadFromJsonString.assert_called_once_with("{}", False)
                model.CreateRenderer.assert_called_once_with(expected_buffers)
                model.Draw.assert_called_once()
                self.assertFalse(renderer.failure)

    def test_renderer_allocation_failure_does_not_draw_a_partial_model(self):
        renderer, _old_model = self.renderer()
        renderer.loaded_key = None
        renderer.runtime = Mock()
        model = renderer.runtime.acquire.return_value.Model.return_value
        model.GetParamCount.return_value = 1
        model.GetDrawableIds.return_value = ["mesh"] * 70
        model.CreateRenderer.side_effect = RuntimeError("fixture allocation failure")
        module = ModuleType("OpenGL")
        module.GL = Mock(GL_COLOR_BUFFER_BIT=2, GL_DEPTH_BUFFER_BIT=4, GL_STENCIL_BUFFER_BIT=8)
        with patch.dict("sys.modules", {"OpenGL": module}), \
             patch.object(avatar.QQuickOpenGLUtils, "resetOpenGLState"), \
             patch.object(avatar.QOpenGLContext, "currentContext", return_value=Mock()), \
             patch.object(avatar, "descriptor", return_value=("{}", {"motions": [], "expressions": []})):
            avatar.AvatarRenderer.render(renderer)
        model.Draw.assert_not_called()
        model.DestroyRenderer.assert_called_once()
        self.assertTrue(renderer.failure)

    def test_failed_framebuffer_bind_never_clears_the_default_target(self):
        renderer, model = self.renderer()
        renderer.framebufferObject().bind.return_value = False
        module = ModuleType("OpenGL")
        module.GL = Mock()
        with patch.dict("sys.modules", {"OpenGL": module}), \
             patch.object(avatar.QQuickOpenGLUtils, "resetOpenGLState"):
            avatar.AvatarRenderer.render(renderer)
        module.GL.glClear.assert_not_called()
        model.Draw.assert_not_called()
        self.assertTrue(renderer.failure)

    def test_initial_gl_state_failure_is_reported_without_drawing(self):
        renderer, model = self.renderer()
        self.render(renderer, resets=[RuntimeError("initial state failed"), None])
        model.Draw.assert_not_called()
        model.DestroyRenderer.assert_called_once()
        self.assertEqual(renderer.report.emit.call_args.args[3:], ("error", "initial state failed"))

    def test_final_gl_state_failure_cleans_model_and_overrides_ready(self):
        renderer, model = self.renderer()
        self.render(renderer, resets=[None, RuntimeError("final state failed")])
        model.Draw.assert_called_once()
        model.DestroyRenderer.assert_called_once()
        self.assertTrue(renderer.failure)
        self.assertEqual(renderer.report.emit.call_args.args[3:], ("error", "final state failed"))

    def test_context_invalidation_allows_a_fresh_sdk_acquisition(self):
        sdk, renderer = Mock(), Mock()
        runtime = SimpleNamespace(renderers=[], sdk=None)
        with patch.dict("sys.modules", {"live2d": sdk}):
            self.assertIs(avatar.AvatarRuntime.acquire(runtime, renderer), sdk)
            avatar.AvatarRuntime.release(runtime)
            self.assertIs(avatar.AvatarRuntime.acquire(runtime, renderer), sdk)
        self.assertEqual(sdk.init.call_count, 1)
        self.assertEqual(sdk.glInit.call_count, 2)
        self.assertEqual(runtime.renderers, [renderer])

    def test_initialization_failure_preserves_original_error_and_can_retry(self):
        sdk, renderer = Mock(), Mock()
        sdk.glInit.side_effect = [RuntimeError("initialization failed"), None]
        runtime = SimpleNamespace(renderers=[], sdk=None)
        with patch.dict("sys.modules", {"live2d": sdk}):
            with self.assertRaisesRegex(RuntimeError, "initialization failed"):
                avatar.AvatarRuntime.acquire(runtime, renderer)
            self.assertIsNone(runtime.sdk)
            self.assertIs(avatar.AvatarRuntime.acquire(runtime, renderer), sdk)
        self.assertEqual(runtime.renderers, [renderer])
        sdk.init.assert_called_once()
        sdk.dispose.assert_not_called()

    def test_two_contexts_release_models_and_graphics_before_process_framework(self):
        sdk, calls = Mock(), Mock()
        calls.attach_mock(sdk, "sdk")
        with patch.dict("sys.modules", {"live2d": sdk}):
            for _ in range(2):
                renderer = Mock()
                calls.attach_mock(renderer.release_model, "release_model")
                runtime = SimpleNamespace(renderers=[], sdk=None)
                avatar.AvatarRuntime.acquire(runtime, renderer)
                avatar.AvatarRuntime.release(runtime)
            avatar._framework.dispose()
            avatar._framework.dispose()
        self.assertEqual([call[0] for call in calls.mock_calls], [
            "sdk.init", "sdk.glInit", "release_model", "sdk.glRelease",
            "sdk.glInit", "release_model", "sdk.glRelease", "sdk.dispose"])

    def test_scene_graph_error_schedules_exit_once_even_before_event_loop(self):
        engine, root, bridge = Mock(), Mock(), Mock()
        engine.rootObjects.return_value = [root]
        queued = []
        with patch.object(quick_app, "QQmlApplicationEngine", return_value=engine), \
             patch.object(quick_app, "register_type"), \
             patch.object(quick_app, "AvatarRuntime"), \
             patch.object(quick_app.QTimer, "singleShot", side_effect=lambda _delay, callback: queued.append(callback)), \
             patch.object(quick_app.QCoreApplication, "exit") as leave:
            self.assertIs(quick_app.create_engine(bridge, test_mode=True), engine)
            handler = root.sceneGraphError.connect.call_args.args[0]
            handler(0, "fixture graphics failure")
            handler(0, "duplicate notification")
            leave.assert_not_called()
            self.assertEqual(len(queued), 1)
            queued[0]()
            leave.assert_called_once_with(1)
        self.assertEqual(engine._startup_error, "fixture graphics failure")

    def test_graphics_error_propagates_to_entry_after_event_loop_and_cleanup(self):
        bridge, engine, app = Mock(), Mock(_startup_error="fixture context failure"), Mock()
        app.exec.return_value = 1
        with patch.object(quick_app, "application", return_value=app), \
             patch.object(quick_app, "Bridge", return_value=bridge), \
             patch.object(quick_app, "create_engine", return_value=engine), \
             patch.object(quick_app.QCoreApplication, "sendPostedEvents"):
            with self.assertRaisesRegex(RuntimeError, "Safe-Graphics.cmd"):
                quick_app.run("unused-fixture-path")
        bridge.shutdown.assert_called_once()
        engine.deleteLater.assert_called_once()

    def test_shutdown_failure_still_delivers_engine_deferred_deletion(self):
        bridge, engine, app = Mock(), Mock(), Mock()
        bridge.shutdown.side_effect = RuntimeError("worker shutdown failed")
        with patch.object(quick_app, "application", return_value=app), \
             patch.object(quick_app, "Bridge", return_value=bridge), \
             patch.object(quick_app, "create_engine", return_value=engine), \
             patch.object(quick_app.QCoreApplication, "sendPostedEvents") as posted:
            with self.assertRaisesRegex(RuntimeError, "worker shutdown failed"):
                quick_app.run("unused-fixture-path")
        engine.deleteLater.assert_called_once()
        posted.assert_called_once_with(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
