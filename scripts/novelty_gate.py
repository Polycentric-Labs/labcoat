# scripts/novelty_gate.py
"""labcoat Tier-2 minimal novelty gate — Confirmed-Novelty Yield (CNY), a SATURATION signal, NOT a value-aware
fitness function (that is the unsolved Tier-3 problem). Pure stdlib (hashlib, re); no network/key/datetime.now()
— thresholds, timestamps, the seen-set, and any embedding distance_fn are INJECTED (the Tier-1 determinism
contract). Novelty is computed ONLY over validation_verdict=='confirmed' records, so a degenerating loop emitting
varied-but-fabricated findings scores 0 (reuses the audit-v2 honesty invariant as the core anti-gaming property).

Scope (the scoping memo's hard conditions): WARN-only until calibrated; never silently auto-stops (the loop_decision
branch pauses-and-pings only when explicitly enforcing); warm-up >= window. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import hashlib
import re


def normalize(text: str) -> str:
    """Lowercase, replace punctuation with spaces, collapse whitespace. None/empty -> ''."""
    t = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def finding_key(text: str) -> str:
    """Stable Stage-1 dedup key: sha256 hex of the normalized text."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def _shingles(text: str, k: int = 3) -> set:
    """k-word shingles over the normalized text. Short texts -> a single whole-text shingle."""
    words = normalize(text).split()
    if not words:
        return set()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def jaccard_distance(a: str, b: str, *, k: int = 3) -> float:
    """1 - Jaccard similarity over k-word shingles. Both empty -> 0.0 (identical)."""
    sa, sb = _shingles(a, k), _shingles(b, k)
    if not sa and not sb:
        return 0.0
    union = len(sa | sb)
    return 1.0 - (len(sa & sb) / union if union else 0.0)


def novelty_distance(text: str, corpus: list[str], *, distance_fn=None) -> float:
    """Distance to the NEAREST corpus entry (= 1 - max similarity). Empty corpus -> 1.0 (fully novel).
    distance_fn(a, b) -> [0,1] distance; default = jaccard_distance (the stdlib public-core floor). An injected
    distance_fn (e.g. 1 - SBERT cosine, pinned) is the optional paraphrase-robust upgrade."""
    if not corpus:
        return 1.0
    df = distance_fn or jaccard_distance
    return min(df(text, c) for c in corpus)


def confirmed_claim_texts(records: list[dict]) -> list[str]:
    """The truth-gated finding stream: claim_text of records with validation_verdict=='confirmed' and a
    non-empty claim_text. (The audit-v2 honesty invariant guarantees confirmed -> completion_status complete.)"""
    return [r.get("claim_text", "") for r in records
            if r.get("validation_verdict") == "confirmed" and (r.get("claim_text") or "").strip()]


def cny(records: list[dict], seen_keys, corpus: list[str], *, tau: float, distance_fn=None) -> dict:
    """Confirmed-Novelty Yield for ONE loop. records = this loop's ledger records; seen_keys = finding keys from
    prior loops (persistent); corpus = prior confirmed finding texts; tau = min novelty_distance to count as novel.
    A confirmed finding counts toward CNY iff (Stage 1) its key is unseen AND (Stage 2) novelty_distance>=tau.
    An unseen-but-too-close finding is still recorded in new_keys (so it is not re-counted next loop).
    Returns {cny, novel_findings, new_keys, new_corpus}. Pure: caller persists the new keys/corpus.
    Note: `corpus` is NOT updated mid-loop, so two findings that are near-duplicates of EACH OTHER but both
    distant from the prior corpus BOTH count this loop (within-loop count-inflation residual — an accepted
    minimal-gate limitation; see the scoping memo)."""
    seen = set(seen_keys)
    novel, new_keys, new_corpus = [], [], []
    for text in confirmed_claim_texts(records):
        key = finding_key(text)
        if key in seen:
            continue
        seen.add(key)
        new_keys.append(key)
        if novelty_distance(text, corpus, distance_fn=distance_fn) >= tau:
            novel.append(text)
            new_corpus.append(text)
    return {"cny": len(novel), "novel_findings": novel, "new_keys": new_keys, "new_corpus": new_corpus}


def yield_collapse(cny_history: list[int], *, floor: int, window: int) -> dict:
    """SPC K-consecutive-low run-rule for degeneracy/yield-collapse on the CNY scalar. Collapse requires BOTH:
    (a) every CNY in the last `window` loops is <= floor, AND (b) the window is non-increasing (last <= first) —
    a 2-condition AND so one quiet exploratory loop never trips it. Needs >= window samples (warm-up) else
    collapsed=False. NOTE: detection only — the gate NEVER auto-stops; loop_decision pauses-and-pings on this.
    The trend test is a crude first-vs-last slope, so a dip-then-recover window whose last == first still reads
    'decaying' — calibrate tau/floor/window on a recorded run before enforcing (WARN-only until then)."""
    if window <= 0 or len(cny_history) < window:
        return {"collapsed": False, "trend": None, "reason": "warm-up: insufficient history"}
    recent = cny_history[-window:]
    all_low = all(v <= floor for v in recent)
    decaying = recent[-1] <= recent[0]
    collapsed = all_low and decaying
    return {"collapsed": collapsed, "trend": "decaying" if decaying else "rising",
            "reason": (f"yield-collapse: last {window} CNY <= floor {floor}, non-increasing" if collapsed
                       else "productive or mixed")}
