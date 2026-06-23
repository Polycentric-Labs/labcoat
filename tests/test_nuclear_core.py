import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import nuclear_core as nc
import audit

def test_parse_decomposition_list_of_dicts_assigns_ids():
    out = nc.parse_decomposition([{"sub_question": "is X novel?", "prompt": "Investigate X"},
                                  {"sub_question": "does Y exist?"}])
    assert out[0] == {"id": "sq1", "sub_question": "is X novel?", "prompt": "Investigate X"}
    # prompt falls back to the sub_question when absent
    assert out[1] == {"id": "sq2", "sub_question": "does Y exist?", "prompt": "does Y exist?"}

def test_parse_decomposition_unwraps_envelope_and_json_string():
    env = {"sub_questions": [{"id": "a", "sub_question": "q", "prompt": "p"}]}
    assert nc.parse_decomposition(env)[0]["id"] == "a"
    import json
    assert nc.parse_decomposition(json.dumps([{"sub_question": "q", "prompt": "p"}]))[0]["sub_question"] == "q"

def test_parse_decomposition_drops_malformed_and_caps():
    items = ["not a dict", {}, {"sub_question": "ok", "prompt": "p"}]
    out = nc.parse_decomposition(items)
    assert [w["sub_question"] for w in out] == ["ok"]
    big = [{"sub_question": f"q{i}", "prompt": "p"} for i in range(100)]
    assert len(nc.parse_decomposition(big)) == 50   # _MAX_SUBQUESTIONS

def test_parse_decomposition_garbage_is_empty():
    assert nc.parse_decomposition(None) == []
    assert nc.parse_decomposition("{not json") == []
    assert nc.parse_decomposition(42) == []

def test_parse_verifications_normalizes_and_failsafes_verdict():
    out = nc.parse_verifications([
        {"claim_text": "repo foo/bar exists", "verdict": "CONFIRMED", "evidence": "gh api"},
        {"claim_text": "CVE-2099-0001 is real", "verdict": "made-up"},   # unknown -> unverifiable
        {"claim_text": "X", "verdict": "fabricated"}])
    assert out[0] == {"claim_text": "repo foo/bar exists", "verdict": "confirmed",
                      "evidence": "gh api", "sources": []}
    assert out[1]["verdict"] == "unverifiable"   # fail-safe: never silently confirmed
    assert out[2]["verdict"] == "fabricated"

def test_parse_verifications_drops_empty_claim_and_unwraps_envelope():
    out = nc.parse_verifications({"verifications": [
        {"claim_text": "", "verdict": "confirmed"}, {"claim": "alt key", "verdict": "confirmed"}]})
    assert [v["claim_text"] for v in out] == ["alt key"]

def test_parse_verifications_garbage_is_empty():
    assert nc.parse_verifications(None) == []
    assert nc.parse_verifications("nonsense") == []

def _clock_seq():
    seq = iter([f"2026-06-22T12:00:0{i}Z" for i in range(9)])
    return lambda: next(seq)

def test_confirmed_to_ledger_records_only_confirmed_with_claim_and_honesty_invariant():
    verifs = [{"claim_text": "A is real", "verdict": "confirmed", "evidence": "url1"},
              {"claim_text": "B is fake", "verdict": "fabricated", "evidence": ""},
              {"claim_text": "C unknown", "verdict": "unverifiable", "evidence": ""}]
    recs = nc.confirmed_to_ledger_records(verifications=verifs, loop_id="L1", query_id="sq1::m",
                                          sub_question="is X novel?", model="m", clock=_clock_seq())
    assert len(recs) == 1
    r = recs[0]
    assert r["validation_verdict"] == "confirmed" and r["completion_status"] == "complete"
    assert r["claim_text"] == "A is real" and r["query_id"] == "sq1::m" and r["model"] == "m"
    assert r["redaction_applied"] is True and r["timestamp"] == "2026-06-22T12:00:00Z"

def test_confirmed_to_ledger_records_empty_when_none_confirmed():
    verifs = [{"claim_text": "B", "verdict": "fabricated"}]
    assert nc.confirmed_to_ledger_records(verifications=verifs, loop_id="L1", query_id="q",
                                          sub_question="s", model="m", clock=_clock_seq()) == []

def test_confirmed_to_ledger_records_are_append_valid():
    # the records must pass audit.append_ledger's re-validation (enums + honesty invariant)
    recs = nc.confirmed_to_ledger_records(
        verifications=[{"claim_text": "A", "verdict": "confirmed"}],
        loop_id="L1", query_id="q", sub_question="s", model="m", clock=_clock_seq())
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    try:
        audit.append_ledger(p, recs[0])
        assert audit.read_ledger(p)[0]["claim_text"] == "A"
    finally:
        os.remove(p)

import orchestrator

def test_compose_loop_state_defaults_are_continue_path():
    st = nc.compose_loop_state()
    assert st == {"pacing_state": "proceed", "pacing_resume_after_s": None, "would_breach": False,
                  "novelty_collapsed": False, "novelty_enforcing": False}
    assert orchestrator.loop_decision(st)["action"] == "continue"

def test_compose_loop_state_coerces_and_passes_through():
    st = nc.compose_loop_state(pacing_state="graceful-pause", pacing_resume_after_s=20.0,
                               would_breach=0, novelty_collapsed=1, novelty_enforcing=0)
    # int flags coerce to bool (0 -> False, 1 -> True); pacing_resume_after_s passes through
    assert st["would_breach"] is False and st["novelty_collapsed"] is True and st["novelty_enforcing"] is False
    assert st["pacing_resume_after_s"] == 20.0
    # budget OK + graceful-pause -> pause (a budget breach would rank ABOVE pause; covered in test_orchestrator)
    assert orchestrator.loop_decision(st)["action"] == "pause"

def test_compose_loop_state_enforcing_collapse_pauses_else_warns():
    # the calibrated 2026-06-23 flip: novelty_enforcing=True + collapsed -> pause-and-ping (corrigible)
    enf = nc.compose_loop_state(novelty_collapsed=True, novelty_enforcing=True)
    assert enf["novelty_enforcing"] is True
    assert orchestrator.loop_decision(enf)["action"] == "pause"
    # WARN-only (enforcing False) + collapsed -> continue (the pre-flip behavior, still available via --no-...)
    warn = nc.compose_loop_state(novelty_collapsed=True, novelty_enforcing=False)
    assert orchestrator.loop_decision(warn)["action"] == "continue"

def test_menu_trigger_maps_decision_to_operator_surface():
    assert nc.menu_trigger({"action": "stop", "reason": "next loop would breach spend tolerance"}) == "tolerance-menu"
    assert nc.menu_trigger({"action": "pause", "reason": "novelty yield-collapse — pause and ping"}) == "novelty-ping"
    assert nc.menu_trigger({"action": "pause", "reason": "rate-limited; pause then resume"}) == "pacing-pause"
    assert nc.menu_trigger({"action": "continue", "reason": "within budget"}) is None
    assert nc.menu_trigger(None) is None

def test_decompose_prompt_includes_question_and_demands_strict_json():
    p = nc.decompose_prompt("is the labcoat novelty engine novel?", max_subquestions=4)
    assert "is the labcoat novelty engine novel?" in p
    assert "STRICT JSON" in p and "sub_question" in p and "4" in p

def test_verify_prompt_is_hard_skeptic_and_failsafe_unverifiable():
    p = nc.verify_prompt("- model claims CVE-2099-0001 exists")
    assert "CVE-2099-0001" in p
    assert "unverifiable" in p and "primary source" in p.lower()
    assert "STRICT JSON" in p

def test_synth_prompt_lists_confirmed_and_forbids_new_claims():
    p = nc.synth_prompt(["A is real", "B is real"])
    assert "A is real" in p and "B is real" in p
    assert "ONLY" in p
    # empty corpus still produces a safe prompt
    assert "no confirmed findings" in nc.synth_prompt([]).lower()

def test_confirmed_to_ledger_records_skips_non_dict_and_empty_claim():
    verifs = [None, "garbage", {"verdict": "confirmed"},            # non-dict items + missing claim_text
              {"claim_text": "  ", "verdict": "confirmed"},         # blank claim
              {"claim_text": "real", "verdict": "confirmed"}]       # the only valid confirmed row
    recs = nc.confirmed_to_ledger_records(verifications=verifs, loop_id="L1", query_id="q",
                                          sub_question="s", model="m", clock=_clock_seq())
    assert [r["claim_text"] for r in recs] == ["real"]

def test_parse_decomposition_ids_are_contiguous_after_malformed():
    out = nc.parse_decomposition(["bad", {}, {"sub_question": "q1", "prompt": "p"},
                                  {"sub_question": "q2", "prompt": "p"}])
    assert [w["id"] for w in out] == ["sq1", "sq2"]   # contiguous on OUTPUT, not input position

def test_parse_verifications_captures_sources_list():
    out = nc.parse_verifications([{"claim_text": "X", "verdict": "confirmed",
                                   "evidence": "e", "sources": ["https://a", " https://b ", ""]}])
    assert out[0]["sources"] == ["https://a", "https://b"]   # stripped, empties dropped, order preserved

def test_parse_verifications_sources_default_empty_when_absent_or_not_list():
    assert nc.parse_verifications([{"claim_text": "Y", "verdict": "unverifiable"}])[0]["sources"] == []
    assert nc.parse_verifications([{"claim_text": "Z", "verdict": "confirmed", "sources": "nope"}])[0]["sources"] == []

def test_parse_verifications_handles_markdown_fenced_json():
    # real brains often wrap JSON in ```json fences despite "STRICT JSON only" — must still parse
    fenced = '```json\n[{"claim_text": "X", "verdict": "confirmed", "sources": ["u"]}]\n```'
    out = nc.parse_verifications(fenced)
    assert out and out[0]["claim_text"] == "X" and out[0]["verdict"] == "confirmed" and out[0]["sources"] == ["u"]

def test_parse_decomposition_handles_prose_wrapped_json():
    # a brain may add a prose preamble/suffix around the JSON array — extract the embedded array
    prose = 'Sure! Here are the sub-questions:\n[{"sub_question": "q1", "prompt": "p1"}]\nLet me know!'
    out = nc.parse_decomposition(prose)
    assert out and out[0]["sub_question"] == "q1"

def test_confirmed_to_ledger_records_none_is_empty():
    assert nc.confirmed_to_ledger_records(verifications=None, loop_id="L1", query_id="q",
                                          sub_question="s", model="m", clock=_clock_seq()) == []


# ---------------------------------------------------------------------------
# Fix 3 (campaign): verify_prompt must request a sources array
# ---------------------------------------------------------------------------

def test_verify_prompt_requests_sources_array():
    p = nc.verify_prompt("- claim X")
    assert "sources" in p and ("array" in p.lower() or "[" in p)


# ---------------------------------------------------------------------------
# Task 4: gap-aware decompose_prompt + gap_prompt
# ---------------------------------------------------------------------------

def test_decompose_prompt_without_gaps_is_original_behavior():
    p = nc.decompose_prompt("is X novel?", max_subquestions=4)
    assert "is X novel?" in p and "NON-OVERLAPPING" in p and "STRICT JSON" in p
    assert "gap" not in p.lower()                      # no gap framing when prior_gaps is None

def test_decompose_prompt_with_gaps_evolves_from_them_contradictions_first():
    gaps = [{"id":"g1","kind":"contradiction","text":"A conflicts with B"},
            {"id":"g2","kind":"gap","text":"Z is unexplored"}]
    p = nc.decompose_prompt("is X novel?", prior_gaps=gaps, max_subquestions=4)
    assert "A conflicts with B" in p and "Z is unexplored" in p
    assert "contradiction" in p.lower() and "do not explain" in p.lower()   # anomaly guard present
    # the original question is still context, but the instruction targets the gaps
    assert "GAP" in p.upper()

def test_gap_prompt_asks_for_kinds_as_strict_json():
    p = nc.gap_prompt(["finding one", "finding two"], ["prior q1"])
    assert "finding one" in p and "prior q1" in p
    for kind in ("contradiction", "future_work", "gap"):
        assert kind in p
    assert "STRICT JSON" in p and "seed_evidence" in p
    assert "won_followup" in p

def test_decompose_prompt_empty_gaps_list_falls_back_to_original():
    p = nc.decompose_prompt("is X novel?", prior_gaps=[])
    assert "GAP" not in p.upper() and "is X novel?" in p   # empty list is falsy -> original decomposition
