import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import stage_b

def test_canonicalize_prompt_demands_fixed_schema():
    p = stage_b.canonicalize_prompt("Use immune signaling for NN activation", "immune signaling")
    assert "immune signaling" in p and "Use immune signaling for NN activation" in p
    assert "STRICT JSON" in p
    # the six normalized fields are named so every claim lands in one register
    for f in ("domain_a_concept", "domain_b_target", "mechanism", "direction", "boundary", "measurable_test"):
        assert f in p

def test_parse_canonical_happy_and_fallback():
    r = stage_b.parse_canonical('{"domain_a_concept":"immune signaling","domain_b_target":"NN activation",'
                                '"mechanism":"gating","direction":"increases","boundary":"deep nets",'
                                '"measurable_test":"accuracy"}', orig_claim="OC", orig_mech="OM")
    assert r["ok"] is True and "gating" in r["canonical_mechanism"]
    assert "immune signaling" in r["canonical_claim"] and "NN activation" in r["canonical_claim"]
    # parse failure -> fall back to the original, flagged ok=False
    bad = stage_b.parse_canonical("not json at all", orig_claim="OC", orig_mech="OM")
    assert bad["ok"] is False and bad["canonical_claim"] == "OC" and bad["canonical_mechanism"] == "OM"

def test_parse_resolution_openalex_inverted_index():
    rec = {"id": "https://openalex.org/W1", "title": "A Title",
           "abstract_inverted_index": {"Hello": [0], "world": [1]}}
    r = stage_b.parse_resolution(rec)
    assert r["resolved"] is True and r["title"] == "A Title" and r["abstract"] == "Hello world"

def test_parse_resolution_crossref_and_empty():
    cr = {"title": ["CR Title"], "abstract": "<p>CR abstract</p>"}
    r = stage_b.parse_resolution(cr)
    assert r["resolved"] is True and r["title"] == "CR Title" and "CR abstract" in r["abstract"]
    assert stage_b.parse_resolution(None)["resolved"] is False
    assert stage_b.parse_resolution({})["resolved"] is False

def test_confirm_prompt_and_parse():
    p = stage_b.confirm_prompt("claim X", "mech Y", "Resolved Title", "Resolved abstract text")
    assert "claim X" in p and "Resolved Title" in p and "Resolved abstract text" in p
    assert "anticipates" in p and "same mechanism" in p.lower() and "direction" in p.lower()
    assert stage_b.parse_confirm('{"anticipates": true, "why": "same mech+dir"}')["anticipates"] is True
    assert stage_b.parse_confirm('{"anticipates": false}')["anticipates"] is False
    # non-dict / parse failure -> anticipates False (conservative: does NOT kill the candidate)
    assert stage_b.parse_confirm("garbage")["anticipates"] is False

def test_objective_survives_truth_table():
    # relevance found covered prior art AND the resolved record confirms anticipation -> KILLED (not survive)
    assert stage_b.objective_survives({"has_prior_art": True}, {"anticipates": True}) is False
    # relevance found covered prior art but the resolved record does NOT anticipate (keyword coincidence) -> survives
    assert stage_b.objective_survives({"has_prior_art": True}, {"anticipates": False}) is True
    # relevance found NO covered prior art -> survives (confirm irrelevant)
    assert stage_b.objective_survives({"has_prior_art": False}, {"anticipates": True}) is True
    assert stage_b.objective_survives({}, {}) is True

def test_objective_survives_routine_application_caught_on_category():
    # CALIBRATION-2026-06-28 fix: 'routine-application' is caught on the CATEGORY alone — a textbook method is not
    # anticipated by one citable paper, and the adjudicator's imperfect/unresolvable citation must NOT let it survive
    # (requiring resolve+confirm here leaked 10/10 obvious negatives in the controls-only calibration).
    assert stage_b.objective_survives({"has_prior_art": True, "category": "routine-application"},
                                      {"anticipates": False}) is False
    assert stage_b.objective_survives({"has_prior_art": True, "category": "routine-application"}, {}) is False
    # 'specific-prior-transfer' claims ONE anticipating paper -> still requires the resolved record to CONFIRM
    # (fake-id / keyword-coincidence guard kept)
    assert stage_b.objective_survives({"has_prior_art": True, "category": "specific-prior-transfer"},
                                      {"anticipates": False}) is True
    assert stage_b.objective_survives({"has_prior_art": True, "category": "specific-prior-transfer"},
                                      {"anticipates": True}) is False
    # no category (the kNN leg passes none) -> treated as specific (resolve+confirm required)
    assert stage_b.objective_survives({"has_prior_art": True}, {"anticipates": False}) is True
    # no prior art -> survives regardless of category
    assert stage_b.objective_survives({"has_prior_art": False, "category": "routine-application"}, {}) is True

def test_panel_survives_all_must_survive():
    assert stage_b.panel_survives([True, True]) is True
    assert stage_b.panel_survives([True, False]) is False     # EITHER finds prior art -> killed
    assert stage_b.panel_survives([]) is True                 # no adjudicator opinion -> survives (vacuous)

def test_cohens_kappa():
    # perfect agreement -> 1.0
    assert abs(stage_b.cohens_kappa([1, 0, 1, 0], [1, 0, 1, 0]) - 1.0) < 1e-9
    # complete disagreement on a balanced set -> negative
    assert stage_b.cohens_kappa([1, 1, 0, 0], [0, 0, 1, 1]) < 0
    # constant raters (no variance) -> defined as 1.0 if identical else 0.0
    assert stage_b.cohens_kappa([1, 1, 1], [1, 1, 1]) == 1.0

def test_soundness_prompt_is_rubric_decomposed_not_novelty():
    p = stage_b.soundness_prompt("claim Z", "mech W")
    assert "claim Z" in p and "mech W" in p and "STRICT JSON" in p
    # rubric-decomposed (mechanism/scale/direction/falsifiable), NOT a novelty or non-obviousness judgment
    for k in ("mechanism", "scale", "direction", "falsifiable"):
        assert k in p.lower()
    assert "novel" not in p.lower() and "non-obvious" not in p.lower()

def test_parse_soundness_and_panel_verdict():
    assert stage_b.parse_soundness('{"sound": true, "score": 0.9, "why": "ok"}')["sound"] is True
    assert stage_b.parse_soundness("garbage")["sound"] is False              # fail-closed
    v = stage_b.soundness_panel_verdict([{"sound": True}, {"sound": True}, {"sound": False}], threshold=2)
    assert v["sound"] is True and v["n_sound"] == 2 and v["n_total"] == 3
    assert stage_b.soundness_panel_verdict([], threshold=2)["sound"] is False  # empty -> fail-closed
    assert stage_b.soundness_panel_verdict([{"sound": True}], threshold=2)["sound"] is False

def test_genuine_survivor():
    assert stage_b.genuine_survivor(True, {"sound": True}) is True
    assert stage_b.genuine_survivor(True, {"sound": False}) is False
    assert stage_b.genuine_survivor(False, {"sound": True}) is False

def test_select_topk_deterministic_stable_ties():
    cands = [{"c": "a"}, {"c": "b"}, {"c": "c"}, {"c": "d"}]
    scores = {"a": 0.1, "b": 0.9, "c": 0.5, "d": 0.9}   # b and d tie at 0.9
    top = stage_b.select_topk(cands, lambda x: scores[x["c"]], k=2)
    # highest first; tie (b,d) broken by stable original order -> b before d
    assert [t["c"] for t in top] == ["b", "d"]
    # k > len -> all, in full descending-score order (ties stable): a(0.1) last, c(0.5), then b,d(0.9) by orig order
    assert [t["c"] for t in stage_b.select_topk(cands, lambda x: scores[x["c"]], k=99)] == ["b", "d", "c", "a"]

def test_fisher_exact_p_one_sided_known_value():
    # 2x2 [[2,0],[0,2]]: row sums (2,2), col sums (2,2), N=4. P(a>=2) = C(2,2)C(2,0)/C(4,2) = 1/6.
    p = stage_b.fisher_exact_p(2, 0, 0, 2, alternative="greater")
    assert abs(p - (1.0 / 6.0)) < 1e-9
    # no difference table -> not significant
    assert stage_b.fisher_exact_p(1, 1, 1, 1, alternative="greater") > 0.5

def test_cmh_single_stratum_known_z():
    # one stratum [[2,0],[0,2]]: E = (2)(2)/4 = 1, a-E = 1; V = (2)(2)(2)(2)/(4^2 * 3) = 1/3.
    # z = 1/sqrt(1/3) = 1.7320508; p_one_sided(greater) = 1 - Phi(z) ~ 0.04163.
    r = stage_b.cochran_mantel_haenszel([((2, 0), (0, 2))])
    assert abs(r["z"] - 1.7320508) < 1e-4
    assert abs(r["p_one_sided"] - 0.041632) < 1e-3
    assert r["n_strata"] == 1

def test_cmh_two_identical_strata_stronger_than_one():
    one = stage_b.cochran_mantel_haenszel([((3, 1), (1, 3))])
    two = stage_b.cochran_mantel_haenszel([((3, 1), (1, 3)), ((3, 1), (1, 3))])
    assert two["p_one_sided"] < one["p_one_sided"]   # more evidence -> smaller p

def test_cluster_bootstrap_seeded_and_excludes_zero():
    # each pair_record: {"ii": (surv, n), "istar": (surv, n)} — big consistent delta -> CI excludes 0
    big = [{"ii": (8, 10), "istar": (2, 10)} for _ in range(8)]
    r1 = stage_b.cluster_bootstrap_delta_ci(big, seed=7, iters=500)
    r2 = stage_b.cluster_bootstrap_delta_ci(big, seed=7, iters=500)
    assert r1 == r2                              # seeded reproducible
    assert r1["delta"] > 0.5 and r1["excludes_zero"] is True and r1["lo"] > 0
    # identical arms -> CI includes 0
    same = [{"ii": (5, 10), "istar": (5, 10)} for _ in range(8)]
    assert stage_b.cluster_bootstrap_delta_ci(same, seed=7, iters=500)["excludes_zero"] is False

def test_icc_high_when_within_pair_homogeneous():
    # pairs perfectly homogeneous internally but differing between -> ICC near 1
    high = [[1, 1, 1], [0, 0, 0], [1, 1, 1], [0, 0, 0]]
    assert stage_b.intraclass_correlation(high) > 0.9
    # pairs internally mixed identically -> ICC near 0
    low = [[1, 0, 1, 0], [0, 1, 0, 1], [1, 0, 1, 0]]
    assert stage_b.intraclass_correlation(low) < 0.2

def test_attribution4_rates_and_primary_delta():
    arms = {
        "i":      [{"survived": True, "genuine": False}, {"survived": False, "genuine": False}],   # distant .5 sound 0
        "i_star": [{"survived": True, "genuine": True},  {"survived": False, "genuine": False},
                   {"survived": False, "genuine": False}, {"survived": False, "genuine": False}],  # distant .25 sound .25
        "ii":     [{"survived": True, "genuine": True},  {"survived": True, "genuine": True},
                   {"survived": False, "genuine": False}, {"survived": False, "genuine": False}],  # distant .5 sound .5
        "iii":    [{"survived": True, "genuine": False}, {"survived": False, "genuine": False}],   # distant .5 sound 0
    }
    a = stage_b.attribution4(arms)
    assert a["ii"]["sound_distant_rate"] == 0.5 and a["i_star"]["sound_distant_rate"] == 0.25
    assert a["sound_delta_ii_istar"] == 0.25 and a["primary_delta"] == 0.25      # PRIMARY = ii - i*
    assert a["ii"]["genuine"] == 2
    z = stage_b.attribution4({"i": [], "i_star": [], "ii": [], "iii": []})
    assert z["primary_delta"] == 0.0 and z["ii"]["sound_distant_rate"] == 0.0     # empty-arm div-guard

def test_control_verdict_b_binomial_void_and_panel_validity():
    # control_results: {control, survived (objective), sound (panel verdict bool)}
    results = (
        [{"control": "neg", "survived": False, "sound": True} for _ in range(9)] +          # all caught + sound-true
        [{"control": "neg", "survived": True,  "sound": True}] +                             # 1 neg leak (<=1 ok)
        [{"control": "pos", "survived": False, "sound": True} for _ in range(15)] +          # recall 1.0
        [{"control": "fringe", "survived": True, "sound": False} for _ in range(5)] +        # fringe caught (unsound)
        [{"control": "hard_neg", "survived": True, "sound": False} for _ in range(9)] +      # hard_neg caught
        [{"control": "hard_neg", "survived": True, "sound": True}]                           # 1 hard_neg missed
    )
    v = stage_b.control_verdict_b(results, neg_void_threshold=2)
    assert v["clean"] is True and v["neg_survived"] == 1                       # 1 < 2 -> not VOID
    assert v["prior_art_recall"] == 1.0
    assert v["fringe_caught_rate"] == 1.0 and v["hard_neg_caught_rate"] == 0.9
    assert v["sound_true_pass_rate"] == 1.0 and v["soundness_panel_valid"] is True   # all >=0.8
    # 2 neg leaks -> VOID
    leak2 = [{"control": "neg", "survived": True, "sound": True} for _ in range(2)]
    assert stage_b.control_verdict_b(leak2, neg_void_threshold=2)["clean"] is False

def test_sequential_decision_branches():
    # CI excludes 0 positive -> confirm (no need to extend)
    assert stage_b.sequential_decision({"lo": 0.05, "hi": 0.3, "delta": 0.17}, pairs_done=14, max_pairs=28)["action"] == "confirm"
    # point<=0 -> kill
    assert stage_b.sequential_decision({"lo": -0.2, "hi": 0.05, "delta": -0.01}, pairs_done=14, max_pairs=28)["action"] == "kill"
    # straddles 0 with positive point AND budget remaining -> extend
    assert stage_b.sequential_decision({"lo": -0.02, "hi": 0.3, "delta": 0.14}, pairs_done=14, max_pairs=28)["action"] == "extend"
    # straddles 0, positive point, but at the cap -> stop (final test applies)
    assert stage_b.sequential_decision({"lo": -0.02, "hi": 0.3, "delta": 0.14}, pairs_done=28, max_pairs=28)["action"] == "stop"

def _att(primary, ii_genuine, distant_primary=0.2):
    return {"primary_delta": primary, "distant_delta_ii_istar": distant_primary,
            "ii": {"genuine": ii_genuine}, "sound_delta_ii_i": 0.1, "sound_delta_iii_i": 0.05,
            "sound_delta_ii_iii": 0.15, "i": {}, "i_star": {}, "iii": {}}

def test_stage_b_report_verdicts():
    clean = {"clean": True, "soundness_panel_valid": True}
    sig_cmh = {"p_one_sided": 0.01}; sig_ci = {"excludes_zero": True, "delta": 0.2, "lo": 0.05, "hi": 0.35}
    # CONFIRM: delta>0, p<0.05, CI excludes 0, >=5 genuine
    r = stage_b.stage_b_report(_att(0.2, 7), sig_cmh, sig_ci, clean, 1, 0.7, {})
    assert "CONFIRM" in r["verdict"] and r["primary_metric"] == "sound_distant"
    # DIRECTIONAL: positive delta but not significant
    r2 = stage_b.stage_b_report(_att(0.2, 7), {"p_one_sided": 0.3}, {"excludes_zero": False, "delta": 0.2}, clean, 1, 0.7, {})
    assert "DIRECTIONAL" in r2["verdict"]
    # KILL: delta <= 0
    r3 = stage_b.stage_b_report(_att(-0.05, 7), sig_cmh, sig_ci, clean, 1, 0.7, {})
    assert "KILL" in r3["verdict"]
    # VOID dominates
    r4 = stage_b.stage_b_report(_att(0.2, 7), sig_cmh, sig_ci, {"clean": False, "soundness_panel_valid": True}, 1, 0.7, {})
    assert "VOID" in r4["verdict"]
    # UNTRUSTED soundness -> falls back to distant, flagged
    r5 = stage_b.stage_b_report(_att(0.2, 7), sig_cmh, sig_ci, {"clean": True, "soundness_panel_valid": False}, 1, 0.7, {})
    assert r5["primary_metric"] == "distant" and r5["soundness_untrusted"] is True
    # CONFIRM blocked by <5 genuine survivors
    r6 = stage_b.stage_b_report(_att(0.2, 3), sig_cmh, sig_ci, clean, 1, 0.7, {})
    assert "DIRECTIONAL" in r6["verdict"]
    assert "non-obvious" in r["ceiling_caveat"].lower()


def test_knn_prior_art_below_threshold_filter_and_sort():
    nbs = [{"id": "W2", "title": "t2", "distance": 0.30}, {"id": "W1", "title": "t1", "distance": 0.10},
           {"id": "W3", "title": "t3", "distance": 0.50}]
    r = stage_b.knn_prior_art(nbs, sim_threshold=0.20)
    assert r["has_candidate"] is True
    assert [c["id"] for c in r["candidates"]] == ["W1"]                       # only distance < 0.20
    assert r["nearest_id"] == "W1" and abs(r["nearest_distance"] - 0.10) < 1e-9
    # nothing below threshold -> no candidate, nearest still reported
    r2 = stage_b.knn_prior_art(nbs, sim_threshold=0.05)
    assert r2["has_candidate"] is False and r2["candidates"] == [] and r2["nearest_id"] == "W1"
    # multiple below threshold -> distance-sorted ascending
    r3 = stage_b.knn_prior_art(nbs, sim_threshold=0.40)
    assert [c["id"] for c in r3["candidates"]] == ["W1", "W2"]
    # empty / None / malformed fail-safe
    z = stage_b.knn_prior_art([], sim_threshold=0.2)
    assert z["has_candidate"] is False and z["nearest_id"] == "" and z["nearest_distance"] is None
    assert stage_b.knn_prior_art(None, sim_threshold=0.2)["has_candidate"] is False
    assert stage_b.knn_prior_art([{"id": "W9"}], sim_threshold=0.2)["has_candidate"] is False  # no distance -> dropped


def test_cluster_bootstrap_custom_keys_and_backcompat():
    # NEW: custom keys compute eng_strong - raw_strong
    recs = [{"eng_strong": (8, 10), "raw_strong": (2, 10)} for _ in range(8)]
    r = stage_b.cluster_bootstrap_delta_ci(recs, seed=7, iters=500,
                                           treat_key="eng_strong", base_key="raw_strong")
    assert r["delta"] > 0.5 and r["excludes_zero"] is True and r["lo"] > 0
    # BACK-COMPAT: default keys (ii/istar) still work, same as v3
    old = [{"ii": (8, 10), "istar": (2, 10)} for _ in range(8)]
    r_old = stage_b.cluster_bootstrap_delta_ci(old, seed=7, iters=500)
    assert r_old["delta"] > 0.5 and r_old["excludes_zero"] is True
    # identical arms via custom keys -> CI includes 0
    same = [{"eng_strong": (5, 10), "raw_strong": (5, 10)} for _ in range(8)]
    assert stage_b.cluster_bootstrap_delta_ci(same, seed=7, iters=500,
                                              treat_key="eng_strong", base_key="raw_strong")["excludes_zero"] is False


def test_attribution_2x2_rates_and_primary_delta():
    arms = {
        "raw_weak":   [{"survived": True,  "genuine": False}, {"survived": False, "genuine": False}],  # distant .5
        "eng_weak":   [{"survived": True,  "genuine": False}, {"survived": True,  "genuine": False},
                       {"survived": False, "genuine": False}, {"survived": False, "genuine": False}],  # distant .5
        "eng_strong": [{"survived": True,  "genuine": True},  {"survived": True,  "genuine": True},
                       {"survived": True,  "genuine": True},  {"survived": False, "genuine": False}],  # distant .75
        "raw_strong": [{"survived": True,  "genuine": True},  {"survived": False, "genuine": False},
                       {"survived": False, "genuine": False}, {"survived": False, "genuine": False}],  # distant .25
    }
    a = stage_b.attribution_2x2(arms)
    assert a["eng_strong"]["distant_rate"] == 0.75 and a["raw_strong"]["distant_rate"] == 0.25
    assert a["distant_delta_engstrong_rawstrong"] == 0.5 and a["primary_delta"] == 0.5     # PRIMARY = eng_strong - raw_strong
    assert a["eng_strong"]["survivors"] == 3
    # interaction = (eng_strong - raw_strong) - (eng_weak - raw_weak) = 0.5 - 0.0 = 0.5
    assert a["distant_interaction"] == 0.5
    # empty arms -> zero deltas, div-guarded
    z = stage_b.attribution_2x2({"raw_weak": [], "eng_weak": [], "eng_strong": [], "raw_strong": []})
    assert z["primary_delta"] == 0.0 and z["eng_strong"]["distant_rate"] == 0.0


def _att2(primary, eng_strong_surv):
    return {"primary_delta": primary, "eng_strong": {"survivors": eng_strong_surv},
            "distant_delta_engstrong_rawstrong": primary, "distant_delta_engstrong_engweak": 0.1,
            "distant_delta_engweak_rawweak": 0.1, "distant_delta_rawstrong_rawweak": 0.2,
            "distant_interaction": 0.0}

def _atts(delta, eng_sound, eng_excl=0.1):
    return {"primary_delta": delta, "eng_strong": {"sound": eng_sound},
            "exclusion_by_arm": {"eng_strong": eng_excl, "raw_strong": 0.1}}

def test_stage_b_report_1b_verdicts():
    valid = {"panel_valid_v2": True}; sig = {"p_one_sided": 0.01}; ci_ok = {"excludes_zero": True, "delta": 0.2}
    assert "CONFIRM" in stage_b.stage_b_report_1b(_atts(0.2, 7), sig, ci_ok, valid)["verdict"]
    assert "KILL" in stage_b.stage_b_report_1b(_atts(-0.05, 7), sig, ci_ok, valid)["verdict"]
    assert "DIRECTIONAL" in stage_b.stage_b_report_1b(_atts(0.2, 7), {"p_one_sided": 0.3}, {"excludes_zero": False}, valid)["verdict"]
    # <5 sound survivors blocks CONFIRM
    assert "DIRECTIONAL" in stage_b.stage_b_report_1b(_atts(0.2, 3), sig, ci_ok, valid)["verdict"]
    # panel not valid -> VOID dominates
    assert "VOID" in stage_b.stage_b_report_1b(_atts(0.2, 7), sig, ci_ok, {"panel_valid_v2": False})["verdict"]
    # engine exclusion > threshold -> EXCLUSION-DOMINATED
    assert "EXCLUSION-DOMINATED" in stage_b.stage_b_report_1b(_atts(0.2, 7, eng_excl=0.6), sig, ci_ok, valid)["verdict"]
    assert "non-obvious" in stage_b.stage_b_report_1b(_atts(0.2, 7), sig, ci_ok, valid)["ceiling_caveat"].lower()


def test_attribution_2x2_sound():
    arms = {
        "raw_weak": [], "eng_weak": [],
        "eng_strong": [{"distant": True, "sound_state": "SOUND"}, {"distant": True, "sound_state": "SOUND"},
                       {"distant": True, "sound_state": "UNSOUND"}, {"distant": True, "sound_state": "EXCLUDE"},
                       {"distant": False, "sound_state": None}],   # adjudicable=3, sound=2 -> 0.667; excl 1/4=0.25
        "raw_strong": [{"distant": True, "sound_state": "SOUND"}, {"distant": True, "sound_state": "UNSOUND"},
                       {"distant": True, "sound_state": "UNSOUND"}, {"distant": True, "sound_state": "UNSOUND"}],  # 1/4=0.25
    }
    a = stage_b.attribution_2x2_sound(arms)
    assert abs(a["eng_strong"]["sound_distant_rate"] - (2/3)) < 1e-9 and a["raw_strong"]["sound_distant_rate"] == 0.25
    assert abs(a["eng_strong"]["exclusion_rate"] - 0.25) < 1e-9 and a["eng_strong"]["sound"] == 2
    assert abs(a["primary_delta"] - (2/3 - 0.25)) < 1e-9
    assert a["exclusion_by_arm"]["eng_strong"] == 0.25
    z = stage_b.attribution_2x2_sound({"raw_weak": [], "eng_weak": [], "eng_strong": [], "raw_strong": []})
    assert z["primary_delta"] == 0.0 and z["eng_strong"]["sound_distant_rate"] == 0.0


def test_control_verdict_soundness_v2_gate():
    rs = ([{"control": "hard_neg", "sound_verdict": "UNSOUND", "unsound_kind": "named_law"} for _ in range(9)] +
          [{"control": "hard_neg", "sound_verdict": "SOUND", "unsound_kind": "none"}] +              # 9/10 caught
          [{"control": "neg", "sound_verdict": "SOUND", "unsound_kind": "none"} for _ in range(9)] +
          [{"control": "neg", "sound_verdict": "UNSOUND", "unsound_kind": "named_law"}])             # 9/10 sound-true; 1 scope-audit flag
    v = stage_b.control_verdict_soundness_v2(rs)
    assert abs(v["hard_neg_caught_rate"] - 0.9) < 1e-9 and abs(v["sound_true_pass_rate"] - 0.9) < 1e-9
    assert v["control_exclusion_rate"] == 0.0 and v["n_scope_audit_flags"] == 1 and v["panel_valid_v2"] is True
    # fails gate when hard_neg < 0.8
    rs2 = ([{"control": "hard_neg", "sound_verdict": "SOUND"} for _ in range(4)] +
           [{"control": "hard_neg", "sound_verdict": "UNSOUND", "unsound_kind": "named_law"} for _ in range(6)] +
           [{"control": "neg", "sound_verdict": "SOUND"} for _ in range(10)])
    assert stage_b.control_verdict_soundness_v2(rs2)["panel_valid_v2"] is False
    # fails gate when exclusion too high
    rs3 = ([{"control": "hard_neg", "sound_verdict": "UNSOUND", "unsound_kind": "named_law"} for _ in range(10)] +
           [{"control": "neg", "sound_verdict": "SOUND"} for _ in range(7)] +
           [{"control": "neg", "sound_verdict": "EXCLUDE"} for _ in range(3)])  # 30% exclusion
    assert stage_b.control_verdict_soundness_v2(rs3)["panel_valid_v2"] is False


def _u(kind="named_law", law="Shannon", conf=0.9, pred="none", role="", tcs="FALSE_STANDARD"):
    return {"verdict": "UNSOUND", "unsound_kind": kind, "governing_constraint": law, "how_exceeded": "x",
            "why_governs": "y", "failed_predicate": pred, "incoherence_role_pair": role, "target_claim_status": tcs,
            "confidence": conf}

def test_soundness_panel_v2_convergence_exclude_default():
    # 2 valid unsound (same law) -> UNSOUND
    assert stage_b.soundness_panel_verdict_v2([_u(), _u(), {"verdict": "SOUND"}])["verdict"] == "UNSOUND"
    # 2 valid unsound on DIFFERENT laws -> STILL UNSOUND (>=2 independent valid convictions; string-convergence dropped
    # 2026-06-29 after calibration found judges phrase the SAME law differently -> false SOUND on unanimous convictions)
    assert stage_b.soundness_panel_verdict_v2([_u(law="Shannon"), _u(law="Carnot"), {"verdict": "SOUND"}])["verdict"] == "UNSOUND"
    # low-confidence unsound is invalid -> recoded, not counted
    assert stage_b.soundness_panel_verdict_v2([_u(conf=0.5), _u(conf=0.5)])["verdict"] == "SOUND"
    # named_law missing how_exceeded -> invalid
    bad = {"verdict": "UNSOUND", "unsound_kind": "named_law", "governing_constraint": "Shannon", "how_exceeded": "",
           "why_governs": "", "confidence": 0.9}
    assert stage_b.soundness_panel_verdict_v2([bad, bad])["verdict"] == "SOUND"
    # 2 incoherent-mapping converging on same (predicate, role) -> UNSOUND
    m = _u(kind="incoherent_mapping", pred="P1", role="selection->averaging", tcs="FALSE_STANDARD")
    assert stage_b.soundness_panel_verdict_v2([m, m])["verdict"] == "UNSOUND"
    # >=2 COHERENT_NOVEL, not unsound -> EXCLUDE
    cn = {"verdict": "SOUND", "target_claim_status": "COHERENT_NOVEL", "confidence": 0.6}
    assert stage_b.soundness_panel_verdict_v2([cn, cn, {"verdict": "SOUND"}])["verdict"] == "EXCLUDE"
    # lone high-conf valid unsound -> flagged, not UNSOUND
    r = stage_b.soundness_panel_verdict_v2([_u(conf=0.95), {"verdict": "SOUND"}, {"verdict": "SOUND"}])
    assert r["verdict"] == "SOUND" and r["flagged"] is True


def test_parse_soundness_v2_valid_and_failclosed():
    good = ('{"verdict":"UNSOUND","unsound_kind":"named_law","governing_constraint":"Shannon source-coding theorem",'
            '"how_exceeded":"claims sub-entropy lossless","why_governs":"applies to lossless codes","confidence":0.9,'
            '"target_claim_status":"FALSE_STANDARD","failed_predicate":"none","why":"violates Shannon"}')
    r = stage_b.parse_soundness_v2(good)
    assert r["verdict"] == "UNSOUND" and r["unsound_kind"] == "named_law" and r["confidence"] == 0.9
    assert r["target_claim_status"] == "FALSE_STANDARD"
    # garbage -> fail-closed ABSTAIN (never a false UNSOUND or SOUND)
    bad = stage_b.parse_soundness_v2("not json at all")
    assert bad["verdict"] == "ABSTAIN" and bad["confidence"] == 0.0
    # unknown verdict / predicate / status normalize safely
    weird = stage_b.parse_soundness_v2('{"verdict":"MAYBE","failed_predicate":"P9","target_claim_status":"X","confidence":"hi"}')
    assert weird["verdict"] == "ABSTAIN" and weird["failed_predicate"] == "none" and weird["target_claim_status"] == "" and weird["confidence"] == 0.0


def test_parse_soundness_v2_rejects_nonfinite_confidence():
    # json.loads accepts bare NaN/Infinity; they must NOT pass the >=0.75 validity gate (nan<0.75 is False -> false UNSOUND)
    for bad in ('{"verdict":"UNSOUND","unsound_kind":"named_law","governing_constraint":"Shannon","how_exceeded":"x",'
                '"why_governs":"y","confidence":NaN}',
                '{"verdict":"UNSOUND","unsound_kind":"named_law","governing_constraint":"Shannon","how_exceeded":"x",'
                '"why_governs":"y","confidence":Infinity}'):
        assert stage_b.parse_soundness_v2(bad)["confidence"] == 0.0
    # two NaN-confidence named-law votes must NOT yield a false panel UNSOUND
    nan_vote = stage_b.parse_soundness_v2('{"verdict":"UNSOUND","unsound_kind":"named_law","governing_constraint":"Shannon",'
                                          '"how_exceeded":"x","why_governs":"y","confidence":NaN}')
    assert stage_b.soundness_panel_verdict_v2([nan_vote, nan_vote])["verdict"] == "SOUND"


def test_soundness_prompt_v2_has_constraint_checking_structure():
    p = stage_b.soundness_prompt_v2("claim X", "mech Y")
    low = p.lower()
    assert "claim x" in low and "mech y" in low
    # retrieve-first + decompose + mapping table + two named paths + novelty carve-out + asymmetry
    for k in ["governing", "mapping", "stripped_target_claim", "coherent_novel",
              "how_exceeded", "failed_predicate", "abstain", "idealization"]:
        assert k in low, k
    assert '"verdict"' in p and "UNSOUND only" in p   # asymmetric: UNSOUND must be earned


def test_stage_b_report_2x2_verdicts():
    clean = {"clean": True}
    sig_cmh = {"p_one_sided": 0.01}; sig_ci = {"excludes_zero": True, "delta": 0.2, "lo": 0.05, "hi": 0.35}
    # CONFIRM: delta>0, p<0.05, CI excludes 0, >=5 eng_strong distant survivors
    r = stage_b.stage_b_report_2x2(_att2(0.2, 7), sig_cmh, sig_ci, clean, 1, 0.06, {})
    assert "CONFIRM" in r["verdict"] and r["primary_metric"] == "distant"
    assert "RESURRECTED" in r["verdict"]
    # KILL: delta <= 0 -> engine value was model strength
    r2 = stage_b.stage_b_report_2x2(_att2(-0.05, 7), sig_cmh, sig_ci, clean, 1, 0.06, {})
    assert "KILL" in r2["verdict"] and "model strength" in r2["verdict"]
    # DIRECTIONAL: positive but not significant
    r3 = stage_b.stage_b_report_2x2(_att2(0.2, 7), {"p_one_sided": 0.3}, {"excludes_zero": False, "delta": 0.2}, clean, 1, 0.06, {})
    assert "DIRECTIONAL" in r3["verdict"]
    # CONFIRM blocked by <5 eng_strong survivors -> DIRECTIONAL
    r4 = stage_b.stage_b_report_2x2(_att2(0.2, 3), sig_cmh, sig_ci, clean, 1, 0.06, {})
    assert "DIRECTIONAL" in r4["verdict"]
    # VOID dominates (neg-control ruler leaked)
    r5 = stage_b.stage_b_report_2x2(_att2(0.2, 7), sig_cmh, sig_ci, {"clean": False}, 1, 0.06, {})
    assert "VOID" in r5["verdict"]
    # ceiling caveat is present + names distant-only
    assert "distant-only" in r["ceiling_caveat"].lower() and "non-obvious" in r["ceiling_caveat"].lower()
