"""Streamed backup manifests and disk-backed plans; ZIP metadata still uses RAM."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
import time
import unicodedata
import uuid
import zipfile

from .durability import _safe_path
from .pack_lock import writer
from .util import SeedError, now_iso

FORMAT = "seedbank/backup@2"
LEGACY_FORMAT = "seedbank/backup@1"
MANIFEST = "seedbank-backup.json"
INDEX = "seedbank-files.jsonl"
EXCLUDED = {"mind/.transactions", "mind/.writer.lock", "mind/.tick.lock",
            "mind/search.sqlite3", "mind/search.sqlite3-wal", "mind/search.sqlite3-shm", "mind/search.sqlite3-journal",
            "mind/media-cache.sqlite3", "mind/media-cache.sqlite3-wal", "mind/media-cache.sqlite3-shm", "mind/media-cache.sqlite3-journal"}
CHUNK = 1024 * 1024
MANIFEST_LIMIT = 32 * 1024 * 1024  # Legacy JSON only; v2 has no total index limit.
HEADER_LIMIT = 64 * 1024
ENTRY_LIMIT = 1024 * 1024


class BackupCancelled(SeedError):
    pass


class _Progress:
    def __init__(self, callback=None, cancel=None):
        self.callback, self.cancel, self.last = callback, cancel, 0.0

    def report(self, stage, files=0, processed=0, total=None, *, force=False):
        if self.cancel is not None and self.cancel.is_set():
            raise BackupCancelled("已取消，未发布新的备份或恢复包。")
        now = time.monotonic()
        if self.callback and (force or now - self.last >= 0.15):
            self.callback({"stage": stage, "files": files, "processed_bytes": processed, "total_bytes": total})
            self.last = now
        if self.cancel is not None and self.cancel.is_set():
            raise BackupCancelled("已取消，未发布新的备份或恢复包。")


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def _excluded(relative):
    key = _key(relative)
    return key in EXCLUDED or key.startswith("mind/.transactions/") or bool(re.search(r"\.tmp-[0-9a-f]{8,32}$", relative))


def _path(root, relative):
    if (not isinstance(relative, str) or not relative or PurePosixPath(relative).as_posix() != relative
            or any(ord(c) < 32 or c in '<>"|?*' for c in relative)):
        raise SeedError("备份包含无效或不便于跨设备恢复的路径。")
    if _excluded(relative):
        raise SeedError("备份包含运行时保留路径。")
    return _safe_path(root, relative)


def _files(root, directory=None):
    for path in sorted((directory or root).iterdir(), key=lambda p: p.name):
        relative = path.relative_to(root).as_posix()
        if _excluded(relative):
            continue
        path = _path(root, relative)
        if path.is_dir():
            yield from _files(root, path)
        elif path.is_file():
            yield relative, path
        else:
            raise SeedError("生命包包含无法备份的特殊文件。")


def _signature(stat):
    return json.dumps([stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns], separators=(",", ":"))


def _source_stat(path):
    # Use the same handle API for every comparison. On Windows, path stat and
    # fstat can report different ctime meanings for the very same file.
    with path.open("rb") as source:
        return os.fstat(source.fileno())


class _Catalog:
    """Private temporary SQL state; no full list of planned or created files."""
    def __init__(self, directory=None):
        handle = tempfile.NamedTemporaryFile(prefix=".seedbank-backup-", suffix=".sqlite3", dir=directory, delete=False)
        self.path = Path(handle.name)
        handle.close()
        self.db = None
        try:
            self.db = sqlite3.connect(self.path, isolation_level=None)
            self.db.execute("PRAGMA journal_mode=OFF")
            self.db.execute("PRAGMA synchronous=OFF")  # Disposable plan, not the life archive.
            self.db.execute("PRAGMA cache_size=-2048")
            self.db.execute("PRAGMA temp_store=FILE")
            self.db.execute("CREATE TABLE files (rel TEXT PRIMARY KEY, key TEXT UNIQUE, size INTEGER, sha TEXT, signature TEXT, created INTEGER DEFAULT 0)")
            self.db.execute("CREATE TABLE dirs (key TEXT PRIMARY KEY, rel TEXT, depth INTEGER, created INTEGER DEFAULT 0)")
            self.db.execute("CREATE TABLE members (name TEXT PRIMARY KEY, size INTEGER)")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        self.path.unlink(missing_ok=True)

    def add(self, relative, size, digest="", signature=""):
        key = _key(relative)
        if self.db.execute("SELECT 1 FROM dirs WHERE key=?", (key,)).fetchone():
            raise SeedError("备份路径同时被用作文件和文件夹。")
        parts = relative.split("/")
        for depth in range(1, len(parts)):
            parent = "/".join(parts[:depth])
            parent_key = _key(parent)
            if self.db.execute("SELECT 1 FROM files WHERE key=?", (parent_key,)).fetchone():
                raise SeedError("备份路径同时被用作文件和文件夹。")
            existing = self.db.execute("SELECT rel FROM dirs WHERE key=?", (parent_key,)).fetchone()
            if existing and existing[0] != parent:
                raise SeedError("备份文件夹名称在不同设备上可能重合。")
            self.db.execute("INSERT OR IGNORE INTO dirs (key,rel,depth) VALUES (?,?,?)", (parent_key, parent, depth))
        try:
            self.db.execute("INSERT INTO files (rel,key,size,sha,signature) VALUES (?,?,?,?,?)", (relative, key, size, digest, signature))
        except sqlite3.IntegrityError as error:
            raise SeedError("备份包含重复路径或跨设备名称冲突。") from error

    def entries(self, *, created=False):
        where = " WHERE created=1" if created else ""
        return self.db.execute("SELECT rel,size,sha,signature FROM files" + where + " ORDER BY rel")


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _publish_file(temporary, output):
    if os.name == "nt":
        os.rename(temporary, output)
    else:
        os.link(temporary, output)
        temporary.unlink()


def create(pack, destination=None, *, progress=None, cancel=None):
    root = Path(pack).expanduser().resolve()
    if not root.is_dir() or not (root / "birth.json").is_file():
        raise SeedError("备份来源缺少生命包出生记录。")
    stamp = now_iso().replace(":", "").replace(".", "-")
    output = Path(destination).expanduser().absolute() if destination else (
        root.parent / "SEEDbank-backups" / f"{root.name}-{stamp}-{uuid.uuid4().hex[:8]}.zip")
    if output.resolve().is_relative_to(root):
        raise SeedError("备份应放在生命包之外，避免把备份再次装进备份。")
    if output.exists() or output.is_symlink():
        raise SeedError("备份目标已存在；请使用新的文件名。")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial-" + uuid.uuid4().hex)
    reporter = _Progress(progress, cancel)
    try:
        with writer(root), _Catalog(output.parent) as catalog, tempfile.TemporaryFile(dir=output.parent) as index:
            count, total = 0, 0
            reporter.report("planning", force=True)
            for relative, path in _files(root):
                stat = _source_stat(path)
                catalog.add(relative, stat.st_size, signature=_signature(stat))
                count += 1
                total += stat.st_size
                reporter.report("planning", count, total)
            if not catalog.db.execute("SELECT 1 FROM files WHERE rel='birth.json'").fetchone():
                raise SeedError("备份缺少出生记录。")
            processed, completed, index_bytes = 0, 0, 0
            index_digest = hashlib.sha256()
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                reporter.report("writing", 0, 0, total, force=True)
                for relative, expected_size, _, signature in catalog.entries():
                    path = _path(root, relative)
                    digest, size = hashlib.sha256(), 0
                    with path.open("rb") as source, archive.open("pack/" + relative, "w", force_zip64=True) as target:
                        if _signature(os.fstat(source.fileno())) != signature:
                            raise SeedError("备份期间来源发生变化，未发布不一致的备份。")
                        while block := source.read(CHUNK):
                            digest.update(block)
                            size += len(block)
                            if size > expected_size:
                                raise SeedError("备份期间来源发生变化，未发布不一致的备份。")
                            target.write(block)
                            processed += len(block)
                            reporter.report("writing", completed, processed, total)
                        if size != expected_size or _signature(os.fstat(source.fileno())) != signature:
                            raise SeedError("备份期间来源发生变化，未发布不一致的备份。")
                    line = _encode({"path": relative, "size": size, "sha256": digest.hexdigest()}) + b"\n"
                    if len(line) > ENTRY_LIMIT:
                        raise SeedError("备份中的单条路径记录过长。")
                    index.write(line)
                    index_bytes += len(line)
                    index_digest.update(line)
                    completed += 1
                # Cooperating writers hold the same lock. Also detect ordinary
                # external changes; filesystem metadata is not tamper-proof.
                observed = 0
                for relative, path in _files(root):
                    expected = catalog.db.execute("SELECT signature FROM files WHERE rel=?", (relative,)).fetchone()
                    if not expected or _signature(_source_stat(path)) != expected[0]:
                        raise SeedError("备份期间来源发生变化，未发布不一致的备份。")
                    observed += 1
                    reporter.report("writing", completed, processed, total)
                if observed != count:
                    raise SeedError("备份期间来源发生变化，未发布不一致的备份。")
                index.seek(0)
                with archive.open(INDEX, "w", force_zip64=True) as target:
                    while block := index.read(CHUNK):
                        target.write(block)
                        reporter.report("writing", completed, processed, total)
                manifest = {"format": FORMAT, "created_at": now_iso(), "pack_name": root.name,
                            "file_count": count, "source_bytes": total, "index": INDEX,
                            "index_bytes": index_bytes, "index_sha256": index_digest.hexdigest()}
                archive.writestr(MANIFEST, _encode(manifest))
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            reporter.report("publishing", count, total, total, force=True)
            _publish_file(temporary, output)
        return {"file": str(output), "files": count, "source_bytes": total, "format": FORMAT}
    finally:
        temporary.unlink(missing_ok=True)


def _header(archive):
    try:
        info = archive.getinfo(MANIFEST)
    except KeyError as error:
        raise SeedError("备份缺少清单。") from error
    if info.file_size > MANIFEST_LIMIT:
        raise SeedError("旧版备份清单过大，无法安全读取；新版使用逐条清单。")
    raw = archive.read(info)
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("format") not in (FORMAT, LEGACY_FORMAT):
        raise SeedError("这不是支持的 SEEDbank 备份格式。")
    if doc["format"] == FORMAT:
        if (len(raw) > HEADER_LIMIT or doc.get("index") != INDEX
                or any(type(doc.get(key)) is not int or doc[key] < 0 for key in ("file_count", "source_bytes", "index_bytes"))
                or not re.fullmatch(r"[0-9a-f]{64}", str(doc.get("index_sha256", "")))):
            raise SeedError("新版备份头不完整。")
    elif not isinstance(doc.get("files"), list):
        raise SeedError("旧版备份清单不完整。")
    return doc, hashlib.sha256(raw).hexdigest()


def _index_rows(archive, doc):
    if doc["format"] == LEGACY_FORMAT:
        yield from doc["files"]
        return
    try:
        info = archive.getinfo(INDEX)
    except KeyError as error:
        raise SeedError("备份缺少逐条文件清单。") from error
    if info.file_size != doc["index_bytes"]:
        raise SeedError("备份文件清单大小不符。")
    digest, size = hashlib.sha256(), 0
    with archive.open(info) as incoming:
        while line := incoming.readline(ENTRY_LIMIT + 1):
            if len(line) > ENTRY_LIMIT or not line.endswith(b"\n"):
                raise SeedError("备份文件清单行过长或不完整。")
            digest.update(line)
            size += len(line)
            yield json.loads(line.decode("utf-8"))
    if size != doc["index_bytes"] or digest.hexdigest() != doc["index_sha256"]:
        raise SeedError("备份文件清单摘要不符。")


def _plan(archive, catalog, base, reporter, *, expected=""):
    for info in archive.infolist():
        mode = (info.external_attr >> 16) & 0o170000
        if info.flag_bits & 1 or info.is_dir() or mode not in (0, 0o100000) or not 0 <= info.file_size < 2 ** 63:
            raise SeedError("备份不支持加密成员、链接、目录成员或特殊文件。")
        try:
            catalog.db.execute("INSERT INTO members VALUES (?,?)", (info.filename, info.file_size))
        except sqlite3.IntegrityError as error:
            raise SeedError("备份存在重复 ZIP 路径。") from error
        reporter.report("reading")
    doc, fingerprint = _header(archive)
    if expected and expected != fingerprint:
        raise SeedError("备份清单已变化，请重新读取备份信息后再恢复。")
    count, total = 0, 0
    for entry in _index_rows(archive, doc):
        if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                or type(entry.get("size")) is not int or not 0 <= entry["size"] < 2 ** 63
                or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))):
            raise SeedError("备份文件清单不完整。")
        relative = entry["path"]
        _path(base, relative)
        member = catalog.db.execute("SELECT size FROM members WHERE name=?", ("pack/" + relative,)).fetchone()
        if not member or member[0] != entry["size"]:
            raise SeedError("备份文件缺失或大小与清单不符。")
        catalog.add(relative, entry["size"], entry["sha256"])
        count += 1
        total += entry["size"]
        reporter.report("reading", count, total)
    expected_members = count + (2 if doc["format"] == FORMAT else 1)
    if (catalog.db.execute("SELECT COUNT(*) FROM members").fetchone()[0] != expected_members
            or not catalog.db.execute("SELECT 1 FROM files WHERE rel='birth.json'").fetchone()):
        raise SeedError("备份内容与清单不一致，或缺少出生记录。")
    if doc["format"] == FORMAT and (count != doc["file_count"] or total != doc["source_bytes"]):
        raise SeedError("备份文件总数或总大小与清单不符。")
    return {"format": doc["format"], "created_at": str(doc.get("created_at") or ""),
            "pack_name": str(doc.get("pack_name") or ""), "files": count, "source_bytes": total,
            "manifest_digest": fingerprint, "contents_verified": False}


def inspect_backup(backup, *, progress=None, cancel=None):
    """Read inventory and metadata; payloads are checked during restoration."""
    source = Path(backup).expanduser().resolve()
    reporter = _Progress(progress, cancel)
    try:
        with zipfile.ZipFile(source, "r") as archive, _Catalog() as catalog:
            base = catalog.path.parent / (".seedbank-preview-" + uuid.uuid4().hex)
            result = _plan(archive, catalog, base, reporter)
            return {**result, "file": str(source), "archive_bytes": source.stat().st_size}
    except (ValueError, zipfile.BadZipFile, RuntimeError) as error:
        raise SeedError("备份无法读取；原备份和现有生命包均保留。") from error


def _parents(staging, relative, catalog):
    parts = relative.split("/")
    for depth in range(1, len(parts)):
        parent = "/".join(parts[:depth])
        folder = _path(staging, parent)
        owned = catalog.db.execute("SELECT created FROM dirs WHERE key=?", (_key(parent),)).fetchone()[0]
        if not owned:
            folder.mkdir(exist_ok=False)
            catalog.db.execute("UPDATE dirs SET created=1 WHERE key=?", (_key(parent),))


def _cleanup(staging, catalog):
    # Only our own files and empty directories. Never sweep other leftovers.
    for relative, _, _, _ in catalog.entries(created=True):
        try:
            _path(staging, relative).unlink(missing_ok=True)
        except (OSError, SeedError):
            pass
    for (relative,) in catalog.db.execute("SELECT rel FROM dirs WHERE created=1 ORDER BY depth DESC"):
        try:
            _path(staging, relative).rmdir()
        except (OSError, SeedError):
            pass
    try:
        staging.rmdir()
    except OSError:
        pass


def restore(backup, destination, *, expected="", progress=None, cancel=None):
    source = Path(backup).expanduser().resolve()
    target = Path(destination).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise SeedError("恢复目标必须是尚不存在的新文件夹；不会覆盖现有生命包。")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name("." + target.name + ".restore-" + uuid.uuid4().hex)
    staging.mkdir(exist_ok=False)
    staging = staging.resolve()
    reporter = _Progress(progress, cancel)
    published = False
    try:
        with _Catalog(target.parent) as catalog:
            try:
                with zipfile.ZipFile(source, "r") as archive:
                    inventory = _plan(archive, catalog, staging, reporter, expected=expected)
                    processed, completed = 0, 0
                    total = inventory["source_bytes"]
                    reporter.report("restoring", 0, 0, total, force=True)
                    for relative, expected_size, expected_hash, _ in catalog.entries():
                        _parents(staging, relative, catalog)
                        file = _path(staging, relative)
                        digest, size = hashlib.sha256(), 0
                        with archive.open("pack/" + relative) as incoming, file.open("xb") as outgoing:
                            catalog.db.execute("UPDATE files SET created=1 WHERE rel=?", (relative,))
                            while block := incoming.read(CHUNK):
                                size += len(block)
                                if size > expected_size:
                                    raise SeedError("解压内容超出清单大小，恢复已停止。")
                                digest.update(block)
                                outgoing.write(block)
                                processed += len(block)
                                reporter.report("restoring", completed, processed, total)
                            outgoing.flush()
                            os.fsync(outgoing.fileno())
                        if size != expected_size or digest.hexdigest() != expected_hash:
                            raise SeedError("备份校验不一致；未发布恢复包。")
                        completed += 1
                    birth = json.loads((staging / "birth.json").read_text(encoding="utf-8-sig"))
                    if not isinstance(birth, dict) or not isinstance(birth.get("name"), str) or not birth["name"] or not birth.get("born_at"):
                        raise SeedError("备份出生记录不完整。")
                reporter.report("publishing", completed, processed, total, force=True)
                if target.exists() or target.is_symlink():
                    raise SeedError("恢复期间目标文件夹已出现；未覆盖它。")
                os.rename(staging, target)  # Windows never replaces an existing directory here.
                published = True
                return {"pack": str(target), "files": completed, "source_bytes": total,
                        "name": birth["name"], "format": inventory["format"], "contents_verified": True}
            finally:
                if not published:
                    _cleanup(staging, catalog)
    except (ValueError, zipfile.BadZipFile, RuntimeError) as error:
        raise SeedError("备份无法读取；原备份和现有生命包均保留。") from error
    finally:
        if not published:
            try:
                staging.rmdir()
            except OSError:
                pass
