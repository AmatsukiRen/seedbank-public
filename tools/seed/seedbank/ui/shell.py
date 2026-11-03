# -*- coding: utf-8 -*-
"""窗口外壳：标题栏/侧栏/主区的尺寸约定（页面与 window.py 共用）。"""
from . import tokens as T

TITLEBAR_H = 36
SIDEBAR_W = 300
PAGE_HEAD_H = 72
CONTENT_MAX = T.CONTENT_MAX


def content_padding(viewport_width: int) -> int:
    """内容列左右留白：内容列 920 居中。"""
    return max(24, (viewport_width - CONTENT_MAX) // 2)
