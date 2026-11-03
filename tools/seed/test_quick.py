from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.dirname(__file__))

import json
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, qInstallMessageHandler
from PySide6.QtQuick import QQuickItem
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from seedbank.pack import hatch
from seedbank.quick.app import application, create_engine
from seedbank.quick.bridge import Bridge
from seedbank.quick.models import Rows


EGG = Path(__file__).resolve().parents[2] / "eggs" / "dafeiyu.egg"


class QuickTest(unittest.TestCase):
    maxDiff = None
    @classmethod
    def setUpClass(cls):
        cls.app = application()
        if os.name == "nt":
            for filename in ("msyh.ttc", "segoeui.ttf", "malgun.ttf"):
                QFontDatabase.addApplicationFont(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", filename))
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="seedbank-qt-test-")
        self.addCleanup(self.workspace.cleanup)
        home = str(Path(self.workspace.name) / "home")
        self.environment = mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home, "SEEDBANK_LANG": "zh_CN"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.messages = []
        self.previous_handler = qInstallMessageHandler(lambda kind, context, message: self.messages.append(str(message)))
        self.addCleanup(lambda: qInstallMessageHandler(self.previous_handler))
        self.pack = Path(self.workspace.name) / "Qt测试.life"
        hatch(self.pack, EGG, "测试")
        self.bridge = Bridge(timers=False, brain_override="stub")
        self.addCleanup(self.bridge.shutdown)
        self.engine = None

    def wait_for(self, condition, timeout=8):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            # Yield Python's GIL as app.exec() does in production. qWait alone
            # can starve the Python worker while this polling loop owns it.
            time.sleep(0.002)
        self.assertTrue(condition(), self.bridge.notice)

    def test_avatar_view_persists_together_and_preserves_other_preferences(self):
        from seedbank.settings import ui_settings_path
        from seedbank.util import read_json, write_json_atomic
        write_json_atomic(ui_settings_path(), {"desktop_theme": "mint", "unrelated": "retain"})
        self.assertTrue(self.bridge.setAvatarView(1.6, .22, -.13))
        saved = read_json(ui_settings_path())
        self.assertEqual(saved["unrelated"], "retain")
        self.assertEqual(saved["desktop_theme"], "mint")
        reopened = Bridge(timers=False, brain_override="stub")
        try:
            self.assertEqual(reopened.preferences["live2d_zoom"], 1.6)
            self.assertEqual(reopened.preferences["live2d_offset_x"], .22)
            self.assertEqual(reopened.preferences["live2d_offset_y"], -.13)
        finally:
            reopened.shutdown()

    def test_avatar_view_failed_save_does_not_change_in_memory_state(self):
        before = dict(self.bridge.preferences)
        with mock.patch("seedbank.quick.bridge.write_json_atomic", side_effect=OSError("unwritable")):
            self.assertFalse(self.bridge.setAvatarView(1.6, .22, -.13))
        self.assertEqual(self.bridge.preferences, before)

    def test_first_launch_without_model_offers_selection_instead_of_loading(self):
        self.interface()
        self.assertEqual(self.bridge.avatarModel, "")
        self.engine.rootContext().setContextProperty("testMode", False)
        stage = self.root.findChild(QObject, "live2dStage")
        self.wait_for(lambda: stage.property("loadStatus") == "unconfigured")
        self.assertIn("选择", self.root.findChild(QObject, "avatarStatus").property("text"))
        self.assertTrue(self.bridge.ready)
        self.assert_no_errors()

    def test_clearing_model_preserves_other_preferences_and_survives_reopen(self):
        self.bridge.preference("desktop_theme", "mint")
        self.bridge.preference("live2d_model", "artificial.model3.json")
        self.bridge.preference("live2d_model", "")
        reopened = Bridge(timers=False, brain_override="stub")
        try:
            self.assertEqual(reopened.avatarModel, "")
            self.assertEqual(reopened.preferences["desktop_theme"], "mint")
        finally:
            reopened.shutdown()

    def test_selecting_a_different_model_resets_the_view_only(self):
        self.bridge.setAvatarView(1.6, .22, -.13)
        self.bridge.preference("desktop_theme", "mint")
        self.bridge.preference("live2d_model", "artificial.model3.json")
        self.assertEqual(self.bridge.preferences["desktop_theme"], "mint")
        self.assertEqual(self.bridge.preferences["live2d_zoom"], 1.0)
        self.assertEqual(self.bridge.preferences["live2d_offset_x"], 0.0)
        self.assertEqual(self.bridge.preferences["live2d_offset_y"], 0.0)

    def open_pack(self):
        self.bridge.openPack(str(self.pack))
        self.wait_for(lambda: self.bridge.ready and not self.bridge._pending)

    def interface(self):
        self.open_pack()
        started = time.perf_counter()
        self.engine = create_engine(self.bridge, test_mode=True)
        self.engine_load_ms = (time.perf_counter() - started) * 1000
        self.root = self.engine.rootObjects()[0]
        self.show_root()
        self.addCleanup(self.dispose)
        QTest.qWait(60)
        self.assert_no_errors()
        return self.root

    def show_root(self):
        if os.environ.get("QT_QPA_PLATFORM") == "windows":
            QQmlExpression(QQmlEngine.contextForObject(self.root), self.root,
                           "flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput").evaluate()
            self.root.setOpacity(0)
        self.root.show()

    def dispose(self):
        if self.engine:
            self.root.setProperty("mayClose", True)
            self.root.close()
            self.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.engine = None

    def assert_no_errors(self):
        failures = [message for message in self.messages if any(part in message for part in
                    ("Error", "Cannot", "Unable", "failed", "Binding loop", "recursive rearrange", "not found", "is not defined"))]
        self.assertEqual(failures, [])

    def find(self, name):
        result = self.root.findChild(QObject, name)
        if result is None:
            result = next((item for item in self.visual_items() if item.objectName() == name), None)
        self.assertIsNotNone(result, name)
        return result

    def visual_items(self):
        pending = list(self.root.contentItem().childItems())
        while pending:
            item = pending.pop()
            yield item
            pending.extend(item.childItems())

    def qml(self, target, script):
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, script)
        value, _undefined = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def test_all_pages_load_without_qml_errors(self):
        self.interface()
        for index in range(5):
            self.root.setProperty("page", index)
            QTest.qWait(20)
            self.assertEqual(self.find("pages").property("currentIndex"), index)
        self.assert_no_errors()

    def test_avatar_mood_changes_expression_without_restarting_hand_gesture(self):
        self.interface()
        pet = self.find("live2dStage")
        self.bridge.snapshot["states"]["mood"] = {"mood": "失落", "energy": .8}
        self.bridge.stateChanged.emit()
        self.app.processEvents()
        self.assertEqual(pet.property("expressionName"), "sad")
        self.qml(pet, "play('wave')")
        self.assertEqual(pet.property("stateName"), "wave")
        self.bridge.snapshot["states"]["mood"]["mood"] = "紧张"
        self.bridge.stateChanged.emit()
        self.app.processEvents()
        self.assertEqual(pet.property("expressionName"), "nervous")
        self.assertEqual(pet.property("stateName"), "wave")
        self.qml(self.find("avatarExpressionReset"), "triggered()")
        self.assertEqual(pet.property("expressionName"), "idle")
        self.assertEqual(pet.property("stateName"), "wave")
        self.qml(self.find("avatarExpressionTimer"), "triggered()")
        self.assertEqual(pet.property("expressionName"), "nervous")
        self.assert_no_errors()

    def test_avatar_automatic_expression_stops_when_hidden_reduced_or_dormant(self):
        self.interface()
        pet = self.find("live2dStage")
        timer = self.find("avatarExpressionTimer")
        self.assertTrue(timer.property("running"))
        pet.setVisible(False)
        self.assertFalse(timer.property("running"))
        self.assertEqual(pet.property("expressionName"), "idle")
        pet.setVisible(True)
        self.assertTrue(timer.property("running"))
        self.bridge.preference("desktop_reduced_motion", True)
        self.assertFalse(timer.property("running"))
        self.qml(pet, "play('mood')")
        self.assertEqual(pet.property("expressionName"), "idle")
        self.bridge.preference("desktop_reduced_motion", False)
        self.bridge.snapshot["states"]["lifecycle"]["state"] = "dormant"
        self.bridge.stateChanged.emit()
        self.assertFalse(timer.property("running"))
        self.assertFalse(self.find("avatarExpressionReset").property("running"))
        self.assert_no_errors()

    def test_avatar_does_not_force_a_happy_face_after_a_sad_conversation(self):
        from seedbank.util import write_json_atomic
        write_json_atomic(self.pack / "mind" / "mood.json", {"mood": "失落", "energy": .8})
        self.interface()
        signals = []
        self.bridge.petAction.connect(signals.append)
        utterances = []
        self.bridge.avatarUtterance.connect(utterances.append)
        self.bridge.setDraft("人工离线对话")
        self.bridge.send()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertNotIn("happy", signals)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0]["expression"], "neutral")
        self.assertEqual(self.find("live2dStage").property("expressionName"), "idle")
        self.assertEqual(self.bridge.mood, "失落")
        self.assert_no_errors()

    def test_channel_settings_are_offline_until_explicit_start(self):
        from seedbank import channels
        with mock.patch.object(channels.subprocess, "Popen") as proc:
            self.interface()
            self.root.setProperty("page", 4)
            self.find("settingsPage").setProperty("section", 4)
            for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
                self.bridge.preference("language", locale)
                for preset in channels.PRESETS:
                    self.bridge.selectChannel(preset["id"])
                    self.bridge.editChannel("owner", "artificial-owner")
                    self.bridge.editChannel("app_id", "artificial-app")
                    self.bridge.editChannel("self_id", "artificial-bot")
                    self.bridge.saveChannel()
                    self.assertFalse(self.bridge.error, self.bridge.notice)
                    QTest.qWait(20)
                    self.assertIsNotNone(self.find("startChannelButton"))
            proc.assert_not_called()
        self.assert_no_errors()

    def test_reply_text_expression_and_gesture_arrive_together(self):
        self.interface()
        pet = self.find("live2dStage")
        packets = []
        reply = "你好，我在这里。"
        self.bridge.avatarUtterance.connect(lambda cue: packets.append((cue, [row["text"] for row in self.bridge.chat.rows])))
        with mock.patch("seedbank.brain.StubBrain.chat", return_value={
                "reply": reply, "presentation": {"expression": "warm", "gesture": "wave"}}):
            self.bridge.setDraft("人工问候")
            self.bridge.send()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(len(packets), 1)
        self.assertIn(reply, packets[0][1])
        self.assertEqual(pet.property("expressionName"), "warm")
        self.assertEqual(pet.property("stateName"), "wave")
        self.assertTrue(pet.property("utteranceActive"))
        self.assertFalse(self.find("avatarExpressionTimer").property("running"))
        # A mood refresh and ambient tick cannot replace a reply's expression.
        self.bridge.snapshot["states"]["mood"]["mood"] = "失落"
        self.bridge.stateChanged.emit()
        self.qml(self.find("avatarExpressionTimer"), "triggered()")
        self.assertEqual(pet.property("expressionName"), "warm")
        self.qml(self.find("avatarUtteranceTimer"), "triggered()")
        self.assertFalse(pet.property("utteranceActive"))
        self.assertEqual(pet.property("expressionName"), "idle")
        self.assertEqual(pet.property("stateName"), "idle")
        self.assertTrue(self.find("avatarExpressionTimer").property("running"))
        self.assert_no_errors()

    def test_reply_animation_is_not_replayed_by_history_or_duplicate_request(self):
        self.interface()
        pet = self.find("live2dStage")
        packets = []
        self.bridge.avatarUtterance.connect(packets.append)
        with mock.patch("seedbank.brain.StubBrain.chat", return_value={
                "reply": "人工回答", "presentation": {"expression": "warm", "gesture": "wave"}}) as chat:
            self.bridge.setDraft("人工输入")
            self.bridge.send()
            identifier = self.bridge._draft_request_id
            self.wait_for(lambda: not self.bridge._pending)
            self.qml(self.find("avatarUtteranceTimer"), "triggered()")
            self.bridge.apply_snapshot(deepcopy(self.bridge.snapshot))
            self.bridge.operate("message", text="人工输入", request_id=identifier)
            self.wait_for(lambda: not self.bridge._pending)
        chat.assert_called_once()
        self.assertEqual(len(packets), 1)
        self.assertFalse(pet.property("utteranceActive"))
        self.assert_no_errors()

    def test_reply_animation_stops_on_hide_reduced_motion_dormancy_or_next_message(self):
        self.interface()
        pet = self.find("live2dStage")
        cue = {"expression": "warm", "gesture": "wave", "duration_ms": 5000}
        self.bridge.avatarUtterance.emit(cue)
        self.assertTrue(pet.property("utteranceActive"))
        pet.setVisible(False)
        self.assertFalse(pet.property("utteranceActive"))
        self.bridge.avatarUtterance.emit(cue)
        pet.setVisible(True)
        self.assertFalse(pet.property("utteranceActive"))
        self.bridge.avatarUtterance.emit(cue)
        self.bridge.preference("desktop_reduced_motion", True)
        self.assertFalse(pet.property("utteranceActive"))
        self.assertEqual(pet.property("expressionName"), "idle")
        self.bridge.preference("desktop_reduced_motion", False)
        self.bridge.avatarUtterance.emit(cue)
        self.bridge.snapshot["states"]["lifecycle"]["state"] = "dormant"
        self.bridge.stateChanged.emit()
        self.assertFalse(pet.property("utteranceActive"))
        self.bridge.snapshot["states"]["lifecycle"]["state"] = "active"
        self.bridge.stateChanged.emit()
        self.bridge.avatarUtterance.emit(cue)
        queued = []
        with mock.patch.object(self.bridge._executor, "submit", side_effect=queued.append):
            self.bridge.setDraft("人工下一句")
            self.bridge.send()
            self.assertFalse(pet.property("utteranceActive"))
            self.assertEqual(pet.property("stateName"), "idle")
            self.assertEqual(pet.property("expressionName"), "think")
        # Restore the real executor before completion schedules diary reads.
        queued.pop(0)()
        self.wait_for(lambda: not self.bridge._pending)
        self.assert_no_errors()

    def test_focused_moods_do_not_show_loading_on_entry_or_ambient_ticks(self):
        from seedbank.util import write_json_atomic
        write_json_atomic(self.pack / "mind" / "mood.json", {"mood": "好奇", "energy": .8})
        self.interface()
        pet = self.find("live2dStage")
        self.assertEqual(pet.property("expressionName"), "idle")
        for mood in ("好奇", "认真", "专注", "思考"):
            with self.subTest(mood=mood):
                self.bridge.snapshot["states"]["mood"]["mood"] = mood
                self.bridge.stateChanged.emit()
                self.qml(self.find("avatarExpressionTimer"), "triggered()")
                self.qml(pet, "play('mood')")
                self.assertEqual(pet.property("expressionName"), "idle")
        self.assert_no_errors()

    def test_background_pulse_and_status_read_do_not_show_loading_expression(self):
        self.interface()
        pet = self.find("live2dStage")
        self.bridge.snapshot["states"]["mood"] = {"mood": "紧张", "energy": .8}
        self.bridge.stateChanged.emit()
        self.assertEqual(pet.property("expressionName"), "nervous")
        queued = []
        with mock.patch.object(self.bridge._executor, "submit", side_effect=queued.append), \
             mock.patch.object(self.bridge.session, "pulse", return_value={"snapshot": self.bridge.snapshot}), \
             mock.patch.object(self.bridge.session, "snapshot", return_value=self.bridge.snapshot):
            for begin in (self.bridge.pulse, self.bridge.loadLifecycle):
                begin()
                self.assertTrue(self.bridge.busy)
                self.assertFalse(self.bridge.avatarThinking)
                self.assertEqual(pet.property("expressionName"), "nervous")
                # A blocked send must not turn a background task into thinking.
                self.bridge.setDraft("人工离线输入")
                self.bridge.send()
                self.assertFalse(self.bridge.avatarThinking)
                self.assertNotEqual(pet.property("expressionName"), "think")
                self.qml(self.find("avatarExpressionTimer"), "triggered()")
                self.assertEqual(pet.property("expressionName"), "nervous")
                queued.pop(0)()
                self.wait_for(lambda: not self.bridge._pending)
                self.assertFalse(self.bridge.avatarThinking)
                self.assertNotEqual(pet.property("expressionName"), "think")
        self.assert_no_errors()

    def test_loading_expression_only_lasts_for_an_accepted_conversation(self):
        from contextlib import nullcontext
        from seedbank.util import write_json_atomic
        write_json_atomic(self.pack / "mind" / "mood.json", {"mood": "好奇", "energy": .8})
        self.interface()
        pet = self.find("live2dStage")
        queued = []
        for fails in (False, True):
            with self.subTest(fails=fails):
                with mock.patch.object(self.bridge._executor, "submit", side_effect=queued.append):
                    self.bridge.setDraft("人工离线输入 " + str(fails))
                    self.bridge.send()
                    self.assertTrue(self.bridge.avatarThinking)
                    self.assertEqual(pet.property("expressionName"), "think")
                    self.assertFalse(self.find("avatarExpressionTimer").property("running"))
                    self.bridge.notify("本地状态提示")
                    self.assertEqual(pet.property("expressionName"), "think")
                # Hold only the initial request. Completion may enqueue a new
                # diary read, which must run on the restored executor.
                failure = mock.patch.object(self.bridge.session, "call", side_effect=RuntimeError("人工失败")) if fails else nullcontext()
                with failure:
                    queued.pop(0)()
                self.wait_for(lambda: not self.bridge._pending)
                self.assertFalse(self.bridge.avatarThinking)
                self.assertEqual(pet.property("expressionName"), "idle")
                self.assertEqual(self.bridge.error, fails)
        self.assert_no_errors()

    def test_date_click_displays_diary_body(self):
        from seedbank.brain import create_stub_brain
        from seedbank.cognition import run_days

        run_days(self.pack, 1, create_stub_brain())
        self.interface()
        self.root.setProperty("page", 1)
        self.bridge.preference("desktop_reduced_motion", True)
        self.bridge.preference("desktop_theme", "night")
        dates = self.find("dateList")
        reader = self.find("diaryReader")
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            for large in (False, True):
                self.bridge.preference("desktop_large_text", large)
                for width, height in ((1520, 780), (1180, 820), (860, 640)):
                    with self.subTest(language=language, large=large, width=width):
                        self.root.setWidth(width)
                        self.root.setHeight(height)
                        QTest.qWait(40)
                        for index, day in ((1, 1), (0, 2)):
                            button = QQmlExpression(QQmlEngine.contextForObject(dates), dates,
                                                    f"itemAtIndex({index})").evaluate()[0]
                            self.assertIsNotNone(button)
                            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
                            QTest.mouseClick(self.root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
                            self.wait_for(lambda: self.bridge.diaryDay == day and not self.bridge._pending)
                            QTest.qWait(15)
                            self.assertIn(f"第 {day:04d} 天", reader.property("text"))
                            origin = reader.mapToScene(QPointF(0, 0))
                            self.assertGreater(reader.width(), 300, f"dates={dates.width()}, reader={reader.width()}, origin={origin}")
                            self.assertLess(dates.width(), 240)
                            self.assertGreater(reader.height(), 30)
                            self.assertTrue(reader.isVisible())
                            self.assertGreaterEqual(origin.x(), 0)
                            self.assertLess(origin.x() + reader.width(), width)
                            self.assertLess(origin.y(), height - 100)
                        capture = os.environ.get("SEEDBANK_DIARY_CAPTURE")
                        if capture and language == "zh_CN" and not large and width == 1520:
                            self.assertTrue(self.root.grabWindow().save(capture))
        self.assert_no_errors()

    def test_background_refresh_clears_finished_loading_notice(self):
        self.open_pack()
        with mock.patch.object(self.bridge.session, "pulse", return_value={"snapshot": self.bridge.snapshot}):
            self.bridge.pulse()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.busy)
        self.assertNotEqual(self.bridge.notice, self.bridge.translate("正在整理，请稍候…"))

    def test_navigation_remains_reachable_in_rail_and_bottom_layouts(self):
        self.interface()
        self.bridge.preference("desktop_reduced_motion", True)
        rail = self.find("navigation")
        for large in (False, True):
            self.bridge.preference("desktop_large_text", large)
            for width, height in ((640, 420), (860, 640), (1280, 840), (1280, 480)):
                self.root.setWidth(width)
                self.root.setHeight(height)
                QTest.qWait(30)
                horizontal = self.root.property("bottomNavigation")
                self.assertGreater(rail.width(), width * 0.8) if horizontal else self.assertLess(rail.width(), width * 0.2)
                previous_end = 0
                for page in range(5):
                    button = self.find("nav-" + str(page))
                    self.assertTrue(button.isVisible())
                    self.assertGreaterEqual(button.height(), 44)
                    point = button.mapToScene(QPointF(0, 0))
                    self.assertGreaterEqual(point.x() if horizontal else point.y(), previous_end)
                    self.assertLessEqual(point.y() + button.height(), self.root.height())
                    rail_origin = rail.mapToScene(QPointF(0, 0))
                    self.assertLessEqual(point.x() + button.width(), rail_origin.x() + rail.width() + 1)
                    previous_end = point.x() + button.width() if horizontal else point.y() + button.height()
                    button.clicked.emit()
                    self.assertEqual(self.root.property("page"), page)
        self.assert_no_errors()

    def test_short_companion_layout_keeps_messages_input_and_single_stage(self):
        self.interface()
        self.bridge.setDraft("窗口变化时保留这段输入。")
        stage, pet = self.find("companionStage"), self.find("live2dStage")
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            for large in (False, True):
                self.bridge.preference("desktop_large_text", large)
                for width, height in ((640, 420), (910, 500), (1280, 840)):
                    with self.subTest(language=language, large=large, size=(width, height)):
                        self.root.setWidth(width)
                        self.root.setHeight(height)
                        QTest.qWait(30)
                        self.assertIs(self.find("live2dStage"), pet)
                        self.assertGreater(stage.width(), 100)
                        self.assertGreater(pet.height(), 60)
                        self.assertGreater(self.find("chatList").height(), 40)
                        self.assertEqual(self.find("composer").property("text"), "窗口变化时保留这段输入。")
                        for name in ("sendMessage", "composerScroll", "avatarWave"):
                            item = self.find(name)
                            origin = item.mapToScene(QPointF(0, 0))
                            self.assertTrue(item.isVisible(), name)
                            self.assertGreaterEqual(origin.x(), 0, name)
                            self.assertGreaterEqual(origin.y(), 0, name)
                            self.assertLessEqual(origin.x() + item.width(), width + 1, name)
                            self.assertLessEqual(origin.y() + item.height(), height + 1, name)
        self.assert_no_errors()

    def test_short_reading_pages_keep_their_scrolling_content_reachable(self):
        self.interface()
        self.bridge.preference("desktop_large_text", True)
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            for width, height in ((640, 420), (910, 500)):
                self.root.setWidth(width)
                self.root.setHeight(height)
                for index, name in ((1, "dateList"), (2, "memoryList"), (3, "lifeList"), (4, "settingsScroll")):
                    with self.subTest(language=language, size=(width, height), page=index):
                        self.root.setProperty("page", index)
                        QTest.qWait(30)
                        item = self.find(name)
                        origin = item.mapToScene(QPointF(0, 0))
                        self.assertTrue(item.isVisible())
                        self.assertGreater(item.height(), 40)
                        self.assertGreaterEqual(origin.y(), 0)
                        self.assertLessEqual(origin.y() + item.height(), self.root.height() + 1)
                        self.assertFalse(self.find("companionStage").isVisible())
        self.assert_no_errors()

    def test_short_memory_tools_preserve_filters_and_search_when_folded(self):
        self.interface()
        self.root.setWidth(640)
        self.root.setHeight(420)
        self.root.setProperty("page", 2)
        QTest.qWait(30)
        toggle = self.find("memoryToolsToggle")
        self.assertTrue(toggle.isVisible())
        self.assertFalse(self.find("memoryToolsScroll").isVisible())
        self.find("memorySearch").setProperty("text", "以前的事情")
        toggle.clicked.emit()
        QTest.qWait(20)
        history = self.find("includeMemoryHistory")
        history.setProperty("checked", True)
        history.toggled.emit()
        self.wait_for(lambda: not self.bridge._pending)
        toggle.clicked.emit()
        QTest.qWait(20)
        self.assertTrue(history.property("checked"))
        self.assertEqual(self.find("memorySearch").property("text"), "以前的事情")
        self.assertIn("1", toggle.property("text"))
        self.assertGreater(self.find("memoryList").height(), 100)
        self.root.setWidth(1280)
        self.root.setHeight(840)
        QTest.qWait(30)
        self.assertTrue(self.find("memoryToolsScroll").isVisible())
        self.assertTrue(history.property("checked"))
        self.assertEqual(self.find("memorySearch").property("text"), "以前的事情")
        self.assert_no_errors()

    def test_short_welcome_keeps_form_scrollable_without_creating_pack(self):
        self.engine = create_engine(self.bridge, test_mode=True)
        self.root = self.engine.rootObjects()[0]
        self.addCleanup(self.dispose)
        self.root.setWidth(640)
        self.root.setHeight(480)
        self.root.show()
        self.bridge.preference("desktop_large_text", True)
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            QTest.qWait(30)
            scroll = self.find("welcomeScroll")
            origin = scroll.mapToScene(QPointF(0, 0))
            self.assertGreater(scroll.height(), 80)
            self.assertGreater(scroll.property("contentHeight"), scroll.height())
            self.assertLessEqual(origin.y() + scroll.height(), self.root.height())
            self.assertTrue(self.find("createPackButton").isVisible())
            self.assertFalse(self.bridge.ready)
        self.assert_no_errors()

    def test_live2d_stage_uses_local_model_without_loading_native_sdk_in_tests(self):
        self.interface()
        from seedbank.live2d_model import DEFAULT_MODEL
        self.assertEqual(self.bridge.avatarModel, str(DEFAULT_MODEL))
        stage = self.find("companionStage")
        pet = self.find("live2dStage")
        self.assertEqual(pet.property("loadStatus"), "disabled")
        self.assertIsNone(self.root.findChild(QObject, "live2dView"))
        self.assertGreater(stage.width(), 180)
        for page in (1, 2, 3, 4):
            self.root.setProperty("page", page)
            QTest.qWait(20)
            self.assertFalse(stage.isVisible())
        self.root.setProperty("page", 0)
        QTest.qWait(20)
        self.assertTrue(stage.isVisible())
        self.assert_no_errors()

    def test_diary_read_failure_shows_retry_and_recovers(self):
        self.interface()
        self.wait_for(lambda: not self.bridge._pending)
        self.root.setProperty("page", 1)
        day = self.bridge.diaryDay
        with mock.patch.object(self.bridge.session, "diary", side_effect=OSError("fixture unreadable diary")):
            self.assertTrue(self.bridge.selectDay(day))
            self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.diaryStatus, "error")
        self.assertEqual(self.bridge.diaryText, "")
        self.assertIn("fixture unreadable", self.bridge.diaryError)
        QTest.qWait(20)
        self.assertTrue(self.find("retryDiary").isVisible())
        self.find("retryDiary").clicked.emit()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.diaryStatus, "ready")
        self.assertEqual(self.bridge.diaryError, "")
        self.assertIn(f"第 {day:04d} 天", self.bridge.diaryText)
        self.assert_no_errors()

    def test_older_diary_failure_cannot_replace_new_selection(self):
        self.open_pack()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.days.replace([{"day": 1, "date": "2026-11-01"}, {"day": 2, "date": "2026-11-02"}])
        jobs = []
        def capture(kind, work, callback, **options):
            jobs.append((callback, options["on_error"]))
            return True
        with mock.patch.object(self.bridge, "submit", side_effect=capture):
            self.bridge.selectDay(1)
            self.assertFalse(self.bridge.selectDay(1))
            self.bridge.selectDay(2)
        jobs[1][0]("Second day")
        jobs[0][1]("Late error from first day")
        jobs[0][0]("Late first day")
        self.assertEqual(self.bridge.diaryDay, 2)
        self.assertEqual(self.bridge.diaryDate, "2026-11-02")
        self.assertEqual(self.bridge.diaryText, "Second day")
        self.assertEqual(self.bridge.diaryStatus, "ready")
        self.assertEqual(self.bridge.diaryError, "")

    def test_missing_diary_is_an_error_and_restoring_fixture_recovers(self):
        self.open_pack()
        self.wait_for(lambda: not self.bridge._pending)
        row = self.bridge.snapshot["days"][0]
        path = self.pack / "life" / row["file"]
        original = path.read_bytes()
        path.unlink()
        try:
            self.bridge.selectDay(row["day"])
            self.wait_for(lambda: not self.bridge._pending)
            self.assertEqual(self.bridge.diaryStatus, "error")
            self.assertEqual(self.bridge.diaryText, "")
        finally:
            path.write_bytes(original)
        self.bridge.selectDay(row["day"])
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.diaryStatus, "ready")

    def test_switching_diary_returns_reader_to_top(self):
        self.interface()
        self.wait_for(lambda: not self.bridge._pending)
        self.root.setProperty("page", 1)
        self.bridge.days.replace([{"day": 1, "date": "2026-11-01"}, {"day": 2, "date": "2026-11-02"}])
        with mock.patch.object(self.bridge.session, "diary", side_effect=lambda day: "# Diary\n\n" + ("A long diary paragraph.\n\n" * 200 if day == 1 else "A short entry.")):
            self.bridge.selectDay(1)
            self.wait_for(lambda: not self.bridge._pending)
            QTest.qWait(30)
            scroll = self.find("diaryScroll")
            flick = scroll.property("contentItem")
            flick.setProperty("contentY", 400)
            self.assertGreater(flick.property("contentY"), 0)
            self.bridge.selectDay(2)
            self.wait_for(lambda: not self.bridge._pending)
            QTest.qWait(30)
        self.assertAlmostEqual(flick.property("contentY"), 0)
        self.assertIn("A short entry.", self.find("diaryReader").property("text"))
        self.assert_no_errors()

    def test_long_draft_scrolls_and_survives_navigation(self):
        self.interface()
        self.root.setWidth(860)
        self.root.setHeight(640)
        self.bridge.preference("desktop_large_text", True)
        composer = self.find("composer")
        draft = "这是一段保留在输入框的长消息。\n" * 80
        composer.setProperty("text", draft)
        QTest.qWait(40)
        scroll = self.find("composerScroll")
        self.assertTrue(scroll.property("clip"))
        self.assertGreater(scroll.property("contentHeight"), scroll.height())
        self.assertLess(scroll.height(), self.root.height() * 0.3)
        self.root.setProperty("page", 1)
        self.root.setProperty("page", 0)
        self.assertEqual(composer.property("text"), draft)
        self.assertEqual(self.bridge.draft, draft)
        composer.setProperty("text", "长" * 2001)
        self.assertFalse(self.find("sendMessage").isEnabled())
        composer.setProperty("text", "😀" * 1200)
        self.assertTrue(self.find("sendMessage").isEnabled())
        self.assert_no_errors()

    def test_reselecting_same_model_reloads_without_changing_identity(self):
        from PySide6.QtCore import QUrl
        self.open_pack()
        self.wait_for(lambda: not self.bridge._pending)
        identity = (self.pack / "birth.json").read_bytes()
        model_dir = Path(self.workspace.name) / "avatar"
        model_dir.mkdir()
        (model_dir / "body.moc3").write_bytes(b"fixture; never rendered")
        (model_dir / "texture.png").write_bytes(b"fixture; never rendered")
        model = model_dir / "fixture.model3.json"
        model.write_text(json.dumps({"Version": 3, "FileReferences": {
            "Moc": "body.moc3", "Textures": ["texture.png"]}}), encoding="utf-8")
        requests = []
        self.bridge.avatarReloadRequested.connect(lambda: requests.append(True))
        for _ in range(2):
            self.bridge.selectAvatarModel(QUrl.fromLocalFile(str(model)).toString())
        self.assertEqual(len(requests), 2)
        self.assertEqual(self.bridge.avatarModel, str(model))
        self.assertEqual(identity, (self.pack / "birth.json").read_bytes())

    def test_scrollbars_hide_when_unneeded_and_fill_scroll_panels(self):
        self.interface()
        self.bridge.preference("desktop_reduced_motion", True)
        QTest.qWait(180)
        footer = self.root.grabWindow().copy(0, self.root.height() - 40, self.root.width(), 40)
        for page in (0, 1, 4):
            self.root.setProperty("page", page)
            QTest.qWait(30)
            for item in self.visual_items():
                if "SlimBar" not in item.metaObject().className() or not item.isVisible():
                    continue
                self.assertGreater(item.height(), 50)
                if item.property("size") >= 1:
                    self.assertEqual(item.property("contentItem").opacity(), 0)
        self.assertTrue(self.find("settingsScroll").property("clip"))
        self.assertEqual(self.root.grabWindow().copy(0, self.root.height() - 40, self.root.width(), 40), footer)

    def test_welcome_scroll_reaches_creation_at_all_languages_and_sizes(self):
        self.engine = create_engine(self.bridge, test_mode=True)
        self.root = self.engine.rootObjects()[0]
        self.addCleanup(self.dispose)
        self.show_root()
        self.bridge.preference("desktop_reduced_motion", True)
        self.bridge.preference("desktop_large_text", True)
        scroll = self.find("welcomeScroll")
        button = self.find("createPackButton")
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            for width, height in ((860, 640), (1180, 820)):
                self.root.setWidth(width)
                self.root.setHeight(height)
                QTest.qWait(40)
                flickable = scroll.property("contentItem")
                flickable.setProperty("contentY", max(0, flickable.property("contentHeight") - flickable.height()))
                QTest.qWait(20)
                position = button.mapToScene(QPointF(0, 0))
                self.assertGreaterEqual(position.x(), 0)
                self.assertGreaterEqual(position.y(), 0)
                self.assertLessEqual(position.x() + button.width(), width)
                self.assertLessEqual(position.y() + button.height(), height)
                for item in scroll.findChildren(QQuickItem):
                    if "SlimBar" in item.metaObject().className() and item.property("size") < 1:
                        self.assertGreater(item.height(), 50)
        self.assert_no_errors()

    def test_models_skip_equal_snapshots_and_append_without_reset(self):
        rows = Rows()
        reset = mock.Mock()
        rows.modelReset.connect(reset)
        self.assertTrue(rows.replace([{"text": "one"}]))
        self.assertFalse(rows.replace([{"text": "one"}]))
        self.assertTrue(rows.replace([{"text": "one"}, {"text": "two"}]))
        reset.assert_not_called()
        self.assertEqual(rows.rowCount(), 2)
        rows.replace([{"text": "new"}, {"text": "one"}, {"text": "two"}])
        rows.replace([{"text": "new"}, {"text": "two"}])
        reset.assert_not_called()

    def test_new_chat_before_observations_preserves_reading_position(self):
        self.interface()
        snapshot = deepcopy(self.bridge.snapshot)
        snapshot["transcript"] = [{"who": "主人", "text": f"消息 {index}：" + "你好。" * 30} for index in range(80)]
        self.bridge.apply_snapshot(snapshot)
        messages = self.find("chatList")
        QTest.qWait(40)
        messages.setProperty("followTail", False)
        context = QQmlEngine.contextForObject(messages)
        QQmlExpression(context, messages, "positionViewAtIndex(20, ListView.Beginning)").evaluate()
        QTest.qWait(40)
        visible_index = QQmlExpression(context, messages, "indexAt(10, contentY + 10)")
        visible_offset = QQmlExpression(context, messages, "itemAt(10, contentY + 10).y - contentY")
        saved_index = visible_index.evaluate()[0]
        saved_offset = visible_offset.evaluate()[0]
        self.assertEqual(saved_index, 20)
        resets = mock.Mock()
        self.bridge.chat.modelReset.connect(resets)
        snapshot = deepcopy(snapshot)
        snapshot["transcript"].append({"who": "主人", "text": "新消息"})
        self.bridge.apply_snapshot(snapshot)
        QTest.qWait(40)
        resets.assert_not_called()
        self.assertEqual(visible_index.evaluate()[0], saved_index)
        self.assertAlmostEqual(visible_offset.evaluate()[0], saved_offset, delta=3)

    def test_revision_only_does_not_reset_models(self):
        self.open_pack()
        resets = mock.Mock()
        for model in (self.bridge.chat, self.bridge.days, self.bridge.memories, self.bridge.life):
            model.modelReset.connect(resets)
        snapshot = deepcopy(self.bridge.snapshot)
        snapshot["revision"] += 1
        self.bridge.apply_snapshot(snapshot)
        resets.assert_not_called()
        self.assertFalse(self.bridge._pending)

    def test_offline_chat_keeps_newer_draft(self):
        self.open_pack()
        self.bridge.setDraft("今天见到了一束光。")
        self.bridge.send()
        self.assertTrue(self.bridge.busy)
        self.bridge.setDraft("还没发出的下一句")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.draft, "还没发出的下一句")
        self.assertGreater(self.bridge.chat.rowCount(), 0)
        self.assertFalse(self.bridge.error)

    def test_send_clears_only_sent_draft(self):
        self.interface()
        composer = self.find("composer")
        composer.setProperty("text", "你好，我来看你了。")
        self.bridge.send()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.draft, "")
        self.assertEqual(composer.property("text"), "")
        self.assert_no_errors()

    def test_memory_filter_and_virtualized_thousand_rows(self):
        self.interface()
        snapshot = deepcopy(self.bridge.snapshot)
        snapshot["memories"] = [{"id": str(index), "day": 1, "text": f"记忆 {index}：" + "今天慢慢来。" * 12,
                                  "forgotten": index == 0} for index in range(1000)]
        self.bridge.apply_snapshot(snapshot)
        self.root.setProperty("page", 2)
        QTest.qWait(80)
        self.assertEqual(self.bridge.memories.rowCount(), 999)
        objects = list(self.visual_items())
        self.assertLess(len(objects), 1500)
        self.bridge.filterMemories("记忆 0：", True)
        self.assertEqual(self.bridge.memories.rowCount(), 1)
        self.assert_no_errors()

    def test_settings_all_sections_and_drafts_survive_navigation(self):
        self.interface()
        self.root.setProperty("page", 4)
        settings = self.find("settingsPage")
        for section in range(4):
            settings.setProperty("section", section)
            QTest.qWait(30)
        self.bridge.editSetting("model", "draft-model")
        self.root.setProperty("page", 0)
        self.root.setProperty("page", 4)
        settings.setProperty("section", 1)
        QTest.qWait(20)
        self.assertEqual(self.bridge.form["model"], "draft-model")
        self.assertTrue(self.bridge.dirty)
        self.assert_no_errors()

    def test_language_choice_ignores_wheel(self):
        self.interface()
        self.root.setProperty("page", 4)
        choice = self.find("languageChoice")
        self.assertFalse(choice.property("wheelEnabled"))
        self.assertEqual(self.bridge.preferences["language"], "zh_CN")
        self.bridge.preference("language", "ja_JP")
        self.assertEqual(self.bridge.notice, self.bridge.translate("今天也一起慢慢来。"))
        self.assertEqual(choice.property("currentIndex"), 2)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_api_key_is_masked_and_saved_outside_life_pack(self):
        from seedbank.settings import PRESETS, load_settings
        from seedbank.brain import _key_for, load_brain_config
        self.interface()
        self.root.setProperty("page", 4)
        self.find("settingsPage").setProperty("section", 1)
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.applyPreset(next(i for i, row in enumerate(PRESETS) if row["label"] == "OpenAI（API Key）"))
        self.app.processEvents()
        field = self.find("field-API Key")
        self.assertTrue(field.isVisible())
        # Keep the enum comparison in QML: PySide cannot convert this private
        # QQuickTextInput enum when it is read through QObject.property().
        self.assertTrue(self.qml(field, "echoMode === TextInput.Password"))
        key = "seedbank-artificial-UI-key"
        field.setProperty("text", key)
        field.textEdited.emit()
        self.assertTrue(self.bridge.dirty)
        self.assertNotIn(key, str(self.bridge.form))
        with mock.patch("seedbank.quick.bridge.test_brain", side_effect=AssertionError("No connection request")) as transport:
            self.bridge.testConnection()
            self.assertIn("先保存", self.bridge.notice)
            self.bridge.saveSettings()
            self.wait_for(lambda: not self.bridge._pending)
            transport.assert_not_called()
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(self.bridge.apiKeyDraft, "")
        self.app.processEvents()
        self.assertEqual(field.property("text"), "")
        self.assertEqual(_key_for(load_brain_config(self.pack)), key)
        self.assertNotIn(key, str(load_settings(self.pack)))
        self.assertFalse(self.bridge.dirty)
        self.bridge.editApiKey(key + "-replacement")
        self.assertTrue(self.bridge.dirty)
        self.assert_no_errors()

    @unittest.skipUnless(os.name == "nt", "Windows key entry UI")
    def test_api_key_draft_clears_when_provider_changes(self):
        from seedbank.settings import PRESETS
        self.interface()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.applyPreset(next(i for i, row in enumerate(PRESETS) if row["label"] == "OpenAI（API Key）"))
        self.bridge.editApiKey("seedbank-artificial-key")
        self.bridge.editSetting("base_url", "https://example.invalid/v1")
        self.assertEqual(self.bridge.apiKeyDraft, "")
        self.assertEqual(self.bridge.form["api_key_ref"], "")
        self.bridge.editApiKey("seedbank-artificial-key")
        self.bridge.applyPreset(next(i for i, row in enumerate(PRESETS) if row["adapter"] == "codex"))
        self.assertFalse(self.bridge.remoteApi)
        self.assertEqual(self.bridge.apiKeyDraft, "")
        self.assert_no_errors()

    def test_provider_presets_update_compatibility_and_clear_old_credentials(self):
        from seedbank.settings import PRESETS
        self.interface()
        self.wait_for(lambda: not self.bridge._pending)
        self.root.setProperty("page", 4)
        self.find("settingsPage").setProperty("section", 1)
        for provider in ("gemini", "qwen", "ark", "kimi", "zhipu", "minimax", "siliconflow", "openrouter", "qianfan", "hunyuan"):
            self.bridge._form.update(api_key_ref="a" * 32, vision_model="old-provider-vision")
            self.bridge.editApiKey("artificial-secret")
            self.bridge.applyPreset(next(i for i, p in enumerate(PRESETS) if p.get("provider") == provider))
            self.app.processEvents()
            self.assertEqual(self.bridge.form["api_key_ref"], "")
            self.assertEqual(self.bridge.apiKeyDraft, "")
            self.assertEqual(self.bridge.form["vision_model"], "")
            self.assertEqual(self.bridge.form["response_format_mode"], "prompt")
            self.assertEqual(self.bridge.form["temperature_mode"], "default")
            self.assertTrue(self.bridge.providerHint)
            with self.assertRaises(ValueError):
                self.bridge.validated_form()
            self.bridge.editSetting("model", "artificial-model")
            self.assertEqual(self.bridge.validated_form()["provider"], provider)
            self.assert_no_errors()

    def test_provider_options_show_in_each_language_without_calls(self):
        from seedbank.settings import PRESETS
        self.interface()
        self.wait_for(lambda: not self.bridge._pending)
        self.root.setProperty("page", 4)
        self.find("settingsPage").setProperty("section", 1)
        self.bridge.applyPreset(next(i for i, p in enumerate(PRESETS) if p.get("provider") == "gemini"))
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            self.app.processEvents()
            temperature = self.find("field-" + self.bridge.translate("温度（0–2）"))
            self.assertFalse(temperature.isVisible())
            self.bridge.editSetting("temperature_mode", "custom")
            self.app.processEvents()
            self.assertTrue(temperature.isVisible())
            self.bridge.editSetting("temperature_mode", "default")
            self.assert_no_errors()

    def test_codex_settings_draft_fields_and_usage_do_not_contact_model(self):
        from seedbank.settings import PRESETS, load_settings
        with mock.patch("seedbank.codex_transport.subprocess.Popen", side_effect=AssertionError("No model process in settings")) as process:
            self.interface()
            original = load_settings(self.pack)
            self.root.setProperty("page", 4)
            self.find("settingsPage").setProperty("section", 1)
            self.app.processEvents()
            self.wait_for(lambda: not self.bridge._pending)
            preset = next(index for index, row in enumerate(PRESETS) if row["adapter"] == "codex")
            self.bridge.applyPreset(preset)
            for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
                self.bridge.preference("language", language)
                self.root.setWidth(860)
                self.root.setHeight(640)
                self.app.processEvents()
                limit = self.find("field-" + self.bridge.translate("每轮活动最多调用（1–3）"))
                self.assertTrue(limit.isVisible())
                self.assertGreater(limit.width(), 100)
                self.assertEqual(limit.property("text"), "2")
                for caption in ("接口地址", "密钥环境变量名", "温度（0–2）", "视觉模型（可留空）"):
                    name = "field-" + self.bridge.translate(caption)
                    self.assertFalse(any(item.objectName() == name and item.isVisible() for item in self.visual_items()))
                refresh = next(item for item in self.visual_items() if item.isVisible()
                               and item.property("text") == self.bridge.translate("刷新本机 GPT 用量")
                               and hasattr(item, "clicked"))
                refresh.clicked.emit()
                self.assertTrue(self.bridge.codexUsage)
                self.assertEqual(load_settings(self.pack), original)
                self.assertFalse(self.bridge._pending)
                self.assert_no_errors()
            process.assert_not_called()

    def test_codex_limit_edit_save_and_reopen_preserves_identity_without_calls(self):
        from seedbank.settings import PRESETS, load_settings
        with mock.patch("seedbank.codex_transport.subprocess.Popen", side_effect=AssertionError("No model process while saving")) as process:
            self.interface()
            birth = (self.pack / "birth.json").read_bytes()
            self.root.setProperty("page", 4)
            self.find("settingsPage").setProperty("section", 1)
            self.app.processEvents()
            self.wait_for(lambda: not self.bridge._pending)
            self.bridge.applyPreset(next(i for i, row in enumerate(PRESETS) if row["adapter"] == "codex"))
            self.app.processEvents()
            limit = self.find("field-每轮活动最多调用（1–3）")
            limit.setProperty("text", "1")
            limit.textEdited.emit()
            self.assertEqual(self.bridge.form["codex_max_calls"], "1")
            save = next(item for item in self.visual_items() if item.isVisible()
                        and item.property("text") == "保存设置" and hasattr(item, "clicked"))
            save.clicked.emit()
            self.wait_for(lambda: not self.bridge._pending and self.bridge._saved.get("adapter") == "codex")
            self.assertFalse(self.bridge.error, self.bridge.notice)
            self.assertFalse(self.bridge.conversationDirty, {
                key: (self.bridge.form.get(key), self.bridge._saved.get(key))
                for key in self.bridge.form.keys() | self.bridge._saved.keys()
                if self.bridge.form.get(key) != self.bridge._saved.get(key)})
            self.assertEqual(load_settings(self.pack)["adapter"], "codex")
            self.assertEqual(load_settings(self.pack)["codex_max_calls"], 1)
            self.assertEqual((self.pack / "birth.json").read_bytes(), birth)
            self.bridge.applyPreset(next(i for i, row in enumerate(PRESETS) if row["adapter"] == "anthropic"))
            self.app.processEvents()
            self.assertTrue(self.find("field-接口地址").isVisible())
            self.assertEqual(load_settings(self.pack)["adapter"], "codex")
            self.assertTrue(self.bridge.conversationDirty)
            self.bridge.shutdown()
            reopened = Bridge(timers=False, brain_override="stub")
            self.addCleanup(reopened.shutdown)
            reopened.openPack(str(self.pack))
            self.wait_for(lambda: reopened.ready and not reopened._pending)
            self.assertEqual(reopened.form["codex_max_calls"], 1)
            self.assertEqual(reopened.form["adapter"], "codex")
            process.assert_not_called()
            self.assert_no_errors()

    def test_codex_invalid_limit_keeps_saved_settings_and_draft(self):
        from seedbank.settings import PRESETS, load_settings
        self.interface()
        original = load_settings(self.pack)
        self.root.setProperty("page", 4)
        self.find("settingsPage").setProperty("section", 1)
        # Opening this section reads the local continuity report asynchronously.
        # Wait for that existing job before exercising the enabled Save button.
        self.app.processEvents()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.applyPreset(next(i for i, row in enumerate(PRESETS) if row["adapter"] == "codex"))
        self.app.processEvents()
        limit = self.find("field-每轮活动最多调用（1–3）")
        save = next(item for item in self.visual_items() if item.isVisible()
                    and item.property("text") == "保存设置" and hasattr(item, "clicked"))
        for invalid in ("0", "4", "many"):
            limit.setProperty("text", invalid)
            limit.textEdited.emit()
            save.clicked.emit()
            self.assertTrue(self.bridge.error)
            self.assertFalse(self.bridge._pending)
            self.assertEqual(self.bridge.form["codex_max_calls"], invalid)
            self.assertEqual(load_settings(self.pack), original)
        self.assert_no_errors()

    def test_continuity_panel_is_explicit_and_stub_is_not_a_pass(self):
        self.interface()
        self.root.setProperty("page", 4)
        self.find("settingsPage").setProperty("section", 1)
        self.wait_for(lambda: not self.bridge._pending)
        self.find("continuityCapture")
        self.assertFalse(self.bridge.continuity.get("has_baseline"))
        self.assertTrue(self.bridge.assessContinuity("capture"))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.continuity["capture_reason"], "stub")
        self.assertTrue(self.bridge.assessContinuity("check"))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertIsNone(self.bridge.continuity["report"]["passed"])
        self.assertIn("离线模式未评估", self.bridge.continuityText)
        self.bridge.editSetting("model", "unsaved")
        self.assertFalse(self.bridge.assessContinuity("check"))
        self.assertFalse(self.find("continuityCheck").property("enabled"))
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            self.bridge.preference("desktop_large_text", True)
            self.root.setWidth(860)
            self.app.processEvents()
            panel = self.find("continuityPanel")
            result = self.find("continuityResult")
            self.assertGreater(result.height(), 0)
            self.assertLessEqual(result.width(), panel.width())
            self.assert_no_errors()
    def test_semantic_panel_default_is_local_and_explicit_index_uses_fake_service(self):
        with mock.patch("seedbank.semantic._request") as request:
            self.interface()
            self.root.setProperty("page", 4)
            self.find("settingsPage").setProperty("section", 2)
            self.wait_for(lambda: not self.bridge._pending)
            self.find("semanticPanel")
            self.assertFalse(self.bridge.form["semantic_enabled"])
            self.assertFalse(self.find("semanticIndex").property("enabled"))
            request.assert_not_called()
            self.bridge.editSetting("semantic_enabled", True)
            self.bridge.editSetting("semantic_model", "fixture-embedding")
            self.assertFalse(self.bridge.semanticIndex("index"))
            self.bridge.saveSettings()
            self.wait_for(lambda: not self.bridge._pending)
            request.assert_not_called()
            request.side_effect = lambda cfg, texts: {"model": "fixture-embedding", "data": [
                {"index": i, "embedding": [1, 0, 0]} for i, _ in enumerate(texts)]}
            self.assertTrue(self.bridge.semanticIndex("index"))
            self.wait_for(lambda: not self.bridge._pending)
            self.assertGreater(self.bridge.semantic["indexed_chunks"], 0)
            for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
                self.bridge.preference("language", language)
                self.bridge.preference("desktop_large_text", True)
                self.root.setWidth(860)
                self.app.processEvents()
                panel = self.find("semanticPanel")
                progress = self.find("semanticProgress")
                self.assertGreater(progress.height(), 0)
                self.assertLessEqual(progress.width(), panel.width())
                self.assert_no_errors()

    def test_keyboard_focus_leaves_hidden_pages_and_search_shortcut(self):
        self.interface()
        composer = self.find("composer")
        composer.forceActiveFocus()
        expression = QQmlExpression(QQmlEngine.contextForObject(self.root), self.root, "navigate(2)")
        expression.evaluate()
        self.app.processEvents()
        self.assertFalse(composer.hasActiveFocus())
        for _ in range(24):
            QTest.keyClick(self.root, Qt.Key.Key_Tab)
            focused = self.root.activeFocusItem()
            self.assertIsNotNone(focused)
            self.assertTrue(focused.isVisible())
        self.assert_no_errors()

    def test_invalid_settings_do_not_write_or_start_jobs(self):
        self.open_pack()
        self.bridge.editSetting("temperature", "nan")
        self.bridge.saveSettings()
        self.assertTrue(self.bridge.error)
        self.assertFalse(self.bridge._pending)
        self.bridge.editSetting("temperature", "0.8")
        self.bridge.editSetting("daily_max", "0")
        self.bridge.saveSettings()
        self.assertTrue(self.bridge.error)

    def test_offline_save_and_qq_validation(self):
        self.open_pack()
        self.bridge.editSetting("daily_max", "12")
        self.bridge.saveSettings()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.form["daily_max"], 12)
        self.assertFalse(self.bridge.dirty)
        self.bridge.toggleQQ()
        self.assertTrue(self.bridge.error)
        self.assertFalse(self.bridge.qqRunning)

    def test_qq_save_is_clean_and_preserves_edits_during_save(self):
        self.open_pack()
        self.bridge.editQQ("owner", "12345678")
        self.bridge.saveQQ()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.dirty)
        self.bridge.editQQ("owner", "22345678")
        self.bridge.saveQQ()
        self.bridge.editQQ("owner", "32345678")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.qqForm["owner"], "32345678")
        self.assertTrue(self.bridge.dirty)

    def test_discovery_and_external_connections_are_mocked(self):
        self.open_pack()
        with mock.patch("seedbank.quick.bridge.localmodels.discover", return_value=[{"label": "Local", "base_url": "http://localhost:1234/v1", "models": ["demo"]}]):
            self.bridge.discover()
            self.wait_for(lambda: not self.bridge._pending)
        self.bridge.chooseModel(0)
        self.assertEqual(self.bridge.form["model"], "demo")
        with mock.patch("seedbank.quick.bridge.test_brain", return_value=(True, "ok")) as connection:
            self.bridge.testConnection()
            self.wait_for(lambda: not self.bridge._pending)
            connection.assert_called_once()
        self.bridge.editQQ("owner", "12345678")
        with mock.patch.object(self.bridge.session, "start_qq", return_value={"running": True}) as start:
            self.bridge.toggleQQ()
            self.wait_for(lambda: not self.bridge._pending)
            start.assert_called_once()

    def test_appearance_actions_do_not_change_autostart_during_tests(self):
        self.open_pack()
        with mock.patch("seedbank.quick.bridge.set_autostart", return_value={"ok": True}) as startup:
            self.bridge.preference("autostart", True)
            startup.assert_called_once()
        self.bridge.preference("always_on_top", True)
        self.assertTrue(self.bridge.preferences["always_on_top"])

    def test_photo_and_observation_update(self):
        self.open_pack()
        picture = Path(__file__).parent / "testdata" / "bright-warm.png"
        from PySide6.QtCore import QUrl
        self.bridge.sendPhoto(QUrl.fromLocalFile(str(picture)).toString())
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error)
        self.assertTrue(self.bridge.chat.rows)

    def test_forget_memory_updates_model_without_destroying_page(self):
        self.interface()
        self.bridge.setDraft("我喜欢下雨天和蓝色。")
        self.bridge.send()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.snapshot["memories"])
        identifier = self.bridge.snapshot["memories"][0]["id"]
        page = self.find("memoryPage")
        self.bridge.forget(identifier)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(next(row for row in self.bridge.snapshot["memories"] if row["id"] == identifier)["forgotten"])
        self.assertIs(self.find("memoryPage"), page)
        self.assert_no_errors()

    def test_fact_dialog_adds_and_resolves_without_model_requests(self):
        from seedbank import facts
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("factsDialog")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.editFact("add", {"subject": "owner", "aspect": "居住地", "value": "杭州"})
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.editFact("add", {"subject": "owner", "aspect": "居住地", "value": "成都"})
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        group = self.bridge.facts["groups"][0]
        self.assertEqual(group["status"], "conflict")
        chosen = next(r for r in group["claims"] if r["value"] == "成都")
        self.bridge.editFact("resolve", {"slot": group["id"], "expected": group["expected"],
                             "selected": chosen["id"], "reason": "搬家", "change_type": "change", "effective_on": "2026-10-31"})
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(facts.listing(self.pack)["groups"][0]["status"], "reported")
        self.assertEqual(dialog.property("editing"), "")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_fact_correction_dialog_retires_old_derived_reply_and_keeps_source(self):
        from seedbank import experience, facts
        from seedbank.memory_state import MemoryPolicy
        old = facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "杭州"})["record"]
        facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "成都"})
        source_id = old["evidence"][0]["id"]
        reply = experience.record(self.pack, kind="conversation", text="UI_OLD_INTERPRETATION_592", day=1,
            source="mind/experiences.jsonl", actor="fixture",
            metadata={"runner": "fixture", "context_dependencies": [source_id]})
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("factsDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'start("resolve", bridge.facts.groups[0], bridge.facts.groups[0].claims.filter(function(r) { return r.value === "成都" })[0].id)').evaluate()
        self.assertEqual(dialog.property("changeType"), "correction")
        self.find("factReason").setProperty("text", "核对后确认原来记错")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(dialog.property("editing"), "")
        self.assertFalse(MemoryPolicy.load(self.pack).allows(reply))
        source = next(r for r in experience.read(self.pack) if r["id"] == source_id)
        self.assertTrue(MemoryPolicy.load(self.pack).allows(source))
        self.assertEqual(facts.listing(self.pack)["groups"][0]["claims"][0]["value"], "成都")
        self.assert_no_errors()

    def test_mistaken_extraction_editor_keeps_draft_after_refresh_failure_and_reuses_receipt(self):
        from seedbank import experience, facts
        event = experience.record(self.pack, kind="conversation", text="我不住杭州，也养猫。", day=1,
                                  source="mind/experiences.jsonl", actor="user")
        facts.apply_proposals(self.pack, [{"subject": "owner", "aspect": "居住地", "value": "杭州", "quote": event["text"]}],
                              event=event, allowed_entities=["owner"], runner="fixture")
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("factsDialog")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        group = self.bridge.facts["groups"][0]
        claim = group["claims"][0]
        expression = "start('retract', " + json.dumps(group) + ", " + json.dumps(claim) + ")"
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, expression).evaluate()
        self.find("factReason").setProperty("text", "没有保留否定")
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=RuntimeError("fixture refresh failure")):
            QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "save()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
        request_id = self.bridge._fact_request_id
        self.assertTrue(request_id)
        self.assertTrue(self.bridge.error)
        self.assertEqual(dialog.property("editing"), "retract")
        self.assertEqual(self.find("factReason").property("text"), "没有保留否定")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(dialog.property("editing"), "")
        self.assertEqual(len([r for r in facts.read(self.pack) if r["kind"] == "retract"]), 1)
        self.assertEqual(self.bridge.facts["groups"], [])
        self.bridge.loadFacts("", True, 0)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.facts["groups"][0]["history"][0]["retracted"])
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_fact_time_dialog_keeps_past_value_separate_from_current_value(self):
        from seedbank import facts
        facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "杭州", "starts_on": "2020-01-01"})
        chosen = facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "成都"})["record"]
        group = facts.listing(self.pack)["groups"][0]
        facts.perform(self.pack, "resolve", {"slot": group["id"], "expected": group["expected"], "selected": chosen["id"],
                      "reason": "搬家", "change_type": "change", "effective_on": "2021-01-01"})
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("factTimeDialog")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.loadFactTime("居住地", "2020-06-01", 0, "", 0))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(self.bridge.factTime["groups"][0]["temporal"]["values"], ["杭州"])
        self.assertTrue(self.bridge.loadFactTime("居住地", "2021-06-01", 0, "", 0))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.factTime["groups"][0]["temporal"]["values"], ["成都"])
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assertTrue(self.bridge.loadFactTime("居住地", "2020-02-30", 0, "", 0))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(self.bridge.factTime, {})
        self.assert_no_errors()

    def test_fact_date_editor_preserves_draft_after_refresh_failure_and_reuses_receipt(self):
        from seedbank import fact_dates, facts, requests
        row = facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "杭州"})["record"]
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("factDateDialog")
        expression = "openFor(" + json.dumps(row["id"]) + ")"
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, expression).evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        details = self.bridge.factDate
        data = {"target": row["id"], "target_hash": details["target_hash"], "expected": details["expected"],
                "date": "2020-01-01", "reason": "用户补充日期"}
        self.find("amendFactDate").setProperty("text", data["date"])
        self.find("amendFactDateReason").setProperty("text", data["reason"])
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
            self.bridge.saveFactDate(data)
            self.wait_for(lambda: not self.bridge._pending)
        identifier = self.bridge._fact_date_request_id
        self.assertTrue(self.bridge.error)
        self.assertEqual(requests.get(self.pack, identifier)["status"], "complete")
        self.assertEqual(self.find("amendFactDateReason").property("text"), data["reason"])
        self.bridge.saveFactDate(data)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(len(fact_dates.detail(self.pack, row["id"])["versions"]), 1)
        self.assertEqual(self.bridge.factDate["date"], "2020-01-01")
        self.assertEqual(self.bridge._fact_date_request_id, "")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_fact_date_editor_rejects_an_obsolete_version_without_losing_input(self):
        from seedbank import fact_dates, facts
        row = facts.perform(self.pack, "add", {"subject": "owner", "aspect": "居住地", "value": "杭州"})["record"]
        self.interface()
        self.root.setProperty("page", 2)
        self.bridge.loadFactDate(row["id"])
        self.wait_for(lambda: not self.bridge._pending)
        details = self.bridge.factDate
        stale = {"target": row["id"], "target_hash": details["target_hash"], "expected": details["expected"],
                 "date": "2020-01-01", "reason": "旧页面的输入"}
        fact_dates.perform(self.pack, {**stale, "date": "2021-01-01", "reason": "其他窗口的新依据"})
        self.find("amendFactDateReason").setProperty("text", stale["reason"])
        self.bridge.saveFactDate(stale)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(self.find("amendFactDateReason").property("text"), stale["reason"])
        self.assertEqual(fact_dates.detail(self.pack, row["id"])["date"], "2021-01-01")
        self.assert_no_errors()

    def test_archive_restore_keeps_current_pack_and_shows_four_languages(self):
        from seedbank import backup
        saved = backup.create(self.pack)
        destination = Path(self.workspace.name) / "restored.life"
        before = (self.pack / "birth.json").read_bytes()
        self.interface()
        self.bridge.showArchiveManager()
        dialog = self.find("archiveDialog")
        self.find("archiveFile").setProperty("text", saved["file"])
        self.bridge.inspectBackup(saved["file"])
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(self.bridge.archiveState["info"]["contents_verified"])
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
            self.assertNotIn("{count}", self.find("archiveFileCount").property("text"))
        self.find("archiveDestination").setProperty("text", str(destination))
        self.bridge.restoreBackup(saved["file"], str(destination))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(self.bridge.pack, self.pack)
        self.assertEqual((destination / "birth.json").read_bytes(), before)
        self.assertTrue(self.bridge.archiveState["result"]["contents_verified"])
        self.assertFalse(self.bridge.archiveState["running"])
        self.assert_no_errors()

    def test_archive_existing_destination_keeps_inputs_and_original_directory(self):
        from seedbank import backup
        saved = backup.create(self.pack)
        self.interface()
        self.bridge.showArchiveManager()
        self.find("archiveFile").setProperty("text", saved["file"])
        self.find("archiveDestination").setProperty("text", str(self.pack))
        self.bridge.inspectBackup(saved["file"])
        self.wait_for(lambda: not self.bridge._pending)
        before = (self.pack / "birth.json").read_bytes()
        self.bridge.restoreBackup(saved["file"], str(self.pack))
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual((self.pack / "birth.json").read_bytes(), before)
        self.assertEqual(self.find("archiveDestination").property("text"), str(self.pack))
        self.assertFalse(self.bridge.archiveState["running"])
        self.assert_no_errors()

    def test_archive_cancellation_is_requested_through_worker_event(self):
        from threading import Event
        from seedbank.backup import BackupCancelled
        self.interface()
        entered = Event()
        def waiting(pack, *, progress, cancel):
            entered.set()
            if not cancel.wait(3):
                raise AssertionError("Cancellation was not delivered")
            raise BackupCancelled("fixture")
        with mock.patch("seedbank.backup.create", side_effect=waiting):
            self.bridge.backupNow()
            self.wait_for(entered.is_set)
            self.bridge.cancelArchive()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(self.bridge.archiveState["running"])
        self.assertEqual(self.bridge.archiveState["result"], {})
        self.assert_no_errors()

    def test_media_intake_retry_after_refresh_failure_uses_saved_request(self):
        from PySide6.QtCore import QUrl
        from seedbank import media_archive, requests
        source = Path(self.workspace.name) / "incoming.png"
        source.write_bytes((Path(__file__).parent / "testdata/bright-warm.png").read_bytes())
        self.interface()
        with mock.patch("seedbank.cognition.vision_translate", return_value={"ok": True, "text": "图中有一片光。", "provider": "fake", "model": "fixture"}) as vision:
            with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
                self.bridge.sendPhoto(QUrl.fromLocalFile(str(source)).toString())
                self.wait_for(lambda: not self.bridge._pending)
            identifier = self.bridge._incoming_media_request_id
            self.assertTrue(identifier)
            self.assertTrue(self.bridge.error)
            self.assertEqual(requests.get(self.pack, identifier)["status"], "complete")
            source.unlink()
            self.bridge.retryMediaInput()
            self.wait_for(lambda: not self.bridge._pending)
            self.assertFalse(self.bridge.error, self.bridge.notice)
            self.assertEqual(vision.call_count, 1)
        self.assertEqual(len(media_archive.read(self.pack)), 1)
        self.assertFalse(self.bridge.mediaInputPending)

    def test_media_intake_queue_can_cancel_without_losing_original(self):
        from PySide6.QtCore import QUrl
        from seedbank import media_archive, requests
        from seedbank.util import SeedError
        self.interface()
        source = Path(__file__).parent / "testdata/bright-warm.png"
        with mock.patch("seedbank.cognition.analyze_image", side_effect=SeedError("fixture interrupted")):
            self.bridge.sendPhoto(QUrl.fromLocalFile(str(source)).toString())
            self.wait_for(lambda: not self.bridge._pending)
        identifier = self.bridge._incoming_media_request_id
        self.assertTrue(self.bridge.mediaInputPending)
        self.bridge.loadMedia("", 0)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.mediaArchive["pending"][0]["id"], identifier)
        self.assertEqual(self.bridge.mediaArchive["records"][0]["processing"]["state"], "pending")
        with mock.patch("seedbank.cognition.vision_translate", side_effect=AssertionError("Cancel must not call a model")):
            self.bridge.processMediaInput(identifier, True)
            self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(self.bridge.mediaInputPending)
        self.assertTrue(requests.get(self.pack, identifier)["result"]["cancelled"])
        self.assertEqual(self.bridge.mediaArchive["records"][0]["processing"]["state"], "cancelled")
        row = media_archive.read(self.pack)[0]
        self.assertEqual((self.pack / row["blob"]).read_bytes(), source.read_bytes())

    def test_media_dialog_keeps_original_and_does_not_open_files_automatically(self):
        from seedbank.cognition import sense_media
        from seedbank.media_archive import detail
        image = Path(__file__).parent / "testdata/bright-warm.png"
        result = sense_media(self.pack, image=image, vision=False)
        identifier = result["assets"][0]
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("mediaArchiveDialog")
        context = QQmlEngine.contextForObject(dialog)
        with mock.patch("seedbank.quick.bridge.QDesktopServices.openUrl") as opener:
            QQmlExpression(context, dialog, "open()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
            self.bridge.loadMediaDetail(identifier)
            self.wait_for(lambda: not self.bridge._pending)
            dialog.setProperty("showingDetail", True)
            self.assertEqual(self.bridge.mediaDetail["state"], "available")
            opener.assert_not_called()
            self.bridge.openMediaCopy(identifier)
            self.wait_for(lambda: not self.bridge._pending)
            opener.assert_called_once()
        self.bridge.saveMedia("forget", {"asset_id": identifier, "reason": "用户暂时放下。"})
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(detail(self.pack, identifier)["state"], "forgotten")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
            self.assertFalse(self.find("revisitMedia").isVisible())
        self.assert_no_errors()

    def test_media_review_retry_after_refresh_failure_does_not_repeat_model(self):
        from seedbank.cognition import sense_media
        from seedbank.media_archive import read
        result = sense_media(self.pack, image=Path(__file__).parent / "testdata/bright-warm.png", vision=False)
        self.interface()
        data = {"asset_id": result["assets"][0], "note": "重新观察原图。"}
        with mock.patch("seedbank.cognition.vision_translate", return_value={"ok": True, "text": "这是新的解释。", "provider": "fake", "model": "fixture"}) as vision:
            with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
                self.bridge.saveMedia("revisit", data)
                self.wait_for(lambda: not self.bridge._pending)
            self.assertTrue(self.bridge.error)
            self.assertTrue(self.bridge._media_request_id)
            self.bridge.saveMedia("revisit", data)
            self.wait_for(lambda: not self.bridge._pending)
            self.assertFalse(self.bridge.error, self.bridge.notice)
            self.assertEqual(vision.call_count, 1)
        self.assertEqual(len([r for r in read(self.pack) if r["kind"] == "receipt"]), 1)
        self.assertEqual(self.bridge._media_request_id, "")

    def test_life_story_dialog_sources_revision_and_four_languages(self):
        from seedbank import experience, life_story
        from seedbank.cognition import start_day
        day = start_day(self.pack)
        experience.record(self.pack, kind="conversation", text="我们今天讨论了怎样表达自己的想法。", day=day["dayNo"], source=day["file"], actor="user")
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("lifeStoryDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'start("save", null); addSource(recordsData.sources[0])').evaluate()
        self.find("storyTitle").setProperty("text", "尝试表达")
        self.find("storyInterpretation").setProperty("text", "这段交流让我注意到表达的困难。")
        self.find("storyReason").setProperty("text", "用户根据记录整理")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(life_story.read(self.pack)[0]["data"]["title"], "尝试表达")
        QQmlExpression(context, dialog, 'start("save", recordsData.records[0])').evaluate()
        self.find("storyInterpretation").setProperty("text", "现在更看重倾听。")
        self.find("storyReason").setProperty("text", "重新理解")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(len(life_story.read(self.pack)), 2)
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
            self.assertNotIn("{count}", self.find("storyPageCount").property("text"))
            self.assertNotIn("{count}", self.find("storyCalendarDays").property("text"))
        self.assert_no_errors()

    def test_life_story_retry_after_refresh_failure_does_not_duplicate_interpretation(self):
        from seedbank import experience, life_story
        from seedbank.cognition import start_day
        day = start_day(self.pack)
        source = experience.record(self.pack, kind="conversation", text="这是一段确实保存的输入。", day=day["dayNo"], source=day["file"], actor="user")
        self.interface()
        data = {"kind": "chapter", "title": "一段经历", "interpretation": "我对这段经历的理解", "change": "", "question": "",
                "status": "open", "reason": "整理", "target": "", "expected": "",
                "anchors": [{"id": source["id"], "hash": life_story._digest(source), "quote": source["text"]}]}
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
            self.bridge.saveLifeStory("save", data)
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(len(life_story.read(self.pack)), 1)
        self.bridge.saveLifeStory("save", data)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(len(life_story.read(self.pack)), 1)

    def test_disclosure_dialog_save_revoke_and_four_languages(self):
        from seedbank import disclosure
        self.interface()
        self.root.setProperty("page", 2)
        dialog = self.find("disclosureDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'start("profile", null, null)').evaluate()
        self.find("disclosureContent").setProperty("text", "我愿意分享这段自我介绍。")
        self.find("disclosureReason").setProperty("text", "用户明确选择")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertTrue(self.bridge.disclosure["records"][0]["available"])
        QQmlExpression(context, dialog, 'start("revoke", null, recordsData.records[0])').evaluate()
        self.find("disclosureReason").setProperty("text", "结束分享")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(disclosure.read(self.pack)[-1]["kind"], "revoke")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_disclosure_retry_after_refresh_failure_does_not_repeat_approval(self):
        from seedbank import disclosure
        self.interface()
        data = {"target": "", "expected": "", "scope": "public", "text": "可以分享的介绍", "reason": "用户选择",
                "source_id": "", "source_hash": ""}
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
            self.bridge.saveDisclosure("profile", data)
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(len(disclosure.read(self.pack)), 1)
        self.bridge.saveDisclosure("profile", data)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(len(disclosure.read(self.pack)), 1)

    def test_relationship_dialog_records_followup_and_contact_setting(self):
        from seedbank import relationships
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("relationshipsDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'start("note", null)').evaluate()
        self.find("relationshipContent").setProperty("text", "今天解释清楚了一件事情")
        self.find("relationshipReason").setProperty("text", "用户记录本次交流")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(self.bridge.relationships["records"][0]["data"]["text"], "今天解释清楚了一件事情")
        QQmlExpression(context, dialog, 'start("issue", null)').evaluate()
        self.find("relationshipContent").setProperty("text", "关于一件事的理解有差异")
        self.find("relationshipReason").setProperty("text", "约定进一步说明")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.qml(dialog, 'start("boundary", null)')
        self.find("relationshipProactive").setProperty("currentIndex", 1)
        self.find("relationshipReason").setProperty("text", "这几天由我先开口")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(relationships.may_initiate(self.pack))
        self.assertEqual(dialog.property("editing"), "")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_agreement_calendar_date_rejects_invalid_input_and_preserves_draft(self):
        from seedbank import learning, relationships
        learning.perform(self.pack, "plan", {"title": "完成一封信", "skill": "表达", "reason": "明确约定条件",
            "next_step": "写信", "criteria": [{"text": "说明具体事情", "group": "信", "check": "feedback"}]})
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("relationshipsDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'start("agreement", null)').evaluate()
        self.find("relationshipGoal").setProperty("currentIndex", 0)
        self.find("relationshipReason").setProperty("text", "按明确的日历日期核对")
        self.find("agreementDate").setProperty("text", "2099-02-30")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(dialog.property("editing"), "agreement")
        self.assertEqual(self.find("agreementDate").property("text"), "2099-02-30")
        self.find("agreementDate").setProperty("text", "2099-03-01")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        row = next(r for r in relationships.read(self.pack) if r["kind"] == "agreement")
        self.assertEqual(row["data"]["due_on"], "2099-03-01")
        self.assertIsNone(row["data"]["due_day"])
        self.assertEqual(dialog.property("editing"), "")
        self.assert_no_errors()

    def test_learning_prerequisite_selection_survives_refresh_failure_and_blocks_practice(self):
        from seedbank import learning
        base = {"skill": "整理", "reason": "按步骤练习", "next_step": "先整理材料",
                "criteria": [{"text": "写出具体事例", "group": "材料"}]}
        first = learning.perform(self.pack, "plan", {**base, "title": "前一步"})["goal_id"]
        second = learning.perform(self.pack, "plan", {**base, "title": "后一步"})["goal_id"]
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("learningDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.loadLearning(second, 0)
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, "startPlan(false); selectPrerequisite(0, true)").evaluate()
        self.find("learningReason").setProperty("text", "先完成前一步")
        self.assertEqual(dialog.property("prerequisiteCount"), 1)
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("fixture refresh failure")):
            QQmlExpression(context, dialog, "save()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(dialog.property("editing"), "plan")
        self.assertEqual(dialog.property("prerequisiteCount"), 1)
        self.assertEqual(self.find("learningReason").property("text"), "先完成前一步")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(dialog.property("editing"), "")
        self.assertFalse(self.find("startPractice").property("enabled"))
        self.assertEqual(self.bridge.learning["criteria"]["data"]["prerequisites"][0]["goal_id"], first)
        self.assertEqual(sum(row["goal_id"] == second and row["format"] == "seedbank/learning@4" for row in learning.read(self.pack)), 1)
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            self.root.setWidth(860)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_learning_dialog_plan_practice_feedback_and_completion(self):
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("learningDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.qml(dialog, 'startPlan(true)')
        self.qml(self.find("learningCriteriaDraft"), 'setProperty(0, "text", "说清感谢的事情")')
        self.find("learningTitle").setProperty("text", "写一封感谢信")
        self.find("learningSkill").setProperty("text", "表达")
        self.find("learningReason").setProperty("text", "练习具体表达")
        self.find("learningNextStep").setProperty("text", "完成一封信")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(dialog.property("editing"), "")
        QQmlExpression(context, dialog, 'start("practice")').evaluate()
        self.find("learningTask").setProperty("text", "感谢今天的帮助")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(len(self.bridge.learning["attempts"]), 1)
        QQmlExpression(context, dialog, 'attempt = recordsData.attempts[0]; start("feedback"); ratings = {c1: "met"}').evaluate()
        self.find("learningReason").setProperty("text", "本次样本符合条件")
        self.find("learningNextStep").setProperty("text", "换个主题再练习")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        QQmlExpression(context, dialog, 'start("complete"); var values = {}; values[groupNames[0]] = recordsData.attempts[0].id; chosen = values').evaluate()
        self.find("learningReason").setProperty("text", "仅确认这次约定的条件")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertTrue(self.bridge.learning["completion_current"]["passed"])
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_failed_practice_can_be_replayed_then_started_as_a_new_attempt(self):
        from seedbank import learning
        goal = learning.perform(self.pack, "plan", {"title": "写一封感谢信", "skill": "表达", "reason": "练习",
            "next_step": "写信", "criteria": [{"text": "提到具体事情", "group": "信", "check": "feedback"}]})["goal_id"]
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("learningDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.loadLearning(goal, 0)
        self.wait_for(lambda: not self.bridge._pending)
        criteria = self.bridge.learning["criteria"]["id"]
        data = {"goal_id": goal, "work_kind": "letter", "topic": "感谢整理资料的帮助", "criteria_id": criteria}
        with mock.patch("seedbank.brain.StubBrain.compose", side_effect=RuntimeError("fixture")), \
                mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
            self.bridge._save_learning("practice", data)
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        identifier = self.bridge._learning_request_id
        self.assertTrue(identifier)
        self.assertEqual(len(learning.listing(self.pack, goal)["attempts"]), 1)
        with mock.patch("seedbank.brain.StubBrain.compose", side_effect=AssertionError("Replay must not call model")):
            self.bridge._save_learning("practice", data)
            self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertIn("尝试已记录", self.bridge.notice)
        self.assertEqual(self.bridge._learning_request_id, "")
        self.assertEqual(len(self.bridge.learning["attempts"]), 1)
        QQmlExpression(context, dialog, "attempt = recordsData.attempts[0]").evaluate()
        self.assertFalse(self.find("reviewPractice").property("enabled"))
        self.bridge._save_learning("practice", data)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(len(self.bridge.learning["attempts"]), 2)
        self.assertEqual(self.bridge.learning["attempts"][0]["status"], "succeeded")
        self.assertEqual(self.bridge.learning["attempts"][1]["status"], "failed")
        self.assert_no_errors()

    def test_learning_strategy_editor_preserves_draft_and_does_not_repeat_saved_version(self):
        from seedbank import learning
        from seedbank.brain import create_stub_brain
        goal = learning.perform(self.pack, "plan", {"title": "写一封感谢信", "skill": "表达", "reason": "练习",
            "next_step": "写信", "criteria": [{"text": "提到具体事情", "group": "信", "check": "feedback"}]})["goal_id"]
        standard = learning.listing(self.pack, goal)["criteria"]["id"]
        result = learning.practice(self.pack, goal, "letter", "感谢具体帮助", create_stub_brain(), criteria_id=standard)
        learning.perform(self.pack, "feedback", {"goal_id": goal, "criteria_id": standard, "outcome_id": result["receipt"]["id"],
            "expected": "", "ratings": {"c1": "unclear"}, "reason": "只有流程样本", "next_step": "明确具体事情"})
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("learningDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'attempt = recordsData.attempts[0]; start("strategy")').evaluate()
        self.find("learningStrategyText").setProperty("text", "先写事实再写感受")
        self.find("learningExpectedResult").setProperty("text", "读者能够指出发生的事")
        self.find("learningAllowReuse").setProperty("checked", True)
        self.find("learningAppliesWhen").setProperty("text", "表达真实经历")
        self.find("learningAvoidWhen").setProperty("text", "没有事实依据")
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=RuntimeError("fixture refresh failure")):
            QQmlExpression(context, dialog, "save()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(dialog.property("editing"), "strategy")
        self.assertEqual(self.find("learningStrategyText").property("text"), "先写事实再写感受")
        self.assertTrue(self.bridge._learning_request_id)
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(dialog.property("editing"), "")
        self.assertEqual(len([r for r in learning.read(self.pack) if r["kind"] == "adjustment"]), 1)
        self.assertEqual(self.bridge.learning["attempts"][0]["adjustment"]["data"]["transfer"]["avoid_when"], "没有事实依据")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_learning_dialog_shows_model_choice_beside_separate_user_observation(self):
        from seedbank import learning
        from test_learning import FixtureBrain
        from test_learning_choices import ChoiceBrain
        def plan(label):
            return learning.perform(self.pack, "plan", {"title": label, "skill": "表达", "reason": "练习",
                "next_step": "写信", "criteria": [{"text": label, "group": "信", "check": "feedback"}]})["goal_id"]
        def create(goal, brain):
            standard = learning.listing(self.pack, goal)["criteria"]["id"]
            result = learning.practice(self.pack, goal, "letter", "说明整理材料时的分工", brain, criteria_id=standard)
            return standard, result["receipt"]["id"]
        source = plan("说明具体帮助")
        criteria, outcome = create(source, FixtureBrain())
        review = learning.perform(self.pack, "feedback", {"goal_id": source, "criteria_id": criteria, "outcome_id": outcome,
            "expected": "", "ratings": {"c1": "not_met"}, "reason": "细节不足", "next_step": "说明发生的事"})["record"]
        strategy = learning.perform(self.pack, "strategy", {"goal_id": source, "feedback_id": review["id"], "expected": "",
            "text": "用具体事情说明感受", "expected_result": "读者能指出发生的事",
            "transfer": {"applies_when": "真实经历", "avoid_when": "没有事实"}})["record"]
        target = plan("说明合作分工")
        criteria, outcome = create(target, ChoiceBrain([{"strategy_id": strategy["id"], "choice": "adapt",
            "reason": "这次是说明分工", "application": "说明具体行为，再描述自己的贡献"}]))
        learning.perform(self.pack, "feedback", {"goal_id": target, "criteria_id": criteria, "outcome_id": outcome,
            "expected": "", "ratings": {"c1": "not_met"}, "reason": "作品仍未说明个人贡献", "next_step": "下次具体指出分工",
            "lesson_observations": [{"lesson_id": strategy["id"], "fit": "applicable", "use": "not_observed",
                "effect": "uncertain", "reason": "尚未看到自述的调整", "quote": ""}]})
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("learningDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.loadLearning(target, 0)
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, "attempt = recordsData.attempts[0]").evaluate()
        self.assertTrue(self.find("strategyChoicesPanel").property("visible"))
        selected = self.bridge.learning["attempts"][0]
        self.assertEqual(selected["strategy_choices"]["items"][0]["choice"], "adapt")
        self.assertEqual(selected["feedback"]["data"]["lesson_observations"][0]["use"], "not_observed")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertTrue(self.find("strategyChoicesPanel").property("visible"))
        self.assert_no_errors()

    def test_learning_observation_editor_retains_draft_and_retries_saved_feedback(self):
        from seedbank import learning
        from test_learning import FixtureBrain
        brain = FixtureBrain()
        def plan(label):
            return learning.perform(self.pack, "plan", {"title": label, "skill": "表达", "reason": "练习",
                "next_step": "写信", "criteria": [{"text": label, "group": "信", "check": "feedback"}]})["goal_id"]
        def create(goal):
            standard = learning.listing(self.pack, goal)["criteria"]["id"]
            result = learning.practice(self.pack, goal, "letter", "感谢整理材料", brain, criteria_id=standard)
            return standard, result["receipt"]["id"]
        source = plan("具体说明帮助")
        criteria, outcome = create(source)
        review = learning.perform(self.pack, "feedback", {"goal_id": source, "criteria_id": criteria, "outcome_id": outcome,
            "expected": "", "ratings": {"c1": "not_met"}, "reason": "细节不足", "next_step": "说清发生的事"})["record"]
        learning.perform(self.pack, "strategy", {"goal_id": source, "feedback_id": review["id"], "expected": "",
            "text": "先说明具体事情", "expected_result": "读者能指出发生的事",
            "transfer": {"applies_when": "真实经历", "avoid_when": "缺少事实"}})
        target = plan("说明合作中的贡献")
        create(target)
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("learningDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.loadLearning(target, 0)
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, 'attempt = recordsData.attempts[0]; start("feedback")').evaluate()
        self.find("learningReason").setProperty("text", "作品描述了具体帮助")
        self.find("learningNextStep").setProperty("text", "在不同任务继续观察")
        observations = self.find("learningObservationDraft")
        self.qml(observations, 'setProperty(0, "selected", true); setProperty(0, "fit", "applicable"); setProperty(0, "use", "observed"); setProperty(0, "effect", "helpful"); setProperty(0, "reason", "能够找到具体事情"); setProperty(0, "quote", "作品里没有这句话")')
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(dialog.property("editing"), "feedback")
        self.qml(observations, 'setProperty(0, "quote", "谢谢你昨天陪我整理材料。")')
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=RuntimeError("fixture refresh failure")):
            QQmlExpression(context, dialog, "save()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(dialog.property("editing"), "feedback")
        self.assertTrue(self.bridge._learning_request_id)
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        rows = [r for r in learning.read(self.pack) if r["format"] == "seedbank/learning@3"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"]["lesson_observations"][0]["effect"], "helpful")
        QQmlExpression(context, dialog, 'attempt = recordsData.attempts[0]; start("feedback")').evaluate()
        self.assertEqual(self.qml(observations, "get(0).quote"), "谢谢你昨天陪我整理材料。")
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_calendar_reminder_keeps_invalid_draft_and_retries_after_refresh_failure(self):
        from seedbank import hands
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("reminderDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.find("calendarReminderText").setProperty("text", "记得浇花")
        self.find("calendarReminderDate").setProperty("text", "2099-02-30")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertTrue(dialog.property("visible"))
        self.assertEqual(self.find("calendarReminderText").property("text"), "记得浇花")
        self.find("calendarReminderDate").setProperty("text", "2099-03-01")
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=RuntimeError("fixture refresh failure")):
            QQmlExpression(context, dialog, "save()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertTrue(dialog.property("visible"))
        self.assertTrue(self.bridge._reminder_request_id)
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(dialog.property("visible"))
        self.assertEqual(len(hands.list_reminders(self.pack)), 1)
        self.assertEqual(hands.list_reminders(self.pack)[0]["due_on"], "2099-03-01")
        self.assertIsNone(hands.list_reminders(self.pack)[0]["due_day"])
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            self.assertGreater(dialog.property("width"), 300)
        self.assert_no_errors()

    def test_calendar_reminder_pending_input_can_be_restored_or_cancelled(self):
        from seedbank import hands, requests
        with mock.patch("seedbank.hands.save_hands", side_effect=OSError("fixture")), self.assertRaises(OSError):
            hands.schedule(self.pack, {"text": "未完成日期输入", "due_on": "2099-03-01"}, request_id="ui-pending-calendar")
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("reminderDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(len(self.bridge.pendingReminders), 1)
        QQmlExpression(context, dialog, "restore(bridge.pendingReminders[0].payload.data)").evaluate()
        self.assertEqual(self.find("calendarReminderText").property("text"), "未完成日期输入")
        self.assertEqual(hands.list_reminders(self.pack), [])
        self.bridge.cancelPendingReminder("ui-pending-calendar")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(self.bridge.pendingReminders, [])
        self.assertTrue(requests.get(self.pack, "ui-pending-calendar")["result"]["cancelled"])
        self.assertEqual(hands.list_reminders(self.pack), [])
        self.assert_no_errors()

    def test_reminder_revision_dialog_preserves_failed_draft_and_history(self):
        from seedbank import hands
        row = hands.schedule(self.pack, {"text": "原来的提醒", "due_on": "2099-03-01"})["reminder"]
        self.interface()
        self.root.setProperty("page", 3)
        dialog = self.find("reminderDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, "selectReminder(bridge.reminderRows[0], 'revise')").evaluate()
        self.find("calendarReminderText").setProperty("text", "调整后的提醒")
        self.find("calendarReminderDate").setProperty("text", "2099-04-01")
        self.find("reminderChangeReason").setProperty("text", "安排变化")
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=RuntimeError("fixture refresh failure")):
            QQmlExpression(context, dialog, "save()").evaluate()
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(self.find("calendarReminderText").property("text"), "调整后的提醒")
        self.assertTrue(dialog.property("visible"))
        self.assertTrue(self.bridge._reminder_change_id)
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        revised = hands.find_reminder(self.pack, row["id"])
        self.assertEqual(revised["due_on"], "2099-04-01")
        self.assertEqual(len(revised["history"]), 1)
        self.assertEqual(revised["history"][0]["before"]["text"], "原来的提醒")
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, "selectReminder(bridge.reminderRows[0], 'cancel')").evaluate()
        self.find("reminderChangeReason").setProperty("text", "不再需要")
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        cancelled = hands.find_reminder(self.pack, row["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(len(cancelled["history"]), 2)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.find("existingReminderChoice").setProperty("currentIndex", 0)
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", locale)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            viewed = dialog.property("viewed")
            if hasattr(viewed, "toVariant"):
                viewed = viewed.toVariant()
            self.assertEqual(viewed["id"], row["id"])
        self.assert_no_errors()

    def test_reminder_dialog_rejects_changed_state_and_can_restore_unfinished_edit(self):
        from seedbank import hands, reminder_changes, requests
        row = hands.schedule(self.pack, {"text": "原来的提醒", "due_on": "2099-03-01"})["reminder"]
        data = {"reminder_id": row["id"], "expected": reminder_changes.fingerprint(row),
                "text": "中断的改期", "due_on": "2099-04-01", "reason": "日期改变"}
        with mock.patch("seedbank.hands.save_hands", side_effect=OSError("fixture")), self.assertRaises(OSError):
            reminder_changes.perform(self.pack, "revise", data, request_id="ui-reminder-change")
        self.interface()
        dialog = self.find("reminderDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        QQmlExpression(context, dialog, "restoreRequest(bridge.pendingReminders[0])").evaluate()
        self.assertEqual(self.find("calendarReminderText").property("text"), "中断的改期")
        hands.mark_said(self.pack, row["id"], self.bridge.day)
        QQmlExpression(context, dialog, "save()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertTrue(dialog.property("visible"))
        self.assertEqual(self.find("reminderChangeReason").property("text"), "日期改变")
        self.bridge.cancelPendingReminder("ui-reminder-change")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(requests.pending(self.pack), [])
        self.assertEqual(hands.find_reminder(self.pack, row["id"])["status"], "said")
        self.assert_no_errors()

    def test_memory_revision_dialog_saves_change_and_retains_history(self):
        from seedbank.util import append_memories
        append_memories(self.pack, [{"id": "m_ui", "day": 1, "text": "我住在杭州。", "kind": "conversation"}])
        self.interface()
        self.root.setProperty("page", 2)
        self.assertTrue(self.bridge.loadMemory("m_ui"))
        self.wait_for(lambda: not self.bridge._pending)
        dialog = self.find("memoryDetails")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "open(); startEdit(null)").evaluate()
        dialog.setProperty("changeType", "change")
        self.find("revisionContent").setProperty("text", "我现在住在成都。")
        self.find("revisionReason").setProperty("text", "已经搬家。")
        self.find("revisionEffectiveDate").setProperty("text", "2026-10-31")
        QTest.qWait(40)
        button = self.find("saveMemoryRevision")
        self.assertTrue(button.property("enabled"))
        point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
        QTest.mouseClick(self.root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(dialog.property("editing"))
        detail = self.bridge.memoryDetail
        self.assertEqual(detail["selected"]["effective_on"], "2026-10-31")
        self.assertEqual(len(detail["versions"]), 2)
        self.assertNotIn("m_ui", [row["id"] for row in self.bridge.memories.rows])
        self.bridge.filterMemories("杭州", False, True)
        self.assertEqual([row["id"] for row in self.bridge.memories.rows], ["m_ui"])
        self.assert_no_errors()

    def test_memory_revision_failure_preserves_draft_and_retries_same_request(self):
        from seedbank.util import append_memories
        append_memories(self.pack, [{"id": "m_ui", "day": 1, "text": "原内容", "kind": "conversation"}])
        self.interface()
        self.bridge.loadMemory("m_ui")
        self.wait_for(lambda: not self.bridge._pending)
        dialog = self.find("memoryDetails")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "open(); startEdit(null)").evaluate()
        self.find("revisionContent").setProperty("text", "新的内容")
        self.find("revisionReason").setProperty("text", "用户纠正")
        with mock.patch("seedbank.cognition._append_journal", side_effect=OSError("injected failure")):
            self.bridge.saveMemoryRevision("m_ui", "新的内容", "用户纠正", "correction", "")
            self.wait_for(lambda: not self.bridge._pending)
        identifier = self.bridge._memory_request_id
        self.assertTrue(self.bridge.error)
        self.assertTrue(dialog.property("editing"))
        self.assertEqual(self.find("revisionContent").property("text"), "新的内容")
        self.bridge.saveMemoryRevision("m_ui", "新的内容", "用户纠正", "correction", "")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(self.bridge._memory_request_id, identifier)
        self.assertEqual(len(self.bridge.memoryDetail["versions"]), 2)
        self.assert_no_errors()

    def test_memory_revision_dialog_locales_and_small_window(self):
        self.interface()
        identifier = self.bridge.snapshot["memories"][0]["id"]
        self.bridge.loadMemory(identifier)
        self.wait_for(lambda: not self.bridge._pending)
        dialog = self.find("memoryDetails")
        QQmlExpression(QQmlEngine.contextForObject(dialog), dialog, "open(); startEdit(null)").evaluate()
        self.root.setWidth(860)
        self.root.setHeight(640)
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            self.bridge.preference("desktop_large_text", True)
            QTest.qWait(40)
            for name in ("revisionContent", "revisionReason", "saveMemoryRevision"):
                item = self.find(name)
                self.assertGreater(item.width(), 60, name)
            button = self.find("saveMemoryRevision")
            point = button.mapToScene(QPointF(button.width(), button.height()))
            self.assertLessEqual(point.x(), self.root.width())
            self.assertLessEqual(point.y(), self.root.height())
            self.assert_no_errors()

    def test_memory_revision_retry_after_snapshot_failure_does_not_duplicate_saved_version(self):
        from seedbank.util import append_memories
        from seedbank.memory_editor import history
        append_memories(self.pack, [{"id": "m_ui", "day": 1, "text": "原内容", "kind": "conversation"}])
        self.interface()
        self.bridge.loadMemory("m_ui")
        self.wait_for(lambda: not self.bridge._pending)
        with mock.patch.object(self.bridge.session, "snapshot", side_effect=OSError("refresh interrupted")):
            self.bridge.saveMemoryRevision("m_ui", "新的内容", "用户纠正", "correction", "")
            self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.error)
        self.assertEqual(len(history(self.pack, "m_ui")["versions"]), 2)
        self.bridge.saveMemoryRevision("m_ui", "新的内容", "用户纠正", "correction", "")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertEqual(len(self.bridge.memoryDetail["versions"]), 2)
        self.assert_no_errors()

    def test_inner_cards_show_provenance_and_narrative_history_in_four_languages(self):
        from seedbank import inner, inner_sources
        from seedbank.desktop.text import t
        from seedbank.i18n import get_locale, set_locale
        self.addCleanup(set_locale, get_locale())
        generation = {"runner": "fixture", "model": "test-only"}
        inner.set_narrative(self.pack, "以前的自我描述", day=1)
        inner.set_narrative(self.pack, "当前的自我描述", day=1, generation=generation)
        inner.add_dream(self.pack, 1, "用户补充的梦")
        self.bridge.snapshot = {"states": {"inner": inner_sources.project(self.pack)}}
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            with self.subTest(language=language):
                set_locale(language)
                self.bridge.lifeSection("heart")
                rows = {row["title"]: row["text"] for row in self.bridge.life.rows}
                self.assertIn("当前的自我描述", rows[t("关于她自己")])
                self.assertIn(t("模型生成的内心记录，仍可修订"), rows[t("关于她自己")])
                self.assertIn("以前的自我描述", rows[t("以前怎样描述自己")])
                self.assertIn(t("用户补充，尚不代表个体自己的认识"), rows[t("梦里的片段")])

    def test_inner_cards_withhold_invalid_current_text_without_reviving_history(self):
        from seedbank import inner, inner_sources
        from seedbank.i18n import get_locale, set_locale
        self.addCleanup(set_locale, get_locale())
        set_locale("zh_CN")
        inner.set_narrative(self.pack, "以前的自我描述", day=1)
        inner.set_narrative(self.pack, "当前的自我描述", day=1)
        changed = inner.load_inner(self.pack)
        changed["narrative"]["text"] = "来源不匹配的内容"
        inner.save_inner(self.pack, changed)
        self.bridge.snapshot = {"states": {"inner": inner_sources.project(self.pack)}}
        self.bridge.lifeSection("heart")
        rows = {row["title"]: row["text"] for row in self.bridge.life.rows}
        self.assertIn("来源已不可用", rows["关于她自己"])
        self.assertNotIn("以前的自我描述", rows["关于她自己"])
        self.assertNotIn("来源不匹配的内容", json.dumps(rows, ensure_ascii=False))
        self.assertIn("以前的自我描述", rows["以前怎样描述自己"])

    def test_inner_attempt_card_preserves_current_description_in_four_languages(self):
        from types import SimpleNamespace
        from seedbank import cognition, development, inner, inner_sources
        from seedbank.desktop.text import t
        from seedbank.i18n import get_locale, set_locale
        self.addCleanup(set_locale, get_locale())
        day = cognition.start_day(self.pack)
        inner.set_narrative(self.pack, "当前保留的描述", day=day["dayNo"])
        brain = SimpleNamespace(name="fixture", narrative=mock.Mock(return_value={
            "text": "不应覆盖的模板", "_generation": {"runner": "fixture", "model": "test-only", "fallback": True}}))
        cognition.perform_inner(self.pack, {}, brain, day, "narrative")
        self.bridge.snapshot = {"states": {"inner": inner_sources.project(self.pack), "development": development.summary(self.pack)}}
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            with self.subTest(language=language):
                set_locale(language)
                self.bridge.lifeSection("heart")
                rows = {row["title"]: row["text"] for row in self.bridge.life.rows}
                self.assertIn("当前保留的描述", rows[t("关于她自己")])
                self.assertNotIn("不应覆盖的模板", json.dumps(rows, ensure_ascii=False))
                self.assertIn(t("未保存"), rows[t("最近的内心整理")])
                self.assertIn(t("生成服务退回了模板，本次未保存内心内容；已有记录保留。"), rows[t("最近的内心整理")])

    def test_inner_attempt_card_distinguishes_unstarted_and_saved(self):
        from types import SimpleNamespace
        from seedbank import cognition, development, inner_sources
        from seedbank.i18n import get_locale, set_locale
        self.addCleanup(set_locale, get_locale())
        set_locale("zh_CN")
        day = cognition.start_day(self.pack)
        cognition.perform_inner(self.pack, {}, SimpleNamespace(name="stub-fixture"), day, "dream")
        brain = SimpleNamespace(name="fixture", narrative=mock.Mock(return_value={
            "text": "新的有来源叙述", "_generation": {"runner": "fixture", "model": "test-only"}}))
        cognition.perform_inner(self.pack, {}, brain, day, "narrative")
        self.bridge.snapshot = {"states": {"inner": inner_sources.project(self.pack), "development": development.summary(self.pack)}}
        self.bridge.lifeSection("heart")
        rows = {row["title"]: row["text"] for row in self.bridge.life.rows}
        self.assertIn("生成梦的片段 · 未开始", rows["最近的内心整理"])
        self.assertIn("整理自我叙述 · 已保存", rows["最近的内心整理"])
        self.assertIn("新的有来源叙述", rows["关于她自己"])

    def test_growth_card_preserves_proposal_reason_and_result_in_four_languages(self):
        from seedbank import actions, cognition, development
        from seedbank.brain import StubBrain
        from seedbank.desktop.text import t
        from seedbank.i18n import get_locale, set_locale
        self.addCleanup(set_locale, get_locale())
        day = cognition.start_day(self.pack)
        reason = "先休息，明天再整理这段经历。"
        receipt = actions.execute(self.pack, [{"type": "rest", "reason": reason}], day=day, source=day["file"],
            brain=StubBrain(), memories=[], generation={"runner": "fixture", "proposal_activity": "initiative"})[0]
        self.bridge.snapshot = {"states": {"development": development.summary(self.pack)}}
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            with self.subTest(language=language):
                set_locale(language)
                self.bridge.lifeSection("growth")
                card = next(row["text"] for row in self.bridge.life.rows if row["title"] == t("行动与结果"))
                self.assertIn(reason, card)
                self.assertIn(receipt["data"]["detail"], card)
                self.assertIn(t("提出时的说明：{text}", text=reason), card)
                self.assertIn(t("独处活动中提出"), card)
                if language != "zh_CN":
                    self.assertNotIn("提出时的说明：", card)

    def test_growth_card_does_not_invent_legacy_reason(self):
        from seedbank import cognition, development
        from seedbank.desktop.text import t
        day = cognition.start_day(self.pack)
        development.record_outcome(self.pack, action="rest", status="succeeded", detail="旧的执行结果",
            day=day["dayNo"], source=day["file"])
        self.bridge.snapshot = {"states": {"development": development.summary(self.pack)}}
        self.bridge.lifeSection("growth")
        card = next(row["text"] for row in self.bridge.life.rows if row["title"] == t("行动与结果"))
        self.assertIn("旧的执行结果", card)
        self.assertIn(t("当时未记录行动理由。"), card)

    def test_life_sections_and_offline_work(self):
        self.interface()
        self.root.setProperty("page", 3)
        for section in ("growth", "heart", "works"):
            self.bridge.lifeSection(section)
            QTest.qWait(20)
            self.assertGreater(self.bridge.life.rowCount(), 0)
        self.bridge.compose("poem")
        self.wait_for(lambda: not self.bridge._pending)
        self.assertGreater(self.bridge.life.rowCount(), 1)
        self.assert_no_errors()

    def test_lifecycle_dialog_stops_activity_preserves_reader_and_explicitly_resumes(self):
        from seedbank import lifecycle
        self.interface()
        day = self.bridge.day
        self.root.setProperty("page", 3)
        dialog = self.find("lifecycleDialog")
        context = QQmlEngine.contextForObject(dialog)
        QQmlExpression(context, dialog, "open()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        button = self.find("changeLifecycle")
        note = self.find("lifecycleNote")
        confirmation = self.find("lifecycleConfirmation")
        self.assertFalse(button.property("enabled"))
        note.setProperty("text", "隔离测试：明确选择暂停活动并保存档案。")
        self.assertFalse(button.property("enabled"))
        confirmation.setProperty("checked", True)
        self.assertTrue(button.property("enabled"))
        QQmlExpression(QQmlEngine.contextForObject(button), button, "clicked()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertFalse(self.bridge.lifeActive)
        self.assertEqual(lifecycle.status(self.pack)["state"], "dormant")
        self.assertFalse(self.find("composer").property("enabled"))
        self.assertFalse(self.find("live2dStage").property("running"))
        self.assertFalse(confirmation.property("checked"))
        self.bridge.selectDay(day)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.diaryText)
        note.setProperty("text", "隔离测试：明确恢复，从当前日期继续。")
        confirmation.setProperty("checked", True)
        QQmlExpression(QQmlEngine.contextForObject(button), button, "clicked()").evaluate()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertFalse(self.bridge.error, self.bridge.notice)
        self.assertTrue(self.bridge.lifeActive)
        self.assertEqual(len(self.bridge.lifecycle["history"]), 2)
        QQmlExpression(context, dialog, "close()").evaluate()
        self.root.setProperty("page", 0)
        QTest.qWait(30)
        self.assertTrue(self.find("composer").property("enabled"))
        self.assertTrue(self.find("live2dStage").property("running"))
        self.assert_no_errors()

    def test_work_failure_notice_does_not_signal_success_animation(self):
        self.interface()
        signals = []
        self.bridge.petAction.connect(signals.append)
        with mock.patch("seedbank.brain.StubBrain.compose", return_value={}):
            self.bridge.compose("poem")
            self.wait_for(lambda: not self.bridge._pending)
        self.assertIn("尝试已记录", self.bridge.notice)
        self.assertNotIn("happy", signals)
        self.assert_no_errors()

    def test_daily_advance_reminder_and_diary(self):
        self.open_pack()
        day = self.bridge.day
        self.bridge.remind("记得喝水", day + 1)
        self.wait_for(lambda: not self.bridge._pending)
        self.bridge.advanceDay()
        self.wait_for(lambda: not self.bridge._pending)
        self.assertEqual(self.bridge.day, day + 1)
        self.bridge.selectDay(day)
        self.wait_for(lambda: not self.bridge._pending)
        self.assertTrue(self.bridge.diaryText)

    def test_welcome_can_create_new_pack(self):
        self.bridge.createPack("新朋友", self.workspace.name, 0)
        self.wait_for(lambda: self.bridge.ready and not self.bridge._pending)
        self.assertTrue((Path(self.workspace.name) / "新朋友.life" / "birth.json").is_file())

    def test_open_updates_both_pack_hints_without_erasing_preferences(self):
        from seedbank.settings import ui_settings_path
        from seedbank.util import read_json, write_json_atomic
        write_json_atomic(ui_settings_path(), {"desktop_theme": "mint", "last_pack": "old.life"})
        self.open_pack()
        saved = read_json(ui_settings_path(), {})
        self.assertEqual(saved["desktop_theme"], "mint")
        self.assertEqual(saved["last_pack"], str(self.pack))

    def test_duplicate_pack_entry_does_not_create_another_window(self):
        import importlib.util
        filename = Path(__file__).resolve().parents[2] / "packaging" / "windows_entry.py"
        spec = importlib.util.spec_from_file_location("seedbank_test_entry", filename)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with mock.patch.object(entry, "_remembered_hint", return_value=self.pack), \
             mock.patch.object(entry, "_acquire_room_lock", return_value=False), \
             mock.patch.object(entry, "_focus_existing_window", return_value=True), \
             mock.patch("seedbank.quick.app.run") as run:
            self.assertEqual(entry._run_gui(), 0)
            run.assert_not_called()

    def test_safe_graphics_entry_sets_process_mode_before_gui(self):
        import importlib.util
        filename = Path(__file__).resolve().parents[2] / "packaging" / "windows_entry.py"
        spec = importlib.util.spec_from_file_location("seedbank_safe_entry", filename)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        seen = []
        with mock.patch.dict(os.environ, {"QT_QUICK_BACKEND": "opengl"}), \
             mock.patch.object(entry, "_bootstrap_import_path"), \
             mock.patch.object(entry, "_recover_stdio"), \
             mock.patch.object(entry, "_patch_frozen_settings"), \
             mock.patch("seedbank.startup_log.enable"), \
             mock.patch("seedbank.startup_log.mark"), \
             mock.patch.object(entry, "_run_gui", side_effect=lambda: seen.append(os.environ.get("QT_QUICK_BACKEND")) or 0):
            self.assertEqual(entry.main(["--safe-graphics"]), 0)
        self.assertEqual(seen, ["software"])

    def test_close_waits_for_pending_job(self):
        self.open_pack()
        finished = mock.Mock()
        self.bridge.closeReady.connect(finished)
        self.bridge.setDraft("你好")
        self.bridge.send()
        self.bridge.requestClose()
        self.wait_for(lambda: self.bridge._closed)
        self.assertTrue(self.bridge.session.closed)
        self.assertEqual(finished.call_count, 1)

    def test_theme_tokens_are_valid_and_primary_button_text_contrasts(self):
        self.interface()
        for theme in ("cream", "mint", "night"):
            self.bridge.preference("desktop_theme", theme)
            self.app.processEvents()
            for token in ("background", "surface", "ink", "muted", "accent", "accentText", "soft", "field", "line", "danger", "dock"):
                expression = QQmlExpression(QQmlEngine.contextForObject(self.root), self.root, "Style." + token)
                color, undefined = expression.evaluate()
                self.assertFalse(undefined, token)
                self.assertTrue(color.isValid(), token)
            for item in self.root.findChildren(QObject):
                if item.property("text") == "发送" and item.property("color") is not None:
                    self.assertEqual(item.property("color").name(), "#162637" if theme == "night" else "#ffffff")

    def test_layout_matrix_languages_themes_sizes_and_sections(self):
        self.interface()
        self.bridge.preference("desktop_reduced_motion", True)
        settings = self.find("settingsPage")
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            self.bridge.preference("language", language)
            for theme in ("cream", "mint", "night"):
                self.bridge.preference("desktop_theme", theme)
                for large in (False, True):
                    self.bridge.preference("desktop_large_text", large)
                    for width, height in ((860, 640), (1180, 820), (1920, 1080)):
                        self.root.setWidth(width)
                        self.root.setHeight(height)
                        for destination, section in ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (4, 1), (4, 2), (4, 3)):
                            with self.subTest(language=language, theme=theme, large=large, size=(width, height), page=destination, section=section):
                                self.root.setProperty("page", destination)
                                if destination == 4:
                                    settings.setProperty("section", section)
                                QTest.qWait(20)
                                for item in self.visual_items():
                                    if not item.isVisible() or "LabelText" not in item.metaObject().className() or not item.property("text"):
                                        continue
                                    if item.property("eliding"):
                                        continue
                                    self.assertLessEqual(float(item.property("contentWidth") or 0), item.width() + 2, item.property("text"))
                                    self.assertLessEqual(float(item.property("contentHeight") or 0), item.height() + 2, item.property("text"))
                                self.assert_no_errors()


if __name__ == "__main__":
    unittest.main()
