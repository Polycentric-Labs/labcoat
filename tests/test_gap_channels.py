import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import gap_channels as gc

def test_abc_whitespace_finds_two_hop_no_direct_link():
    # A-B and B-C present, A-C ABSENT -> (A,C) is an ABC whitespace candidate, bridged by B
    edges = [["fish oil", "blood viscosity"], ["blood viscosity", "raynaud"]]
    out = gc.abc_whitespace(edges)
    assert len(out) == 1
    g = out[0]
    assert {g["a"], g["c"]} == {"fish oil", "raynaud"} and g["bridges"] == ["blood viscosity"]

def test_abc_whitespace_skips_directly_linked_pairs():
    edges = [["a", "b"], ["b", "c"], ["a", "c"]]   # a-c is DIRECT -> not a gap
    assert gc.abc_whitespace(edges) == []

def test_abc_whitespace_relatedness_filter_drops_spurious_absent_edges():
    edges = [["a", "b"], ["b", "c"]]
    # an absent edge is only a gap if a,c are related; relatedness 0 -> dropped
    assert gc.abc_whitespace(edges, relatedness_fn=lambda x, y: 0.0, min_relatedness=0.3) == []
    assert len(gc.abc_whitespace(edges, relatedness_fn=lambda x, y: 0.9, min_relatedness=0.3)) == 1
    assert gc.abc_whitespace([]) == [] and gc.abc_whitespace(None) == []

def test_mine_future_work_extracts_flagged_sentences():
    text = ("We present a new method. In future work, we will scale to 100B params. "
            "The results are strong. This remains an open problem for larger corpora.")
    hits = gc.mine_future_work(text)
    assert any("future work" in h.lower() for h in hits)
    assert any("remains an open" in h.lower() for h in hits)
    assert all("results are strong" not in h.lower() for h in hits)   # non-future sentence excluded
    assert gc.mine_future_work("") == []

def test_find_contradictions_same_subject_opposing():
    claims = [{"subject": "method X scales", "polarity": "+"},
              {"subject": "method X scales", "polarity": "-"},
              {"subject": "method Y is fast", "polarity": "+"}]
    out = gc.find_contradictions(claims)
    assert len(out) == 1 and out[0]["subject"] == "method x scales"
    # distinct VALUES for the same key also contradict
    val = [{"key": "best F1", "value": "0.82"}, {"key": "best F1", "value": "0.91"}]
    assert len(gc.find_contradictions(val)) == 1
    assert gc.find_contradictions([]) == []
    assert gc.find_contradictions([{"subject": "only one", "polarity": "+"}]) == []

def test_reconcile_whitespace_when_no_future_work_match():
    structural = [{"a": "concept_alpha", "c": "concept_beta", "bridges": ["b"]}]
    future = ["In future work we will study scaling laws."]          # neither concept mentioned
    out = gc.reconcile_channels(structural=structural, future_work=future)
    srecs = [g for g in out if g["gap_type"] == "structural"]
    assert srecs and all(g["evidentiary_status"] == "whitespace" for g in srecs)

def test_reconcile_known_but_unaddressed_when_both_concepts_in_one_future_sentence():
    structural = [{"a": "concept_alpha", "c": "concept_beta", "bridges": ["b"]}]
    future = ["In future work we will combine concept_alpha and concept_beta."]
    out = gc.reconcile_channels(structural=structural, future_work=future)
    srecs = [g for g in out if g["gap_type"] == "structural"]
    assert srecs and all(g["evidentiary_status"] == "known-but-unaddressed" for g in srecs)
    # the corroborating sentence is NOT also emitted as a separate speculative gap (S2 dedupe)
    assert not any(g["evidentiary_status"] == "speculative" for g in out)

def test_reconcile_substring_does_not_false_match_short_token():
    # "ml" must NOT match "formally"/"normally" via substring -> stays whitespace (S1 fix)
    structural = [{"a": "ml", "c": "biology", "bridges": ["b"]}]
    future = ["In future work this will be done more formally in biology settings."]
    out = gc.reconcile_channels(structural=structural, future_work=future)
    srecs = [g for g in out if g["gap_type"] == "structural"]
    assert srecs and all(g["evidentiary_status"] == "whitespace" for g in srecs)   # "ml" not a whole word here

def test_reconcile_drops_already_addressed():
    structural = [{"a": "x", "c": "y", "bridges": ["b"]}]
    assert gc.reconcile_channels(structural=structural, addressed={"x | y"}) == []

def test_score_gap_keeps_two_axes_plus_advisory_priority():
    g = {"text": "gap", "gap_type": "structural", "evidentiary_status": "whitespace"}
    scored = gc.score_gap(g, novelty=0.8, utility=0.5)
    assert scored["novelty_score"] == 0.8 and scored["utility_score"] == 0.5   # BOTH axes kept (not collapsed)
    assert scored["priority"] == 0.4                                           # advisory novelty*utility hint
    assert scored["text"] == "gap"                                             # original fields preserved
    # clamped
    assert gc.score_gap(g, novelty=2.0, utility=-1.0)["priority"] == 0.0

def test_to_next_question_candidates_maps_to_loop_evolution_shape():
    reconciled = [
        {"text": "contradiction on: drug Z", "gap_type": "contradiction", "evidentiary_status": "contradiction",
         "channels": ["contradiction"], "provenance": {}},
        {"text": "the unexplored link between A and B", "gap_type": "structural",
         "evidentiary_status": "whitespace", "channels": ["structural"], "provenance": {}}]
    cands = gc.to_next_question_candidates(reconciled)
    # loop_evolution gap-record shape: {kind, text, seed_evidence}; contradiction kind preserved (ranks first there)
    assert cands[0]["kind"] == "contradiction" and cands[0]["text"]
    assert cands[1]["kind"] == "gap"
    assert all(set(c.keys()) >= {"kind", "text", "seed_evidence"} for c in cands)
