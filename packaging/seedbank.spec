# -*- mode: python ; coding: utf-8 -*-
#
# Seedbank 的 PyInstaller 构建脚本（Windows 一键包）。
#
# 怎么用（在仓库根目录）：
#
#     python -m PyInstaller packaging/seedbank.spec --noconfirm --clean
#
# 产物：dist/seedbank.exe —— 单文件、无控制台窗口（console=False），双击就是「她的房间」。
# 正常情况请用 packaging/build_windows.ps1，它会先确认 PyInstaller 装好了。
#
# 这个文件由 PyInstaller 用 exec() 执行，所以不能写 `__main__` 入口，也不能 import
# 自己的模块；能用的全局变量有 SPECPATH（本文件所在目录）等。

import os
import ast
import shutil
import sys
from pathlib import Path

import PySide6
from PyInstaller.building.icon import normalize_icon_type
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata

# spec 在 packaging/ 里；仓库根在上一层。
SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent
SEED_DIR = REPO_ROOT / "tools" / "seed"
EGG_DIR = REPO_ROOT / "eggs" / "dafeiyu.egg"
ENTRY = SPEC_DIR / "windows_entry.py"

# Build one Windows icon from the approved PNG for BOTH the packaged runtime
# and the fixed launcher. This only converts the asset's container/size variants.
BRAND_BUILD_DIR = REPO_ROOT / "build"
BRAND_BUILD_DIR.mkdir(parents=True, exist_ok=True)
BRAND_ICON = BRAND_BUILD_DIR / "seedbank-brand.ico"
# Read the shared version literal without starting application code.
version_tree = ast.parse((SEED_DIR / "seedbank" / "__init__.py").read_text(encoding="utf-8-sig"))
APP_VERSION = next(ast.literal_eval(node.value) for node in version_tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets))
WIN_VERSION = tuple(int(part) for part in APP_VERSION.split(".")) + (0,)
VERSION_RESOURCE = BRAND_BUILD_DIR / "seedbank-version.txt"
VERSION_RESOURCE.write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={WIN_VERSION!r}, prodvers={WIN_VERSION!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'SeedBank contributors'),
    StringStruct('FileDescription', 'SeedBank'),
    StringStruct('FileVersion', {APP_VERSION!r}),
    StringStruct('ProductName', 'SeedBank'),
    StringStruct('ProductVersion', {APP_VERSION!r}),
    StringStruct('OriginalFilename', 'seedbank.exe'),
    StringStruct('LegalCopyright', 'Copyright 2026 AmatsukiRen')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding="utf-8")
APP_MANIFEST = BRAND_BUILD_DIR / "seedbank.manifest"
APP_MANIFEST.write_text((SPEC_DIR / "seedbank.manifest").read_text(encoding="utf-8").replace(
    'version="1.0.0.0"', 'version="' + '.'.join(map(str, WIN_VERSION)) + '"'), encoding="utf-8")
shutil.copyfile(normalize_icon_type(
    str(SEED_DIR / "seedbank" / "quick" / "qml" / "brand" / "seedbank-logo.png"),
    ("ico",), "ico", str(BRAND_BUILD_DIR),
), BRAND_ICON)

if sys.platform == "win32":
    windows_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    os.environ["PATH"] = os.pathsep.join(str(path) for path in (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(PySide6.__file__).parent,
        windows_root / "System32", windows_root,
    ))

if not ENTRY.is_file():
    raise SystemExit(f"[seedbank.spec] 找不到入口文件：{ENTRY}")
if not (EGG_DIR / "species.json").is_file():
    raise SystemExit(f"[seedbank.spec] 找不到蛋：{EGG_DIR}")

# collect_submodules 需要真的 import 到 seedbank，所以先把 tools/seed 放进 sys.path。
# （Analysis 的 pathex 只管 PyInstaller 自己的模块搜索，不管 spec 执行时的 import。）
if str(SEED_DIR) not in sys.path:
    sys.path.insert(0, str(SEED_DIR))

# 显式列一遍子模块：PyInstaller 会静态扫 import，但窗口/网页那些是延迟 import 的，
# 直接把整包收进来最稳（零第三方依赖，多收几个模块也不大）。
hiddenimports = collect_submodules("seedbank")
hiddenimports += collect_submodules("discord") + collect_submodules("dingtalk_stream")
hiddenimports += [
    "PySide6.QtSvg",
    "PySide6.QtOpenGL",
    "live2d._live2d",
    "OpenGL.platform.win32",
    "OpenGL.arrays.ctypesarrays",
    "OpenGL.arrays.ctypesparameters",
    "OpenGL.arrays.lists",
    "OpenGL.arrays.numbers",
    "OpenGL.arrays.numpymodule",
    "OpenGL.arrays.strings",
    # tkinter 一般会被自动收集，但 window.py 是按需 import 的，写死更保险。
    "tkinter",
    "tkinter.filedialog",
    "tkinter.font",
    "tkinter.messagebox",
    "tkinter.ttk",
    "_tkinter",
    # Windows 才有的一些标准库模块：自启写注册表、控制台/stdin 探活。
    "ctypes.wintypes",
    "msvcrt",
    "winreg",
]

# Local Live2D replaces generated artwork. The user's third-party model stays
# outside the distribution; shader files belong to the runtime dependency.
datas = [
    (str(REPO_ROOT / "examples" / "plugins" / "hello"), "examples/plugins/hello"),
    # 第一颗蛋：巫师向导孵化时用（onboarding.find_egg 在冻结后找 <MEIPASS>/eggs/...）。
    (str(EGG_DIR), "eggs/dafeiyu.egg"),
    (str(REPO_ROOT / "eggs" / "open.egg"), "eggs/open.egg"),
    # 四种界面语言：i18n._load 会从 __file__ 同目录的 locales/ 读。
    (str(SEED_DIR / "seedbank" / "locales"), "tools/seed/seedbank/locales"),
    (str(SEED_DIR / "seedbank" / "quick" / "qml"), "seedbank/quick/qml"),
]
datas += copy_metadata("PySide6") + copy_metadata("PySide6_Essentials") + copy_metadata("shiboken6")
datas += collect_data_files("live2d", includes=["FrameworkShaders/**/*"])
datas += copy_metadata("live2d-py") + copy_metadata("PyOpenGL")
for distribution in ("discord.py", "lark-oapi", "dingtalk-stream"):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SEED_DIR), str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(SPEC_DIR / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "startup_hook.py")],
    excludes=[
        # Development-only packages do not belong in the desktop distribution.
        "pytest",
        "IPython",
    ],
    noarchive=False,
    optimize=0,
)

# PySide's QtGui hook also collects optional input-context plugins. This unused
# module has GPLv3/commercial terms, not Qt's usual LGPL option. Exclude both
# plugin and library, including any QML/data copies, from the final archive.
a.binaries = [entry for entry in a.binaries if "virtualkeyboard" not in entry[0].lower()]
a.datas = [entry for entry in a.datas if "virtualkeyboard" not in entry[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="seedbank",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 压缩过的 exe 更容易被国产杀软误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # 双击不闪黑框；命令行模式靠 windows_entry._recover_stdio() 接回终端
    disable_windowed_traceback=False,
    manifest=str(APP_MANIFEST),
    version=str(VERSION_RESOURCE),
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BRAND_ICON),
)
