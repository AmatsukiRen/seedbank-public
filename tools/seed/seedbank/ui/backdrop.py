# -*- coding: utf-8 -*-
"""玻璃拟态的背景：纵向渐变 + 柔和径向光斑。

只在创建/换尺寸时画一次（缓存），不做每帧计算。
"""
import tkinter as tk

from . import tokens as T

_PAINTED = {}


def _mix(a: str, b: str, ratio: float) -> str:
    return T.blend(a, b, max(0.0, min(1.0, ratio)))


def paint(canvas, width: int, height: int, tag: str = "backdrop", force: bool = False) -> None:
    """把整窗渐变 + 2~3 个柔光斑画到 canvas 底层；同尺寸/主题只画一次。"""
    if width <= 2 or height <= 2:
        return
    signature = (width, height, T.current())
    if not force and _PAINTED.get(canvas) == signature:
        return
    _PAINTED[canvas] = signature
    try:
        canvas.delete(tag)
    except tk.TclError:
        return
    if T.get("FLAT_BACKDROP"):
        canvas.create_rectangle(0, 0, width, height, fill=T.get("BG"), outline="", tags=tag)
        canvas.tag_lower(tag)
        return
    top = T.get("BG_TOP")
    bottom = T.get("BG_BOTTOM")
    bands = max(28, min(110, height // 8))
    for index in range(bands):
        ratio = index / max(1, bands - 1)
        color = _mix(top, bottom, ratio)
        y1 = int(height * ratio)
        y2 = int(height * (ratio + 1)) + 1
        canvas.create_rectangle(0, y1, width, y2, fill=color, outline="", tags=tag)
    glows = (
        (0.20, 0.10, 0.36, T.get("GLOW_A")),
        (0.86, 0.22, 0.32, T.get("GLOW_B")),
        (0.52, 1.02, 0.40, T.get("GLOW_A")),
    )
    for gx, gy, gr, color in glows:
        cx, cy = int(width * gx), int(height * gy)
        radius = int(min(width, height) * gr)
        base = _mix(top, bottom, gy)
        steps = 26
        for step in range(steps):
            ratio = step / steps
            rr = max(2, int(radius * (1.0 - ratio)))
            strength = 0.015 + 0.11 * ((1.0 - ratio) ** 1.5)
            mix = _mix(base, color, strength)
            canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=mix,
                               outline="", tags=tag)
    canvas.tag_lower(tag)


import math as _math


def _sample_points(x, y, w, h):
    return [
        (x + w * 0.5, y + h * 0.5),
        (x + w * 0.18, y + h * 0.18),
        (x + w * 0.82, y + h * 0.18),
        (x + w * 0.18, y + h * 0.82),
        (x + w * 0.82, y + h * 0.82),
    ]


def color_at(x: int, y: int, w: int, h: int) -> str:
    """不绘制：按 paint() 同一套渐变+柔光公式，取该区域 5 点采样的平均色。"""
    win_w = max(1, int(getattr(paint, "_last_w", 1280)))
    win_h = max(1, int(getattr(paint, "_last_h", 800)))
    top = T.get("BG_TOP")
    bottom = T.get("BG_BOTTOM")
    glows = (
        (0.20, 0.10, 0.36, T.get("GLOW_A")),
        (0.86, 0.22, 0.32, T.get("GLOW_B")),
        (0.52, 1.02, 0.40, T.get("GLOW_A")),
    )
    rs, gs, bs = 0, 0, 0
    pts = _sample_points(x, y, max(1, w), max(1, h))
    for (px, py) in pts:
        t = max(0.0, min(1.0, py / win_h))
        color = _mix(top, bottom, t)
        for gx, gy, gr, glow in glows:
            cx, cy = gx * win_w, gy * win_h
            rr = gr * max(win_w, win_h)
            d = _math.hypot(px - cx, py - cy)
            ratio = max(0.0, min(1.0, 1.0 - d / max(1.0, rr)))
            if ratio > 0.0:
                strength = 0.015 + 0.11 * ((1.0 - ratio) ** 1.5)
                color = _mix(color, glow, min(0.16, strength))
        c = color.lstrip("#")
        rs += int(c[0:2], 16); gs += int(c[2:4], 16); bs += int(c[4:6], 16)
    n = float(len(pts))
    return "#%02x%02x%02x" % (round(rs / n), round(gs / n), round(bs / n))


def paint_region(canvas, ox: int, oy: int, w: int, h: int, tag: str = "bgregion") -> None:
    """把窗口级渐变+光斑按窗口偏移 (ox,oy) 画进任意 canvas（画在 canvas 局部坐标）。"""
    try:
        win_w, win_h = int(1280), int(800)
        top = T.get("BG_TOP")
        bottom = T.get("BG_BOTTOM")
        glows = (
            (0.20, 0.10, 0.36, T.get("GLOW_A")),
            (0.86, 0.22, 0.32, T.get("GLOW_B")),
            (0.52, 1.02, 0.40, T.get("GLOW_A")),
        )
        canvas.delete(tag)
        step = 14
        rows = max(1, h // step + 1)
        for row in range(rows):
            y0 = row * step
            wy = oy + y0
            t = max(0.0, min(1.0, wy / float(win_h)))
            base = _mix(top, bottom, t)
            rgb = [int(base.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
            for gx, gy, gr, glow in glows:
                cx, cy = gx * win_w - ox, gy * win_h - oy
                rr = gr * max(win_w, win_h)
                dy = (y0 + step * 0.5) - cy
                dx_min = -w
                # 该行光斑最大强度：取行中点与圆心水平距离中点近似
                dist = _math.hypot(dx_min * 0.5, dy)
                ratio = max(0.0, min(1.0, 1.0 - dist / max(1.0, rr)))
                if ratio > 0:
                    strength = 0.015 + 0.11 * ((1.0 - ratio) ** 1.5)
                    gc = glow.lstrip("#")
                    for i in range(3):
                        rgb[i] = round(rgb[i] + (int(gc[i * 2:i * 2 + 2], 16) - rgb[i]) * min(0.16, strength))
            color = "#%02x%02x%02x" % tuple(rgb)
            canvas.create_rectangle(0, y0, w, y0 + step + 1, fill=color, outline="", tags=tag)
    except Exception:
        pass
