"""Local, explicitly enabled, one-shot text plugins. Subprocesses are NOT a sandbox."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .util import write_json_atomic

PROTOCOL = "seedbank/plugin@1"
MAX_FILES, MAX_BYTES, MAX_OUTPUT = 256, 8 * 1024 * 1024, 65536
ID = re.compile(r"[a-z][a-z0-9_.-]{2,79}\Z")


def _stop_process(process):
    # Frozen Windows executables have a bootloader parent and a Python child.
    # Stop that worker tree, rather than only killing the bootloader process.
    if isinstance(process.pid, int):
        if os.name == "nt":
            taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
            try:
                subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if process.poll() is None:
        process.kill()
    process.wait()


def _text(value, limit, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError("插件说明中的文字字段无效。")
    return value.strip()


def _files(root):
    """Enumerate a small local source bundle; never traverse links or junctions."""
    result, total = [], 0
    for directory, folders, names in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if name not in (".git", "__pycache__"))
        for name in folders + names:
            path = Path(directory) / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("插件目录不能包含链接或联接目录。")
        for name in sorted(names):
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(directory) / name
            if not path.is_file():
                raise ValueError("插件目录包含不支持的文件。")
            total += path.stat().st_size
            result.append(path)
            if len(result) > MAX_FILES or total > MAX_BYTES:
                raise ValueError("插件过大：最多 256 个文件、8 MiB。请移除依赖环境和生成文件。")
    return sorted(result)


def inspect_plugin(root):
    root = Path(root).resolve()
    files = _files(root)
    manifest = root / "plugin.json"
    if manifest not in files or manifest.stat().st_size > 32768:
        raise ValueError("请选择包含 plugin.json 的插件文件夹。")
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("protocol") != PROTOCOL:
        raise ValueError("不支持此插件协议；当前支持 seedbank/plugin@1。")
    identifier = _text(data.get("id"), 80)
    if not ID.fullmatch(identifier):
        raise ValueError("插件 ID 需使用小写字母、数字、点、横线或下划线。")
    entry = _text(data.get("entry"), 160)
    target = (root / entry).resolve()
    if not target.is_relative_to(root) or target.suffix != ".py" or target not in files:
        raise ValueError("插件入口必须是插件目录内的 Python 源文件。")
    fields = data.get("settings", [])
    access = data.get("access", [])
    if not isinstance(fields, list) or len(fields) > 12 or not isinstance(access, list) or any(v not in ("network", "files") for v in access):
        raise ValueError("插件配置字段或访问声明无效。")
    settings, keys = [], set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("插件配置字段无效。")
        key = _text(field.get("key"), 80)
        if not ID.fullmatch(key) or key in keys:
            raise ValueError("插件配置字段重复或名称无效。")
        keys.add(key)
        settings.append({"key": key, "label": _text(field.get("label"), 80),
                         "default": _text(field.get("default", ""), 1000, False)})
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return {"id": identifier, "name": _text(data.get("name"), 100),
            "version": _text(data.get("version"), 40), "author": _text(data.get("author"), 100),
            "description": _text(data.get("description", ""), 600, False),
            "entry": target.relative_to(root).as_posix(), "settings": settings,
            "access": list(dict.fromkeys(access)), "digest": digest.hexdigest()}, files


class PluginManager:
    def __init__(self, home=None):
        self.root = Path(home) if home is not None else Path.home() / ".seedbank" / "plugins"
        self.root = self.root.resolve()
        self.registry = self.root / "registry.json"
        self._lock = threading.RLock()
        self._process = None
        self._running = ""
        self._cancel = threading.Event()

    def _read(self):
        if not self.registry.exists():
            return {}
        if self.registry.stat().st_size > 1024 * 1024:
            raise ValueError("插件登记文件过大。")
        data = json.loads(self.registry.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or data.get("format") != "seedbank/plugins@1" or not isinstance(data.get("plugins"), dict):
            raise ValueError("插件登记文件损坏；请先保留文件并联系维护者。")
        if len(data["plugins"]) > 64:
            raise ValueError("最多登记 64 个插件。")
        return data["plugins"]

    def _save(self, rows):
        self.root.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.registry, {"format": "seedbank/plugins@1", "plugins": rows})

    def _folder(self, row):
        bundle = row.get("bundle", "") if isinstance(row, dict) else ""
        if not isinstance(bundle, str) or not re.fullmatch(r"[0-9a-f]{32}", bundle):
            raise ValueError("插件目录登记无效。")
        path = (self.root / bundle).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("插件目录位于管理位置之外。")
        return path

    def _inspect(self, identifier, row):
        info, _ = inspect_plugin(self._folder(row))
        if info["id"] != identifier or info["digest"] != row.get("digest"):
            raise ValueError("插件文件已改变，请重新添加并确认来源。")
        return info

    def list(self):
        with self._lock:
            result = []
            for identifier, row in self._read().items():
                try:
                    info = self._inspect(identifier, row)
                    config = row.get("config", {})
                    info.update(enabled=row.get("enabled") is True,
                                config=config if isinstance(config, dict) else {}, error="",
                                folder=str(self._folder(row)))
                except (OSError, ValueError, TypeError) as error:
                    info = {"id": identifier, "name": identifier, "version": "", "author": "",
                            "description": "", "settings": [], "config": {}, "access": [],
                            "enabled": False, "error": str(error), "folder": ""}
                result.append(info)
            return sorted(result, key=lambda row: row["name"].casefold())

    def install(self, source):
        with self._lock:
            if self._running:
                raise ValueError("请先停止正在运行的插件。")
            source = Path(source).resolve()
            source_info, files = inspect_plugin(source)
            rows = self._read()
            if source_info["id"] not in rows and len(rows) >= 64:
                raise ValueError("最多登记 64 个插件。")
            self.root.mkdir(parents=True, exist_ok=True)
            # Stage only the enumerated bundle, then retain a separate managed copy.
            with tempfile.TemporaryDirectory(prefix="import-", dir=self.root) as staging:
                stage = Path(staging)
                for source_file in files:
                    target = stage / source_file.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, target)
                info, _ = inspect_plugin(stage)
                if info["digest"] != source_info["digest"]:
                    raise ValueError("添加期间插件文件发生了变化，请重新选择。")
                bundle = uuid.uuid4().hex
                target = self.root / bundle
                shutil.copytree(stage, target)
            rows[info["id"]] = {"bundle": bundle, "digest": info["digest"], "enabled": False,
                                "config": {f["key"]: f["default"] for f in info["settings"]}}
            self._save(rows)
            return info["id"]

    def enable(self, identifier, enabled):
        with self._lock:
            rows = self._read()
            if identifier not in rows:
                raise ValueError("未找到此插件。")
            if enabled:
                self._inspect(identifier, rows[identifier])
            else:
                self.cancel(identifier)
            rows[identifier]["enabled"] = bool(enabled)
            self._save(rows)

    def configure(self, identifier, values):
        with self._lock:
            rows = self._read()
            if identifier not in rows:
                raise ValueError("未找到此插件。")
            info = self._inspect(identifier, rows[identifier])
            if not isinstance(values, dict) or set(values) - {field["key"] for field in info["settings"]}:
                raise ValueError("未找到此插件配置项。")
            rows[identifier]["config"] = {field["key"]: _text(values.get(field["key"], field["default"]), 1000, False)
                                          for field in info["settings"]}
            self._save(rows)

    def remove(self, identifier):
        with self._lock:
            self.cancel(identifier)
            rows = self._read()
            rows.pop(identifier, None)
            self._save(rows)

    def cancel(self, identifier=None):
        with self._lock:
            if identifier is None or identifier == self._running:
                self._cancel.set()

    def run(self, identifier, text, *, timeout=30, cancel=None):
        with self._lock:
            if self._running:
                raise ValueError("已有插件正在运行。")
            row = self._read().get(identifier)
            if not isinstance(row, dict) or row.get("enabled") is not True:
                raise ValueError("请先确认来源并启用插件。")
            info = self._inspect(identifier, row)
            request = {"protocol": PROTOCOL, "input": _text(text, 4000, False), "settings": row.get("config", {})}
            payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
            if len(payload) > 20000:
                raise ValueError("插件输入和配置过长。")
            folder = self._folder(row)
            entry = folder / info["entry"]
            self._running = identifier
            self._cancel = cancel if cancel is not None else threading.Event()
        process = None
        try:
            # Only system runtime locations are inherited, not model/bot API keys.
            allowed = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"}
            env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
            env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
            command = ([sys.executable, "--plugin-worker", str(entry)] if getattr(sys, "frozen", False)
                       else [sys.executable, "-B", "-m", "seedbank.plugin_worker", str(entry)])
            if not getattr(sys, "frozen", False):
                env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            with tempfile.TemporaryDirectory(prefix="seedbank-plugin-run-") as work, \
                    tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as outgoing:
                incoming.write(payload)
                incoming.seek(0)
                with self._lock:
                    if self._cancel.is_set():
                        raise ValueError("插件运行已停止。")
                    process = subprocess.Popen(command, cwd=work, env=env, stdin=incoming, stdout=outgoing,
                        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        start_new_session=os.name != "nt")
                    self._process = process
                try:
                    deadline = time.monotonic() + min(30, max(0.1, timeout))
                    while process.poll() is None:
                        if self._cancel.wait(0.05):
                            raise ValueError("插件运行已停止。")
                        if time.monotonic() >= deadline:
                            raise ValueError("插件运行超过 30 秒，已停止。")
                        if os.fstat(outgoing.fileno()).st_size > MAX_OUTPUT:
                            raise ValueError("插件输出过长，已停止。")
                finally:
                    # Close the worker before its temporary working directory/files.
                    if process.poll() is None:
                        _stop_process(process)
                if self._cancel.is_set():
                    raise ValueError("插件运行已停止。")
                outgoing.seek(0)
                raw = outgoing.read(MAX_OUTPUT + 1)
                if len(raw) > MAX_OUTPUT or process.returncode != 0:
                    raise ValueError("插件运行失败或输出过长。")
                try:
                    result = json.loads(raw.decode("utf-8"))
                    if not isinstance(result, dict) or result.get("protocol") != PROTOCOL:
                        raise ValueError()
                    return _text(result.get("text"), 12000, False)
                except (ValueError, UnicodeError):
                    raise ValueError("插件返回格式无效，请联系插件作者。") from None
        finally:
            if process is not None and process.poll() is None:
                _stop_process(process)
            with self._lock:
                self._process = None
                self._running = ""
