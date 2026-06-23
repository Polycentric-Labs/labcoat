import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import orchestrator

def _rec(qid, status, ts="2026-06-21T12:00:00Z"):
    return {"query_id": qid, "completion_status": status, "timestamp": ts}

def test_plan_resume_classifies_by_status():
    records = [_rec("q1", "complete"), _rec("q2", "known-incomplete"),
               _rec("q3", "unavailable"), _rec("q4", "deterministic-fail")]
    plan = orchestrator.plan_resume(records)
    assert plan["done"] == ["q1"]
    assert plan["to_redrive"] == ["q2", "q3"]
    assert plan["abandoned"] == ["q4"]

def test_plan_resume_latest_record_per_query_wins():
    # append-only: q1 was known-incomplete, later completed -> done
    plan = orchestrator.plan_resume([_rec("q1", "known-incomplete"), _rec("q1", "complete")])
    assert plan["done"] == ["q1"] and plan["to_redrive"] == []

def test_plan_resume_dedups_and_preserves_first_seen_order():
    records = [_rec("q2", "known-incomplete"), _rec("q1", "known-incomplete"), _rec("q2", "known-incomplete")]
    plan = orchestrator.plan_resume(records)
    assert plan["to_redrive"] == ["q2", "q1"]

def test_plan_resume_empty_is_all_empty():
    assert orchestrator.plan_resume([]) == {"to_redrive": [], "done": [], "abandoned": []}

def test_plan_resume_skips_records_without_query_id():
    plan = orchestrator.plan_resume([{"completion_status": "complete"}, _rec("q1", "complete")])
    assert plan["done"] == ["q1"]

def test_plan_resume_record_without_status_lands_in_no_bucket():
    # a query_id with a missing/None completion_status is defensively excluded from all buckets
    plan = orchestrator.plan_resume([{"query_id": "q9"}, _rec("q1", "complete")])
    assert plan == {"to_redrive": [], "done": ["q1"], "abandoned": []}
    assert "q9" not in plan["to_redrive"] + plan["done"] + plan["abandoned"]

def test_loop_decision_hard_stop_when_pacing_hard_stop():
    d = orchestrator.loop_decision({"pacing_state": "hard-stop", "pacing_resume_after_s": None, "would_breach": False})
    assert d["action"] == "stop"

def test_loop_decision_stop_on_breach_even_if_paused():
    # budget beats a transient pause: pausing then resuming would still breach
    d = orchestrator.loop_decision({"pacing_state": "graceful-pause", "pacing_resume_after_s": 30.0, "would_breach": True})
    assert d["action"] == "stop" and "tolerance" in d["reason"].lower()

def test_loop_decision_pause_when_paced_and_within_budget():
    d = orchestrator.loop_decision({"pacing_state": "graceful-pause", "pacing_resume_after_s": 12.0, "would_breach": False})
    assert d["action"] == "pause" and d["resume_after_s"] == 12.0

def test_loop_decision_continue_when_clear():
    d = orchestrator.loop_decision({"pacing_state": "proceed", "pacing_resume_after_s": None, "would_breach": False})
    assert d["action"] == "continue"

def test_loop_decision_novelty_collapse_warn_only_continues():
    # WARN-only (default): a novelty collapse does NOT change the action, just warns
    d = orchestrator.loop_decision({"pacing_state": "proceed", "pacing_resume_after_s": None,
                                    "would_breach": False, "novelty_collapsed": True})
    assert d["action"] == "continue" and "WARN" in d["reason"]

def test_loop_decision_novelty_collapse_enforcing_pauses():
    d = orchestrator.loop_decision({"pacing_state": "proceed", "pacing_resume_after_s": None,
                                    "would_breach": False, "novelty_collapsed": True, "novelty_enforcing": True})
    assert d["action"] == "pause" and "novelty" in d["reason"].lower()

def test_loop_decision_budget_still_beats_novelty():
    # budget stop has priority over a novelty collapse
    d = orchestrator.loop_decision({"pacing_state": "proceed", "pacing_resume_after_s": None,
                                    "would_breach": True, "novelty_collapsed": True, "novelty_enforcing": True})
    assert d["action"] == "stop"

def test_loop_decision_novelty_enforcing_but_not_collapsed_continues():
    # the enforcing flag alone (no collapse) must not change behavior
    d = orchestrator.loop_decision({"pacing_state": "proceed", "pacing_resume_after_s": None,
                                    "would_breach": False, "novelty_collapsed": False, "novelty_enforcing": True})
    assert d["action"] == "continue"


def test_orchestrator_host_spec_exists_and_holds_the_core():
    doc = pathlib.Path(__file__).resolve().parent.parent / "references" / "orchestrator-host.md"
    assert doc.exists(), "references/orchestrator-host.md is the operator-facing shell spec"
    text = doc.read_text(encoding="utf-8")
    # the auth rule (CLI/SDK + API key env; NOT the OAuth token; NOT Desktop)
    assert "ANTHROPIC_API_KEY" in text and "CLAUDE_CODE_OAUTH_TOKEN" in text
    # the durable + at-least-once posture
    assert "fsync" in text and "at-least-once" in text.lower()
    # it wires the pure core
    assert "plan_resume" in text and "loop_decision" in text and "pacing_decision" in text
    # the bring-up smoke checklist exists (not unit tests)
    assert "smoke" in text.lower() and "Session 0" in text
