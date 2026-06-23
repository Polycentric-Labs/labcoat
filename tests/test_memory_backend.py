import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import memory_backend as mb

def test_filebackend_seen_corpus_cny_roundtrip(tmp_path):
    b = mb.FileBackend(str(tmp_path))
    b.append_seen_keys(["k1", "k2"]); b.append_seen_keys(["k2", "k3"])   # dedup vs file
    assert b.read_seen_keys() == {"k1", "k2", "k3"}
    b.append_corpus(["finding one", "multi\nline"], valid_time="2026-01-01", tx_time="2026-01-02")
    assert b.read_corpus() == ["finding one", "multi\nline"]            # newline-safe
    b.append_cny(2); b.append_cny(0)
    assert b.read_cny_history() == [2, 0]

def test_filebackend_archive_keeps_best_per_cell(tmp_path):
    b = mb.FileBackend(str(tmp_path))
    b.upsert_elite("cellA", 1.0, "f1", tx_time="t1")
    b.upsert_elite("cellA", 3.0, "f2", tx_time="t2")   # higher
    b.upsert_elite("cellA", 2.0, "f3", tx_time="t3")   # lower -> ignored on read
    assert b.read_archive()["cellA"] == {"quality": 3.0, "finding": "f2"}

def test_filebackend_provenance_append_and_read(tmp_path):
    b = mb.FileBackend(str(tmp_path))
    b.record_provenance("X is real", ["https://a", "https://b"], loop_id="L1",
                        valid_time="2026-01-01", tx_time="2026-01-02")
    rows = b.read_provenance()
    assert rows[0]["finding"] == "X is real" and rows[0]["sources"] == ["https://a", "https://b"]
    assert rows[0]["loop_id"] == "L1" and rows[0]["tx_time"] == "2026-01-02"

def test_sqlitebackend_seen_corpus_cny_roundtrip(tmp_path):
    b = mb.SqliteBackend(str(tmp_path / "mem.db"))
    b.append_seen_keys(["k1", "k2"]); b.append_seen_keys(["k2", "k3"])
    assert b.read_seen_keys() == {"k1", "k2", "k3"}
    b.append_corpus(["one", "multi\nline"], valid_time="v", tx_time="t")
    assert b.read_corpus() == ["one", "multi\nline"]
    b.append_cny(2); b.append_cny(0)
    assert b.read_cny_history() == [2, 0]

def test_sqlitebackend_archive_best_per_cell_and_provenance(tmp_path):
    b = mb.SqliteBackend(str(tmp_path / "mem.db"))
    b.upsert_elite("cellA", 1.0, "f1", tx_time="t1")
    b.upsert_elite("cellA", 3.0, "f2", tx_time="t2")
    b.upsert_elite("cellA", 2.0, "f3", tx_time="t3")
    assert b.read_archive()["cellA"] == {"quality": 3.0, "finding": "f2"}
    b.record_provenance("X", ["https://a", "https://b"], loop_id="L1", valid_time="v", tx_time="t")
    rows = b.read_provenance()
    assert rows[0]["sources"] == ["https://a", "https://b"] and rows[0]["loop_id"] == "L1"

def test_sqlitebackend_is_append_only_and_persists_across_reopen(tmp_path):
    p = str(tmp_path / "mem.db")
    b1 = mb.SqliteBackend(p); b1.append_corpus(["a"]); b1.append_cny(1)
    b2 = mb.SqliteBackend(p)   # reopen the same db file
    assert b2.read_corpus() == ["a"] and b2.read_cny_history() == [1]

def test_sqlitebackend_creates_missing_parent_dir(tmp_path):
    b = mb.SqliteBackend(str(tmp_path / "newsub" / "deeper" / "mem.db"))   # parent dirs don't exist yet
    b.append_cny(1)
    assert b.read_cny_history() == [1]


# ---------------------------------------------------------------------------
# Fix 4 (campaign): provenance persists evidence
# ---------------------------------------------------------------------------

def test_filebackend_provenance_persists_evidence(tmp_path):
    b = mb.FileBackend(str(tmp_path))
    b.record_provenance("X", ["https://a"], loop_id="L1", valid_time="v", tx_time="t", evidence="see https://a")
    assert b.read_provenance()[0]["evidence"] == "see https://a"

def test_sqlitebackend_provenance_persists_evidence(tmp_path):
    b = mb.SqliteBackend(str(tmp_path / "m.db"))
    b.record_provenance("X", ["https://a"], loop_id="L1", valid_time="v", tx_time="t", evidence="see https://a")
    assert b.read_provenance()[0]["evidence"] == "see https://a"
