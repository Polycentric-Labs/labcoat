# scripts/run_scope.py
"""labcoat C1 — run-scoped identifiers so a SHARED workspace does not collide across invocations. The ledger
key (loop_id) was always 'L{i}', so two questions sharing one workspace cross-contaminated _gather_findings +
fleet-resume. derive_run_id makes a per-invocation prefix; make_loop_id composes the run-scoped ledger key.
Pure stdlib; deterministic; the start timestamp is INJECTED (no datetime.now()). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import hashlib


def derive_run_id(question: str, started_at_iso: str) -> str:
    """Short, deterministic, filesystem-safe run id from the question + an injected ISO start timestamp.
    Same (question, timestamp) -> same id; a different question OR timestamp -> a different id. 'r' + 11 hex."""
    seed = f"{(question or '').strip()}|{(started_at_iso or '').strip()}".encode("utf-8")
    return "r" + hashlib.sha256(seed).hexdigest()[:11]


def make_loop_id(run_id: str, loop_i: int) -> str:
    """Compose the run-scoped ledger loop id: '{run_id}.L{loop_i}'. A blank/None run_id falls back to the
    legacy bare 'L{loop_i}' so a single-question run is unchanged (back-compat)."""
    rid = (run_id or "").strip()
    return f"{rid}.L{int(loop_i)}" if rid else f"L{int(loop_i)}"
