import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import run_scope as rs

def test_derive_run_id_deterministic_and_scoped():
    a = rs.derive_run_id("is X novel?", "2026-06-23T00:00:00Z")
    assert a == rs.derive_run_id("is X novel?", "2026-06-23T00:00:00Z")   # deterministic
    assert a != rs.derive_run_id("is Y novel?", "2026-06-23T00:00:00Z")   # question-scoped
    assert a != rs.derive_run_id("is X novel?", "2026-06-23T00:00:01Z")   # time-scoped
    assert a.startswith("r") and len(a) == 12 and a[1:].isalnum()

def test_make_loop_id_run_scoped_and_legacy_fallback():
    assert rs.make_loop_id("r0123456789a", 2) == "r0123456789a.L2"
    assert rs.make_loop_id("", 1) == "L1"        # blank run_id -> legacy bare id (back-compat)
    assert rs.make_loop_id(None, 0) == "L0"
