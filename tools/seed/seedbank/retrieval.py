"""Rebuildable local search over memories and the original life archive.

CJK n-grams and Unicode word tokens need no downloaded model or service. A model
may reformulate a query via the bounded memory_search protocol; this index
does not pretend lexical similarity is semantic certainty.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from . import experience, file_state, jsonl
from .memory_state import MemoryPolicy, source_file, is_template
from .pack_lock import serialized
from .util import SeedError, list_days, read_memories, sha256

VERSION = "12"
STOP = {"什么", "怎么", "如何", "是否", "以前", "之前", "记得", "记忆", "那个", "这个", "我们", "你的", "我的", "说过", "还记", "得我", "提过", "一下"}
_CJK = r"\u3005\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3\U00020000-\U0002fa1f"
# Separate mixed-script runs as well: an initial Latin word must not swallow
# adjacent kana/Hangul. Normalization is only for matching, never source text.
_TOKEN_RUNS = re.compile(fr"([{_CJK}]+)|([^\W{_CJK}]+)")


def tokens(text):
    out = []
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    for cjk, word in _TOKEN_RUNS.findall(normalized):
        if word:
            out.append(word)
        elif len(cjk) == 1:
            out.append(cjk)
        else:
            out.extend(cjk[i:i + n] for n in (2, 3) for i in range(len(cjk) - n + 1)
                       if cjk[i:i + n] not in STOP)
    return list(dict.fromkeys(out))


def document_tokens(text):
    """Index embedded CJK characters for short queries as well as word spans.

    Multi-character queries still use tokens(), so searching 月光 does not
    match a document merely because 月 and 光 occur separately. Use the same
    document terms when scoring raw-archive fallback results.
    """
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    characters = (char for cjk, _ in _TOKEN_RUNS.findall(normalized) for char in cjk)
    return list(dict.fromkeys([*tokens(text), *characters]))


def _connection(pack):
    path = Path(pack) / "mind" / "search.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    try:
        db.execute("PRAGMA busy_timeout=15000")
        # A connection-local ~16 MiB page-cache target avoids excessive page
        # churn while building millions of terms. It allocates on demand and
        # leaves the index schema, journal and durability settings unchanged.
        db.execute("PRAGMA cache_size=-16384")
        db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        version = db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()
        if not version or version[0] != VERSION:
            db.executescript("DROP TABLE IF EXISTS entries; DROP TABLE IF EXISTS terms; DROP TABLE IF EXISTS sources;")
            # Only at a schema rebuild: return obsolete cache pages to disk
            # before reindexing. Raw life files never live in this database.
            db.execute("VACUUM")
        # Short composite-key terms need no separate rowid/primary-key tree.
        # Keep large entry payloads in the ordinary rowid table.
        db.executescript("""
            CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, source_key TEXT, source_ref TEXT, payload TEXT);
            CREATE INDEX IF NOT EXISTS entries_source ON entries(source_key);
            CREATE INDEX IF NOT EXISTS entries_reference ON entries(source_key, source_ref);
            CREATE TABLE IF NOT EXISTS terms (
                token TEXT NOT NULL, entry_id TEXT NOT NULL, PRIMARY KEY(token, entry_id)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS terms_entry ON terms(entry_id);
            CREATE TABLE IF NOT EXISTS sources (key TEXT PRIMARY KEY, stamp TEXT);
        """)
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('version', ?)", (VERSION,))
        db.commit()
    except Exception:
        db.close()
        raise
    return db


def _stamp(file):
    return file_state.stamp(file)


def _event_row(event):
    kind = event.get("kind", "thought")
    text = str(event.get("text", ""))
    metadata = event.get("metadata", {})
    actor = str(event.get("actor", "对方"))
    if metadata.get("audience_id") and metadata["audience_id"] != "owner":
        actor = "个体" if metadata.get("runner") else "当前交流对象"
    if kind == "conversation":
        text = actor + "：" + text
    return {"id": event["id"], "day": event["day"], "at": event.get("occurred_at"),
            "kind": kind, "text": text, "source": experience.source_of(event),
            "actor": actor,
            "archive_actor": str(event.get("actor", "对方")),
            "utterance_role": ("runtime" if metadata.get("runner") == "runtime" else
                               "model" if metadata.get("runner") else
                               "speaker" if "person_id" in metadata else "unattributed"),
            "disclosure_basis": metadata.get("source_basis", "") if kind == "disclosure" else "",
            "importance": 0.4, "tags": ["原始事件"] + (["梦"] if kind == "dream" else ["创作"] if kind == "creation" else []),
            "depends_on": event.get("depends_on", []),
            "runner": "runtime", "origin": "experience", "template_generated": is_template(event)}


def _legacy_rows(pack, day, events=(), *, covered=None):
    source = "life/" + day["file"]
    raw = (Path(pack) / source).read_text(encoding="utf-8-sig")
    if covered is None:
        covered = {(e.get("actor"), e.get("text")) for e in events if e.get("source") == source}
    section = ""
    rows = []
    for index, paragraph in enumerate(re.split(r"\n\s*\n", raw)):
        paragraph = paragraph.strip()
        if paragraph.startswith("## "):
            section = paragraph.splitlines()[0][3:].strip()
            paragraph = "\n".join(paragraph.splitlines()[1:]).strip()
        if not paragraph or paragraph.startswith("#") or paragraph == "---":
            continue
        kind = {"对话": "conversation", "感知": "perception", "见闻": "hearsay", "今天": "diary"}.get(section)
        if not kind:
            continue
        for line_no, part in enumerate(paragraph.splitlines() if section == "对话" else [paragraph]):
            match = re.match(r"^\*\*(.+?)\*\*[：:](.*)$", part)
            if match and (match[1], match[2].strip()) in covered:
                continue
            # Chunking preserves the raw source; no model invents a summary here.
            for chunk_no, start in enumerate(range(0, len(part), 1200)):
                text = part[start:start + 1200]
                identifier = "archive_" + sha256(f"{source}|{index}|{line_no}|{chunk_no}|{text}")[:24]
                rows.append({"id": identifier, "day": day["day"], "at": day["date"],
                             "kind": kind, "text": text, "source": source,
                             "importance": 0.35, "tags": ["原始档案", section],
                             "origin": "legacy_archive", "runner": "archive"})
    return rows


def _upsert(db, key, stamp, rows):
    for row in rows:
        identifier = str(row.get("id") or "")
        if not identifier or not row.get("text"):
            continue
        db.execute("DELETE FROM terms WHERE entry_id=?", (identifier,))
        db.execute("INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?)",
                   (identifier, key, source_file(row.get("source")), json.dumps(row, ensure_ascii=False)))
        words = document_tokens(str(row.get("text")) + " " + str(row.get("search_aliases", ""))
                       + " " + " ".join(str(t) for t in row.get("tags", [])))
        db.executemany("INSERT OR IGNORE INTO terms VALUES (?, ?)", ((word, identifier) for word in words))
    db.execute("INSERT OR REPLACE INTO sources VALUES (?, ?)", (key, stamp))


def _replace(db, key, stamp, rows):
    db.execute("DELETE FROM terms WHERE entry_id IN (SELECT id FROM entries WHERE source_key=?)", (key,))
    db.execute("DELETE FROM entries WHERE source_key=?", (key,))
    _upsert(db, key, stamp, rows)


def _aliases(db, rows, *, incremental=False):
    originals = {str(row.get("id")): row for row in rows}
    for row in rows:
        target = str(row.get("supersedes") or "")
        original = originals.get(target)
        if incremental and target and original is None:
            stored = db.execute("SELECT payload FROM entries WHERE id=? AND source_key='memories'", (target,)).fetchone()
            original = json.loads(stored[0]) if stored else {}
        yield {**row, "search_aliases": str((original or {}).get("text", ""))}


def _covered(db, source):
    covered = set()
    for payload, in db.execute("SELECT payload FROM entries WHERE source_key='experiences' AND source_ref=?", (source,)):
        row = json.loads(payload)
        if row.get("kind") == "conversation":
            actor = row["actor"]
            covered.add((row.get("archive_actor", actor), row["text"][len(actor) + 1:]))
    return covered


def sync(pack, db):
    """Index known appends only; fall back to source rebuild after other edits."""
    stamps = dict(db.execute("SELECT key, stamp FROM sources"))
    files = [("memories", Path(pack) / "mind" / "memories.jsonl")]
    event_file = experience.path(pack)
    files.append(("experiences", event_file))
    files.append(("development", Path(pack) / "mind/development.jsonl"))
    days = list_days(pack)
    by_source = {"life/" + day["file"]: day for day in days}
    files.extend((key, Path(pack) / key) for key in by_source)
    active = {key for key, file in files if file.exists()}
    changed_sources = set()
    with db:
        for key in set(stamps) - active:
            if key == "experiences":
                changed_sources.update(row[0] for row in db.execute(
                    "SELECT DISTINCT source_ref FROM entries WHERE source_key='experiences'"))
            _replace(db, key, "", [])
            db.execute("DELETE FROM sources WHERE key=?", (key,))
        for key, file in files:
            if not file.exists():
                continue
            stamp = _stamp(file)
            if stamps.get(key) == stamp and key not in changed_sources:
                continue
            if key in ("memories", "experiences", "development"):
                delta = jsonl.changes_since(file, stamps[key]) if key in stamps else None
                if key == "memories":
                    rows = _aliases(db, read_memories(pack) if delta is None else delta,
                                    incremental=delta is not None)
                elif key == "experiences":
                    events = experience.read(pack) if delta is None else delta
                    if delta is None:
                        changed_sources.update(row[0] for row in db.execute(
                            "SELECT DISTINCT source_ref FROM entries WHERE source_key='experiences'"))
                    changed_sources.update(source_file(row.get("source")) for row in events)
                    rows = (_event_row(row) for row in events)
                else:
                    from .development import events as development_events
                    from .action_archive import from_event
                    from .goal_history import project as goal_project
                    from .judgment_history import project as judgment_project
                    events = development_events(pack) if delta is None else delta
                    rows = (projected for event in events if (projected := (goal_project(event) or judgment_project(event) or from_event(event))) is not None)
                if delta is None:
                    # Materialize aliases before replacing their old source.
                    _replace(db, key, stamp, list(rows))
                else:
                    _upsert(db, key, stamp, rows)
            else:
                rows = _legacy_rows(pack, by_source[key], covered=_covered(db, key))
                _replace(db, key, stamp, rows)


class RecallRangeError(SeedError):
    """An invalid requested range must never become an unrestricted search."""


def date_range(first=None, last=None):
    from .deadlines import calendar_date
    try:
        first, last = calendar_date(first, optional=True), calendar_date(last, optional=True)
    except SeedError:
        raise RecallRangeError("回查起止日期需要有效的 YYYY-MM-DD；不知道时请留空。") from None
    if first and last and first > last:
        raise RecallRangeError("回查开始日期不能晚于结束日期。")
    return date.fromisoformat(first) if first else None, date.fromisoformat(last) if last else None


def _date(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _archive_candidates(pack):
    """Read source files when the disposable index is unavailable."""
    memories = read_memories(pack)
    originals = {str(row.get("id")): row for row in memories}
    for row in memories:
        yield {**row, "search_aliases": str(originals.get(str(row.get("supersedes")), {}).get("text", ""))}
    events = experience.read(pack)
    yield from (_event_row(row) for row in events)
    from .development import events as development_events
    from .action_archive import from_event
    from .goal_history import project as goal_project
    from .judgment_history import project as judgment_project
    yield from (projected for event in development_events(pack) if (projected := (goal_project(event) or judgment_project(event) or from_event(event))) is not None)
    for day in list_days(pack):
        yield from _legacy_rows(pack, day, events)


def _eligible(row, policy, historical, after, before):
    if row.get("origin") == "judgment_archive" or row.get("id") in policy.judgment_rows:
        from .judgment_history import eligible
        if not eligible(row, policy):
            return False
    if row.get("origin") == "goal_archive" or row.get("id") in policy.goal_rows:
        from .goal_history import eligible
        if not eligible(row, policy):
            return False
    if row.get("origin") == "action_archive" or row.get("id") in policy.action_rows:
        from .action_archive import eligible
        if not eligible(row, policy):
            return False
    if row.get("kind") == "life_story":
        # Chapters have their own version-aware context; raw old prose must not
        # bypass it through the general memory or embedding index.
        return False
    if not policy.allows(row, historical=historical):
        return False
    if row.get("origin") == "legacy_archive":
        source = source_file(row.get("source"))
        if source in policy.affected_sources or (not historical and source in policy.revised_sources):
            return False
    recorded = _date(row.get("at"))
    return not ((after and (recorded is None or recorded < after))
                or (before and (recorded is None or recorded > before)))


@serialized
def search(pack, query="", k=8, *, date_from=None, date_to=None, historical=False, policy=None, use_semantic=True):
    from . import semantic
    # Validate requested filters before loading or indexing any source, and
    # before an optional embedding request can leave this process.
    after, before = date_range(date_from, date_to)
    policy = policy if policy is not None else MemoryPolicy.load(pack)
    semantic_rows = []
    semantic.note(pack, "not_used" if not query else "disabled")
    enabled = False
    if query and use_semantic:
        try:
            enabled = semantic.configuration(pack)["enabled"]
            if enabled:
                # Refresh policy under the writer lock before any corpus leaves
                # the process, even if a caller supplied an older policy view.
                policy = policy.refresh() if hasattr(policy, "refresh") else MemoryPolicy.load(pack)
        except (SeedError, OSError, ValueError) as error:
            enabled = False
            semantic.note(pack, "lexical_fallback", error_type=type(error).__name__)
    terms = tokens(query)[:96]
    if query and not terms and not enabled:
        return []
    if not query:
        candidates = policy.visible(historical=historical)
    else:
        db = None
        try:
            db = _connection(pack)
            sync(pack, db)
            marks = ",".join("?" for _ in terms)
            candidates = []
            lexical_rows = db.execute(
                f"SELECT e.payload FROM entries e JOIN terms t ON e.id=t.entry_id WHERE t.token IN ({marks}) "
                "GROUP BY e.id ORDER BY COUNT(*) DESC, e.id", terms) if terms else []
            for payload, in lexical_rows:
                row = json.loads(payload)
                if _eligible(row, policy, historical, after, before):
                    candidates.append(row)
                    if len(candidates) >= 120:
                        break
            if enabled:
                try:
                    semantic_rows = semantic.candidates(pack, db, query, policy, historical=historical,
                                                         after=after, before=before)
                except (SeedError, OSError, ValueError, ArithmeticError, sqlite3.Error) as error:
                    semantic.failed(pack, error)
        except (sqlite3.Error, json.JSONDecodeError) as error:
            semantic.note(pack, "lexical_fallback", error_type=type(error).__name__)
            print(f"[seed] 记忆索引暂不可用（{type(error).__name__}），改为回查原始档案。", file=sys.stderr)
            candidates = _archive_candidates(pack)
        finally:
            if db is not None:
                db.close()
    today = datetime.now().date()
    results = []
    seen = set()
    for row in candidates:
        if not _eligible(row, policy, historical, after, before):
            continue
        recorded = _date(row.get("at"))
        row_tokens = set(document_tokens(row.get("text", "") + " " + str(row.get("search_aliases", ""))
                                + " " + " ".join(str(t) for t in row.get("tags", []))))
        matches = len(set(terms) & row_tokens)
        if terms and not matches:
            continue
        relevance = matches / max(1, len(terms))
        recency = 0.5 ** (max(0, (today - recorded).days) / 30) if recorded else 0.0
        try:
            importance = float(row.get("importance", 0.3))
        except (ValueError, TypeError):
            importance = 0.3
        importance = min(1.0, max(0.0, importance)) if math.isfinite(importance) else 0.3
        key = str(row.get("text", "")).strip()
        if key in seen:
            continue
        seen.add(key)
        row = policy.annotate(row)
        if historical and row.get("origin") == "legacy_archive" and source_file(row.get("source")) in policy.revised_sources:
            row = {**row, "source_has_revision": True}
        results.append({"memory": row, "score": 3 * relevance + 0.5 * importance + 0.2 * recency,
                        "parts": {"recency": recency, "importance": importance, "relevance": relevance}})
    results.sort(key=lambda r: r["score"], reverse=True)
    if semantic_rows:
        results = _fuse(results, semantic_rows, policy, historical, after, before, query)
    from .facts import annotate_recalled
    from .life_story import annotate_recalled as annotate_story
    return annotate_story(pack, annotate_recalled(pack, results[:max(1, min(int(k), 100))], policy), policy)


def _fuse(lexical, semantic_rows, policy, historical, after, before, query):
    """Reciprocal ranks; a similarity is relevance evidence, not factual truth."""
    merged = {}
    for rank, row in enumerate(lexical, 1):
        identifier = str(row["memory"]["id"])
        merged[identifier] = {**row, "score": 1 / (60 + rank),
                              "parts": {**row["parts"], "lexical_rank": rank, "lexical_score": row["score"]}}
    for rank, (memory, similarity) in enumerate(semantic_rows, 1):
        if not _eligible(memory, policy, historical, after, before):
            continue
        identifier = str(memory["id"])
        if identifier not in merged:
            annotated = policy.annotate(memory)
            if historical and memory.get("origin") == "legacy_archive" and source_file(memory.get("source")) in policy.revised_sources:
                annotated["source_has_revision"] = True
            merged[identifier] = {"memory": annotated, "score": 0, "parts": {}}
        merged[identifier]["score"] += 1 / (60 + rank)
        merged[identifier]["parts"].update(semantic_rank=rank, semantic_similarity=similarity)
    # Literal phrases remain easy to find even when meaning-neighbours are numerous.
    needle = str(query).strip().casefold()
    for row in merged.values():
        exact = len(needle) >= 2 and needle in str(row["memory"].get("text", "")).casefold()
        row["score"] += 0.04 if exact else 0
        row["parts"]["exact_phrase"] = exact
    ranked, seen = [], set()
    for row in sorted(merged.values(), key=lambda r: (-r["score"], str(r["memory"]["id"]))):
        text = str(row["memory"].get("text", "")).strip()
        if text not in seen:
            seen.add(text)
            ranked.append(row)
    return ranked
