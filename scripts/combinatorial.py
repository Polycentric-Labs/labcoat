# scripts/combinatorial.py
"""labcoat N3 — combinatorial / analogical synthesis: the PURE engine that generates-scores-archives novel
cross-domain combinations. Design (grounded in the 2026-06-23 research synthesis Q-N3):
  - PROPOSER brain != JUDGE brain (partition_fleet) — the single most-demanded call (novelty mirage 2606.12071,
    self-preference 2404.13076, evaluator separation CORAL 2604.01658).
  - creativity = novelty x utility, MULTIPLICATIVE (2509.21043) — trivial OR incoherent -> ~0 (never additive).
  - analogical-reasoning proposer (base->target relational mapping, 2605.11258), NOT free-association.
  - retrieval-grounded novelty judge (N1 / RND 2503.01508 / 2506.22026) — never an unanchored 'is this novel?'.
  - MAP-Elites archive (1504.04909 / DEI 2605.27130) over the (domainA,domainB,mechanism) descriptor: report
    COVERAGE + QD-SCORE, not a single best.
HONEST LIMITS (do not overclaim): QD-score is an UPPER BOUND on diversity+surface-plausibility, NOT a value
estimate — ideation novelty decays under execution (2506.20803), so post-grounding survival is reported SEPARATELY
and coverage/QD-score is NEVER surfaced as 'N discoveries'. Descriptor binning here is a STRUCTURAL placeholder
(normalized-string hash); semantic descriptor clustering (embedding) is the seam/future work. The model-touching
parts are pure PROMPT builders + INJECTED novelty_fn/utility_fn. ADVISORY; not wired to a live loop this round.
Pure stdlib; deterministic; no network/key/datetime.now(). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import re
import hashlib
import novelty_gate

_MAX_COMBINATIONS = 100


def _extract_json(s):
    """Pull a JSON value from a brain response that may be fenced/prose-wrapped (mirrors nuclear_core)."""
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
    if isinstance(obj, str):
        obj = _extract_json(obj)
        if obj is None:
            return []
    if isinstance(obj, dict):
        for key in ("combinations", "items", "candidates", "results"):
            if isinstance(obj.get(key), list):
                return obj[key]
        return []
    return obj if isinstance(obj, list) else []


def parse_combinations(obj) -> list:
    """Normalize proposer brain output into [{id, domain_a, domain_b, mechanism, claim}]. Drops entries missing
    any of domain_a / domain_b / mechanism (a combination needs two domains + a transferred mechanism); claim may
    be empty at parse. Assigns c1..cN; caps at _MAX_COMBINATIONS. Tolerant of JSON-string/fenced/enveloped input."""
    out = []
    for item in _coerce(obj):
        if not isinstance(item, dict):
            continue
        da = str(item.get("domain_a") or "").strip()
        db = str(item.get("domain_b") or "").strip()
        mech = str(item.get("mechanism") or "").strip()
        if not (da and db and mech):
            continue
        out.append({"id": str(item.get("id") or f"c{len(out) + 1}"), "domain_a": da, "domain_b": db,
                    "mechanism": mech, "claim": str(item.get("claim") or "").strip()})
        if len(out) >= _MAX_COMBINATIONS:
            break
    return out


def structural_coherence(combination) -> bool:
    """Pure pre-admission gate: kill obvious degenerates BEFORE any (costly) judge call. Require two DISTINCT
    non-empty domains (a cross-domain combination, not a self-combination), a non-empty mechanism, and a non-empty
    claim. (Semantic coherence is the brain judge's job — this is the cheap structural floor.)"""
    if not isinstance(combination, dict):
        return False
    da = str(combination.get("domain_a") or "").strip().lower()
    db = str(combination.get("domain_b") or "").strip().lower()
    mech = str(combination.get("mechanism") or "").strip()
    claim = str(combination.get("claim") or "").strip()
    return bool(da and db and mech and claim and da != db)


def creativity_score(novelty: float, utility: float) -> float:
    """The N3 admission score = novelty x utility, both clamped to [0,1]. MULTIPLICATIVE on purpose (2509.21043):
    a trivial (low-novelty) OR an incoherent/useless (low-utility) combination scores ~0 — an additive blend would
    let a hyper-novel-but-useless idea survive on novelty alone (the ideation-execution failure 2506.20803)."""
    n = min(1.0, max(0.0, float(novelty)))
    u = min(1.0, max(0.0, float(utility)))
    return n * u


def _norm(s: str) -> str:
    return novelty_gate.normalize(str(s or ""))


def combination_descriptor(combination) -> tuple:
    """The (domainA, domainB, mechanism) descriptor, normalized + the domain PAIR order-normalized (sorted) so a
    combination and its mirror map to one cell (a cross-domain combination is symmetric).
    Assumes a valid combination record (post-parse_combinations / post-structural_coherence); missing keys
    normalize to empty strings."""
    da, db = sorted([_norm(combination.get("domain_a")), _norm(combination.get("domain_b"))])
    return (da, db, _norm(combination.get("mechanism")))


def _bucket(text: str, bins: int) -> int:
    """Stable hash of a normalized string into [0, bins). Deterministic across processes (hashlib, not hash())."""
    h = hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()
    return int(h, 16) % int(bins)


def cell_index(descriptor, *, bins: int = 16) -> tuple:
    """Map a descriptor to a finite grid cell (bins per dimension -> bins**3 total cells) so coverage is
    measurable. STRUCTURAL placeholder: exact-after-normalization descriptors co-locate; semantic clustering of
    near-but-not-identical descriptors is the seam/future work (the honest descriptor-design open question)."""
    da, db, mech = descriptor
    return (_bucket(da, bins), _bucket(db, bins), _bucket(mech, bins))


def admit(archive, *, cell, candidate, creativity) -> dict:
    """MAP-Elites admission (pure — returns a NEW dict): the cell keeps its single highest-creativity elite.
    Replace iff the cell is empty OR `creativity` is strictly greater than the incumbent's.
    The candidate is shallow-copied on storage so mutating the original dict after admission cannot corrupt
    the archive."""
    out = dict(archive or {})
    cur = out.get(cell)
    if cur is None or float(creativity) > cur.get("creativity", float("-inf")):
        out[cell] = {"creativity": float(creativity), "candidate": dict(candidate) if isinstance(candidate, dict) else candidate}
    return out


def coverage(archive, *, bins: int = 16) -> float:
    """Fraction of grid cells filled = |archive| / bins**3. The QD 'illuminate the space' signal (not best-only)."""
    total = int(bins) ** 3
    return (len(archive or {}) / total) if total else 0.0


def qd_score(archive) -> float:
    """QD-score = sum of elite creativity over filled cells. HONEST: an UPPER BOUND on diversity+surface-
    plausibility, NOT a value estimate (see module docstring / archive_report)."""
    return float(sum(float(v.get("creativity", 0.0)) for v in (archive or {}).values()))


def elites(archive) -> list:
    """The elite candidate dicts across all filled cells (order not guaranteed)."""
    return [v["candidate"] for v in (archive or {}).values() if v.get("candidate") is not None]


def propose_prompt(domain_a: str, domain_b: str, *, n: int = 3) -> str:
    """Pure builder: the ANALOGICAL-REASONING proposer. Forces base->target relational structure-mapping (the
    measured advantage over free-association; 2605.11258), NOT 'brainstorm wild combinations'."""
    return (
        f"You are a combinatorial-creativity proposer. Find the shared RELATIONAL STRUCTURE between DOMAIN A "
        f"({domain_a}) and DOMAIN B ({domain_b}), then TRANSFER a specific mechanism from one to the other to "
        f"produce at most {n} novel, specific, TESTABLE cross-domain combinations. Map the relational structure "
        "explicitly; do not free-associate or restate the domains.\n\n"
        "Return STRICT JSON only: a list of objects, each {\"domain_a\": \"...\", \"domain_b\": \"...\", "
        "\"mechanism\": \"the transferred mechanism\", \"claim\": \"the specific, testable cross-domain claim\"}. "
        "No prose.")


def judge_prompt(combination, retrieved_prior_art) -> str:
    """Pure builder: the RETRIEVAL-GROUNDED judge. The model judges the combination AGAINST the retrieved prior
    art along explicit facets (nearest prior work / plausibility / utility) — it is NEVER asked an unanchored
    'is this novel?' (the novelty mirage 2606.12071). Novelty itself is scored externally (N1); this judge cites
    the nearest prior work + assesses plausibility & utility."""
    art = "\n".join(f"- {a}" for a in (retrieved_prior_art or [])) or "(no prior art retrieved)"
    claim = str((combination or {}).get("claim") or "")
    return (
        "You are the retrieval-grounded JUDGE for a cross-domain combination. Judge the CANDIDATE only AGAINST "
        "the RETRIEVED PRIOR ART below — do not rely on parametric memory. Identify the NEAREST prior work (cite "
        "it), then rate plausibility (is the mechanism transfer coherent?) and utility (is the claim useful / "
        "testable?). Do not answer a free-form 'is this novel?'.\n\n"
        f"CANDIDATE CLAIM: {claim}\nMECHANISM: {str((combination or {}).get('mechanism') or '')}\n\n"
        f"RETRIEVED PRIOR ART:\n{art}\n\n"
        "Return STRICT JSON only: {\"nearest_prior_work\": \"...\", \"plausibility\": 0.0, \"utility\": 0.0, "
        "\"rationale\": \"...\"}. plausibility/utility in [0,1]. No prose.")


def partition_fleet(models, *, judge_ids=None, judge_fraction: float = 0.5) -> dict:
    """Split the fleet into DISJOINT proposer_pool and judge_pool — the single most-demanded N3 architectural call
    (proposer brain != judge brain). If judge_ids is given, those models judge and the rest propose; else the last
    ceil(judge_fraction * N) models judge. Raises if the result would leave either pool empty (so the invariant
    'a model never both proposes and judges its own output' is structurally guaranteed)."""
    ms = list(models or [])
    if judge_ids is not None:
        jids = {str(j) for j in judge_ids}
        judge = [m for m in ms if str(m.get("id")) in jids]
        propose = [m for m in ms if str(m.get("id")) not in jids]
    else:
        import math
        k = max(1, math.ceil(float(judge_fraction) * len(ms)))
        propose, judge = ms[:len(ms) - k], ms[len(ms) - k:]
    if judge_ids is not None and not judge:
        raise ValueError("partition_fleet: judge_ids matched no models in the fleet")
    if not judge:
        raise ValueError("partition_fleet: judge_pool would be empty")
    if not propose:
        raise ValueError("partition_fleet: proposer_pool would be empty (judge_ids matched all models?)")
    return {"proposer_pool": propose, "judge_pool": judge}


def run_round(combinations, *, novelty_fn, utility_fn, archive=None, bins: int = 16) -> dict:
    """Pure single-round N3 driver over parsed combinations. For each: structural_coherence gate (reject
    degenerates BEFORE scoring) -> creativity = creativity_score(novelty_fn(c), utility_fn(c)) -> descriptor ->
    cell -> admit. novelty_fn/utility_fn are INJECTED (the seam: novelty_fn = N1 external_novelty over retrieved
    prior art; utility_fn = the grounded-utility score). Returns {archive, admitted, rejected_incoherent,
    zero_value, report}.
    A structurally-coherent combination scoring creativity==0 (zero novelty OR zero utility) is NOT archived (it
    is no elite); its id is recorded in `zero_value`. So the archive/coverage reflect only value-bearing cells.
    Fully deterministic given the injected scorers — the live fleet/judge calls live outside (deferred)."""
    arch = dict(archive or {})
    admitted, rejected, zero_value = [], [], []
    for c in (combinations or []):
        if not structural_coherence(c):
            rejected.append(c.get("id"))
            continue
        cr = creativity_score(novelty_fn(c), utility_fn(c))
        if cr > 0.0:
            cell = cell_index(combination_descriptor(c), bins=bins)
            arch = admit(arch, cell=cell, candidate=c, creativity=cr)
            admitted.append({"id": c.get("id"), "cell": cell, "creativity": cr})
        else:
            zero_value.append(c.get("id"))
    return {"archive": arch, "admitted": admitted, "rejected_incoherent": rejected,
            "zero_value": zero_value, "report": archive_report(arch, bins=bins)}


def parse_judge(obj) -> dict:
    """Normalize a retrieval-grounded JUDGE response into {nearest_prior_work, plausibility, utility, rationale}.
    Tolerant of JSON-string / fenced / enveloped input (reuses _extract_json). plausibility/utility clamped to
    [0,1]; missing/invalid numerics -> 0.0; missing strings -> ''. The utility_fn signal source."""
    data = _extract_json(obj) if isinstance(obj, str) else obj
    if not isinstance(data, dict):
        return {"nearest_prior_work": "", "plausibility": 0.0, "utility": 0.0, "rationale": ""}

    def _f(key):
        try:
            return min(1.0, max(0.0, float(data.get(key))))
        except (TypeError, ValueError):
            return 0.0

    return {"nearest_prior_work": str(data.get("nearest_prior_work") or ""),
            "plausibility": _f("plausibility"), "utility": _f("utility"),
            "rationale": str(data.get("rationale") or "")}


def aggregate_utility(judge_dicts) -> float:
    """Combine multiple judges' verdicts into ONE utility in [0,1] = mean over judges of (plausibility * utility).
    Multiplicative per judge (incoherent OR useless -> ~0); averaged across the disjoint judge pool. Empty -> 0.0.
    Each item may be a parse_judge dict OR a raw judge response (str/dict) -> parsed via parse_judge."""
    ds = list(judge_dicts or [])
    if not ds:
        return 0.0
    total = 0.0
    for d in ds:
        j = d if (isinstance(d, dict) and "plausibility" in d and "utility" in d) else parse_judge(d)
        p = min(1.0, max(0.0, float(j.get("plausibility", 0.0) or 0.0)))
        u = min(1.0, max(0.0, float(j.get("utility", 0.0) or 0.0)))
        total += p * u
    return min(1.0, max(0.0, total / len(ds)))


def ground_prompt(combination) -> str:
    """Pure builder: the hard-skeptic WEB-GROUNDING pass on an ELITE combination. The brain (with web access)
    verifies the cross-domain CLAIM against PRIMARY sources and decides whether it SURVIVES — coherent, NOT
    already trivially well-known as stated, and NOT refuted. Skeptical by default (grounded=false on doubt):
    post-grounding survival is the only 'real' signal (2506.20803)."""
    c = combination or {}
    claim = str(c.get("claim") or "")
    mech = str(c.get("mechanism") or "")
    return (
        "You are a HARD-SKEPTIC grounding verifier with web access. Verify the following cross-domain CLAIM against "
        "PRIMARY sources (search the literature/web). Decide if it SURVIVES: it is coherent, NOT already trivially "
        "well-known/established as stated, and NOT refuted by existing evidence. Be skeptical: if you cannot "
        "substantiate that it survives, mark grounded=false.\n\n"
        f"CLAIM: {claim}\nMECHANISM: {mech}\n\n"
        "Return STRICT JSON only: {\"grounded\": true|false, \"verdict\": "
        "\"survives|already-known|refuted|incoherent\", \"evidence\": \"cite the primary source(s) consulted\"}. "
        "No prose.")


def parse_grounding(obj) -> dict:
    """Tolerant parse of a ground_prompt response -> {grounded, verdict, evidence}. FAIL-CLOSED: grounded defaults
    to False on any missing / ambiguous / parse failure (unverified != survived)."""
    data = _extract_json(obj) if isinstance(obj, str) else obj
    if not isinstance(data, dict):
        return {"grounded": False, "verdict": "", "evidence": ""}
    g = data.get("grounded")
    grounded = (g is True) or (isinstance(g, str) and g.strip().lower() in ("true", "yes", "survives"))
    return {"grounded": bool(grounded), "verdict": str(data.get("verdict") or ""),
            "evidence": str(data.get("evidence") or "")}


def archive_report(archive, *, bins: int = 16, grounded_survivors=None) -> dict:
    """The HONEST N3 report. coverage + qd_score (EXPLICITLY labeled an upper bound on diversity+surface-
    plausibility, never a discovery count) + n_elites + post_grounding_survival_rate (the survivors that passed
    downstream grounding / total elites) reported SEPARATELY — None when no grounding data is supplied (honestly
    undefined, not faked). This is the 'never report QD-score as N discoveries' discipline (2506.20803).
    Coverage is a LOWER BOUND on actual descriptor diversity — hash-bucket collisions (cell_index) can merge
    distinct descriptors into one cell; qd_score is the value signal."""
    n = len(archive or {})
    survival = None
    if grounded_survivors is not None:
        survivors = {str(s) for s in grounded_survivors}
        ids = {str(v["candidate"].get("id")) for v in (archive or {}).values() if v.get("candidate")}
        survival = (len(survivors & ids) / len(ids)) if ids else 0.0
    return {"coverage": coverage(archive, bins=bins), "qd_score": qd_score(archive),
            "qd_score_is_upper_bound": True, "n_elites": n, "post_grounding_survival_rate": survival}
