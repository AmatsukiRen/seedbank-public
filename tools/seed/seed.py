#!/usr/bin/env python3
"""Seedbank 命令行入口。

  python tools/seed/seed.py hatch eggs/dafeiyu.egg ~/fish/小蓝.life
  python tools/seed/seed.py chat ~/fish/小蓝.life

不需要安装任何东西；只要 Python >= 3.10。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seedbank.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
