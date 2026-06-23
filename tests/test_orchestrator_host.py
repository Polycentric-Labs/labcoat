import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import orchestrator_host as host
import audit
import spend

def test_expand_fleet_work_one_item_per_subq_model():
    subqs = [{"id": "s1", "sub_question": "is X novel?", "prompt": "Investigate X"},
             {"id": "s2", "sub_question": "does Y exist?", "prompt": "Check Y"}]
    models = [{"id": "google/gemini-2.5-pro"}, {"id": "x-ai/grok-4"}]
    work = host.expand_fleet_work(subqs, models)
    assert len(work) == 4
    assert work[0]["query_id"] == "s1::google/gemini-2.5-pro"
    assert work[0]["sub_question"] == "is X novel?" and work[0]["prompt"] == "Investigate X"
    assert work[0]["model_spec"] == {"id": "google/gemini-2.5-pro"}
    assert {w["query_id"] for w in work} == {
        "s1::google/gemini-2.5-pro", "s1::x-ai/grok-4", "s2::google/gemini-2.5-pro", "s2::x-ai/grok-4"}

def test_expand_fleet_work_empty():
    assert host.expand_fleet_work([], [{"id": "m"}]) == []
    assert host.expand_fleet_work([{"id": "s", "sub_question": "q", "prompt": "p"}], []) == []

def test_expand_fleet_work_loop_scoped_query_ids():
    # loop-evolution fix: positional sq ids collide across loops; loop_id must scope the query_id so a later
    # loop's evolved sub-questions are NOT skipped by the durable-resume dedup. (Live-smoke finding 2026-06-23.)
    subqs = [{"id": "sq1", "sub_question": "q", "prompt": "p"}]
    models = [{"id": "m1"}]
    w1 = host.expand_fleet_work(subqs, models, loop_id="rABC.L1")
    w2 = host.expand_fleet_work(subqs, models, loop_id="rABC.L2")
    assert w1[0]["query_id"] == "rABC.L1::sq1::m1"
    assert w2[0]["query_id"] == "rABC.L2::sq1::m1"
    assert w1[0]["query_id"] != w2[0]["query_id"]                 # L2's sq1 must differ from L1's sq1
    assert host.expand_fleet_work(subqs, models)[0]["query_id"] == "sq1::m1"   # back-compat: no loop_id -> legacy

def test_select_work_does_not_skip_a_different_loops_queries():
    # L1's loop-scoped sq1 is complete; L2's loop-scoped sq1 must still be driven (the bug the smoke caught)
    subqs = [{"id": "sq1", "sub_question": "q", "prompt": "p"}]
    ledger = [{"query_id": "rX.L1::sq1::m1", "completion_status": "complete"}]
    l2_work = host.expand_fleet_work(subqs, [{"id": "m1"}], loop_id="rX.L2")
    assert [w["query_id"] for w in host.select_work(l2_work, ledger)] == ["rX.L2::sq1::m1"]


def _work(qid):
    return {"query_id": qid, "sub_question": "q", "prompt": "p", "model_spec": {"id": "m"}}

def _led(qid, status):
    return {"query_id": qid, "completion_status": status}

def test_select_work_drives_new_and_redrive_skips_done_and_abandoned():
    work = [_work("a"), _work("b"), _work("c"), _work("d")]
    ledger = [_led("a", "complete"),            # done -> skip
              _led("b", "known-incomplete"),    # redrive
              _led("c", "deterministic-fail")]  # abandoned -> skip
    # "d" is not in the ledger at all -> new -> drive
    sel = host.select_work(work, ledger)
    assert [w["query_id"] for w in sel] == ["b", "d"]

def test_select_work_empty_ledger_drives_all():
    work = [_work("a"), _work("b")]
    assert [w["query_id"] for w in host.select_work(work, [])] == ["a", "b"]


def _ok_fleet(prompt, models, *, available, **kw):
    # one model_spec in, one result out (the host drives one outbound query at a time)
    m = models[0]["id"]
    return [{"model": m, "ok": True, "completion_status": "complete", "cost_est": 0.002,
             "capture_path": f"caps/{m}.partial", "text": "..."}]

def _clean_redactor(prompt, *, client_terms=()):
    return {"hard_block": False, "clean_text": prompt, "signal": {"recommend_stop": False},
            "findings": [], "redactions_applied": []}

def _clock_seq():
    seq = iter([f"2026-06-21T12:00:0{i}Z" for i in range(9)])
    return lambda: next(seq)

def test_drive_query_records_intent_then_result_and_accumulates_spend(tmp_path):
    led = str(tmp_path / "L.jsonl")
    tr = spend.Tracker()
    w = {"query_id": "s1::m", "sub_question": "is X novel?", "prompt": "Investigate X",
         "model_spec": {"id": "m"}}
    out = host.drive_query(w, loop_id="L1", ledger_path=led, tracker=tr, available=["m"], clock=_clock_seq(),
                           fleet_runner=_ok_fleet, redactor=_clean_redactor, est_cost=0.01)
    rows = audit.read_ledger(led)
    # an intent (known-incomplete) row written BEFORE the call, then the result (complete) row
    assert rows[0]["completion_status"] == "known-incomplete"   # the fsync'd intent
    assert rows[-1]["completion_status"] == "complete" and rows[-1]["query_id"] == "s1::m"
    assert tr.reserved() == 0.0           # reservation released on a confirmed result
    assert tr.openrouter() == 0.002       # actual fleet cost committed
    assert out["ok"] is True

def test_drive_query_hard_block_halts_without_calling_fleet(tmp_path):
    led = str(tmp_path / "L.jsonl")
    def _blocking_redactor(prompt, *, client_terms=()):
        return {"hard_block": True, "clean_text": None, "signal": None,
                "findings": [{"label": "OpenRouter API key shape"}], "redactions_applied": []}
    def _never_fleet(*a, **k):
        raise AssertionError("fleet must NOT be called when redaction hard-blocks")
    w = {"query_id": "s1::m", "sub_question": "q", "prompt": "sk-or-v1-LEAK", "model_spec": {"id": "m"}}
    out = host.drive_query(w, loop_id="L1", ledger_path=led, tracker=spend.Tracker(), available=["m"],
                           clock=_clock_seq(), fleet_runner=_never_fleet, redactor=_blocking_redactor, est_cost=0.01)
    assert out["hard_block"] is True
    assert audit.read_ledger(led) == []   # nothing left the machine; nothing recorded


def _led_full(qid, status):
    return audit.make_ledger_record(timestamp="2026-06-21T11:00:00Z", loop_id="L0", query_id=qid,
        sub_question="q", model="m", redaction_applied=True, raw_capture_path=None, completion_status=status)

def test_run_loop_drives_all_then_decides_continue(tmp_path):
    led = str(tmp_path / "L.jsonl")
    subqs = [{"id": "s1", "sub_question": "q1", "prompt": "p1"},
             {"id": "s2", "sub_question": "q2", "prompt": "p2"}]
    work = host.expand_fleet_work(subqs, [{"id": "m"}])
    out = host.run_loop(work, ledger_path=led, loop_id="L1", clock=_clock_seq(), fleet_runner=_ok_fleet,
                        redactor=_clean_redactor, available=["m"], tracker=spend.Tracker(),
                        est_per_query=0.01, tolerance=100.0, next_loop_est=0.05)
    assert out["decision"]["action"] == "continue"
    assert out["driven"] == 2 and out["halted"] is False
    # both sub-questions recorded complete
    rows = audit.read_ledger(led)
    assert sum(1 for r in rows if r["completion_status"] == "complete") == 2

def test_run_loop_reboot_resume_only_redrives_incomplete(tmp_path):
    led = str(tmp_path / "L.jsonl")
    # simulate a crashed prior loop: s1::m completed, s2::m only has the intent (known-incomplete)
    audit.append_ledger(led, _led_full("s1::m", "complete"))
    audit.append_ledger(led, _led_full("s2::m", "known-incomplete"))
    work = host.expand_fleet_work([{"id": "s1", "sub_question": "q1", "prompt": "p1"},
                                   {"id": "s2", "sub_question": "q2", "prompt": "p2"}], [{"id": "m"}])
    driven_qids = []
    def _tracking_fleet(prompt, models, *, available, **kw):
        driven_qids.append(models[0]["id"]); return _ok_fleet(prompt, models, available=available)
    out = host.run_loop(work, ledger_path=led, loop_id="L2", clock=_clock_seq(), fleet_runner=_tracking_fleet,
                        redactor=_clean_redactor, available=["m"], tracker=spend.Tracker(),
                        est_per_query=0.01, tolerance=100.0, next_loop_est=0.05)
    # ONLY s2 was re-driven (s1 was already complete -> skipped)
    assert out["driven"] == 1
    assert driven_qids == ["m"]   # exactly one outbound drive happened (s2::m); s1::m was skipped

def test_run_loop_stops_when_next_loop_would_breach_tolerance(tmp_path):
    led = str(tmp_path / "L.jsonl")
    work = host.expand_fleet_work([{"id": "s1", "sub_question": "q1", "prompt": "p1"}], [{"id": "m"}])
    # tolerance tiny: after this loop, next_loop_est would breach -> decision stop
    out = host.run_loop(work, ledger_path=led, loop_id="L1", clock=_clock_seq(), fleet_runner=_ok_fleet,
                        redactor=_clean_redactor, available=["m"], tracker=spend.Tracker(),
                        est_per_query=0.01, tolerance=0.001, next_loop_est=0.05)
    assert out["decision"]["action"] == "stop" and "tolerance" in out["decision"]["reason"].lower()

def test_run_loop_resilient_to_fleet_exception_releases_reservation(tmp_path):
    led = str(tmp_path / "L.jsonl")
    work = host.expand_fleet_work([{"id": "s1", "sub_question": "q1", "prompt": "p1"}], [{"id": "m"}])
    def _raising_fleet(prompt, models, *, available, **kw):
        raise RuntimeError("boom")
    tr = spend.Tracker()
    out = host.run_loop(work, ledger_path=led, loop_id="L1", clock=_clock_seq(), fleet_runner=_raising_fleet,
                        redactor=_clean_redactor, available=["m"], tracker=tr,
                        est_per_query=0.01, tolerance=100.0, next_loop_est=0.05)
    assert out["halted"] is True and "boom" in (out["error"] or "")
    assert tr.reserved() == 0.0          # reservation released despite the exception (no leak)
    # the fsync'd intent is on disk (known-incomplete) so a future loop re-drives it
    rows = audit.read_ledger(led)
    assert rows[-1]["completion_status"] == "known-incomplete"
