# scripts/novelty_log.py
"""Persistent high-signal source-domain log. The skill seeds Phase 2/3 from it AND always hunts NEW sources.
Single-process / single-user by design (no file locking); appends are not concurrency-safe across processes.
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import pathlib

_DEFAULT = pathlib.Path(__file__).resolve().parent.parent / "references" / "good-sources.md"
_MARK = "- "


def read_good_sources(*, path: pathlib.Path | None = None) -> list[str]:
    p = path or _DEFAULT
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(_MARK):
            out.append(s[len(_MARK):].strip().lower())
    return out


def append_good_sources(domains: list[str], *, path: pathlib.Path | None = None) -> None:
    p = path or _DEFAULT
    seen = set(read_good_sources(path=p))
    new: list[str] = []
    for d in domains:
        key = d.strip().replace("\n", "").replace("\r", "").lower()
        if key and key not in seen:   # dedups within this call AND against the file
            new.append(key)
            seen.add(key)
    if not new:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    is_new = not p.exists()
    needs_sep = (not is_new) and p.stat().st_size > 0 and not p.read_text(encoding="utf-8").endswith("\n")
    with p.open("a", encoding="utf-8") as f:
        if is_new:
            f.write("# good-sources — high-signal research domains (auto-appended)\n\n")
        elif needs_sep:
            f.write("\n")
        for d in new:
            f.write(f"{_MARK}{d}\n")
