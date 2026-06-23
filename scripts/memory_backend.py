# scripts/memory_backend.py
"""labcoat Tier-3 — the pluggable MemoryBackend seam (spec §6.3). Public zero-infra default; richer backends
drop in without touching the engine. Two impls:
  FileBackend   — wraps the existing flat-file novelty_store (+ archive/provenance JSONL); the no-dependency fallback.
  SqliteBackend — stdlib sqlite3, APPEND-ONLY, bi-temporal (valid_time/tx_time) + a provenance table; the §6.3
                  Tier-1 default (public-domain, no server/network/LLM-to-ingest).
Both: pure stdlib; the dir/DB path + ALL timestamps are INJECTED (no datetime.now()). Append-only everywhere
(supersede by inserting a later row, never UPDATE/DELETE). Single-process/single-user (matches novelty_store).
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import os
import sqlite3
import novelty_store


class FileBackend:
    """Flat-file backend (the public zero-dependency fallback). seen/corpus/cny reuse novelty_store verbatim;
    the QD archive + provenance are append-only JSONL. Timestamps are accepted (uniform interface) and recorded
    in the archive/provenance JSONL; the seen/corpus/cny files keep novelty_store's plain format."""

    def __init__(self, base_dir):
        self.base = os.fspath(base_dir)
        self.seen = os.path.join(self.base, "novelty-seen.keys")
        self.corpus = os.path.join(self.base, "novelty-corpus.jsonl")
        self.cny = os.path.join(self.base, "cny-history.txt")
        self.archive = os.path.join(self.base, "qd-archive.jsonl")
        self.provenance = os.path.join(self.base, "provenance.jsonl")

    def read_seen_keys(self):
        return novelty_store.read_seen_keys(self.seen)

    def append_seen_keys(self, keys, *, tx_time=None):
        novelty_store.append_seen_keys(self.seen, keys)

    def read_corpus(self):
        return novelty_store.read_corpus(self.corpus)

    def append_corpus(self, texts, *, valid_time=None, tx_time=None):
        novelty_store.append_corpus(self.corpus, texts)

    def read_cny_history(self):
        return novelty_store.read_cny_history(self.cny)

    def append_cny(self, value, *, tx_time=None):
        novelty_store.append_cny(self.cny, value)

    def upsert_elite(self, behavior_key, quality, finding, *, tx_time=None):
        os.makedirs(self.base, exist_ok=True)
        with open(self.archive, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"behavior_key": behavior_key, "quality": float(quality),
                                 "finding": finding, "tx_time": tx_time}, ensure_ascii=False) + "\n")

    def read_archive(self):
        out = {}
        try:
            with open(self.archive, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        row = json.loads(s)
                    except json.JSONDecodeError:
                        continue
                    k = row.get("behavior_key")
                    if k is None:
                        continue
                    q = float(row.get("quality", 0.0))
                    if k not in out or q > out[k]["quality"]:
                        out[k] = {"quality": q, "finding": row.get("finding")}
        except FileNotFoundError:
            return {}
        return out

    def record_provenance(self, finding, sources, *, loop_id, valid_time=None, tx_time=None, evidence: str = ""):
        os.makedirs(self.base, exist_ok=True)
        with open(self.provenance, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"finding": finding, "sources": list(sources or []), "loop_id": loop_id,
                                 "valid_time": valid_time, "tx_time": tx_time,
                                 "evidence": str(evidence or "")}, ensure_ascii=False) + "\n")

    def read_provenance(self):
        out = []
        try:
            with open(self.provenance, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        row = json.loads(s)
                        row.setdefault("evidence", "")
                        out.append(row)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return []
        return out


class SqliteBackend:
    """stdlib sqlite3 backend (§6.3 Tier-1 default). APPEND-ONLY + bi-temporal (valid_time/tx_time) +
    provenance. supersede-by-insert (never UPDATE/DELETE). Deterministic: db_path + all timestamps injected.
    Each call opens + closes its own connection (Windows file-lock safe)."""

    def __init__(self, db_path):
        self.db_path = os.fspath(db_path)
        self._init()

    def _execute(self, sql, params=(), *, many=False, fetch=False):
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.executemany(sql, params) if many else conn.execute(sql, params)
            rows = cur.fetchall() if fetch else None
            conn.commit()
            return rows
        finally:
            conn.close()

    def _init(self):
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS seen_keys (key TEXT, tx_time TEXT);"
                "CREATE TABLE IF NOT EXISTS corpus (text TEXT, valid_time TEXT, tx_time TEXT);"
                "CREATE TABLE IF NOT EXISTS cny_history (value INTEGER, tx_time TEXT);"
                "CREATE TABLE IF NOT EXISTS archive (behavior_key TEXT, quality REAL, finding TEXT, tx_time TEXT);"
                "CREATE TABLE IF NOT EXISTS provenance "
                "(finding TEXT, sources TEXT, loop_id TEXT, valid_time TEXT, tx_time TEXT, evidence TEXT);")
            conn.commit()
        finally:
            conn.close()

    def read_seen_keys(self):
        return {r[0] for r in self._execute("SELECT key FROM seen_keys", fetch=True) if r[0]}

    def append_seen_keys(self, keys, *, tx_time=None):
        existing = self.read_seen_keys()
        new = []
        for k in keys:
            k = (k or "").strip()
            if k and k not in existing:
                new.append((k, tx_time)); existing.add(k)
        if new:
            self._execute("INSERT INTO seen_keys (key, tx_time) VALUES (?, ?)", new, many=True)

    def read_corpus(self):
        return [r[0] for r in self._execute("SELECT text FROM corpus ORDER BY rowid", fetch=True)]

    def append_corpus(self, texts, *, valid_time=None, tx_time=None):
        rows = [(t, valid_time, tx_time) for t in texts if (t or "").strip()]
        if rows:
            self._execute("INSERT INTO corpus (text, valid_time, tx_time) VALUES (?, ?, ?)", rows, many=True)

    def read_cny_history(self):
        return [int(r[0]) for r in self._execute("SELECT value FROM cny_history ORDER BY rowid", fetch=True)]

    def append_cny(self, value, *, tx_time=None):
        self._execute("INSERT INTO cny_history (value, tx_time) VALUES (?, ?)", (int(value), tx_time))

    def upsert_elite(self, behavior_key, quality, finding, *, tx_time=None):
        self._execute("INSERT INTO archive (behavior_key, quality, finding, tx_time) VALUES (?, ?, ?, ?)",
                      (behavior_key, float(quality), finding, tx_time))

    def read_archive(self):
        out = {}
        for k, q, f in self._execute("SELECT behavior_key, quality, finding FROM archive ORDER BY rowid",
                                     fetch=True):
            if k is None:
                continue
            q = float(q)
            if k not in out or q > out[k]["quality"]:
                out[k] = {"quality": q, "finding": f}
        return out

    def record_provenance(self, finding, sources, *, loop_id, valid_time=None, tx_time=None, evidence: str = ""):
        self._execute(
            "INSERT INTO provenance (finding, sources, loop_id, valid_time, tx_time, evidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (finding, json.dumps(list(sources or [])), loop_id, valid_time, tx_time, str(evidence or "")))

    def read_provenance(self):
        out = []
        for finding, sources, loop_id, valid_time, tx_time, evidence in self._execute(
                "SELECT finding, sources, loop_id, valid_time, tx_time, evidence FROM provenance ORDER BY rowid",
                fetch=True):
            try:
                src = json.loads(sources) if sources else []
            except (json.JSONDecodeError, TypeError):
                src = []
            out.append({"finding": finding, "sources": src, "loop_id": loop_id,
                        "valid_time": valid_time, "tx_time": tx_time, "evidence": evidence or ""})
        return out
