# scripts/orchestrator.py
"""labcoat Tier-2 durable orchestrator — the PURE decision core (functional core / imperative shell split).
No network, no API key, no datetime.now() — every input is injected (the Tier-1 determinism contract). The live
Agent-SDK / Windows-Service host is a thin shell, spec'd in references/orchestrator-host.md (not built here).

Guarantee = at-least-once + application idempotency (no engine does better; the upstream gateway has no request
dedup). The cost backstop is pessimistic spend reservation (spend.Tracker.reserve). License: MIT. Author: Allen Byrd.
"""
from __future__ import annotations

# Ledger completion_status -> resume bucket (mirrors scripts/audit.py + fleet.py enums).
_DONE = {"complete"}                       # finished: skip; the fsync'd capture IS the recorded output
_REDRIVE = {"known-incomplete", "unavailable"}   # genuinely unfinished -> re-issue (reserved pessimistically)
_ABANDON = {"deterministic-fail"}          # a 4xx -> never retry (would fail identically + waste money)


def plan_resume(records: list[dict]) -> dict:
    """Reboot-resume plan from the append-only ledger. Classify each query_id by its LATEST record's
    completion_status into {to_redrive, done, abandoned}. First-seen query_id order; deduped. An unknown
    status (shouldn't occur given the enum) is left out of all buckets (defensive)."""
    latest: dict[str, str] = {}
    order: list[str] = []
    for r in records:
        qid = r.get("query_id")
        if qid is None:
            continue
        if qid not in latest:
            order.append(qid)
        latest[qid] = r.get("completion_status")
    plan: dict[str, list[str]] = {"to_redrive": [], "done": [], "abandoned": []}
    for qid in order:
        st = latest[qid]
        if st in _DONE:
            plan["done"].append(qid)
        elif st in _REDRIVE:
            plan["to_redrive"].append(qid)
        elif st in _ABANDON:
            plan["abandoned"].append(qid)
    return plan


def loop_decision(state: dict) -> dict:
    """Next-loop action from the composed signals. Priority (budget beats a transient pause):
      1. pacing hard-stop      -> stop   (quota/credits exhausted)
      2. would_breach          -> stop   (next loop would cross the spend tolerance; surface the option menu)
      3. pacing graceful-pause -> pause  (resume_after_s)
      4. novelty yield-collapse -> pause (only if novelty_enforcing; else WARN + continue)
    `would_breach` is computed by the shell via spend.would_next_loop_breach on the reserved-aware total
    (keeps this module decoupled from spend). The over-tolerance OPTION MENU is SKILL.md prose; this returns
    only the decision."""
    pacing = state.get("pacing_state")
    if pacing == "hard-stop":
        return {"action": "stop", "reason": "pacing hard-stop (quota/credits exhausted)", "resume_after_s": None}
    if state.get("would_breach"):
        return {"action": "stop", "reason": "next loop would breach spend tolerance", "resume_after_s": None}
    if pacing == "graceful-pause":
        return {"action": "pause", "reason": "rate-limited; pause then resume",
                "resume_after_s": state.get("pacing_resume_after_s")}
    # 4th branch (BELOW budget + pacing): novelty yield-collapse. WARN-only by default — never auto-stops;
    # pauses-and-pings ONLY when explicitly enforcing (the scoping memo's safety condition).
    if state.get("novelty_collapsed"):
        if state.get("novelty_enforcing"):
            return {"action": "pause", "reason": "novelty yield-collapse — pause and ping (surface option menu)",
                    "resume_after_s": None}
        return {"action": "continue", "reason": "WARN: novelty yield-collapse (gate is WARN-only)",
                "resume_after_s": None}
    return {"action": "continue", "reason": "within budget and not rate-limited", "resume_after_s": None}
