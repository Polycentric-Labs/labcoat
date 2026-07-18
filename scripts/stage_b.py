# scripts/stage_b.py
"""labcoat N3 Stage-B — PURE measurement core (dual-leg prior-art: knn_prior_art + id-resolution+confirm; soundness
panel; matched selection; cluster-robust stats; attribution; verdict). canonicalize_prompt/parse_canonical are RETAINED
for reuse/tests but NOT used in the v3 dual-leg pipeline (canonicalization caused the v2 VOID). stdlib only,
deterministic, no network/key/clock (all live calls injected by the shell). Imports shared Stage-A machinery.
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import math, random
import combinatorial  # pure _extract_json
import stage_a        # blind_candidates, relevance_prompt, parse_relevance, extract_resolvable_ids, raw_propose_prompt

_CANON_FIELDS = ("domain_a_concept", "domain_b_target", "mechanism", "direction", "boundary", "measurable_test")


def canonicalize_prompt(claim: str, mechanism: str = "") -> str:
    """Arm-BLIND style normalizer: rewrite any claim into ONE fixed 6-field register so adjudication never sees the
    arm's native style (the #1 dogfood fix — removes the style confound for all arms uniformly).
    NOTE: RETAINED for reuse/tests but NOT used in the v3 dual-leg pipeline (canonicalization caused the v2 VOID)."""
    return (
        "Rewrite the scientific CLAIM below into a single neutral, uniform register with EXACTLY these six fields, "
        "preserving the substantive content but stripping rhetorical flourish, jargon density, and length differences. "
        "Do not add or remove substantive claims; only normalize style.\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mechanism}\n\n"
        'Return STRICT JSON only: {"domain_a_concept":"...","domain_b_target":"...","mechanism":"...",'
        '"direction":"...","boundary":"...","measurable_test":"..."}. No prose.')


def parse_canonical(response, *, orig_claim: str, orig_mech: str) -> dict:
    """Parse the canonicalizer response -> {ok, canonical_claim, canonical_mechanism, fields}. On any parse failure,
    fall back to the ORIGINAL text (flagged ok=False) so a bad rewrite never drops a candidate."""
    data = response if isinstance(response, dict) else combinatorial._extract_json(str(response or ""))
    if not isinstance(data, dict) or not str(data.get("mechanism") or "").strip():
        return {"ok": False, "canonical_claim": orig_claim, "canonical_mechanism": orig_mech, "fields": {}}
    fields = {k: str(data.get(k) or "") for k in _CANON_FIELDS}
    claim = (f"In {fields['domain_b_target']}, {fields['mechanism']} {fields['direction']} "
             f"(from {fields['domain_a_concept']}); boundary: {fields['boundary']}; test: {fields['measurable_test']}.")
    return {"ok": True, "canonical_claim": claim, "canonical_mechanism": fields["mechanism"], "fields": fields}


def _reconstruct_inverted(idx) -> str:
    if not isinstance(idx, dict) or not idx:
        return ""
    pos = []
    for word, locs in idx.items():
        for l in (locs or []):
            pos.append((l, word))
    return " ".join(w for _, w in sorted(pos))


def parse_resolution(record) -> dict:
    """Normalize an OpenAlex/Crossref/arXiv record -> {resolved, title, abstract, id}. OpenAlex abstracts arrive as an
    inverted index (reconstruct); Crossref title is a list; missing/empty -> resolved False (conservative: a record we
    cannot resolve does NOT count as prior art)."""
    if not isinstance(record, dict) or not record:
        return {"resolved": False, "title": "", "abstract": "", "id": ""}
    title = record.get("title")
    if isinstance(title, list):
        title = title[0] if title else ""
    title = str(title or "").strip()
    abstract = record.get("abstract")
    if not abstract and record.get("abstract_inverted_index"):
        abstract = _reconstruct_inverted(record["abstract_inverted_index"])
    abstract = str(abstract or "").replace("<p>", "").replace("</p>", "").strip()
    rid = str(record.get("id") or record.get("DOI") or "").strip()
    return {"resolved": bool(title or abstract), "title": title, "abstract": abstract, "id": rid}


def confirm_prompt(claim: str, mechanism: str, title: str, abstract: str) -> str:
    """Does the RESOLVED record actually ANTICIPATE this claim (same mechanism AND same direction), not merely share
    keywords or run the reverse direction? Closes the keyword-coincidence false-positive."""
    return (
        "You are a hard-skeptic prior-art examiner. Decide whether the RESOLVED PRIOR WORK actually ANTICIPATES the "
        "CLAIM — i.e. it already makes the SAME mechanism transfer in the SAME direction. Keyword overlap, a reverse-"
        "direction transfer, or a merely-adjacent topic does NOT count as anticipation.\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mechanism}\n\n"
        f"RESOLVED PRIOR WORK TITLE: {title}\nRESOLVED PRIOR WORK ABSTRACT: {abstract}\n\n"
        'Return STRICT JSON only: {"anticipates": true|false, "why": "one sentence"}. No prose.')


def parse_confirm(response) -> dict:
    data = response if isinstance(response, dict) else combinatorial._extract_json(str(response or ""))
    if not isinstance(data, dict):
        return {"anticipates": False, "why": ""}
    return {"anticipates": bool(data.get("anticipates")), "why": str(data.get("why") or "")[:160]}


def objective_survives(relevance, confirm) -> bool:
    """Survives the objective prior-art leg. Category-aware (CALIBRATION-2026-06-28 fix):
    - no covered prior art -> SURVIVES.
    - 'routine-application' -> CAUGHT on the category alone. A standard/textbook method is not anticipated by ONE
      citable paper; requiring the adjudicator's (imperfect, often unresolvable or mis-pointed) citation to resolve+
      confirm here let 10/10 obvious negatives survive in calibration. The category IS the prior-art judgment.
    - 'specific-prior-transfer' (or any non-routine category, incl. the kNN leg which passes none) -> CAUGHT only if the
      cited/retrieved record RESOLVED and the confirm step CONFIRMS anticipation. Keeps the fake-id / keyword-coincidence
      guard exactly where a SPECIFIC anticipating paper is claimed.
    `relevance` from stage_a.parse_relevance (or the kNN-leg relevance dict); `confirm` from parse_confirm."""
    rel = relevance or {}
    if not bool(rel.get("has_prior_art")):
        return True
    if str(rel.get("category") or "").strip().lower() == "routine-application":
        return False
    return not bool((confirm or {}).get("anticipates"))


def panel_survives(survivals) -> bool:
    """A candidate survives the prior-art leg only if ALL adjudicators independently find no prior art (killed if EITHER
    finds confirmed prior art) — raises recall, reduces false novelty (SQ6 fix)."""
    s = list(survivals or [])
    return all(bool(x) for x in s)


def cohens_kappa(a, b) -> float:
    """Cohen's kappa for two binary raters over paired labels. po = observed agreement; pe = chance agreement from
    marginals. Constant-and-identical raters -> 1.0; no agreement beyond chance -> ~0; systematic disagreement -> <0."""
    a, b = list(a or []), list(b or [])
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    po = sum(1 for i in range(n) if a[i] == b[i]) / n
    pa1, pb1 = sum(a[:n]) / n, sum(b[:n]) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


def knn_prior_art(neighbors, *, sim_threshold) -> dict:
    """PURE: given kNN neighbors [{id,title,distance}] (cosine DISTANCE; closer = more likely prior art), return the
    prior-art CANDIDATES whose distance < sim_threshold, distance-sorted ascending. The shell then resolve+confirms each
    (nearest first) to decide anticipation. Deterministic; empty/None/malformed -> no candidate (fail-safe)."""
    nbs = [n for n in (neighbors or []) if isinstance(n, dict) and n.get("distance") is not None]
    nbs = sorted(nbs, key=lambda n: float(n["distance"]))
    cands = [n for n in nbs if float(n["distance"]) < float(sim_threshold)]
    nearest = nbs[0] if nbs else None
    return {"has_candidate": bool(cands), "candidates": cands,
            "nearest_id": (str(nearest["id"]) if nearest else ""),
            "nearest_distance": (float(nearest["distance"]) if nearest else None)}


def soundness_prompt(claim: str, mechanism: str = "") -> str:
    """Rubric-decomposed soundness (mechanistic coherence + scientific plausibility), NOT a novelty/non-obviousness
    judgment. Decomposed scoring reduces verbosity/fluency halo bias."""
    return (
        "Rate the scientific SOUNDNESS of the CLAIM — is it mechanistically coherent and physically/biologically "
        "plausible, or is it pseudo-science / word-salad / internally contradictory? This is a SOUNDNESS judgment "
        "only; a perfectly ordinary sound claim scores high.\n"
        "Judge four sub-criteria: (1) is a concrete MECHANISM specified? (2) is it SCALE-consistent (no impossible "
        "magnitudes)? (3) is the DIRECTION of effect coherent? (4) is it FALSIFIABLE?\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mechanism}\n\n"
        'Return STRICT JSON only: {"sound": true|false, "score": 0.0-1.0, "why": "one sentence"}. No prose.')


def soundness_prompt_v2(claim: str, mechanism: str = "") -> str:
    """Constraint-checking refuter-verifier (dogfood-locked). RETRIEVE the governing law FIRST, DECOMPOSE + fill a
    cross-domain MAPPING TABLE, then mark UNSOUND only via a SPECIFIC named artifact (a named law violated, or a failed
    structure-preserving predicate). SOUND/ABSTAIN is the default; idealizations/approximations/novelty are NOT
    violations; a genuinely-novel-but-coherent target mechanism is COHERENT_NOVEL (NOT unsound)."""
    return (
        "Judge the scientific SOUNDNESS of the CLAIM (mechanistic coherence + physical/biological plausibility). Do NOT "
        "reward fluent or authoritative language. Work in THIS ORDER and show your work:\n"
        "1. RETRIEVE: for each core entity, state the governing law/bound/scale/valid-domain BEFORE judging.\n"
        "2. DECOMPOSE: extract the causal chain. If the claim transfers a mechanism across domains, fill a MAPPING "
        "TABLE: source entities/operation/monotone-quantity/feedback -> the target equivalents.\n"
        "3. CHECK two UNSOUND paths (UNSOUND only if you can name a SPECIFIC artifact):\n"
        "   (a) NAMED-LAW VIOLATION: name the specific law/bound, HOW the claim exceeds it (quantitative/scale), and WHY "
        "that law governs THIS link (applicability). \n"
        "   (b) INCOHERENT MAPPING: a failed structure-preserving predicate -- P1 role-type (e.g. a selection operator "
        "cannot map to an additive magnitude or an averaging op), P2 strip ALL source vocabulary and ask if the target "
        "relationship follows from target mechanics ALONE, P3 a single invariant literally true in BOTH domains. Set "
        "target_claim_status: TRUE_STANDARD / FALSE_STANDARD / UNDEFINED / COHERENT_NOVEL.\n"
        "RULES: Do NOT mark UNSOUND for idealizations, approximations, scope-limits, incompleteness, or NOVELTY. A "
        "coherent target mechanism that is merely NEW (not an existing named method) is COHERENT_NOVEL, NOT unsound. If "
        "you cannot name a law AND cannot name a failed predicate, the claim is SOUND or ABSTAIN -- never UNSOUND.\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mechanism}\n\n"
        'Return STRICT JSON only: {"verdict":"SOUND|UNSOUND|ABSTAIN", "unsound_kind":"none|named_law|incoherent_mapping", '
        '"governing_constraint":"", "how_exceeded":"", "why_governs":"", "mapping_table":"", "stripped_target_claim":"", '
        '"target_claim_status":"TRUE_STANDARD|FALSE_STANDARD|UNDEFINED|COHERENT_NOVEL", "failed_predicate":"none|P1|P2|P3", '
        '"incoherence_role_pair":"", "confidence":0.0, "why":""}. UNSOUND only with a named law (how_exceeded+why_governs) '
        "OR a failed predicate (incoherence_role_pair + target_claim_status in FALSE_STANDARD/UNDEFINED). No prose.")


_SOUNDNESS_V2_VERDICTS = {"SOUND", "UNSOUND", "ABSTAIN"}
_TARGET_STATUSES = {"TRUE_STANDARD", "FALSE_STANDARD", "UNDEFINED", "COHERENT_NOVEL"}


def parse_soundness_v2(response) -> dict:
    """Parse a v2 judge response; fail-closed -> ABSTAIN (never a false UNSOUND/SOUND on garbage)."""
    data = response if isinstance(response, dict) else combinatorial._extract_json(str(response or ""))
    base = {"verdict": "ABSTAIN", "unsound_kind": "none", "governing_constraint": "", "how_exceeded": "",
            "why_governs": "", "mapping_table": "", "stripped_target_claim": "", "target_claim_status": "",
            "failed_predicate": "none", "incoherence_role_pair": "", "confidence": 0.0, "why": ""}
    if not isinstance(data, dict):
        return base
    v = str(data.get("verdict") or "").strip().upper()
    base["verdict"] = v if v in _SOUNDNESS_V2_VERDICTS else "ABSTAIN"
    kind = str(data.get("unsound_kind") or "none").strip().lower()
    base["unsound_kind"] = kind if kind in ("none", "named_law", "incoherent_mapping") else "none"
    fp = str(data.get("failed_predicate") or "none").strip().upper()
    base["failed_predicate"] = fp if fp in ("P1", "P2", "P3") else "none"
    tcs = str(data.get("target_claim_status") or "").strip().upper()
    base["target_claim_status"] = tcs if tcs in _TARGET_STATUSES else ""
    try:
        c = float(data.get("confidence"))
        base["confidence"] = c if math.isfinite(c) else 0.0   # NaN/Infinity (json.loads accepts them) must NOT pass the
    except (TypeError, ValueError):                            # >=0.75 gate (nan<0.75 is False) -> would enable a false UNSOUND
        base["confidence"] = 0.0
    for k, n in (("governing_constraint", 160), ("how_exceeded", 160), ("why_governs", 200), ("mapping_table", 400),
                 ("stripped_target_claim", 300), ("incoherence_role_pair", 120), ("why", 160)):
        base[k] = str(data.get(k) or "")[:n]
    return base


def _valid_unsound_v2(vote, *, min_conf=0.75) -> bool:
    if vote.get("verdict") != "UNSOUND" or float(vote.get("confidence") or 0.0) < min_conf:
        return False
    if vote.get("unsound_kind") == "named_law":
        return bool(vote.get("governing_constraint")) and bool(vote.get("how_exceeded")) and bool(vote.get("why_governs"))
    if vote.get("unsound_kind") == "incoherent_mapping":
        return (vote.get("failed_predicate") in ("P1", "P2", "P3") and bool(vote.get("incoherence_role_pair"))
                and vote.get("target_claim_status") in ("FALSE_STANDARD", "UNDEFINED"))
    return False


def soundness_panel_verdict_v2(votes, *, min_valid: int = 2, min_conf: float = 0.75) -> dict:
    """UNSOUND iff >=min_valid VALID unsound votes -- each backed by a SPECIFIC named artifact (a named law with
    how_exceeded + why_governs, OR a failed predicate P1/P2/P3 with an incoherence_role_pair) at confidence>=min_conf.
    The named-artifact + confidence bar is what protects the sound gate; requiring >=min_valid INDEPENDENT valid
    convictions is the reliable convergence signal -- NOT identical free-text law STRINGS. (The original same-string
    convergence discarded UNANIMOUS convictions: calibration 2026-06-29 found all 3 judges voting UNSOUND-Shannon on a
    Shannon violator but phrasing the law differently -> no string match -> a false SOUND. Dropped.) EXCLUDE iff (not
    UNSOUND) and >=min_valid COHERENT_NOVEL votes (empirically-open -> not LLM-adjudicable). Else SOUND. A lone
    valid-unsound vote with confidence>=0.9 -> flagged (no auto-reject)."""
    vs = list(votes or [])
    valid = [v for v in vs if _valid_unsound_v2(v, min_conf=min_conf)]
    flagged = (len(valid) == 1 and float(valid[0].get("confidence") or 0.0) >= 0.9)
    n_open = sum(1 for v in vs if v.get("target_claim_status") == "COHERENT_NOVEL")
    if len(valid) >= min_valid:
        return {"verdict": "UNSOUND", "n_valid_unsound": len(valid), "converged_on": "",
                "n_coherent_novel": n_open, "flagged": False}
    if n_open >= min_valid:
        return {"verdict": "EXCLUDE", "n_valid_unsound": len(valid), "converged_on": "",
                "n_coherent_novel": n_open, "flagged": flagged}
    return {"verdict": "SOUND", "n_valid_unsound": len(valid), "converged_on": "",
            "n_coherent_novel": n_open, "flagged": flagged}


def parse_soundness(response) -> dict:
    data = response if isinstance(response, dict) else combinatorial._extract_json(str(response or ""))
    if not isinstance(data, dict):
        return {"sound": False, "score": 0.0, "why": ""}
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        score = 0.0
    return {"sound": bool(data.get("sound")), "score": score, "why": str(data.get("why") or "")[:160]}


def soundness_panel_verdict(votes, *, threshold: int = 2) -> dict:
    """2-of-3 (configurable) panel. Empty -> fail-closed (sound False)."""
    vs = list(votes or [])
    n_sound = sum(1 for v in vs if (v or {}).get("sound"))
    return {"sound": (n_sound >= threshold and len(vs) > 0), "n_sound": n_sound, "n_total": len(vs)}


def genuine_survivor(obj_survives, panel) -> bool:
    """A GENUINE survivor = prior-art-distant AND advisory-sound (>=2/3 panel)."""
    return bool(obj_survives) and bool((panel or {}).get("sound"))


def select_topk(candidates, score_fn, k: int) -> list:
    """Deterministic top-k by an injected score (descending); ties broken by stable original order. The SHARED selection
    used by both arm ii (engine-proposed) and arm i* (raw-proposed) — the only difference between them is the PROPOSAL."""
    items = list(candidates or [])
    scored = [(-(float(score_fn(c))), i, c) for i, c in enumerate(items)]
    scored.sort(key=lambda t: (t[0], t[1]))
    return [c for _, _, c in scored[:max(0, int(k))]]


def fisher_exact_p(a, b, c, d, *, alternative: str = "greater") -> float:
    """One-sided Fisher exact over the 2x2 [[a,b],[c,d]] (hypergeometric tail). DIAGNOSTIC only (pooled, ignores
    pair-clustering) — kept for Stage-A comparability; CMH is the primary test."""
    a, b, c, d = int(a), int(b), int(c), int(d)
    r1, r2, k, N = a + b, c + d, a + c, a + b + c + d
    if N == 0:
        return 1.0

    def P(x):
        return (math.comb(r1, x) * math.comb(r2, k - x)) / math.comb(N, k)

    lo, hi = max(0, k - r2), min(r1, k)
    if alternative == "greater":
        return sum(P(x) for x in range(a, hi + 1))
    if alternative == "less":
        return sum(P(x) for x in range(lo, a + 1))
    pa = P(a)
    return sum(P(x) for x in range(lo, hi + 1) if P(x) <= pa + 1e-12)


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def cochran_mantel_haenszel(strata) -> dict:
    """CMH across per-pair 2x2 strata, each ((a,b),(c,d)) = (arm-ii survived/not, arm-i* survived/not). Returns the
    signed one-sided p (direction = arm-ii > arm-i*), the two-sided chi2 (continuity-corrected), the Mantel-Haenszel
    common odds ratio, and n_strata. The PRIMARY test (accounts for within-pair clustering)."""
    sum_a = sum_E = sum_V = 0.0
    num_or = den_or = 0.0
    used = 0
    for st in (strata or []):
        (a, b), (c, d) = st
        a, b, c, d = float(a), float(b), float(c), float(d)
        n = a + b + c + d
        if n <= 1:
            continue
        r1, r2, col1, col2 = a + b, c + d, a + c, b + d
        v = (r1 * r2 * col1 * col2) / (n * n * (n - 1))
        if v <= 0:          # an all-zero row/column carries no information -> not an informative stratum
            continue
        used += 1
        sum_a += a
        sum_E += r1 * col1 / n
        sum_V += v
        num_or += a * d / n
        den_or += b * c / n
    if used == 0 or sum_V <= 0:
        return {"z": 0.0, "p_one_sided": 1.0, "cmh_chi2": 0.0, "common_or": float("nan"), "n_strata": used}
    diff = sum_a - sum_E
    z = diff / math.sqrt(sum_V)
    chi2 = (abs(diff) - 0.5) ** 2 / sum_V if abs(diff) > 0.5 else 0.0   # two-sided, continuity-corrected
    p_one = 1.0 - _norm_cdf(z)                                          # greater (arm-ii > arm-i*)
    common_or = (num_or / den_or) if den_or > 0 else float("inf")
    return {"z": z, "p_one_sided": p_one, "cmh_chi2": chi2, "common_or": common_or, "n_strata": used}


def _pooled_delta(records, *, treat_key="ii", base_key="istar") -> float:
    st = nt = sb = nb = 0
    for r in records:
        a, na = r[treat_key]; c, nc = r[base_key]
        st += a; nt += na; sb += c; nb += nc
    rt = st / nt if nt else 0.0
    rb = sb / nb if nb else 0.0
    return rt - rb


def cluster_bootstrap_delta_ci(pair_records, *, seed: int = 0, iters: int = 2000, alpha: float = 0.05,
                               treat_key: str = "ii", base_key: str = "istar") -> dict:
    """Cluster (pair) bootstrap CI on the pooled rate delta (treat_key - base_key). Resample PAIRS with replacement
    (NOT candidates) — the correct unit under within-pair clustering (Cameron-Gelbach-Miller 2008). Seeded.
    Defaults (ii/istar) reproduce the v3 contrast; v4 passes treat_key='eng_strong', base_key='raw_strong'."""
    recs = list(pair_records or [])
    point = _pooled_delta(recs, treat_key=treat_key, base_key=base_key) if recs else 0.0
    if not recs:
        return {"delta": 0.0, "lo": 0.0, "hi": 0.0, "excludes_zero": False}
    rng = random.Random(seed)
    n = len(recs)
    deltas = []
    for _ in range(int(iters)):
        sample = [recs[rng.randrange(n)] for _ in range(n)]
        deltas.append(_pooled_delta(sample, treat_key=treat_key, base_key=base_key))
    deltas.sort()
    lo = deltas[max(0, int((alpha / 2) * len(deltas)))]
    hi = deltas[min(len(deltas) - 1, int((1 - alpha / 2) * len(deltas)))]
    return {"delta": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "excludes_zero": (lo > 0 or hi < 0)}


def intraclass_correlation(pair_outcomes) -> float:
    """One-way ANOVA ICC for binary outcomes grouped by pair (the design-effect driver). pair_outcomes = list of lists
    of 0/1. ICC = (MSB - MSW) / (MSB + (m0-1)*MSW), clamped to [0,1]. Degenerate -> 0.0."""
    groups = [list(g) for g in (pair_outcomes or []) if g]
    K = len(groups)
    allv = [x for g in groups for x in g]
    N = len(allv)
    if K < 2 or N <= K:
        return 0.0
    grand = sum(allv) / N
    ssb = sum(len(g) * ((sum(g) / len(g)) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - (sum(g) / len(g))) ** 2 for x in g) for g in groups)
    msb = ssb / (K - 1)
    msw = ssw / (N - K)
    sizes = [len(g) for g in groups]
    m0 = (N - sum(s * s for s in sizes) / N) / (K - 1)
    denom = msb + (m0 - 1) * msw
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, (msb - msw) / denom))


def _arm_rates(cands) -> dict:
    cs = list(cands or [])
    n = len(cs)
    surv = sum(1 for c in cs if c.get("survived"))
    gen = sum(1 for c in cs if c.get("genuine"))
    return {"candidates": n, "survivors": surv, "genuine": gen,
            "distant_rate": (surv / n if n else 0.0), "sound_distant_rate": (gen / n if n else 0.0)}


def attribution4(arms) -> dict:
    r = {key: _arm_rates(arms.get(key)) for key in ("i", "i_star", "ii", "iii")}
    def sd(k): return r[k]["sound_distant_rate"]
    def di(k): return r[k]["distant_rate"]
    out = dict(r)
    out["sound_delta_ii_istar"] = round(sd("ii") - sd("i_star"), 4)   # PRIMARY contrast
    out["sound_delta_ii_i"] = round(sd("ii") - sd("i"), 4)
    out["sound_delta_iii_i"] = round(sd("iii") - sd("i"), 4)
    out["sound_delta_ii_iii"] = round(sd("ii") - sd("iii"), 4)
    out["distant_delta_ii_istar"] = round(di("ii") - di("i_star"), 4)
    out["distant_delta_ii_i"] = round(di("ii") - di("i"), 4)
    out["primary_delta"] = out["sound_delta_ii_istar"]
    return out


def attribution_2x2(arms) -> dict:
    """v4 engine@strong probe. arms keyed raw_weak/eng_weak/eng_strong/raw_strong (each a list of {survived, genuine}).
    PRIMARY (distant) = distant_rate(eng_strong) - distant_rate(raw_strong). Distant-only: sound_distant_rate present but
    not the gate this leg."""
    keys = ("raw_weak", "eng_weak", "eng_strong", "raw_strong")
    r = {k: _arm_rates(arms.get(k)) for k in keys}
    def di(k): return r[k]["distant_rate"]
    out = dict(r)
    out["distant_delta_engstrong_rawstrong"] = round(di("eng_strong") - di("raw_strong"), 4)   # PRIMARY
    out["distant_delta_engstrong_engweak"]   = round(di("eng_strong") - di("eng_weak"), 4)
    out["distant_delta_engweak_rawweak"]     = round(di("eng_weak") - di("raw_weak"), 4)
    out["distant_delta_rawstrong_rawweak"]   = round(di("raw_strong") - di("raw_weak"), 4)
    out["distant_interaction"] = round((di("eng_strong") - di("raw_strong"))
                                       - (di("eng_weak") - di("raw_weak")), 4)
    out["primary_delta"] = out["distant_delta_engstrong_rawstrong"]
    return out


def _sound_arm_rates(items) -> dict:
    its = list(items or [])
    distant = [i for i in its if i.get("distant")]
    excluded = [i for i in distant if i.get("sound_state") == "EXCLUDE"]
    adjud = [i for i in distant if i.get("sound_state") in ("SOUND", "UNSOUND")]
    sound = [i for i in adjud if i.get("sound_state") == "SOUND"]
    nd = len(distant)
    return {"n": len(its), "distant": nd, "excluded": len(excluded), "adjudicable": len(adjud), "sound": len(sound),
            "exclusion_rate": (len(excluded) / nd if nd else 0.0),
            "sound_distant_rate": (len(sound) / len(adjud) if adjud else 0.0)}


def attribution_2x2_sound(arms) -> dict:
    """1b sound attribution over 3 states (SOUND/UNSOUND/EXCLUDE). sound_distant_rate = sound / adjudicable-distant;
    exclusion_rate = excluded / distant. PRIMARY = sound_distant(eng_strong) - sound_distant(raw_strong)."""
    keys = ("raw_weak", "eng_weak", "eng_strong", "raw_strong")
    r = {k: _sound_arm_rates(arms.get(k)) for k in keys}
    def sd(k): return r[k]["sound_distant_rate"]
    out = dict(r)
    delta = sd("eng_strong") - sd("raw_strong")
    out["sound_distant_delta_engstrong_rawstrong"] = round(delta, 4)
    out["primary_delta"] = delta
    out["exclusion_by_arm"] = {k: r[k]["exclusion_rate"] for k in keys}
    return out


def stage_b_report_1b(att_sound, cmh, ci, control_verdict_v2, *, exclusion_dominated_threshold: float = 0.5) -> dict:
    """1b sound_distant verdict over the ADJUDICABLE subset. VOID if the v2 panel failed Phase-A. EXCLUSION-DOMINATED if
    the engine arm's exclusion rate exceeds the threshold (the exclusion rate IS the finding). Else CONFIRM (delta>0 AND
    p<0.05 AND CI excludes 0 AND eng_strong sound>=5) / KILL (delta<=0) / DIRECTIONAL."""
    valid = bool(control_verdict_v2.get("panel_valid_v2"))
    delta = att_sound.get("primary_delta", 0.0)
    p = float(cmh.get("p_one_sided", 1.0)); excl = bool(ci.get("excludes_zero"))
    n_sound = int((att_sound.get("eng_strong") or {}).get("sound", 0))
    eng_excl = float((att_sound.get("exclusion_by_arm") or {}).get("eng_strong", 0.0))
    if not valid:
        verdict = "VOID — soundness panel failed its Phase-A validity gate; not trusted, no sound verdict"
    elif eng_excl > exclusion_dominated_threshold:
        verdict = ("EXCLUSION-DOMINATED — most engine survivors are COHERENT_NOVEL-unfalsifiable (not LLM-adjudicable); "
                   "the per-arm exclusion rate IS the finding, sound_distant delta is secondary/underpowered")
    elif delta <= 0:
        verdict = "KILL — engine@strong does NOT beat raw@strong on sound_distant (over the adjudicable subset)"
    elif delta > 0 and p < 0.05 and excl and n_sound >= 5:
        verdict = "CONFIRM (sound_distant) — engine@strong beats raw@strong on the TRUSTED sound axis (over adjudicable items)"
    else:
        verdict = "DIRECTIONAL-ONLY — positive sound_distant delta but not statistically significant"
    return {"verdict": verdict, "primary_metric": "sound_distant_adjudicable", "primary_delta": delta,
            "cmh_p_one_sided": p, "ci": ci, "eng_strong_sound_survivors": n_sound,
            "exclusion_by_arm": att_sound.get("exclusion_by_arm"), "attribution": att_sound,
            "controls": control_verdict_v2,
            "ceiling_caveat": ("Stage B 1b measures engine-attributable + prior-art-distant + advisory-SOUND over the "
                               "ADJUDICABLE subset under protocol P. Genuinely-novel-coherent transfers are EXCLUDED "
                               "(unfalsified != sound; the human-expert boundary) and reported as a per-arm exclusion "
                               "rate. NOT human-verified non-obvious.")}


def _rate(items, pred):
    items = list(items)
    return (sum(1 for x in items if pred(x)) / len(items)) if items else None


def control_verdict_b(control_results, *, neg_void_threshold: int = 2) -> dict:
    """Ruler + soundness-panel validity. `clean` (not VOID) iff fewer than `neg_void_threshold` NEG controls survived the
    objective leg (binomial, NOT all-or-nothing — LLM stochasticity makes >=1 expected). Panel-valid iff hard_neg caught
    >=0.8 AND fringe caught >=0.8 AND neg-as-sound-true rated sound >=0.8. 'caught' (for fringe/hard_neg) = rated UNSOUND."""
    rs = list(control_results or [])
    neg = [r for r in rs if r.get("control") == "neg"]
    pos = [r for r in rs if r.get("control") == "pos"]
    fringe = [r for r in rs if r.get("control") == "fringe"]
    hard = [r for r in rs if r.get("control") == "hard_neg"]
    neg_survived = sum(1 for r in neg if r.get("survived"))
    prior_art_recall = _rate(pos, lambda r: not r.get("survived"))
    fringe_caught = _rate(fringe, lambda r: not r.get("sound"))
    hard_caught = _rate(hard, lambda r: not r.get("sound"))
    sound_true_pass = _rate(neg, lambda r: r.get("sound"))
    def ok(x): return (x is not None and x >= 0.8)
    panel_valid = ok(fringe_caught) and ok(hard_caught) and ok(sound_true_pass)
    return {"clean": neg_survived < neg_void_threshold, "neg_survived": neg_survived, "n_neg": len(neg),
            "prior_art_recall": prior_art_recall, "fringe_caught_rate": fringe_caught,
            "hard_neg_caught_rate": hard_caught, "sound_true_pass_rate": sound_true_pass,
            "soundness_panel_valid": panel_valid}


def control_verdict_soundness_v2(control_results) -> dict:
    """Phase-A validity gate for the v2 panel. panel_valid_v2 iff hard_neg_caught>=0.8 AND sound_true_pass>=0.8 AND
    control_exclusion_rate<=0.2. scope_audit counts neg controls rated UNSOUND via a named law (mis-applied-law
    over-rejection signal)."""
    rs = list(control_results or [])
    neg = [r for r in rs if r.get("control") == "neg"]
    hard = [r for r in rs if r.get("control") == "hard_neg"]
    hard_caught = _rate(hard, lambda r: r.get("sound_verdict") == "UNSOUND")
    sound_true = _rate(neg, lambda r: r.get("sound_verdict") == "SOUND")
    excl = _rate(rs, lambda r: r.get("sound_verdict") == "EXCLUDE")
    scope = sum(1 for r in neg if r.get("sound_verdict") == "UNSOUND" and r.get("unsound_kind") == "named_law")
    def ok(x): return x is not None and x >= 0.8
    panel_valid = ok(hard_caught) and ok(sound_true) and (excl is not None and excl <= 0.2)
    return {"hard_neg_caught_rate": hard_caught, "sound_true_pass_rate": sound_true,
            "control_exclusion_rate": excl, "n_scope_audit_flags": scope, "panel_valid_v2": panel_valid}


def sequential_decision(ci, *, pairs_done: int, max_pairs: int) -> dict:
    """Group-sequential interim rule on the cluster-bootstrap CI of the primary delta. confirm if CI excludes 0 positive;
    kill if the point estimate is non-positive; extend if it straddles 0 with a positive point AND budget remains; else
    stop (the final pre-registered test decides). The interim does NOT spend the full alpha (the final test is the gate)."""
    lo, hi, delta = float(ci.get("lo", 0)), float(ci.get("hi", 0)), float(ci.get("delta", 0))
    if delta <= 0:
        return {"action": "kill", "reason": "primary point estimate non-positive at interim"}
    if lo > 0:
        return {"action": "confirm", "reason": "CI excludes 0 (positive) at interim"}
    if pairs_done < max_pairs:
        return {"action": "extend", "reason": "CI straddles 0 with positive point; budget remains"}
    return {"action": "stop", "reason": "at max pairs; defer to final test"}


def stage_b_report(attribution4_dict, cmh, ci, control_verdict_b_dict, off_distribution, kappa, cost_by_arm) -> dict:
    """The honest pre-registered Stage-B verdict. VOID dominates; UNTRUSTED soundness falls back to distant_rate; else
    CONFIRM iff (delta>0 AND CMH p<0.05 AND bootstrap CI excludes 0 AND arm-ii >=5 genuine survivors), DIRECTIONAL-ONLY
    iff delta>0 not-significant, KILL iff delta<=0."""
    void = not bool(control_verdict_b_dict.get("clean", False))
    panel_valid = bool(control_verdict_b_dict.get("soundness_panel_valid", False))
    untrusted = not panel_valid
    primary_metric = "sound_distant" if panel_valid else "distant"
    delta = attribution4_dict.get("primary_delta" if panel_valid else "distant_delta_ii_istar", 0.0)
    p = float(cmh.get("p_one_sided", 1.0))
    excl = bool(ci.get("excludes_zero"))
    ii = attribution4_dict.get("ii") or {}
    n_gen = int(ii.get("genuine", 0))
    # the pre-registered ">=5 survivor" floor tracks the ACTIVE primary metric: genuine (sound+distant) when the panel is
    # trusted, else the distant survivors under the distant_rate fallback (else a broken panel would zero the floor).
    n_floor = n_gen if panel_valid else int(ii.get("survivors", 0))
    if void:
        verdict = "VOID — adjudication ruler leaked (>= neg-control threshold survived); fix before any verdict"
    elif delta <= 0:
        verdict = "KILL — the engine does NOT beat the matched top-k-novelty selector (arm ii - arm i* <= 0)"
    elif delta > 0 and p < 0.05 and excl and n_floor >= 5:
        verdict = "CONFIRM — engine beats the matched selector, statistically significant (cluster-robust)"
    else:
        verdict = "DIRECTIONAL-ONLY — positive delta but not statistically significant (still underpowered)"
    if untrusted and not void:
        verdict += "  [SOUNDNESS-UNTRUSTED: panel failed its controls -> on distant_rate fallback]"
    return {"verdict": verdict, "primary_metric": primary_metric, "soundness_untrusted": untrusted,
            "primary_delta": delta, "cmh_p_one_sided": p, "ci": ci, "ii_genuine_survivors": n_gen,
            "attribution": attribution4_dict, "controls": control_verdict_b_dict, "adjudicator_kappa": kappa,
            "off_distribution": off_distribution, "cost_by_arm": cost_by_arm,
            "ablation": {"ii_minus_istar": attribution4_dict.get("primary_delta"),
                         "ii_minus_i": attribution4_dict.get("sound_delta_ii_i"),
                         "iii_minus_i": attribution4_dict.get("sound_delta_iii_i"),
                         "ii_minus_iii": attribution4_dict.get("sound_delta_ii_iii")},
            "ceiling_caveat": ("Stage B v3 measures engine-attributable + prior-art-distant + advisory-sound under protocol "
                               "P. PRIMARY contrast arm-ii vs a MATCHED top-k-novelty selector arm-i* (SYSTEM-LEVEL: "
                               "generation + native style, NOT isolated). Prior-art = a DUAL leg on ORIGINAL claim text: "
                               "sonar-pro OR-killed with a deterministic SPECTER2-kNN leg (style-robust), cluster-robust "
                               "stats. It does NOT measure human-verified non-obvious, and the kNN leg BOUNDS but does not "
                               "erase the retrieval-blind-spot confound. Missed prior art still inflates BOTH arms, so the "
                               "rate-DELTA is the signal.")}


def stage_b_report_2x2(attribution_2x2_dict, cmh, ci, control_verdict_b_dict, off_distribution, kappa,
                       cost_by_arm) -> dict:
    """v4 DISTANT-ONLY report. PRIMARY = distant(eng_strong - raw_strong). VOID dominates (neg-control ruler leak); else
    CONFIRM iff (delta>0 AND CMH p<0.05 AND bootstrap CI excludes 0 AND eng_strong >= 5 distant survivors) -> headline
    RESURRECTED pending soundness (1b); DIRECTIONAL iff delta>0 not-significant; KILL iff delta<=0 -> the engine's value
    was model strength, not machinery. No soundness panel this leg (distant != sound)."""
    void = not bool(control_verdict_b_dict.get("clean", False))
    delta = attribution_2x2_dict.get("primary_delta", 0.0)
    p = float(cmh.get("p_one_sided", 1.0))
    excl = bool(ci.get("excludes_zero"))
    eng_strong = attribution_2x2_dict.get("eng_strong") or {}
    n_floor = int(eng_strong.get("survivors", 0))
    if void:
        verdict = "VOID — adjudication ruler leaked (>= neg-control threshold survived); fix before any verdict"
    elif delta <= 0:
        verdict = ("KILL — engine@strong does NOT beat raw@strong on prior-art-distance (eng_strong - raw_strong <= 0): "
                   "the engine's measured value was model strength, not machinery")
    elif delta > 0 and p < 0.05 and excl and n_floor >= 5:
        verdict = ("CONFIRM (distant-only) — engine@strong beats raw@strong on prior-art-distance, cluster-robust; "
                   "headline RESURRECTED pending soundness (build 1b)")
    else:
        verdict = "DIRECTIONAL-ONLY — positive distant delta but not statistically significant (underpowered)"
    return {"verdict": verdict, "primary_metric": "distant", "primary_delta": delta, "cmh_p_one_sided": p, "ci": ci,
            "eng_strong_distant_survivors": n_floor, "attribution": attribution_2x2_dict,
            "controls": control_verdict_b_dict, "adjudicator_kappa": kappa, "off_distribution": off_distribution,
            "cost_by_arm": cost_by_arm,
            "ablation": {"engstrong_minus_rawstrong": attribution_2x2_dict.get("distant_delta_engstrong_rawstrong"),
                         "engstrong_minus_engweak": attribution_2x2_dict.get("distant_delta_engstrong_engweak"),
                         "engweak_minus_rawweak": attribution_2x2_dict.get("distant_delta_engweak_rawweak"),
                         "rawstrong_minus_rawweak": attribution_2x2_dict.get("distant_delta_rawstrong_rawweak"),
                         "interaction": attribution_2x2_dict.get("distant_interaction")},
            "ceiling_caveat": ("Stage B v4 (engine@strong probe, DISTANT-ONLY) measures engine-attributable + "
                               "prior-art-distant under protocol P. PRIMARY = engine@strong (single opus-4.7 proposer) vs "
                               "raw@strong (opus-4.7), matched tier, paired-by-pair (CMH + cluster-bootstrap CI). The "
                               "soundness panel is NOT run this leg (distant != sound). It does NOT measure advisory-sound "
                               "(needs build 1b) or human-verified non-obvious. The dual prior-art leg bounds but does not "
                               "erase the retrieval-blind-spot confound; missed prior art inflates BOTH arms, so the "
                               "rate-DELTA is the signal.")}
