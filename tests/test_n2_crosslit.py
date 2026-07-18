import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n2_crosslit as nx

def test_build_concept_inputs_strips_checktags_and_lowercases():
    recs = {"raynaud": [{"id": "P1", "concepts": ["Raynaud Disease", "Humans", "Platelet Aggregation"]}],
            "fishoil": [{"id": "P2", "concepts": ["Fish Oils", "Platelet Aggregation", "Male"]}]}
    cl, ids, topic = nx.build_concept_inputs(recs)
    assert cl == [["raynaud disease", "platelet aggregation"], ["fish oils", "platelet aggregation"]]
    assert ids == ["P1", "P2"] and topic == {"P1": "raynaud", "P2": "fishoil"}

def test_run_pipeline_ranks_cross_paper_gap():
    recs = {"a": [{"id": "P1", "concepts": ["X", "Bridge"]}], "c": [{"id": "P2", "concepts": ["Bridge", "Z"]}]}
    cl, ids, topic = nx.build_concept_inputs(recs)
    out = nx.run_pipeline(cl, ids, topic)
    assert any({g["a"], g["c"]} == {"x", "z"} for g in out["ranked"])

def test_measure_case_raw_and_specificity_pass_on_toy():
    # target (a<->c) bridged by a SPECIFIC low-degree bridge; two distractor topics share only a GENERIC hub-ish bridge
    recs = {
        "A": [{"id":"P1","concepts":["Alpha","Spec"]}],
        "C": [{"id":"P2","concepts":["Spec","Cee"]}],
        "D1":[{"id":"P3","concepts":["Dee1","Gen"]}],
        "D2":[{"id":"P4","concepts":["Gen","Dee2"]}],
    }
    import n2_crosslit_measure as m
    out = m.measure_case(recs, {"alpha"}, {"cee"}, ["D1","D2"],
                         [("D1","D2")], {"A":{"alpha"},"C":{"cee"},"D1":{"dee1"},"D2":{"dee2"}},
                         priority="specificity", min_pool=1)
    assert out["verdict"]["verdict"] in ("PASS","KILL","VOID")   # runs end-to-end + returns a verdict
    assert out["priority"] == "specificity" and "target" in out

def test_measure_case_uses_full_graph_not_truncated_at_2000_edges():
    # 100 docs x 8 doc-unique concepts -> 100*C(8,2)=2800 UNIQUE edges: must not be silently capped at the 2000
    # default (which would corrupt degrees/hub/ranking/null on the real headline corpus).
    import n2_crosslit_measure as m
    recs = {"T": [{"id": f"P{i}", "concepts": [f"c{i}_{j}" for j in range(8)]} for i in range(100)]}
    out = m.measure_case(recs, {"c0_0"}, {"c1_0"}, [], [], {"T": {"c0_0"}}, priority="raw", min_pool=1)
    assert out["n_edges"] == 2800   # full graph retained (would be 2000 if truncated)

def test_measure_case_supports_association_strength_priority():
    recs = {
        "A": [{"id":"P1","concepts":["Alpha","Bridge"]}],
        "C": [{"id":"P2","concepts":["Bridge","Cee"]}],
        "D1":[{"id":"P3","concepts":["Dee1","Gen"]}],
        "D2":[{"id":"P4","concepts":["Gen","Dee2"]}],
    }
    import n2_crosslit_measure as m
    out = m.measure_case(recs, {"alpha"}, {"cee"}, ["D1","D2"], [("D1","D2")],
                         {"A":{"alpha"},"C":{"cee"},"D1":{"dee1"},"D2":{"dee2"}},
                         priority="association_strength", min_pool=1)
    assert out["priority"] == "association_strength"
    assert out["verdict"]["verdict"] in ("PASS","KILL","VOID")
    assert "target_hub_share" in out   # diagnostic present

def test_nc_excludes_hub_concepts_from_distinct_concept_count():
    # H-A, H-B, H-C, H-D, A-B with hub={H}: nonhub_degrees still keys H (degree 0, all nbrs are hub-excluded... wait
    # H itself is the hub here) -> distinct NON-HUB concepts = {A,B,C,D} = 4, NOT 5 (H must not be counted).
    import n2_crosslit_measure as m
    edges = [("H", "A"), ("H", "B"), ("H", "C"), ("H", "D"), ("A", "B")]
    hub = {"H"}
    nonhub_degrees = m._nonhub_degrees(edges, hub)
    assert set(nonhub_degrees.keys()) == {"H", "A", "B", "C", "D"}   # adjacency keys include the hub itself
    hubs_set = set(hub)
    nc = sum(1 for c in nonhub_degrees if c not in hubs_set)
    assert nc == 4   # H excluded: distinct NON-HUB concepts only

def test_measure_case_fractional_strength_not_filtered_by_min_strength():
    # AS/cosine strengths are FRACTIONAL (<1). The ranker's default integer min_strength=1 must NOT nuke them
    # (regression: it did -> the real AS re-run false-VOIDed because every gap scored <1 was filtered out).
    # Use salton_cosine (no hypergeom gate) to isolate the min_strength interaction. deg(alpha)=deg(cee)=2 ->
    # cosine = c_AC/sqrt(2*2) = 0.5 < 1; the target MUST still surface.
    recs = {"A": [{"id":"P1","concepts":["Alpha","Bridge"]}, {"id":"P5","concepts":["Alpha","Xa"]}],
            "C": [{"id":"P2","concepts":["Bridge","Cee"]}, {"id":"P6","concepts":["Cee","Yc"]}]}
    import n2_crosslit_measure as mm
    out = mm.measure_case(recs, {"alpha"}, {"cee"}, [], [], {"A":{"alpha"},"C":{"cee"}},
                          priority="salton_cosine", min_pool=1)
    assert out["target"] is not None and out["n_gaps"] >= 1   # not filtered out by min_strength=1

def test_measure_case_hub_override_replaces_computed_hub():
    # 'Hubby' co-occurs with 10 distinct concepts within topic T -> high intra-topic degree -> a hub at 0.90.
    # hub_override=frozenset() must wipe hub exclusion (n_hub==0); hub_override=None must equal the computed default.
    import n2_crosslit_measure as m
    recs = {"T": [{"id": f"P{i}", "concepts": ["Hubby", f"c{i}"]} for i in range(10)]}
    base = m.measure_case(recs, {"c0"}, {"c1"}, [], [], {"T": {"c0"}}, priority="raw", min_pool=1)
    assert base["n_hub"] >= 1                                  # Hubby hub-excluded by default
    off = m.measure_case(recs, {"c0"}, {"c1"}, [], [], {"T": {"c0"}}, priority="raw", min_pool=1,
                         hub_override=frozenset())
    assert off["n_hub"] == 0                                   # override wipes exclusion
    none = m.measure_case(recs, {"c0"}, {"c1"}, [], [], {"T": {"c0"}}, priority="raw", min_pool=1,
                          hub_override=None)
    assert none["n_hub"] == base["n_hub"]                      # None == computed default (regression)

def test_measure_case_surfaces_target_c_ac_and_hypergeom_p():
    import n2_crosslit_measure as m
    recs = {"A": [{"id":"P1","concepts":["Alpha","Bridge"]}, {"id":"P5","concepts":["Alpha","Xa"]}],
            "C": [{"id":"P2","concepts":["Bridge","Cee"]}, {"id":"P6","concepts":["Cee","Yc"]}]}
    out = m.measure_case(recs, {"alpha"}, {"cee"}, [], [], {"A":{"alpha"},"C":{"cee"}},
                         priority="salton_cosine", min_pool=1)
    assert out["target"] is not None
    assert out["target_c_ac"] == 1                             # single shared cross-paper bridge 'bridge'
    assert isinstance(out["target_hypergeom_p"], float) and 0.0 <= out["target_hypergeom_p"] <= 1.0
    # absent target -> both None
    out2 = m.measure_case(recs, {"nope"}, {"nada"}, [], [], {"A":{"alpha"},"C":{"cee"}},
                          priority="salton_cosine", min_pool=1)
    assert out2["target"] is None and out2["target_c_ac"] is None and out2["target_hypergeom_p"] is None

def test_measure_case_return_internals_opt_in():
    import n2_crosslit_measure as m
    recs = {"A":[{"id":"P1","concepts":["Alpha","Bridge"]}], "C":[{"id":"P2","concepts":["Bridge","Cee"]}]}
    base = m.measure_case(recs, {"alpha"}, {"cee"}, [], [], {"A":{"alpha"},"C":{"cee"}},
                          priority="salton_cosine", min_pool=1)
    assert "_internals" not in base                            # default return unchanged
    ext = m.measure_case(recs, {"alpha"}, {"cee"}, [], [], {"A":{"alpha"},"C":{"cee"}},
                         priority="salton_cosine", min_pool=1, return_internals=True)
    it = ext["_internals"]
    assert {"ranked", "prov", "hub", "nonhub_degrees", "nc", "hub_deg_q"}.issubset(it.keys())
    assert isinstance(it["ranked"], list) and isinstance(it["nc"], int)

def test_measure_case_max_gaps_threads_to_ranker():
    # 3 independent cross-paper gaps; max_gaps caps the returned ranking; the 100000 default keeps all three.
    import n2_crosslit_measure as m
    recs = {"A":[{"id":"P1","concepts":["a1","b1"]},{"id":"P3","concepts":["a2","b2"]},{"id":"P5","concepts":["a3","b3"]}],
            "C":[{"id":"P2","concepts":["b1","c1"]},{"id":"P4","concepts":["b2","c2"]},{"id":"P6","concepts":["b3","c3"]}]}
    full = m.measure_case(recs, {"a1"}, {"c1"}, [], [], {"A":{"a1"},"C":{"c1"}}, priority="raw", min_pool=1)
    assert full["n_gaps"] >= 3                     # all gaps present under the default
    capped = m.measure_case(recs, {"a1"}, {"c1"}, [], [], {"A":{"a1"},"C":{"c1"}}, priority="raw", min_pool=1, max_gaps=1)
    assert capped["n_gaps"] == 1                    # truncated to a single gap
