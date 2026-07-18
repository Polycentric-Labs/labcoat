import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_index

def test_index_available_is_bool():
    assert isinstance(n1_index.n1_index_available(), bool)

def test_build_index_without_faiss_raises_clear_message():
    import pytest
    if n1_index.n1_index_available():
        pytest.skip("faiss/numpy ARE installed; graceful-degrade path not exercised here")
    with pytest.raises(RuntimeError) as ei:
        n1_index.build_index([{"id": "a", "vec": [0.0, 1.0], "date": "2020-01-01", "title": "T"}],
                             embedder_fingerprint={"name": "x"})
    assert "requirements-n1.txt" in str(ei.value)

def test_save_snapshot_stores_gate_and_corpus_loo_thresholds(tmp_path):
    import pytest, json
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed")
    fp = {"name": "x", "revision": "r", "query_adapter": "q", "doc_adapter": "d",
          "dim": 2, "normalize": "l2", "metric": "cosine"}
    raw = [[1.0, 0.0], [0.92, 0.39], [0.0, 1.0], [0.7, 0.7]]
    idx = n1_index.FaissN1Index(raw, ["a", "b", "c", "e"], ["2020-01-01"] * 4, ["T"] * 4,
                                fingerprint=fp, faiss=__import__("faiss"), np=__import__("numpy"))
    corpus_loo = idx.off_distribution_threshold()
    # explicit gate_threshold -> stored as off_distribution_threshold; corpus_loo always under its own key
    n1_index.save_snapshot(idx, str(tmp_path / "snap"), gate_threshold=0.4242)
    meta = json.loads((tmp_path / "snap" / "meta.json").read_text(encoding="utf-8"))
    assert abs(meta["off_distribution_threshold"] - 0.4242) < 1e-9
    assert abs(meta["corpus_loo_threshold"] - corpus_loo) < 1e-9
    # no gate_threshold -> off_distribution_threshold falls back to corpus_loo (back-compat)
    n1_index.save_snapshot(idx, str(tmp_path / "snap2"))
    meta2 = json.loads((tmp_path / "snap2" / "meta.json").read_text(encoding="utf-8"))
    assert abs(meta2["off_distribution_threshold"] - corpus_loo) < 1e-9
    assert abs(meta2["corpus_loo_threshold"] - corpus_loo) < 1e-9

def test_annotate_snapshot_diagnostics_merges_without_touching_gate(tmp_path):
    import json, n1_index
    snap = tmp_path / "snap"; snap.mkdir()
    (snap / "meta.json").write_text(json.dumps(
        {"ids": ["W1"], "off_distribution_threshold": 0.2350, "corpus_loo_threshold": 0.0765}), encoding="utf-8")
    n1_index.annotate_snapshot_diagnostics(str(snap), roc_auroc_heldout_field=0.82, roc_fpr_at_tpr95=0.11)
    meta = json.loads((snap / "meta.json").read_text(encoding="utf-8"))
    assert meta["off_distribution_threshold"] == 0.2350          # GATE untouched
    assert meta["roc_auroc_heldout_field"] == 0.82 and meta["roc_fpr_at_tpr95"] == 0.11


def test_annotate_snapshot_diagnostics_rejects_protected_gate_keys(tmp_path):
    # passing the gate / corpus_loo in kv must be DROPPED (the gate is set ONLY by the build path) — the dangerous path
    import json, n1_index
    snap = tmp_path / "snap"; snap.mkdir()
    (snap / "meta.json").write_text(json.dumps(
        {"off_distribution_threshold": 0.2350, "corpus_loo_threshold": 0.0765}), encoding="utf-8")
    meta = n1_index.annotate_snapshot_diagnostics(
        str(snap), off_distribution_threshold=0.9999, corpus_loo_threshold=0.5, roc_auroc_heldout_field=0.8)
    assert meta["off_distribution_threshold"] == 0.2350          # gate override REJECTED
    assert meta["corpus_loo_threshold"] == 0.0765               # protected diagnostic REJECTED
    assert meta["roc_auroc_heldout_field"] == 0.8               # a genuine diagnostic key IS applied

def test_faiss_query_calibrated_threshold_oracle_matches_inmemory():
    import pytest
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed; oracle runs only with the live deps")
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    import n1_novelty
    fp = {"name": "x", "revision": "r", "query_adapter": "q", "doc_adapter": "d",
          "dim": 2, "normalize": "l2", "metric": "cosine"}
    raw = [[1.0, 0.0], [0.92, 0.39], [0.0, 1.0], [-0.4, 0.9], [0.7, 0.7]]   # spread unit-ish vectors
    ids = ["a", "b", "c", "d", "e"]
    idx = n1_index.FaissN1Index(raw, ids, ["2020-01-01"] * 5, ["T"] * 5,
                                fingerprint=fp, faiss=__import__("faiss"), np=__import__("numpy"))
    qvecs = [[0.95, 0.05], [0.1, 0.95], [0.6, 0.75]]      # query vectors (raw)
    qids = ["a", "c", "novel"]                             # first two share ids with corpus (exclude-self)
    faiss_thr = idx.query_calibrated_threshold(qvecs, qids, percentile=0.95)
    mem = n1_novelty.InMemoryN1Index([{"id": i, "vec": v} for i, v in zip(ids, raw)],
                                     distance_fn=n1_novelty.cosine_distance)
    mem_thr = mem.query_calibrated_threshold([{"id": i, "vec": v} for i, v in zip(qids, qvecs)], percentile=0.95)
    assert faiss_thr is not None and mem_thr is not None
    assert abs(faiss_thr - mem_thr) < 1e-6                 # faiss path == pure oracle


def test_nearest_k_returns_ordered_ids_titles_distances():
    import pytest
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed")
    fp = {"name": "x", "revision": "r", "query_adapter": "q", "doc_adapter": "d",
          "dim": 2, "normalize": "l2", "metric": "cosine"}
    raw = [[1.0, 0.0], [0.92, 0.39], [0.0, 1.0], [0.7, 0.7]]
    idx = n1_index.FaissN1Index(raw, ["a", "b", "c", "e"], ["2020-01-01"] * 4, ["Ta", "Tb", "Tc", "Te"],
                                fingerprint=fp, faiss=__import__("faiss"), np=__import__("numpy"))
    nbs = idx.nearest_k([1.0, 0.0], k=2, date_cutoff="2025-01-01")
    assert len(nbs) == 2
    assert set(nbs[0]) == {"id", "title", "distance"}
    assert nbs[0]["id"] == "a" and nbs[0]["title"] == "Ta"          # exact-match query -> "a" nearest
    assert nbs[0]["distance"] <= nbs[1]["distance"]                 # ascending distance
    # date filter excluding all -> []
    assert idx.nearest_k([1.0, 0.0], k=2, date_cutoff="2019-01-01") == []
