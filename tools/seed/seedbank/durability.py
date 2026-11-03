"""Recoverable local file mutations. Call operation while owning pack_lock.writer.

Before-images and write intents reach disk before live files are replaced.
Uncommitted operations roll back; committed operations only need cleanup.
This protects local process interruption, not remote API side effects or media
failure. Recovery refuses to overwrite files changed outside the transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import uuid

from .util import SeedError, now_iso
from . import file_state

FORMAT = "seedbank/transaction@2"
DIRECTORY = "mind/.transactions"
_local = threading.local()


class RecoveryRequired(SeedError):
    pass


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _safe_path(root, relative):
    value = str(relative)
    parts = PurePosixPath(value).parts
    if (not parts or "\\" in value or ":" in value or value.startswith("/")
            or any(p in (".", "..") or p != p.rstrip(" .")
                   or re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in parts)):
        raise RecoveryRequired("恢复路径无效；已保留事务文件。")
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            raise RecoveryRequired("恢复路径包含链接或联接；已保留事务文件。")
    if not target.resolve().is_relative_to(root):
        raise RecoveryRequired("恢复路径超出生命包；已保留事务文件。")
    return target


def replace_bytes(path, data):
    """Durable single-file replacement, bypassing transaction interception."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        file_state.forget(path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _save(folder, manifest):
    replace_bytes(folder / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))


def _load(root, folder):
    try:
        file = _safe_path(root, f"{DIRECTORY}/{folder.name}/manifest.json")
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecoveryRequired("事务日志无法读取；请先保留生命包副本，不要删除恢复文件。") from error
    if (not isinstance(data, dict) or data.get("format") not in (FORMAT, "seedbank/transaction@1") or data.get("id") != folder.name
            or data.get("state") not in ("active", "committed", "rolled_back")
            or data.get("birth_sha256") != _digest((root / "birth.json").read_bytes())
            or not isinstance(data.get("files"), list)):
        raise RecoveryRequired("事务日志格式或出生身份不匹配；已保留恢复文件。")
    seen = set()
    for index, entry in enumerate(data["files"]):
        if not isinstance(entry, dict) or not isinstance(entry.get("existed"), bool):
            raise RecoveryRequired("事务文件清单不完整；已保留恢复文件。")
        if entry.get("mode") == "append":
            if (not isinstance(entry.get("before_size"), int) or entry["before_size"] < 0
                    or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("before_sha256", "")))
                    or not isinstance(entry.get("intents"), list) or not entry["intents"]):
                raise RecoveryRequired("追加事务清单不完整。")
            for number, intent in enumerate(entry["intents"]):
                if (not isinstance(intent, dict) or intent.get("file") != f"{index}-{number}.tail"
                        or not isinstance(intent.get("size"), int) or intent["size"] < 0
                        or not re.fullmatch(r"[0-9a-f]{64}", str(intent.get("sha256", "")))):
                    raise RecoveryRequired("追加事务的尾部快照不完整。")
        elif (entry.get("mode", "replace") != "replace" or entry.get("before") != f"{index}.before"
                or not isinstance(entry.get("hashes"), list)
                or not all(h is None or (isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)) for h in entry["hashes"])):
            raise RecoveryRequired("事务替换清单不完整。")
        target = _safe_path(root, entry.get("path", ""))
        key = os.path.normcase(str(target))
        if key in seen or target.is_relative_to(root / DIRECTORY):
            raise RecoveryRequired("事务文件清单包含重复或保留路径。")
        seen.add(key)
    return data


def _cleanup(root, folder):
    # Only files from our private UUID directory, never a recursive pack delete.
    if folder.parent != _safe_path(root, DIRECTORY) or not re.fullmatch(r"[0-9a-f]{32}", folder.name):
        raise RecoveryRequired("事务清理路径无效。")
    files = list(folder.iterdir())
    for file in files:
        if (file.is_symlink() or not file.is_file()
                or not (file.name == "manifest.json" or re.fullmatch(r"\d+\.before|\d+-\d+\.tail", file.name)
                        or re.fullmatch(r"(?:manifest\.json|\d+\.before|\d+-\d+\.tail)\.tmp-[0-9a-f]{32}", file.name))):
            raise RecoveryRequired("事务目录包含未知文件，已保留。")
    # Remove manifest last: cleanup itself can be interrupted and resumed.
    for file in files:
        if file.name != "manifest.json":
            file.unlink(missing_ok=True)
    (folder / "manifest.json").unlink(missing_ok=True)
    folder.rmdir()


def _rollback(root, folder, data):
    restore = []
    for entry in data["files"]:
        target = _safe_path(root, entry["path"])
        if entry.get("mode") == "append":
            _check_append(root, folder, entry)
            restore.append((target, entry))
            continue
        before = None
        if entry["existed"]:
            backup = _safe_path(root, f"{DIRECTORY}/{folder.name}/{entry['before']}")
            try:
                before = backup.read_bytes()
            except OSError as error:
                raise RecoveryRequired("恢复快照缺失，已保留当前文件与事务日志。") from error
            if _digest(before) != entry.get("before_sha256"):
                raise RecoveryRequired("恢复快照内容不匹配，已停止恢复。")
        if target.exists():
            if not target.is_file():
                raise RecoveryRequired("恢复目标不是文件，已停止恢复。")
            current = _digest(target.read_bytes())
            if current not in entry["hashes"] and current != entry.get("before_sha256"):
                raise RecoveryRequired("中断后有文件被其他程序修改；请保留两份内容，恢复未覆盖它。")
        elif entry["existed"] and None not in entry["hashes"]:
            raise RecoveryRequired("中断后原有文件被移走；恢复未覆盖其他内容。")
        restore.append((target, before))
    # Preflight every target before changing any. Repeating these writes is safe.
    for target, before in reversed(restore):
        if isinstance(before, dict):
            _truncate(target, before["before_size"], before["existed"])
        elif before is None:
            target.unlink(missing_ok=True)
        else:
            replace_bytes(target, before)
    data["state"] = "rolled_back"
    data["finished_at"] = now_iso()
    _save(folder, data)


def _truncate(path, size, existed=True):
    if existed:
        with path.open("r+b") as handle:
            handle.truncate(size)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        path.unlink(missing_ok=True)
    file_state.forget(path)


def _check_append(root, folder, entry):
    path = _safe_path(root, entry["path"])
    size = path.stat().st_size if path.exists() else 0
    baseline = entry["before_size"]
    if (entry["existed"] and not path.is_file()) or size < baseline:
        raise RecoveryRequired("追加日志的原始内容缺失，恢复已停止。")
    # Recovery re-hashes the prefix from disk; never trust the hot-path cache.
    if file_state.hash_state(path, limit=baseline).hexdigest() != entry["before_sha256"]:
        raise RecoveryRequired("追加日志的历史内容被外部修改，恢复未覆盖它。")
    tails = []
    for intent in entry["intents"]:
        file = _safe_path(root, f"{DIRECTORY}/{folder.name}/{intent['file']}")
        raw = file.read_bytes()
        if len(raw) != intent["size"] or _digest(raw) != intent["sha256"]:
            raise RecoveryRequired("追加日志的恢复快照损坏，已停止恢复。")
        tails.append(raw)
    length = size - baseline
    if length > max(len(tail) for tail in tails):
        raise RecoveryRequired("追加日志出现未记录内容，恢复未截掉它。")
    current = b""
    if path.exists():
        with path.open("rb") as source:
            source.seek(baseline)
            current = source.read(length)
    if not any(tail.startswith(current) for tail in tails):
        raise RecoveryRequired("追加日志的尾部存在未知改动，恢复已停止。")


def recover_locked(pack):
    root = Path(pack).expanduser().resolve()
    directory = _safe_path(root, DIRECTORY)
    if not directory.exists():
        return []
    recovered = []
    folders = sorted(directory.iterdir(), key=lambda p: p.name)
    for folder in folders:
        if not re.fullmatch(r"[0-9a-f]{32}", folder.name):
            raise RecoveryRequired("恢复目录包含未知项目，请保留原档案。")
        folder = _safe_path(root, f"{DIRECTORY}/{folder.name}")
        if not folder.is_dir():
            raise RecoveryRequired("恢复目录结构不完整。")
        if not (folder / "manifest.json").exists():
            # Initial manifest never completed, so no live write was allowed.
            _cleanup(root, folder)
            continue
        data = _load(root, folder)
        if data["state"] == "active":
            _rollback(root, folder, data)
            recovered.append({"id": data["id"], "operation": data.get("operation"), "state": "rolled_back"})
        _cleanup(root, folder)
    return recovered


class Mutation:
    def __init__(self, root, name):
        self.root = root
        identifier = uuid.uuid4().hex
        self.folder = _safe_path(root, f"{DIRECTORY}/{identifier}")
        self.folder.mkdir(parents=True, exist_ok=False)
        self.data = {"format": FORMAT, "id": identifier, "operation": str(name), "state": "active",
                     "started_at": now_iso(), "birth_sha256": _digest((root / "birth.json").read_bytes()), "files": []}
        self.failed = False
        _save(self.folder, self.data)

    def prepare(self, path, content):
        path = Path(path).absolute()
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError as error:
            raise RecoveryRequired("本轮操作试图写出生命包，已阻止。") from error
        path = _safe_path(self.root, relative)
        if path.is_relative_to(self.root / DIRECTORY):
            raise RecoveryRequired("事务日志不能作为普通内容修改。")
        entry = next((e for e in self.data["files"] if e["path"] == relative), None)
        if entry is not None and entry.get("mode") == "append":
            raise RecoveryRequired("同一轮不能先追加再整体替换同一档案；原内容已保留。")
        if entry is None:
            existed = path.exists()
            previous = path.read_bytes() if existed else b""
            filename = f"{len(self.data['files'])}.before"
            if existed:
                replace_bytes(self.folder / filename, previous)
            entry = {"path": relative, "before": filename, "existed": existed,
                     "before_sha256": _digest(previous) if existed else None, "hashes": []}
            self.data["files"].append(entry)
        checksum = _digest(content) if content is not None else None
        if checksum not in entry["hashes"]:
            entry["hashes"].append(checksum)
        _save(self.folder, self.data)

    def prepare_append(self, path, content):
        path = Path(path).absolute()
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError as error:
            raise RecoveryRequired("追加目标超出当前生命包。") from error
        path = _safe_path(self.root, relative)
        if path.is_relative_to(self.root / DIRECTORY):
            raise RecoveryRequired("不能向事务日志追加普通内容。")
        entry = next((e for e in self.data["files"] if e["path"] == relative), None)
        if entry is not None and entry.get("mode") != "append":
            raise RecoveryRequired("同一轮不能先整体替换再追加同一档案。")
        if entry is None:
            existed = path.exists()
            entry = {"path": relative, "mode": "append", "existed": existed,
                     "before_size": path.stat().st_size if existed else 0,
                     "before_sha256": file_state.hash_state(path).hexdigest(), "intents": []}
            self.data["files"].append(entry)
        tail = b""
        if path.exists():
            with path.open("rb") as source:
                source.seek(entry["before_size"])
                tail = source.read()
        intended = tail + content
        filename = f"{self.data['files'].index(entry)}-{len(entry['intents'])}.tail"
        replace_bytes(self.folder / filename, intended)
        entry["intents"].append({"file": filename, "size": len(intended), "sha256": _digest(intended)})
        _save(self.folder, self.data)


def in_operation():
    """Whether a caller would accidentally join a larger rollback boundary."""
    return getattr(_local, "mutation", None) is not None


def before_write(path, content):
    mutation = getattr(_local, "mutation", None)
    if mutation is not None:
        mutation.prepare(path, content)
        for savepoint in getattr(_local, "savepoints", []):
            savepoint.capture(path)


def append_bytes(path, content):
    """Append with a durable operation-tail intent; partial writes can roll back."""
    path = Path(path)
    mutation = getattr(_local, "mutation", None)
    if mutation is None:
        raise RecoveryRequired("追加档案需要持有生命包事务。")
    mutation.prepare_append(path, content)
    for savepoint in getattr(_local, "savepoints", []):
        savepoint.capture_append(path)
    state = file_state.hash_state(path)
    size = path.stat().st_size if path.exists() else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("ab") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.stat().st_size != size + len(content):
            raise RecoveryRequired("追加期间档案发生并发变化，已停止本轮操作。")
        state.update(content)
        file_state.remember(path, state)
    except BaseException:
        file_state.forget(path)
        raise


class Savepoint:
    """In-memory nested rollback; the durable parent covers process crashes."""
    def __init__(self, mutation):
        self.mutation = mutation
        self.before = {}

    def capture(self, path):
        path = Path(path).absolute()
        if path not in self.before:
            self.before[path] = path.read_bytes() if path.exists() else None

    def capture_append(self, path):
        path = Path(path).absolute()
        if path not in self.before:
            self.before[path] = {"mode": "append", "size": path.stat().st_size if path.exists() else 0,
                                 "existed": path.exists(), "sha256": file_state.hash_state(path).hexdigest()}

    def restore(self):
        for path, data in reversed(list(self.before.items())):
            entry = next(e for e in self.mutation.data["files"]
                         if e["path"] == path.relative_to(self.mutation.root).as_posix())
            if isinstance(data, dict) and data.get("mode") == "append":
                _check_append(self.mutation.root, self.mutation.folder, entry)
                if file_state.hash_state(path, limit=data["size"]).hexdigest() != data["sha256"]:
                    raise RecoveryRequired("保存点之前的内容发生变化，已停止恢复。")
                _truncate(path, data["size"], data["existed"])
                continue
            if path.exists() and _digest(path.read_bytes()) not in entry["hashes"] + [entry.get("before_sha256")]:
                raise RecoveryRequired("嵌套操作失败后内容被外部修改，已保留恢复文件。")
            if data is None:
                path.unlink(missing_ok=True)
            else:
                replace_bytes(path, data)


@contextmanager
def operation(pack, name):
    root = Path(pack).expanduser().resolve()
    current = getattr(_local, "mutation", None)
    if current is not None:
        if current.root != root:
            raise RecoveryRequired("一轮事务不能跨越两个生命包。")
        savepoint = Savepoint(current)
        stack = getattr(_local, "savepoints", [])
        _local.savepoints = stack
        stack.append(savepoint)
        try:
            yield current
        except BaseException:
            try:
                savepoint.restore()
            except BaseException:
                current.failed = True
                raise
            raise
        finally:
            stack.pop()
        return
    mutation = Mutation(root, name)
    _local.mutation = mutation
    try:
        yield mutation
        if mutation.failed:
            raise RecoveryRequired("本轮有步骤未完成，正在恢复到操作前状态。")
        mutation.data["state"] = "committed"
        mutation.data["finished_at"] = now_iso()
        _save(mutation.folder, mutation.data)
    except BaseException:
        _local.mutation = None
        # Load the durable intent, not a possibly unsaved in-memory edit.
        durable = _load(root, mutation.folder)
        if durable["state"] != "committed":
            _rollback(root, mutation.folder, durable)
        raise
    finally:
        _local.mutation = None
        try:
            durable = _load(root, mutation.folder)
            if durable["state"] in ("committed", "rolled_back"):
                _cleanup(root, mutation.folder)
        except (OSError, RecoveryRequired):
            # Leave a terminal manifest for the next lock holder to clean up.
            pass
