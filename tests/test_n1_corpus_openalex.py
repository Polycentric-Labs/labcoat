import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_corpus_openalex as oa

def test_reconstruct_abstract_orders_by_position_and_repeats():
    assert oa.reconstruct_abstract({"a": [0, 2], "b": [1]}) == "a b a"
    assert oa.reconstruct_abstract({"The": [0], "cat": [1], "sat": [2]}) == "The cat sat"

def test_reconstruct_abstract_empty_and_none():
    assert oa.reconstruct_abstract(None) == ""
    assert oa.reconstruct_abstract({}) == ""
    assert oa.reconstruct_abstract({"solo": [0]}) == "solo"

def test_normalize_openalex_record_strips_id_builds_fields():
    work = {"id": "https://openalex.org/W42", "title": "A Study",
            "abstract_inverted_index": {"hello": [0], "world": [1]},
            "publication_date": "2021-05-09",
            "primary_topic": {"display_name": "Immunology"},
            "concepts": [{"display_name": "T cell"}, {"display_name": "Antibody"}]}
    rec = oa.normalize_openalex_record(work)
    assert rec["id"] == "W42"
    assert rec["title"] == "A Study"
    assert rec["abstract"] == "hello world"
    assert rec["date"] == "2021-05-09"
    assert rec["categories"][0] == "Immunology" and "T cell" in rec["categories"]

def test_normalize_openalex_record_tolerates_missing_fields():
    rec = oa.normalize_openalex_record({"id": "https://openalex.org/W7", "display_name": "Fallback Title"})
    assert rec["id"] == "W7" and rec["title"] == "Fallback Title"
    assert rec["abstract"] == "" and rec["date"] == "" and rec["categories"] == []

def _fake_get(mapping):
    # mapping: url-substring -> (status, json). Returns a get(url, params)->(status,json) that records calls.
    calls = []
    def _get(url, params):
        calls.append((url, params))
        for sub, resp in mapping.items():
            if sub in url:
                return resp
        return 404, {}
    _get.calls = calls
    return _get

def test_resolve_concepts_verifies_display_name():
    g = _fake_get({"/concepts": (200, {"results": [{"display_name": "Immunology",
                                                    "id": "https://openalex.org/C203014093"}]})})
    out = oa.resolve_concepts(["Immunology"], get=g)
    assert out == [{"name": "Immunology", "id": "C203014093"}]

def test_resolve_concepts_fail_closed_on_mismatch_or_empty():
    import pytest
    bad = _fake_get({"/concepts": (200, {"results": [{"display_name": "Immunity", "id": "https://openalex.org/C1"}]})})
    with pytest.raises(RuntimeError):
        oa.resolve_concepts(["Immunology"], get=bad)        # display_name != requested -> fail closed
    empty = _fake_get({"/concepts": (200, {"results": []})})
    with pytest.raises(RuntimeError):
        oa.resolve_concepts(["Nope"], get=empty)            # no hit -> fail closed

def _page(results, next_cursor):
    return {"results": results, "meta": {"next_cursor": next_cursor}}

def test_fetch_openalex_cursor_and_dedupe(tmp_path):
    # concept c1 returns W1,W2 then ends; concept c2 returns W2 (dup),W3 then ends. dedupe -> W1,W2,W3.
    def _w(i): return {"id": f"https://openalex.org/W{i}", "title": f"T{i}",
                       "abstract_inverted_index": {"x": [0]}, "publication_date": "2021-01-01"}
    seq = {}  # (cid,cursor) -> page
    pages = {
        ("C1", "*"): _page([_w(1), _w(2)], None),
        ("C2", "*"): _page([_w(2), _w(3)], None),
    }
    def _get(url, params):
        cid = params["filter"].split("concepts.id:")[1].split(",")[0]
        cur = params["cursor"]
        return 200, pages[(cid, cur)]
    recs = oa.fetch_openalex(["C1", "C2"], per_concept=10, cache_dir=str(tmp_path), get=_get,
                             sleep=lambda s: None)
    ids = [r["id"] for r in recs]
    assert ids == ["W1", "W2", "W3"]            # W2 deduped across concepts

def test_fetch_openalex_cache_hit_no_network(tmp_path):
    import hashlib, json as _json
    cid, cur = "C9", "*"
    key = hashlib.sha256(f"{cid}|2018-01-01|200|{cur}".encode("utf-8")).hexdigest()[:16]
    (tmp_path / f"openalex_{key}.json").write_text(
        _json.dumps(_page([{"id": "https://openalex.org/W5", "title": "T5",
                            "abstract_inverted_index": {"y": [0]}, "publication_date": "2020-01-01"}], None)),
        encoding="utf-8")
    def _boom(url, params):
        raise AssertionError("network called on cache hit")
    recs = oa.fetch_openalex(["C9"], per_concept=10, cache_dir=str(tmp_path), get=_boom,
                             sleep=lambda s: None)
    assert [r["id"] for r in recs] == ["W5"]

def test_fetch_openalex_retries_on_429(tmp_path):
    calls = {"n": 0}
    def _get(url, params):
        calls["n"] += 1
        if calls["n"] == 1:
            return 429, {}
        return 200, _page([{"id": "https://openalex.org/W1", "title": "T",
                            "abstract_inverted_index": {"z": [0]}, "publication_date": "2021-01-01"}], None)
    recs = oa.fetch_openalex(["C1"], per_concept=10, cache_dir=str(tmp_path), get=_get, sleep=lambda s: None)
    assert calls["n"] == 2 and [r["id"] for r in recs] == ["W1"]

def test_fetch_openalex_threads_cursor_across_pages(tmp_path):
    def _w(i): return {"id": f"https://openalex.org/W{i}", "title": f"T{i}",
                       "abstract_inverted_index": {"x": [0]}, "publication_date": "2021-01-01"}
    pages = {"*": _page([_w(1), _w(2)], "CUR2"), "CUR2": _page([_w(3)], None)}
    seen_cursors = []
    def _get(url, params):
        seen_cursors.append(params["cursor"])
        return 200, pages[params["cursor"]]
    recs = oa.fetch_openalex(["C1"], per_concept=10, cache_dir=str(tmp_path), get=_get, sleep=lambda s: None)
    assert [r["id"] for r in recs] == ["W1", "W2", "W3"]
    assert seen_cursors == ["*", "CUR2"]                       # cursor threaded into page 2
    assert len(list(tmp_path.glob("openalex_*.json"))) == 2    # distinct cache file per page
