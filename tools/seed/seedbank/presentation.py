"""Bounded, optional delivery cues; never emotions, memories or executable actions."""

EXPRESSIONS = frozenset({"neutral", "happy", "warm", "sad", "nervous", "angry"})
GESTURES = frozenset({"none", "wave"})


def normalize(value):
    value = value if isinstance(value, dict) else {}

    def allowed(key, choices, default):
        item = value.get(key)
        item = item.strip().casefold() if isinstance(item, str) else ""
        return item if item in choices else default

    return {"expression": allowed("expression", EXPRESSIONS, "neutral"),
            "gesture": allowed("gesture", GESTURES, "none")}


def utterance(reply, cue):
    """UI timing for a text reply, not an audio duration or extra model request."""
    text = reply.strip()[:1200] if isinstance(reply, str) else ""
    return {**normalize(cue), "duration_ms": min(12000, max(3000, 1800 + len(text) * 70))}
