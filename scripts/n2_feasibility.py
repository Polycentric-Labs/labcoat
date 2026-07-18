"""labcoat N2 — Phase-0 feasibility helpers (PURE, deterministic): quantify whether a PubMed sub-corpus can carry
the Swanson bridge before any build spend. License: MIT. Author: Allen Byrd."""
from __future__ import annotations


def _text_blob(rec) -> str:
    mesh = " ".join(str(m) for m in (rec.get("concepts") or rec.get("mesh") or []))
    return (mesh + " " + str(rec.get("abstract") or "")).lower()


def bridge_presence_fraction(records, bridge_terms) -> float:
    recs = list(records or [])
    if not recs:
        return 0.0
    terms = [str(t).strip().lower() for t in (bridge_terms or []) if str(t).strip()]
    hit = sum(1 for r in recs if any(t in _text_blob(r) for t in terms))
    return hit / len(recs)


def abstract_or_mesh_availability(records) -> float:
    recs = list(records or [])
    if not recs:
        return 0.0
    ok = sum(1 for r in recs if (str(r.get("abstract") or "").strip() or (r.get("concepts") or r.get("mesh"))))
    return ok / len(recs)


def phase0_verdict(presence_by_side, availability_by_side, *, min_presence=0.25, min_availability=0.50) -> dict:
    reasons, go = [], True
    for side, p in (presence_by_side or {}).items():
        if p < min_presence:
            go = False
            reasons.append(f"{side}: bridge-presence {p:.2f} < {min_presence:.2f}")
    for side, a in (availability_by_side or {}).items():
        if a < min_availability:
            go = False
            reasons.append(f"{side}: abstract/MeSH availability {a:.2f} < {min_availability:.2f}")
    return {"go": go, "reasons": reasons, "presence": dict(presence_by_side or {}),
            "availability": dict(availability_by_side or {}),
            "floors": {"presence": min_presence, "availability": min_availability}}
