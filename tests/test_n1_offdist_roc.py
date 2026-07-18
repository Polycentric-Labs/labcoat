# tests/test_n1_offdist_roc.py
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pytest
import n1_offdist_roc as h
import n1_index

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "openalex_heldout_arthistory.json"


class _StubEmb:
    DIM = 8
    def embed(self, texts, *, role="document", batch_size=32):
        # deterministic, role-sensitive: queries land slightly off the doc manifold
        out = []
        for t in texts:
            base = (len(t) % 5) * 0.1
            out.append([1.0, base, (0.2 if role == "query" else 0.0), 0, 0, 0, 0, 0])
        return out
    def fingerprint(self):
        return {"name": "stub", "query_adapter": "q", "doc_adapter": "d", "revision": None,
                "dim": 8, "normalize": "l2", "metric": "cosine"}


def _full_index():
    emb = _StubEmb()
    recs = [{"id": f"W{i}", "title": f"corpus title {i}", "date": "2020-01-01"} for i in range(40)]
    vecs = emb.embed([r["title"] for r in recs], role="document")
    entries = [{"id": r["id"], "vec": v, "date": r["date"], "title": r["title"]} for r, v in zip(recs, vecs)]
    idx = n1_index.build_index(entries, embedder_fingerprint=emb.fingerprint())
    idx._loaded_threshold = 0.30
    return idx, emb


def test_build_scores_assembles_labeled_set_and_split():
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed")
    idx, emb = _full_index()
    import n1_corpus_openalex as oa
    page = json.loads(_FIX.read_text(encoding="utf-8"))
    field_recs = [oa.normalize_openalex_record(w) for w in page["results"]]
    assembled, extras = h.build_scores(idx, emb, heldout_fields=[{"name": "arthistory", "records": field_recs}],
                                       per_field=50, test_frac=0.25, seed=1)
    # labels present for both classes; in_corpus group is label 0; field group is label 1
    assert 0 in assembled["labels"] and 1 in assembled["labels"]
    assert all(assembled["labels"][i] == 0 for i in assembled["index_of"]["in_corpus"])
    assert "heldout_field:arthistory" in assembled["index_of"]
    assert "synthetic" in assembled["index_of"] and "random" in assembled["index_of"]
    assert extras["deployed_gate"] == 0.30                       # gate carried through unchanged
    assert "in_corpus_ref" in extras and "field_meta" in extras  # percentile_rank reference + per-field counts
    assert "arthistory" in extras["field_meta"]


def test_report_layers_and_field_stratified():
    import roc
    assembled = roc.assemble_labeled_set(
        in_corpus=[0.10, 0.12, 0.14, 0.16],
        ood_by_kind={"heldout_field:a": [0.7, 0.72], "heldout_field:b": [0.65, 0.68],
                     "synthetic": [0.6], "random": [0.95, 0.97]})
    extras = {"deployed_gate": 0.30, "calibration_split_threshold": 0.25}
    rep = h.report(assembled, extras, n_boot=50, seed=3)
    assert set(rep["per_field"]) == {"heldout_field:a", "heldout_field:b"}
    assert rep["heldout_field"]["auroc"] == 1.0      # honest headline layer (real fields only, no synthetic/random)
    assert rep["real_text"]["auroc"] == 1.0          # fields+synthetic all far above in_corpus
    assert rep["field_stratified"]["n_fields"] == 2
    assert rep["field_stratified"]["median_fpr_at_tpr95"] == 0.0   # true median of [0.0, 0.0]
    assert rep["real_text"]["deployed_gate_op"]["fpr"] == 0.0   # gate 0.30 flags no in_corpus here
    assert rep["soft_score"]["ref_size"] == 0        # no in_corpus_ref supplied in this synthetic extras


def test_report_soft_score_percentile_rank():
    import roc
    assembled = roc.assemble_labeled_set(in_corpus=[0.1, 0.2, 0.3, 0.4],
                                         ood_by_kind={"heldout_field:a": [0.9]})
    extras = {"deployed_gate": 0.35, "calibration_split_threshold": 0.25,
              "in_corpus_ref": [0.1, 0.2, 0.3, 0.4]}
    rep = h.report(assembled, extras, n_boot=20, seed=1)
    # gate 0.35 sits at/above 3 of 4 in-corpus distances -> percentile_rank 0.75; calib-split 0.25 -> 0.5
    assert rep["soft_score"]["deployed_gate_percentile_rank"] == 0.75
    assert rep["soft_score"]["calib_split_percentile_rank"] == 0.5
    assert rep["soft_score"]["ref_size"] == 4


def test_annotate_roundtrip_from_harness_numbers(tmp_path):
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed")
    import roc
    snap = tmp_path / "snap"; snap.mkdir()
    (snap / "meta.json").write_text(json.dumps({"off_distribution_threshold": 0.30}), encoding="utf-8")
    scores = [0.1, 0.2, 0.8, 0.9]; labels = [0, 0, 1, 1]
    meta = n1_index.annotate_snapshot_diagnostics(str(snap), roc_auroc_heldout_field=roc.roc_auc(scores, labels))
    assert meta["off_distribution_threshold"] == 0.30 and meta["roc_auroc_heldout_field"] == 1.0
