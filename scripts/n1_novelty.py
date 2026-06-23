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


def external_novelty(query_vec, index, *, k, date_cutoff, eps: float = 1e-9) -> float:
    """The end-to-end ADVISORY N1 score in [0,1]: query the injected index for the candidate's + neighbors' kNN
    distances (date-cutoff enforced), then the pure RND-style relative density. Empty/eligible-less pool -> 1.0
    (nothing to compare against = fully novel). date_cutoff is REQUIRED (keyword-only)."""
    cand_dists, neighbor_dists_list = index.knn(query_vec, k=k, date_cutoff=date_cutoff)
    if not cand_dists:
        return 1.0
    return rnd_novelty(cand_dists, neighbor_dists_list, eps=eps)
