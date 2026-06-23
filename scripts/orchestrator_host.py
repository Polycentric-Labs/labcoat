# scripts/orchestrator_host.py
"""Tier-2 durable orchestrator HOST — the imperative SHELL that wires the pure core into a real, reboot-durable
FLEET LOOP DRIVER (sync). Injectable fleet_runner / redactor / clock so the loop is integration-testable with NO
network, key, or spend; the live path injects fleet.run_fleet + redaction_gate.redact + a real ISO clock.

The outbound-query resume unit is (sub-question, model): query_id = f"{subq_id}::{model_id}" so
orchestrator.plan_resume keys cleanly. Guarantee = at-least-once + pessimistic spend reservation. The async
Agent-SDK brain (decompose/synthesize) is the §5.2 Nuclear pipeline, NOT this minimal bring-up.
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import audit
import orchestrator
import spend


def expand_fleet_work(subquestions: list[dict], models: list[dict], *, loop_id: str = "") -> list[dict]:
    """Fan each sub-question across each model into a flat list of single outbound-query work items.
    Each item: {query_id, sub_question, prompt, model_spec}. The query_id is LOOP-SCOPED when loop_id is given —
    f"{loop_id}::{subq_id}::{model_id}" — because sub-question ids are positional (sq1..sqN) and REPEAT across
    loops; without the loop_id prefix a later loop's evolved sq1 collides with an earlier loop's completed sq1 and
    the durable-resume dedup (select_work/plan_resume) skips it, so an evolved loop fans out 0 queries (the
    2026-06-23 live-smoke finding). A blank loop_id keeps the legacy bare f"{subq_id}::{model_id}" (back-compat)."""
    work = []
    for sq in subquestions:
        for m in models:
            qid = f"{loop_id}::{sq['id']}::{m['id']}" if loop_id else f"{sq['id']}::{m['id']}"
            work.append({"query_id": qid, "sub_question": sq["sub_question"],
                         "prompt": sq["prompt"], "model_spec": m})
    return work


def select_work(work: list[dict], ledger_records: list[dict]) -> list[dict]:
    """Resume: drive every work item EXCEPT those already done (complete) or abandoned (deterministic-fail) —
    i.e. re-drive the known-incomplete / unavailable and drive the never-seen (new). Preserves `work` order.
    (plan_resume classifies each ledger query_id into exactly one bucket, so 'not done and not abandoned'
    == 'to_redrive or new'.)"""
    plan = orchestrator.plan_resume(ledger_records)
    skip = set(plan["done"]) | set(plan["abandoned"])
    return [w for w in work if w["query_id"] not in skip]


def drive_query(w: dict, *, loop_id: str, ledger_path: str, tracker, available, clock,
                fleet_runner, redactor, est_cost: float, client_terms=()) -> dict:
    """Drive ONE outbound query end-to-end with the durable ordering:
    redact -> (hard_block? halt, nothing leaves) -> reserve(est) -> append intent (known-incomplete, fsync=True,
    record-BEFORE-call) -> fleet_runner(clean_text, [model_spec]) -> release(est) + commit actual cost +
    append the result record. Returns {ok, hard_block, result} (result = the fleet result dict or None)."""
    r = redactor(w["prompt"], client_terms=client_terms)
    if r.get("hard_block"):
        return {"ok": False, "hard_block": True, "result": None}   # caller halts + rotates
    tracker.reserve(est_cost)
    intent = audit.make_ledger_record(
        timestamp=clock(), loop_id=loop_id, query_id=w["query_id"], sub_question=w["sub_question"],
        model=w["model_spec"]["id"], redaction_applied=True, raw_capture_path=None,
        completion_status="known-incomplete")
    audit.append_ledger(ledger_path, intent, fsync=True)   # the reboot-durable record-before-call write
    try:
        results = fleet_runner(r["clean_text"], [w["model_spec"]], available=available)
        fr = results[0] if results else {"model": w["model_spec"]["id"], "completion_status": "unavailable",
                                         "cost_est": 0.0, "capture_path": None}  # unavailable -> re-driven next loop
        tracker.add_openrouter(fr.get("cost_est", 0.0))
        audit.append_ledger(ledger_path, audit.ledger_record_from_fleet(
            timestamp=clock(), loop_id=loop_id, query_id=w["query_id"], sub_question=w["sub_question"],
            redaction_applied=True, fleet_result=fr))
    finally:
        tracker.release(est_cost)   # ALWAYS release, even if fleet_runner raises -> no reservation leak (the
                                    # fsync'd intent stays known-incomplete on disk, so resume re-drives it)
    return {"ok": fr.get("completion_status") == "complete", "hard_block": False, "result": fr}


def run_loop(work: list[dict], *, ledger_path: str, loop_id: str, clock, fleet_runner, redactor, available,
             tracker, est_per_query: float, tolerance: float, next_loop_est: float, client_terms=()) -> dict:
    """One durable loop: resume from the ledger, drive each not-yet-complete outbound query, then decide whether
    the NEXT loop may run. Returns {decision, driven, halted, error, breakdown}. `halted` is True if a redaction
    hard-block OR an unexpected drive error stopped the loop early; `error` holds the repr of any such error
    (a Class-A secret hard-block never leaves the machine + must be rotated)."""
    sel = select_work(work, audit.read_ledger(ledger_path))
    driven, halted, error = 0, False, None
    for w in sel:
        try:
            out = drive_query(w, loop_id=loop_id, ledger_path=ledger_path, tracker=tracker, available=available,
                              clock=clock, fleet_runner=fleet_runner, redactor=redactor, est_cost=est_per_query,
                              client_terms=client_terms)
        except Exception as e:   # noqa: BLE001 — an unexpected drive/fleet error: the fsync'd intent stays on
            error, halted = repr(e), True   # disk (resume re-drives it). Stop gracefully, never crash with no return.
            break
        if out["hard_block"]:
            halted = True
            break
        driven += 1
    # per-loop gate: would the NEXT loop breach tolerance on the pessimistic (committed + reserved) total?
    spent = tracker.breakdown()["total_with_reserved_usd"]
    breach = spend.would_next_loop_breach(spent, next_loop_est, tolerance)
    decision = orchestrator.loop_decision(
        # no live rate-limit signal in the v1 fleet loop driver -> any non-stop/pause pacing_state falls through
        # to the budget/continue path; the live header -> pacing.pacing_decision wiring is the Nuclear follow-on.
        {"pacing_state": "proceed", "pacing_resume_after_s": None,
         "would_breach": not breach["within_tolerance"]})
    return {"decision": decision, "driven": driven, "halted": halted, "error": error,
            "breakdown": tracker.breakdown()}
