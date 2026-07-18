import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pubmed_adapter as pa

# Every test that exercises the network shell sets/clears NCBI_CONTACT_EMAIL via monkeypatch (auto-restored), so the
# suite asserts the same result whether or not the developer's own machine happens to export a contact address.
_TEST_EMAIL = "researcher@example.org"

_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle><MedlineCitation>
  <PMID Version="1">3945825</PMID>
  <Article>
   <Journal><JournalIssue><PubDate><Year>1985</Year></PubDate></JournalIssue></Journal>
   <ArticleTitle>Fish oil, Raynaud's syndrome, and undiscovered public knowledge.</ArticleTitle>
   <Abstract><AbstractText Label="AIM">Dietary fish oil raises blood viscosity concerns.</AbstractText>
   <AbstractText Label="RESULT">Platelet aggregation fell.</AbstractText></Abstract>
  </Article>
  <MeshHeadingList>
   <MeshHeading><DescriptorName UI="D001796" MajorTopicYN="N">Blood Viscosity</DescriptorName></MeshHeading>
   <MeshHeading><DescriptorName UI="D011928" MajorTopicYN="Y">Raynaud Disease</DescriptorName></MeshHeading>
   <MeshHeading><DescriptorName UI="D005395">Fish Oils</DescriptorName>
     <QualifierName>administration &amp; dosage</QualifierName></MeshHeading>
  </MeshHeadingList>
 </MedlineCitation></PubmedArticle>
 <PubmedArticle><MedlineCitation>
  <PMID Version="1">1</PMID>
  <Article><Journal><JournalIssue><PubDate><MedlineDate>1984 Jan-Feb</MedlineDate></PubDate></JournalIssue></Journal>
   <ArticleTitle>No abstract, no mesh.</ArticleTitle></Article>
 </MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""

def test_parse_efetch_xml_extracts_fields():
    recs = pa.parse_efetch_xml(_EFETCH_XML)
    assert len(recs) == 2
    r = recs[0]
    assert r["pmid"] == "3945825"
    assert r["title"].startswith("Fish oil")
    assert "blood viscosity" in r["abstract"].lower() and "platelet aggregation" in r["abstract"].lower()
    assert r["mesh"] == ["Blood Viscosity", "Raynaud Disease", "Fish Oils"]
    assert r["year"] == 1985

def test_parse_efetch_xml_handles_missing_abstract_and_medlinedate():
    recs = pa.parse_efetch_xml(_EFETCH_XML)
    r = recs[1]
    assert r["pmid"] == "1" and r["abstract"] == "" and r["mesh"] == [] and r["year"] == 1984

def test_mesh_concept_list_dedupes_first_seen():
    rec = {"mesh": ["Blood Viscosity", "Fish Oils", "Blood Viscosity"]}
    assert pa.mesh_concept_list(rec) == ["Blood Viscosity", "Fish Oils"]

def test_normalize_pubmed_record_shape():
    rec = {"pmid": "42", "title": "T", "abstract": "A", "mesh": ["X", "Y"], "year": 1980}
    n = pa.normalize_pubmed_record(rec)
    assert n == {"id": "42", "title": "T", "abstract": "A", "concepts": ["X", "Y"], "year": 1980}

def test_parse_efetch_xml_rejects_entity_declarations():
    # billion-laughs style payload must NOT be expanded; the hardened parser returns [] safely
    boom = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY lol "lol">]><PubmedArticleSet>&lol;</PubmedArticleSet>'
    assert pa.parse_efetch_xml(boom) == []

def test_parse_esearch_json_returns_pmids():
    text = '{"esearchresult": {"count": "2", "idlist": ["3945825", "1"]}}'
    assert pa.parse_esearch_json(text) == ["3945825", "1"]

def test_parse_esearch_json_malformed_returns_empty():
    assert pa.parse_esearch_json("not json") == []
    assert pa.parse_esearch_json('{"esearchresult": {}}') == []

_ESEARCH_JSON = '{"esearchresult": {"count":"1","idlist":["3945825"]}}'

def test_esearch_pmids_uses_injected_get_and_polite_params(monkeypatch):
    monkeypatch.setenv("NCBI_CONTACT_EMAIL", _TEST_EMAIL)
    calls = {}
    def fake_get(url, params):
        calls["url"] = url; calls["params"] = params
        return (200, _ESEARCH_JSON)
    ids = pa.esearch_pmids('"Raynaud Disease"[MeSH] AND ("1900"[PDAT] : "1985"[PDAT])', retmax=10, get=fake_get)
    assert ids == ["3945825"]
    assert "esearch.fcgi" in calls["url"]
    assert calls["params"]["db"] == "pubmed" and calls["params"]["retmode"] == "json"
    assert calls["params"]["retmax"] == 10
    assert calls["params"]["tool"] == "labcoat" and calls["params"]["email"] == _TEST_EMAIL

def test_esearch_pmids_fails_closed_when_contact_env_absent(monkeypatch):
    # Documented behavior: no contact -> RuntimeError naming the env var, and NOTHING is sent to NCBI. Never a fake.
    monkeypatch.delenv("NCBI_CONTACT_EMAIL", raising=False)
    def boom(url, params):
        raise AssertionError("must not call NCBI without a contact address")
    with pytest.raises(RuntimeError, match="NCBI_CONTACT_EMAIL"):
        pa.esearch_pmids('"Raynaud Disease"[MeSH]', get=boom)

def test_esearch_pmids_blank_contact_env_is_treated_as_absent(monkeypatch):
    monkeypatch.setenv("NCBI_CONTACT_EMAIL", "   ")
    def boom(url, params):
        raise AssertionError("must not call NCBI with a whitespace-only contact address")
    with pytest.raises(RuntimeError, match="NCBI_CONTACT_EMAIL"):
        pa.esearch_pmids("term", get=boom)

def test_explicit_email_arg_overrides_contact_env(monkeypatch):
    monkeypatch.setenv("NCBI_CONTACT_EMAIL", _TEST_EMAIL)
    calls = {}
    def fake_get(url, params):
        calls["params"] = params
        return (200, _ESEARCH_JSON)
    pa.esearch_pmids("term", get=fake_get, email="override@example.net")
    assert calls["params"]["email"] == "override@example.net"

def test_no_contact_address_is_hardcoded_in_the_module():
    # Regression guard for the swap: the shipped source must carry no real address, only the env var + placeholders.
    src = pathlib.Path(pa.__file__).read_text(encoding="utf-8")
    assert "NCBI_CONTACT_EMAIL" in src
    import re as _re
    for addr in _re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", src):
        assert addr.endswith("example.org"), f"non-placeholder address hardcoded in pubmed_adapter.py: {addr}"

def test_efetch_records_batches_and_sleeps_between_live_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("NCBI_CONTACT_EMAIL", _TEST_EMAIL)
    slept = []
    def fake_get(url, params):
        assert "efetch.fcgi" in url and params["retmode"] == "xml"
        assert params["email"] == _TEST_EMAIL and params["tool"] == "labcoat"
        return (200, _EFETCH_XML)
    recs = pa.efetch_records(["3945825", "1", "2"], get=fake_get, sleep=lambda s: slept.append(s),
                             cache_dir=str(tmp_path), batch=2)
    # 3 ids, batch=2 -> 2 live batches -> 1 inter-batch sleep; each batch returns the 2-record fixture
    assert len(recs) == 4
    assert len(slept) >= 1 and all(s >= 0.34 for s in slept)

def test_efetch_records_fails_closed_when_contact_env_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("NCBI_CONTACT_EMAIL", raising=False)
    def boom(url, params):
        raise AssertionError("must not call NCBI without a contact address")
    with pytest.raises(RuntimeError, match="NCBI_CONTACT_EMAIL"):
        pa.efetch_records(["3945825"], get=boom, cache_dir=str(tmp_path))

def test_efetch_records_cached_replay_needs_no_contact_env(monkeypatch, tmp_path):
    # A fully-cached replay of a frozen corpus sends nothing to NCBI, so it must still run with no contact set.
    monkeypatch.setenv("NCBI_CONTACT_EMAIL", _TEST_EMAIL)
    pa.efetch_records(["3945825"], get=lambda url, params: (200, _EFETCH_XML), cache_dir=str(tmp_path))
    monkeypatch.delenv("NCBI_CONTACT_EMAIL", raising=False)
    def boom(url, params):
        raise AssertionError("cached replay must not hit the network")
    recs = pa.efetch_records(["3945825"], get=boom, cache_dir=str(tmp_path))
    assert len(recs) == 2 and recs[0]["pmid"] == "3945825"

def test_efetch_records_empty_input_no_calls(monkeypatch):
    monkeypatch.delenv("NCBI_CONTACT_EMAIL", raising=False)
    def boom(url, params):  # must not be called
        raise AssertionError("should not fetch for empty pmids")
    assert pa.efetch_records([], get=boom) == []
