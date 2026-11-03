"""Presentation-only emotion choices. Never changes mood, memory or identity."""
import math
import random


EXPRESSIONS = {
    "happy": "SeedHappy", "warm": "SeedWarm", "think": "SeedThink",
    "sad": "SeedSad", "nervous": "SeedNervous", "angry": "SeedAngry",
}

_MOODS = {
    "happy": {"开心", "快乐", "高兴", "愉快", "兴奋", "happy", "joyful", "excited"},
    "warm": {"害羞", "温暖", "感动", "安心", "shy", "warm", "grateful"},
    "sad": {"失落", "难过", "伤心", "悲伤", "不开心", "sad", "disappointed"},
    "nervous": {"紧张", "不安", "担心", "焦虑", "nervous", "anxious", "worried"},
    "angry": {"生气", "愤怒", "恼火", "angry", "frustrated"},
}


def mood_style(mood, energy=1.0):
    value = str(mood or "").strip().casefold()
    style = next((key for key, values in _MOODS.items() if value in values), "idle")
    try:
        energy = float(energy)
        if not math.isfinite(energy):
            energy = 1.0
    except (TypeError, ValueError, OverflowError):
        energy = 1.0
    # Low energy tones down an existing positive display, never invents
    # a different mood. Unrecognized/custom moods retain the neutral face.
    if energy < .25:
        style = "warm" if style == "happy" else style
    return style


def choose_expression(style, previous="", *, choose=None):
    # SeedThink is the model's loading symbol, reserved for an explicit request
    # in progress. Curiosity/focus must not make an idle character look stuck.
    choices = ("happy", "warm") if style == "happy" else (style,) if style in EXPRESSIONS and style != "think" else ("idle",)
    alternatives = tuple(value for value in choices if value != previous) or choices
    return (choose or random.choice)(alternatives)


class ExpressionPlayback:
    def __init__(self):
        self.current = None

    def update(self, model, state, available):
        expression = EXPRESSIONS.get(state)
        expression = expression if expression in available else ""
        if expression == self.current:
            return
        model.ResetExpressions()
        if expression:
            model.SetExpression(expression)
        self.current = expression
