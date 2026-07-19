#!/usr/bin/env python3
"""divergence — cross-vendor divergence as an ADVISORY fabrication-triage signal (finishline item #2).

When a fleet of models produces a proper noun (a CVE, arXiv id, repo, version, model slug), the DEGREE to which
different VENDORS disagree on its value is a one-sided fabrication flag: high cross-vendor divergence => verify this
one first. Low divergence is NOT a safety guarantee (vendors share training data and co-hallucinate) — so this signal
only ORDERS the verify queue; it never clears a proper noun and never replaces verify-to-kill. [labcoat honesty stake]

Grouping is by VENDOR (provider), not model: two Anthropic models agreeing is not two independent votes.

Prior art (verified 2026-07-19): arXiv:2606.19509 (Dasula/Desikan/Srivastava, EIML@ICML 2026) — Attribution
Disagreement Score + cross-model calibrator. This module is the multi-vendor, research-proper-noun, productized
analog: rare as an integrated workflow, NOT novel. Pure stdlib; the retrospective test reuses scripts/roc.py.
"""
import math
from collections import Counter

import roc  # AUROC (= Mann-Whitney U) + seeded stratified bootstrap CI; reused for the retrospective test


def normalize_value(s: str) -> str:
    """Canonicalize a proper-noun value: strip wrapping backticks/quotes/space, drop a leading `vendor/` prefix,
    lowercase. e.g. `` `Anthropic/Claude-3.5-Sonnet` `` -> ``claude-3.5-sonnet``."""
    s = s.strip().strip("`\"'").strip()
    if "/" in s:
        s = s.split("/", 1)[1]
    return s.strip().lower()


def vendor_of(model_id: str) -> str:
    """The provider prefix of an OpenRouter-style id (`anthropic/claude-opus-4.8` -> `anthropic`); lowercased.
    No slash -> the whole id lowercased."""
    return (model_id.split("/", 1)[0] if "/" in model_id else model_id).lower()


def collapse_by_vendor(model_values: dict) -> dict:
    """`{model_id: raw_value}` -> `{vendor: modal_normalized_value}`. Empty/None values dropped; per vendor take the
    modal normalized value (ties -> lexicographically first) so correlated same-vendor models count as one vote."""
    groups: dict = {}
    for mid, val in model_values.items():
        if val is None or str(val).strip() == "":
            continue
        groups.setdefault(vendor_of(mid), []).append(normalize_value(str(val)))
    out = {}
    for vendor, vals in groups.items():
        counts = Counter(vals)
        top = max(counts.values())
        out[vendor] = sorted(v for v, n in counts.items() if n == top)[0]
    return out


def _nonempty_values(vendor_values: dict) -> list:
    return [v for v in vendor_values.values() if v is not None and str(v).strip() != ""]


def divergence(vendor_values: dict) -> float | None:
    """PRIMARY statistic: `(D-1)/(V-1)` where V = answering vendors, D = distinct values. Bounded [0,1]
    (0 = consensus, 1 = every vendor differs). None if V < 2 (undefined). Assumes normalized values."""
    vals = _nonempty_values(vendor_values)
    V = len(vals)
    if V < 2:
        return None
    D = len(set(vals))
    return (D - 1) / (V - 1)


def entropy_divergence(vendor_values: dict) -> float | None:
    """ROBUSTNESS statistic: normalized Shannon entropy `H / log(V)` over the value distribution (captures a lone
    outlier vs an even split). Bounded [0,1]. None if V < 2. Assumes normalized values."""
    vals = _nonempty_values(vendor_values)
    V = len(vals)
    if V < 2:
        return None
    counts = Counter(vals)
    H = -sum((n / V) * math.log(n / V) for n in counts.values())
    return H / math.log(V)


def abstention_rate(fleet_vendors: list, vendor_values: dict) -> float:
    """Fraction of `fleet_vendors` that gave NO value — honest uncertainty, tracked apart from divergence."""
    if not fleet_vendors:
        return 0.0
    answered = set(vendor_values.keys())
    return sum(1 for v in fleet_vendors if v not in answered) / len(fleet_vendors)


# ---------------------------------------------------------------------------
# Retrospective study (Component 2) — reuses roc.py. PRE-REGISTERED knobs; see references/divergence-prereg.md.
# ---------------------------------------------------------------------------
def _arm(enriched: list, pos_labels: set, neg_label: str, *, seed: int, k_min: int, n_boot: int) -> dict:
    """One test arm: scores = divergence, positive class = pos_labels, negative class = {neg_label}.

    AUROC = P(a positive out-diverges a negative) via roc.roc_auc (tie-safe Mann-Whitney U). Frozen verdicts:
    INCONCLUSIVE if either class < k_min; WEAK_EXISTENCE_PROOF if bootstrap CI.lo > 0.5; else HONEST_NEGATIVE.
    """
    scores, labels = [], []
    for r in enriched:
        if r["label"] in pos_labels:
            scores.append(r["_div"]); labels.append(1)
        elif r["label"] == neg_label:
            scores.append(r["_div"]); labels.append(0)
    n_pos, n_neg = labels.count(1), labels.count(0)
    arm = {"n_pos": n_pos, "n_neg": n_neg, "auc": None, "ci": None, "rank_biserial": None}
    if min(n_pos, n_neg) < k_min:
        arm["verdict"] = "INCONCLUSIVE"
        return arm
    auc = roc.roc_auc(scores, labels)
    ci = roc.auc_ci(scores, labels, n_boot=n_boot, seed=seed, stratified=True)
    arm["auc"] = auc
    arm["ci"] = ci
    arm["rank_biserial"] = (2 * auc - 1) if auc is not None else None
    arm["verdict"] = "WEAK_EXISTENCE_PROOF" if (ci is not None and ci["lo"] > 0.5) else "HONEST_NEGATIVE"
    return arm


def run_study(rows: list, *, seed: int, k_min: int = 15, n_boot: int = 2000) -> dict:
    """Pre-registered retrospective test: is cross-vendor divergence higher on FABRICATED proper nouns than CONFIRMED?

    rows: {"slot_id","referent","vendor_values":{vendor:value},"label" in confirmed/fabricated/misleading/unverifiable}.
    Values are normalized before divergence; slots with < 2 answering vendors are excluded (counted in excluded_lt2).
    PRIMARY = fabricated(1) vs confirmed(0) [misleading + unverifiable excluded]; SECONDARY = (fabricated ∪ misleading)
    vs confirmed. Returns {n_slots, excluded_lt2, primary, secondary}. One-sided advisory signal — never a classifier.
    """
    enriched, excluded = [], 0
    for r in rows:
        vv = {vd: normalize_value(str(val)) for vd, val in r["vendor_values"].items()
              if val is not None and str(val).strip() != ""}
        d = divergence(vv)
        if d is None:
            excluded += 1
            continue
        rr = dict(r); rr["_div"] = d
        enriched.append(rr)
    return {
        "n_slots": len(rows),
        "excluded_lt2": excluded,
        "primary": _arm(enriched, {"fabricated"}, "confirmed", seed=seed, k_min=k_min, n_boot=n_boot),
        "secondary": _arm(enriched, {"fabricated", "misleading"}, "confirmed", seed=seed, k_min=k_min, n_boot=n_boot),
    }


# ---------------------------------------------------------------------------
# Prospective instrument (Component 3) — the ADVISORY verify-first queue.
# ---------------------------------------------------------------------------
def score_run(extractions: list, *, fleet_vendors: list | None = None) -> list:
    """Score per-proper-noun cross-vendor divergence for a live run and return the verify-FIRST queue.

    extractions: `[{"proper_noun","vendor_values":{vendor:value}, ...}]`. Adds `divergence`, `entropy`, and (if
    `fleet_vendors` given) `abstention`; returns a NEW list sorted by divergence DESC (V<2 -> divergence None, sorts
    last). ADVISORY ORDERING ONLY — it tells you what to verify first; it NEVER clears a proper noun. [honesty stake]
    """
    scored = []
    for ex in extractions:
        vv = {vd: normalize_value(str(v)) for vd, v in ex["vendor_values"].items()
              if v is not None and str(v).strip() != ""}
        rec = dict(ex)
        rec["divergence"] = divergence(vv)
        rec["entropy"] = entropy_divergence(vv)
        if fleet_vendors is not None:
            rec["abstention"] = abstention_rate(fleet_vendors, vv)
        scored.append(rec)
    scored.sort(key=lambda r: (r["divergence"] is not None, r["divergence"] if r["divergence"] is not None else -1.0),
                reverse=True)
    return scored
