# scripts/n1_index.py
"""labcoat N1 ANN index shell — a faiss IndexFlatIP (exact cosine on L2-normalized vectors) implementing the SAME
.knn(query_vec, *, k, date_cutoff) contract as the pure InMemoryN1Index, so external_novelty(_capped) works over
the live literature index. Cosine distance = clamp01(1 - inner_product) — the SAME clamp as n1_novelty.cosine_distance,
so the faiss path agrees with the pure InMemoryN1Index oracle. Optional deps (faiss-cpu>=1.12 + numpy); the zero-dep
core never imports them. HNSW is the documented one-line scale-out swap; flat-exact for the slice.
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import n1_novelty

_INSTALL_HINT = "live N1 index requires: pip install -r requirements-n1.txt (faiss-cpu>=1.12, numpy)"


def n1_index_available() -> bool:
    try:
        import faiss  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


class FaissN1Index:
    """faiss IndexFlatIP over L2-normalized vectors. .knn / .cite_nearest match InMemoryN1Index semantics; cosine
    distance = clamp01(1 - IP). Retains per-entry metadata for date-filtering + reconstruct for neighbor-of-neighbor."""

    def __init__(self, vecs, ids, dates, titles, *, fingerprint, faiss, np):
        self._faiss = faiss
        self._np = np
        self._ids = list(ids)
        self._dates = list(dates)
        self._titles = list(titles)
        self._fp = dict(fingerprint)
        self._loaded_threshold = None
        x = np.ascontiguousarray(np.asarray(vecs, dtype="float32"))
        faiss.normalize_L2(x)
        self._x = x
        self._index = faiss.IndexFlatIP(int(x.shape[1]))
        self._index.add(x)
        if x.shape[0] > 0:  # reconstruct round-trip assert (Flat is lossless; vectors already normalized)
            assert np.allclose(self._index.reconstruct(0), x[0], atol=1e-5), "faiss reconstruct round-trip failed"

    def _eligible(self, date_cutoff) -> set:
        return {i for i, dt in enumerate(self._dates) if str(dt or "") < str(date_cutoff)}

    def _normq(self, vec):
        q = self._np.ascontiguousarray(self._np.asarray([vec], dtype="float32"))
        self._faiss.normalize_L2(q)
        return q

    def knn(self, query_vec, *, k, date_cutoff):
        """Return (cand_knn_distances, neighbor_knn_distances_list) over date-eligible entries — same contract as
        InMemoryN1Index.knn. date_cutoff REQUIRED (keyword-only)."""
        elig = self._eligible(date_cutoff)
        if not elig or self._index.ntotal == 0:
            return [], []
        q = self._normq(query_vec)
        D, I = self._index.search(q, self._index.ntotal)
        ip_by_idx = {int(idx): float(d) for idx, d in zip(I[0], D[0]) if int(idx) >= 0}
        order = [int(idx) for idx in I[0] if int(idx) in elig]
        nearest = order[:int(k)]
        cand_dists = [_clamp01(1.0 - ip_by_idx[i]) for i in nearest]
        neighbor_dists_list = []
        for ni in nearest:
            v = self._np.ascontiguousarray(self._index.reconstruct(int(ni)).reshape(1, -1))
            Dn, In = self._index.search(v, self._index.ntotal)
            nd = [_clamp01(1.0 - float(d)) for idx, d in zip(In[0], Dn[0])
                  if int(idx) in elig and int(idx) != ni][:int(k)]
            neighbor_dists_list.append(nd)
        return cand_dists, neighbor_dists_list

    def nearest_k(self, query_vec, *, k, date_cutoff):
        """Top-k date-eligible neighbors with ids/titles/distances (cosine distance = clamp01(1-IP)), nearest first.
        For the Stage-B kNN prior-art leg. Returns [] for an empty/ineligible index. date_cutoff REQUIRED."""
        elig = self._eligible(date_cutoff)
        if not elig or self._index.ntotal == 0:
            return []
        q = self._normq(query_vec)
        D, I = self._index.search(q, self._index.ntotal)
        out = []
        for idx, ip in zip(I[0], D[0]):
            i = int(idx)
            if i < 0 or i not in elig:
                continue
            out.append({"id": self._ids[i], "title": self._titles[i], "distance": _clamp01(1.0 - float(ip))})
            if len(out) >= int(k):
                break
        return out

    def cite_nearest(self, query_vec, *, date_cutoff):
        elig = self._eligible(date_cutoff)
        if not elig or self._index.ntotal == 0:
            return None
        q = self._normq(query_vec)
        D, I = self._index.search(q, self._index.ntotal)
        for idx, d in zip(I[0], D[0]):
            if int(idx) in elig:
                return {"id": self._ids[int(idx)], "title": self._titles[int(idx)],
                        "distance": _clamp01(1.0 - float(d))}
        return None

    def off_distribution_threshold(self, *, percentile: float = 0.95):
        """Corpus LOO-NN-distance percentile threshold (the OOD cap input). Self-search per corpus vector, then the
        pure nearest-rank percentile. Returns None for <2 vectors."""
        if self._index.ntotal < 2:
            return None
        D, I = self._index.search(self._x, 2)
        # Exclude the self-hit by INDEX (don't assume column 0 is self — duplicates could reorder ties): for each
        # row take the first neighbor whose corpus index != the row's own index. LOO NN distance = clamp01(1 - IP).
        loo = []
        for r in range(D.shape[0]):
            j = next((c for c in range(D.shape[1]) if int(I[r][c]) != r), None)
            if j is not None:
                loo.append(_clamp01(1.0 - float(D[r][j])))
        return n1_novelty.corpus_nn_percentile_threshold(loo, percentile=percentile)

    def query_calibrated_threshold(self, query_vecs, query_ids, *, percentile: float = 0.95):
        """Query-regime off-distribution threshold (SHELL): for each query vec, the cosine distance (clamp01(1-IP))
        to the nearest corpus doc whose id != the paired query id (exclude-self by id); then the pure nearest-rank
        percentile. Oracle-equals the pure InMemoryN1Index.query_calibrated_threshold on the same vectors/ids. No
        date filter (regime, not temporal). Returns None for an empty index / no eligible distances."""
        if self._index.ntotal == 0:
            return None
        ds = []
        for vec, qid in zip(query_vecs, query_ids):
            q = self._normq(vec)
            D, I = self._index.search(q, self._index.ntotal)
            for idx, ip in zip(I[0], D[0]):
                if int(idx) < 0 or self._ids[int(idx)] == qid:
                    continue
                ds.append(_clamp01(1.0 - float(ip)))
                break
        return n1_novelty.corpus_nn_percentile_threshold(ds, percentile=percentile)


def build_index(entries, *, embedder_fingerprint):
    """Build a FaissN1Index from [{id,vec,date,title}]. Raises RuntimeError (install hint) if deps absent."""
    if not n1_index_available():
        raise RuntimeError(_INSTALL_HINT)
    import faiss
    import numpy as np
    vecs = [e["vec"] for e in entries]
    ids = [e.get("id") for e in entries]
    dates = [e.get("date") for e in entries]
    titles = [e.get("title") for e in entries]
    return FaissN1Index(vecs, ids, dates, titles, fingerprint=embedder_fingerprint, faiss=faiss, np=np)


def save_snapshot(index, path, *, percentile: float = 0.95, gate_threshold=None):
    """Persist vectors (.npy) + metadata/fingerprint/thresholds (meta.json) to a snapshot dir.
    off_distribution_threshold = the GATE threshold = `gate_threshold` (the query-calibrated value supplied by the
    build) when provided, else the corpus-LOO fallback. corpus_loo_threshold = the diagnostic paper->paper LOO
    percentile (ALWAYS stored). The gate consumer (load_snapshot -> _loaded_threshold) is unchanged.
    Returns corpus_loo so callers avoid a second self-search pass."""
    if not n1_index_available():
        raise RuntimeError(_INSTALL_HINT)
    import numpy as np
    p = pathlib.Path(path)
    p.mkdir(parents=True, exist_ok=True)
    np.save(p / "vecs.npy", index._x)
    corpus_loo = index.off_distribution_threshold(percentile=percentile)
    gate = gate_threshold if gate_threshold is not None else corpus_loo
    meta = {"ids": index._ids, "dates": index._dates, "titles": index._titles,
            "fingerprint": index._fp,
            "off_distribution_threshold": gate,
            "corpus_loo_threshold": corpus_loo}
    (p / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return corpus_loo


_PROTECTED_SNAPSHOT_KEYS = ("off_distribution_threshold", "corpus_loo_threshold")


def annotate_snapshot_diagnostics(path, **kv):
    """Merge diagnostic keys (e.g. roc_auroc_heldout_field, roc_fpr_at_tpr95, roc_auc_ci, youden_threshold,
    calibration_split_threshold) into an existing snapshot meta.json. ADDITIVE — the build-derived gate
    (off_distribution_threshold) and the corpus_loo_threshold diagnostic are PROTECTED: any attempt to pass them
    in kv is DROPPED (the gate is set ONLY by the build path, never by a post-hoc diagnostic annotation). Returns
    the merged meta. Pure file I/O."""
    kv = {k: v for k, v in kv.items() if k not in _PROTECTED_SNAPSHOT_KEYS}
    p = pathlib.Path(path)
    meta = json.loads((p / "meta.json").read_text(encoding="utf-8"))
    meta.update(kv)
    (p / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def load_snapshot(path, *, active_fingerprint):
    """Load a snapshot, FAIL-CLOSED on a pinned-embedder fingerprint mismatch (a drifted embedder corrupts
    distances). Returns a FaissN1Index with ._loaded_threshold set."""
    if not n1_index_available():
        raise RuntimeError(_INSTALL_HINT)
    import faiss
    import numpy as np
    p = pathlib.Path(path)
    meta = json.loads((p / "meta.json").read_text(encoding="utf-8"))
    if not n1_novelty.fingerprint_match(meta.get("fingerprint", {}), active_fingerprint):
        raise RuntimeError("pinned-embedder fingerprint mismatch — snapshot built with a different embedder; "
                           "refusing to load (re-embed the corpus with the active embedder)")
    vecs = np.load(p / "vecs.npy")
    idx = FaissN1Index(vecs, meta["ids"], meta["dates"], meta["titles"],
                       fingerprint=meta["fingerprint"], faiss=faiss, np=np)
    idx._loaded_threshold = meta.get("off_distribution_threshold")
    return idx
