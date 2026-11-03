"""QQ 载体适配器（兼容入口）—— 让 QQ 成为她的一扇窗。

真正的实现已经搬进 `tools/seed/seedbank/qq.py`（内置版，`seed qq` 用的就是它）。
这个文件保留原路径与函数名，方便旧脚本/测试继续用：

  python adapters/qq-onebot/qq_onebot.py --pack ~/fish/小蓝.life --owner 123456789

它不登录 QQ：QQ 那一侧由第三方 OneBot 实现（SnowLuma / NapCat /
LLOneBot / Lagrange …）负责，我们只对接 OneBot v11 的 HTTP API 与 HTTP 上报。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tools" / "seed"))

from seedbank.qq import (  # noqa: E402
    DEFAULT_ONEBOT_HTTP,
    DEFAULT_QQ_PORT,
    MAX_IMAGE_BYTES,
    MAX_TEXT,
    BridgeClient,
    ConsoleSender,
    OneBotSender,
    QQAdapter,
    SubprocessBridge,
    decide,
    extract_text,
    find_images,
    main,
    mentioned,
    parse_groups,
    serve,
    test_connection,
)

__all__ = [
    "DEFAULT_ONEBOT_HTTP",
    "DEFAULT_QQ_PORT",
    "MAX_IMAGE_BYTES",
    "MAX_TEXT",
    "BridgeClient",
    "ConsoleSender",
    "OneBotSender",
    "QQAdapter",
    "SubprocessBridge",
    "decide",
    "extract_text",
    "find_images",
    "main",
    "mentioned",
    "parse_groups",
    "serve",
    "test_connection",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
