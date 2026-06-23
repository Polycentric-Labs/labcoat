# scripts/redaction_gate.py
"""Fail-closed sensitive-data gate for outbound research prompts. Catches secret SHAPES + absolute user
paths + obvious PII markers. NOTE: a regex gate is necessary-not-sufficient; the skill ALSO asks the operator what
to redact and 3x-verifies. Findings carry only {label, start, end, cls} OFFSETS — never the matched secret
value — so logging findings cannot leak a secret. Non-str input fails CLOSED (raises). License: MIT.
Author: Allen Byrd."""
from __future__ import annotations
import re


class SensitiveDataError(Exception):
    """Raised when assert_clean finds sensitive content (fail-closed)."""


# Each entry: (regex, label, cls)  where cls is "A" (secret -> hard-block) or "B" (contextual -> surgical)
_PATTERNS = [
    (r"sk-or-v1-[A-Za-z0-9]{16,}", "OpenRouter API key shape", "A"),
    (r"sk-ant-[A-Za-z0-9-]{16,}", "Anthropic key shape", "A"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub PAT shape", "A"),
    (r"github_pat_[A-Za-z0-9_]{30,}", "GitHub fine-grained PAT shape", "A"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id", "A"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "PEM private key", "A"),
    (r"pplx-[A-Za-z0-9]{16,}", "Perplexity key shape", "A"),
    (r"\.secrets\b", "secret-store reference", "A"),
    (r"[A-Za-z]:\\Users\\[^\\\s]+", "absolute Windows user path", "B"),
    (r"/(?:home|Users)/[^/\s]+", "absolute POSIX user path", "B"),
    (r"\b[\w.-]+@[\w.-]+\.\w{2,}\b", "email address", "B"),
]
_COMPILED = [(re.compile(p), label, cls) for p, label, cls in _PATTERNS]
_LABEL_CLASS = {label: cls for _, label, cls in _PATTERNS}
_LABEL_CLASS["client term"] = "B"  # caller-supplied terms are always Class B


def classify(label: str) -> str:
    """Return 'A' (secret, hard-block) or 'B' (contextual, surgical) for a finding label."""
    return _LABEL_CLASS.get(label, "B")


def class_a_labels() -> set[str]:
    return {label for label, cls in _LABEL_CLASS.items() if cls == "A"}


_SSH_URL = re.compile(r"\b[\w.-]+@[\w.-]+:[\w./~-]+")  # git@host:path style


def scan_for_sensitive(text: str) -> list[dict]:
    """Return [{label, start, end, cls}] findings (offsets only — safe to log). Non-str raises TypeError."""
    if not isinstance(text, str):
        raise TypeError(f"scan_for_sensitive requires str, got {type(text).__name__!r}")
    ssh_spans = [(m.start(), m.end()) for m in _SSH_URL.finditer(text)]
    out = []
    for rx, label, cls in _COMPILED:
        for m in rx.finditer(text):
            if label == "email address" and any(s <= m.start() < e for s, e in ssh_spans):
                continue  # benign SSH URL, not an email
            out.append({"label": label, "start": m.start(), "end": m.end(), "cls": cls})
    return out


_PLACEHOLDER = {
    "absolute Windows user path": "PATH", "absolute POSIX user path": "PATH",
    "email address": "EMAIL", "client term": "CLIENT", "person name": "PERSON",
}


def _merge_overlapping(spans: list[dict]) -> list[dict]:
    """Merge/deduplicate overlapping Class-B spans. Greedy: sort by start asc then end desc;
    keep a span only if it does not overlap an already-kept span. Contained spans (e.g. a
    client_term inside a path/email) are dropped so the wider containing span wins."""
    # Sort: earlier start wins; among same start, wider span (larger end) wins.
    sorted_spans = sorted(spans, key=lambda f: (f["start"], -f["end"]))
    kept: list[dict] = []
    for f in sorted_spans:
        if kept and f["start"] < kept[-1]["end"]:
            # Overlaps the last kept span — skip this one (the wider span already covers it).
            continue
        kept.append(f)
    return kept


def apply_redactions(text: str, findings: list[dict]) -> tuple[str, list[dict]]:
    """Replace each Class-B finding span (reverse order = index-safe) with a typed, indexed placeholder.
    Overlapping spans are merged before replacement so wider spans dominate.
    Class-A findings are NOT redacted here (they hard-block upstream). Returns (clean_text, applied[])."""
    b = [f for f in findings if f.get("cls", classify(f["label"])) == "B"]
    b = _merge_overlapping(b)
    counters, applied, plan = {}, [], []
    for f in b:
        kind = _PLACEHOLDER.get(f["label"], "REDACTED")
        counters[kind] = counters.get(kind, 0) + 1
        ph = f"<{kind}_{counters[kind]}>"
        plan.append((f["start"], f["end"], ph))
        applied.append({"label": f["label"], "placeholder": ph})
    out = text
    for start, end, ph in sorted(plan, key=lambda t: t[0], reverse=True):
        out = out[:start] + ph + out[end:]
    return out, applied


def signal(original: str, clean: str, findings: list[dict]) -> dict:
    """Heuristic 'is the query still useful?' check after surgical redaction.
    Two stop conditions (OR):
      1. AND-threshold: redacted_pct > 0.15 AND entity_count >= 3  (mostly-redacted with many entities)
      2. Residual-floor: non-whitespace chars remaining after removing all <...> placeholders < 10
         (gutted query — so little substance left it's not worth sending)."""
    b = [f for f in findings if f.get("cls", classify(f["label"])) == "B"]
    nonws = max(1, len(re.sub(r"\s", "", original)))
    redacted_chars = sum(f["end"] - f["start"] for f in b)
    redacted_pct = redacted_chars / nonws
    entity_count = len(b)
    residual = re.sub(r"<[^>]+>", "", clean)       # strip placeholder tokens
    residual_chars = len(re.sub(r"\s", "", residual))  # non-whitespace chars left
    recommend_stop = (redacted_pct > 0.15 and entity_count >= 3) or (residual_chars < 10)
    return {"redacted_pct": round(redacted_pct, 3), "entity_count": entity_count,
            "recommend_stop": recommend_stop, "residual_chars": residual_chars}


def _client_findings(text: str, client_terms) -> list[dict]:
    if client_terms is None:
        return []
    out = []
    for term in client_terms:
        t = (str(term) if term is not None else "").strip()
        if not t:
            continue
        for m in re.finditer(re.escape(t), text, re.IGNORECASE):
            out.append({"label": "client term", "start": m.start(), "end": m.end(), "cls": "B"})
    return out


def presidio_available() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
        return True
    except Exception:
        return False


def _presidio_classB(text: str) -> list[dict]:
    """Optional NER PII spans via Presidio, normalized to our finding shape (all Class B). [] if unavailable."""
    if not presidio_available():
        return []
    try:
        from presidio_analyzer import AnalyzerEngine
        results = AnalyzerEngine().analyze(text=text, language="en")
        return [{"label": "person name" if r.entity_type == "PERSON" else r.entity_type.lower(),
                 "start": r.start, "end": r.end, "cls": "B"} for r in results]
    except Exception:
        return []  # graceful degrade — never break the portable core


def redact(prompt: str, *, client_terms=()) -> dict:
    """Two-class gate. Class A (secret) -> hard_block (clean_text None, caller must halt).
    Class B (path/email/client term/presidio NER) -> surgical typed-placeholder redaction + signal check.
    Findings carry offsets only (never the matched value)."""
    if not isinstance(prompt, str):
        raise TypeError(f"redact requires str, got {type(prompt).__name__!r}")
    base = scan_for_sensitive(prompt) + _client_findings(prompt, client_terms)
    seen = {(f["start"], f["end"]) for f in base}
    findings = base + [f for f in _presidio_classB(prompt) if (f["start"], f["end"]) not in seen]
    if any(f["cls"] == "A" for f in findings):
        return {"clean_text": None, "hard_block": True, "findings": findings,
                "redactions_applied": [], "signal": None}
    clean, applied = apply_redactions(prompt, findings)
    return {"clean_text": clean, "hard_block": False, "findings": findings,
            "redactions_applied": applied, "signal": signal(prompt, clean, findings)}


def assert_clean(text: str) -> None:
    """Fail-closed on Class-A secrets ONLY (backward-compat gate). For full two-class handling
    use redact(). Never echoes a matched value (labels + count only)."""
    if not isinstance(text, str):
        raise TypeError(f"assert_clean requires str, got {type(text).__name__!r}")
    a = [f for f in scan_for_sensitive(text) if f["cls"] == "A"]
    if a:
        labels = sorted({f["label"] for f in a})
        raise SensitiveDataError(
            f"Outbound prompt blocked: {len(a)} secret(s) [{', '.join(labels)}]. "
            f"Halt + rotate. (Matched values intentionally not shown.)"
        )
