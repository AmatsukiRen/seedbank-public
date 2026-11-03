"""Public desktop entry points and compatibility helpers."""

from .desktop.app import CompanionWindow as WhaleWindow, WINDOW_TITLE
from .desktop.pet import PET_ROOT, PET_SMALL_ROOT, PET_STATES, PetStage
from .desktop.theme import PALETTES, Theme
from .desktop.wizard import SetupWizard
from .i18n import t


def window(pack_dir, brain_override=""):
    from .quick.app import window as quick_window
    return quick_window(pack_dir, brain_override)


PET_ROOT_SMALL = PET_SMALL_ROOT
SIDEBAR_BG = PALETTES["cream"]["stage"]
MOOD_FACES = {
    "开心": "😊", "高兴": "😊", "平静": "🙂", "好奇": "🤔", "疲惫": "😪",
    "困": "😪", "难过": "😔", "害怕": "😟", "吃醋": "😤", "生气": "😤",
}


class _PetStage(PetStage):
    def __init__(self, parent, bg=None):
        super().__init__(parent, Theme(), asset_path=PET_ROOT, bg=bg)


def mood_face(mood: str) -> str:
    return next((face for word, face in MOOD_FACES.items() if word in str(mood or "")), "🐋")


def day_caption(day_no, date) -> str:
    try:
        number = int(day_no)
    except (TypeError, ValueError):
        number = 0
    raw = str(date or "")
    try:
        month, day = int(raw[5:7]), int(raw[8:10])
    except ValueError:
        return t("第 {number} 天", number=number)
    if month and day:
        return t("第 {number} 天 · {month} 月 {day} 日", number=number, month=month, day=day)
    return t("第 {number} 天", number=number)
