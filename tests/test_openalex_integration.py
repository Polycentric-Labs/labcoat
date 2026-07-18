"""Integration test over a REAL (trimmed) OpenAlex fixture + the full corpus->snapshot->load pipeline. Guards the
deep-build path against silent regressions: reconstruct/normalize on real inverted indices, dedupe-by-id on real ids,
and (faiss-guarded) build_and_save_index -> save -> load round-trip with the gate threshold consumed + fingerprint
fail-close. Uses a stub embedder (no SPECTER2) so it stays fast."""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_corpus_openalex as oa

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "openalex_sample.json"


def _fixture_page():
    return json.loads(_FIX.read_text(encoding="utf-8"))


def test_normalize_real_openalex_work():
    work = _fixture_page()["results"][0]
    rec = oa.normalize_openalex_record(work)
    assert rec["id"].startswith("W") and "openalex.org" not in rec["id"]   # bare id, prefix stripped
    assert rec["title"]                                                    # real title present
    assert len(rec["abstract"]) > 50                                       # reconstructed from a real inverted index
    assert rec["date"][:4].isdigit() and len(rec["date"]) == 10            # YYYY-MM-DD


def test_fetch_openalex_dedupes_real_fixture(tmp_path):
    # injected get returns the single fixture page (meta.next_cursor=None terminates). The fixture's 4 works include
    # a duplicate id, so dedupe-by-id yields 3 unique records with non-empty real abstracts.
    page = _fixture_page()
    def _get(url, params):
        return 200, page
    recs = oa.fetch_openalex(["Cfix"], per_concept=50, cache_dir=str(tmp_path), get=_get, sleep=lambda s: None)
    ids = [r["id"] for r in recs]
    assert len(ids) == 3 and len(set(ids)) == 3                            # the duplicate id was deduped away
    assert all(r["abstract"] for r in recs)                               # all reconstructed non-empty


class _StubEmb:
    DIM = 2
    def embed(self, texts, *, role="document", batch_size=32):
        return [[1.0, float((len(t) % 7) + (1 if role == "query" else 0)) * 0.1] for t in texts]
    def fingerprint(self):
        return {"name": "stub", "query_adapter": "q", "doc_adapter": "d", "revision": None,
                "dim": 2, "normalize": "l2", "metric": "cosine"}


def test_openalex_endtoend_snapshot_roundtrip_and_fingerprint_failclose(tmp_path):
    import pytest
    import n1_index, n1_build
    if not n1_index.n1_index_available():
        pytest.skip("faiss/numpy not installed")
    page = _fixture_page()
    recs = oa.fetch_openalex(["Cfix"], per_concept=50, cache_dir=str(tmp_path / "cache"),
                             get=lambda u, p: (200, page), sleep=lambda s: None)
    emb = _StubEmb()
    snap = str(tmp_path / "snap")
    n, corpus_loo, gate = n1_build.build_and_save_index(recs, embedder=emb, snapshot_path=snap)
    assert n == 3
    meta = json.loads((tmp_path / "snap" / "meta.json").read_text(encoding="utf-8"))
    assert "off_distribution_threshold" in meta and "corpus_loo_threshold" in meta
    # load round-trips with the matching fingerprint; the GATE (query-calibrated) value is what load exposes
    idx = n1_index.load_snapshot(snap, active_fingerprint=emb.fingerprint())
    assert idx._loaded_threshold == meta["off_distribution_threshold"]
    # fingerprint mismatch fail-closes (a drifted embedder must NOT silently load)
    drifted = dict(emb.fingerprint()); drifted["revision"] = "DIFFERENT"
    with pytest.raises(RuntimeError):
        n1_index.load_snapshot(snap, active_fingerprint=drifted)
