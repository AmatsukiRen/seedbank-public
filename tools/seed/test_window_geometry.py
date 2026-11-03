"""User-run work-area regressions. No native window, render or life pack."""
import unittest
from unittest.mock import patch, Mock

from PySide6.QtCore import QObject, Signal, QRect, QMargins
from PySide6.QtGui import QWindow
from seedbank.quick.window_geometry import constrained, valid_geometry, WindowPlacement


class Screen(QObject):
    availableGeometryChanged = Signal(object)
    logicalDotsPerInchChanged = Signal(float)

    def __init__(self, area):
        super().__init__()
        self.area = QRect(*area)

    def availableGeometry(self):
        return self.area


class Window(QObject):
    screenChanged = Signal(object)
    visibilityChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.rect = QRect(0, 0, 1280, 840)
        self.margins = QMargins(8, 32, 8, 8)
        self.mode = QWindow.Visibility.Windowed
        self.selected = None
        self.minimum = [640, 420]

    def setScreen(self, screen):
        self.selected = screen
        self.screenChanged.emit(screen)

    def frameMargins(self):
        return self.margins

    def setMinimumWidth(self, width):
        self.minimum[0] = width

    def setMinimumHeight(self, height):
        self.minimum[1] = height

    def setGeometry(self, rect):
        self.rect = rect

    def geometry(self):
        return self.rect

    def visibility(self):
        return self.mode


class WindowGeometryTest(unittest.TestCase):
    def setUp(self):
        # Scheduling is mocked; tests invoke the placement response directly.
        timer = patch("seedbank.quick.window_geometry.QTimer", return_value=Mock())
        timer.start()
        self.addCleanup(timer.stop)

    def enclosed(self, result, area, margins):
        width, height, x, y = result
        left, top, right, bottom = margins
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        self.assertGreaterEqual(x - left, area[0])
        self.assertGreaterEqual(y - top, area[1])
        self.assertLessEqual(x + width + right, area[0] + area[2])
        self.assertLessEqual(y + height + bottom, area[1] + area[3])

    def snapshot(self, window):
        rect = window.geometry()
        return rect.width(), rect.height(), rect.x(), rect.y()

    def test_first_launch_fits_small_work_area_including_frame(self):
        area, margins = (0, 0, 910, 500), (8, 32, 8, 8)
        self.enclosed(constrained(None, area, margins), area, margins)

    def test_oversized_saved_window_and_removed_monitor_position_are_recovered(self):
        area, margins = (0, 0, 1280, 680), (8, 32, 8, 8)
        self.enclosed(constrained((3000, 2000, -4000, 3000), area, margins), area, margins)
        window, screen = Window(), Screen(area)
        WindowPlacement(window, [screen], (10 ** 80, 10 ** 80, -10 ** 80, 10 ** 80))
        self.enclosed(self.snapshot(window), area, margins)

    def test_valid_negative_monitor_position_and_user_size_are_preserved(self):
        area, margins = (-1920, -120, 1920, 1040), (8, 32, 8, 8)
        saved = (860, 640, -1500, 30)
        self.assertEqual(constrained(saved, area, margins), saved)

    def test_work_area_smaller_than_normal_minimum_still_contains_window(self):
        area, margins = (30, 20, 610, 400), (8, 32, 8, 8)
        result = constrained((860, 640, 0, 0), area, margins)
        self.enclosed(result, area, margins)
        self.assertLess(result[0], 640)
        self.assertLess(result[1], 420)

    def test_malformed_settings_use_default_placement(self):
        area, margins = (0, 0, 900, 500), (8, 32, 8, 8)
        for value in (None, [], [True, 640, 0, 0], [860, "640", 0, 0], [0, 640, 0, 0], [-1, 600, 0, 0]):
            with self.subTest(value=value):
                self.assertFalse(valid_geometry(value))
                self.enclosed(constrained(value, area, margins), area, margins)

    def test_screen_change_repositions_and_shrinks_without_recreating_content(self):
        window = Window()
        first, second = Screen((0, 0, 1920, 1040)), Screen((-910, 0, 910, 500))
        controller = WindowPlacement(window, [first, second], (1000, 800, 100, 100))
        self.assertIs(window.selected, first)
        window.setScreen(second)
        controller.fit_current()
        self.enclosed(self.snapshot(window), (-910, 0, 910, 500), (8, 32, 8, 8))
        self.assertIs(controller.window, window)

    def test_changed_available_space_and_frame_margins_are_applied(self):
        window, screen = Window(), Screen((0, 0, 1920, 1040))
        controller = WindowPlacement(window, [screen], (1280, 840, 100, 100))
        window.margins = QMargins(10, 42, 10, 10)
        screen.area = QRect(0, 40, 960, 500)
        screen.availableGeometryChanged.emit(screen.area)
        controller.timer.start.assert_called_with(0)
        controller.fit_current()
        self.enclosed(self.snapshot(window), (0, 40, 960, 500), (10, 42, 10, 10))
        self.assertLessEqual(window.minimum[1], 448)

    def test_window_manager_keeps_maximized_fullscreen_and_minimized_geometry(self):
        window, screen = Window(), Screen((0, 0, 1920, 1040))
        controller = WindowPlacement(window, [screen])
        for mode in (QWindow.Visibility.Maximized, QWindow.Visibility.FullScreen, QWindow.Visibility.Minimized):
            window.mode = mode
            window.rect = QRect(-20, -20, 2000, 1100)
            before = self.snapshot(window)
            controller.fit_current()
            self.assertEqual(self.snapshot(window), before)


if __name__ == "__main__":
    unittest.main()
