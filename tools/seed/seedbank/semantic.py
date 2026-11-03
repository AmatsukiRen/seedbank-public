"""Opt-in embeddings in the disposable search cache, with live recall policy.

No download, provider request or corpus migration occurs merely on import.
Enablement authorizes bounded indexing/query requests to the configured service.
"""
from __future__ import annotations

from collections import OrderedDict
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .pack_lock import durable, serialized
from .util import SeedError, now_iso, read_json, sha256, write_json_atomic

FORMAT = "seedbank/semantic@1"
ENCODER = "plain-chunks-v1"
CHUNK_CHARS = 400
OVERLAP = 60
MAX_DIMENSIONS = 8192
MAX_RESPONSE = 16 * 1024 * 1024
MAX_INPUT_BYTES = 8000
MAX_BATCH_BYTES = 64000
DEFAULTS = {"format": FORMAT, "enabled": False, "model": "", "base_url": "http://localhost:11434/v1",
            "api_key_env": "", "revision": "1", "min_similarity": 0.55,
            "query_prefix": "", "document_prefix": ""}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_QUERIES = OrderedDict()
_STATUS = OrderedDict()
_FAILURES = OrderedDict()


class SemanticError(SeedError):
    pass


def configuration(pack):
    data = read_json(Path(pack) / "mind/semantic.json", {})
    if not isinstance(data, dict):
        raise SemanticError("语义检索配置不是对象；原文件已保留。")
    return clean({**DEFAULTS, **data})


def clean(data):
    cfg = {key: data.get(key, value) for key, value in DEFAULTS.items()}
    if cfg["format"] != FORMAT:
        raise SemanticError("不认识的语义检索配置格式，原文件已保留。")
    if type(cfg["enabled"]) is not bool:
        raise SemanticError("语义检索开关必须是 true 或 false。")
    for key in ("model", "base_url", "api_key_env", "revision", "query_prefix", "document_prefix"):
        if not isinstance(cfg[key], str) or len(cfg[key]) > 1000 or any(ord(c) < 32 for c in cfg[key]):
            raise SemanticError("语义检索配置含无效字段。")
    for key in ("model", "base_url", "api_key_env", "revision"):
        cfg[key] = cfg[key].strip()
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    try:
        address = urlparse(cfg["base_url"])
        port = address.port
    except ValueError:
        raise SemanticError("语义接口地址或端口无效。") from None
    if (address.scheme not in ("http", "https") or not address.hostname or address.username or address.password
            or address.query or address.fragment or port == 0
            or (address.scheme == "http" and address.hostname.lower() not in LOCAL_HOSTS)):
        raise SemanticError("语义接口需使用 HTTPS（本机可用 HTTP），地址不能包含密钥、账号或查询参数。")
    if cfg["api_key_env"] and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cfg["api_key_env"]):
        raise SemanticError("请填写语义服务的密钥环境变量名，不要填写密钥。")
    try:
        minimum = float(cfg["min_similarity"])
    except (ValueError, TypeError):
        raise SemanticError("语义相似度下限需要 0 到 1 之间的数值。") from None
    if type(cfg["min_similarity"]) is bool or not math.isfinite(minimum) or not 0 <= minimum <= 1:
        raise SemanticError("语义相似度下限需要 0 到 1 之间的数值。")
    cfg["min_similarity"] = minimum
    if cfg["enabled"] and not cfg["model"]:
        raise SemanticError("启用语义检索前，请填写嵌入模型名称。")
    if not cfg["revision"]:
        raise SemanticError("语义模型版本标记不能为空。")
    cfg["format"] = FORMAT
    return cfg


@durable
def configure(pack, patch):
    cfg = clean({**configuration(pack), **{k: v for k, v in patch.items() if k in DEFAULTS}})
    write_json_atomic(Path(pack) / "mind/semantic.json", cfg)
    _FAILURES.pop(_key(pack), None)
    return cfg


def profile(cfg):
    return sha256(json.dumps({"encoder": ENCODER, **{k: cfg[k] for k in
                  ("base_url", "model", "revision", "query_prefix", "document_prefix")}}, sort_keys=True))


def _key(pack):
    return str(Path(pack).resolve())


def note(pack, state, **fields):
    key = _key(pack)
    _STATUS[key] = {"state": state, "at": now_iso(), **fields}
    _STATUS.move_to_end(key)
    while len(_STATUS) > 32:
        _STATUS.popitem(last=False)


def last_status(pack):
    return dict(_STATUS.get(_key(pack), {"state": "not_used"}))


def failed(pack, error):
    _FAILURES[_key(pack)] = time.monotonic()
    _FAILURES.move_to_end(_key(pack))
    while len(_FAILURES) > 32:
        _FAILURES.popitem(last=False)
    note(pack, "lexical_fallback", error_type=type(error).__name__)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(cfg, texts):
    """OpenAI-compatible embeddings; no redirects, no response-body error logs."""
    headers = {"Content-Type": "application/json"}
    local = urlparse(cfg["base_url"]).hostname.lower() in LOCAL_HOSTS
    if not local and cfg["api_key_env"]:
        key = os.environ.get(cfg["api_key_env"], "")
        if not key:
            raise SemanticError("没有找到语义服务的密钥环境变量。")
        headers["Authorization"] = "Bearer " + key
    payload = json.dumps({"model": cfg["model"], "input": texts, "encoding_format": "float"}).encode("utf-8")
    request = urllib.request.Request(cfg["base_url"] + "/embeddings", data=payload, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=15) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise SemanticError("语义服务返回过大；没有更新索引。")
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SemanticError(f"语义服务 HTTP {error.code}；没有使用响应正文作为记忆。") from None
    except (urllib.error.URLError, OSError, UnicodeError, json.JSONDecodeError):
        raise SemanticError("语义服务不可用或返回内容无法读取。") from None


def _vector(values):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_DIMENSIONS:
        raise SemanticError("语义向量维度无效。")
    try:
        valid = all(type(v) in (float, int) and math.isfinite(v) for v in values)
    except OverflowError:
        valid = False
    if not valid:
        raise SemanticError("语义向量包含无效数值。")
    scale = max(abs(v) for v in values)
    if not scale:
        raise SemanticError("语义服务返回零向量。")
    scaled = [v / scale for v in values]
    norm = math.sqrt(math.fsum(v * v for v in scaled))
    return [v / norm for v in scaled]


def embed(cfg, texts):
    sizes = [len(text.encode("utf-8")) for text in texts]
    if (not texts or len(texts) > 64 or sum(sizes) > MAX_BATCH_BYTES
            or any(not text.strip() or size > MAX_INPUT_BYTES for text, size in zip(texts, sizes))):
        raise SemanticError("语义请求超过单批容量。")
    payload = _request(cfg, texts)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != len(texts):
        raise SemanticError("语义服务没有返回完整的输入对应关系。")
    vectors = [None] * len(texts)
    for row in data:
        index = row.get("index") if isinstance(row, dict) else None
        if type(index) is not int or not 0 <= index < len(texts) or vectors[index] is not None:
            raise SemanticError("语义向量编号缺失、重复或越界。")
        vectors[index] = _vector(row.get("embedding"))
    dimensions = {len(v) for v in vectors}
    if len(dimensions) != 1:
        raise SemanticError("同批语义向量的维度不一致。")
    returned_model = payload.get("model")
    if not isinstance(returned_model, str) or not returned_model or len(returned_model) > 1000:
        raise SemanticError("语义服务未标明返回模型，不能混入现有索引。")
    return vectors, {"dimensions": len(vectors[0]), "returned_model": returned_model}


def _schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS semantic_documents (entry_id TEXT PRIMARY KEY, stamp TEXT);
        CREATE TABLE IF NOT EXISTS semantic_chunks (
            entry_id TEXT, ordinal INTEGER, digest TEXT, start INTEGER, end INTEGER,
            PRIMARY KEY(entry_id, ordinal));
        CREATE INDEX IF NOT EXISTS semantic_digest ON semantic_chunks(digest);
        CREATE TABLE IF NOT EXISTS semantic_vectors (
            profile TEXT, digest TEXT, dimensions INTEGER, vector BLOB, checksum TEXT,
            PRIMARY KEY(profile, digest));
        CREATE TABLE IF NOT EXISTS semantic_spaces (profile TEXT PRIMARY KEY, description TEXT);
    """)


def _stamp(row):
    return sha256(json.dumps([ENCODER, row.get("kind", ""), row.get("text", "")], ensure_ascii=False))


def _chunk_text(row, start, end):
    # No old-text search aliases, summaries or model-generated substitutes.
    return str(row.get("kind", "")) + "\n" + str(row.get("text", ""))[start:end]


def catalog(db, policy):
    """Refresh chunk references locally; preserve vectors by exact content hash."""
    from .retrieval import _eligible
    _schema(db)
    with db:
        db.execute("CREATE TEMP TABLE IF NOT EXISTS semantic_allowed (id TEXT PRIMARY KEY)")
        db.execute("DELETE FROM semantic_allowed")
        for identifier, payload, old_stamp in db.execute(
                "SELECT e.id,e.payload,d.stamp FROM entries e LEFT JOIN semantic_documents d ON e.id=d.entry_id"):
            row = json.loads(payload)
            if not _eligible(row, policy, True, None, None):
                continue
            db.execute("INSERT OR IGNORE INTO semantic_allowed VALUES (?)", (identifier,))
            stamp = _stamp(row)
            if stamp == old_stamp:
                continue
            db.execute("DELETE FROM semantic_chunks WHERE entry_id=?", (identifier,))
            text = str(row.get("text", ""))
            for ordinal, start in enumerate(range(0, len(text), CHUNK_CHARS - OVERLAP)):
                end = min(len(text), start + CHUNK_CHARS)
                body = _chunk_text(row, start, end)
                db.execute("INSERT INTO semantic_chunks VALUES (?, ?, ?, ?, ?)",
                           (identifier, ordinal, sha256(body), start, end))
                if end == len(text):
                    break
            db.execute("INSERT OR REPLACE INTO semantic_documents VALUES (?, ?)", (identifier, stamp))
        if not getattr(policy, "restricted", False):
            db.execute("DELETE FROM semantic_documents WHERE entry_id NOT IN (SELECT id FROM semantic_allowed)")
            db.execute("DELETE FROM semantic_chunks WHERE entry_id NOT IN (SELECT id FROM semantic_allowed)")
            db.execute("DELETE FROM semantic_vectors WHERE digest NOT IN (SELECT digest FROM semantic_chunks)")


def _space(db, space, description):
    old = db.execute("SELECT description FROM semantic_spaces WHERE profile=?", (space,)).fetchone()
    if old and json.loads(old[0]) != description:
        raise SemanticError("语义模型标识或维度已变化，请修改版本标记或清空语义缓存后重新建立。")
    return old


def counts(db, cfg, *, scoped=False):
    subset = "SELECT digest FROM semantic_chunks" + (" WHERE entry_id IN (SELECT id FROM semantic_allowed)" if scoped else "")
    total = db.execute("SELECT COUNT(DISTINCT digest) FROM (" + subset + ")").fetchone()[0]
    ready = db.execute("SELECT COUNT(*) FROM semantic_vectors WHERE profile=? AND digest IN (" + subset + ")",
                       (profile(cfg),)).fetchone()[0]
    return {"total_chunks": total, "indexed_chunks": ready, "pending_chunks": total - ready}


def index_batch(pack, db, cfg, policy, limit=8):
    catalog(db, policy)
    space = profile(cfg)
    selected = {}
    byte_count = 0
    for digest, payload, start, end in db.execute(
            "SELECT c.digest,e.payload,c.start,c.end FROM semantic_chunks c JOIN entries e ON c.entry_id=e.id "
            "JOIN semantic_allowed a ON a.id=c.entry_id "
            "LEFT JOIN semantic_vectors v ON v.profile=? AND v.digest=c.digest WHERE v.digest IS NULL "
            "ORDER BY c.entry_id,c.ordinal", (space,)):
        if digest not in selected:
            body = cfg["document_prefix"] + _chunk_text(json.loads(payload), start, end)
            size = len(body.encode("utf-8"))
            if selected and byte_count + size > MAX_BATCH_BYTES:
                break
            selected[digest] = body
            byte_count += size
        if len(selected) >= limit:
            break
    if selected:
        vectors, description = embed(cfg, list(selected.values()))
        _space(db, space, description)
        with db:
            db.execute("INSERT OR REPLACE INTO semantic_spaces VALUES (?, ?)", (space, json.dumps(description)))
            for digest, vector in zip(selected, vectors):
                raw = struct.pack(f"<{len(vector)}f", *vector)
                db.execute("INSERT OR REPLACE INTO semantic_vectors VALUES (?, ?, ?, ?, ?)",
                           (space, digest, len(vector), raw, sha256(raw)))
    return {**counts(db, cfg, scoped=True), "added_chunks": len(selected)}


def _query(pack, db, cfg, text):
    space = profile(cfg)
    key = (_key(pack), space, text)
    previous = _QUERIES.get(key)
    if previous and time.monotonic() - previous[0] < 300:
        _space(db, space, previous[2])
        _QUERIES.move_to_end(key)
        return previous[1]
    vectors, description = embed(cfg, [cfg["query_prefix"] + text])
    _space(db, space, description)
    _QUERIES[key] = (time.monotonic(), vectors[0], description)
    while len(_QUERIES) > 64:
        _QUERIES.popitem(last=False)
    return vectors[0]


def candidates(pack, db, query, policy, *, historical=False, after=None, before=None, limit=40):
    """Return best matching full source rows, filtered using live policy."""
    from .retrieval import _eligible
    cfg = configuration(pack)
    if not cfg["enabled"]:
        note(pack, "disabled")
        return []
    if time.monotonic() - _FAILURES.get(_key(pack), -1e9) < 60:
        note(pack, "lexical_fallback", error_type="RetryCooldown")
        return []
    progress = index_batch(pack, db, cfg, policy, 8)
    if not progress["indexed_chunks"]:
        note(pack, "empty", **progress)
        return []
    # Long queries fall back to lexical; do not silently embed only a prefix.
    vector = _query(pack, db, cfg, str(query))
    winners = {}
    for identifier, payload, stamp, dimensions, raw, checksum in db.execute(
            "SELECT e.id,e.payload,d.stamp,v.dimensions,v.vector,v.checksum FROM semantic_chunks c "
            "JOIN entries e ON e.id=c.entry_id JOIN semantic_documents d ON d.entry_id=e.id "
            "JOIN semantic_vectors v ON v.digest=c.digest AND v.profile=?", (profile(cfg),)):
        row = json.loads(payload)
        if not _eligible(row, policy, historical, after, before) or _stamp(row) != stamp:
            continue
        if (type(dimensions) is not int or not isinstance(raw, bytes) or dimensions != len(vector)
                or len(raw) != dimensions * 4 or sha256(raw) != checksum):
            raise SemanticError("语义缓存维度不一致，请清空语义缓存后重建。")
        stored = struct.unpack(f"<{dimensions}f", raw)
        if any(not math.isfinite(v) for v in stored):
            raise SemanticError("语义缓存包含无效数值。")
        score = max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(vector, stored))))
        if score < cfg["min_similarity"] or score <= winners.get(identifier, ({}, -2))[1]:
            continue
        winners[identifier] = (row, score)
        if len(winners) > limit:
            del winners[min(winners, key=lambda key: winners[key][1])]
    note(pack, "hybrid", **progress, matches=len(winners), model=cfg["model"])
    _FAILURES.pop(_key(pack), None)
    return sorted(winners.values(), key=lambda item: item[1], reverse=True)


@serialized
def manage(pack, action="status", *, limit=64):
    from .retrieval import _connection, sync
    from .memory_state import MemoryPolicy
    cfg = configuration(pack)
    if not (Path(pack) / "birth.json").is_file():
        raise SemanticError("不是生命包：缺少 birth.json。")
    if action not in ("status", "index", "clear"):
        raise SemanticError("语义索引操作只能是 status / index / clear。")
    db = _connection(pack)
    try:
        sync(pack, db)
        policy = MemoryPolicy.load(pack)
        if action != "index":
            catalog(db, policy)
        if action == "clear":
            with db:
                db.execute("DELETE FROM semantic_vectors WHERE profile=?", (profile(cfg),))
                db.execute("DELETE FROM semantic_spaces WHERE profile=?", (profile(cfg),))
            for key in list(_QUERIES):
                if key[0] == _key(pack):
                    del _QUERIES[key]
            note(pack, "cleared")
            _FAILURES.pop(_key(pack), None)
        if action == "index":
            if not cfg["enabled"]:
                raise SemanticError("请先启用并保存语义检索设置。")
            result = index_batch(pack, db, cfg, policy, max(1, min(int(limit), 64)))
            note(pack, "indexed", **result)
            _FAILURES.pop(_key(pack), None)
        result = counts(db, cfg)
        return {**result, "enabled": cfg["enabled"], "model": cfg["model"], "profile": profile(cfg),
                "last_query": last_status(pack), "scope": "recallable_history"}
    finally:
        db.close()
