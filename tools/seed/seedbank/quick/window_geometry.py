"""Keep the client and native frame inside the current screen's work area."""
from PySide6.QtCore import QObject, QTimer, QRect
from PySide6.QtGui import QWindow

MINIMUM = (640, 420)
DEFAULT = (1280, 840)


def valid_geometry(value):
    return (isinstance(value, (tuple, list)) and len(value) == 4
            and all(type(part) is int for part in value) and value[0] > 0 and value[1] > 0)


def constrained(geometry, area, margins=(0, 0, 0, 0)):
    """Input/output are client (width, height, x, y); area is (x, y, w, h)."""
    ax, ay, aw, ah = area
    left, top, right, bottom = (max(0, value) for value in margins)
    available_w, available_h = max(1, aw - left - right), max(1, ah - top - bottom)
    requested_w, requested_h = geometry[:2] if valid_geometry(geometry) else DEFAULT
    width = min(available_w, max(min(MINIMUM[0], available_w), requested_w))
    height = min(available_h, max(min(MINIMUM[1], available_h), requested_h))
    x, y = geometry[2:] if valid_geometry(geometry) else (ax + left + (available_w - width) // 2,
                                                         ay + top + (available_h - height) // 2)
    x = max(ax + left, min(x, ax + aw - right - width))
    y = max(ay + top, min(y, ay + ah - bottom - height))
    return width, height, x, y


def _contains(screen, x, y):
    area = screen.availableGeometry()
    # Compare as Python integers before handing possibly damaged saved values
    # to Qt's bounded integer coordinates.
    return area.x() <= x < area.x() + area.width() and area.y() <= y < area.y() + area.height()


class WindowPlacement(QObject):
    """React to screen changes without constraining ordinary user resizing."""
    def __init__(self, window, screens, saved=None):
        super().__init__(window)
        self.window, self.screen = window, None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fit_current)
        window.screenChanged.connect(self.follow_screen)
        window.visibilityChanged.connect(self.schedule)
        if not screens:
            return
        preferred = screens[1] if len(screens) > 1 else screens[0]
        if valid_geometry(saved):
            preferred = next((screen for screen in screens if _contains(screen, saved[2], saved[3])), preferred)
        window.setScreen(preferred)
        self.follow_screen(preferred)
        self.place(saved)

    def follow_screen(self, screen):
        if screen is self.screen:
            self.schedule()
            return
        if self.screen is not None:
            for signal in ("availableGeometryChanged", "logicalDotsPerInchChanged"):
                try:
                    getattr(self.screen, signal).disconnect(self.schedule)
                except (RuntimeError, TypeError):
                    pass  # The old screen may already have been removed.
        self.screen = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self.schedule)
            screen.logicalDotsPerInchChanged.connect(self.schedule)
        self.schedule()

    def schedule(self, *_):
        self.timer.start(0)

    def place(self, requested):
        screen = self.screen
        if screen is None:
            return
        area, margins = screen.availableGeometry(), self.window.frameMargins()
        if area.isEmpty():
            return
        borders = (margins.left(), margins.top(), margins.right(), margins.bottom())
        width, height, x, y = constrained(requested, (area.x(), area.y(), area.width(), area.height()), borders)
        self.window.setMinimumWidth(min(MINIMUM[0], max(1, area.width() - borders[0] - borders[2])))
        self.window.setMinimumHeight(min(MINIMUM[1], max(1, area.height() - borders[1] - borders[3])))
        self.window.setGeometry(QRect(x, y, width, height))

    def fit_current(self):
        # The window manager owns maximized/full-screen/minimized geometry.
        if self.window.visibility() == QWindow.Visibility.Windowed:
            rect = self.window.geometry()
            self.place((rect.width(), rect.height(), rect.x(), rect.y()))
