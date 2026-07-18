import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import stage_a

def test_extract_resolvable_ids_doi_and_arxiv():
    assert stage_a.extract_resolvable_ids("see 10.1038/s41586-021-03819-2 and arXiv:2409.04109") == \
        ["10.1038/s41586-021-03819-2", "2409.04109"]

def test_extract_resolvable_ids_none():
    assert stage_a.extract_resolvable_ids("no identifiers here, just prose") == []

def test_extract_resolvable_ids_strips_trailing_punct_and_dedupes():
    assert stage_a.extract_resolvable_ids("10.1234/x, 10.1234/x. and 2409.04109;") == ["10.1234/x", "2409.04109"]

def test_extract_resolvable_ids_ignores_too_short_doi_prefix():
    # cite-or-fail: a real DOI registrant prefix is >=4 digits; "10.1/x" is not a DOI -> not matched
    assert stage_a.extract_resolvable_ids("see 10.1/x (not a real DOI)") == []

def test_parse_prior_art_asserted_with_id_counts():
    r = stage_a.parse_prior_art('{"prior_art_found": true, "nearest_id": "10.1234/x", "nearest_title": "T", "difference": "D"}')
    assert r["has_prior_art"] is True and r["nearest_id"] == "10.1234/x" and r["difference"] == "D"

def test_parse_prior_art_asserted_without_resolvable_id_is_discarded():
    # cite-or-fail: model claims prior art but gives no resolvable id -> DISCARDED (counts as no prior art)
    r = stage_a.parse_prior_art('{"prior_art_found": true, "nearest_id": "see related work", "nearest_title": "X"}')
    assert r["has_prior_art"] is False

def test_parse_prior_art_none_found():
    r = stage_a.parse_prior_art('{"prior_art_found": false, "nearest_id": "", "difference": ""}')
    assert r["has_prior_art"] is False and r["nearest_id"] is None

def test_stage_a_report_verdicts():
    att_adds = {"machinery_adds_value": True, "machinery_delta_rate": 0.25}
    att_no = {"machinery_adds_value": False, "machinery_delta_rate": -0.1}
    clean = {"clean": True, "false_positives": []}
    leak = {"clean": False, "false_positives": ["b1"]}

    r_b = stage_a.stage_a_report(att_adds, clean, off_distribution=1)
    assert "EARNS-STAGE-B" in r_b["verdict"] and r_b["ruler_clean"] is True
    assert "non-obvious" in r_b["ceiling_caveat"].lower() or "prior-art" in r_b["ceiling_caveat"].lower()

    r_neg = stage_a.stage_a_report(att_no, clean, off_distribution=0)
    assert "HONEST-NEGATIVE" in r_neg["verdict"]

    r_void = stage_a.stage_a_report(att_adds, leak, off_distribution=0)
    assert "VOID" in r_void["verdict"] and r_void["ruler_clean"] is False  # VOID dominates even if machinery adds value

def test_attribution_rate_delta_and_div_guard():
    arm_i = [{"survived": True}, {"survived": False}, {"survived": False}, {"survived": False}]   # 1/4 = 0.25
    arm_ii = [{"survived": True}, {"survived": True}, {"survived": False}, {"survived": False}]   # 2/4 = 0.50
    a = stage_a.attribution(arm_i, arm_ii)
    assert a["arm_i"]["survival_rate"] == 0.25 and a["arm_ii"]["survival_rate"] == 0.50
    assert a["machinery_delta_rate"] == 0.25 and a["machinery_adds_value"] is True
    # empty arms -> rate 0.0, no div-by-zero, no value added
    z = stage_a.attribution([], [])
    assert z["arm_i"]["survival_rate"] == 0.0 and z["machinery_adds_value"] is False

def test_control_verdict_clean_and_void():
    clean = [
        {"id": "b1", "control": "neg", "survived": False},   # obvious control correctly caught -> good
        {"id": "b2", "control": "neg", "survived": False},
        {"id": "b3", "control": "pos", "survived": False},   # prior-art-recall probe: prior art FOUND -> recall hit
        {"id": "b4", "control": None, "survived": True},     # a real candidate -> ignored by the verdict
    ]
    v = stage_a.control_verdict(clean)
    assert v["clean"] is True and v["false_positives"] == [] and v["prior_art_recall"] == 1.0

    leak = [{"id": "b1", "control": "neg", "survived": True},   # a known-obvious control SURVIVED -> ruler broken
            {"id": "b2", "control": "pos", "survived": True}]   # probe SURVIVED -> prior art MISSED -> recall 0
    v2 = stage_a.control_verdict(leak)
    assert v2["clean"] is False and v2["false_positives"] == ["b1"] and v2["prior_art_recall"] == 0.0

def test_blind_candidates_strips_labels_and_is_deterministic():
    cands = [
        {"claim": "c1", "mechanism": "m1", "arm": "i", "pair": "a:b", "control": None},
        {"claim": "c2", "mechanism": "m2", "arm": "ii", "pair": "a:b", "control": None},
        {"claim": "c3", "mechanism": "m3", "arm": None, "pair": None, "control": "neg"},
    ]
    blinded, origin = stage_a.blind_candidates(cands, seed=7)
    # labels stripped from the blinded items the adjudicator sees
    for b in blinded:
        assert set(b.keys()) == {"id", "claim", "mechanism"}
    # origin map recovers arm/pair/control by blinded id
    claims_by_id = {b["id"]: b["claim"] for b in blinded}
    for bid, o in origin.items():
        assert set(o.keys()) == {"arm", "pair", "control"}
    # deterministic: same seed -> same order
    blinded2, _ = stage_a.blind_candidates(cands, seed=7)
    assert [b["id"] for b in blinded] == [b["id"] for b in blinded2]
    assert [b["claim"] for b in blinded] == [b["claim"] for b in blinded2]
    # all original claims preserved exactly once
    assert sorted(b["claim"] for b in blinded) == ["c1", "c2", "c3"]

def test_prior_art_prompt_demands_resolvable_id():
    p = stage_a.prior_art_prompt("a cross-domain claim", "the mechanism")
    assert "a cross-domain claim" in p and "the mechanism" in p
    assert "DOI" in p and "arXiv" in p
    assert "prior_art_found" in p  # strict JSON contract
    # cite-or-fail instruction present
    assert "resolvable" in p.lower() or "cannot" in p.lower()

def test_raw_propose_prompt_is_plain_no_structure_mapping():
    p = stage_a.raw_propose_prompt("immunology", "NLP", n=3)
    assert "immunology" in p and "NLP" in p and "3" in p
    assert "STRICT JSON" in p
    # the raw baseline must NOT invoke structure-mapping / relational-transfer framing (that's arm ii's edge)
    assert "structure" not in p.lower() and "relational" not in p.lower() and "analog" not in p.lower()

def test_survives_objective():
    assert stage_a.survives_objective({"has_prior_art": False}) is True
    assert stage_a.survives_objective({"has_prior_art": True}) is False
    assert stage_a.survives_objective({}) is True  # absence of prior art -> survives

def test_parse_prior_art_fenced_and_nonjson_fallback():
    fenced = '```json\n{"prior_art_found": true, "nearest_id": "arXiv:2409.04109"}\n```'
    assert stage_a.parse_prior_art(fenced)["has_prior_art"] is True
    # non-JSON garbage with a bare id present -> conservative: id present implies prior art
    assert stage_a.parse_prior_art("garbage 10.1038/abc def")["has_prior_art"] is True

# ── Task 1: relevance_prompt + parse_relevance ──────────────────────────────

def test_parse_relevance_routine_application_with_id_is_prior_art():
    r = stage_a.parse_relevance(
        '{"category": "routine-application", "nearest_id": "10.1234/foo", '
        '"nearest_topic": "SGD", "why": "standard method"}')
    assert r["has_prior_art"] is True
    assert r["category"] == "routine-application"
    assert r["nearest_id"] == "10.1234/foo"

def test_parse_relevance_specific_prior_transfer_with_id_is_prior_art():
    r = stage_a.parse_relevance(
        '{"category": "specific-prior-transfer", "nearest_id": "2409.04109", '
        '"nearest_topic": "SIR in ecology", "why": "exact transfer published"}')
    assert r["has_prior_art"] is True
    assert r["category"] == "specific-prior-transfer"

def test_parse_relevance_no_covering_prior_art_survives_regardless_of_id():
    # 'no-covering-prior-art' -> survives (has_prior_art False) even if a nearest_id is present
    r = stage_a.parse_relevance(
        '{"category": "no-covering-prior-art", "nearest_id": "10.9999/nearby", '
        '"nearest_topic": "vaguely related", "why": "no covering prior"}')
    assert r["has_prior_art"] is False
    assert r["category"] == "no-covering-prior-art"

def test_parse_relevance_covered_category_but_no_resolvable_id_cite_or_fail():
    # cite-or-fail: covered category but no resolvable id -> discarded -> False
    r = stage_a.parse_relevance(
        '{"category": "routine-application", "nearest_id": "", '
        '"nearest_topic": "some method", "why": "no actual id given"}')
    assert r["has_prior_art"] is False

def test_parse_relevance_tolerates_fenced_json():
    raw = '```json\n{"category": "specific-prior-transfer", "nearest_id": "10.1038/s41586-021-03819-2", ' \
          '"nearest_topic": "AlphaFold", "why": "exact paper"}\n```'
    r = stage_a.parse_relevance(raw)
    assert r["has_prior_art"] is True
    assert r["nearest_id"] == "10.1038/s41586-021-03819-2"

def test_parse_relevance_non_dict_or_bad_json_returns_safe_fallback():
    r = stage_a.parse_relevance("not json at all")
    assert r["has_prior_art"] is False
    assert r["category"] is None

def test_parse_relevance_unknown_category_survives():
    # a hallucinated/unexpected category is NOT covered -> has_prior_art False -> survives (review LOW #4)
    r = stage_a.parse_relevance(
        '{"category": "ambiguous", "nearest_id": "10.1234/x", "nearest_topic": "?", "why": "model went off-menu"}')
    assert r["has_prior_art"] is False
    assert r["category"] == "ambiguous"

def test_parse_relevance_accepts_dict_input():
    # robustness (review LOW #2): a dict passed directly is used as-is, not str()-repr'd into a parse failure
    r = stage_a.parse_relevance({"category": "routine-application", "nearest_id": "10.1234/y"})
    assert r["has_prior_art"] is True and r["category"] == "routine-application"

def test_relevance_prompt_contains_claim_categories_and_strict_json():
    claim = "apply dropout regularization to transformer language models"
    mechanism = "stochastic noise injection"
    p = stage_a.relevance_prompt(claim, mechanism)
    assert claim in p
    assert mechanism in p
    assert "routine-application" in p
    assert "specific-prior-transfer" in p
    assert "no-covering-prior-art" in p
    assert "STRICT JSON" in p
