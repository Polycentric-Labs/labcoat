import sys, pathlib, hashlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_corpus

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "arxiv_sample.xml"

def test_parse_feed_finds_entries():
    entries = n1_corpus._parse_feed(_FIX.read_text(encoding="utf-8"))
    assert len(entries) == 2

def test_normalize_record_strips_id_and_version_and_collapses():
    entries = n1_corpus._parse_feed(_FIX.read_text(encoding="utf-8"))
    rec = n1_corpus.normalize_record(entries[0])
    assert rec["id"] == "2503.01508"                       # prefix + trailing v2 stripped
    assert rec["date"] == "2025-03-03"                     # published (v1) date, YYYY-MM-DD
    assert rec["title"] == "Enabling AI Scientists to Recognize Innovation"   # whitespace collapsed
    assert rec["abstract"] == "We propose a domain-agnostic algorithm for assessing novelty."
    assert "cs.DL" in rec["categories"] and "cs.AI" in rec["categories"]
    assert rec["categories"][0] == "cs.DL"                 # primary category first

def test_embed_text_joins_title_sep_abstract():
    rec = {"title": "T", "abstract": "A"}
    assert n1_corpus.embed_text(rec) == "T[SEP]A"
    assert n1_corpus.embed_text({"title": "T", "abstract": ""}) == "T[SEP]"

def test_fetch_arxiv_uses_cache_no_network(tmp_path):
    # Pre-populate the cache so fetch_arxiv never touches the network.
    query, start, page_size = "cat:cs.LG", 0, 200
    key = hashlib.sha256(f"{query}|{start}|{page_size}".encode()).hexdigest()[:16]
    (tmp_path / f"arxiv_{key}.xml").write_text(_FIX.read_text(encoding="utf-8"), encoding="utf-8")
    def _boom(*a, **k):  # injected sleep must never be called on a pure cache hit
        raise AssertionError("sleep called on cache hit")
    recs = n1_corpus.fetch_arxiv(query, max_results=2, cache_dir=str(tmp_path),
                                 start=start, page_size=page_size, sleep=_boom)
    assert len(recs) == 2
    assert recs[0]["id"] == "2503.01508" and recs[1]["id"] == "2204.06507"
