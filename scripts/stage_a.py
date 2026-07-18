# scripts/stage_a.py
"""labcoat N3 Stage-A — PURE measurement core (cite-or-fail prior-art, blinding, attribution, report). stdlib only,
deterministic, no network/key/clock (all live calls injected by the shell). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import re
import random
import combinatorial  # for _extract_json (pure, stdlib)

_DOI_RE = re.compile(r"10\.\d{4,}/[^\s\"'<>)\];,]+", re.I)  # real DOI registrant prefix is >=4 digits (no upper cap)
_ARXIV_RE = re.compile(r"\b\d{4}\.\d{4,5}\b")


def extract_resolvable_ids(text) -> list:
    """All DOI + arXiv ids in a string (the cite-or-fail gate). Dedupe preserving order; strip trailing punctuation."""
    s = str(text or "")
    raw = _DOI_RE.findall(s) + _ARXIV_RE.findall(s)
    seen, out = set(), []
    for i in raw:
        i = i.rstrip(".,;")
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def stage_a_report(attribution_dict, control_verdict_dict, off_distribution) -> dict:
    """The honest Stage-A report. VOID (ruler leaked) DOMINATES; else EARNS-STAGE-B iff machinery adds value; else
    HONEST-NEGATIVE. The ceiling caveat is baked in (engine-attributable + prior-art-distant, NOT non-obvious)."""
    void = not bool(control_verdict_dict.get("clean", False))
    adds = bool(attribution_dict.get("machinery_adds_value", False))
    if void:
        verdict = "VOID — adjudication ruler leaked (a negative/known-obvious control survived); fix before any verdict"
    elif adds:
        verdict = "EARNS-STAGE-B — machinery beats the raw baseline AND the ruler is clean"
    else:
        verdict = "HONEST-NEGATIVE — N3 machinery does not beat the raw weak-proposer baseline"
    return {"verdict": verdict, "ruler_clean": not void, "machinery_adds_value": adds,
            "attribution": attribution_dict, "controls": control_verdict_dict, "off_distribution": off_distribution,
            "ceiling_caveat": ("Stage A measures engine-attributable + prior-art-distant (coverage floor: 'no prior "
                               "art found under protocol P', never 'novel'); it does NOT measure human-verified "
                               "non-obvious. cite-or-fail kills false-POSITIVE prior art only; missed prior art "
                               "inflates survival, so the rate DELTA (ii vs i), not the absolute rate, is the signal.")}


def _rate(cands) -> dict:
    cs = list(cands or [])
    surv = sum(1 for c in cs if c.get("survived"))
    return {"candidates": len(cs), "survivors": surv, "survival_rate": (surv / len(cs) if cs else 0.0)}


def attribution(arm_i, arm_ii) -> dict:
    """Engine-machinery attribution at MATCHED (weak) fleet: machinery adds value iff arm (ii) FULL-N3's objective-
    survival RATE exceeds arm (i) RAW's (rate, not raw count, controls for proposal volume). Reports both."""
    ri, rii = _rate(arm_i), _rate(arm_ii)
    return {"arm_i": ri, "arm_ii": rii,
            "machinery_delta_rate": round(rii["survival_rate"] - ri["survival_rate"], 4),
            "machinery_adds_value": rii["survival_rate"] > ri["survival_rate"]}


def control_verdict(control_results) -> dict:
    """Ruler-validity gate — tests BOTH adjudication failure directions.
    (1) FALSE-POSITIVE direction: a NEGATIVE (known-obvious/published) control that SURVIVES the objective bar means the
        ruler failed to find prior art that obviously exists -> ruler broken -> measurement VOID (`clean=False`).
    (2) FALSE-NEGATIVE / missed-prior-art direction: `pos` controls are PRIOR-ART-RECALL probes (documented published
        cross-domain transfers — prior art DEFINITELY exists, so they MUST be caught, i.e. NOT survive). `prior_art_recall`
        = fraction of probes whose prior art was correctly FOUND (= not survived); a LOW value flags the missed-prior-art
        weakness (cite-or-fail's blind spot — the dogfood's H4/H8 concern) and is advisory, NOT a VOID trigger.
    Real candidates (control is None) are ignored by the verdict."""
    rs = list(control_results or [])
    neg = [r for r in rs if r.get("control") == "neg"]
    pos = [r for r in rs if r.get("control") == "pos"]
    fps = [r.get("id") for r in neg if r.get("survived")]
    prior_art_recall = (sum(1 for r in pos if not r.get("survived")) / len(pos)) if pos else None
    return {"clean": len(fps) == 0, "false_positives": fps,
            "n_neg": len(neg), "n_pos": len(pos), "prior_art_recall": prior_art_recall}


def blind_candidates(candidates, *, seed: int = 0):
    """Strip arm/pair/control/source labels, assign opaque ids (b1..bN), seeded-deterministic shuffle so the
    adjudicator (and a later operator read) cannot tell which arm / control a candidate came from. Returns
    (blinded_list[{id,claim,mechanism}], origin_map{id: {arm,pair,control}})."""
    items = list(candidates or [])
    order = list(range(len(items)))
    random.Random(seed).shuffle(order)
    blinded, origin = [], {}
    for new_i, orig_i in enumerate(order):
        c = items[orig_i] or {}
        bid = f"b{new_i + 1}"
        blinded.append({"id": bid, "claim": str(c.get("claim") or ""), "mechanism": str(c.get("mechanism") or "")})
        origin[bid] = {"arm": c.get("arm"), "pair": c.get("pair"), "control": c.get("control")}
    return blinded, origin


def relevance_prompt(claim: str, mechanism: str = "") -> str:
    """Calibrated relevance adjudication prompt (cite-or-fail only for covered categories). Classifies the claim
    into exactly one of {routine-application, specific-prior-transfer, no-covering-prior-art}; only the first two
    have prior art — and cite-or-fail still applies within those categories."""
    return (
        "You are a hard-skeptic prior-art examiner with web access. Classify the CLAIM into exactly one category:\n"
        " - 'routine-application': it is a standard/textbook application of an ESTABLISHED method or technique to a "
        "task where such application is already common practice. (The foundational or standard literature for that "
        "method THEN counts as prior art — cite a representative resolvable id.)\n"
        " - 'specific-prior-transfer': a published work already makes THIS specific cross-domain mechanism transfer "
        "(cite its resolvable id).\n"
        " - 'no-covering-prior-art': it transfers a mechanism into a domain/use where NEITHER a general-method "
        "literature NOR a specific published work covers it — a genuinely novel cross-domain combination.\n\n"
        "Be calibrated: do not stretch 'routine-application' to cover a genuinely novel cross-domain transfer, and do "
        "not call something novel merely because no paper states it in the exact same words.\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mechanism}\n\n"
        'Return STRICT JSON only: {"category": "routine-application|specific-prior-transfer|no-covering-prior-art", '
        '"nearest_id": "resolvable DOI/arXiv or empty", "nearest_topic": "...", "why": "..."}. No prose.')


def parse_relevance(response) -> dict:
    """Calibrated cite-or-fail parse of the relevance adjudication response.
    Returns {has_prior_art, category, nearest_id, nearest_topic, why}.
    - covered categories (routine-application, specific-prior-transfer) + resolvable id present -> has_prior_art True
    - no-covering-prior-art -> has_prior_art False (survives) regardless of nearest_id
    - cite-or-fail: covered category but no resolvable id -> discarded -> has_prior_art False
    - non-dict / parse-failure -> has_prior_art False, category None (safe fallback)."""
    if isinstance(response, dict):
        data = response
    else:
        data = combinatorial._extract_json(str(response or ""))   # _extract_json handles fenced/enveloped JSON natively
    if not isinstance(data, dict):
        return {"has_prior_art": False, "category": None, "nearest_id": None, "nearest_topic": "", "why": ""}
    cat = str(data.get("category") or "").strip().lower()
    ids = extract_resolvable_ids(str(data.get("nearest_id") or ""))
    covered = cat in ("routine-application", "specific-prior-transfer")
    has = covered and bool(ids)
    return {"has_prior_art": has, "category": cat,
            "nearest_id": (ids[0] if ids else None),
            "nearest_topic": str(data.get("nearest_topic") or ""),
            "why": str(data.get("why") or "")[:160]}


def prior_art_prompt(claim: str, mechanism: str = "") -> str:
    """The objective prior-art search prompt (web=True). Hard-skeptic, cite-or-fail: any prior-art claim MUST carry a
    resolvable DOI/arXiv id, else report prior_art_found=false."""
    return (
        "You are a hard-skeptic prior-art searcher with web access. Find the NEAREST PRIOR published work to the CLAIM "
        "below. If prior art exists you MUST cite a resolvable DOI or arXiv id; if you cannot find a resolvable id, "
        "report prior_art_found=false (an unverifiable citation does NOT count as prior art).\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mechanism}\n\n"
        'Return STRICT JSON only: {"prior_art_found": true|false, "nearest_id": "DOI or arXiv id or empty", '
        '"nearest_title": "...", "difference": "how the claim differs from the nearest prior work"}. No prose.')


def raw_propose_prompt(domain_a: str, domain_b: str, *, n: int = 3) -> str:
    """Arm (i) RAW baseline: a plain ask for cross-domain ideas — deliberately NO structure-mapping / analogical /
    relational framing (that framing is part of N3's machinery, isolated in arm ii)."""
    return (f"Give {n} specific, testable cross-domain combinations of {domain_a} and {domain_b}. "
            "Return STRICT JSON only: a list of objects "
            '{"domain_a": "...", "domain_b": "...", "mechanism": "...", "claim": "..."}. No prose.')


def survives_objective(prior_art) -> bool:
    """A candidate SURVIVES the objective leg iff no DOI/arXiv-resolvable prior art was found (coverage floor:
    'no prior art found under protocol P', never 'novel')."""
    return not bool((prior_art or {}).get("has_prior_art"))


def parse_prior_art(search_response) -> dict:
    """cite-or-fail parse of the prior-art search response -> {has_prior_art, nearest_id, nearest_title, difference}.
    Prior art counts ONLY if the model asserts it AND a resolvable DOI/arXiv id is present (an unverifiable citation is
    DISCARDED). Tolerant of JSON-string / fenced / enveloped input. Non-dict fallback: a bare resolvable id in the raw
    text implies prior art (conservative)."""
    data = combinatorial._extract_json(search_response) if isinstance(search_response, str) else search_response
    if not isinstance(data, dict):
        ids = extract_resolvable_ids(str(search_response or ""))
        return {"has_prior_art": bool(ids), "nearest_id": (ids[0] if ids else None),
                "nearest_title": "", "difference": ""}
    asserted = bool(data.get("prior_art_found"))
    ids = extract_resolvable_ids(str(data.get("nearest_id") or "") + " " + str(data.get("nearest_title") or ""))
    has = asserted and bool(ids)
    return {"has_prior_art": has, "nearest_id": (ids[0] if ids else None),
            "nearest_title": str(data.get("nearest_title") or ""), "difference": str(data.get("difference") or "")}
