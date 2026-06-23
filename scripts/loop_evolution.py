# scripts/loop_evolution.py
"""labcoat loop-evolution — the PURE next-question generator. Given prior loops' confirmed findings + the
brain-surfaced gaps/contradictions, normalize/rank/filter the candidate next-questions so loop N+1 investigates
the GAPS (contradictions FIRST — the research's highest-value, honestly-unproven lever), not the original
question re-decomposed. No network/key/datetime.now(); the brain calls + clock live in the shell. All similarity
reuses novelty_gate (stdlib Jaccard floor; an injected distance_fn is the optional upgrade seam). ADVISORY:
nothing here auto-stops the loop. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import re
import novelty_gate

_KINDS = ("contradiction", "won_followup", "future_work", "gap")
_KIND_RANK = {"contradiction": 0, "won_followup": 1, "future_work": 2, "gap": 3}
_MAX_GAPS = 50


def _extract_json(s):
    """Pull a JSON value out of a brain text response that may be fenced or prose-wrapped (mirrors
    nuclear_core._extract_json). Returns None if all attempts fail."""
    s = (s or "").strip()
    candidates = [s]
    if s.startswith("```"):
        body = re.sub(r"^```[A-Za-z0-9]*\s*", "", s)
        candidates.append(re.sub(r"\s*```$", "", body).strip())
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
    src = candidates[-1]
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        i, j = src.find(open_ch), src.rfind(close_ch)
        if 0 <= i < j:
            try:
                return json.loads(src[i:j + 1])
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _coerce(obj) -> list:
    """Brain gap output may be a JSON string (fenced/prose), an enveloped dict, or a bare list -> list of dicts."""
    if isinstance(obj, str):
        obj = _extract_json(obj)
        if obj is None:
            return []
    if isinstance(obj, dict):
        for key in ("gaps", "items", "candidates", "results"):
            if isinstance(obj.get(key), list):
                return obj[key]
        return []
    return obj if isinstance(obj, list) else []


def parse_gaps(obj) -> list:
    """Normalize gap-stage brain output into [{id, kind, text, seed_evidence}]. kind in _KINDS; unknown/missing
    kind -> 'gap' (safe default). Drops empty-text entries; assigns g1..gN; caps at _MAX_GAPS."""
    out = []
    for item in _coerce(obj):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("question") or "").strip()
        if not text:
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in _KINDS:
            kind = "gap"
        out.append({"id": str(item.get("id") or f"g{len(out) + 1}"), "kind": kind, "text": text,
                    "seed_evidence": str(item.get("seed_evidence") or "").strip()})
        if len(out) >= _MAX_GAPS:
            break
    return out


def rank_gaps(gaps) -> list:
    """Stable-sort so contradictions rank ABOVE coverage gaps: contradiction<won_followup<future_work<gap.
    Order within a kind is preserved (Python sort is stable)."""
    return sorted(list(gaps or []), key=lambda g: _KIND_RANK.get(g.get("kind"), 3))


def minimal_criterion(candidate_text, established_texts, *, max_similarity: float = 0.7, distance_fn=None) -> bool:
    """The Goldilocks predicate (trivial-rejection half): False if the candidate next-question is trivially
    answerable — i.e. too SIMILAR to something already established (nearest-established distance < 1-max_similarity).
    Empty candidate -> False. No established texts -> True (nothing to be trivial against). The 'unanswerable'
    half is not purely detectable and is left to the brain + minimal_criterion's caller."""
    text = (candidate_text or "").strip()
    if not text:
        return False
    est = [t for t in (established_texts or []) if (t or "").strip()]
    if not est:
        return True
    nearest = novelty_gate.novelty_distance(text, est, distance_fn=distance_fn)   # 1 - max similarity
    return nearest >= (1.0 - float(max_similarity))


def question_novelty(candidate_text, prior_questions, *, distance_fn=None) -> float:
    """Archive-distance of a candidate next-question to the prior loop questions (1 - max similarity). Empty
    prior_questions -> 1.0 (fully novel). Reuses novelty_gate.novelty_distance (stdlib Jaccard or injected fn)."""
    return novelty_gate.novelty_distance(candidate_text or "", list(prior_questions or []), distance_fn=distance_fn)


def select_evolved_questions(ranked_gaps, prior_questions, established_texts, *, min_question_distance: float = 0.3,
                             max_similarity_to_established: float = 0.7, max_select: int = 6, distance_fn=None) -> list:
    """Filter ranked gap candidates into the next loop's seed set, preserving rank order. Keep a gap iff it
    (a) passes minimal_criterion vs established_texts AND (b) its question_novelty vs prior_questions >=
    min_question_distance. Annotates each survivor with 'question_distance'; caps at max_select."""
    out = []
    for g in (ranked_gaps or []):
        text = str(g.get("text") or "").strip()
        if not text:
            continue
        if not minimal_criterion(text, established_texts, max_similarity=max_similarity_to_established,
                                 distance_fn=distance_fn):
            continue
        qd = question_novelty(text, prior_questions, distance_fn=distance_fn)
        if qd < float(min_question_distance):
            continue
        out.append({**g, "question_distance": qd})
        if len(out) >= int(max_select):
            break
    return out


def question_stream_collapsed(history, *, floor_distance: float = 0.3, window: int = 3) -> dict:
    """Saturation of the QUESTION stream (distinct from CNY finding-saturation): the loop is no longer asking
    DISTINCT questions. Same SPC K-consecutive-low run-rule as novelty_gate.yield_collapse, on the per-loop
    question-novelty SCALAR (float): collapse iff over the last `window` values ALL <= floor_distance AND
    non-increasing (last <= first). Needs >= window samples (warm-up). ADVISORY — never auto-stops.
    Not yet called from the shell — reserved for calibration reporting once a multi-loop distance history exists.
    Non-increasing is a crude first-vs-last slope (matches yield_collapse); a dip-then-recover window can still
    trigger — calibrate before enforcing."""
    hist = [float(x) for x in (history or [])]
    win = hist[-int(window):]
    collapsed = (len(win) >= int(window) and all(v <= float(floor_distance) for v in win) and win[-1] <= win[0])
    return {"collapsed": bool(collapsed), "window": int(window), "samples": win}
