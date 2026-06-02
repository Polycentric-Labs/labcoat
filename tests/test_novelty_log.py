# tests/test_novelty_log.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import novelty_log as nl

def test_append_and_read_roundtrip(tmp_path):
    f = tmp_path / "good-sources.md"
    nl.append_good_sources(["arxiv.org", "nvd.nist.gov"], path=f)
    got = nl.read_good_sources(path=f)
    assert "arxiv.org" in got and "nvd.nist.gov" in got

def test_append_dedups_case_insensitive(tmp_path):
    f = tmp_path / "good-sources.md"
    nl.append_good_sources(["ArXiv.org"], path=f)
    nl.append_good_sources(["arxiv.org"], path=f)
    assert nl.read_good_sources(path=f).count("arxiv.org") == 1

def test_read_missing_file_returns_empty(tmp_path):
    assert nl.read_good_sources(path=tmp_path / "nope.md") == []

def test_same_call_dedup(tmp_path):
    f = tmp_path / "good-sources.md"
    nl.append_good_sources(["arxiv.org", "ArXiv.org"], path=f)
    assert nl.read_good_sources(path=f).count("arxiv.org") == 1

def test_embedded_newline_domain_does_not_corrupt(tmp_path):
    f = tmp_path / "good-sources.md"
    nl.append_good_sources(["arxiv.org\nevil.com"], path=f)
    result = nl.read_good_sources(path=f)
    assert "evil.com" not in result          # no bare unprefixed line was written
    # every stored entry is a single bullet line (file structure intact)
    body = f.read_text(encoding="utf-8")
    assert all(line.startswith("- ") or line.startswith("#") or line.strip() == ""
               for line in body.splitlines())

def test_whitespace_domain_is_ignored(tmp_path):
    f = tmp_path / "good-sources.md"
    nl.append_good_sources(["   "], path=f)
    assert not f.exists()                     # nothing to write -> no ghost file
