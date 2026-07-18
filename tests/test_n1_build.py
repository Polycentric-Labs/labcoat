import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_build, n1_index

class _StubEmb:
    DIM = 2
    def embed(self, texts, *, role="document", batch_size=32):
        # deterministic 2D unit-ish vectors; query role nudged so query!=doc (exercises the calibration path)
        return [[1.0, float((len(t) % 7) + (1 if role == "query" else 0)) * 0.1] for t in texts]
    def fingerprint(self):
        return {"name": "stub", "query_adapter": "q", "doc_adapter": "d", "revision": None,
                "dim": 2, "normalize": "l2", "metric": "cosine"}

def test_build_and_save_index_writes_snapshot_with_both_thresholds(tmp_path):
    import pytest
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed")
    recs = [{"id": f"W{i}", "title": f"Title number {i}", "abstract": f"abstract body {i}", "date": "2021-01-01"}
            for i in range(6)]
    n, corpus_loo, gate = n1_build.build_and_save_index(recs, embedder=_StubEmb(), snapshot_path=str(tmp_path / "snap"))
    assert n == 6
    meta = json.loads((tmp_path / "snap" / "meta.json").read_text(encoding="utf-8"))
    assert "off_distribution_threshold" in meta and "corpus_loo_threshold" in meta
    assert len(meta["ids"]) == 6
