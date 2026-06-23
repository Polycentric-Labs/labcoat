# scripts/novelty_store.py
"""labcoat Tier-2 Nuclear — persistence behind the pure novelty gate. novelty_gate.cny is pure and returns
new_keys/new_corpus but does NOT persist; this adds the cross-loop, reboot-durable file layer: the seen-set
(sha256 finding keys), the confirmed-finding corpus (JSONL, newline-safe), and the per-loop CNY history.
Single-process / single-user append-only discipline (mirrors novelty_log.py); injected paths; pure stdlib;
no network/key/datetime.now(). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import os


def _ensure_parent(path) -> None:
    d = os.path.dirname(os.fspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def read_seen_keys(path) -> set:
    """The persistent Stage-1 seen-set: one finding key per line. Missing file -> empty set."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return {ln.strip() for ln in fh if ln.strip()}
    except FileNotFoundError:
        return set()


def append_seen_keys(path, keys) -> None:
    """Append only keys not already present (dedup vs the file AND within this call). Order preserved.
    Empty / all-duplicate -> no write."""
    existing = read_seen_keys(path)
    new = []
    for k in keys:
        k = (k or "").strip()
        if k and k not in existing:
            new.append(k)
            existing.add(k)
    if not new:
        return
    _ensure_parent(path)
    with open(path, "a", encoding="utf-8") as fh:
        for k in new:
            fh.write(k + "\n")


def read_corpus(path) -> list:
    """The persistent confirmed-finding corpus: one JSON-encoded text per line (newline-safe). Missing -> [];
    blank lines skipped; a malformed line is skipped defensively."""
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for ln in fh:
                s = ln.strip()
                if not s:
                    continue
                try:
                    out.append(json.loads(s))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return out


def append_corpus(path, texts) -> None:
    """Append confirmed-finding texts, each JSON-encoded on its own line (so a newline inside a finding can't
    corrupt the line-per-record format). No dedup here — the gate de-dupes by key upstream. Empty -> no-op."""
    items = [t for t in texts if (t or "").strip()]
    if not items:
        return
    _ensure_parent(path)
    with open(path, "a", encoding="utf-8") as fh:
        for t in items:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")


def read_cny_history(path) -> list:
    """The per-loop CNY scalar history: one int per line. Missing -> []; a non-int line is skipped."""
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for ln in fh:
                s = ln.strip()
                if not s:
                    continue
                try:
                    out.append(int(s))
                except ValueError:
                    continue
    except FileNotFoundError:
        return []
    return out


def append_cny(path, value: int) -> None:
    """Append one loop's CNY count."""
    _ensure_parent(path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{int(value)}\n")
