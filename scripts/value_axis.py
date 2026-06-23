# scripts/value_axis.py
"""labcoat Tier-3 — the value-aware QUALITY axis CNY (the diversity axis) deliberately omits. The chosen first
quality scalar (per the design + brief): weight a confirmed finding by the number of INDEPENDENT primary sources
that confirmed it (implicit in the Phase-3/4 verification records). ADVISORY ONLY — no Goodhart-proof value
metric exists, so the weight is CAPPED, computed only over confirmed findings, and the loop decision does NOT
consume it until calibrated on a recorded run. Pure stdlib; injected inputs; no network/key/datetime.now().
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import novelty_gate


def source_count(verification: dict) -> int:
    """Number of UNIQUE, normalized primary sources confirming one finding. Prefers a `sources` list (case- and
    whitespace-insensitive dedup); falls back to 1 when only a non-empty `evidence` string is present; 0 when
    neither. Defensive on non-dict / empty input."""
    if not isinstance(verification, dict):
        return 0
    raw = verification.get("sources")
    if isinstance(raw, (list, tuple)):
        uniq = {str(s).strip().lower() for s in raw if str(s).strip()}
        if uniq:
            return len(uniq)
    return 1 if str(verification.get("evidence") or "").strip() else 0


def quality_weight(count: int, *, cap: int = 3) -> float:
    """Capped, monotone per-finding quality weight: min(count, cap) as a float (>= 0). The cap is the
    'novelty's weight can't dominate' defense — one heavily-sourced finding can't swamp the signal."""
    c = max(0, int(count))
    return float(min(c, cap))


def weighted_cny(source_counts, *, cap: int = 3) -> float:
    """ADVISORY quality-weighted yield for one loop = sum of capped quality weights over the loop's
    novel-confirmed findings (REPORTED alongside the integer CNY count, never replacing it)."""
    return sum(quality_weight(sc, cap=cap) for sc in source_counts)


def cost_per_verified_finding(total_spend_usd: float, confirmed_count: int):
    """ADVISORY auxiliary signal (hard to game): spend per confirmed finding — the scoping memo's cheap
    secondary for slow-collapse vs diminishing-returns. None when count == 0 (undefined)."""
    if not confirmed_count:
        return None
    return round(max(0.0, total_spend_usd) / confirmed_count, 4)


def qd_archive_update(archive: dict, *, behavior_key: str, quality: float, finding: str) -> dict:
    """MAP-Elites-lite: keep the highest-quality ELITE per coarse novelty cell (behavior_key). Returns a NEW
    archive dict (pure — does not mutate the input); the confirmed-corpus IS the archive, the novelty-distance
    bucket IS the cell. A new finding replaces the cell's elite only if its quality is strictly greater."""
    out = dict(archive or {})
    cur = out.get(behavior_key)
    if cur is None or quality > cur.get("quality", float("-inf")):
        out[behavior_key] = {"quality": float(quality), "finding": finding}
    return out


def weighted_yield_collapse(weighted_history, *, floor: float, window: int) -> dict:
    """The degeneracy detector — the SAME SPC K-consecutive-low run-rule the CNY gate uses
    (novelty_gate.yield_collapse), applied to the quality-WEIGHTED scalar, so it catches 'still novel but
    thinner' (fewer independent sources) that count-only CNY misses. ADVISORY; pause-and-ping, never auto-stop.
    Delegates to novelty_gate.yield_collapse — one metric, designed together with the CNY gate."""
    return novelty_gate.yield_collapse(list(weighted_history), floor=floor, window=window)
