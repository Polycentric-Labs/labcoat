# scripts/gap_channels.py
"""labcoat N2 — gap / whitespace channels: the PURE multi-channel detector that enriches Unit A's single LLM gap
stage. Channels (research synthesis Q-N2): structural ABC-whitespace (Swanson undiscovered-public-knowledge),
future-work mining, structural contradiction, + a RECONCILIATION layer that tags each candidate's evidentiary
status (the integration the field says is unsolved -> N2's differentiator). Then two-axis (novelty + utility)
scoring (never a single LLM-judge self-score). Output converts to loop_evolution's gap-record shape.
HONEST LIMITS: an absent graph edge is a gap ONLY if the two concepts are textually/semantically related (so
abc_whitespace fuses with an injected relatedness_fn — naive ABC has high false positives, synthesis finding 3);
no benchmark exists, so N2 emits scored HYPOTHESES, not validated gaps (the loop is the prospective validation).
The known-but-unaddressed upgrade requires BOTH concepts in a SINGLE future-work sentence (word-boundary match)
— still a heuristic; semantic matching is future work.
The concept-graph / claim extraction that BUILDS the inputs from a corpus is the deferred adapter seam. Inputs
injected; pure stdlib; no network/key/datetime.now(). ADVISORY. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import math
import re

_MAX = 50


def abc_whitespace(edges, *, relatedness_fn=None, min_relatedness: float = 0.0, max_candidates: int = _MAX,
                   max_bridge_degree=None, provenance=None, exclude_intra=False) -> list:
    """Swanson ABC open-discovery: over an undirected concept CO-OCCURRENCE graph, find concept pairs (A,C) that
    are 2-hop connected through a shared bridge B (A-B and B-C edges) but have ZERO direct A-C edge -> a
    structurally identifiable whitespace. Fuses with text: if relatedness_fn is given, keep (A,C) only when
    relatedness_fn(A,C) >= min_relatedness (drops spurious absent edges). Returns [{a, c, bridges}], a<=c.
    `max_bridge_degree`: if given (not None), exclude bridges whose degree > max_bridge_degree (hub-flood fix:
    the corpus topic-term co-occurs with everything, becoming a trivial B that floods spurious gaps).
    `provenance`: optional {frozenset({x,y}): {doc_ids}} (see cooccurrence_provenance). When given, each gap
    gains "paper_scope": "cross" iff SOME bridge B has its A-B and B-C witnessing doc-sets not identical to a
    single shared paper (i.e. they differ, or together span >1 paper); "intra" iff every bridge's A-B and B-C
    are only ever co-witnessed within the same single paper. `exclude_intra=True` drops intra gaps.
    `provenance=None` -> output byte-identical to today (no paper_scope key)."""
    adj = {}
    for e in (edges or []):
        if not (isinstance(e, (list, tuple)) and len(e) >= 2):
            continue
        a, b = str(e[0]).strip(), str(e[1]).strip()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    degree = {k: len(v) for k, v in adj.items()}
    out, nodes = [], sorted(adj)
    for i, a in enumerate(nodes):
        for c in nodes[i + 1:]:
            if c in adj.get(a, set()):                       # direct co-mention -> not a gap
                continue
            bridges = adj.get(a, set()) & adj.get(c, set())  # shared neighbours B
            if max_bridge_degree is not None:
                bridges = {b for b in bridges if degree.get(b, 0) <= int(max_bridge_degree)}  # drop HUB bridges
            if not bridges:
                continue
            if relatedness_fn is not None and float(relatedness_fn(a, c)) < float(min_relatedness):
                continue
            rec = {"a": a, "c": c, "bridges": sorted(bridges)}
            if provenance is not None:
                scope = "intra"
                for b in bridges:
                    ab = provenance.get(frozenset({a, b})) or set()
                    bc = provenance.get(frozenset({b, c})) or set()
                    if ab and bc and (ab - bc or bc - ab or len(ab | bc) > 1):
                        scope = "cross"
                        break
                if exclude_intra and scope == "intra":
                    continue
                rec["paper_scope"] = scope
            out.append(rec)
            if len(out) >= int(max_candidates):
                return out
    return out


_FW_PATTERNS = [r"future work", r"in (?:the )?future", r"we (?:will|plan to|leave)\b",
                r"remains? (?:an? )?open", r"could be extended", r"left (?:for|to) future",
                r"promising direction", r"open (?:question|problem)"]


def mine_future_work(text) -> list:
    """Extract author-stated FUTURE-WORK sentences (high recall, tagged LOW-TRUST downstream — they are vague,
    self-promotional, and often already addressed by concurrent work). Pure sentence split + pattern match."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", str(text or "")):
        sl = s.lower()
        if any(re.search(p, sl) for p in _FW_PATTERNS):
            t = s.strip()
            if t:
                out.append(t)
    return out


def find_contradictions(claims) -> list:
    """Structural EXPLICIT contradiction channel. A contradiction requires the SAME subject AND the SAME context —
    scientific contradictions are mostly CONDITIONAL (research tweak A: differing context = reconcilable, NOT a
    contradiction). Group by (subject, context); flag a group whose claims disagree (opposing polarity OR distinct
    values). No-context claims share the '' (unconditioned) group. Returns [{subject, context, claims}]."""
    by_key = {}
    for c in (claims or []):
        if not isinstance(c, dict):
            continue
        subj = str(c.get("subject") or c.get("key") or "").strip().lower()
        if not subj:
            continue
        ctx = str(c.get("context") or "").strip().lower()
        by_key.setdefault((subj, ctx), []).append(c)
    out = []
    for (subj, ctx), items in by_key.items():
        polarities = {str(c.get("polarity") or "").strip() for c in items if str(c.get("polarity") or "").strip()}
        values = {str(c.get("value") or "").strip().lower() for c in items if str(c.get("value") or "").strip()}
        if len(polarities) > 1 or len(values) > 1:
            out.append({"subject": subj, "context": ctx, "claims": items})
    return out


def _pair_key(a, c) -> str:
    return " | ".join(sorted([str(a).strip().lower(), str(c).strip().lower()]))


def reconcile_channels(*, structural=None, future_work=None, contradictions=None, addressed=None) -> list:
    """The RECONCILIATION layer: merge the channels into unified candidate-gap records, tagging each with an
    evidentiary status — 'whitespace' (structural only), 'known-but-unaddressed' (structural AND future-work),
    'speculative' (future-work only), 'contradiction' (contradiction channel). Drops any structural gap whose
    pair-key is in `addressed` (already explored/solved). Pure; provenance preserved per record."""
    _addressed = set(addressed or ())
    fw = [str(s).strip() for s in (future_work or []) if str(s).strip()]
    fw_lower = [s.lower() for s in fw]
    matched_fw = set()                      # indices of fw sentences that corroborated a structural gap
    out = []
    for g in (structural or []):
        a, c = g.get("a"), g.get("c")
        key = _pair_key(a, c)
        if key in _addressed:
            continue
        a_l, c_l = str(a or "").strip().lower(), str(c or "").strip().lower()
        in_fw, hit_idx = False, None
        if a_l and c_l:
            ra, rc = r"\b" + re.escape(a_l) + r"\b", r"\b" + re.escape(c_l) + r"\b"
            for idx, s in enumerate(fw_lower):
                if re.search(ra, s) and re.search(rc, s):
                    in_fw, hit_idx = True, idx
                    break
        status = "known-but-unaddressed" if in_fw else "whitespace"
        if in_fw:
            matched_fw.add(hit_idx)
        out.append({"text": f"the unexplored link between {a} and {c} (bridged by {', '.join(g.get('bridges') or [])})",
                    "gap_type": "structural", "evidentiary_status": status,
                    "channels": ["structural"] + (["future_work"] if in_fw else []),
                    "provenance": {"bridges": g.get("bridges"), "pair_key": key}})
    # future-work statements not matched to a structural pair -> speculative
    for idx, s in enumerate(fw):
        if idx in matched_fw:
            continue
        out.append({"text": s, "gap_type": "future_work", "evidentiary_status": "speculative",
                    "channels": ["future_work"], "provenance": {}})
    for con in (contradictions or []):
        out.append({"text": f"contradiction on: {con.get('subject')}", "gap_type": "contradiction",
                    "evidentiary_status": "contradiction", "channels": ["contradiction"],
                    "provenance": {"claims": con.get("claims")}})
    return out


def score_gap(gap, *, novelty: float, utility: float) -> dict:
    """Two-axis scoring: attach novelty_score AND utility_score (clamped [0,1]) to the gap record — N2 must NOT
    collapse to a single novelty scalar (the loop optimizes the joint frontier). `priority` = novelty*utility is
    an ADVISORY rank hint only (multiplicative, like N3 creativity: novel-but-useless or trivial -> low). Pure."""
    n = min(1.0, max(0.0, float(novelty)))
    u = min(1.0, max(0.0, float(utility)))
    out = dict(gap or {})
    out.update({"novelty_score": n, "utility_score": u, "priority": n * u})
    return out


_STATUS_TO_KIND = {"contradiction": "contradiction", "known-but-unaddressed": "future_work",
                   "speculative": "future_work", "whitespace": "gap"}


def to_next_question_candidates(reconciled_gaps) -> list:
    """Convert reconciled N2 gaps into loop_evolution's gap-record shape {kind, text, seed_evidence} so the
    multi-channel output feeds the existing rank_gaps / select_evolved_questions (contradictions rank first there).
    The evidentiary_status maps to the loop_evolution kind; provenance becomes seed_evidence. Pure.
    The 4 loop_evolution kinds are a COARSE first-pass bucket; the precise evidentiary tier (whitespace /
    known-but-unaddressed / speculative / contradiction) is carried in seed_evidence so the loop brain can
    re-rank — the kind projection is intentionally lossy."""
    out = []
    for g in (reconciled_gaps or []):
        text = str(g.get("text") or "").strip()
        if not text:
            continue
        status = str(g.get("evidentiary_status") or "")
        kind = _STATUS_TO_KIND.get(status, "gap")
        prov = g.get("provenance") or ""
        seed = (f"[{status}] {prov}").strip()
        out.append({"kind": kind, "text": text, "seed_evidence": seed})
    return out


_TITLE_RE = re.compile(r"[A-Z][a-z]+(?:[ -][A-Z][a-z]+)*")
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_CAP_STOP = {"the", "we", "this", "these", "those", "in", "on", "for", "a", "an", "our", "it", "as", "to",
             "by", "at", "from", "and", "but", "or", "however", "moreover", "thus", "here", "there", "they",
             "their", "its", "is", "are", "was", "were", "be", "can", "may", "also", "using", "use", "used",
             "based", "via", "with", "first", "second", "finally", "results", "method", "paper"}


def extract_concepts(text, *, max_terms: int = 12) -> list:
    """Heuristic concept terms: Title-Case phrases + ALL-CAPS acronyms, in first-seen order. Dedupe
    case-insensitively (keep first surface form), drop <2 chars + capitalized stopwords, cap at max_terms. Pure,
    deterministic. CRUDE (catches method/model/proper-noun names; misses lowercase concepts)."""
    s = str(text or "")
    found = [(m.start(), m.group()) for m in _TITLE_RE.finditer(s)]
    found += [(m.start(), m.group()) for m in _ACRONYM_RE.finditer(s)]
    found.sort(key=lambda x: x[0])
    out, seen = [], set()
    for _pos, term in found:
        t = re.sub(r"\s+", " ", term).strip()
        words = t.split()
        while words and words[0].lower() in _CAP_STOP:   # drop leading caps stopwords (e.g. sentence-initial "The Transformer" -> "Transformer")
            words.pop(0)
        t = " ".join(words)
        key = t.lower()
        if len(t) < 2 or key in _CAP_STOP or key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= int(max_terms):
            break
    return out


def concept_degrees(edges) -> dict:
    """Co-occurrence DEGREE (number of distinct partner concepts) per concept, over undirected edges. Pure."""
    adj = {}
    for e in (edges or []):
        if not (isinstance(e, (list, tuple)) and len(e) >= 2):
            continue
        a, b = str(e[0]).strip(), str(e[1]).strip()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return {k: len(v) for k, v in adj.items()}


def hub_bridge_threshold(edges, *, percentile: float = 0.90):
    """The degree value at the nearest-rank `percentile` of the concept-degree distribution, CAPPED strictly below the
    maximum degree so the highest-degree node (the corpus-topic HUB) is ALWAYS excludable: a bridge with degree
    GREATER than this is treated as a HUB by abc_whitespace(max_bridge_degree=...). The `min(n-2, ...)` cap is the fix
    for small concept sets — without it, the percentile index lands ON the max degree (e.g. ceil(0.9*n)-1 == n-1 for
    n<10) and strict `>` would never exclude the hub. None for < 2 concepts. Edge case: if the TOP TWO degrees TIE
    (co-dominant hubs) both equal the threshold and are kept; the dominant single-topic hub (the common case) is
    always excluded. Pure."""
    degs = sorted(concept_degrees(edges).values())
    n = len(degs)
    if n < 2:
        return None
    p = max(0.0, min(1.0, float(percentile)))
    idx = max(0, min(n - 2, math.ceil(p * n) - 1))   # n-2 (not n-1) so the threshold is strictly below the max degree
    return degs[idx]


def pmi_context_relatedness(concept_lists, *, eps: float = 1e-9):
    """A PURE PPMI-context distributional relatedness fn (FREE; no embedder). From per-doc concept lists: df[X]=#docs
    with X, df[X,Y]=#docs with both, N=#docs; PPMI(X,Y)=max(0, ln(df[X,Y]*N / (df[X]*df[Y]))). context[X]={Y:PPMI}.
    relatedness(a,c)=cosine(context[a],context[c]); the dot is over SHARED partners, the norms over the FULL context
    vectors (standard cosine). 0.0 if either context empty / no overlap. SECOND-ORDER (Church & Hanks 1990): A,C
    related iff similar co-occurrence contexts -> real gaps (share many non-hub intermediates) score high; hub-only
    spurious pairs score LOWER (diluted by their non-shared context), not necessarily ~0. N=1 (single doc) -> all
    PPMI=0 -> relatedness 0.0 (PMI is undefined at N=1). Pure, deterministic."""
    docs = [sorted(set(str(t).strip() for t in (cl or []) if str(t).strip())) for cl in (concept_lists or [])]
    docs = [d for d in docs if d]
    N = len(docs)
    df, pair = {}, {}
    for d in docs:
        for x in d:
            df[x] = df.get(x, 0) + 1
        for i, x in enumerate(d):
            for y in d[i + 1:]:
                k = (x, y) if x < y else (y, x)
                pair[k] = pair.get(k, 0) + 1
    context = {}
    for (x, y), c_xy in pair.items():
        ppmi = math.log((c_xy * N) / (df[x] * df[y])) if N > 0 else 0.0
        if ppmi > 0:
            context.setdefault(x, {})[y] = ppmi
            context.setdefault(y, {})[x] = ppmi

    def relatedness(a, c) -> float:
        va, vc = context.get(str(a).strip(), {}), context.get(str(c).strip(), {})
        if not va or not vc:
            return 0.0
        shared = set(va) & set(vc)
        if not shared:
            return 0.0
        dot = sum(va[k] * vc[k] for k in shared)
        na = sum(v * v for v in va.values()) ** 0.5
        nc = sum(v * v for v in vc.values()) ** 0.5
        if na < eps or nc < eps:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nc)))

    return relatedness


def cooccurrence_edges_from_concepts(concept_lists, *, max_edges: int = 2000) -> list:
    """Unordered unique concept pairs (a,c) a<c co-occurring within a doc's concept list, deduped across docs,
    capped at max_edges. concept_lists = list of per-doc concept-term lists (the edge builder shared by the stdlib
    and LLM extractors). Pure."""
    seen, out = set(), []
    for concepts in (concept_lists or []):
        uniq = sorted(set(str(t).strip() for t in (concepts or []) if str(t).strip()))
        for i, a in enumerate(uniq):
            for c in uniq[i + 1:]:
                if (a, c) in seen:
                    continue
                seen.add((a, c))
                out.append((a, c))
                if len(out) >= int(max_edges):
                    return out
    return out


def cooccurrence_edges(docs, *, max_terms_per_doc: int = 12, max_edges: int = 2000) -> list:
    """Unordered unique concept pairs co-occurring within a doc (via the stdlib extract_concepts), deduped + capped.
    Pure. Delegates to cooccurrence_edges_from_concepts so the LLM extractor reuses the same edge builder."""
    return cooccurrence_edges_from_concepts(
        [extract_concepts(d, max_terms=max_terms_per_doc) for d in (docs or [])], max_edges=max_edges)


_POS_RE = re.compile(r"\b(improves?|increases?|outperforms?|boosts?|raises?|enhances?)\b", re.I)
_NEG_RE = re.compile(r"\b(reduces?|decreases?|degrades?|fails?|underperforms?|lowers?|worsens?)\b", re.I)


def extract_claims(text) -> list:
    """Crude claim records for find_contradictions: per sentence with a polarity verb, emit
    {subject: first concept term (lowercased), polarity: '+'/'-'}. Skip sentences with no verb or no concept.
    Pure, deterministic. HONEST: very crude; rarely yields cross-doc contradictions (explicit contradictions are
    rare — the LLM seam is the real version)."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", str(text or "")):
        pol = "+" if _POS_RE.search(s) else ("-" if _NEG_RE.search(s) else None)
        if pol is None:
            continue
        terms = extract_concepts(s, max_terms=1)
        if not terms:
            continue
        out.append({"subject": terms[0].lower(), "polarity": pol})
    return out


def cooccurrence_provenance(concept_lists, doc_ids) -> dict:
    """Sidecar: frozenset({a,b}) -> set(doc_id) for concept pairs co-occurring within a doc. UNCAPPED (the provenance
    set size is the true co-occurrence count PPMI wants). Pure; a<b handled by frozenset. doc_ids[i] labels
    concept_lists[i]; extra/missing ids are ignored beyond the shorter length."""
    prov = {}
    ids = list(doc_ids or [])
    for i, concepts in enumerate(concept_lists or []):
        if i >= len(ids):
            break
        did = ids[i]
        uniq = sorted(set(str(t).strip() for t in (concepts or []) if str(t).strip()))
        for j, a in enumerate(uniq):
            for c in uniq[j + 1:]:
                prov.setdefault(frozenset({a, c}), set()).add(did)
    return prov


def bridge_overlap_relatedness(provenance, *, hub_bridges=frozenset()):
    """Cross-lit relatedness from the Swanson bridge-overlap signal (NOT intra-corpus PPMI). Builds a concept->
    {bridge: weight} map from provenance-set sizes, then relatedness(a,c) = 1 - 1/(1+w) where w sums the provenance
    weight of shared NON-HUB bridges. Pure; monotone in shared-bridge evidence; 0.0 when none."""
    adj = {}   # node -> {neighbor: weight}
    for pair, docs in (provenance or {}).items():
        it = list(pair)
        if len(it) != 2:
            continue
        x, y = it[0], it[1]
        w = len(docs or ())
        adj.setdefault(x, {})[y] = adj.setdefault(x, {}).get(y, 0) + w
        adj.setdefault(y, {})[x] = adj.setdefault(y, {}).get(x, 0) + w
    hubs = set(hub_bridges or ())

    def relatedness(a, c) -> float:
        na, nc = adj.get(str(a).strip(), {}), adj.get(str(c).strip(), {})
        shared = (set(na) & set(nc)) - hubs
        w = sum(na[b] + nc[b] for b in shared)
        return 0.0 if w <= 0 else (1.0 - 1.0 / (1.0 + w))

    return relatedness


def topic_aware_hub_bridges(edges, doc_of_concept_topic, *, percentile: float = 0.90) -> frozenset:
    """Provenance-aware hub exclusion: rank concepts by MAX intra-topic degree (largest degree within any single
    fetch-topic), and mark as hubs those strictly above the nearest-rank percentile (capped below the max so the
    dominant single-topic hub is always excludable). A cross-topic-SPANNING bridge has low intra-topic degree even
    if its total degree is high, so it is KEPT. `edges` is accepted for signature symmetry but unused (topic
    structure is the signal). Pure."""
    maxdeg = {c: max(t.values()) if t else 0 for c, t in (doc_of_concept_topic or {}).items()}
    degs = sorted(maxdeg.values())
    n = len(degs)
    if n < 2:
        return frozenset()
    p = max(0.0, min(1.0, float(percentile)))
    idx = max(0, min(n - 2, math.ceil(p * n) - 1))
    thr = degs[idx]
    return frozenset(c for c, d in maxdeg.items() if d > thr)


def cross_paper_bridge_strength(gap, provenance, *, hub_bridges=frozenset()) -> int:
    """FROZEN priority kernel: count-weighted CROSS-PAPER shared-bridge evidence for a gap {a,c,bridges}. A bridge B
    contributes |prov[{a,B}] ∪ prov[{B,c}]| only when it is cross-paper (some a-B doc != some B-c doc) and non-hub.
    Corpus-intrinsic, no post-discovery signal. Pure."""
    a, c = str((gap or {}).get("a") or "").strip(), str((gap or {}).get("c") or "").strip()
    hubs = set(hub_bridges or ())
    total = 0
    for b in (gap or {}).get("bridges") or []:
        b = str(b).strip()
        if not b or b in hubs:
            continue
        ab = (provenance or {}).get(frozenset({a, b})) or set()
        bc = (provenance or {}).get(frozenset({b, c})) or set()
        if ab and bc and (ab - bc or bc - ab or len(ab | bc) > 1):   # cross-paper only
            total += len(ab | bc)
    return total


MESH_CHECK_TAGS = frozenset({
    "humans", "animals", "male", "female", "adult", "aged", "middle aged", "adolescent", "child",
    "child, preschool", "infant", "infant, newborn", "young adult", "aged, 80 and over", "age factors",
    "sex factors", "pregnancy", "rats", "mice", "rabbits", "dogs", "cattle", "swine", "guinea pigs",
    "rats, inbred strains", "rats, sprague-dawley", "rats, wistar", "mice, inbred c57bl", "mice, inbred strains",
    "time factors", "reproducibility of results", "sensitivity and specificity", "retrospective studies",
    "prospective studies", "follow-up studies", "random allocation", "double-blind method", "support, non-u.s. gov't",
    "support, u.s. gov't, p.h.s.", "comparative study", "in vitro techniques", "administration, oral",
    "injections, intravenous", "dose-response relationship, drug", "analysis of variance",
})


def cross_paper_gaps_ranked(edges, provenance, *, hub_bridges=frozenset(), min_strength: int = 1,
                            max_gaps: int = 100000, strength_fn=None) -> list:
    """GLOBAL answer-blind ABC ranking. Bridge-centric enumeration (tractable: hubs excluded bound per-bridge degree):
    for each non-hub bridge B, every pair (A,C) of B's neighbours with NO direct A-C edge is a candidate gap bridged
    by B; accumulate bridges per pair, then score each by cross_paper_bridge_strength (cross-paper non-hub evidence
    only) and keep strength>=min_strength, sorted by strength desc then (a,c) lexicographic (deterministic total
    order, including on genuinely symmetric graphs, e.g. a 4-cycle where {A,C} and the two bridges {B1,B2} mutually
    bridge one another with identical strength). Pure/deterministic; does NOT reference any target or sub-corpus
    tag. `strength_fn(gap, provenance, hub_bridges) -> number` overrides the scoring function; None (default)
    uses cross_paper_bridge_strength, byte-identical to the prior behavior."""
    score = strength_fn or (lambda g, p, h: cross_paper_bridge_strength(g, p, hub_bridges=h))
    adj = {}
    for e in (edges or []):
        if not (isinstance(e, (list, tuple)) and len(e) >= 2):
            continue
        a, b = str(e[0]).strip(), str(e[1]).strip()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    hubs = set(hub_bridges or ())
    pair_bridges = {}
    for b, nbrs in adj.items():
        if b in hubs:
            continue
        ns = sorted(nbrs)
        for i, x in enumerate(ns):
            ax = adj.get(x, set())
            for y in ns[i + 1:]:
                if y in ax:            # direct edge -> not a gap
                    continue
                pair_bridges.setdefault((x, y), set()).add(b)
    out = []
    for (x, y), bridges in pair_bridges.items():
        gap = {"a": x, "c": y, "bridges": sorted(bridges)}
        s = score(gap, provenance, hubs)
        if s >= int(min_strength):
            gap["strength"] = s
            out.append(gap)
    out.sort(key=lambda g: (-g["strength"], g["a"], g["c"]))
    return out[:int(max_gaps)]


def specificity_weighted_bridge_strength(gap, provenance, degrees, n_concepts, *, hub_bridges=frozenset()) -> float:
    """FROZEN priority (specificity variant): raw cross-paper bridge evidence with each bridge B down-weighted by an
    IDF term idf(B)=log2(1 + n_concepts/degree(B)) so GENERIC high-degree bridges (which inflate large-literature
    pairs) contribute less than SPECIFIC low-degree ones. Textbook Swanson-LBD B-term suppression. Pure."""
    a, c = str((gap or {}).get("a") or "").strip(), str((gap or {}).get("c") or "").strip()
    hubs = set(hub_bridges or ())
    total = 0.0
    for b in (gap or {}).get("bridges") or []:
        b = str(b).strip()
        if not b or b in hubs:
            continue
        ab = (provenance or {}).get(frozenset({a, b})) or set()
        bc = (provenance or {}).get(frozenset({b, c})) or set()
        if ab and bc and (ab - bc or bc - ab or len(ab | bc) > 1):    # cross-paper only
            deg = max(1, int((degrees or {}).get(b, 1)))
            total += len(ab | bc) * math.log2(1.0 + float(n_concepts) / deg)
    return total


def specificity_strength_fn(degrees, n_concepts):
    """Factory: a strength_fn (gap, provenance, hub_bridges) -> specificity_weighted_bridge_strength(...). Pure."""
    def _fn(gap, provenance, hub_bridges):
        return specificity_weighted_bridge_strength(gap, provenance, degrees, n_concepts, hub_bridges=hub_bridges)
    return _fn


def strip_check_tags(concepts) -> list:
    """Drop generic MeSH check-tags (population/method/support descriptors that are not scientific concepts) +
    purely-numeric tokens, preserving first-seen order. Pure. Input assumed lowercased."""
    out = []
    for c in (concepts or []):
        t = str(c).strip()
        if not t or t in MESH_CHECK_TAGS or t.replace(".", "").isdigit():
            continue
        out.append(t)
    return out


def pair_rank(ranked, a_terms, c_terms):
    """Best-ranked gap whose endpoints hit a_terms x c_terms (either orientation). 1-based rank. None if absent. Pure."""
    A, C = {str(t).strip().lower() for t in a_terms}, {str(t).strip().lower() for t in c_terms}
    for i, g in enumerate(ranked or []):
        a, c = str(g.get("a") or "").lower(), str(g.get("c") or "").lower()
        if (a in A and c in C) or (a in C and c in A):
            return {"rank": i + 1, "strength": g.get("strength"), "a": g.get("a"), "c": g.get("c")}
    return None


def pool_pair_strengths(ranked, topic_terms) -> dict:
    """frozenset({topic1,topic2}) -> best gap strength between their anchor terms (for null + hard-neg sets). Pure."""
    terms = {k: {str(t).strip().lower() for t in v} for k, v in (topic_terms or {}).items()}
    best = {}
    keys = list(terms)
    for i, t1 in enumerate(keys):
        for t2 in keys[i + 1:]:
            r = pair_rank(ranked, terms[t1], terms[t2])
            if r is not None:
                best[frozenset({t1, t2})] = r["strength"]
    return best


def _percentile(sample, pct):
    s = sorted(float(x) for x in (sample or []))
    if not s:
        return None
    k = max(0, min(len(s) - 1, int(math.ceil(pct / 100.0 * len(s))) - 1))
    return s[k]


def beats_percentile(value, sample, pct=95.0) -> bool:
    """value strictly exceeds the nearest-rank pct percentile of sample; empty sample -> True. Pure."""
    p = _percentile(sample, pct)
    return True if p is None else float(value) > p


def crosslit_verdict(target, hardneg_strengths, null_strengths, *, pool_size, min_pool=30, null_pct=95.0) -> dict:
    """VOID (target absent / pool<min_pool) | KILL (a hard-neg out-scores OR fails the null pct) | PASS. Pure."""
    if target is None:
        return {"verdict": "VOID", "reasons": ["target pair absent from ranking (bridge not surfaced)"]}
    if int(pool_size) < int(min_pool):
        return {"verdict": "VOID", "reasons": [f"pool {pool_size} < min_pool {min_pool} (underpowered)"]}
    s = float(target["strength"])
    hn = [float(x) for x in (hardneg_strengths or [])]
    reasons, ok = [], True
    if hn and not all(s > x for x in hn):
        ok = False
        reasons.append(f"target strength {s:.3f} does not out-rank all {len(hn)} hard-negatives (max {max(hn):.3f})")
    if not beats_percentile(s, null_strengths, null_pct):
        ok = False
        reasons.append(f"target strength {s:.3f} does not beat the {null_pct:.0f}th-pct empirical null")
    return {"verdict": "PASS" if ok else "KILL", "reasons": reasons or ["out-ranks all hard-negatives + beats the null"],
            "target_strength": s, "target_rank": target.get("rank"),
            "null_pct_value": _percentile(null_strengths, null_pct), "n_hardneg": len(hn)}


def _log_binom(n, k):
    if k < 0 or k > n or n < 0:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hypergeom_sf(k, N, K, n) -> float:
    """P(X >= k) for X ~ Hypergeometric(population N, successes K, draws n). Pure (math.lgamma); log-sum-exp
    for numerical stability. Returns a probability in [0,1]. Out-of-range args -> 1.0 (non-significant)."""
    N, K, n, k = int(N), int(K), int(n), int(k)
    if K < 0 or n < 0 or K > N or n > N or N <= 0:
        return 1.0
    lo = max(int(k), 0, n - (N - K))
    hi = min(K, n)
    if lo > hi:
        return 0.0 if k > hi else 1.0
    logden = _log_binom(N, n)
    terms = [_log_binom(K, i) + _log_binom(N - K, n - i) - logden for i in range(lo, hi + 1)]
    mx = max(terms)
    s = mx + math.log(sum(math.exp(t - mx) for t in terms))
    return max(0.0, min(1.0, math.exp(s)))


def pair_bridge_count(gap, provenance, *, hub_bridges=frozenset()) -> int:
    """c_AC: number of the gap's shared bridges B that are NON-HUB and CROSS-paper (some a-B doc != some B-c doc)."""
    a, c = str((gap or {}).get("a") or "").strip(), str((gap or {}).get("c") or "").strip()
    hubs = set(hub_bridges or ())
    n = 0
    for b in (gap or {}).get("bridges") or []:
        b = str(b).strip()
        if not b or b in hubs:
            continue
        ab = (provenance or {}).get(frozenset({a, b})) or set()
        bc = (provenance or {}).get(frozenset({b, c})) or set()
        if ab and bc and (ab - bc or bc - ab or len(ab | bc) > 1):
            n += 1
    return n


def association_strength_fn(degrees):
    """strength_fn: AS(A,C) = c_AC / (deg(A)*deg(C)) — the observed/expected co-sharing normalizer (van Eck-Waltman
    2009). Divides out endpoint (literature-size) degree, the confound IDF never touched. degrees = {concept: non-hub
    degree}. 0 if either degree is 0."""
    def _fn(gap, provenance, hub_bridges):
        a, c = str((gap or {}).get("a") or "").strip(), str((gap or {}).get("c") or "").strip()
        da, dc = float((degrees or {}).get(a, 0)), float((degrees or {}).get(c, 0))
        if da <= 0 or dc <= 0:
            return 0.0
        return pair_bridge_count(gap, provenance, hub_bridges=hub_bridges) / (da * dc)
    return _fn


def salton_cosine_fn(degrees):
    """strength_fn: cosine = c_AC / sqrt(deg(A)*deg(C)) — the sqrt denominator resists AS's tiny-literature over-reward."""
    def _fn(gap, provenance, hub_bridges):
        a, c = str((gap or {}).get("a") or "").strip(), str((gap or {}).get("c") or "").strip()
        da, dc = float((degrees or {}).get(a, 0)), float((degrees or {}).get(c, 0))
        if da <= 0 or dc <= 0:
            return 0.0
        return pair_bridge_count(gap, provenance, hub_bridges=hub_bridges) / math.sqrt(da * dc)
    return _fn


def hub_share_fraction(gap, provenance, degrees, *, hub_bridges=frozenset(), hub_degree_quantile_value) -> float:
    """Diagnostic: fraction of the gap's non-hub cross-paper bridges whose degree >= hub_degree_quantile_value.
    High => a PARTIAL discrimination result is STRUCTURAL (bridge-degree-variance) not semantic. 0.0 if no bridges."""
    a, c = str((gap or {}).get("a") or "").strip(), str((gap or {}).get("c") or "").strip()
    hubs = set(hub_bridges or ())
    kept, high = 0, 0
    for b in (gap or {}).get("bridges") or []:
        b = str(b).strip()
        if not b or b in hubs:
            continue
        ab = (provenance or {}).get(frozenset({a, b})) or set()
        bc = (provenance or {}).get(frozenset({b, c})) or set()
        if ab and bc and (ab - bc or bc - ab or len(ab | bc) > 1):
            kept += 1
            if float((degrees or {}).get(b, 0)) >= float(hub_degree_quantile_value):
                high += 1
    return (high / kept) if kept else 0.0
