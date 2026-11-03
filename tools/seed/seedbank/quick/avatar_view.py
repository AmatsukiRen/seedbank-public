"""Local presentation preferences, independent of the individual's life pack."""
import math


def normalized_view(values):
    values = values if isinstance(values, dict) else {}
    result = {}
    for key, default, lower, upper in (
        ("live2d_zoom", 1.0, .65, 1.6),
        ("live2d_offset_x", 0.0, -.45, .45),
        ("live2d_offset_y", 0.0, -.45, .45),
    ):
        try:
            value = float(values.get(key, default))
            if not math.isfinite(value):
                value = default
        except (TypeError, ValueError, OverflowError):
            value = default
        result[key] = max(lower, min(upper, value))
    return result
