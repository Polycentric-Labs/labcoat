# scripts/n1_novelty.py
"""labcoat N1 — literature-grounded novelty. A PURE, deterministic RND-STYLE relative-neighbor-density scorer:
novelty = the candidate's local density RELATIVE to its neighbors' local densities (the relative-density principle
from arXiv:2503.01508 'Enabling AI Scientists to Recognize Innovation / Relative Neighbor Density', Wang et al.
2025). This is a CLEAN stdlib formulation of the principle, NOT a verbatim reimplementation of the paper's exact
estimator. Relative-not-absolute density is the Goodhart-resistance property: a lone point in a sparse region whose
NEIGHBORS are also sparse scores LOW (not falsely 'maximally novel'), defeating distance-inflation.

The math operates on injected distances/densities (no embedder/index/network/clock here). The corpus index is
INJECTED via the adapter seam (InMemoryN1Index is a reference; the real citation-aware embedder + ANN corpus are a
deferred adapter). N1 is ADVISORY. License: MIT. Author: Allen Byrd.

HONEST LIMITS (do not overclaim): Goodhart-RESISTANT, not Goodhart-IMMUNE. No published adversarial novelty-
gaming benchmark exists; this test suite ships a small distance-inflation red-team as a START, not a proof.
NOT YET WIRED into the live loop/value-axis — N1 is a ready-to-plug ADVISORY scorer; the real citation-aware
embedder (SPECTER2/SciNCL) + ANN corpus + date-rolling index are a deferred adapter. Every real N1 verdict must
surface its corpus + date cutoff ("novel relative to THIS corpus as of THIS date"). The sparse-region defense
requires corpus COVERAGE in that region; a point entirely OUTSIDE the corpus always finds denser nearby neighbors
and scores high regardless — that is why the design pairs N1 with an explicit high-tail cap (off-distribution
points flagged as likely garbage, not super-novel)."""
from __future__ import annotations
import math


def local_density(neighbor_distances, *, eps: float = 1e-9) -> float:
    """A kNN local-density estimate: the inverse of the mean distance to the (already-selected) neighbors. Closer
    neighbors -> higher density. Empty -> 0.0 (maximally sparse / novel). eps guards a zero mean."""
    ds = [float(d) for d in (neighbor_distances or [])]
    if not ds:
        return 0.0
    return 1.0 / ((sum(ds) / len(ds)) + float(eps))


def relative_neighbor_density(candidate_density: float, neighbor_densities) -> float:
    """The RND-style relative score in [0,1]: the FRACTION of the candidate's neighbors that are DENSER than the
    candidate itself. High (->1) = the candidate sits in a sparser region than its neighbors = novel. Empty
    neighbors -> 1.0 (nothing nearby = fully novel). This relative form is the Goodhart-resistant core.
    Ties use strict `>` (a neighbor exactly as dense as the candidate does NOT count as denser)."""
    nd = [float(d) for d in (neighbor_densities or [])]
    if not nd:
        return 1.0
    return sum(1 for d in nd if d > float(candidate_density)) / len(nd)


def rnd_novelty(candidate_knn_distances, neighbor_knn_distances_list, *, eps: float = 1e-9) -> float:
    """Compose the RND-style novelty in [0,1] from raw distance data: the candidate's local density vs the local
    densities of each of its neighbors. candidate_knn_distances = distances from the candidate to its k neighbors;
    neighbor_knn_distances_list = for each of those neighbors, ITS distances to its own k neighbors. Pure.
    Neighbors with empty own-distance lists (e.g. a single-entry corpus yields no own-kNN data) are SKIPPED —
    they provide no comparison signal; skipping them lets the empty-neighbor case fall through to
    relative_neighbor_density([]) -> 1.0 (insufficient data = treat as novel), not the false 0.0 inversion."""
    cand_density = local_density(candidate_knn_distances, eps=eps)
    # a neighbor with no own-kNN data (e.g. a single-entry corpus) gives no comparison -> skip it
    neigh_densities = [local_density(nd, eps=eps) for nd in (neighbor_knn_distances_list or []) if nd]
    return relative_neighbor_density(cand_density, neigh_densities)


class InMemoryN1Index:
    """A REFERENCE injected index over [{id, vec, date}] — proves the N1 adapter seam without standing up a live
    ANN/embedder (the real citation-aware embedder + FAISS/arXiv corpus are a deferred adapter). distance_fn(vec_a,
    vec_b) -> float is injected. Deterministic; pure given its inputs (no clock — date_cutoff is passed IN)."""

    def __init__(self, entries, *, distance_fn):
        self._entries = [e for e in (entries or []) if e.get("vec") is not None]
        self._distance_fn = distance_fn

    def _eligible(self, date_cutoff):
        """Entries strictly BEFORE the cutoff (neighbors must predate the candidate — temporal-leakage fix)."""
        return [e for e in self._entries if str(e.get("date") or "") < str(date_cutoff)]

    def _knn_distances(self, query_vec, pool, *, k, exclude_id=None):
        ds = [self._distance_fn(query_vec, e["vec"]) for e in pool if e.get("id") != exclude_id]
        ds.sort()
        return ds[:int(k)]

    def knn(self, query_vec, *, k, date_cutoff):
        """Return (candidate_knn_distances, neighbor_knn_distances_list) over date-eligible entries. For each of
        the candidate's k nearest eligible neighbors, also return THAT neighbor's k nearest-neighbor distances
        (within the eligible pool) — the raw data rnd_novelty needs. date_cutoff is REQUIRED (keyword-only)."""
        pool = self._eligible(date_cutoff)
        if not pool:
            return [], []
        scored = sorted(pool, key=lambda e: self._distance_fn(query_vec, e["vec"]))
        nearest = scored[:int(k)]
        cand_dists = [self._distance_fn(query_vec, e["vec"]) for e in nearest]
        neighbor_dists_list = [self._knn_distances(e["vec"], pool, k=k, exclude_id=e.get("id")) for e in nearest]
        return cand_dists, neighbor_dists_list

    def cite_nearest(self, query_vec, *, date_cutoff):
        """The nearest date-eligible prior work: {id, title, distance} or None. Pure (date_cutoff passed in)."""
        pool = self._eligible(date_cutoff)
        if not pool:
            return None
        best = min(pool, key=lambda e: self._distance_fn(query_vec, e["vec"]))
        return {"id": best.get("id"), "title": best.get("title"),
                "distance": float(self._distance_fn(query_vec, best["vec"]))}

    def query_calibrated_threshold(self, query_entries, *, percentile: float = 0.95):
        """Query-regime off-distribution threshold: the `percentile` of {query -> nearest different-id corpus doc}
        distances over this index's entries, via the injected distance_fn. Returns None when no eligible distances
        (the gate then never flags — advisory). Pure. NO date filter (calibration is embedding-regime, not temporal)."""
        ds = query_regime_nn_distances(query_entries, self._entries, distance_fn=self._distance_fn)
        return corpus_nn_percentile_threshold(ds, percentile=percentile)


def cosine_distance(vec_a, vec_b, *, eps: float = 1e-9) -> float:
    """Cosine distance in [0,1] = 1 - cosine_similarity, CLAMPED to [0,1]. Pure list math (no numpy in the core).
    The clamp matches FaissN1Index's `1 - inner_product` clamp so the faiss path agrees with this exact oracle.
    Empty / length-mismatched / zero-norm inputs -> 1.0 (maximally far; nothing to compare)."""
    a = [float(x) for x in (vec_a or [])]
    b = [float(x) for x in (vec_b or [])]
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na < eps or nb < eps:
        return 1.0
    cos = max(-1.0, min(1.0, dot / (na * nb)))
    return max(0.0, min(1.0, 1.0 - cos))


def corpus_loo_nn_distances(vectors, *, distance_fn) -> list:
    """Leave-one-out nearest-neighbor distance for each vector: the min distance to any OTHER vector. O(N^2), pure.
    Used to derive the off-distribution threshold and to validate the faiss path. < 2 vectors -> [] (no neighbor)."""
    vs = list(vectors or [])
    n = len(vs)
    if n < 2:
        return []
    out = []
    for i in range(n):
        best = None
        for j in range(n):
            if i == j:
                continue
            d = distance_fn(vs[i], vs[j])
            if best is None or d < best:
                best = d
        out.append(float(best))
    return out


def query_regime_nn_distances(query_entries, corpus_entries, *, distance_fn) -> list:
    """The QUERY-regime analogue of corpus_loo_nn_distances: for each query entry {id, vec}, the min distance to a
    corpus entry with a DIFFERENT id (exclude-self by id). This measures how far a QUERY (e.g. a corpus title
    re-embedded with the query adapter) lands from the nearest OTHER corpus document — the distribution the
    off-distribution gate is actually applied to. Pure, O(Q*N). A query with no eligible different-id corpus entry
    is SKIPPED (contributes no distance); entries missing 'vec' are skipped. distance_fn(vec_a, vec_b) -> float."""
    corpus = [c for c in (corpus_entries or []) if c.get("vec") is not None]
    out = []
    for q in (query_entries or []):
        if q.get("vec") is None:
            continue
        qid = q.get("id")
        best = None
        for c in corpus:
            if c.get("id") == qid:
                continue
            d = distance_fn(q["vec"], c["vec"])
            if best is None or d < best:
                best = d
        if best is not None:
            out.append(float(best))
    return out


def corpus_nn_percentile_threshold(loo_nn_distances, *, percentile: float = 0.95):
    """Nearest-rank percentile of the corpus leave-one-out NN distances -> the off-distribution threshold.
    Index = ceil(percentile*N) - 1, clamped to [0, N-1] (so ~ (1-percentile) of the corpus EXCEEDS it; this is
    the correct order statistic, NOT int(p*N) which drifts with N). Empty -> None (uncalibrated). A leave-one-out,
    TPR95-STYLE approximation of the Sun et al. 2022 percentile-threshold convention (arXiv:2204.06507)."""
    d = sorted(float(x) for x in (loo_nn_distances or []))
    n = len(d)
    if n == 0:
        return None
    p = max(0.0, min(1.0, float(percentile)))
    idx = max(0, min(n - 1, math.ceil(p * n) - 1))
    return d[idx]


def high_tail_cap(cand_knn_distances, *, off_distribution_threshold) -> dict:
    """OOD guard for RND novelty: flag off_distribution when the candidate's NEAREST distance (k=1 min, the most
    conservative signal) exceeds the corpus-derived threshold. RND alone cannot self-detect out-of-corpus points
    (arXiv:2503.01508 §5.3); this pairs it with a kNN-distance OOD gate (arXiv:2204.06507). Empty distances ->
    off (no eligible neighbors). threshold None -> never flags (uncalibrated; advisory only). Always reports the
    candidate's `nearest_distance` (None when no distances) for honest transparency. Pure."""
    ds = [float(d) for d in (cand_knn_distances or [])]
    if not ds:
        return {"off_distribution": True, "reason": "no eligible neighbors", "nearest_distance": None}
    nearest = min(ds)
    if off_distribution_threshold is None:
        return {"off_distribution": False, "reason": "uncalibrated threshold; advisory only",
                "nearest_distance": nearest}
    thr = float(off_distribution_threshold)
    if nearest > thr:
        return {"off_distribution": True, "reason": f"nearest {nearest:.4f} > threshold {thr:.4f} (out of corpus)",
                "nearest_distance": nearest}
    return {"off_distribution": False, "reason": f"nearest {nearest:.4f} <= threshold {thr:.4f}",
            "nearest_distance": nearest}


_FINGERPRINT_FIELDS = ("name", "revision", "query_adapter", "doc_adapter", "dim", "normalize", "metric")


def fingerprint_match(snapshot_fp, active_fp) -> bool:
    """Strict pinned-embedder-contract equality (fail-closed). Both must be dicts carrying ALL contract fields and
    be fully equal (so a missing OR extra field, or any value drift, -> False). A drifted embedder silently
    corrupts distances, so the snapshot loader refuses on mismatch."""
    if not isinstance(snapshot_fp, dict) or not isinstance(active_fp, dict):
        return False
    if any(f not in snapshot_fp or f not in active_fp for f in _FINGERPRINT_FIELDS):
        return False
    return snapshot_fp == active_fp


def external_novelty(query_vec, index, *, k, date_cutoff, eps: float = 1e-9) -> float:
    """The end-to-end ADVISORY N1 score in [0,1]: query the injected index for the candidate's + neighbors' kNN
    distances (date-cutoff enforced), then the pure RND-style relative density. Empty/eligible-less pool -> 1.0
    (nothing to compare against = fully novel). date_cutoff is REQUIRED (keyword-only)."""
    cand_dists, neighbor_dists_list = index.knn(query_vec, k=k, date_cutoff=date_cutoff)
    if not cand_dists:
        return 1.0
    return rnd_novelty(cand_dists, neighbor_dists_list, eps=eps)


def external_novelty_capped(query_vec, index, *, k, date_cutoff, off_distribution_threshold, eps: float = 1e-9) -> dict:
    """ADVISORY end-to-end N1 with the OOD cap + cited nearest prior work. Returns
    {score, off_distribution, reason, nearest}. score = rnd_novelty over the index's kNN (empty pool -> 1.0);
    off_distribution from high_tail_cap on the candidate's kNN distances; nearest from index.cite_nearest if the
    index provides it (duck-typed across InMemoryN1Index / FaissN1Index), else None. date_cutoff REQUIRED."""
    cand_dists, neighbor_dists_list = index.knn(query_vec, k=k, date_cutoff=date_cutoff)
    score = 1.0 if not cand_dists else rnd_novelty(cand_dists, neighbor_dists_list, eps=eps)
    cap = high_tail_cap(cand_dists, off_distribution_threshold=off_distribution_threshold)
    cite = getattr(index, "cite_nearest", None)
    nearest = cite(query_vec, date_cutoff=date_cutoff) if callable(cite) else None
    return {"score": score, "off_distribution": cap["off_distribution"], "reason": cap["reason"],
            "nearest": nearest, "nearest_distance": cap["nearest_distance"]}
