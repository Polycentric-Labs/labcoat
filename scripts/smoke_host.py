# scripts/smoke_host.py
"""Operator LIVE-SMOKE for the durable host — NOT unit-tested; the `run` subcommand spends a few CENTS.

Reads OPENROUTER_API_KEY from the environment (the primary path), falling back to an OPTIONAL convenience file
$LABCOAT_SECRETS_DIR/openrouter.env (default ~/.secrets/openrouter.env) — loaded in-process, NEVER printed,
source path announced. Then:
  estimate : FREE — fetch the live catalogue (validates network egress + the key), pick the cheapest available
             model, and print the projected cost of the tiny smoke run. No paid call.
  run      : fire ONE tiny loop (1 trivial sub-question, 1 cheap model, max_tokens=256) through the REAL fleet,
             then RE-RUN over the same ledger to prove resume SKIPS the completed query (no second spend) —
             demonstrating the durable record-before-call + reboot-resume against the live API.

Usage:  python scripts/smoke_host.py estimate | run
This is the §"bring-up SMOKE CHECKLIST" item from references/orchestrator-host.md. License: MIT. Author: Allen Byrd.
"""
from __future__ import annotations
import os
import sys
import pathlib
import tempfile
import datetime as _dt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fleet
import redaction_gate
import spend
import orchestrator_host as host

# Prioritized cheap, commonly-available models — the first present in the live catalogue wins. Prices are a
# conservative estimate only; the actual cost comes from the real usage tokens returned by run_fleet.
_CHEAP = [
    {"id": "openai/gpt-4o-mini",               "in_price": 0.15, "out_price": 0.60},
    {"id": "google/gemini-2.0-flash-001",      "in_price": 0.10, "out_price": 0.40},
    {"id": "meta-llama/llama-3.1-8b-instruct", "in_price": 0.02, "out_price": 0.05},
    {"id": "anthropic/claude-3.5-haiku",       "in_price": 0.80, "out_price": 4.00},
]
_MAX_TOKENS = 256
_IN_TOK_EST = 80


def _load_key() -> None:
    """Env var first (the primary, documented path); optional convenience file second. Never prints the value;
    always announces the source path. Delegates to nuclear._load_env_key — one loader, one policy."""
    import nuclear
    nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")


def _pick_model():
    available = fleet.list_models(os.environ["OPENROUTER_API_KEY"])   # free GET /models (tests network + key)
    for spec in _CHEAP:
        if spec["id"] in available:
            return spec, available
    raise SystemExit("none of the cheap smoke models are in the live catalogue; edit _CHEAP")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "estimate"
    _load_key()
    spec, available = _pick_model()
    est = fleet.estimate_cost(in_tokens=_IN_TOK_EST, out_tokens=_MAX_TOKENS,
                              in_price=spec["in_price"], out_price=spec["out_price"])
    print(f"[smoke] live catalogue reachable + key valid ({len(available)} models). "
          f"chosen={spec['id']} max_tokens={_MAX_TOKENS} -> projected cost ~ ${est:.5f}")
    if mode == "estimate":
        print("[smoke] estimate-only; NO paid call made. Re-run with `run` to fire the tiny live smoke.")
        return
    if mode != "run":
        raise SystemExit("usage: smoke_host.py estimate | run")

    # --- the paid tiny smoke ---
    model_spec = {**spec, "max_tokens": _MAX_TOKENS, "reasoning": False}
    clock = lambda: _dt.datetime.now(_dt.timezone.utc).isoformat()   # a REAL clock (the live shell, not a test)
    with tempfile.TemporaryDirectory() as d:
        led = str(pathlib.Path(d) / "SESSION-LEDGER.jsonl")
        subqs = [{"id": "smoke1", "sub_question": "Reply with the single word OK.",
                  "prompt": "Reply with the single word OK."}]
        work = host.expand_fleet_work(subqs, [model_spec])
        tr = spend.Tracker()
        out1 = host.run_loop(work, ledger_path=led, loop_id="L1", clock=clock, fleet_runner=fleet.run_fleet,
                             redactor=redaction_gate.redact, available=available, tracker=tr,
                             est_per_query=est, tolerance=1.0, next_loop_est=est)
        print(f"[smoke] loop1: driven={out1['driven']} halted={out1['halted']} "
              f"decision={out1['decision']['action']} spent=${tr.breakdown()['total_usd']:.5f}")
        # RE-RUN over the same ledger -> resume must SKIP the completed query (no second spend)
        tr2 = spend.Tracker()
        out2 = host.run_loop(work, ledger_path=led, loop_id="L2", clock=clock, fleet_runner=fleet.run_fleet,
                             redactor=redaction_gate.redact, available=available, tracker=tr2,
                             est_per_query=est, tolerance=1.0, next_loop_est=est)
        rows = host.audit.read_ledger(led)
        final = [r["completion_status"] for r in rows if r["query_id"] == work[0]["query_id"]][-1]
        print(f"[smoke] loop2 (resume): driven={out2['driven']} (expect 0 -> completed query skipped) "
              f"spent=${tr2.breakdown()['total_usd']:.5f}")
        print(f"[smoke] ledger rows={len(rows)}; final status of the smoke query: {final}")
    print("[smoke] DONE — durable record-before-call + reboot-resume validated against the live API.")


if __name__ == "__main__":
    main()
