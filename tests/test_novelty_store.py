import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import novelty_store as ns

def test_read_seen_keys_missing_file_is_empty_set(tmp_path):
    assert ns.read_seen_keys(str(tmp_path / "nope.txt")) == set()

def test_append_then_read_seen_keys_roundtrip(tmp_path):
    p = str(tmp_path / "seen.txt")
    ns.append_seen_keys(p, ["aaa", "bbb"])
    assert ns.read_seen_keys(p) == {"aaa", "bbb"}

def test_append_seen_keys_dedups_against_file_and_within_call(tmp_path):
    p = str(tmp_path / "seen.txt")
    ns.append_seen_keys(p, ["aaa", "aaa", "bbb"])   # within-call dup
    ns.append_seen_keys(p, ["bbb", "ccc"])          # vs-file dup
    lines = [ln for ln in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert sorted(lines) == ["aaa", "bbb", "ccc"]   # each key exactly once

def test_append_seen_keys_empty_is_noop(tmp_path):
    p = str(tmp_path / "seen.txt")
    ns.append_seen_keys(p, [])
    assert ns.read_seen_keys(p) == set()

def test_corpus_missing_file_is_empty(tmp_path):
    assert ns.read_corpus(str(tmp_path / "nope.jsonl")) == []

def test_corpus_roundtrip_is_newline_safe(tmp_path):
    p = str(tmp_path / "corpus.jsonl")
    ns.append_corpus(p, ["finding one", "multi\nline finding"])
    ns.append_corpus(p, ["third"])
    assert ns.read_corpus(p) == ["finding one", "multi\nline finding", "third"]

def test_append_corpus_skips_blank_and_empty(tmp_path):
    p = str(tmp_path / "corpus.jsonl")
    ns.append_corpus(p, ["", "  ", "real"])
    ns.append_corpus(p, [])
    assert ns.read_corpus(p) == ["real"]

def test_cny_history_missing_is_empty(tmp_path):
    assert ns.read_cny_history(str(tmp_path / "nope.txt")) == []

def test_cny_history_append_and_read(tmp_path):
    p = str(tmp_path / "cny.txt")
    ns.append_cny(p, 3)
    ns.append_cny(p, 0)
    ns.append_cny(p, 2)
    assert ns.read_cny_history(p) == [3, 0, 2]
