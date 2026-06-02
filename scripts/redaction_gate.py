# scripts/redaction_gate.py
"""Fail-closed sensitive-data gate for outbound research prompts. Catches secret SHAPES + absolute user
paths + obvious PII markers. NOTE: a regex gate is necessary-not-sufficient; the skill ALSO asks Allen what
to redact and 3x-verifies. Findings carry only {label, start, end} OFFSETS — never the matched secret value —
so logging findings cannot leak a secret. Non-str input fails CLOSED (raises). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import re


class SensitiveDataError(Exception):
    """Raised when assert_clean finds sensitive content (fail-closed)."""


_PATTERNS = [
    (r"sk-or-v1-[A-Za-z0-9]{16,}", "OpenRouter API key shape"),
    (r"sk-ant-[A-Za-z0-9-]{16,}", "Anthropic key shape"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub PAT shape"),
    (r"github_pat_[A-Za-z0-9_]{30,}", "GitHub fine-grained PAT shape"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "PEM private key"),
    (r"pplx-[A-Za-z0-9]{16,}", "Perplexity key shape"),
    (r"[A-Za-z]:\\Users\\[^\\\s]+", "absolute Windows user path"),
    (r"/(?:home|Users)/[^/\s]+", "absolute POSIX user path"),
    (r"\.secrets\b", "secret-store reference"),
    (r"\b[\w.-]+@[\w.-]+\.\w{2,}\b", "email address"),
]
_COMPILED = [(re.compile(p), label) for p, label in _PATTERNS]


def scan_for_sensitive(text: str) -> list[dict]:
    """Return a list of {label, start, end} findings (empty = clean).
    Findings carry OFFSETS only — never the matched value — so they are safe to log.
    Fail-closed: a non-str input raises TypeError (callers must pass the assembled prompt string)."""
    if not isinstance(text, str):
        raise TypeError(f"scan_for_sensitive requires str, got {type(text).__name__!r}")
    out = []
    for rx, label in _COMPILED:
        for m in rx.finditer(text):
            out.append({"label": label, "start": m.start(), "end": m.end()})
    return out


def assert_clean(text: str) -> None:
    """Fail-closed: raise SensitiveDataError if anything is flagged; raise TypeError on non-str input.
    NEVER echoes the matched value (only labels + count)."""
    if not isinstance(text, str):
        raise TypeError(f"assert_clean requires str, got {type(text).__name__!r}")
    findings = scan_for_sensitive(text)
    if findings:
        labels = sorted({f["label"] for f in findings})
        raise SensitiveDataError(
            f"Outbound prompt blocked: {len(findings)} sensitive item(s) [{', '.join(labels)}]. "
            f"Redact before sending. (Matched values intentionally not shown.)"
        )
